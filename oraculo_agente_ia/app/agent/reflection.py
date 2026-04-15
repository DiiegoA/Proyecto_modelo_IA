from __future__ import annotations

from app.agent.types import ReflectionVerdict


class ReflectionCritic:
    def review(
        self,
        *,
        route: str,
        answer: str,
        citations: list[dict],
        missing_fields: list[str],
        prediction_result: dict | None,
        safety_flags: list[dict],
    ) -> ReflectionVerdict:
        issues: list[str] = []
        suggested_answer: str | None = None

        if safety_flags:
            issues.append("Safety flags were raised.")
            return ReflectionVerdict(
                is_safe=False,
                has_sufficient_evidence=False,
                needs_clarification=False,
                issues=issues,
                suggested_answer="No puedo ayudar con esa solicitud de forma segura.",
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

        return ReflectionVerdict(
            is_safe=True,
            has_sufficient_evidence=not issues or suggested_answer is None,
            needs_clarification=bool(missing_fields),
            issues=issues,
            suggested_answer=suggested_answer,
        )
