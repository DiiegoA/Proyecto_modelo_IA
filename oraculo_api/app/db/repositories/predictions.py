from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import PredictionLog


class PredictionRepository:
    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        *,
        user_id: str,
        request_id: str,
        ip_address: str,
        label: str,
        probability: float,
        latency_ms: float,
        model_version: str,
        payload_hash: str,
        input_payload: dict,
        normalized_payload: dict,
        notes: str | None = None,
    ) -> PredictionLog:
        prediction_log = PredictionLog(
            user_id=user_id,
            request_id=request_id,
            ip_address=ip_address,
            label=label,
            probability=probability,
            latency_ms=latency_ms,
            model_version=model_version,
            payload_hash=payload_hash,
            input_payload=input_payload,
            normalized_payload=normalized_payload,
            notes=notes,
        )
        self.session.add(prediction_log)
        self.session.flush()
        self.session.refresh(prediction_log)
        return prediction_log

    def list_for_user(
        self,
        *,
        user_id: str,
        skip: int,
        limit: int,
        label: str | None = None,
        min_probability: float | None = None,
    ) -> tuple[list[PredictionLog], int]:
        statement: Select[tuple[PredictionLog]] = select(PredictionLog).where(PredictionLog.user_id == user_id)

        if label:
            statement = statement.where(PredictionLog.label == label)
        if min_probability is not None:
            statement = statement.where(PredictionLog.probability >= min_probability)

        total = self.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = self.session.scalars(
            statement.order_by(PredictionLog.created_at.desc()).offset(skip).limit(limit)
        ).all()
        return rows, total

    def get_for_user(self, *, prediction_id: str, user_id: str) -> PredictionLog | None:
        statement = select(PredictionLog).where(
            PredictionLog.id == prediction_id,
            PredictionLog.user_id == user_id,
        )
        return self.session.scalar(statement)
