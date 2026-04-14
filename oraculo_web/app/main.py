from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import Settings, get_settings
from app.gateway import GatewayError, OraculoGateway
from app.schemas import ChatInvokeRequest, ErrorEnvelope, LoginRequest, RegisterRequest, SessionResponse, SessionUser

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _error_response(*, status_code: int, code: str, message: str, detail: dict[str, Any] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": ErrorEnvelope(
                code=code,
                message=message,
                detail=detail or {},
            ).model_dump(mode="json")
        },
    )


def get_gateway(request: Request) -> OraculoGateway:
    return request.app.state.gateway


def _get_session_token(request: Request) -> str:
    token = request.session.get("access_token")
    if not isinstance(token, str) or not token:
        raise GatewayError(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="authentication_required",
            message="Necesitas iniciar sesion para usar Oraculo Web.",
            detail={},
        )
    return token


def create_app(settings: Settings | None = None, gateway: OraculoGateway | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    application = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        debug=app_settings.debug,
        docs_url=app_settings.docs_url if app_settings.docs_enabled else None,
        redoc_url=app_settings.redoc_url if app_settings.docs_enabled else None,
        openapi_url=app_settings.openapi_url if app_settings.docs_enabled else None,
    )

    application.state.settings = app_settings
    application.state.gateway = gateway or OraculoGateway(app_settings)

    application.add_middleware(GZipMiddleware, minimum_size=1024)
    application.add_middleware(
        SessionMiddleware,
        secret_key=app_settings.session_secret_key,
        session_cookie=app_settings.session_cookie_name,
        max_age=app_settings.session_max_age_seconds,
        same_site="lax",
        https_only=app_settings.session_cookie_https_only,
    )
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=app_settings.allowed_hosts)
    application.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @application.exception_handler(GatewayError)
    def handle_gateway_error(_: Request, exc: GatewayError) -> JSONResponse:
        return _error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            detail=exc.detail,
        )

    @application.exception_handler(RequestValidationError)
    def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="validation_error",
            message="La peticion no cumple el contrato esperado.",
            detail={"issues": exc.errors()},
        )

    @application.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @application.get("/api/health/live", tags=["Health"])
    def live_health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/api/auth/register", response_model=SessionResponse, tags=["Auth"])
    def register(
        payload: RegisterRequest,
        request: Request,
        app_gateway: OraculoGateway = Depends(get_gateway),
    ) -> SessionResponse:
        app_gateway.register(payload)
        login_payload = LoginRequest(email=payload.email, password=payload.password)
        token_payload = app_gateway.login(login_payload)
        request.session.clear()
        request.session["access_token"] = token_payload["access_token"]
        request.session["user"] = token_payload["user"]
        return SessionResponse(authenticated=True, user=SessionUser(**token_payload["user"]))

    @application.post("/api/auth/login", response_model=SessionResponse, tags=["Auth"])
    def login(
        payload: LoginRequest,
        request: Request,
        app_gateway: OraculoGateway = Depends(get_gateway),
    ) -> SessionResponse:
        token_payload = app_gateway.login(payload)
        request.session.clear()
        request.session["access_token"] = token_payload["access_token"]
        request.session["user"] = token_payload["user"]
        return SessionResponse(authenticated=True, user=SessionUser(**token_payload["user"]))

    @application.get("/api/auth/me", response_model=SessionResponse, tags=["Auth"])
    def me(
        request: Request,
        app_gateway: OraculoGateway = Depends(get_gateway),
    ) -> SessionResponse:
        token = _get_session_token(request)
        user_payload = app_gateway.me(token)
        request.session["user"] = user_payload
        return SessionResponse(authenticated=True, user=SessionUser(**user_payload))

    @application.post("/api/auth/logout", response_model=SessionResponse, tags=["Auth"])
    def logout(request: Request) -> SessionResponse:
        request.session.clear()
        return SessionResponse(authenticated=False, user=None)

    @application.post("/api/chat/invoke", tags=["Chat"])
    def invoke_chat(
        payload: ChatInvokeRequest,
        request: Request,
        app_gateway: OraculoGateway = Depends(get_gateway),
    ) -> dict[str, Any]:
        token = _get_session_token(request)
        return app_gateway.invoke_chat(token=token, payload=payload.model_dump(exclude_none=True))

    return application


app = create_app()
