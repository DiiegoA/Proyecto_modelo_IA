from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.ml.model_manager import ModelPrediction


class FakeModelManager:
    def __init__(self) -> None:
        self.loaded = False
        self.version = "fake-1.0.0"

    @property
    def is_loaded(self) -> bool:
        return self.loaded

    @property
    def model_version(self) -> str:
        return self.version

    def load_model(self) -> None:
        self.loaded = True

    def unload_model(self) -> None:
        self.loaded = False

    def predict_one(self, input_data: dict) -> ModelPrediction:
        label = ">50K" if input_data["education_num"] >= 13 and input_data["hours_per_week"] >= 40 else "<=50K"
        probability = 0.91 if label == ">50K" else 0.24
        return ModelPrediction(
            label=label,
            probability=probability,
            raw_probabilities=[1 - probability, probability],
            model_version=self.version,
        )


def build_test_settings(database_url: str, **overrides) -> Settings:
    base_values = {
        "environment": "test",
        "debug": False,
        "docs_enabled": True,
        "database_url": database_url,
        "jwt_secret_key": "test-secret-key-32-characters-minimum",
        "allowed_hosts": ["testserver", "localhost", "127.0.0.1", "*.hf.space", "*.huggingface.co"],
        "cors_allow_origins": ["http://testserver"],
        "rate_limit_enabled": True,
        "rate_limit_requests": 50,
        "rate_limit_window_seconds": 60,
        "auto_seed_admin": False,
        "seed_admin_email": None,
        "seed_admin_password": None,
    }
    return Settings(**(base_values | overrides))


@pytest.fixture
def app(tmp_path) -> Generator:
    db_path = tmp_path / "test_api.db"
    settings = build_test_settings(f"sqlite:///{db_path}")
    application = create_app(settings=settings, model_manager=FakeModelManager())
    yield application


@pytest.fixture
def client(app) -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_token(client: TestClient) -> str:
    registration_payload = {
        "email": "user@example.com",
        "full_name": "Test User",
        "password": "StrongPass!123",
    }
    client.post("/api/v1/auth/register", json=registration_payload)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": registration_payload["email"], "password": registration_payload["password"]},
    )
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(auth_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def valid_prediction_payload() -> dict[str, object]:
    return {
        "age": 45,
        "workclass": "Private",
        "fnlwgt": 250000,
        "education": "Masters",
        "education.num": 14,
        "marital.status": "Married-civ-spouse",
        "occupation": "Exec-managerial",
        "relationship": "Husband",
        "race": "White",
        "sex": "Male",
        "capital.gain": 15000,
        "capital.loss": 0,
        "hours.per.week": 50,
        "native.country": "United-States",
    }
