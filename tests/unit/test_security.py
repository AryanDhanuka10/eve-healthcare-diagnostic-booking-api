import time
from datetime import timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.security import (
    compute_webhook_signature,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
    verify_webhook_signature,
)
from app.exceptions import AuthenticationError, InvalidWebhookSignature


def test_password_is_hashed_and_verifiable():
    hashed = hash_password("Passw0rd123")
    assert hashed != "Passw0rd123" and hashed.startswith("$argon2")
    assert verify_password("Passw0rd123", hashed)
    assert not verify_password("wrong", hashed)


def test_same_password_gets_different_salted_hashes():
    assert hash_password("Passw0rd123") != hash_password("Passw0rd123")


def test_verify_password_with_garbage_hash_is_false_not_error():
    assert verify_password("x", "not-a-hash") is False


def test_jwt_roundtrip():
    token, expires_in = create_access_token("user-1")
    assert decode_access_token(token) == "user-1"
    assert expires_in == get_settings().access_token_expire_minutes * 60


def test_expired_jwt_rejected():
    token, _ = create_access_token("user-1", expires_delta=timedelta(seconds=-5))
    with pytest.raises(AuthenticationError) as exc:
        decode_access_token(token)
    assert exc.value.code == "TOKEN_EXPIRED"


def test_tampered_or_foreign_signed_jwt_rejected():
    forged = jwt.encode(
        {"sub": "x", "exp": time.time() + 60}, "another-secret-another-secret-123456", algorithm="HS256"
    )
    with pytest.raises(AuthenticationError):
        decode_access_token(forged)
    with pytest.raises(AuthenticationError):
        decode_access_token("garbage")


def test_jwt_without_required_claims_rejected():
    no_sub = jwt.encode(
        {"exp": time.time() + 60}, get_settings().jwt_secret_key.get_secret_value(), algorithm="HS256"
    )
    with pytest.raises(AuthenticationError):
        decode_access_token(no_sub)


def test_alg_none_token_rejected():
    unsigned = jwt.encode({"sub": "x", "exp": time.time() + 60}, None, algorithm="none")
    with pytest.raises(AuthenticationError):
        decode_access_token(unsigned)


BODY = b'{"a":1}'


def _verify(**overrides):
    ts = str(int(time.time()))
    kwargs = {
        "secret": "s3cret-s3cret-1234",
        "timestamp_header": ts,
        "signature_header": compute_webhook_signature("s3cret-s3cret-1234", ts, BODY),
        "body": BODY,
        "tolerance_seconds": 300,
    }
    kwargs.update(overrides)
    verify_webhook_signature(**kwargs)


def test_valid_webhook_signature_passes():
    _verify()


@pytest.mark.parametrize(
    "overrides",
    [
        {"signature_header": None},
        {"timestamp_header": None},
        {"signature_header": "deadbeef"},
        {"body": b'{"a":2}'},  # body tampered after signing
        {"timestamp_header": "abc"},
        {"timestamp_header": str(int(time.time()) - 3600)},  # replay outside tolerance
    ],
)
def test_bad_webhook_signature_rejected(overrides):
    with pytest.raises(InvalidWebhookSignature):
        _verify(**overrides)
