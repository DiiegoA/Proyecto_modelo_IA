from __future__ import annotations

from fastapi import Depends, Header, Request

from app.clients.oraculo_api import AuthenticatedUser
from app.core.config import Settings
from app.core.security import bearer_scheme, decode_user_token, extract_bearer_token, require_admin_key
from app.services.agent import AgentService
from app.services.health import HealthService
from app.services.knowledge import KnowledgeAdminService
from app.services.thread import ThreadService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_agent_service(request: Request) -> AgentService:
    return request.app.state.agent_service


def get_health_service(request: Request) -> HealthService:
    return request.app.state.health_service


def get_knowledge_service(request: Request) -> KnowledgeAdminService:
    return request.app.state.knowledge_service


def get_thread_service(request: Request) -> ThreadService:
    return request.app.state.thread_service


def get_oraculo_api_client(request: Request):
    return request.app.state.oraculo_api_client


def get_current_user(
    credentials=Depends(bearer_scheme),
    settings: Settings = Depends(get_settings),
    oraculo_api_client=Depends(get_oraculo_api_client),
) -> AuthenticatedUser:
    token = extract_bearer_token(credentials)
    if settings.oraculo_api_verify_remote_user:
        return oraculo_api_client.validate_user_token(token)
    payload = decode_user_token(token, settings)
    return AuthenticatedUser(
        id=payload.sub,
        email="",
        full_name="",
        role=payload.role,
        is_active=True,
        access_token=token,
    )


def require_admin(
    x_agent_admin_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    require_admin_key(x_agent_admin_key, settings)
