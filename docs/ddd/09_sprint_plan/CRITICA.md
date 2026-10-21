# Crítica del plan de sprints (plan-critic, iteración 1)

Fecha: 21 de octubre de 2026. Revisado en profundidad: Sprints 0 a 4 y README. Sprints 5 a 10 solo por índice.

## Veredicto: RECHAZADO

Corregible con ediciones puntuales. El orden de historias y migraciones es sólido; lo que no puede ejecutarse tal cual es el mecanismo de gates por slice y la imagen Docker del API.

## Bloqueantes

### B-1. `slice-gate.sh` corre carpetas enteras de pruebas, pero el plan deja todas las pruebas de la wave en rojo antes de implementar
- Evidencia: `08/EP-00-cimientos/US-008` líneas 31 y 78 mapean `members` a `tests/members`, `core/<x>` a `tests/core`, `crypto` a `tests/crypto` (carpeta completa). `09/README.md` líneas 48 a 51 y 219 a 220 fijan "Wave 3a: todas las pruebas en rojo, luego Wave 3b". `SPRINT-01.md` líneas 92 a 154: el gate de S1-B1 (`core/audit && crypto`, línea 168) ejecutaría también `test_passwords`, `test_jwt`, `test_ratelimit`, `test_local_provider`, todas en rojo. Igual con `tests/members` en S2-B7 contra B8 y con `tests/memberships` en todo el Sprint 3.
- Front, mismo problema: A-01 (`README.md` 259 a 264) corre `npm run lint` y `npx tsc --noEmit` sobre todo el proyecto; los tests de la Wave 5a importan componentes que aún no existen.
- Por qué rompe: ningún slice obtiene el sello; `checkpoint-commit.sh` exige el sello.
- Corrección: alternar rojo y verde por slice (escribir las pruebas del slice, implementarlo, siguiente slice), y ampliar US-008 para que `slice-gate.sh <modulo> [archivos de prueba...]` acepte la lista del slice y para que `tsc` y `lint` del front se limiten a lo tocado. Relajar "falla, no por import" (`README.md` 219): una prueba de código inexistente falla por import; se crea el stub vacío antes.

### B-2. Nombres de módulo del plan que `slice-gate.sh` no acepta o no mapea
- Evidencia: T14 de US-008 (línea 86) valida `^[a-z_]+(/[a-z_]+)?$` (un solo nivel). El plan usa `web/features/auth`, `web/features/system`, `web/features/members`, `web/features/plans`, `web/features/payments`, `web/features/memberships`, `web/features/dashboard` (`SPRINT-02.md` 218 a 233, `SPRINT-03.md` 262 a 290, `SPRINT-04.md` 273 a 283). A-01 define `web/<feature>`; las dos notaciones se contradicen; `web/app` no está definido. `slice-gate.sh core/main` (`SPRINT-00.md` 210, `SPRINT-01.md` 183, `SPRINT-04.md` 249): `main.py` vive en `src/app/`, no en `core/`. `worker`, `cli`, `dashboard` (`SPRINT-04.md` 180, 225, 241) sin mapeo. `slice-gate.sh core` sobre `tests/test_ci_database.py` y `tests/architecture` (`SPRINT-00.md` 119, 128): no están bajo `tests/core`.
- Corrección: tabla de mapeo completa en US-008 (incluye `web/<feature>`, `main`, `worker`, `cli`, `dashboard`, `architecture`); regex con guiones y varios niveles; unificar la notación en todos los sprints.

### B-3. La imagen del API (US-005) no contiene `uv`, `alembic.ini` ni `migrations/`, y las demos los usan
- Evidencia: US-005 T5 y T6 (líneas 75 y 76): `uv` solo en la etapa builder; runtime copia `/app` con `PATH=/app/.venv/bin`; el Dockerfile copia `pyproject.toml`, `uv.lock` y `src`, nada más. Ninguna tarea copia `migrations/` ni `alembic.ini` (los crea US-012). T13 (línea 83): compose dev solo monta `../api/src`. US-020 línea 72: el `lifespan` corre `alembic upgrade` al arrancar; sin `migrations/` el contenedor sale con error desde el Sprint 0. Comandos que fallan: `SPRINT-00.md` 20 (`docker compose exec api uv run alembic current`), `SPRINT-01.md` 25 y 33 (`docker compose run --rm tools uv run python -m app.cli ...`; además T11 fija `entrypoint: ["python","-m","app.cli"]`, así que `uv run` llegaría como argumentos), `SPRINT-04.md` 35.
- Corrección: `COPY alembic.ini migrations ./` en builder y runtime; `../api/migrations` al bind mount de dev; `alembic heads` en `test_api_image.sh`; comandos sin `uv run`: `docker compose exec api alembic current`, `docker compose run --rm tools init-keys`, `docker compose run --rm worker python -m app.worker.main --run-once expirations`.

