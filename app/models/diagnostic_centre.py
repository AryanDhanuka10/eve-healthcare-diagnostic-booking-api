import uuid

from sqlalchemy import CheckConstraint, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class DiagnosticCentre(Base, TimestampMixin):
    __tablename__ = "diagnostic_centres"
    __table_args__ = (
        UniqueConstraint("name", "location", name="uq_diagnostic_centres_name_location"),
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
        CheckConstraint("length(trim(location)) > 0", name="location_not_blank"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    location: Mapped[str] = mapped_column(String(255), nullable=False)
