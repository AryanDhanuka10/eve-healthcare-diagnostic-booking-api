import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WebhookEvent(Base):
    """Ledger of received provider events. UNIQUE(provider_event_id) *is* the idempotency key."""

    __tablename__ = "webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    provider_event_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payment_reference: Mapped[str] = mapped_column(String(64), nullable=False)
    # Lets us tell a harmless retry from a *different* payload re-using an event id.
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(30))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
