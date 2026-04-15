from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.agent.prediction_contract import FIELD_DISPLAY_NAMES, compute_missing_fields


class ConversationState(BaseModel):
    assistant_name: str = "AdultBot"
    conversation_goal: str = "general"
    active_route: str | None = None
    prediction_slots: dict[str, Any] = Field(default_factory=dict)
    next_slot_to_ask: str | None = None
    conversation_summary: str = ""
    last_reflection: str = ""
    reflection_notes: list[str] = Field(default_factory=list)
    language: str = "es"
    turn_count: int = 0


def load_conversation_state(
    messages: list[dict[str, Any]] | None,
    *,
    assistant_name: str,
    default_language: str = "es",
) -> ConversationState:
    base_state = ConversationState(assistant_name=assistant_name, language=default_language)
    if not messages:
        return base_state

    for message in reversed(messages):
        if message.get("role") != "assistant":
            continue
        metadata = message.get("metadata") or {}
        raw_state = metadata.get("conversation_state")
        if not raw_state:
            continue
        try:
            restored = ConversationState.model_validate(raw_state)
            restored.assistant_name = assistant_name or restored.assistant_name
            restored.language = restored.language or default_language
            restored.turn_count = count_user_turns(messages)
            if not restored.conversation_summary:
                restored.conversation_summary = build_recent_summary(messages)
            return restored
        except Exception:
            continue

    base_state.turn_count = count_user_turns(messages)
    base_state.conversation_summary = build_recent_summary(messages)
    return base_state


def count_user_turns(messages: list[dict[str, Any]] | None) -> int:
    if not messages:
        return 0
    return sum(1 for message in messages if message.get("role") == "user")


def build_recent_summary(messages: list[dict[str, Any]] | None, *, limit: int = 6) -> str:
    if not messages:
        return ""
    condensed_lines: list[str] = []
    for message in messages[-limit:]:
        role = message.get("role", "unknown")
        content = str(message.get("content", "")).strip().replace("\n", " ")
        if not content:
            continue
        condensed_lines.append(f"{role}: {content[:180]}")
    return "\n".join(condensed_lines)


def build_recent_history(messages: list[dict[str, Any]] | None, *, limit: int = 8) -> list[dict[str, str]]:
    if not messages:
        return []
    history: list[dict[str, str]] = []
    for message in messages[-limit:]:
        role = str(message.get("role", "user"))
        content = str(message.get("content", "")).strip()
        if content:
            history.append({"role": role, "content": content})
    return history


def merge_prediction_slots(
    prior_slots: dict[str, Any] | None,
    current_slots: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(prior_slots or {})
    for key, value in (current_slots or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        merged[key] = value
    return merged


def is_prediction_in_progress(state: ConversationState | dict[str, Any] | None) -> bool:
    if state is None:
        return False
    if isinstance(state, dict):
        active_route = state.get("active_route")
        slots = state.get("prediction_slots") or {}
    else:
        active_route = state.active_route
        slots = state.prediction_slots
    return active_route in {"prediction", "hybrid"} or bool(slots)


def next_prediction_field(prediction_slots: dict[str, Any]) -> str | None:
    missing = compute_missing_fields(prediction_slots)
    return missing[0] if missing else None


def prediction_progress_display(prediction_slots: dict[str, Any]) -> dict[str, Any]:
    missing = compute_missing_fields(prediction_slots)
    return {
        "captured": {key: value for key, value in prediction_slots.items() if key in FIELD_DISPLAY_NAMES},
        "missing": missing,
        "captured_display": [FIELD_DISPLAY_NAMES[key] for key in prediction_slots if key in FIELD_DISPLAY_NAMES],
        "missing_display": [FIELD_DISPLAY_NAMES[key] for key in missing],
    }
