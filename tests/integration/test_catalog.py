def test_public_can_list_and_get_centres_and_tests(client, catalog):
    assert client.get("/centres").status_code == 200
    assert client.get(f"/centres/{catalog['centre']['id']}").status_code == 200
    assert client.get("/tests").status_code == 200
    r = client.get(f"/centres/{catalog['centre']['id']}/tests")
    assert r.status_code == 200 and r.json()["total"] == 1


def test_non_admin_cannot_create_centre(client, user_headers):
    r = client.post("/centres", json={"name": "X", "location": "Y"}, headers=user_headers)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "ADMIN_REQUIRED"


def test_unauthenticated_cannot_create_centre(client):
    assert client.post("/centres", json={"name": "X", "location": "Y"}).status_code == 401


def test_duplicate_centre_name_location_rejected(client, admin_headers):
    payload = {"name": "Same Labs", "location": "Pune"}
    assert client.post("/centres", json=payload, headers=admin_headers).status_code == 201
    r = client.post("/centres", json=payload, headers=admin_headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CENTRE_EXISTS"


def test_duplicate_test_name_rejected(client, admin_headers):
    assert client.post("/tests", json={"name": "X-Ray"}, headers=admin_headers).status_code == 201
    r = client.post("/tests", json={"name": "X-Ray"}, headers=admin_headers)
    assert r.status_code == 409 and r.json()["error"]["code"] == "TEST_EXISTS"


def test_nonexistent_centre_and_test_are_404(client):
    fake = "00000000-0000-0000-0000-000000000000"
    assert client.get(f"/centres/{fake}").status_code == 404
    assert client.get(f"/tests/{fake}").status_code == 404


def test_offering_requires_existing_centre_and_test(client, admin_headers, catalog):
    fake = "00000000-0000-0000-0000-000000000000"
    r = client.put(
        f"/centres/{fake}/tests/{catalog['test']['id']}", json={"price": "10.00"}, headers=admin_headers
    )
    assert r.status_code == 404


def test_negative_or_zero_price_rejected(client, admin_headers, catalog):
    r = client.put(
        f"/centres/{catalog['centre']['id']}/tests/{catalog['other_test']['id']}",
        json={"price": "0"},
        headers=admin_headers,
    )
    assert r.status_code == 422


def test_price_update_does_not_retroactively_change_existing_bookings(
    client, admin_headers, user_headers, catalog, booking
):
    assert booking["amount"] == "500.00"
    r = client.put(
        f"/centres/{catalog['centre']['id']}/tests/{catalog['test']['id']}",
        json={"price": "999.00"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    refetched = client.get(f"/bookings/{booking['id']}", headers=user_headers).json()
    assert refetched["amount"] == "500.00"
