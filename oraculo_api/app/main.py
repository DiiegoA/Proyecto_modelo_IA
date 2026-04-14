from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.router import router as api_router
from app.core.config import Settings, get_settings
from app.core.error_handlers import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import (
    MaxRequestSizeMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)
from app.db import models  # noqa: F401
from app.db.seeds import seed_admin_user
from app.db.session import build_engine, build_session_factory, create_tables
from app.ml.model_manager import ModelManager

logger = logging.getLogger("oraculo_api")


def create_app(settings: Settings | None = None, model_manager: ModelManager | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        engine = build_engine(app_settings)
        session_factory = build_session_factory(engine)

        app.state.settings = app_settings
        app.state.engine = engine
        app.state.session_factory = session_factory

        if app_settings.auto_create_tables:
            create_tables(engine)

        with session_factory() as session:
            seed_admin_user(session, app_settings)
            session.commit()

        active_model_manager = model_manager or ModelManager(app_settings.resolved_model_path)
        active_model_manager.load_model()
        app.state.model_manager = active_model_manager

        logger.info("%s started in %s mode.", app_settings.app_name, app_settings.environment)
        yield

        if hasattr(app.state.model_manager, "unload_model"):
            app.state.model_manager.unload_model()
        app.state.engine.dispose()
        logger.info("%s shutdown completed.", app_settings.app_name)

    docs_enabled = app_settings.docs_enabled
    application = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        debug=app_settings.debug,
        lifespan=lifespan,
        docs_url=app_settings.docs_url if docs_enabled else None,
        redoc_url=app_settings.redoc_url if docs_enabled else None,
        openapi_url=app_settings.openapi_url if docs_enabled else None,
    )

    application.add_middleware(GZipMiddleware, minimum_size=1024)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    application.add_middleware(TrustedHostMiddleware, allowed_hosts=app_settings.allowed_hosts)
    application.add_middleware(SecurityHeadersMiddleware, settings=app_settings)
    application.add_middleware(MaxRequestSizeMiddleware, max_request_size_bytes=app_settings.max_request_size_bytes)
    application.add_middleware(RateLimitMiddleware, settings=app_settings)
    application.add_middleware(RequestContextMiddleware)

    register_error_handlers(application)
    application.include_router(api_router)

    @application.get("/", tags=["Root"])
    def root() -> dict[str, str]:
        return {
            "service": app_settings.app_name,
            "version": app_settings.app_version,
            "environment": app_settings.environment,
        }

    return application


app = create_app()
