import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PaymentStatus


class PaymentCreate(BaseModel):
    booking_id: uuid.UUID
    simulate_outcome: Literal["SUCCESS", "FAILED", "PENDING"] | None = Field(
        default=None,
        description=(
            "Simulator control. Omit for a random outcome (weighted by PAYMENT_SUCCESS_RATE). "
            "PENDING simulates a provider that settles later via the webhook."
        ),
    )


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    booking_id: uuid.UUID
    amount: Decimal
    status: PaymentStatus
    provider_reference: str
    created_at: datetime
    updated_at: datetime