## Altas

### A-1. Nadie genera la llave JWT Ed25519 en Compose
- Evidencia: `08/README.md` 668 ("Nadie genera hoy la llave JWT"); US-033 83 y 114 documentan `openssl` en una carpeta del host, pero `keys` es un volumen nombrado; US-023 T8 (62) solo crea la KEK y la llave del bus. Sin pasos `JWT_` ni `openssl` en `09/`.
- Por qué rompe: desde S1-B8/B10 el API no arranca; el login del Sprint 2 no se puede demostrar.
- Corrección: `cli init-keys` crea también `jwt_ed25519.pem` y `.pub` con modo 600, con prueba, en S1-B4 o Wave 0 del Sprint 1. Corregir la demo de `SPRINT-01.md` 25: `init-keys` no crea las DEK; las crea el API al arrancar (`ensure_keys`, US-025 74, `created_by = SYSTEM_USER_ID`).

### A-2. La nota A-02 está desactualizada y nadie hace push
- Evidencia: `README.md` 266 dice que el repo "no tiene commits"; falso (`HEAD` en `main` con tres commits). `.gitattributes` existe sin `*.woff2 binary` que `SPRINT-00.md` 98 da por parte de US-001. A-02 manda commitear `docs/` y `CLAUDE.md` en `main`; US-001 13 y 73 asumen "main sin commits". US-001 100: la protección de ramas en repos privados exige plan Pro o Team. Los scripts nunca hacen push (`README.md` 251) pero `SPRINT-00.md` 119 y 246 y cada cierre piden CI en un PR sin decir quién empuja. `checkpoint-commit.sh` hace `git add -A` y barrería archivos pendientes ajenos al slice.
- Corrección: reescribir A-02: (1) `git status` y revisión; (2) rama `chore/sprint-00-cimientos` desde el `main` actual; (3) commit de T-DOC en esa rama; (4) paso humano explícito de push y PR en cada sprint; (5) confirmar el plan de GitHub antes de prometer protección de `main`. Agregar `*.woff2 binary`.

### A-3. El gate de S0-W0-4 depende de una prueba de S0-B1
- Evidencia: `SPRINT-00.md` 128 usa `tests/core/test_env_example.py` como gate de la Wave 0; esa prueba compara `.env.example` con `Settings` (US-011), que está en S0-B1 (línea 150), después de la Wave 0.
- Corrección: quitar `test_env_example.py` del gate de W0-4; dejarlo en S0-B1.

### A-4. No hay paso de línea base del entorno
- Evidencia: `00b_impact_analysis.md` 50 exige verificar en la Wave 0 puertos libres y Docker en WSL2; ningún paso del plan lo hace. La Wave 0 usa 80, 8000, 5432 y 5433 (US-005 T13); el 80 en Windows suele estar tomado.
- Corrección: slice S0-W0-0 de solo verificación: `docker version`, `docker compose version`, WSL2, `uv --version`, Python 3.12, puertos libres, Git Bash; resultado en el reporte.

### A-5. Las mitigaciones dependen de pruebas de arquitectura que `slice-gate.sh` no ejecuta
- Evidencia: `SPRINT-02.md` 295 y 296 (`test_members_encrypted_at_rest.py` "bloquea el checkpoint"); `SPRINT-03.md` 356 y 357 (`test_service_import_graph.py` "bloquea desde S3-B4"). Ambos en `tests/architecture`, sin mapeo (B-2).
- Corrección: `slice-gate.sh` incluye `tests/architecture` en cada slice.

### A-6. Dos criterios diferidos sin sprint que los cierre
- Evidencia: `SPRINT-00.md` 200: T8 de US-018 se activa con US-042, US-069 (Sprint 2) y US-074 (Sprint 3); no aparece en `SPRINT-02.md` ni `SPRINT-03.md`. `SPRINT-00.md` 130: la medición T6 de US-007 "se cierra en el Sprint 1"; `SPRINT-01.md` no la menciona.
- Corrección: T8 de US-018 en S2-B2/S2-B7 y S3-B10; T6 de US-007 en el cierre de S1-B4 o en la validación del Sprint 1.

