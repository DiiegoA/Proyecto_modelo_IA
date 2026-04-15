from __future__ import annotations

from collections.abc import Generator
from uuid import uuid4

from app.agent.graph import AgentWorkflow
from app.clients.oraculo_api import AuthenticatedUser
from app.memory.service import MemoryService
from app.schemas.chat import ChatRequest, ChatResponse, PredictionResult, StreamEvent
from app.services.thread import ThreadService


class AgentService:
    def __init__(
        self,
        *,
        workflow: AgentWorkflow,
        thread_service: ThreadService,
        memory_service: MemoryService,
    ):
        self.workflow = workflow
        self.thread_service = thread_service
        self.memory_service = memory_service

    def invoke(self, *, payload: ChatRequest, current_user: AuthenticatedUser) -> ChatResponse:
        thread_id = payload.thread_id or str(uuid4())
        prior_messages = self.thread_service.list_message_dicts(
            thread_id=thread_id,
            user_id=current_user.id,
            limit=50,
        ) if payload.thread_id else []

        state = {
            "thread_id": thread_id,
            "user_id": current_user.id,
            "user_token": current_user.access_token,
            "language": payload.language,
            "current_input": payload.message,
            "messages": prior_messages + [{"role": "user", "content": payload.message, "metadata": payload.metadata}],
            "response_mode": "invoke",
            "trace_id": str(uuid4()),
        }
        result = self.workflow.invoke(state)
        memory_events = self.memory_service.remember_from_interaction(
            user_id=current_user.id,
            thread_id=thread_id,
            user_message=payload.message,
            assistant_message=result["answer"],
        )
        self.thread_service.record_turn(
            thread_id=thread_id,
            user_id=current_user.id,
            user_message=payload.message,
            assistant_message=result["answer"],
            route=result["intent"],
            citations=result.get("citations", []),
            trace_id=result["trace_id"],
            assistant_metadata={
                "memory_events": memory_events,
                "reflection_report": result.get("reflection_report", {}),
                "conversation_state": result.get("conversation_state", {}),
                "slot_requested": result.get("slot_requested"),
                "llm_provider": result.get("llm_provider"),
            },
        )

        prediction_result = result.get("tool_results", {}).get("prediction")
        response = ChatResponse(
            thread_id=thread_id,
            route=result["intent"],
            answer=result["answer"],
            citations=result.get("citations", []),
            missing_fields=result.get("missing_prediction_fields", []),
            prediction_result=PredictionResult(**prediction_result) if prediction_result else None,
            confidence=result.get("confidence", 0.0),
            safety_flags=result.get("safety_flags", []),
            trace_id=result["trace_id"],
        )
        return response

    def stream(self, *, payload: ChatRequest, current_user: AuthenticatedUser) -> Generator[StreamEvent, None, None]:
        yield StreamEvent(event="accepted", data={"thread_id": payload.thread_id})
        response = self.invoke(payload=payload, current_user=current_user)
        yield StreamEvent(event="route", data={"route": response.route, "thread_id": response.thread_id})
        if response.missing_fields:
            yield StreamEvent(event="slot_requested", data={"field": response.missing_fields[0], "thread_id": response.thread_id})
        if response.prediction_result is not None:
            yield StreamEvent(event="tool_completed", data={"tool": "prediction_api", "prediction_id": response.prediction_result.prediction_id})
        if response.citations:
            yield StreamEvent(event="tool_completed", data={"tool": "knowledge_retrieval", "citations": len(response.citations)})
        yield StreamEvent(event="final", data=response.model_dump(mode="json"))
