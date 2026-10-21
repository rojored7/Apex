# US-020 · `create_app()`, migraciones al arrancar y `/health` — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-01-nucleo-compartido/US-020-create-app-migraciones-y-health.md`
- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context / módulo:** core (`api/src/app/main.py`, `api/src/app/core/health.py`, `api/migrations/env.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

DECISIONES N-16 acepta el supuesto de la historia: `/health` en la raíz y en `/api/v1/health`, el backup como dato informativo y 503 con OpenBao sellado. El resto del alcance está completo. Quedan resueltas dos trampas técnicas:
- correr Alembic, que es síncrono y abre su propio loop en `env.py`, desde el `lifespan` async, en un hilo aparte;
- que `app.main:app` exista para Uvicorn sin construir la app al importar el módulo, cosa que necesita US-021.

## Resumen

Esta historia entrega:
- `create_app(settings=None)`, que valida la configuración, configura los logs, registra los handlers de error, el middleware de acceso y los listeners de auditoría, carga los services (eventos) y monta los routers bajo `/api/v1`;
- un `lifespan` que ejecuta `alembic upgrade head` con el actor `SYSTEM_USER_ID`, bajo un `pg_advisory_lock` tomado en `env.py`, y luego los pasos de arranque que registren otras historias;
- `core/health.py`, con un registro de comprobaciones críticas e informativas y `GET /health` (y `/api/v1/health`), que hace `SELECT 1` con un límite de 2 s.

## Correcciones aplicadas por DECISIONES.md

- `/health` en la raíz y además en `/api/v1/health`: el supuesto queda aceptado por DECISIONES N-16.
- Las comprobaciones registradas por otras historias tienen dos niveles: `critical=True`, que pone el código en 503 si falla (OpenBao sellado, US-136), y `critical=False`, que es informativo y mantiene el 200 (backup, US-115). Lo fija DECISIONES N-16.
- Los pasos de arranque (apertura de DEKs de US-025, migraciones) corren con `actor_scope(SYSTEM_USER_ID)`, para que el `created_by` y la auditoría de lo que se cree al arrancar tengan un actor. Lo fija DECISIONES N-15.

## Validación contra el dominio

- No toca aggregates ni reglas RN. Garantiza que el esquema esté al día antes de aceptar tráfico.
- Sin eventos propios. Llama a `load_module_services()`, que registra los handlers de todos los módulos (US-014).

## Validación contra la arquitectura

- `main.py` es el único lugar que conoce la lista de módulos (`MODULES`). `core/` no importa módulos. `create_app` sí puede hacerlo, porque `main.py` no es `core/`.
- `/health` está en la lista blanca sin rol (`04_architecture_decision.md` sección 6). La prueba de rutas con rol de US-035 lo excluye por nombre.
- Todas las rutas de módulos quedan bajo `/api/v1` (criterio 6), y lo verifica una prueba de arquitectura.
- `/health` no devuelve datos personales, configuración ni errores internos: solo `status`, `db`, `version` y el estado de cada comprobación registrada (`ok`, `down` o `unknown`).
- Bus de criptografía: el arranque deja el punto `register_startup_step` para que US-025 abra las DEKs. Esta historia no importa `core/crypto`.
- Paginación y auditoría `__audited__`: no aplican.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (no crea tablas; ejecuta las existentes).

### Models
- No aplica.

### Service
- [ ] T1 · `core/config.py`: agregar `APP_VERSION: str = "dev"`, que no es secreto. El build de la imagen lo fija con el SHA de git (`ARG GIT_SHA` → `ENV APP_VERSION`) — 0,5 h
- [ ] T2 · `main.py`, con `create_app(settings: Settings | None = None) -> FastAPI`:
  1. `settings = settings or get_settings()`;
  2. `configure_logging(settings)`;
  3. `FastAPI(title="APEX API", version=settings.APP_VERSION, lifespan=lifespan, responses=ERROR_RESPONSES)`;
  4. `register_error_handlers(app)`;
  5. `app.add_middleware(RequestLogMiddleware)`;
  6. `install_audit_listeners()`;
  7. `load_module_services()`;
  8. un `APIRouter(prefix="/api/v1")` con los routers de los módulos;
  9. el router de salud montado en `/` y en `/api/v1`.
  
  Para Uvicorn, `app` se expone con `__getattr__` de módulo (PEP 562), que construye la app la primera vez que se pide `app.main.app` (criterio 7). Así, importar `create_app` no arranca nada — 2 h
- [ ] T3 · `MODULES: Final[tuple[str, ...]]` (los módulos de v0.1, que cada historia de módulo agrega); `load_module_services()`, que importa `app.modules.<x>.service`; e `include_module_routers(router)`, que importa `app.modules.<x>.router`. El worker y el CLI llaman también a `load_module_services()` — 1 h
- [ ] T4 · `lifespan(app)`:
  - dentro de `actor_scope(SYSTEM_USER_ID)`, ejecuta `await asyncio.to_thread(run_migrations, settings)`, donde `run_migrations` llama a `alembic.command.upgrade(cfg, "head")`. En otro hilo, el `asyncio.run` de `env.py` no choca con el loop de Uvicorn;
  - si la migración falla, loguea y relanza: Uvicorn termina con un código distinto de 0 y no acepta peticiones (criterio 3);
  - después ejecuta, en orden, los pasos de `register_startup_step(name, fn)` (US-025 abre las DEKs aquí).
  
  — 2 h
- [ ] T5 · `migrations/env.py`: `MIGRATION_LOCK_KEY: Final[int]` (bigint fijo, distinto de `AUDIT_CHAIN_LOCK_KEY`). Antes de `context.run_migrations()`, ejecuta `SELECT pg_advisory_lock(:key)` sobre la conexión de migración, y al terminar `pg_advisory_unlock(:key)` en un `finally`. Así el api, el worker y el CLI nunca migran a la vez (criterio 4) — 1 h
- [ ] T6 · `core/health.py`:
  - `CheckResult = Literal["ok", "down", "unknown"]`;
  - `register_health_check(name: str, fn: Callable[[], Awaitable[CheckResult]], *, critical: bool) -> None`;
  - la comprobación `db` incorporada: `SELECT 1` con `asyncio.wait_for(..., timeout=2.0)` y el engine con `connect_args={"timeout": 2}`, de modo que una base caída responde en menos de 3 s (criterio 2);
  - `async def health_status() -> tuple[int, HealthOut]`: 200 con `status = "ok"`, o 503 con `status = "degraded"` si falla una comprobación crítica;
  - `HealthOut` con `status`, `db`, `version` y una clave por cada comprobación registrada;
  - router `GET /health` sin dependencia de rol (criterios 1, 2 y 5).
  
  — 1,5 h

### Schemas
- No aplica (el schema `HealthOut` está en T6, dentro de `core/health.py`).

### Router
- No aplica, salvo `/health`, que está en T6. Los routers de módulos los aporta cada épica.

### Tests unitarios puros
- No aplica.

### Tests de service con PostgreSQL
- [ ] T7 · `tests/core/test_migration_lock.py`: dos `run_migrations` en hilos simultáneos contra `db_test` vacía terminan sin error, `alembic_version` tiene una sola fila en `head`, y el segundo espera al primero, cosa que se verifica con `pg_locks` durante la espera (criterio 4) — 1,5 h
- [ ] T8 · `tests/core/test_startup_failure.py`: con un `script_location` de prueba que contiene una migración que lanza una excepción, entrar al `lifespan` relanza el error. Además, un proceso `uvicorn` lanzado con `subprocess` termina con un código distinto de 0 (criterio 3) — 0,5 h

### Tests de router
- [ ] T9 · `tests/core/test_health.py`:
  - con la base arriba, `GET /health` y `GET /api/v1/health` dan 200 con `status = "ok"` y `db = "ok"` (criterio 1);
  - con un engine apuntando a un puerto cerrado, la respuesta es 503 con `db = "down"` en menos de 3 s (criterio 2);
  - responde sin token (criterio 5);
  - el cuerpo no contiene `DATABASE_URL`, la contraseña ni rutas de llaves;
  - una comprobación registrada con `critical=False` que falla mantiene el 200, y una con `critical=True` da 503 (N-16).
  
  — 2 h

### Tests de arquitectura
- [ ] T10 · `api/tests/architecture/test_routes_under_api_v1.py`: recorre `create_app().routes` y falla si una `APIRoute` no empieza por `/api/v1`, salvo `/health` (criterio 6). También verifica que `worker/main.py` y `cli.py` llaman a `load_module_services()` e `install_audit_listeners()` (búsqueda con `ast`) — 1,5 h

### Front
- No aplica.

### DevOps
- [ ] T11 · Smoke en Compose:
  - `docker compose -f infra/compose.yml -f infra/compose.dev.yml up -d`;
  - el healthcheck del api (US-005) usa `/health` y queda `healthy`;
  - detener `db` deja `/health` en 503;
  - `ARG GIT_SHA` en `api/Dockerfile` para `APP_VERSION`.
  
  — 1 h

### Seguridad
- [ ] T12 · Revisión:
  - `/health` no expone configuración ni trazas;
  - `version` es solo el SHA corto;
  - las migraciones corren con el actor técnico y no con un usuario real;
  - los locks asesores usan claves distintas y se liberan en `finally`;
  - N-14 (`/docs` apagado en producción) queda a cargo de EP-03 y `create_app` acepta la configuración.
  
  — 0,5 h

## Orden de ejecución
1. T9 (en rojo)
2. T1
3. T6
4. T3
5. T2
6. T5
7. T7
8. T4
9. T8
10. T10
11. T11
12. T12

## Dependencias técnicas
- US-012 · Base de datos y Alembic multiesquema: engine, `env.py` y migraciones.
- US-017 · Envelope de errores: `register_error_handlers` y `ERROR_RESPONSES`.
- US-018 · Logging JSON: `configure_logging` y `RequestLogMiddleware`.
- US-016 · Hook de auditoría: `install_audit_listeners` y `actor_scope(SYSTEM_USER_ID)` de `core/context.py`.
- US-014 · Bus de eventos: `load_module_services()` registra los handlers.
- US-005 · Dockerfile y Compose: healthcheck y `ARG GIT_SHA`.
- US-025, US-115 y US-136: registran pasos de arranque y comprobaciones de salud sobre este punto de extensión.

## Endpoints
- `GET /health` — roles: ninguno (lista blanca)
- `GET /api/v1/health` — roles: ninguno (lista blanca)

## Riesgos
- `alembic.command.upgrade` dentro del loop de Uvicorn falla con "asyncio.run() cannot be called from a running event loop" — mitigación: `asyncio.to_thread` (T4), probado en T7 y T8.
- El conector de asyncpg espera 60 s por defecto con la base caída, y `/health` incumpliría los 3 s — mitigación: `wait_for(2.0)` y `connect_args={"timeout": 2}` (T6), medido en T9.
- Un `app = create_app()` en el nivel superior del módulo obligaría a tener `.env` y llaves solo para exportar OpenAPI (US-021) — mitigación: `__getattr__` perezoso (T2).
- El api y el worker arrancan a la vez con migraciones pendientes — mitigación: lock asesor en `env.py` (T5), que cubre también al CLI.
- Una migración larga deja al api sin aceptar tráfico y Compose lo marca `unhealthy` — mitigación: `start_period` del healthcheck en US-005, ajustado por el operador; las migraciones de datos van por CLI y no por Alembic (regla 8).

## Estimación
- Backend: 8 h
- Front: 0 h
- Pruebas: 5,5 h
- DevOps / seguridad: 1,5 h
- **Total: 15 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_health.py tests/core/test_migration_lock.py tests/core/test_startup_failure.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` (con el lock asesor activo)
- [ ] `cd api && uv run uvicorn app.main:app` arranca y `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health` devuelve 200
- [ ] `curl -s http://localhost:8000/api/v1/health | jq .db` devuelve `"ok"`
- [ ] Con `docker compose -f infra/compose.yml stop db`, `curl -s -m 3 -o /dev/null -w "%{http_code}" http://localhost:8000/health` devuelve 503
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.main --cov=app.core.health --cov-fail-under=80`
