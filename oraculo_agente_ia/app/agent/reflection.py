from __future__ import annotations

from typing import TYPE_CHECKING

from app.agent.types import ReflectionVerdict

if TYPE_CHECKING:
    from app.agent.model_gateway import ModelGateway


class ReflectionCritic:
    def __init__(self, model_gateway: "ModelGateway | None" = None) -> None:
        self.model_gateway = model_gateway

    def review(
        self,
        *,
        route: str,
        question: str,
        answer: str,
        citations: list[dict],
        missing_fields: list[str],
        prediction_result: dict | None,
        safety_flags: list[dict],
        language: str,
        history: list[dict] | None = None,
        conversation_state: dict | None = None,
    ) -> ReflectionVerdict:
        issues: list[str] = []
        suggested_answer: str | None = None
        reflection_note = ""

        if safety_flags:
            issues.append("Safety flags were raised.")
            return ReflectionVerdict(
                is_safe=False,
                has_sufficient_evidence=False,
                needs_clarification=False,
                issues=issues,
                suggested_answer="No puedo ayudar con esa solicitud de forma segura.",
                reflection_note="Se detecto una solicitud insegura; la respuesta fue bloqueada.",
            )

        if route in {"rag", "hybrid"} and not citations:
            issues.append("RAG-style answers must include citations.")
            suggested_answer = "No tengo respaldo suficiente en la base documental para responder con seguridad."

        if route == "prediction" and not missing_fields and prediction_result is None:
            issues.append("Prediction route completed without prediction result.")
            suggested_answer = "La API de prediccion no devolvio un resultado valido. Intentalo de nuevo."

        if route == "prediction" and missing_fields:
            answer_lower = answer.lower()
            requests_any_missing_field = any(field.lower() in answer_lower for field in missing_fields)
            if not requests_any_missing_field:
                issues.append("Prediction clarification should request at least one missing field.")
                suggested_answer = (
                    "Necesito un dato adicional para continuar con la prediccion. "
                    f"Por favor indicame {missing_fields[0]}."
                )
                reflection_note = "La aclaracion de prediccion no estaba solicitando los campos faltantes de forma util."

        if not issues and self.model_gateway is not None:
            review = self.model_gateway.reflect_answer(
                route=route,
                question=question,
                draft_answer=answer,
                citations=citations,
                missing_fields=missing_fields,
                prediction_result=prediction_result,
                safety_flags=safety_flags,
                language=language,
                history=history,
                conversation_state=conversation_state,
            )
            if review is not None:
                if review.issues:
                    issues.extend(review.issues)
                if review.reflection_note:
                    reflection_note = review.reflection_note
                if review.should_revise and review.improved_answer:
                    suggested_answer = review.improved_answer

        return ReflectionVerdict(
            is_safe=True,
            has_sufficient_evidence=not issues or suggested_answer is None,
            needs_clarification=bool(missing_fields),
            issues=issues,
            suggested_answer=suggested_answer,
            reflection_note=reflection_note,
            revised=bool(suggested_answer and suggested_answer != answer),
        )
