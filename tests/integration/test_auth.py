def test_signup_login_me_flow(client):
    r = client.post(
        "/auth/signup", json={"email": "New@Example.com", "password": "Passw0rd1", "full_name": "New User"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "new@example.com"  # normalised
    assert "hashed_password" not in body  # response schema, not the ORM object

    r = client.post("/auth/login", data={"username": "new@example.com", "password": "Passw0rd1"})
    assert r.status_code == 200
    token = r.json()["access_token"]

    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["email"] == "new@example.com"


def test_duplicate_signup_rejected(client):
    payload = {"email": "dupe@example.com", "password": "Passw0rd1", "full_name": "A"}
    assert client.post("/auth/signup", json=payload).status_code == 201
    r = client.post("/auth/signup", json=payload)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_signup_case_insensitive_duplicate_rejected(client):
    client.post("/auth/signup", json={"email": "case@example.com", "password": "Passw0rd1", "full_name": "A"})
    r = client.post(
        "/auth/signup", json={"email": "CASE@EXAMPLE.com", "password": "Passw0rd1", "full_name": "A"}
    )
    assert r.status_code == 409


def test_login_wrong_password_and_unknown_email_both_401(client):
    client.post("/auth/signup", json={"email": "e@example.com", "password": "Passw0rd1", "full_name": "A"})
    r1 = client.post("/auth/login", data={"username": "e@example.com", "password": "WrongPass1"})
    r2 = client.post("/auth/login", data={"username": "nobody@example.com", "password": "WrongPass1"})
    assert r1.status_code == r2.status_code == 401
    assert r1.json()["error"]["code"] == r2.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_protected_endpoint_without_token_rejected(client):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_protected_endpoint_with_invalid_jwt_rejected(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer not.a.valid.jwt"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "INVALID_TOKEN"


def test_malformed_signup_payload_is_422(client):
    r = client.post("/auth/signup", json={"email": "not-an-email", "password": "x", "full_name": ""})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"
