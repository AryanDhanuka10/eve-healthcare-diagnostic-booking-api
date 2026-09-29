import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.diagnostic_test import DiagnosticTest


class CentreTest(Base, TimestampMixin):
    """Junction table for the centre <-> test N:M relation. Holds the per-centre price."""

    __tablename__ = "centre_tests"
    __table_args__ = (CheckConstraint("price > 0", name="price_positive"),)

    centre_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diagnostic_centres.id", ondelete="RESTRICT"), primary_key=True
    )
    test_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("diagnostic_tests.id", ondelete="RESTRICT"), primary_key=True, index=True
    )
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)

    test: Mapped[DiagnosticTest] = relationship()
