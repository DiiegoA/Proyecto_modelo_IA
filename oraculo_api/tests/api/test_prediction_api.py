from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.exceptions import ModelInferenceError


def test_prediction_requires_authentication(client: TestClient, valid_prediction_payload: dict) -> None:
    response = client.post("/api/v1/predictions", json=valid_prediction_payload)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_error"


def test_prediction_success_creates_audit_log(
    client: TestClient,
    auth_headers: dict[str, str],
    valid_prediction_payload: dict,
) -> None:
    response = client.post("/api/v1/predictions", json=valid_prediction_payload, headers=auth_headers)

    assert response.status_code == 201
    body = response.json()
    assert body["prediction"] == ">50K"
    assert body["probability"] == 0.91
    assert body["request_id"]
    assert body["model_version"] == "fake-1.0.0"
    assert body["normalized_payload"]["education_num"] == 14
    assert response.headers["X-Request-ID"]


def test_prediction_rejects_invalid_payload(
    client: TestClient,
    auth_headers: dict[str, str],
    valid_prediction_payload: dict,
) -> None:
    payload = dict(valid_prediction_payload)
    payload["age"] = 5
    response = client.post("/api/v1/predictions", json=payload, headers=auth_headers)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_prediction_rejects_large_payload(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/predictions",
        content="x" * 40_000,
        headers={"Content-Type": "application/json"} | auth_headers,
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_list_predictions_supports_query_filters(
    client: TestClient,
    auth_headers: dict[str, str],
    valid_prediction_payload: dict,
) -> None:
    client.post("/api/v1/predictions", json=valid_prediction_payload, headers=auth_headers)
    low_income_payload = dict(valid_prediction_payload)
    low_income_payload["education.num"] = 9
    low_income_payload["hours.per.week"] = 20
    client.post("/api/v1/predictions", json=low_income_payload, headers=auth_headers)

    response = client.get(
        "/api/v1/predictions?label=%3E50K&min_probability=0.8",
        headers=auth_headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["pagination"]["total"] == 1
    assert body["items"][0]["prediction"] == ">50K"


def test_get_prediction_by_id(
    client: TestClient,
    auth_headers: dict[str, str],
    valid_prediction_payload: dict,
) -> None:
    creation_response = client.post(
        "/api/v1/predictions",
        json=valid_prediction_payload,
        headers=auth_headers,
    )
    prediction_id = creation_response.json()["id"]

    response = client.get(f"/api/v1/predictions/{prediction_id}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["id"] == prediction_id


def test_prediction_history_is_isolated_per_user(
    client: TestClient,
    auth_headers: dict[str, str],
    valid_prediction_payload: dict,
) -> None:
    own_prediction = client.post("/api/v1/predictions", json=valid_prediction_payload, headers=auth_headers).json()

    client.post(
        "/api/v1/auth/register",
        json={
            "email": "other@example.com",
            "full_name": "Other User",
            "password": "StrongPass!123",
        },
    )
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "other@example.com", "password": "StrongPass!123"},
    )
    other_headers = {"Authorization": f"Bearer {login_response.json()['access_token']}"}

    response = client.get(f"/api/v1/predictions/{own_prediction['id']}", headers=other_headers)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "resource_not_found"


def test_prediction_failure_is_mapped_to_controlled_error(
    app,
    client: TestClient,
    auth_headers: dict[str, str],
    valid_prediction_payload: dict,
) -> None:
    class BrokenModelManager:
        @property
        def is_loaded(self) -> bool:
            return True

        def predict_one(self, input_data: dict):
            raise ModelInferenceError("Broken model.")

    app.state.model_manager = BrokenModelManager()

    response = client.post("/api/v1/predictions", json=valid_prediction_payload, headers=auth_headers)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "model_inference_error"
