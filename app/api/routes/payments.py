import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.api.responses import errors
from app.schemas.payment import PaymentCreate, PaymentRead
from app.services import payment_service

router = APIRouter(prefix="/payments", tags=["Payments (simulated)"])


# Spec-mandated path is "/payments/"; the slash-less alias avoids a redirect and is hidden from docs.
@router.post(
    "/",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Pay for a booking (simulated provider)",
    responses=errors(401, 403, 404, 409, 422),
)
@router.post("", response_model=PaymentRead, status_code=status.HTTP_201_CREATED, include_in_schema=False)
def create_payment(data: PaymentCreate, db: DbSession, user: CurrentUser):
    """SIMULATED: no real money moves. The fake provider returns SUCCESS or FAILED (or PENDING, settled later
    by webhook), and the booking is updated in the same transaction."""
    return payment_service.create_payment(db, user, data)


@router.get(
    "/{payment_id}",
    response_model=PaymentRead,
    summary="Get one of my payments",
    responses=errors(401, 404, 422),
)
def get_payment(payment_id: uuid.UUID, db: DbSession, user: CurrentUser):
    return payment_service.get_payment(db, user, payment_id)
