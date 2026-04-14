from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import FakeModelManager, build_test_settings


def test_security_headers_and_request_id_are_present(client: TestClient) -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"


def test_docs_endpoint_remains_renderable_under_csp(client: TestClient) -> None:
    response = client.get("/docs")

    assert response.status_code == 200
    assert "Swagger UI" in response.text
    assert "cdn.jsdelivr.net" in response.headers["Content-Security-Policy"]


def test_huggingface_space_docs_allow_embedding_in_app_tab(client: TestClient) -> None:
    response = client.get("/docs", headers={"Host": "demo-space.hf.space"})

    assert response.status_code == 200
    assert "X-Frame-Options" not in response.headers
    assert "frame-ancestors https://huggingface.co https://*.huggingface.co" in response.headers[
        "Content-Security-Policy"
    ]


def test_rate_limit_blocks_excess_requests(tmp_path) -> None:
    settings = build_test_settings(
        f"sqlite:///{tmp_path / 'rate_limit.db'}",
        rate_limit_requests=1,
        rate_limit_window_seconds=60,
    )
    app = create_app(settings=settings, model_manager=FakeModelManager())

    with TestClient(app) as client:
        first_response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "limit@example.com",
                "full_name": "Limit User",
                "password": "StrongPass!123",
            },
        )
        second_response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "limit2@example.com",
                "full_name": "Limit User Two",
                "password": "StrongPass!123",
            },
        )

    assert first_response.status_code == 201
    assert second_response.status_code == 429
    assert second_response.json()["error"]["code"] == "rate_limit_exceeded"


def test_trusted_host_middleware_rejects_invalid_hosts(client: TestClient) -> None:
    response = client.get("/api/v1/health/live", headers={"Host": "evil.example.com"})

    assert response.status_code == 400


def test_allowed_hosts_configuration_normalizes_full_urls(tmp_path) -> None:
    settings = build_test_settings(
        f"sqlite:///{tmp_path / 'trusted_hosts.db'}",
        allowed_hosts=[
            "localhost/docs",
            "127.0.0.1:8000/docs",
            "https://demo-space.hf.space/docs",
        ],
    )
    app = create_app(settings=settings, model_manager=FakeModelManager())

    with TestClient(app) as client:
        localhost_response = client.get("/api/v1/health/live", headers={"Host": "localhost:8000"})
        space_response = client.get("/api/v1/health/live", headers={"Host": "demo-space.hf.space"})

    assert localhost_response.status_code == 200
    assert space_response.status_code == 200
