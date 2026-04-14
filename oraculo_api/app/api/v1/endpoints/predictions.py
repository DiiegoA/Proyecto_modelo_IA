from fastapi import APIRouter, Depends, Query, Request, status

from app.api.dependencies import get_current_user, get_prediction_service, get_settings
from app.core.config import Settings
from app.db.models import User
from app.schemas.prediction import (
    PredictionDetailResponse,
    PredictionInput,
    PredictionListResponse,
    PredictionLabel,
)
from app.services.prediction import PredictionService

router = APIRouter(prefix="/predictions", tags=["Predictions"])


@router.post("", response_model=PredictionDetailResponse, status_code=status.HTTP_201_CREATED)
def create_prediction(
    payload: PredictionInput,
    request: Request,
    current_user: User = Depends(get_current_user),
    prediction_service: PredictionService = Depends(get_prediction_service),
) -> PredictionDetailResponse:
    return prediction_service.predict(
        payload=payload,
        user=current_user,
        request_id=request.state.request_id,
        client_ip=request.state.client_ip,
    )


@router.get("", response_model=PredictionListResponse)
def list_predictions(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    label: PredictionLabel | None = Query(default=None),
    min_probability: float | None = Query(default=None, ge=0.0, le=1.0),
    current_user: User = Depends(get_current_user),
    prediction_service: PredictionService = Depends(get_prediction_service),
    settings: Settings = Depends(get_settings),
) -> PredictionListResponse:
    safe_limit = min(limit, settings.prediction_history_max_limit)
    return prediction_service.list_predictions(
        user=current_user,
        skip=skip,
        limit=safe_limit,
        label=label,
        min_probability=min_probability,
    )


@router.get("/{prediction_id}", response_model=PredictionDetailResponse)
def get_prediction(
    prediction_id: str,
    current_user: User = Depends(get_current_user),
    prediction_service: PredictionService = Depends(get_prediction_service),
) -> PredictionDetailResponse:
    return prediction_service.get_prediction(
        prediction_id=prediction_id,
        user=current_user,
    )
