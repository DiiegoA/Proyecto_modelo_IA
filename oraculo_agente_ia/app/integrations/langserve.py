from __future__ import annotations

from langchain_core.runnables import RunnableLambda
from langserve import add_routes


def mount_langserve_debug_routes(app, *, workflow, knowledge_service) -> None:
    routing_runnable = RunnableLambda(
        lambda payload: workflow.router.route(
            payload["message"],
            extracted_field_count=0,
            conversation_state=payload.get("conversation_state"),
            history=payload.get("history"),
            language=payload.get("language", "es"),
        ).model_dump()
    )
    rag_runnable = RunnableLambda(
        lambda payload: {"hits": knowledge_service.retrieve(query=payload["query"])}
    )
    add_routes(
        app,
        routing_runnable,
        path="/debug/langserve/router",
        enabled_endpoints=("invoke", "stream", "playground", "input_schema", "output_schema"),
    )
    add_routes(
        app,
        rag_runnable,
        path="/debug/langserve/rag",
        enabled_endpoints=("invoke", "stream", "playground", "input_schema", "output_schema"),
    )
