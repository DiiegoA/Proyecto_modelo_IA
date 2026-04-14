from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AppError(Exception):
    message: str
    status_code: int = 400
    code: str = "app_error"
    detail: dict[str, Any] = field(default_factory=dict)


class BadRequestError(AppError):
    def __init__(self, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, status_code=400, code="bad_request", detail=detail or {})


class AuthenticationError(AppError):
    def __init__(self, message: str = "Authentication failed.") -> None:
        super().__init__(message=message, status_code=401, code="authentication_error")


class AuthorizationError(AppError):
    def __init__(self, message: str = "You are not allowed to access this resource.") -> None:
        super().__init__(message=message, status_code=403, code="authorization_error")


class ResourceNotFoundError(AppError):
    def __init__(self, resource_name: str, resource_id: str) -> None:
        super().__init__(
            message=f"{resource_name} '{resource_id}' was not found.",
            status_code=404,
            code="resource_not_found",
            detail={"resource_name": resource_name, "resource_id": resource_id},
        )


class ConflictError(AppError):
    def __init__(self, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message=message, status_code=409, code="conflict", detail=detail or {})


class RateLimitExceededError(AppError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            message="Rate limit exceeded. Please retry later.",
            status_code=429,
            code="rate_limit_exceeded",
            detail={"retry_after_seconds": retry_after_seconds},
        )


class ServiceUnavailableError(AppError):
    def __init__(self, message: str = "Service temporarily unavailable.") -> None:
        super().__init__(message=message, status_code=503, code="service_unavailable")


class ModelInferenceError(AppError):
    def __init__(self, message: str = "Model inference failed.") -> None:
        super().__init__(message=message, status_code=500, code="model_inference_error")
