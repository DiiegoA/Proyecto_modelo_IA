from __future__ import annotations

import logging
import sys
from dataclasses import dataclass
import json
from pathlib import Path
from threading import Lock
from typing import Any

import joblib
import numpy as np
import pandas as pd

import app.ml.custom_transformers as custom_transformers
from app.core.exceptions import ModelInferenceError, ServiceUnavailableError

logger = logging.getLogger("oraculo_api.model")


@dataclass(slots=True)
class ModelPrediction:
    label: str
    probability: float
    raw_probabilities: list[float]
    model_version: str


class ModelManager:
    def __init__(self, model_path: str | Path):
        self.model_path = Path(model_path)
        self.pipeline: Any = None
        self.manifest: dict[str, Any] = {}
        self._lock = Lock()

    @property
    def is_loaded(self) -> bool:
        return self.pipeline is not None

    @property
    def model_version(self) -> str:
        if self.manifest.get("model_version"):
            return str(self.manifest["model_version"])
        if self.pipeline is None:
            return "unloaded"
        return str(getattr(self.pipeline, "version", "unknown"))

    @property
    def manifest_path(self) -> Path:
        return self.model_path.with_name("model_manifest.json")

    def _register_pickle_bridge(self) -> None:
        setattr(
            sys.modules["__main__"],
            "PipelineProduccionMLOps",
            custom_transformers.PipelineProduccionMLOps,
        )

    def load_model(self) -> None:
        with self._lock:
            if self.pipeline is not None:
                return

            if not self.model_path.exists():
                raise ServiceUnavailableError(f"Model artifact not found at '{self.model_path}'.")

            try:
                self._register_pickle_bridge()
                self.pipeline = joblib.load(self.model_path)
                if hasattr(self.pipeline, "_infer_missing_artefacts"):
                    self.pipeline._infer_missing_artefacts()
                if self.manifest_path.exists():
                    self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                logger.info("Model artifact loaded from %s", self.model_path)
            except Exception as exc:
                logger.exception("Unable to load model artifact: %s", exc)
                raise ServiceUnavailableError("Model artifact could not be loaded.") from exc

    def unload_model(self) -> None:
        with self._lock:
            self.pipeline = None
            self.manifest = {}

    def _ensure_loaded(self) -> Any:
        if self.pipeline is None:
            raise ServiceUnavailableError("Model is not loaded.")
        return self.pipeline

    @staticmethod
    def _to_frame(input_data: dict[str, Any] | pd.DataFrame) -> pd.DataFrame:
        if isinstance(input_data, pd.DataFrame):
            return input_data.copy()
        return pd.DataFrame([input_data])

    def predict(self, input_data: dict[str, Any] | pd.DataFrame) -> np.ndarray:
        pipeline = self._ensure_loaded()
        try:
            frame = self._to_frame(input_data)
            return pipeline.predict(frame)
        except Exception as exc:
            logger.exception("Prediction failed: %s", exc)
            raise ModelInferenceError("Prediction failed.") from exc

    def predict_proba(self, input_data: dict[str, Any] | pd.DataFrame) -> np.ndarray:
        pipeline = self._ensure_loaded()
        try:
            frame = self._to_frame(input_data)
            return pipeline.predict_proba(frame)
        except Exception as exc:
            logger.exception("Probability inference failed: %s", exc)
            raise ModelInferenceError("Probability inference failed.") from exc

    def predict_one(self, input_data: dict[str, Any]) -> ModelPrediction:
        labels = self.predict(input_data)
        probabilities = self.predict_proba(input_data)
        probability_vector = probabilities[0].tolist()
        positive_probability = float(probability_vector[1] if len(probability_vector) > 1 else probability_vector[0])
        return ModelPrediction(
            label=str(labels[0]),
            probability=positive_probability,
            raw_probabilities=probability_vector,
            model_version=self.model_version,
        )
