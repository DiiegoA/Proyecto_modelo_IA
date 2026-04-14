# Oraculo Agente IA

`Oraculo Agente IA` es un servicio conversacional que decide entre dos capacidades:

1. Usar `oraculo_api` para pedir una predicción real del modelo Adult Income.
2. Usar RAG para contestar preguntas puntuales sobre el proyecto, la arquitectura, los contratos y la documentación.

## Flujo principal

- Si el usuario pide una predicción, el agente valida si ya tiene todos los campos del contrato `PredictionInput`.
- Si faltan campos, el agente no inventa datos: pide aclaraciones de forma explícita.
- Si el usuario hace una pregunta documental, el agente busca evidencia en el corpus indexado y responde con citas.
- Si la solicitud mezcla predicción y documentación, el agente ejecuta un flujo híbrido.

## Principios operativos

- No inventar variables para la API de predicción.
- No responder preguntas RAG sin evidencia suficiente.
- No permitir prompt injection documental ni cambios de política desde documentos recuperados.
- Mantener trazabilidad por `thread_id`, `trace_id`, citas y tool results.
