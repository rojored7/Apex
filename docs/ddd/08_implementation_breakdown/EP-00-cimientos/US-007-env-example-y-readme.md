# US-007 · `.env.example` completo y README de arranque — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-00-cimientos/US-007-env-example-y-readme.md`
- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context / módulo:** ninguno de negocio, terreno (`.env.example`, `README.md`, `api/tests/core/test_env_example.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 1

## Estado de preparación

**READY**

Las variables de la Tarea 0 están en `docs/PLAN.md` y la historia las completa. DECISIONES N-15 aclara que no existe una variable para el usuario técnico, y las variables que agregan otras historias (por ejemplo `FRONT_BASE_URL` de N-11 o `TRUSTED_PROXIES` de N-14) quedan obligadas por la prueba de consistencia, que es justamente el mecanismo de esta historia. No queda ningún supuesto abierto.

## Resumen

Un `.env.example` en la raíz con cada variable del sistema, un comentario de una línea por variable y valores marcador evidentes (`cambiar-esto`), y un `README.md` que lleva a una persona del equipo desde un clon limpio hasta `/health` en verde en 5 minutos, con la advertencia en negrita de que perder la KEK es perder los datos cifrados. Una prueba compara los campos de `Settings` (US-011) con las claves del archivo y falla nombrando la variable que falte.

## Correcciones aplicadas por DECISIONES.md

- No se agrega ninguna variable para el actor técnico (`SYSTEM_ACTOR_ID` u otra): el usuario técnico es la constante `SYSTEM_USER_ID` = `00000000-0000-0000-0000-000000000001`, creada por la migración `0004_auth`, no configurable: corregido por DECISIONES N-15. `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` sí se mantienen: son del primer admin humano (US-041), no del usuario técnico.
- `TZ_DISPLAY=America/Bogota` se mantiene como la lista de la Tarea 0, con el comentario de que el "hoy" de negocio no depende de esta variable: lo fija `today_bogota()` de `core/clock.py`: corregido por DECISIONES Q28 (aclaración del comentario).
- Variables que llegan con historias posteriores (`FRONT_BASE_URL` de N-11, `TRUSTED_PROXIES` de N-14, las de canales de N-35 y Q12 en v0.2): no se agregan por adelantado; la prueba de consistencia obliga a cada historia a agregarlas al crear el campo en `Settings`.

## Validación contra el dominio

- No hay aggregates, entidades, value objects, invariantes RN-xx ni eventos.

## Validación contra la arquitectura

- "Seguridad" de `CLAUDE.md`: todo por `.env`, se versiona `.env.example`, nada de secretos en el código. El `.gitignore` de US-001 ya excluye `.env` y `.env.*` salvo `!.env.example`.
- Rutas de llaves dentro del contenedor, en el volumen nombrado `keys` de US-005: `/run/apex/keys/kek.bin`, `/run/apex/keys/jwt_ed25519.pem`, `/run/apex/keys/jwt_ed25519.pub`.
- `DATABASE_URL` apunta al host `db` de Compose con driver `postgresql+asyncpg`. Las `POSTGRES_*` no son campos de `Settings`: las lee el contenedor `db`. Por eso la prueba verifica "todo campo de `Settings` está en el archivo", no igualdad.
- La prueba vive en `api/tests/core/` porque depende de `app.core.config.Settings` (US-011). La validación al arrancar de secretos presentes es de US-039.
- Sin módulos, sin bus, sin roles, sin paginación ni auditoría: no aplica.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- No aplica.

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T1 · `api/tests/core/test_env_example.py::test_toda_variable_de_settings_esta_documentada`: localiza `.env.example` en la raíz (`Path(__file__).resolve().parents[3]`), parsea las claves (líneas `CLAVE=valor`, ignora comentarios y vacías), toma `Settings.model_fields` con su alias o `env_prefix` aplicado y en mayúsculas, y falla con el nombre de cada variable faltante; `pytest.importorskip("app.core.config")` hasta que exista US-011 (criterio 1) — 1 h
- [ ] T2 · `api/tests/core/test_env_example.py::test_sin_secretos_reales`: para claves que terminan en `PASSWORD`, `SECRET`, `TOKEN` o `KEY`, el valor es vacío o contiene `cambiar-esto`; ninguna línea contiene `BEGIN PRIVATE KEY` (criterio 2) — 0,5 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- No aplica.

### Front
- No aplica.

### DevOps
- [ ] T3 · `.env.example` en la raíz, en bloques comentados: base de datos (`POSTGRES_USER=apex`, `POSTGRES_PASSWORD=cambiar-esto`, `POSTGRES_DB=apex`, `DATABASE_URL=postgresql+asyncpg://apex:cambiar-esto@db:5432/apex`); llaves (`JWT_PRIVATE_KEY_PATH=/run/apex/keys/jwt_ed25519.pem`, `JWT_PUBLIC_KEY_PATH=/run/apex/keys/jwt_ed25519.pub`, `CRYPTO_PROVIDER=local`, `CRYPTO_LOCAL_KEK_PATH=/run/apex/keys/kek.bin`); aplicación (`TZ_DISPLAY=America/Bogota`, `UPLOADS_DIR=/data/uploads`, `CORS_ORIGINS=http://localhost`, `LOG_LEVEL=INFO`); primer admin (`ADMIN_EMAIL=admin@ejemplo.local`, `ADMIN_INITIAL_PASSWORD=cambiar-esto`, comentario "un solo uso, US-041; bórrala del .env después de crear el admin"); un comentario de una línea por variable — 1 h
- [ ] T4 · `README.md` sección "Arranque en 5 minutos": requisitos (Docker Engine con Compose v2, `uv`, Node 22 para el front); pasos desde la raíz del repositorio: `cp .env.example .env` y cambiar los `cambiar-esto`; `docker compose -f infra/compose.yml -f infra/compose.dev.yml up -d --build`; `docker compose -f infra/compose.yml -f infra/compose.dev.yml run --rm tools init-keys` (US-023, servicio `tools` de US-005); comprobar `curl http://localhost:8000/health`; comandos de desarrollo de la sección "Comandos" de `CLAUDE.md` (`cd api && uv sync`, `uv run pytest`, `uv run ruff check . && uv run ruff format . && uv run mypy src`); nota para Windows: clonar dentro del sistema de archivos de WSL2 — 1 h
- [ ] T5 · `README.md` advertencia en negrita: "**Si pierdes la KEK (`kek.bin` del volumen `keys`), pierdes para siempre los datos cifrados de los socios. Respáldala fuera del servidor antes de cargar datos reales.**" con enlace al procedimiento de US-116 cuando exista — 0,5 h
- [ ] T6 · Medir el arranque siguiendo solo el README desde un clon limpio y anotar el tiempo en el PR (criterio 3; se mide cuando existan US-020 y US-023; antes se anota hasta `api` en ejecución) — 0,5 h

### Seguridad
- [ ] T7 · Revisión: ningún valor real en `.env.example`; `git check-ignore .env` responde con la regla de US-001; el README no sugiere guardar llaves en carpetas montadas desde Windows (riesgo 4 de `00b_impact_analysis.md`) — 0,5 h

## Orden de ejecución
1. T1, T2 (pruebas en rojo o saltadas hasta US-011)
2. T3 (archivo)
3. T4, T5 (README)
4. T7 (revisión)
5. T6 (medición)

## Dependencias técnicas
- US-005 · Dockerfile del api y Compose: los comandos y el servicio `tools` que documenta el README.
- US-011 · Configuración desde `.env`: `Settings`, del que depende T1 (hasta entonces la prueba se salta con `importorskip`).
- US-020 · `create_app()` y `/health`, US-023 · `cli init-keys`: necesarias para medir el arranque completo (T6).

## Endpoints
- Ninguno.

## Riesgos
- `importorskip` deja la prueba en "saltada" y nadie lo nota cuando US-011 se integra con otro nombre de módulo — mitigación: US-011 incluye en su Definición de hecho que `tests/core/test_env_example.py` pasa de "skipped" a "passed".
- Nombre de variable distinto entre `Settings` y `.env.example` por `env_prefix` o alias de pydantic-settings — mitigación: T1 calcula el nombre de la misma forma que pydantic-settings (alias si existe, si no `env_prefix` + nombre en mayúsculas).
- `CORS_ORIGINS` en formato lista: pydantic-settings espera JSON para listas — mitigación: el ejemplo usa el formato que defina US-011 (JSON `["http://localhost"]` o separado por comas con validador); T3 se ajusta en el PR de US-011 si cambia.
- Las mismas credenciales en `POSTGRES_PASSWORD` y en `DATABASE_URL` pueden quedar distintas al cambiarlas a mano — mitigación: comentario explícito en el bloque y paso del README que lo recuerda.

## Estimación
- Backend: 0 h
- Front: 0 h
- Pruebas: 1,5 h
- DevOps / seguridad: 3,5 h
- **Total: 5 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_env_example.py -q` (en verde; "skipped" solo mientras no exista US-011)
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `grep -cE "^(DATABASE_URL|JWT_PRIVATE_KEY_PATH|JWT_PUBLIC_KEY_PATH|CRYPTO_PROVIDER|CRYPTO_LOCAL_KEK_PATH|TZ_DISPLAY|UPLOADS_DIR|CORS_ORIGINS|ADMIN_EMAIL|ADMIN_INITIAL_PASSWORD|LOG_LEVEL|POSTGRES_USER|POSTGRES_PASSWORD|POSTGRES_DB)=" .env.example` devuelve 14
- [ ] `grep -c "SYSTEM_ACTOR_ID\|SYSTEM_USER_ID" .env.example` devuelve 0
- [ ] `docker compose -f infra/compose.yml -f infra/compose.dev.yml config` termina con código 0 con un `.env` copiado del ejemplo
- [ ] Tiempo de arranque siguiendo el README anotado en el PR (5 minutos o menos hasta `/health` en 200)
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app --cov-fail-under=80`
