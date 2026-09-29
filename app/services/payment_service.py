"""Simulated payments. There is no real gateway: the "provider" is a local function."""

import logging
import random
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.models.booking import Booking
from app.models.enums import BookingStatus, PaymentStatus
from app.models.payment import Payment
from app.models.user import User
from app.schemas.payment import PaymentCreate
from app.services import booking_service
from app.services.db_errors import violated_constraint
from app.services.state_machine import ensure_booking_transition, ensure_payment_transition

logger = logging.getLogger(__name__)


def _simulate_provider(requested: str | None) -> PaymentStatus:
    if requested:
        return PaymentStatus(requested)
    ok = random.random() < get_settings().payment_success_rate
    return PaymentStatus.SUCCESS if ok else PaymentStatus.FAILED


def settle_payment(booking: Booking, payment: Payment, new_status: PaymentStatus) -> None:
    """Apply a final payment result and the matching booking transition together.

    Used by both POST /payments and the webhook so the two can never disagree on the rules.
    Caller must hold row locks on both rows and commit.
    """
    ensure_payment_transition(payment.status, new_status)
    if new_status == PaymentStatus.SUCCESS:
        ensure_booking_transition(booking.status, BookingStatus.CONFIRMED)
        booking.status = BookingStatus.CONFIRMED
    elif new_status == PaymentStatus.FAILED:
        ensure_booking_transition(booking.status, BookingStatus.FAILED)
        booking.status = BookingStatus.FAILED
    payment.status = new_status


def create_payment(db: Session, user: User, data: PaymentCreate) -> Payment:
    if data.simulate_outcome and not get_settings().allow_simulation_override:
        raise PermissionDeniedError(
            "simulate_outcome is disabled in this environment", code="SIMULATION_DISABLED"
        )

    # Lock the booking: concurrent pay/cancel/webhook calls for it now serialise here.
    booking = booking_service.get_booking(db, user, data.booking_id, lock=True)
    if booking.status != BookingStatus.PENDING:
        raise ConflictError(
            f"Booking is {booking.status.value} and cannot be paid", code="BOOKING_NOT_PAYABLE"
        )
    live = db.scalar(
        select(Payment.id).where(
            Payment.booking_id == booking.id,
            Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.SUCCESS]),
        )
    )
    if live:
        raise ConflictError("A payment already exists for this booking", code="PAYMENT_ALREADY_EXISTS")

    outcome = _simulate_provider(data.simulate_outcome)
    payment = Payment(
        booking_id=booking.id,
        amount=booking.amount,  # always the price locked at booking time, never client-supplied
        status=PaymentStatus.PENDING,
        provider_reference=f"sim_{uuid.uuid4().hex}",
    )
    db.add(payment)
    try:
        db.flush()
        if outcome != PaymentStatus.PENDING:
            settle_payment(booking, payment, outcome)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Backstop for the partial unique index; the row lock normally prevents reaching it.
        if violated_constraint(exc) == "uq_payments_one_active_per_booking":
            raise ConflictError(
                "A payment already exists for this booking", code="PAYMENT_ALREADY_EXISTS"
            ) from exc
        raise
    logger.info(
        "payment_processed",
        extra={
            "event": "payment_processed",
            "payment_id": str(payment.id),
            "booking_id": str(booking.id),
            "payment_status": payment.status.value,
            "booking_status": booking.status.value,
        },
    )
    return payment


def get_payment(db: Session, user: User, payment_id: uuid.UUID) -> Payment:
    payment = db.scalars(
        select(Payment).join(Booking).where(Payment.id == payment_id, Booking.user_id == user.id)
    ).one_or_none()
    if payment is None:
        raise NotFoundError("Payment not found", code="PAYMENT_NOT_FOUND")
    return payment
