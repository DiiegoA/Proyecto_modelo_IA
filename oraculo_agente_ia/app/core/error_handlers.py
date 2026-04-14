from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.exceptions import OraculoAgentError
from app.schemas.common import ErrorResponse

logger = logging.getLogger("oraculo_agent.errors")


def build_error_payload(
    request: Request,
    *,
    code: str,
    message: str,
    detail: dict[str, Any] | None = None,
    status_code: int = 400,
) -> JSONResponse:
    payload = ErrorResponse(
        error={
            "code": code,
            "message": message,
            "detail": detail or {},
            "request_id": getattr(request.state, "request_id", "unknown"),
            "timestamp": datetime.now(timezone.utc),
        }
    )
    return JSONResponse(status_code=status_code, content=payload.model_dump(mode="json"))


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(OraculoAgentError)
    async def handle_domain_error(request: Request, exc: OraculoAgentError) -> JSONResponse:
        logger.warning("Domain error: %s", exc.message)
        return build_error_payload(
            request,
            code=exc.code,
            message=exc.message,
            detail=exc.detail,
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return build_error_payload(
            request,
            code="validation_error",
            message="Invalid request payload.",
            detail={"errors": exc.errors()},
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", exc)
        return build_error_payload(
            request,
            code="internal_server_error",
            message="Unexpected internal server error.",
            detail={},
            status_code=500,
        )
