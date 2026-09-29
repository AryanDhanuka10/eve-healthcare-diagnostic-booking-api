import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from app.core.config import get_settings
from app.models.enums import BookingStatus
from app.schemas.diagnostic import CentreRead, TestRead
from app.schemas.payment import PaymentRead


class BookingCreate(BaseModel):
    centre_id: uuid.UUID
    test_id: uuid.UUID
    appointment_at: datetime

    @field_validator("appointment_at")
    @classmethod
    def _validate_appointment(cls, v: datetime) -> datetime:
        # Naive datetimes are ambiguous (whose timezone?), so we reject them outright.
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError(
                "appointment_at must include a timezone offset, e.g. 2026-10-01T09:30:00+05:30 or ...Z"
            )
        settings = get_settings()
        v = v.astimezone(UTC)
        now = datetime.now(UTC)
        if v < now + timedelta(minutes=settings.booking_min_lead_minutes):
            raise ValueError(
                f"appointment_at must be at least {settings.booking_min_lead_minutes} minutes in the future"
            )
        if v > now + timedelta(days=settings.booking_max_advance_days):
            raise ValueError(
                f"appointment_at cannot be more than {settings.booking_max_advance_days} days ahead"
            )
        return v


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    centre: CentreRead
    test: TestRead
    appointment_at: datetime
    amount: Decimal
    status: BookingStatus
    payments: list[PaymentRead]
    created_at: datetime
    updated_at: datetime
