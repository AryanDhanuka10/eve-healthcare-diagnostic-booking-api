from tests.conftest import future_iso


def test_create_booking_is_pending_with_snapshotted_amount(client, user_headers, catalog):
    r = client.post(
        "/bookings",
        json={
            "centre_id": catalog["centre"]["id"],
            "test_id": catalog["test"]["id"],
            "appointment_at": future_iso(),
        },
        headers=user_headers,
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "PENDING" and body["amount"] == "500.00"


def test_booking_requires_authentication(client, catalog):
    r = client.post(
        "/bookings",
        json={
            "centre_id": catalog["centre"]["id"],
            "test_id": catalog["test"]["id"],
            "appointment_at": future_iso(),
        },
    )
    assert r.status_code == 401


def test_test_not_offered_by_centre_is_rejected(client, user_headers, catalog):
    r = client.post(
        "/bookings",
        json={
            "centre_id": catalog["centre"]["id"],
            "test_id": catalog["other_test"]["id"],
            "appointment_at": future_iso(),
        },
        headers=user_headers,
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "TEST_NOT_OFFERED"


def test_booking_with_nonexistent_centre_or_test_is_404(client, user_headers, catalog):
    fake = "00000000-0000-0000-0000-000000000000"
    r = client.post(
        "/bookings",
        json={"centre_id": fake, "test_id": catalog["test"]["id"], "appointment_at": future_iso()},
        headers=user_headers,
    )
    assert r.status_code == 404
    r = client.post(
        "/bookings",
        json={"centre_id": catalog["centre"]["id"], "test_id": fake, "appointment_at": future_iso()},
        headers=user_headers,
    )
    assert r.status_code == 404


def test_duplicate_active_slot_rejected(client, user_headers, catalog):
    payload = {
        "centre_id": catalog["centre"]["id"],
        "test_id": catalog["test"]["id"],
        "appointment_at": future_iso(),
    }
    assert client.post("/bookings", json=payload, headers=user_headers).status_code == 201
    r = client.post("/bookings", json=payload, headers=user_headers)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "DUPLICATE_BOOKING"


def test_user_cannot_see_or_cancel_another_users_booking(client, user_headers, other_headers, booking):
    r = client.get(f"/bookings/{booking['id']}", headers=other_headers)
    assert r.status_code == 404  # not 403: existence of someone else's booking id is not revealed
    r = client.post(f"/bookings/{booking['id']}/cancel", headers=other_headers)
    assert r.status_code == 404


def test_cancel_pending_booking_succeeds(client, user_headers, booking):
    r = client.post(f"/bookings/{booking['id']}/cancel", headers=user_headers)
    assert r.status_code == 200 and r.json()["status"] == "CANCELLED"


def test_cancel_already_cancelled_booking_rejected(client, user_headers, booking):
    client.post(f"/bookings/{booking['id']}/cancel", headers=user_headers)
    r = client.post(f"/bookings/{booking['id']}/cancel", headers=user_headers)
    assert r.status_code == 409
    assert (
        r.json()["error"]["code"] == "INVALID_STATE_TRANSITION"
        or "transition" in r.json()["error"]["message"].lower()
    )


def test_cancel_nonexistent_booking_is_404(client, user_headers):
    fake = "00000000-0000-0000-0000-000000000000"
    assert client.post(f"/bookings/{fake}/cancel", headers=user_headers).status_code == 404


def test_list_bookings_is_scoped_to_caller_and_supports_status_filter(
    client, user_headers, other_headers, booking
):
    assert (
        client.post(
            "/bookings",
            json={
                "centre_id": booking["centre"]["id"],
                "test_id": booking["test"]["id"],
                "appointment_at": future_iso(5),
            },
            headers=other_headers,
        ).status_code
        == 201
    )

    mine = client.get("/bookings", headers=user_headers).json()
    assert mine["total"] == 1 and mine["items"][0]["id"] == booking["id"]

    filtered = client.get("/bookings", params={"status": "CONFIRMED"}, headers=user_headers).json()
    assert filtered["total"] == 0


def test_pagination_params_validated(client, user_headers):
    assert client.get("/bookings", params={"limit": 0}, headers=user_headers).status_code == 422
    assert client.get("/bookings", params={"limit": 101}, headers=user_headers).status_code == 422
    assert client.get("/bookings", params={"offset": -1}, headers=user_headers).status_code == 422


def test_appointment_without_timezone_rejected(client, user_headers, catalog):
    r = client.post(
        "/bookings",
        json={
            "centre_id": catalog["centre"]["id"],
            "test_id": catalog["test"]["id"],
            "appointment_at": "2027-01-01T10:00:00",
        },
        headers=user_headers,
    )
    assert r.status_code == 422
