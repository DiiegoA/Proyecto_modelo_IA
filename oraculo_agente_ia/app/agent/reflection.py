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
            suggested_answer = "La API de predicción no devolvió un resultado válido. Inténtalo de nuevo."

        if route == "prediction" and missing_fields and "faltan" not in answer.lower():
            issues.append("Prediction clarification should explicitly request missing fields.")
            suggested_answer = (
                "Necesito más datos para pedir la predicción a la API. "
                f"Campos faltantes: {', '.join(missing_fields)}."
            )

        return ReflectionVerdict(
            is_safe=True,
            has_sufficient_evidence=not issues or suggested_answer is None,
            needs_clarification=bool(missing_fields),
            issues=issues,
            suggested_answer=suggested_answer,
        )
