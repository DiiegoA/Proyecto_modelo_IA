# Oraculo Web

Cliente web en `FastAPI` para operar tu stack completo desde una sola interfaz:

- registra e inicia sesion contra `oraculo_api`
- guarda la sesion web sin pedir que el usuario pegue tokens manualmente
- reenvia el bearer a `oraculo_agente_ia`
- permite conversar en lenguaje natural para que el agente decida entre `prediction`, `rag`, `hybrid`, `clarification` o `unsafe`

## Flujo funcional

1. El usuario crea cuenta o inicia sesion desde la web.
2. `oraculo_web` llama a `oraculo_api /api/v1/auth/register` o `/api/v1/auth/login`.
3. La web conserva el `access_token` en una cookie de sesion del servidor.
4. Cuando el usuario escribe en el chat, `oraculo_web` manda el mensaje a `oraculo_agente_ia /api/v1/chat/invoke` usando ese mismo bearer.
5. El agente decide:
   - `prediction`: consulta tu API del modelo
   - `rag`: responde con conocimiento y citas
   - `hybrid`: combina ambas cosas
   - `clarification`: pide datos faltantes

## Variables de entorno

Copia `.env.example` a `.env` y ajusta lo necesario:

```env
ORACULO_WEB_ORACULO_API_BASE_URL=https://diiegoal-oraculo-api.hf.space
ORACULO_WEB_ORACULO_AGENT_BASE_URL=https://diiegoal-oraculo-agente-ia.hf.space
ORACULO_WEB_SESSION_SECRET_KEY=change-this-session-secret-key
```

## Ejecucion local

```powershell
cd "C:\Users\tobby\Documents\IA\Clase\Dataset Adult Census Income\Proyecto\oraculo_web"
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --reload --port 3000
```

Abre:

- `http://127.0.0.1:3000`

## Sugerencias de uso

- Para prediccion:
  `Haz una prediccion con este JSON: {...}`
- Para RAG:
  `Explicame que hace el proyecto y que endpoint usa el agente para chat`
- Para hybrid:
  `Haz una prediccion con este JSON y dime que endpoint usa el agente`

## Pruebas

```powershell
.venv\Scripts\python -m pytest -q
```
