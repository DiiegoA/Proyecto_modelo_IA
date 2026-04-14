from __future__ import annotations

from contextlib import ExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from qdrant_client import QdrantClient
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.agent.graph import AgentWorkflow
from app.agent.model_gateway import ModelGateway
from app.api.router import router as api_router
from app.clients.oraculo_api import OraculoApiClient
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
from app.db.session import build_engine, build_session_factory, create_tables
from app.integrations.langserve import mount_langserve_debug_routes
from app.memory.service import MemoryService
from app.rag.service import KnowledgeService
from app.services.agent import AgentService
from app.services.health import HealthService
from app.services.knowledge import KnowledgeAdminService
from app.services.thread import ThreadService


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        from langgraph.checkpoint.sqlite import SqliteSaver

        exit_stack = ExitStack()
        engine = build_engine(app_settings)
        session_factory = build_session_factory(engine)
        create_tables(engine)
        qdrant_client = QdrantClient(path=str(app_settings.resolved_qdrant_path))

        checkpointer = exit_stack.enter_context(
            SqliteSaver.from_conn_string(str(app_settings.resolved_checkpoints_db_path))
        )

        model_gateway = ModelGateway(app_settings)
        oraculo_api_client = OraculoApiClient(app_settings)
        knowledge_runtime = KnowledgeService(
            settings=app_settings,
            session_factory=session_factory,
            model_gateway=model_gateway,
            qdrant_client=qdrant_client,
        )
        memory_service = MemoryService(
            settings=app_settings,
            session_factory=session_factory,
            model_gateway=model_gateway,
            qdrant_client=qdrant_client,
        )
        thread_service = ThreadService(session_factory)
        workflow = AgentWorkflow(
            model_gateway=model_gateway,
            knowledge_service=knowledge_runtime,
            memory_service=memory_service,
            oraculo_api_client=oraculo_api_client,
            checkpointer=checkpointer,
        )
        agent_service = AgentService(
            workflow=workflow,
            thread_service=thread_service,
            memory_service=memory_service,
        )
        knowledge_admin_service = KnowledgeAdminService(knowledge_runtime)
        health_service = HealthService(
            settings=app_settings,
            session_factory=session_factory,
            knowledge_service=knowledge_runtime,
            oraculo_api_client=oraculo_api_client,
        )

        app.state.settings = app_settings
        app.state.engine = engine
        app.state.session_factory = session_factory
        app.state.qdrant_client = qdrant_client
        app.state.model_gateway = model_gateway
        app.state.oraculo_api_client = oraculo_api_client
        app.state.knowledge_runtime = knowledge_runtime
        app.state.memory_service = memory_service
        app.state.workflow = workflow
        app.state.agent_service = agent_service
        app.state.knowledge_service = knowledge_admin_service
        app.state.thread_service = thread_service
        app.state.health_service = health_service

        if app_settings.auto_reindex_on_startup:
            knowledge_runtime.reindex(mode="incremental")
        if app_settings.enable_langserve and not getattr(app.state, "langserve_mounted", False):
            mount_langserve_debug_routes(app, workflow=workflow, knowledge_service=knowledge_runtime)
            app.state.langserve_mounted = True

        yield

        qdrant_client.close()
        engine.dispose()
        exit_stack.close()

    application = FastAPI(
        title=app_settings.app_name,
        version=app_settings.app_version,
        debug=app_settings.debug,
        lifespan=lifespan,
        docs_url=app_settings.docs_url if app_settings.docs_enabled else None,
        redoc_url=app_settings.redoc_url if app_settings.docs_enabled else None,
        openapi_url=app_settings.openapi_url if app_settings.docs_enabled else None,
    )

    application.add_middleware(GZipMiddleware, minimum_size=1024)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
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
