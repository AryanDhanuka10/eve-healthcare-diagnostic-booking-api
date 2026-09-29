"""Importing this package registers every model on Base.metadata (needed by Alembic)."""

from app.models.booking import Booking
from app.models.centre_test import CentreTest
from app.models.diagnostic_centre import DiagnosticCentre
from app.models.diagnostic_test import DiagnosticTest
from app.models.payment import Payment
from app.models.user import User
from app.models.webhook_event import WebhookEvent

__all__ = [
    "Booking",
    "CentreTest",
    "DiagnosticCentre",
    "DiagnosticTest",
    "Payment",
    "User",
    "WebhookEvent",
]
