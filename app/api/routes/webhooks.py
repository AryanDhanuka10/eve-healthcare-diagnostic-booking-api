from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request
from pydantic import ValidationError

from app.api.deps import DbSession
from app.api.responses import errors
from app.core.config import get_settings
from app.core.security import verify_webhook_signature
from app.exceptions import AppError
from app.schemas.webhook import WebhookAck, WebhookPayload
from app.services import webhook_service

router = APIRouter(prefix="/payments", tags=["Webhooks"])


async def raw_body(request: Request) -> bytes:
    # The signature covers the exact bytes sent, so we must verify before re-serialising anything.
    return await request.body()


@router.post(
    "/webhook/",
    response_model=WebhookAck,
    summary="Payment provider webhook (idempotent)",
    responses=errors(401, 404, 409, 422),
)
@router.post("/webhook", response_model=WebhookAck, include_in_schema=False)
def payment_webhook(
    body: Annotated[bytes, Depends(raw_body)],
    db: DbSession,
    x_webhook_timestamp: Annotated[
        str | None, Header(description="Unix seconds when the provider signed the request")
    ] = None,
    x_webhook_signature: Annotated[
        str | None, Header(description="hex HMAC-SHA256 of '<timestamp>.<raw body>'")
    ] = None,
):
    """Authenticated by HMAC signature, not JWT. Safe to deliver any number of times:
    the same `event_id` is applied at most once (see README)."""
    settings = get_settings()
    verify_webhook_signature(
        secret=settings.webhook_secret.get_secret_value(),
        timestamp_header=x_webhook_timestamp,
        signature_header=x_webhook_signature,
        body=body,
        tolerance_seconds=settings.webhook_tolerance_seconds,
    )
    try:
        payload = WebhookPayload.model_validate_json(body)
    except ValidationError as exc:
        details = [
            {"loc": ".".join(map(str, e["loc"])), "msg": e["msg"], "type": e["type"]} for e in exc.errors()
        ]
        raise AppError("Invalid webhook payload", code="INVALID_WEBHOOK_PAYLOAD", details=details) from exc
    return webhook_service.process_webhook(db, payload)
