import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.prediction import PredictionInput


VALID_PAYLOAD = {
    "age": 35,
    "workclass": "Private",
    "fnlwgt": 150000,
    "education": "Bachelors",
    "education.num": 13,
    "marital.status": "Married-civ-spouse",
    "occupation": "Tech-support",
    "relationship": "Husband",
    "race": "White",
    "sex": "Male",
    "capital.gain": 5000,
    "capital.loss": 0,
    "hours.per.week": 40,
    "native.country": "United-States",
}


def test_prediction_input_accepts_aliases() -> None:
    payload = PredictionInput(**VALID_PAYLOAD)
    assert payload.education_num == 13
    assert payload.capital_gain == 5000
    assert payload.marital_status == "Married-civ-spouse"


@pytest.mark.parametrize(
    "field_name, invalid_value",
    [
        ("age", 16),
        ("education.num", 0),
        ("hours.per.week", 100),
        ("workclass", ""),
        ("native.country", "x" * 65),
        ("sex", "Unknown"),
    ],
)
def test_prediction_input_rejects_invalid_values(field_name: str, invalid_value) -> None:
    payload = dict(VALID_PAYLOAD)
    payload[field_name] = invalid_value
    with pytest.raises(ValidationError):
        PredictionInput(**payload)


def test_prediction_input_rejects_unknown_fields() -> None:
    payload = dict(VALID_PAYLOAD)
    payload["unexpected"] = "boom"
    with pytest.raises(ValidationError):
        PredictionInput(**payload)


def test_register_request_enforces_password_strength() -> None:
    with pytest.raises(ValidationError):
        RegisterRequest(email="user@example.com", full_name="User Test", password="weakpassword")


def test_login_request_normalizes_email() -> None:
    payload = LoginRequest(email="USER@EXAMPLE.COM", password="StrongPass!123")
    assert payload.email == "user@example.com"
