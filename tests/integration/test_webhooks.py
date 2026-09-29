import concurrent.futures

from tests.conftest import event, pay, send_webhook


def _ref(client, user_headers, booking_id):
    return pay(client, user_headers, booking_id, "PENDING").json()["provider_reference"]


def test_webhook_success_confirms_booking(client, user_headers, booking):
    ref = _ref(client, user_headers, booking["id"])
    r = send_webhook(client, event("evt-1", ref))
    assert r.status_code == 200
    body = r.json()
    assert body["outcome"] == "APPLIED" and body["booking_status"] == "CONFIRMED"


def test_webhook_failed_fails_booking(client, user_headers, booking):
    ref = _ref(client, user_headers, booking["id"])
    r = send_webhook(client, event("evt-2", ref, "payment.failed"))
    assert r.json()["outcome"] == "APPLIED" and r.json()["booking_status"] == "FAILED"


def test_duplicate_webhook_delivery_has_no_extra_side_effects(client, user_headers, booking):
    ref = _ref(client, user_headers, booking["id"])
    payload = event("evt-dup", ref)
    first = send_webhook(client, payload)
    second = send_webhook(client, payload)
    third = send_webhook(client, payload)
    assert first.json()["outcome"] == "APPLIED"
    assert second.json()["outcome"] == third.json()["outcome"] == "DUPLICATE"

    booking_after = client.get(f"/bookings/{booking['id']}", headers=user_headers).json()
    assert booking_after["status"] == "CONFIRMED"
    assert len(booking_after["payments"]) == 1  # no duplicate payment rows


def test_same_event_id_with_different_payload_is_conflict(client, user_headers, booking):
    ref = _ref(client, user_headers, booking["id"])
    assert send_webhook(client, event("evt-mismatch", ref, "payment.succeeded")).status_code == 200
    r = send_webhook(client, event("evt-mismatch", ref, "payment.failed"))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "EVENT_PAYLOAD_MISMATCH"


def test_webhook_for_unknown_payment_reference_is_404_and_not_retried_as_duplicate(client):
    r = send_webhook(client, event("evt-unknown", "sim_does_not_exist"))
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "PAYMENT_NOT_FOUND"
    # Retrying the identical event is STILL a fresh attempt: the failed claim was rolled back.
    r2 = send_webhook(client, event("evt-unknown", "sim_does_not_exist"))
    assert r2.status_code == 404


def test_webhook_conflicting_with_already_final_payment_is_ignored_not_applied(client, user_headers, booking):
    ref = _ref(client, user_headers, booking["id"])
    assert send_webhook(client, event("evt-a", ref, "payment.succeeded")).json()["outcome"] == "APPLIED"
    r = send_webhook(client, event("evt-b", ref, "payment.failed"))
    assert r.status_code == 200
    assert r.json()["outcome"] == "IGNORED"
    assert r.json()["payment_status"] == "SUCCESS"  # history not rewritten


def test_webhook_missing_or_bad_signature_rejected(client, user_headers, booking):
    ref = _ref(client, user_headers, booking["id"])
    payload = event("evt-sig", ref)
    r = send_webhook(client, payload, signature="0" * 64)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_WEBHOOK_SIGNATURE"


def test_webhook_stale_timestamp_rejected(client, user_headers, booking):
    ref = _ref(client, user_headers, booking["id"])
    r = send_webhook(client, event("evt-old", ref), timestamp=1)
    assert r.status_code == 401


def test_webhook_invalid_payload_shape_rejected(client):
    r = client.post(
        "/payments/webhook/",
        **_signed_body(client, {"event_id": "e", "event_type": "payment.exploded", "payment_reference": "r"}),
    )
    assert r.status_code == 422


def _signed_body(client, payload):
    from tests.conftest import webhook_request

    return webhook_request(payload)


def test_concurrent_identical_webhooks_apply_exactly_once(client, user_headers, booking):
    """Fires the same event id from several threads at once against the real Postgres DB."""
    ref = _ref(client, user_headers, booking["id"])
    payload = event("evt-concurrent", ref)

    def fire():
        return send_webhook(client, payload)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = [f.result() for f in [pool.submit(fire) for _ in range(8)]]

    outcomes = sorted(r.json()["outcome"] for r in results)
    assert outcomes.count("APPLIED") == 1
    assert outcomes.count("DUPLICATE") == 7

    booking_after = client.get(f"/bookings/{booking['id']}", headers=user_headers).json()
    assert booking_after["status"] == "CONFIRMED"
    assert len(booking_after["payments"]) == 1
