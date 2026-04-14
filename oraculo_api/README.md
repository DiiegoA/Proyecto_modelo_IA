---
title: Oraculo Adult Income API
emoji: 🚀
colorFrom: green
colorTo: blue
sdk: docker
app_port: 7860
base_path: /docs
pinned: false
---

# Oraculo Adult Income API

API REST profesional para inferencia del dataset Adult Census Income, reconstruida con enfoque de clean code, seguridad por capas, pruebas agresivas y contrato estable entre notebook y producción.

## Objetivo

Esta API resuelve tres problemas reales del proyecto:

1. Exponer inferencia de modelo con un contrato HTTP limpio, autenticado y auditable.
2. Blindar el salto entre `EDA_For_All_Tree_clean.ipynb` y el artefacto `pipeline_produccion.pkl`.
3. Dejar una base escalable para crecer a más endpoints, más usuarios y despliegue en Render.

## Stack elegido

Tecnologías aplicadas en la implementación final:

- `FastAPI`: framework principal, OpenAPI/Swagger, validación HTTP y alto rendimiento.
- `Python`: lenguaje base del servicio, notebook y pipeline.
- `Pydantic v2`: DTOs, validaciones estrictas, aliases y contratos de entrada/salida.
- `SQLAlchemy 2.0`: ORM principal y capa de persistencia.
- `Alembic`: migraciones versionadas de base de datos.
- `SQLite` por defecto y `PostgreSQL` listo por `DATABASE_URL`: desarrollo local y despliegue escalable.
- `JWT + bcrypt`: autenticación stateless y hashing de contraseñas.
- `Swagger/OpenAPI`: documentación viva de endpoints.
- `Pytest + TestClient`: pruebas HTTP, seguridad, errores y dominio.
- `Uvicorn`: servidor ASGI para local y producción.
- `Starlette middlewares`: CORS, GZip, Trusted Hosts, request id, límites de payload, rate limiting básico.
- `joblib + LightGBM/sklearn pipeline`: artefacto de inferencia.

Tecnología no seleccionada deliberadamente:

- `SQLModel`: no se usó en esta versión porque superpone responsabilidades con SQLAlchemy + Pydantic. Para este nivel de control y separación entre ORM y DTOs, SQLAlchemy 2.0 fue una mejor decisión.

Tecnologías adicionales que faltaban en la lista original y sí son importantes:

- `pydantic-settings` para configuración por entorno.
- `bcrypt` para hashing directo y estable.
- `httpx/TestClient` para pruebas HTTP.
- `Request ID / security headers / rate limiting` para endurecimiento operativo.

## Arquitectura

La API quedó organizada por capas:

- `app/main.py`: app factory, lifespan, middlewares y bootstrap.
- `app/api/`: routers, versionado y dependencias.
- `app/core/`: configuración, seguridad, middleware, logging, errores.
- `app/db/`: base ORM, sesión, modelos, repositorios, seeds.
- `app/services/`: reglas de negocio.
- `app/ml/`: carga del artefacto y contrato con el pipeline.
- `app/schemas/`: DTOs HTTP.
- `alembic/`: migraciones.
- `tests/`: pruebas HTTP, seguridad, esquemas y modelo.

## Funcionalidades incluidas

- Registro y login con JWT.
- Endpoint autenticado de predicción.
- Historial de predicciones por usuario.
- Consulta puntual por `prediction_id`.
- Health checks `live` y `ready`.
- Seeds de administrador por variables de entorno.
- Manejador de errores unificado.
- Headers de seguridad y request id.
- Protección por tamaño máximo de payload.
- Rate limiting in-memory.
- Compatibilidad con el artefacto actual del modelo.

## Endpoints

### Salud

- `GET /`
- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`

### Autenticación

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`

### Predicciones

- `POST /api/v1/predictions`
- `GET /api/v1/predictions`
- `GET /api/v1/predictions/{prediction_id}`

## Seguridad aplicada

### OWASP / API hardening

- JWT firmado y validado.
- Contraseñas hasheadas con `bcrypt`.
- DTOs con `extra="forbid"` para bloquear campos sorpresa.
- Validación fuerte de tipos, rangos y longitudes.
- `TrustedHostMiddleware` para rechazar hosts no permitidos.
- Headers de seguridad (`CSP`, `X-Frame-Options`, `nosniff`, `Cache-Control`).
- Límite de tamaño de payload.
- Rate limiting básico por IP.
- Errores controlados sin exponer stacktrace al cliente.
- Persistencia auditada de cada predicción.

