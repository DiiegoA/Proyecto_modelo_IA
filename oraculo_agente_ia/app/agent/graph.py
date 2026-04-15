from __future__ import annotations

from uuid import uuid4

from langchain_core.documents import Document
from langgraph.graph import END, START, StateGraph

from app.agent.dialogue import (
    ConversationState,
    build_recent_summary,
    load_conversation_state,
    merge_prediction_slots,
    next_prediction_field,
)
from app.agent.model_gateway import ModelGateway
from app.agent.prediction_contract import (
    FIELD_DISPLAY_NAMES,
    alias_payload,
    extract_prediction_fields,
    validate_prediction_fields,
)
from app.agent.reflection import ReflectionCritic
from app.agent.routing import IntentRouter
from app.agent.types import AgentState, ToolCallPlan
from app.clients.oraculo_api import OraculoApiClient
from app.memory.service import MemoryService
from app.rag.service import KnowledgeService


class AgentWorkflow:
    def __init__(
        self,
        *,
        model_gateway: ModelGateway,
        knowledge_service: KnowledgeService,
        memory_service: MemoryService,
        oraculo_api_client: OraculoApiClient,
        checkpointer=None,
    ):
        self.model_gateway = model_gateway
        self.knowledge_service = knowledge_service
        self.memory_service = memory_service
        self.oraculo_api_client = oraculo_api_client
        self.router = IntentRouter(model_gateway)
        self.critic = ReflectionCritic(model_gateway)
        self.graph = self._build_graph(checkpointer)

    def _build_graph(self, checkpointer):
        graph = StateGraph(AgentState)
        graph.add_node("load_context", self._load_context)
        graph.add_node("route_intent", self._route_intent)
        graph.add_node("chat", self._chat_node)
        graph.add_node("prediction", self._prediction_node)
        graph.add_node("rag", self._rag_node)
        graph.add_node("hybrid", self._hybrid_node)
        graph.add_node("clarification", self._clarification_node)
        graph.add_node("unsafe", self._unsafe_node)
        graph.add_node("reflection", self._reflection_node)

        graph.add_edge(START, "load_context")
        graph.add_edge("load_context", "route_intent")
        graph.add_conditional_edges(
            "route_intent",
            lambda state: state["intent"],
            {
                "chat": "chat",
                "prediction": "prediction",
                "rag": "rag",
                "hybrid": "hybrid",
                "clarification": "clarification",
                "unsafe": "unsafe",
            },
        )
        graph.add_edge("chat", "reflection")
        graph.add_edge("prediction", "reflection")
        graph.add_edge("rag", "reflection")
        graph.add_edge("hybrid", "reflection")
        graph.add_edge("clarification", "reflection")
        graph.add_edge("unsafe", "reflection")
        graph.add_edge("reflection", END)
        return graph.compile(checkpointer=checkpointer, debug=False, name="oraculo_agent_graph")

    def invoke(self, state: AgentState) -> AgentState:
        config = {"configurable": {"thread_id": state["thread_id"]}}
        return self.graph.invoke(state, config=config)

    def _coerce_conversation_state(self, raw_state: dict | None, *, language: str) -> ConversationState:
        if raw_state:
            try:
                return ConversationState.model_validate(raw_state)
            except Exception:
                pass
        return ConversationState(
            assistant_name=self.model_gateway.settings.assistant_name,
            language=language,
        )

    def _persistable_conversation_state(
        self,
        conversation_state: ConversationState,
        *,
        messages: list[dict],
        answer: str,
        language: str,
        active_route: str,
        conversation_goal: str,
        prediction_slots: dict | None = None,
        next_slot_to_ask: str | None = None,
        reflection_note: str | None = None,
    ) -> dict:
        updated = conversation_state.model_copy(deep=True)
        updated.assistant_name = self.model_gateway.settings.assistant_name
        updated.language = language
        updated.active_route = active_route
        updated.conversation_goal = conversation_goal
        if prediction_slots is not None:
            updated.prediction_slots = prediction_slots
        updated.next_slot_to_ask = next_slot_to_ask
        updated.conversation_summary = build_recent_summary(
            [*(messages or []), {"role": "assistant", "content": answer}],
            limit=self.model_gateway.settings.chat_history_window,
        )
        clean_reflection = (reflection_note or "").strip()
        if clean_reflection:
            notes = [note.strip() for note in updated.reflection_notes if str(note).strip()]
            if not notes or notes[-1] != clean_reflection:
                notes.append(clean_reflection)
            updated.reflection_notes = notes[-3:]
            updated.last_reflection = clean_reflection
        return updated.model_dump()

    def _load_context(self, state: AgentState) -> dict:
        messages = state.get("messages", [])
        language = state.get("language", "es")
        memories = self.memory_service.search_memories(user_id=state["user_id"], query=state["current_input"], limit=3)
        conversation_state = load_conversation_state(
            messages,
            assistant_name=self.model_gateway.settings.assistant_name,
            default_language=language,
        )
        return {
            "trace_id": state.get("trace_id", str(uuid4())),
            "memory_events": [{"type": "memory_context", "content": memory} for memory in memories],
            "messages": messages,
            "conversation_state": conversation_state.model_dump(),
            "llm_provider": self.model_gateway.llm_provider_label,
        }

    def _route_intent(self, state: AgentState) -> dict:
        language = state.get("language", "es")
        history = state.get("messages", [])
        conversation_state = self._coerce_conversation_state(state.get("conversation_state"), language=language)
        extracted_fields = extract_prediction_fields(state["current_input"])

        decision = self.router.route(
            state["current_input"],
            extracted_field_count=len(extracted_fields),
            conversation_state=conversation_state.model_dump(),
            history=history,
            language=language,
        )

        if decision.intent in {"prediction", "hybrid", "clarification"} or conversation_state.active_route in {"prediction", "hybrid"}:
            llm_extracted_fields = self.model_gateway.extract_prediction_fields_with_llm(
                state["current_input"],
                language,
                history=history,
            )
            if llm_extracted_fields:
                enriched_fields = dict(llm_extracted_fields)
                enriched_fields.update(extracted_fields)
                extracted_fields = enriched_fields
                decision = self.router.route(
                    state["current_input"],
                    extracted_field_count=len(extracted_fields),
                    conversation_state=conversation_state.model_dump(),
                    history=history,
                    language=language,
                )

        merged_slots = merge_prediction_slots(conversation_state.prediction_slots, extracted_fields)
        next_slot = next_prediction_field(merged_slots) if decision.intent in {"prediction", "hybrid"} else None

        tool_plan = ToolCallPlan(
            tools=[
                tool_name
                for tool_name, needed in (
                    ("prediction_api", decision.needs_prediction),
                    ("knowledge_retrieval", decision.needs_retrieval),
                )
                if needed
            ],
            reasoning=decision.rationale,
        )

        routed_state = conversation_state.model_copy(deep=True)
        routed_state.assistant_name = self.model_gateway.settings.assistant_name
        routed_state.language = language
        if decision.intent in {"prediction", "hybrid"}:
            routed_state.conversation_goal = "prediction"
            routed_state.active_route = decision.intent
            routed_state.prediction_slots = merged_slots
            routed_state.next_slot_to_ask = next_slot
        elif decision.intent == "rag":
            routed_state.conversation_goal = "knowledge"
            routed_state.active_route = "rag"
            routed_state.prediction_slots = merged_slots
        elif decision.intent == "chat":
            routed_state.conversation_goal = "conversation"
            routed_state.active_route = "chat"
            routed_state.prediction_slots = merged_slots
        else:
            routed_state.active_route = decision.intent
            routed_state.prediction_slots = merged_slots

        return {
            "intent": decision.intent,
            "confidence": decision.confidence,
            "extracted_prediction_fields": merged_slots,
            "tool_results": {"plan": tool_plan.model_dump()},
            "conversation_state": routed_state.model_dump(),
            "slot_requested": FIELD_DISPLAY_NAMES.get(next_slot, next_slot) if next_slot else None,
        }

    def _chat_node(self, state: AgentState) -> dict:
        language = state.get("language", "es")
        memories = [event["content"] for event in state.get("memory_events", []) if event.get("type") == "memory_context"]
        conversation_state = self._coerce_conversation_state(state.get("conversation_state"), language=language)
        envelope = self.model_gateway.compose_chat_answer(
            question=state["current_input"],
            history=state.get("messages", []),
            memories=memories,
            language=language,
            conversation_state=conversation_state.model_dump(),
        )
        return {
            "answer": envelope.answer,
            "citations": [],
            "tool_results": state.get("tool_results", {}),
            "safety_flags": envelope.safety_flags,
            "confidence": envelope.confidence,
            "missing_prediction_fields": [],
            "slot_requested": None,
            "conversation_state": self._persistable_conversation_state(
                conversation_state,
                messages=state.get("messages", []),
                answer=envelope.answer,
                language=language,
                active_route="chat",
                conversation_goal="conversation",
                prediction_slots=conversation_state.prediction_slots,
                next_slot_to_ask=conversation_state.next_slot_to_ask,
            ),
        }

    def _prediction_node(self, state: AgentState) -> dict:
        language = state.get("language", "es")
        conversation_state = self._coerce_conversation_state(state.get("conversation_state"), language=language)
        prediction_slots = merge_prediction_slots(
            conversation_state.prediction_slots,
            state.get("extracted_prediction_fields", {}),
        )
        is_complete, missing_fields, payload = validate_prediction_fields(prediction_slots)
        display_missing_fields = [FIELD_DISPLAY_NAMES[field_name] for field_name in missing_fields]
        requested_fields_internal = self.model_gateway.requested_prediction_fields(missing_fields)
        requested_fields_display = [FIELD_DISPLAY_NAMES[field_name] for field_name in requested_fields_internal]
        next_field_internal = requested_fields_internal[0] if requested_fields_internal else next_prediction_field(prediction_slots)
        next_field_display = FIELD_DISPLAY_NAMES.get(next_field_internal, next_field_internal)

        if not is_complete or payload is None:
            envelope = self.model_gateway.compose_prediction_answer(
                prediction_result={},
                missing_fields=display_missing_fields,
                question=state["current_input"],
                language=language,
                history=state.get("messages", []),
                conversation_state=conversation_state.model_dump(),
                next_field=next_field_display,
                known_slots=prediction_slots,
                requested_fields=requested_fields_display,
            )
            return {
                "answer": envelope.answer,
                "missing_prediction_fields": display_missing_fields,
                "tool_results": state.get("tool_results", {}),
                "citations": [],
                "safety_flags": envelope.safety_flags,
                "confidence": envelope.confidence,
                "slot_requested": ", ".join(requested_fields_display) if requested_fields_display else next_field_display,
                "conversation_state": self._persistable_conversation_state(
                    conversation_state,
                    messages=state.get("messages", []),
                    answer=envelope.answer,
                    language=language,
                    active_route="prediction",
                    conversation_goal="prediction",
                    prediction_slots=prediction_slots,
                    next_slot_to_ask=next_field_internal,
                ),
            }

        prediction = self.oraculo_api_client.predict(
            alias_payload(payload),
            user_token=state.get("user_token"),
        )
        prediction_result = {
            "prediction_id": prediction.prediction_id,
            "label": prediction.label,
            "probability": prediction.probability,
            "model_version": prediction.model_version,
            "execution_time_ms": prediction.execution_time_ms,
            "request_id": prediction.request_id,
            "input_payload": prediction.input_payload,
            "normalized_payload": prediction.normalized_payload,
        }
        envelope = self.model_gateway.compose_prediction_answer(
            prediction_result=prediction_result,
            missing_fields=[],
            question=state["current_input"],
            language=language,
            history=state.get("messages", []),
            conversation_state=conversation_state.model_dump(),
            next_field=None,
            known_slots=prediction_slots,
        )
        tool_results = dict(state.get("tool_results", {}))
        tool_results["prediction"] = prediction_result
        return {
            "answer": envelope.answer,
            "missing_prediction_fields": [],
            "tool_results": tool_results,
            "citations": [],
            "safety_flags": envelope.safety_flags,
            "confidence": envelope.confidence,
            "slot_requested": None,
            "conversation_state": self._persistable_conversation_state(
                conversation_state,
                messages=state.get("messages", []),
                answer=envelope.answer,
                language=language,
                active_route="prediction",
                conversation_goal="prediction_completed",
                prediction_slots=prediction_slots,
                next_slot_to_ask=None,
            ),
        }

    def _rag_node(self, state: AgentState) -> dict:
        language = state.get("language", "es")
        conversation_state = self._coerce_conversation_state(state.get("conversation_state"), language=language)
        retrieval_query = self.model_gateway.rewrite_retrieval_query(
            question=state["current_input"],
            history=state.get("messages", []),
            language=language,
        )
        hits = self.knowledge_service.retrieve(query=retrieval_query)
        documents = [
            Document(
                page_content=hit["snippet"],
                metadata={
                    "source_id": hit["source_id"],
                    "source_path": hit["source_path"],
                    "title": hit["title"],
                    "score": hit["score"],
                },
            )
            for hit in hits
        ]
        memories = [event["content"] for event in state.get("memory_events", []) if event.get("type") == "memory_context"]
        envelope = self.model_gateway.compose_rag_answer(
            question=state["current_input"],
            hits=documents,
            memories=memories,
            language=language,
            history=state.get("messages", []),
            conversation_state=conversation_state.model_dump(),
        )
        citations = [
            {
                "source_id": hit["source_id"],
                "source_path": hit["source_path"],
                "title": hit["title"],
                "snippet": hit["snippet"],
                "score": hit["score"],
            }
            for hit in hits
        ]
        tool_results = dict(state.get("tool_results", {}))
        tool_results["retrieval"] = {"hits": hits, "query": retrieval_query}
        return {
            "answer": envelope.answer,
            "retrieval_hits": hits,
            "citations": citations,
            "tool_results": tool_results,
            "safety_flags": envelope.safety_flags,
            "confidence": envelope.confidence,
            "missing_prediction_fields": [],
            "slot_requested": None,
            "conversation_state": self._persistable_conversation_state(
                conversation_state,
                messages=state.get("messages", []),
                answer=envelope.answer,
                language=language,
                active_route="rag",
                conversation_goal="knowledge",
                prediction_slots=conversation_state.prediction_slots,
                next_slot_to_ask=conversation_state.next_slot_to_ask,
            ),
        }

    def _hybrid_node(self, state: AgentState) -> dict:
        language = state.get("language", "es")
        conversation_state = self._coerce_conversation_state(state.get("conversation_state"), language=language)
        prediction_state = self._prediction_node(state)
        rag_state = self._rag_node(state)
        prediction_envelope = self.model_gateway.compose_prediction_answer(
            prediction_result=prediction_state.get("tool_results", {}).get("prediction", {}),
            missing_fields=prediction_state.get("missing_prediction_fields", []),
            question=state["current_input"],
            language=language,
            history=state.get("messages", []),
            conversation_state=prediction_state.get("conversation_state", conversation_state.model_dump()),
            next_field=prediction_state.get("slot_requested"),
            known_slots=state.get("extracted_prediction_fields", {}),
        )
        rag_envelope = self.model_gateway.compose_rag_answer(
            question=state["current_input"],
            hits=[
                Document(
                    page_content=hit["snippet"],
                    metadata={
                        "source_id": hit["source_id"],
                        "source_path": hit["source_path"],
                        "title": hit["title"],
                        "score": hit["score"],
                    },
                )
                for hit in rag_state.get("retrieval_hits", [])
            ],
            memories=[event["content"] for event in state.get("memory_events", []) if event.get("type") == "memory_context"],
            language=language,
            history=state.get("messages", []),
            conversation_state=conversation_state.model_dump(),
        )
        hybrid_envelope = self.model_gateway.compose_hybrid_answer(
            question=state["current_input"],
            prediction_envelope=prediction_envelope,
            rag_envelope=rag_envelope,
            language=language,
            history=state.get("messages", []),
            conversation_state=conversation_state.model_dump(),
        )
        tool_results = dict(state.get("tool_results", {}))
        tool_results.update(prediction_state.get("tool_results", {}))
        tool_results.update(rag_state.get("tool_results", {}))
        merged_slots = merge_prediction_slots(
            conversation_state.prediction_slots,
            state.get("extracted_prediction_fields", {}),
        )
        next_slot_internal = next_prediction_field(merged_slots)
        return {
            "answer": hybrid_envelope.answer,
            "retrieval_hits": rag_state.get("retrieval_hits", []),
            "citations": rag_state.get("citations", []),
            "tool_results": tool_results,
            "safety_flags": hybrid_envelope.safety_flags,
            "confidence": hybrid_envelope.confidence,
            "missing_prediction_fields": prediction_state.get("missing_prediction_fields", []),
            "slot_requested": prediction_state.get("slot_requested"),
            "conversation_state": self._persistable_conversation_state(
                conversation_state,
                messages=state.get("messages", []),
                answer=hybrid_envelope.answer,
                language=language,
                active_route="hybrid",
                conversation_goal="hybrid",
                prediction_slots=merged_slots,
                next_slot_to_ask=next_slot_internal,
            ),
        }

    def _clarification_node(self, state: AgentState) -> dict:
        language = state.get("language", "es")
        conversation_state = self._coerce_conversation_state(state.get("conversation_state"), language=language)
        memories = [event["content"] for event in state.get("memory_events", []) if event.get("type") == "memory_context"]
        envelope = self.model_gateway.compose_clarification_answer(
            question=state["current_input"],
            history=state.get("messages", []),
            memories=memories,
            language=language,
            conversation_state=conversation_state.model_dump(),
        )
        return {
            "answer": envelope.answer,
            "citations": [],
            "tool_results": state.get("tool_results", {}),
            "safety_flags": envelope.safety_flags,
            "confidence": envelope.confidence,
            "missing_prediction_fields": [],
            "slot_requested": None,
            "conversation_state": self._persistable_conversation_state(
                conversation_state,
                messages=state.get("messages", []),
                answer=envelope.answer,
                language=language,
                active_route="clarification",
                conversation_goal="clarification",
                prediction_slots=conversation_state.prediction_slots,
                next_slot_to_ask=conversation_state.next_slot_to_ask,
            ),
        }

    def _unsafe_node(self, state: AgentState) -> dict:
        language = state.get("language", "es")
        conversation_state = self._coerce_conversation_state(state.get("conversation_state"), language=language)
        envelope = self.model_gateway.compose_unsafe_answer(
            question=state["current_input"],
            language=language,
        )
        return {
            "answer": envelope.answer,
            "citations": [],
            "tool_results": state.get("tool_results", {}),
            "safety_flags": envelope.safety_flags,
            "confidence": envelope.confidence,
            "missing_prediction_fields": [],
            "slot_requested": None,
            "conversation_state": self._persistable_conversation_state(
                conversation_state,
                messages=state.get("messages", []),
                answer=envelope.answer,
                language=language,
                active_route="unsafe",
                conversation_goal="unsafe",
                prediction_slots=conversation_state.prediction_slots,
                next_slot_to_ask=conversation_state.next_slot_to_ask,
            ),
        }

    def _reflection_node(self, state: AgentState) -> dict:
        tool_results = state.get("tool_results", {})
        language = state.get("language", "es")
        conversation_state = self._coerce_conversation_state(state.get("conversation_state"), language=language)
        verdict = self.critic.review(
            route=state["intent"],
            question=state.get("current_input", ""),
            answer=state.get("answer", ""),
            citations=state.get("citations", []),
            missing_fields=state.get("missing_prediction_fields", []),
            prediction_result=tool_results.get("prediction"),
            safety_flags=state.get("safety_flags", []),
            language=language,
            history=state.get("messages", []),
            conversation_state=conversation_state.model_dump(),
        )
        answer = verdict.suggested_answer or state.get("answer", "")
        updated_conversation_state = self._persistable_conversation_state(
            conversation_state,
            messages=state.get("messages", []),
            answer=answer,
            language=language,
            active_route=conversation_state.active_route or state["intent"],
            conversation_goal=conversation_state.conversation_goal or state["intent"],
            prediction_slots=conversation_state.prediction_slots,
            next_slot_to_ask=conversation_state.next_slot_to_ask,
            reflection_note=verdict.reflection_note,
        )
        return {
            "answer": answer,
            "reflection_report": verdict.model_dump(),
            "confidence": state.get("confidence", 0.0) if not verdict.issues else min(0.55, state.get("confidence", 0.0)),
            "conversation_state": updated_conversation_state,
        }
