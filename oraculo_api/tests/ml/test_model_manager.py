from pathlib import Path

import pytest

from app.core.exceptions import ServiceUnavailableError
from app.ml.model_manager import ModelManager


VALID_PAYLOAD = {
    "age": 45,
    "workclass": "Private",
    "fnlwgt": 250000,
    "education": "Masters",
    "education_num": 14,
    "marital_status": "Married-civ-spouse",
    "occupation": "Exec-managerial",
    "relationship": "Husband",
    "race": "White",
    "sex": "Male",
    "capital_gain": 15000,
    "capital_loss": 0,
    "hours_per_week": 50,
    "native_country": "United-States",
}


def test_model_manager_loads_real_artifact() -> None:
    manager = ModelManager(Path("app/ml/pipeline_produccion.pkl"))
    manager.load_model()

    assert manager.is_loaded is True
    assert manager.model_version


def test_model_manager_predict_one_real_artifact() -> None:
    manager = ModelManager(Path("app/ml/pipeline_produccion.pkl"))
    manager.load_model()

    prediction = manager.predict_one(VALID_PAYLOAD)

    assert prediction.label in {"<=50K", ">50K"}
    assert 0.0 <= prediction.probability <= 1.0
    assert len(prediction.raw_probabilities) == 2


def test_model_manager_rejects_missing_artifact(tmp_path) -> None:
    manager = ModelManager(tmp_path / "missing.pkl")
    with pytest.raises(ServiceUnavailableError):
        manager.load_model()
