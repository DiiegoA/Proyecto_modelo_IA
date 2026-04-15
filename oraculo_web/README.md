# Oraculo Web

Frontend web en `FastAPI` para trabajar con el stack completo de Oráculo desde una interfaz minimalista y profesional.

## Qué hace

- autentica usuarios contra `oraculo_api`
- conserva la sesión en cookie del servidor
- reenvía el bearer a `oraculo_agente_ia`
- expone una experiencia chat-first con `AdultBot`
- mantiene el `thread_id` en `localStorage` para continuidad conversacional

## Experiencia actual

La UI está pensada como un workspace sobrio:

- acceso y sesión en una columna lateral compacta
- panel central de conversación con `AdultBot`
- quick actions para saludo, capacidades, predicción guiada y consulta documental
- estados visuales intermedios mientras el agente procesa
- render diferenciado para predicciones, citas y flags de seguridad

## Flujo

1. el usuario se registra o inicia sesión desde la web
2. `oraculo_web` llama a `oraculo_api`
3. guarda la sesión en cookie
4. cuando el usuario escribe, la web llama a `oraculo_agente_ia /api/v1/chat/invoke`
5. la respuesta se renderiza como conversación natural, predicción, RAG o híbrido

## Variables de entorno

```env
ORACULO_WEB_ORACULO_API_BASE_URL=https://diiegoal-oraculo-api.hf.space
ORACULO_WEB_ORACULO_AGENT_BASE_URL=https://diiegoal-oraculo-agente-ia.hf.space
ORACULO_WEB_SESSION_SECRET_KEY=change-this-session-secret-key
```

## Ejecución local

```powershell
cd "C:\Users\tobby\Documents\IA\Clase\Dataset Adult Census Income\Proyecto\oraculo_web"
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --reload --port 3000
```

Abre:

- `http://127.0.0.1:3000`

## Pruebas

```powershell
.venv\Scripts\python -m pytest -q
```

La suite valida:

- login y registro
- sesión protegida
- proxy al endpoint de chat
- render base del frontend
- compatibilidad con ruta `chat`
