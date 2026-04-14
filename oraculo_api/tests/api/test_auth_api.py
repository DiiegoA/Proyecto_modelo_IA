from fastapi.testclient import TestClient


def test_register_user_success(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "user@example.com",
            "full_name": "Test User",
            "password": "StrongPass!123",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "user@example.com"
    assert body["role"] == "user"


def test_register_duplicate_user_returns_conflict(client: TestClient) -> None:
    payload = {
        "email": "duplicate@example.com",
        "full_name": "Duplicate User",
        "password": "StrongPass!123",
    }

    first_response = client.post("/api/v1/auth/register", json=payload)
    second_response = client.post("/api/v1/auth/register", json=payload)

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert second_response.json()["error"]["code"] == "conflict"


def test_login_returns_token(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "login@example.com",
            "full_name": "Login User",
            "password": "StrongPass!123",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "StrongPass!123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "login@example.com"


def test_login_rejects_invalid_password(client: TestClient) -> None:
    client.post(
        "/api/v1/auth/register",
        json={
            "email": "invalid-login@example.com",
            "full_name": "Invalid Login",
            "password": "StrongPass!123",
        },
    )

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "invalid-login@example.com", "password": "WrongPass!123"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_error"


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_error"


def test_me_returns_current_user(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/auth/me", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"
