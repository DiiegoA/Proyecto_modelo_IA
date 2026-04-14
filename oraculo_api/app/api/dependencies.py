from __future__ import annotations

from collections.abc import Generator

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import AuthorizationError
from app.core.security import bearer_scheme, decode_access_token, extract_bearer_token
from app.db.models import User
from app.db.repositories import PredictionRepository, UserRepository
from app.db.session import yield_session
from app.ml.model_manager import ModelManager
from app.services import AuthService, HealthService, PredictionService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_model_manager(request: Request) -> ModelManager:
    return request.app.state.model_manager


def get_db_session(request: Request) -> Generator[Session, None, None]:
    yield from yield_session(request.app.state.session_factory)


def get_user_repository(session: Session = Depends(get_db_session)) -> UserRepository:
    return UserRepository(session)


def get_prediction_repository(session: Session = Depends(get_db_session)) -> PredictionRepository:
    return PredictionRepository(session)


def get_auth_service(
    settings: Settings = Depends(get_settings),
    user_repository: UserRepository = Depends(get_user_repository),
) -> AuthService:
    return AuthService(user_repository=user_repository, settings=settings)


def get_prediction_service(
    model_manager: ModelManager = Depends(get_model_manager),
    prediction_repository: PredictionRepository = Depends(get_prediction_repository),
) -> PredictionService:
    return PredictionService(
        model_manager=model_manager,
        prediction_repository=prediction_repository,
    )


def get_health_service(
    settings: Settings = Depends(get_settings),
    model_manager: ModelManager = Depends(get_model_manager),
) -> HealthService:
    return HealthService(settings=settings, model_manager=model_manager)


def get_current_user(
    credentials=Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    token = extract_bearer_token(credentials)
    token_payload = decode_access_token(token, settings)
    user = auth_service.get_user(token_payload.sub)
    if not user.is_active:
        raise AuthorizationError("Inactive users cannot access this resource.")
    return user


def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise AuthorizationError("Administrator privileges are required.")
    return current_user
