from __future__ import annotations

from uuid import uuid4

from langchain_core.documents import Document
from langgraph.graph import END, START, StateGraph

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
        self.critic = ReflectionCritic()
        self.graph = self._build_graph(checkpointer)

    def _build_graph(self, checkpointer):
        graph = StateGraph(AgentState)
        graph.add_node("load_context", self._load_context)
        graph.add_node("route_intent", self._route_intent)
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
                "prediction": "prediction",
                "rag": "rag",
                "hybrid": "hybrid",
                "clarification": "clarification",
                "unsafe": "unsafe",
            },
        )
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

    def _load_context(self, state: AgentState) -> dict:
        memories = self.memory_service.search_memories(user_id=state["user_id"], query=state["current_input"], limit=3)
        return {
            "trace_id": state.get("trace_id", str(uuid4())),
            "memory_events": [{"type": "memory_context", "content": memory} for memory in memories],
            "messages": state.get("messages", []),
        }

    def _route_intent(self, state: AgentState) -> dict:
        extracted_fields = extract_prediction_fields(state["current_input"])
        decision = self.router.route(state["current_input"], extracted_field_count=len(extracted_fields))
        if decision.intent in {"prediction", "hybrid", "clarification"}:
            llm_extracted_fields = self.model_gateway.extract_prediction_fields_with_llm(
                state["current_input"],
                state.get("language", "es"),
            )
            if llm_extracted_fields:
                enriched_fields = dict(llm_extracted_fields)
                enriched_fields.update(extracted_fields)
                extracted_fields = enriched_fields
                decision = self.router.route(state["current_input"], extracted_field_count=len(extracted_fields))
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
        return {
            "intent": decision.intent,
            "confidence": decision.confidence,
            "extracted_prediction_fields": extracted_fields,
            "tool_results": {"plan": tool_plan.model_dump()},
        }

    def _prediction_node(self, state: AgentState) -> dict:
        is_complete, missing_fields, payload = validate_prediction_fields(state.get("extracted_prediction_fields", {}))
        display_missing_fields = [FIELD_DISPLAY_NAMES[field_name] for field_name in missing_fields]

        if not is_complete or payload is None:
            envelope = self.model_gateway.compose_prediction_answer(
                prediction_result={},
                missing_fields=display_missing_fields,
                question=state["current_input"],
                language=state.get("language", "es"),
            )
            return {
                "answer": envelope.answer,
                "missing_prediction_fields": display_missing_fields,
                "tool_results": state.get("tool_results", {}),
                "citations": [],
                "safety_flags": envelope.safety_flags,
                "confidence": envelope.confidence,
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
            language=state.get("language", "es"),
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
        }

    def _rag_node(self, state: AgentState) -> dict:
        hits = self.knowledge_service.retrieve(query=state["current_input"])
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
            language=state.get("language", "es"),
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
        tool_results["retrieval"] = {"hits": hits}
        return {
            "answer": envelope.answer,
            "retrieval_hits": hits,
            "citations": citations,
            "tool_results": tool_results,
            "safety_flags": envelope.safety_flags,
            "confidence": envelope.confidence,
            "missing_prediction_fields": [],
        }

    def _hybrid_node(self, state: AgentState) -> dict:
        prediction_state = self._prediction_node(state)
        rag_state = self._rag_node(state)
        prediction_envelope = self.model_gateway.compose_prediction_answer(
            prediction_result=prediction_state.get("tool_results", {}).get("prediction", {}),
            missing_fields=prediction_state.get("missing_prediction_fields", []),
            question=state["current_input"],
            language=state.get("language", "es"),
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
            language=state.get("language", "es"),
        )
        hybrid_envelope = self.model_gateway.compose_hybrid_answer(
            prediction_envelope=prediction_envelope,
            rag_envelope=rag_envelope,
        )
        tool_results = dict(state.get("tool_results", {}))
        tool_results.update(prediction_state.get("tool_results", {}))
        tool_results.update(rag_state.get("tool_results", {}))
        return {
            "answer": hybrid_envelope.answer,
            "retrieval_hits": rag_state.get("retrieval_hits", []),
            "citations": rag_state.get("citations", []),
            "tool_results": tool_results,
            "safety_flags": hybrid_envelope.safety_flags,
            "confidence": hybrid_envelope.confidence,
            "missing_prediction_fields": prediction_state.get("missing_prediction_fields", []),
        }

    def _clarification_node(self, state: AgentState) -> dict:
        return {
            "answer": (
                "Necesito un poco mas de contexto. Si quieres una prediccion, puedes escribirme los datos del "
                "dataset Adult en lenguaje natural, por ejemplo: Soy hombre, tengo 39 anos, estudie Bachelors "
                "y trabajo 40 horas por semana. Si prefieres, tambien sirve `clave: valor` o JSON. "
                "Si quieres informacion puntual del proyecto o la API, haz la pregunta documental directamente."
            ),
            "citations": [],
            "tool_results": state.get("tool_results", {}),
            "safety_flags": [],
            "confidence": 0.25,
            "missing_prediction_fields": [],
        }

    def _unsafe_node(self, state: AgentState) -> dict:
        return {
            "answer": "No puedo ayudar con instrucciones para evadir seguridad, exfiltrar prompts o alterar polÃ­ticas del sistema.",
            "citations": [],
            "tool_results": state.get("tool_results", {}),
            "safety_flags": [{"code": "unsafe_request", "message": "Potential prompt injection or unsafe request detected."}],
            "confidence": 0.95,
            "missing_prediction_fields": [],
        }

    def _reflection_node(self, state: AgentState) -> dict:
        tool_results = state.get("tool_results", {})
        verdict = self.critic.review(
            route=state["intent"],
            answer=state.get("answer", ""),
            citations=state.get("citations", []),
            missing_fields=state.get("missing_prediction_fields", []),
            prediction_result=tool_results.get("prediction"),
            safety_flags=state.get("safety_flags", []),
        )
        answer = verdict.suggested_answer or state.get("answer", "")
        return {
            "answer": answer,
            "reflection_report": verdict.model_dump(),
            "confidence": state.get("confidence", 0.0) if not verdict.issues else min(0.5, state.get("confidence", 0.0)),
        }
