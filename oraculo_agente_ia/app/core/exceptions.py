from __future__ import annotations

from typing import Any


class OraculoAgentError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "oraculo_agent_error",
        status_code: int = 400,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.detail = detail or {}


class AuthenticationError(OraculoAgentError):
    def __init__(self, message: str = "Authentication failed.", detail: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="authentication_error", status_code=401, detail=detail)


class AuthorizationError(OraculoAgentError):
    def __init__(self, message: str = "Not authorized.", detail: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="authorization_error", status_code=403, detail=detail)


class ResourceNotFoundError(OraculoAgentError):
    def __init__(self, resource_name: str, resource_id: str) -> None:
        super().__init__(
            f"{resource_name} '{resource_id}' was not found.",
            code="resource_not_found",
            status_code=404,
            detail={"resource": resource_name, "resource_id": resource_id},
        )


class UpstreamServiceError(OraculoAgentError):
    def __init__(self, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="upstream_service_error", status_code=502, detail=detail)


class ConfigurationError(OraculoAgentError):
    def __init__(self, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message, code="configuration_error", status_code=500, detail=detail)


class InsufficientEvidenceError(OraculoAgentError):
    def __init__(self, message: str = "Insufficient evidence to answer safely.") -> None:
        super().__init__(
            message,
            code="insufficient_evidence",
            status_code=422,
            detail={"reason": "retrieval_evidence_missing"},
        )
