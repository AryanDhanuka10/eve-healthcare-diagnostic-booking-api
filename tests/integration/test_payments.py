from tests.conftest import pay


def test_successful_payment_confirms_booking(client, user_headers, booking):
    r = pay(client, user_headers, booking["id"], "SUCCESS")
    assert r.status_code == 201
    assert r.json()["status"] == "SUCCESS"
    refetched = client.get(f"/bookings/{booking['id']}", headers=user_headers).json()
    assert refetched["status"] == "CONFIRMED"


def test_failed_payment_fails_booking(client, user_headers, booking):
    r = pay(client, user_headers, booking["id"], "FAILED")
    assert r.status_code == 201 and r.json()["status"] == "FAILED"
    refetched = client.get(f"/bookings/{booking['id']}", headers=user_headers).json()
    assert refetched["status"] == "FAILED"


def test_pending_payment_leaves_booking_pending_until_webhook(client, user_headers, booking):
    r = pay(client, user_headers, booking["id"], "PENDING")
    assert r.status_code == 201 and r.json()["status"] == "PENDING"
    refetched = client.get(f"/bookings/{booking['id']}", headers=user_headers).json()
    assert refetched["status"] == "PENDING"


def test_duplicate_payment_attempt_rejected(client, user_headers, booking):
    assert pay(client, user_headers, booking["id"], "PENDING").status_code == 201
    r = pay(client, user_headers, booking["id"], "SUCCESS")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PAYMENT_ALREADY_EXISTS"


def test_payment_for_non_payable_booking_rejected(client, user_headers, booking):
    client.post(f"/bookings/{booking['id']}/cancel", headers=user_headers)
    r = pay(client, user_headers, booking["id"], "SUCCESS")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "BOOKING_NOT_PAYABLE"


def test_cannot_pay_for_someone_elses_booking(client, other_headers, booking):
    r = pay(client, other_headers, booking["id"], "SUCCESS")
    assert r.status_code == 404  # ownership hidden behind NotFound, like GET/cancel


def test_pay_for_nonexistent_booking_is_404(client, user_headers):
    fake = "00000000-0000-0000-0000-000000000000"
    assert pay(client, user_headers, fake, "SUCCESS").status_code == 404


def test_invalid_simulate_outcome_value_is_422(client, user_headers, booking):
    r = client.post(
        "/payments/", json={"booking_id": booking["id"], "simulate_outcome": "MAYBE"}, headers=user_headers
    )
    assert r.status_code == 422


def test_get_payment_is_owner_scoped(client, user_headers, other_headers, booking):
    payment_id = pay(client, user_headers, booking["id"], "SUCCESS").json()["id"]
    assert client.get(f"/payments/{payment_id}", headers=user_headers).status_code == 200
    assert client.get(f"/payments/{payment_id}", headers=other_headers).status_code == 404


def test_cancelling_a_confirmed_booking_refunds_the_payment(client, user_headers, booking):
    pay(client, user_headers, booking["id"], "SUCCESS")
    r = client.post(f"/bookings/{booking['id']}/cancel", headers=user_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "CANCELLED"
    assert body["payments"][0]["status"] == "REFUNDED"


def test_cannot_cancel_booking_with_payment_in_progress(client, user_headers, booking):
    pay(client, user_headers, booking["id"], "PENDING")
    r = client.post(f"/bookings/{booking['id']}/cancel", headers=user_headers)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "PAYMENT_IN_PROGRESS"