### Vulnerabilidades orientadas a LLM

Tu lista incluía amenazas como `many-shot jailbreaking`, `indirect prompt injection`, `context hijacking`, `context poisoning`, `lost in the middle` y `context overflow`.

Punto importante:

- Esta API no expone un endpoint LLM conversacional, así que esas amenazas no aplican de forma directa al plano HTTP actual.
- Sí aplican al notebook y a cualquier automatización futura que use prompts, agentes o generación asistida.

Mitigaciones prácticas adoptadas o recomendadas:

- Tratar todo texto externo como entrada no confiable.
- No ejecutar prompts del usuario dentro del backend de inferencia.
- Mantener separación entre features del modelo y texto libre.
- Exportar el artefacto desde el notebook con validación previa.
- Generar `model_manifest.json` junto con el `.pkl` para trazabilidad.
- Evitar que la API acepte instrucciones ejecutables o plantillas arbitrarias.

## Contrato Notebook -> API

El notebook limpio `EDA_For_All_Tree_clean.ipynb` quedó orientado a producción:

- Exporta `pipeline_produccion.pkl`.
- Valida el pipeline con una muestra real antes de serializar.
- Genera `model_manifest.json`.
- Reúne artefactos serializables y modelos de forma explícita.

El backend, a través de `ModelManager` y `PipelineProduccionMLOps`, puede:

- Cargar el artefacto.
- Reconstruir artefactos faltantes si el notebook exportó algo incompleto.
- Leer el `model_manifest.json` cuando exista.

## Base de datos

Entidades incluidas:

- `users`
- `prediction_logs`

Persistencia incluida:

- usuarios autenticados
- historial de predicciones
- payload original
- payload normalizado
- request id
- latencia
- versión del modelo
- hash del payload

## Migraciones Alembic

Inicialización incluida:

- `alembic.ini`
- `alembic/env.py`
- migración inicial `initial_api_schema`

Comandos útiles:

```bash
alembic upgrade head
alembic revision --autogenerate -m "descripcion"
alembic downgrade -1
```

## Seeds

Si defines:

- `ORACULO_SEED_ADMIN_EMAIL`
- `ORACULO_SEED_ADMIN_PASSWORD`
- `ORACULO_AUTO_SEED_ADMIN=true`

la aplicación crea un administrador por bootstrap si no existe.

## Configuración

Variables principales:

- `ORACULO_DATABASE_URL`
- `ORACULO_MODEL_PATH`
- `ORACULO_JWT_SECRET_KEY`
- `ORACULO_ALLOWED_HOSTS`
- `ORACULO_CORS_ALLOW_ORIGINS`
- `ORACULO_RATE_LIMIT_REQUESTS`
- `ORACULO_RATE_LIMIT_WINDOW_SECONDS`
- `ORACULO_MAX_REQUEST_SIZE_BYTES`
- `ORACULO_DOCS_ENABLED`
- `ORACULO_SECURITY_HEADERS_ENABLED`

Uso recomendado por entorno:

- Local: crea un archivo `.env` en la raíz del proyecto.
- Hugging Face Spaces: configura estas variables desde `Settings > Variables and secrets`.
- Producción tradicional: usa variables de entorno del proveedor, no hardcodes secretos en el repositorio.

## Ejecución local

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Swagger:

- `http://127.0.0.1:8000/docs`

## Tests

La suite prueba:

- esquemas
- autenticación
- autorización
- predicción
- historial
- aislamiento de datos entre usuarios
- health checks
- middlewares de seguridad
- payload demasiado grande
- rate limit
- modelo real (`pipeline_produccion.pkl`)

Ejecución:

```bash
venv\Scripts\pytest -q
```

Estado actual de la suite:

- `35 passed`

## Despliegue en Render

Recomendación:

1. Subir el proyecto con `requirements.txt`.
2. Configurar `Start Command`:

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

3. Definir variables de entorno:

- `ORACULO_ENVIRONMENT=production`
- `ORACULO_DATABASE_URL=<postgres-url>`
- `ORACULO_JWT_SECRET_KEY=<secret-largo>`
- `ORACULO_ALLOWED_HOSTS=<tu-dominio-onrender>`
- `ORACULO_DOCS_ENABLED=false`

4. Subir `pipeline_produccion.pkl` y, cuando exista, `model_manifest.json`.

## Despliegue en Hugging Face Spaces

