from __future__ import annotations


def test_register_logs_in_and_sets_session(client, fake_gateway):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "diiegoaguirrel@gmail.com",
            "full_name": "Diego Aguirre",
            "password": "Lauracamila95*",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["authenticated"] is True
    assert payload["user"]["email"] == "diiegoaguirrel@gmail.com"
    assert fake_gateway.register_calls[0]["email"] == "diiegoaguirrel@gmail.com"
    assert fake_gateway.login_calls[0]["email"] == "diiegoaguirrel@gmail.com"


def test_auth_me_requires_existing_session(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_required"


def test_chat_invoke_uses_token_from_session_cookie(client, fake_gateway):
    login_response = client.post(
        "/api/auth/login",
        json={
            "email": "diiegoaguirrel@gmail.com",
            "password": "Lauracamila95*",
        },
    )
    assert login_response.status_code == 200

    response = client.post(
        "/api/chat/invoke",
        json={
            "thread_id": "thread-99",
            "message": "Haz una prediccion con este JSON: {\"age\": 39}",
            "language": "es",
            "metadata": {"source": "test"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["route"] == "prediction"
    assert fake_gateway.chat_calls == [
        {
            "token": "session-token",
            "payload": {
                "thread_id": "thread-99",
                "message": "Haz una prediccion con este JSON: {\"age\": 39}",
                "language": "es",
                "metadata": {"source": "test"},
            },
        }
    ]


def test_index_serves_frontend(client):
    response = client.get("/")

    assert response.status_code == 200
    assert "Oraculo Web" in response.text
