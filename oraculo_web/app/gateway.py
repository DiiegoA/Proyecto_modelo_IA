from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings
from app.schemas import LoginRequest, RegisterRequest


@dataclass
class GatewayError(Exception):
    status_code: int
    code: str
    message: str
    detail: dict[str, Any]


class OraculoGateway:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _request(
        self,
        *,
        base_url: str,
        method: str,
        path: str,
        json_payload: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            with httpx.Client(base_url=base_url, timeout=self.settings.request_timeout_seconds, headers=headers) as client:
                response = client.request(method, path, json=json_payload)
        except httpx.HTTPError as exc:
            raise GatewayError(
                status_code=502,
                code="upstream_unreachable",
                message="No se pudo contactar el servicio remoto.",
                detail={"base_url": base_url, "error": str(exc)},
            ) from exc

        if response.status_code >= 400:
            payload = self._safe_json(response)
            error_payload = payload.get("error", {}) if isinstance(payload, dict) else {}
            raise GatewayError(
                status_code=response.status_code,
                code=str(error_payload.get("code", "upstream_error")),
                message=str(error_payload.get("message", "El servicio remoto devolvio un error.")),
                detail=dict(error_payload.get("detail", {})) if isinstance(error_payload.get("detail", {}), dict) else {},
            )

        payload = self._safe_json(response)
        if not isinstance(payload, dict):
            raise GatewayError(
                status_code=502,
                code="invalid_upstream_payload",
                message="El servicio remoto devolvio una respuesta invalida.",
                detail={"base_url": base_url, "path": path},
            )
        return payload

    @staticmethod
    def _safe_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}

    def register(self, payload: RegisterRequest) -> dict[str, Any]:
        return self._request(
            base_url=self.settings.oraculo_api_base_url,
            method="POST",
            path="/api/v1/auth/register",
            json_payload=payload.model_dump(),
        )

    def login(self, payload: LoginRequest) -> dict[str, Any]:
        return self._request(
            base_url=self.settings.oraculo_api_base_url,
            method="POST",
            path="/api/v1/auth/login",
            json_payload=payload.model_dump(),
        )

    def me(self, token: str) -> dict[str, Any]:
        return self._request(
            base_url=self.settings.oraculo_api_base_url,
            method="GET",
            path="/api/v1/auth/me",
            token=token,
        )

    def invoke_chat(self, *, token: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            base_url=self.settings.oraculo_agent_base_url,
            method="POST",
            path="/api/v1/chat/invoke",
            json_payload=payload,
            token=token,
        )
