"""Test setup. Integration tests run against a REAL PostgreSQL database (never the dev DB)."""

import os
from datetime import UTC, datetime, timedelta

# Must be set before `app` is imported: settings and the engine are created at import time.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/eve_test"
)
os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-key-at-least-32-characters"
os.environ["WEBHOOK_SECRET"] = "test-webhook-secret"

import json
import time

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text

from alembic import command
from app.core.security import compute_webhook_signature, hash_password
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.enums import UserRole
from app.models.user import User

PASSWORD = "Sup3rSecret!"
TABLES = "webhook_events, payments, bookings, centre_tests, diagnostic_tests, diagnostic_centres, users"


@pytest.fixture(scope="session", autouse=True)
def _migrated_database():
    """Build the schema with Alembic itself, so the migrations are tested too."""
    cfg = Config("alembic.ini")
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def make_user(client: TestClient, email: str, role: UserRole = UserRole.USER) -> dict[str, str]:
    """Create a user and return Authorization headers. Admins are inserted directly (no signup path)."""
    if role == UserRole.ADMIN:
        with SessionLocal() as s:
            s.add(User(email=email, hashed_password=hash_password(PASSWORD), full_name="Admin", role=role))
            s.commit()
    else:
        r = client.post("/auth/signup", json={"email": email, "password": PASSWORD, "full_name": "Test User"})
        assert r.status_code == 201, r.text
    r = client.post("/auth/login", data={"username": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def admin_headers(client):
    return make_user(client, "admin@example.com", UserRole.ADMIN)


@pytest.fixture
def user_headers(client):
    return make_user(client, "alice@example.com")


@pytest.fixture
def other_headers(client):
    return make_user(client, "bob@example.com")


@pytest.fixture
def catalog(client, admin_headers) -> dict:
    """One centre offering one test at 500.00, plus a second test the centre does NOT offer."""
    centre = client.post(
        "/centres", json={"name": "City Labs", "location": "Delhi"}, headers=admin_headers
    ).json()
    test = client.post("/tests", json={"name": "CBC"}, headers=admin_headers).json()
    other_test = client.post("/tests", json={"name": "MRI"}, headers=admin_headers).json()
    r = client.put(
        f"/centres/{centre['id']}/tests/{test['id']}", json={"price": "500.00"}, headers=admin_headers
    )
    assert r.status_code == 200, r.text
    return {"centre": centre, "test": test, "other_test": other_test}


def future_iso(days: int = 3) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


@pytest.fixture
def booking(client, user_headers, catalog) -> dict:
    r = client.post(
        "/bookings",
        json={
            "centre_id": catalog["centre"]["id"],
            "test_id": catalog["test"]["id"],
            "appointment_at": future_iso(),
        },
        headers=user_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def pay(client, headers, booking_id, outcome="SUCCESS"):
    return client.post(
        "/payments/", json={"booking_id": booking_id, "simulate_outcome": outcome}, headers=headers
    )


def webhook_request(payload: dict, *, secret="test-webhook-secret", timestamp=None, signature=None) -> dict:
    """kwargs for client.post(...) carrying a correctly signed body (overridable to test bad signatures)."""
    body = json.dumps(payload).encode()
    ts = str(timestamp if timestamp is not None else int(time.time()))
    return {
        "content": body,
        "headers": {
            "Content-Type": "application/json",
            "X-Webhook-Timestamp": ts,
            "X-Webhook-Signature": signature or compute_webhook_signature(secret, ts, body),
        },
    }


def send_webhook(client: TestClient, payload: dict, **kw):
    return client.post("/payments/webhook/", **webhook_request(payload, **kw))


def event(event_id: str, ref: str, kind: str = "payment.succeeded") -> dict:
    return {"event_id": event_id, "event_type": kind, "payment_reference": ref}
