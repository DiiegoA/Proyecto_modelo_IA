from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, UpstreamServiceError

logger = logging.getLogger("oraculo_agent.oraculo_api_client")


@dataclass
class AuthenticatedUser:
    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    access_token: str | None = None


@dataclass
class PredictionApiResult:
    prediction_id: str
    label: str
    probability: float
    model_version: str
    execution_time_ms: float
    request_id: str
    input_payload: dict[str, Any]
    normalized_payload: dict[str, Any]


class OraculoApiClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._service_token: str | None = None
        self._service_token_expires_at: float = 0.0

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self.settings.oraculo_api_base_url,
            timeout=self.settings.oraculo_api_timeout_seconds,
            headers={"Accept": "application/json"},
        )

    def _request(
        self,
        *,
        method: str,
        path: str,
        json_payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        retry_count: int = 2,
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(retry_count + 1):
            try:
                with self._client() as client:
                    response = client.request(method, path, json=json_payload, headers=headers)
                if response.status_code >= 500:
                    raise UpstreamServiceError(
                        "The upstream Oraculo API returned a server error.",
                        detail={"status_code": response.status_code, "body": response.text[:500]},
                    )
                return response
            except (httpx.HTTPError, UpstreamServiceError) as exc:
                last_error = exc
                if attempt == retry_count:
                    break
                time.sleep(0.35 * (attempt + 1))
        raise UpstreamServiceError(
            "Could not reach Oraculo API.",
            detail={"base_url": self.settings.oraculo_api_base_url, "error": str(last_error)},
        )

    def authenticate_service_account(self, *, force_refresh: bool = False) -> str:
        if not force_refresh and self._service_token and time.time() < self._service_token_expires_at:
            return self._service_token
        response = self._request(
            method="POST",
            path="/api/v1/auth/login",
            json_payload={
                "email": self.settings.oraculo_api_service_email,
                "password": self.settings.oraculo_api_service_password,
            },
        )
        if response.status_code != 200:
            raise AuthenticationError(
                "The technical account could not authenticate against Oraculo API.",
                detail={"status_code": response.status_code, "body": response.text[:500]},
            )
        payload = response.json()
        self._service_token = payload["access_token"]
        self._service_token_expires_at = time.time() + max(30, int(payload.get("expires_in_seconds", 300)) - 15)
        return self._service_token

    def validate_user_token(self, user_token: str) -> AuthenticatedUser:
        if not self.settings.oraculo_api_verify_remote_user:
            return AuthenticatedUser(id="unknown", email="", full_name="", role="user", is_active=True, access_token=user_token)
        response = self._request(
            method="GET",
            path="/api/v1/auth/me",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        if response.status_code != 200:
            raise AuthenticationError(
                "The provided user token is not valid in Oraculo API.",
                detail={"status_code": response.status_code},
            )
        payload = response.json()
        return AuthenticatedUser(
            id=payload["id"],
            email=payload["email"],
            full_name=payload["full_name"],
            role=payload["role"],
            is_active=payload["is_active"],
            access_token=user_token,
        )

    def predict(self, payload: dict[str, Any], *, user_token: str | None = None) -> PredictionApiResult:
        auth_token = user_token or self.authenticate_service_account()
        response = self._request(
            method="POST",
            path="/api/v1/predictions",
            json_payload=payload,
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        if response.status_code == 401 and user_token is not None:
            auth_token = self.authenticate_service_account()
            response = self._request(
                method="POST",
                path="/api/v1/predictions",
                json_payload=payload,
                headers={"Authorization": f"Bearer {auth_token}"},
            )
        elif response.status_code == 401:
            service_token = self.authenticate_service_account(force_refresh=True)
            response = self._request(
                method="POST",
                path="/api/v1/predictions",
                json_payload=payload,
                headers={"Authorization": f"Bearer {service_token}"},
            )
        if response.status_code != 201:
            raise UpstreamServiceError(
                "The prediction request failed in Oraculo API.",
                detail={"status_code": response.status_code, "body": response.text[:500]},
            )
        data = response.json()
        return PredictionApiResult(
            prediction_id=data["id"],
            label=data["prediction"],
            probability=float(data["probability"]),
            model_version=data["model_version"],
            execution_time_ms=float(data["execution_time_ms"]),
            request_id=data["request_id"],
            input_payload=data["input_payload"],
            normalized_payload=data["normalized_payload"],
        )

    def health_check(self) -> dict[str, Any]:
        response = self._request(method="GET", path="/api/v1/health/ready", retry_count=1)
        if response.status_code != 200:
            raise UpstreamServiceError(
                "The upstream Oraculo API readiness check failed.",
                detail={"status_code": response.status_code, "body": response.text[:300]},
            )
        return response.json()
