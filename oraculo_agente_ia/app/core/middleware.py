from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import Settings
from app.core.error_handlers import build_error_payload


def resolve_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id", str(uuid4()))
        request.state.request_id = request_id
        request.state.started_at = time.perf_counter()
        request.state.client_ip = resolve_client_ip(request)
        response = await call_next(request)
        duration_ms = (time.perf_counter() - request.state.started_at) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time-MS"] = f"{duration_ms:.2f}"
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self.settings = settings

    @staticmethod
    def _is_huggingface_space_request(request: Request) -> bool:
        host = (request.url.hostname or "").lower()
        return host.endswith(".hf.space")

    def _frame_ancestors_for_request(self, request: Request) -> str:
        if self._is_huggingface_space_request(request):
            return "https://huggingface.co https://*.huggingface.co"
        return "'none'"

    def _content_security_policy_for_request(self, request: Request) -> str:
        path = request.url.path
        frame_ancestors = self._frame_ancestors_for_request(request)
        docs_paths = {
            self.settings.docs_url,
            self.settings.redoc_url,
            self.settings.openapi_url,
            f"{self.settings.docs_url}/oauth2-redirect" if self.settings.docs_url else None,
        }

        if path in {value for value in docs_paths if value}:
            return (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.redoc.ly https://unpkg.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
                "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.jsdelivr.net; "
                "font-src 'self' data: https://cdn.jsdelivr.net https://fonts.gstatic.com; "
                "connect-src 'self'; "
                f"frame-ancestors {frame_ancestors}; "
                "base-uri 'self';"
            )

        return f"default-src 'none'; frame-ancestors {frame_ancestors}; base-uri 'none';"

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if not self.settings.security_headers_enabled:
            return response
        frame_ancestors = self._frame_ancestors_for_request(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        if frame_ancestors == "'none'":
            response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        response.headers["Content-Security-Policy"] = self._content_security_policy_for_request(request)
        return response


class MaxRequestSizeMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self.settings = settings

    def _limit_for_path(self, path: str) -> int:
        knowledge_upload_path = f"{self.settings.api_v1_prefix}/knowledge/upload"
        if path == knowledge_upload_path:
            return self.settings.knowledge_upload_max_request_size_bytes
        return self.settings.max_request_size_bytes

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        max_request_size_bytes = self._limit_for_path(request.url.path)
        if content_length and int(content_length) > max_request_size_bytes:
            return build_error_payload(
                request,
                code="payload_too_large",
                message="Payload exceeds the maximum allowed size.",
                detail={"max_request_size_bytes": max_request_size_bytes},
                status_code=413,
            )
        return await call_next(request)


class SimpleInMemoryRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._storage: dict[str, Deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def is_allowed(self, client_key: str) -> tuple[bool, int]:
        now = time.time()
        with self._lock:
            bucket = self._storage[client_key]
            while bucket and now - bucket[0] > self.window_seconds:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                retry_after = max(1, int(self.window_seconds - (now - bucket[0])))
                return False, retry_after
            bucket.append(now)
            return True, 0


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, settings: Settings):
        super().__init__(app)
        self.settings = settings
        self.limiter = SimpleInMemoryRateLimiter(
            max_requests=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )

    async def dispatch(self, request: Request, call_next):
        if not self.settings.rate_limit_enabled or request.url.path in self.settings.rate_limit_exempt_paths:
            return await call_next(request)
        is_allowed, retry_after = self.limiter.is_allowed(resolve_client_ip(request))
        if not is_allowed:
            return build_error_payload(
                request,
                code="rate_limit_exceeded",
                message="Rate limit exceeded. Please retry later.",
                detail={"retry_after_seconds": retry_after},
                status_code=429,
            )
        return await call_next(request)