## Medias

- M-1. S3-B3 (US-095) prueba `POST /memberships/{id}/payments`, pero el gate `membership_payability` lo registra memberships en S3-B4 (`SPRINT-03.md` 168 a 190; G-03). Declarar un doble de prueba del gate en B3 o mover la prueba de router a B4.
- M-2. `SPRINT-01.md` 219: desde S1-B9 "el arranque falla si no hay cargador", pero `auth.service.get_principal` se registra en S1-B11; `conftest` debe registrar un doble. `tests/auth/test_principal_loader.py` (139) está en B9 y su gate (`core/security`) no lo ejecuta.
- M-3. S2-F4 agrupa 8 historias (US-045 a US-052, `SPRINT-02.md` 219); excede el límite de 1 a 4 (`README.md` 56). Dividir en dos slices con sello propio.
- M-4. S2-B6 incluye `tests/audit/test_reveal_entry.py` (101); su productor US-074 llega en Sprint 3. Probar `audit.record(action='reveal')` directo, no `skip`.
- M-5. `CLAUDE.md` no lista `settings` ni `dashboard` en su estructura y T-DOC no los agrega. Agregarlos a T-DOC.
- M-6. `run-gates.sh` corre `--cov=app --cov-fail-under=80` sobre toda la app (US-008 80); el DoD lo describe por módulo (`SPRINT-01.md` 330, `SPRINT-03.md` 371). Alinear.
- M-7. Demos de `SPRINT-02.md` 19 y `SPRINT-04.md` 32 usan `docker compose up` sin `--build`. Agregar `--build` o explicar el bind mount.
- M-8. Sprint 4 es el más cargado (3 slices Wave 0, 12 backend, 4 front, 389 h). Dividir en 4A (worker, auditoría, tablero, planes) y 4B (backup, KEK, rotación, despliegue, importación, ADR).

## Bajas

- `0004_auth` inserta `SYSTEM_USER_ID` en Alembic (`SPRINT-01.md` 236); regla de datos 8 de `CLAUDE.md` dice que los datos van por CLI. Es dato de referencia para la FK: documentar la excepción.
- Rollback: el ciclo `upgrade/downgrade/upgrade` solo prueba la última migración; no hay volcado de la base de desarrollo antes de migraciones con triggers (`0002`, `0011`). Escribirlo.
- El gate de US-003 (`tests/test_ci_database.py`) usa `DATABASE_URL` mientras el plan habla de `TEST_DATABASE_URL`; si no está definida, la prueba se salta en silencio.

## Supuestos verificados

- "El repositorio no tiene commits" → FALSO.
- "La imagen del API permite `uv run alembic`" → FALSO (US-005 75 y 76).
- "Las 119 historias aparecen una sola vez; puntos y horas cuadran" → CONFIRMADO (203, 365, 374, 389, 389 h).
- "Migraciones 0001 a 0013 en orden; ninguna historia necesita una tabla posterior" → CONFIRMADO.
- "Ningún front entra antes de su API" → CONFIRMADO.
- "`btree_gist` en `postgres:16`" → plausible, no probado.
- "Volumen `keys` nombrado y usuario no root dueño" → CONFIRMADO.
- "El trigger de pagos deja pasar `updated_at`" → CONFIRMADO; sin riesgo entre el trigger de `0011` y el handler de `PaymentRegistered`.
- "`uv`, Python 3.12 y puertos libres en la máquina" → NO VERIFICABLE desde documentos (A-4).

## Qué le falta para ser APROBADO

1. B-1 y B-2: rojo por slice o lista de archivos en `slice-gate.sh`, mapeo completo y `tsc`/`lint` acotados.
2. B-3: copiar `alembic.ini` y `migrations/` a la imagen; comandos sin `uv run`.
3. A-1 y A-4: creación de la llave JWT y línea base del entorno.
4. A-2: reescribir A-02 y el flujo de push y PR.
5. A-3: mover `test_env_example.py`.
6. A-5: pruebas de arquitectura en cada gate.
7. A-6: cierres de los diferidos huérfanos.
8. Opcional: M-3 y M-8.