Este repositorio ya quedó preparado para un `Docker Space`.

Archivos listos para eso:

- `Dockerfile`
- `.dockerignore`
- front matter de Spaces al inicio de este `README.md`

Pasos:

1. Crea un nuevo Space en Hugging Face.
2. Selecciona `Docker` como SDK.
3. Sube este proyecto completo.
4. En `Settings > Variables and secrets`, configura como mínimo:

- `ORACULO_JWT_SECRET_KEY`
- `ORACULO_SEED_ADMIN_EMAIL`
- `ORACULO_SEED_ADMIN_PASSWORD`
- `ORACULO_ALLOWED_HOSTS`
- `ORACULO_DOCS_ENABLED=true`

5. Si quieres persistencia real para SQLite, usa almacenamiento persistente y define:

```bash
ORACULO_DATABASE_URL=sqlite:////data/oraculo.db
```

Si no activas almacenamiento persistente, la base será efímera y se reiniciará con el Space.

Notas importantes para Spaces:

- Swagger abrirá en `/docs` porque el Space usa `base_path: /docs`.
- El contenedor escucha en `7860`, que es el puerto esperado por el Space.
- El `Dockerfile` arranca con `alembic upgrade head` y luego `uvicorn app.main:app --host 0.0.0.0 --port 7860`.
- No necesitas un archivo `.env` dentro del Space si ya definiste las variables en `Settings > Variables and secrets`.
- Si quieres ocultar Swagger más adelante, cambia `ORACULO_DOCS_ENABLED=false`.
- El modelo `pipeline_produccion.pkl`, `adult.csv` y el código backend deben permanecer en el repositorio o en el contexto del contenedor.

### Troubleshooting en Spaces

#### El contenedor arrancó, pero el `App` tab dice "ha rechazado la conexión"

Si en los logs ves algo como esto:

- `Uvicorn running on http://0.0.0.0:7860`
- `GET /docs HTTP/1.1" 200`

entonces el contenedor sí arrancó bien y el problema no suele ser el `Dockerfile`.

La causa más común en este proyecto era de seguridad de embebido:

- Hugging Face renderiza el `App` tab dentro de un `iframe`.
- Si la API responde con `X-Frame-Options: DENY` o `Content-Security-Policy` con `frame-ancestors 'none'`, el navegador bloquea la interfaz aunque `/docs` responda `200`.

La versión actual del proyecto ya quedó ajustada para ese escenario:

- mantiene headers estrictos para tráfico normal
- permite embebido únicamente cuando la petición llega desde `*.hf.space`
- conserva Swagger funcional en `/docs`

Checklist rápida cuando pase esto:

1. Abre primero la URL directa del Space, por ejemplo `https://tu-space.hf.space/docs`.
2. Si la URL directa carga y el `App` tab no, haz `Factory reboot` del Space.
3. Verifica que tu Space realmente tenga la última versión del repositorio.
4. Revisa que `ORACULO_ALLOWED_HOSTS` incluya `*.hf.space,*.huggingface.co`.
5. Confirma que `ORACULO_DOCS_ENABLED=true` si quieres exponer Swagger.

#### No tengo `.env` en Hugging Face

Eso es normal.

- En Spaces no necesitas subir `.env`.
- Hugging Face inyecta variables y secretos desde la configuración del Space.
- Localmente sí puedes usar `.env` para desarrollar.

#### SQLite se reinicia sola en Spaces

Eso también es normal si no configuraste almacenamiento persistente.

- Sin volumen persistente, la base local es efímera.
- Si quieres conservar usuarios, historial y seeds entre reinicios, usa `/data` y configura:

```bash
ORACULO_DATABASE_URL=sqlite:////data/oraculo.db
```

## Qué falta para una versión todavía más dura

Si quieres llevarla más arriba todavía, las siguientes mejoras son naturales:

- rate limiting distribuido con Redis
- refresh tokens
- roles más finos (`admin`, `analyst`, `service`)
- observabilidad con Prometheus / OpenTelemetry
- CI con lint, type-check y cobertura
- separación formal entre API pública e interna
- Postgres nativo en desarrollo

## Resumen ejecutivo

Esta versión ya no es una API improvisada alrededor de un notebook. Ahora tienes una base con:

- arquitectura limpia
- autenticación
- persistencia
- auditoría
- migraciones
- seguridad razonable
- tests HTTP exhaustivos
- contrato más sano entre notebook y producción

Es una base seria para seguir construyendo.
