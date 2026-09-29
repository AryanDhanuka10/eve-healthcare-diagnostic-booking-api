from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.diagnostic_centre import DiagnosticCentre
from app.models.diagnostic_test import DiagnosticTest
from app.models.enums import BookingStatus
from app.models.payment import Payment


class Booking(Base, TimestampMixin):
    __tablename__ = "bookings"
    __table_args__ = (
        # A booking can only reference a test that the centre actually offers.
        ForeignKeyConstraint(
            ["centre_id", "test_id"],
            ["centre_tests.centre_id", "centre_tests.test_id"],
            name="fk_bookings_centre_test_offering",
            ondelete="RESTRICT",
        ),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_bookings_user_created", "user_id", "created_at"),
        # Stops the same user double-booking the same test/centre/time (e.g. double click).
        Index(
            "uq_bookings_active_slot",
            "user_id",
            "centre_id",
            "test_id",
            "appointment_at",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'CONFIRMED')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    centre_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diagnostic_centres.id", ondelete="RESTRICT"), nullable=False
    )
    test_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diagnostic_tests.id", ondelete="RESTRICT"), nullable=False
    )
    appointment_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Price snapshot taken at booking time; later price changes never touch it.
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status", native_enum=False, length=20, create_constraint=True),
        default=BookingStatus.PENDING,
        server_default=BookingStatus.PENDING.value,
        nullable=False,
    )

    centre: Mapped[DiagnosticCentre] = relationship()
    test: Mapped[DiagnosticTest] = relationship()
    payments: Mapped[list[Payment]] = relationship(back_populates="booking", order_by="Payment.created_at")
