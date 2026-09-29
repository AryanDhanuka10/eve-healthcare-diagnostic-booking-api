from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.auth import SignupRequest
from app.schemas.booking import BookingCreate
from app.schemas.diagnostic import CentreCreate, CentreUpdate, OfferingUpsert
from app.schemas.webhook import WebhookPayload
from app.services.webhook_service import payload_hash

IDS = {"centre_id": "0b6c1a52-3f0e-4d4a-8a44-0c5c1f2b7e11", "test_id": "5a1c1c0e-8a3e-4a55-9d0c-7f0f7d5a9b22"}


def _booking(when):
    return BookingCreate(**IDS, appointment_at=when)


def test_appointment_must_be_timezone_aware():
    with pytest.raises(ValidationError, match="timezone"):
        _booking(datetime.now() + timedelta(days=2))


def test_appointment_in_past_or_too_soon_rejected():
    with pytest.raises(ValidationError):
        _booking(datetime.now(UTC) - timedelta(days=1))
    with pytest.raises(ValidationError):
        _booking(datetime.now(UTC) + timedelta(minutes=5))


def test_appointment_too_far_ahead_rejected():
    with pytest.raises(ValidationError):
        _booking(datetime.now(UTC) + timedelta(days=400))


def test_appointment_is_normalised_to_utc():
    ist = datetime.now(UTC).astimezone(timezone_ist()) + timedelta(days=2)
    assert _booking(ist).appointment_at.utcoffset() == timedelta(0)


def timezone_ist():
    from datetime import timezone

    return timezone(timedelta(hours=5, minutes=30))


@pytest.mark.parametrize("pw", ["short1", "allletters", "12345678"])
def test_weak_passwords_rejected(pw):
    with pytest.raises(ValidationError):
        SignupRequest(email="a@example.com", password=pw, full_name="A")


def test_email_is_lowercased():
    assert SignupRequest(email="A@Example.COM", password="Passw0rd1", full_name="A").email == "a@example.com"


def test_blank_names_rejected_and_names_trimmed():
    with pytest.raises(ValidationError):
        CentreCreate(name="   ", location="Delhi")
    assert CentreCreate(name="  Lab  ", location=" Delhi ").name == "Lab"


def test_centre_update_needs_a_field():
    with pytest.raises(ValidationError):
        CentreUpdate()


@pytest.mark.parametrize("price", ["0", "-1", "12.345", "abc"])
def test_bad_prices_rejected(price):
    with pytest.raises(ValidationError):
        OfferingUpsert(price=price)


def test_webhook_payload_rejects_unknown_type_and_extra_fields():
    with pytest.raises(ValidationError):
        WebhookPayload(event_id="e", event_type="payment.refunded", payment_reference="r")
    with pytest.raises(ValidationError):
        WebhookPayload(event_id="e", event_type="payment.failed", payment_reference="r", extra="x")


def test_payload_hash_is_stable_and_content_sensitive():
    a = WebhookPayload(event_id="e1", event_type="payment.failed", payment_reference="r")
    b = WebhookPayload.model_validate_json(
        '{"payment_reference":"r","event_type":"payment.failed","event_id":"e1"}'
    )
    c = WebhookPayload(event_id="e1", event_type="payment.succeeded", payment_reference="r")
    assert payload_hash(a) == payload_hash(b) != payload_hash(c)
