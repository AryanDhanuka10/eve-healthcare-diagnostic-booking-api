"""Password hashing, JWT handling and webhook signature verification."""

import hashlib
import hmac
import time
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings
from app.exceptions import AuthenticationError, InvalidWebhookSignature

# Argon2id with library-recommended parameters.
_password_hash = PasswordHash.recommended()
# Verified against when the email is unknown so login timing does not reveal
# which emails are registered.
DUMMY_HASH = _password_hash.hash("timing-equalisation-only")


def hash_password(plain: str) -> str:
    return _password_hash.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _password_hash.verify(plain, hashed)
    except Exception:  # malformed / unknown hash format
        return False


def create_access_token(subject: str, expires_delta: timedelta | None = None) -> tuple[str, int]:
    """Return (token, expires_in_seconds). `sub` is the user id."""
    settings = get_settings()
    delta = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": subject, "iat": now, "exp": now + delta},
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )
    return token, int(delta.total_seconds())


def decode_access_token(token: str) -> str:
    """Validate signature + expiry and return the subject, or raise 401."""
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],  # pinned: prevents alg-confusion
            options={"require": ["exp", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired", code="TOKEN_EXPIRED") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Invalid token", code="INVALID_TOKEN") from exc
    return str(claims["sub"])


def compute_webhook_signature(secret: str, timestamp: str, body: bytes) -> str:
    """HMAC-SHA256 over `"<timestamp>.<raw body>"` (same scheme Stripe-style providers use)."""
    message = timestamp.encode() + b"." + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_webhook_signature(
    *,
    secret: str,
    timestamp_header: str | None,
    signature_header: str | None,
    body: bytes,
    tolerance_seconds: int,
    now: float | None = None,
) -> None:
    if not timestamp_header or not signature_header:
        raise InvalidWebhookSignature("Missing webhook signature headers")
    try:
        timestamp = int(timestamp_header)
    except ValueError as exc:
        raise InvalidWebhookSignature("Invalid webhook timestamp") from exc
    if abs((now if now is not None else time.time()) - timestamp) > tolerance_seconds:
        raise InvalidWebhookSignature("Webhook timestamp outside tolerance window")
    expected = compute_webhook_signature(secret, timestamp_header, body)
    if not hmac.compare_digest(expected, signature_header):  # constant-time
        raise InvalidWebhookSignature("Webhook signature mismatch")
