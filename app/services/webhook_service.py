"""Idempotent processing of provider webhooks.

Idempotency key = provider event id, enforced by a UNIQUE constraint in PostgreSQL:

1. INSERT the event row with ON CONFLICT DO NOTHING (this "claims" the event).
   If a concurrent request is inserting the same id, PostgreSQL makes us wait for it
   to commit or roll back, so exactly one request ever owns an event id.
2. Claimed  -> apply side effects in the SAME transaction as the insert.
   Not claimed -> it is a retry: return DUPLICATE without touching any state.
Because claim + side effects commit atomically, a crash mid-way leaves no half-processed
event: the provider's retry is treated as a first delivery.
"""

import hashlib
import json
import logging

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.exceptions import ConflictError, NotFoundError
from app.models.booking import Booking
from app.models.enums import PaymentStatus
from app.models.payment import Payment
from app.models.webhook_event import WebhookEvent
from app.schemas.webhook import WebhookAck, WebhookOutcome, WebhookPayload
from app.services.payment_service import settle_payment
from app.services.state_machine import can_transition_payment

logger = logging.getLogger(__name__)

EVENT_TO_STATUS = {
    "payment.succeeded": PaymentStatus.SUCCESS,
    "payment.failed": PaymentStatus.FAILED,
}


def payload_hash(payload: WebhookPayload) -> str:
    """Canonical hash (key order independent) used to detect conflicting re-use of an event id."""
    canonical = json.dumps(payload.model_dump(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def process_webhook(db: Session, payload: WebhookPayload) -> WebhookAck:
    digest = payload_hash(payload)
    claim = (
        pg_insert(WebhookEvent)
        .values(
            provider_event_id=payload.event_id,
            event_type=payload.event_type,
            payment_reference=payload.payment_reference,
            payload_hash=digest,
        )
        .on_conflict_do_nothing(index_elements=["provider_event_id"])
        .returning(WebhookEvent.id)
    )
    event_pk = db.execute(claim).scalar_one_or_none()

    if event_pk is None:
        return _handle_duplicate(db, payload, digest)

    # Find the payment, then lock booking BEFORE payment (same order as pay/cancel).
    payment = db.scalar(select(Payment).where(Payment.provider_reference == payload.payment_reference))
    if payment is None:
        # Raising rolls back the claim too, so a later retry (after the payment exists) still works.
        db.rollback()
        logger.warning(
            "webhook_unknown_payment",
            extra={"event": "webhook_unknown_payment", "event_id": payload.event_id},
        )
        raise NotFoundError("Unknown payment reference", code="PAYMENT_NOT_FOUND")
    booking = db.scalars(
        select(Booking)
        .where(Booking.id == payment.booking_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    payment = db.scalars(
        select(Payment)
        .where(Payment.id == payment.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()

    target = EVENT_TO_STATUS[payload.event_type]
    if payment.status == target:
        outcome = WebhookOutcome.ALREADY_APPLIED  # e.g. synchronous result already recorded it
    elif can_transition_payment(payment.status, target):
        settle_payment(booking, payment, target)
        outcome = WebhookOutcome.APPLIED
    else:
        # Payment already final in a different state. Never rewrite history from a webhook:
        # keep the audit row, flag it for humans, change nothing.
        outcome = WebhookOutcome.IGNORED
        logger.error(
            "webhook_conflicts_with_final_state",
            extra={
                "event": "webhook_ignored",
                "event_id": payload.event_id,
                "payment_status": payment.status.value,
                "event_type": payload.event_type,
            },
        )

    db.execute(
        update(WebhookEvent)
        .where(WebhookEvent.id == event_pk)
        .values(outcome=outcome.value, processed_at=func.now())
    )
    db.commit()
    logger.info(
        "webhook_processed",
        extra={
            "event": "webhook_processed",
            "event_id": payload.event_id,
            "outcome": outcome.value,
            "payment_id": str(payment.id),
        },
    )
    return WebhookAck(
        event_id=payload.event_id,
        outcome=outcome,
        payment_status=payment.status,
        booking_status=booking.status,
    )


def _handle_duplicate(db: Session, payload: WebhookPayload, digest: str) -> WebhookAck:
    db.rollback()  # nothing to keep; end the transaction so the next read sees committed data
    existing = db.scalars(
        select(WebhookEvent).where(WebhookEvent.provider_event_id == payload.event_id)
    ).one()
    if existing.payload_hash != digest:
        logger.error(
            "webhook_payload_conflict",
            extra={"event": "webhook_payload_conflict", "event_id": payload.event_id},
        )
        raise ConflictError(
            "Event id was already used with a different payload", code="EVENT_PAYLOAD_MISMATCH"
        )
    payment = db.scalar(select(Payment).where(Payment.provider_reference == existing.payment_reference))
    booking = db.get(Booking, payment.booking_id) if payment else None
    logger.info("webhook_duplicate", extra={"event": "webhook_duplicate", "event_id": payload.event_id})
    return WebhookAck(
        event_id=payload.event_id,
        outcome=WebhookOutcome.DUPLICATE,
        payment_status=payment.status if payment else None,
        booking_status=booking.status if booking else None,
    )
