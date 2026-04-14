from __future__ import annotations

import hashlib
import json
import time

from app.db.models import User
from app.db.repositories import PredictionRepository
from app.ml.model_manager import ModelManager
from app.schemas.common import PaginationMeta
from app.schemas.prediction import (
    PredictionDetailResponse,
    PredictionInput,
    PredictionListResponse,
)


class PredictionService:
    def __init__(self, *, model_manager: ModelManager, prediction_repository: PredictionRepository):
        self.model_manager = model_manager
        self.prediction_repository = prediction_repository

    @staticmethod
    def _hash_payload(payload: dict) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _build_detail_response(prediction_log) -> PredictionDetailResponse:
        return PredictionDetailResponse(
            id=prediction_log.id,
            prediction=prediction_log.label,
            probability=prediction_log.probability,
            is_counterfactual_applied=False,
            execution_time_ms=prediction_log.latency_ms,
            model_version=prediction_log.model_version,
            request_id=prediction_log.request_id,
            created_at=prediction_log.created_at,
            input_payload=prediction_log.input_payload,
            normalized_payload=prediction_log.normalized_payload,
        )

    def predict(
        self,
        *,
        payload: PredictionInput,
        user: User,
        request_id: str,
        client_ip: str,
    ) -> PredictionDetailResponse:
        started_at = time.perf_counter()
        input_payload = payload.model_dump(by_alias=True)
        normalized_payload = payload.model_dump(by_alias=False)

        model_prediction = self.model_manager.predict_one(normalized_payload)
        latency_ms = (time.perf_counter() - started_at) * 1000

        prediction_log = self.prediction_repository.create(
            user_id=user.id,
            request_id=request_id,
            ip_address=client_ip,
            label=model_prediction.label,
            probability=model_prediction.probability,
            latency_ms=latency_ms,
            model_version=model_prediction.model_version,
            payload_hash=self._hash_payload(normalized_payload),
            input_payload=input_payload,
            normalized_payload=normalized_payload,
        )
        return self._build_detail_response(prediction_log)

    def list_predictions(
        self,
        *,
        user: User,
        skip: int,
        limit: int,
        label: str | None,
        min_probability: float | None,
    ) -> PredictionListResponse:
        rows, total = self.prediction_repository.list_for_user(
            user_id=user.id,
            skip=skip,
            limit=limit,
            label=label,
            min_probability=min_probability,
        )
        return PredictionListResponse(
            items=[self._build_detail_response(row) for row in rows],
            pagination=PaginationMeta(total=total, skip=skip, limit=limit),
        )

    def get_prediction(self, *, prediction_id: str, user: User) -> PredictionDetailResponse:
        prediction_log = self.prediction_repository.get_for_user(prediction_id=prediction_id, user_id=user.id)
        if prediction_log is None:
            from app.core.exceptions import ResourceNotFoundError

            raise ResourceNotFoundError("Prediction", prediction_id)

        return self._build_detail_response(prediction_log)
