from __future__ import annotations

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.enums import PaymentStatus

if TYPE_CHECKING:
    from app.models.booking import Booking


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        # At most one live payment (PENDING or SUCCESS) per booking. This is the
        # database-level guard behind "no duplicate payments", even under races.
        Index(
            "uq_payments_one_active_per_booking",
            "booking_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'SUCCESS')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    booking_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("bookings.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=False, length=20, create_constraint=True),
        default=PaymentStatus.PENDING,
        server_default=PaymentStatus.PENDING.value,
        nullable=False,
    )
    # The simulated provider's reference; webhooks identify payments by this value.
    provider_reference: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    booking: Mapped[Booking] = relationship(back_populates="payments")
