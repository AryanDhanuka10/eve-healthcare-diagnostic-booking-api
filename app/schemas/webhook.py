from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BookingStatus, PaymentStatus


class WebhookPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(
        min_length=1, max_length=128, description="Provider-unique event id (idempotency key)"
    )
    event_type: Literal["payment.succeeded", "payment.failed"]
    payment_reference: str = Field(min_length=1, max_length=64)


class WebhookOutcome(StrEnum):
    APPLIED = "APPLIED"  # first delivery, state changed
    ALREADY_APPLIED = "ALREADY_APPLIED"  # first delivery of a new event, but payment already in that state
    IGNORED = "IGNORED"  # payment already settled to a *different* final state; recorded, not applied
    DUPLICATE = "DUPLICATE"  # this event id was processed before; no side effects


class WebhookAck(BaseModel):
    event_id: str
    outcome: WebhookOutcome
    payment_status: PaymentStatus | None = None
    booking_status: BookingStatus | None = None
