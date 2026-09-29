import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.exceptions import BusinessRuleError, ConflictError, NotFoundError
from app.models.booking import Booking
from app.models.centre_test import CentreTest
from app.models.enums import BookingStatus, PaymentStatus
from app.models.payment import Payment
from app.models.user import User
from app.schemas.booking import BookingCreate
from app.services import catalog_service
from app.services.db_errors import violated_constraint
from app.services.state_machine import ensure_booking_transition, ensure_payment_transition

logger = logging.getLogger(__name__)

_LOAD = (
    selectinload(Booking.payments),
    selectinload(Booking.centre),
    selectinload(Booking.test),
)


def create_booking(db: Session, user: User, data: BookingCreate) -> Booking:
    catalog_service.get_centre(db, data.centre_id)
    catalog_service.get_test(db, data.test_id)
    # FOR SHARE: a concurrent price change must wait, so the amount we snapshot is
    # the price that was current when this booking committed.
    offering = db.get(CentreTest, (data.centre_id, data.test_id), with_for_update={"read": True})
    if offering is None:
        raise BusinessRuleError("This centre does not offer the selected test", code="TEST_NOT_OFFERED")

    booking = Booking(
        user_id=user.id,
        centre_id=data.centre_id,
        test_id=data.test_id,
        appointment_at=data.appointment_at,
        amount=offering.price,
        status=BookingStatus.PENDING,
    )
    db.add(booking)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if violated_constraint(exc) == "uq_bookings_active_slot":
            raise ConflictError(
                "You already have an active booking for this test, centre and time", code="DUPLICATE_BOOKING"
            ) from exc
        raise
    logger.info(
        "booking_created",
        extra={
            "event": "booking_created",
            "booking_id": str(booking.id),
            "user_id": str(user.id),
            "amount": str(booking.amount),
        },
    )
    return get_booking(db, user, booking.id)


def get_booking(db: Session, user: User, booking_id: uuid.UUID, *, lock: bool = False) -> Booking:
    """Fetch a booking owned by `user`.

    Someone else's booking is reported as 404 (not 403) so booking ids cannot be probed.
    With lock=True the booking row is locked (SELECT ... FOR UPDATE) until commit/rollback.
    """
    stmt = select(Booking).where(Booking.id == booking_id, Booking.user_id == user.id).options(*_LOAD)
    if lock:
        stmt = stmt.with_for_update(of=Booking).execution_options(populate_existing=True)
    booking = db.scalars(stmt).one_or_none()
    if booking is None:
        raise NotFoundError("Booking not found", code="BOOKING_NOT_FOUND")
    return booking


def list_bookings(
    db: Session, user: User, limit: int, offset: int, status: BookingStatus | None
) -> tuple[list[Booking], int]:
    where = [Booking.user_id == user.id]
    if status:
        where.append(Booking.status == status)
    rows = db.scalars(
        select(Booking)
        .where(*where)
        .options(*_LOAD)
        .order_by(Booking.created_at.desc(), Booking.id)
        .limit(limit)
        .offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(Booking).where(*where)) or 0
    return list(rows), total


def cancel_booking(db: Session, user: User, booking_id: uuid.UUID) -> Booking:
    # Lock order everywhere: booking first, then its payments. Consistent ordering
    # prevents deadlocks between cancel, pay and webhook.
    booking = get_booking(db, user, booking_id, lock=True)
    ensure_booking_transition(booking.status, BookingStatus.CANCELLED)

    payments = db.scalars(
        select(Payment)
        .where(Payment.booking_id == booking.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    if any(p.status == PaymentStatus.PENDING for p in payments):
        # A provider callback is still in flight; cancelling now could race with it.
        raise ConflictError("A payment for this booking is still in progress", code="PAYMENT_IN_PROGRESS")
    for payment in payments:
        if payment.status == PaymentStatus.SUCCESS:
            ensure_payment_transition(payment.status, PaymentStatus.REFUNDED)
            payment.status = PaymentStatus.REFUNDED  # simulated refund

    booking.status = BookingStatus.CANCELLED
    db.commit()
    logger.info("booking_cancelled", extra={"event": "booking_cancelled", "booking_id": str(booking.id)})
    return get_booking(db, user, booking.id)
