import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession, Page
from app.api.responses import errors
from app.models.enums import BookingStatus
from app.schemas.booking import BookingCreate, BookingRead
from app.schemas.common import Page as PageOut
from app.services import booking_service

router = APIRouter(prefix="/bookings", tags=["Bookings"])


@router.post(
    "",
    response_model=BookingRead,
    status_code=status.HTTP_201_CREATED,
    summary="Book a diagnostic test",
    responses=errors(401, 404, 409, 422),
)
def create_booking(data: BookingCreate, db: DbSession, user: CurrentUser):
    """Creates a PENDING booking. `amount` is taken from the centre's current price, not from the client."""
    return booking_service.create_booking(db, user, data)


@router.get("", response_model=PageOut[BookingRead], summary="List my bookings", responses=errors(401, 422))
def list_bookings(db: DbSession, user: CurrentUser, page: Page, status: BookingStatus | None = None):
    items, total = booking_service.list_bookings(db, user, page.limit, page.offset, status)
    return PageOut(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get(
    "/{booking_id}",
    response_model=BookingRead,
    summary="Get one of my bookings",
    responses=errors(401, 404, 422),
)
def get_booking(booking_id: uuid.UUID, db: DbSession, user: CurrentUser):
    return booking_service.get_booking(db, user, booking_id)


@router.post(
    "/{booking_id}/cancel",
    response_model=BookingRead,
    summary="Cancel one of my bookings",
    responses=errors(401, 404, 409, 422),
)
def cancel_booking(booking_id: uuid.UUID, db: DbSession, user: CurrentUser):
    """PENDING or CONFIRMED bookings can be cancelled. A paid booking's payment is (simulated) refunded."""
    return booking_service.cancel_booking(db, user, booking_id)
