# US-104 · Verificar cadena desde pantalla — desglose técnico

> **Corregido en S4A-W0-1** (`docs/ddd/blueprints/sprint-04a-plan.md`, sección 1 y enmiendas E1 a E10; registro en `docs/ddd/DECISIONES.md`, "Sprint 4A"). Donde el texto de abajo choque con estas notas, mandan las notas:
> - `verify_chain(rows, *, start_prev_hash=ZERO_HASH, start_seq=1) -> VerifyResult` ampliada: `VerifyResult` gana `last_seq` y `last_hash` al final con `None` por defecto (las construcciones posicionales existentes siguen verdes); `broken_at_seq` es la primera fila que no encaja (si falta la 1234, es la 1235) y la cola perdida se marca `last_seq + 1` (S4A-D11).
> - `core/audit.py` conserva solo `verify_chain`; `AuditVerification`, `run_verification`, `format_verify_message` y las constantes nacen en `core/audit_verify.py`, que importa de `core/audit`, `core/db`, `core/clock` y `core/context` y de nadie más; `AUDIT_VERIFY_LOCK_KEY = 4_270_003` (S4A-D12).
> - La tabla es `audit.verifications` (migración `0013_audit_verifications`) y la fila `verify` de la cadena lleva `table_name="audit.verifications"`, no `"verifications"` (S4A-D12, S4A-D41).
> - Un solo nombre, `broken_at_seq`, en la columna y en el API; no existe `broken_seq` (S4A-D14).
> - `0013` suma `through_hash char(64) NOT NULL` con CHECK `^[0-9a-f]{64}$`; `run_verification` compara contra el ancla de la última verificación `ok` (exige que la fila `seq = ancla.through_seq` exista con `hash = ancla.through_hash`; si no, `ok = false` y `broken_at_seq = min(last_seq + 1, ancla.through_seq)`); solo una `ok` mueve el ancla y cada `ok` escribe `logger.info("audit anchor", ...)`; sin ancla: "íntegra desde el origen, sin verificación anterior que comparar" (S4A-D43).
> - El 202 se arma a mano en `responses=` (`responses_for` no admite 202 y `core/errors.py` no se toca); la tarea se guarda en `_BACKGROUND_TASKS` y el `shutdown` del lifespan la cancela; la conexión del candado se abre con `execution_options(isolation_level="AUTOCOMMIT")` y se cierra con `await conn.invalidate()` en el `finally` tras intentar `pg_advisory_unlock`; `VERIFY_MAX_SECONDS = 900` con `asyncio.timeout`; `test_guarded_calls.py` gana la excepción por ruta exacta con control negativo (S4A-D14, S4A-D44, enmienda E10).
> - `POST /audit/verify` consume las cubetas `audit-verify` (3/min, `USER_AUDIT_VERIFY_LIMIT_PER_MIN`) y `audit-verify-hour` (20/h, `USER_AUDIT_VERIFY_LIMIT_PER_HOUR`), no `admin-write`; declara 429 y entra en `CON_LIMITE`; `GET /audit/verify/last` va sin límite (S4A-D47, S4A-D14).
> - `VERIFY_BATCH_SIZE = 500` con lectura por rango acotado de `seq` y `await asyncio.sleep(0)` entre lotes; ningún bloque síncrono pasa de 100 ms (S4A-D47, ajustada por S4A-D120).
> - `SYNC_VERIFY_MAX_ROWS = 100_000` como valor final, calibrado por `test_verify_performance.py` (S4A-D91; S4A-D13 partía de un valor inicial que el ensayo corrigió).
> - La prueba de rendimiento se marca `perf`, no `slow`: `uv run pytest -m perf tests/audit/test_verify_performance.py -q`, fuera del gate (S4A-D41, S4A-D68).
> - El front sondea `GET /audit/verify/last` con tope de `VERIFY_MAX_SECONDS` y luego dice "la verificación no terminó; vuelve a intentarlo" (S4A-D58).

- **Historia:** `docs/ddd/07_user_stories/EP-11-auditoria/US-104-verificar-cadena-desde-pantalla.md`
- **Épica:** EP-11 · Auditoría y trazabilidad
- **Bounded context / módulo:** Audit (`api/src/app/modules/audit/` y `api/src/app/core/audit.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

DECISIONES N-30 cierra los tres puntos abiertos de la historia: rutas `POST /audit/verify` y `GET /audit/verify/last`, salto de `seq` como ruptura y persistencia de cada resultado en `audit.verifications` (migración canónica `0013_audit_verifications`). La exclusión mutua entre verificaciones se resuelve con un advisory lock de PostgreSQL, sin estado en memoria. Queda un requisito para US-015 (cómo se asigna `seq`) que se informa como contradicción entre épicas, con solución técnica clara.

## Resumen

Implementa la verificación de la cadena desde el API: `core.audit.verify_chain(rows_iter)` (pura, compartida con US-105), `audit.service.verify(by)` que recorre la cadena por lotes en orden de `seq` hasta el `through_seq` tomado al empezar, se detiene en la primera fila rota o en el primer `seq` faltante, guarda el resultado en `audit.verifications` y escribe la entrada `verify` en la propia cadena. Con 100.000 filas o menos responde 200 al terminar; con más, lanza una tarea en segundo plano y responde 202 con la última verificación. `GET /audit/verify/last` lee la última fila de `audit.verifications`. En el front, el botón "Verificar cadena" con sus estados.

## Correcciones aplicadas por DECISIONES.md

- Supuesto de la historia "no hay tabla nueva; la última verificación se lee de la entrada `verify` más reciente" → el resultado se persiste en `audit.verifications` (`started_at`, `finished_at`, `through_seq`, `ok`, `broken_at_seq`, `triggered_by`) y la última verificación se lee de ahí: corregido por DECISIONES N-30. La entrada `verify` en `audit_log` se mantiene (criterio 5 de la historia).
- Supuesto "si el API se reinicia, la verificación en curso se pierde y se puede volver a pedir" → se mantiene para la verificación en curso, pero un resultado terminado nunca se pierde porque está en `audit.verifications`: corregido por DECISIONES N-30.
- Supuesto "`GET /audit/verify/last` se agrega al contrato" y "un salto en `seq` es ruptura en el primer `seq` faltante" → aceptados por DECISIONES N-30.
- El hash usa `core.crypto.bus.digest` (SHA-256) y no `hashlib`: DECISIONES N-06.

## Validación contra el dominio

- Aggregate `AuditEntry`; RN-16: `hash = SHA-256(prev_hash || canonical(row))`, la verificación recorre toda la cadena y una fila alterada la rompe.
- Funciones puras en `core/audit.py`: `chain_hash(prev_hash, row)` (US-015) y `verify_chain(rows: Iterable[AuditRowForHash], *, start_prev_hash: str = ZERO_HASH, start_seq: int = 1) -> VerifyResult(ok, rows_checked, broken_at_seq, last_seq, last_hash)`. Detecta tres rupturas: `prev_hash` distinto del `hash` anterior, `hash` recalculado distinto del guardado y `seq` que no es el anterior más uno. Al aceptar `start_prev_hash` y `start_seq`, se puede llamar por lotes sin cargar la tabla.
- Entidad nueva `AuditVerification` (tabla `audit.verifications`), append-only, del contexto Audit. No es un aggregate de negocio; es el registro de resultados que pide N-30.
- Eventos: ninguno. La verificación escribe una entrada `verify` con `record_id = verifications.id`, `table_name = "audit.verifications"` y `after = { ok, rows_checked, broken_at_seq, through_seq, started_at, finished_at, source: "api" }`.

## Validación contra la arquitectura

- `core/audit.py` aloja `verify_chain` y el modelo `AuditVerification` (los modelos de auditoría viven en `core/audit.py`, `05_service_design.md` sección 2); `modules/audit/service.py` orquesta la lectura por lotes, el lock y la persistencia. `core/audit.py` solo depende de `core/crypto` (`bus.digest`, N-06), nunca de módulos.
- Exclusión mutua: `pg_try_advisory_lock(AUDIT_VERIFY_LOCK_KEY)` en una conexión dedicada que mantiene la verificación; si no se obtiene, 409 `verification_running`. El lock se libera solo si el proceso muere, así que un reinicio no deja la verificación "trabada" y funciona aunque Uvicorn corra con varios workers.
- Segundo plano: tarea `asyncio` creada por el service con su propia sesión y conexión, referencia guardada en un registro del módulo para que no la recoja el recolector; errores registrados en el log JSON y la tarea libera el lock en `finally`.
- Rol `require_role("admin")`. Sin bus de cifrado (solo `digest`). Lint `banned-api`: `core/audit.py` no importa `hashlib`.
- `audit.verifications` no lleva `__audited__` (su resultado ya entra a la cadena como entrada `verify`); lleva columnas comunes y el trigger append-only `audit.forbid_mutation()` de `0002_audit_log`.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- [ ] T1 · `0013_audit_verifications`: tabla `audit.verifications` con `id UUID PK`, `started_at TIMESTAMPTZ NOT NULL`, `finished_at TIMESTAMPTZ NOT NULL`, `through_seq BIGINT NOT NULL CHECK (through_seq >= 0)`, `rows_checked BIGINT NOT NULL CHECK (rows_checked >= 0)`, `ok BOOLEAN NOT NULL`, `broken_at_seq BIGINT NULL`, `triggered_by UUID NOT NULL`, `source TEXT NOT NULL CHECK (source IN ('api','cli'))`, columnas comunes; `CHECK ((ok AND broken_at_seq IS NULL) OR (NOT ok AND broken_at_seq IS NOT NULL))`, `CHECK (started_at <= finished_at)`; índice `ix_verifications_finished_at (finished_at DESC)`; trigger `verifications_forbid_mutation BEFORE UPDATE OR DELETE ... EXECUTE FUNCTION audit.forbid_mutation()`; `downgrade` elimina trigger, índice y tabla. Se agregan `rows_checked` y `source` a las columnas de N-30 porque la respuesta y US-105 los necesitan — 2 h

### Models
- [ ] T2 · `core/audit.py`: modelo `AuditVerification(CommonColumnsMixin, Base)` con `__table_args__ = {"schema": "audit"}`, sin `__audited__` — 0,5 h

### Service
- [ ] T3 · `core/audit.py`: `VerifyResult` (dataclass congelada) y función pura `verify_chain(rows, start_prev_hash, start_seq)` según "Validación contra el dominio"; constante `VERIFY_BATCH_SIZE = 500` — 2 h
- [ ] T4 · `core/audit.py`: `async def run_verification(conn, *, source: Literal["api","cli"], by: UUID) -> AuditVerification`: toma `through_seq = SELECT max(seq)`, recorre `WHERE seq > :last ORDER BY seq LIMIT :batch` con cursor de servidor, encadena `verify_chain` por lotes, se detiene en la primera ruptura, inserta `AuditVerification` y llama a `record(action="verify", table_name="audit.verifications", record_id=verification.id, after={...}, user_id=by)` en la misma transacción; nunca escribe filas existentes. Se ubica en `core` porque US-105 lo usa desde la CLI sin pasar por un módulo — 3 h
- [ ] T5 · `modules/audit/service.py`: `async def verify(by: UUID) -> VerifyOutcome` (`Finished(result)` o `Started(last)`): abre conexión dedicada, `pg_try_advisory_lock`; si no se obtiene, `VerificationRunning` (409 `verification_running`); si `max(seq) <= 100_000` (constante `SYNC_VERIFY_MAX_ROWS`, calibrada), corre `run_verification` y devuelve `Finished`; si no, crea la tarea en segundo plano y devuelve `Started(last=await last_verification())`; `async def last_verification(session) -> AuditVerification | None` — 3 h

### Schemas
- [ ] T6 · `modules/audit/schemas.py`: `VerifyResultOut { ok, rows_checked, broken_at_seq, through_seq, started_at, finished_at, triggered_by, source }` (un solo nombre, `broken_at_seq`, en la columna y en el API; S4A-D14) y `VerifyStartedOut { status: "running", last: VerifyResultOut | None }` — 0,5 h

### Router
- [ ] T7 · `modules/audit/router.py`: `POST /audit/verify` (200 `VerifyResultOut` o 202 `VerifyStartedOut`, 409) y `GET /audit/verify/last` (200 `VerifyResultOut | null`), ambos con `Depends(require_role("admin"))` y registrados antes de `GET /audit/{seq}`; códigos 200, 202, 401, 403, 409 — 1 h

### Tests unitarios puros
- [ ] T8 · `api/tests/core/test_verify_chain.py`: cadena vacía, una fila, cadena íntegra de 50, fila 1 alterada, fila del medio alterada, última alterada, fila borrada (salto de `seq` reportado en el primer faltante), `prev_hash` manipulado, verificación por dos lotes con `start_prev_hash`/`start_seq` igual a la verificación de una vez — 2 h

### Tests de service con PostgreSQL
- [ ] T9 · `api/tests/audit/test_verify.py`: cadena íntegra de 5.000 entradas (fábrica `audit_chain_factory` con `record()` real y `FrozenClock`) da `ok` y `rows_checked = 5000`; la fila 1234 alterada con `ALTER TABLE audit.audit_log DISABLE TRIGGER` dentro de la transacción de prueba da `broken_at_seq = 1234`; cada verificación deja una fila en `audit.verifications` y una entrada `verify` que entra a la cadena (una segunda verificación sigue íntegra); la verificación no cambia ninguna fila existente (hash de la tabla antes y después); `UPDATE` sobre `audit.verifications` rechazado — 3 h
- [ ] T10 · `api/tests/audit/test_verify_concurrency.py`: con el advisory lock tomado por otra conexión, `verify` levanta 409; con más de `SYNC_VERIFY_MAX_ROWS` (la prueba baja la constante por monkeypatch) devuelve `Started` y la tarea termina dejando la fila en `audit.verifications`; mientras corre, otra petición del API responde — 2 h
- [ ] T11 · `api/tests/audit/test_verify_performance.py` (marca `perf`): 100.000 filas encadenadas generadas por la fábrica, verificación completa en menos de 60 s — 1 h

### Tests de router
- [ ] T12 · `api/tests/audit/test_router_verify.py`: 200 admin con resultado, 202 con `status = "running"`, 409 `verification_running`, `GET /audit/verify/last` con y sin verificaciones previas, 403 coach, 401 sin token — 1 h

### Tests de arquitectura
- [ ] T13 · `test_banned_imports.py` (US-007/US-022) sigue verde: `core/audit.py` no importa `hashlib`; `test_every_route_has_role.py` cubre las dos rutas — 0,5 h

### Front
- [ ] T14 · `web/src/features/system/api.ts`: `useVerifyChain()` (mutación) y `useLastVerification()` con `refetchInterval` mientras el estado es `running`; `web/src/features/system/components/VerifyChainButton.tsx`: botón "Verificar cadena", estado "Verificando...", resultado "Cadena íntegra: N filas verificadas" o "Cadena rota en el registro seq X" con enlace al detalle (US-103), fecha de la última verificación en hora de Bogotá, mensaje para el 409 — 2 h
- [ ] T15 · `web/src/features/system/components/VerifyChainButton.test.tsx`: estados 200, 202 con sondeo y 409 — 1 h

### DevOps
- [ ] T16 · Regenerar `docs/openapi.json`; documentar en `docs/adr/` (junto a la serialización canónica de US-015/US-119) el algoritmo de verificación, el umbral de 100.000 filas y la clave del advisory lock — 1 h

### Seguridad
- [ ] T17 · Revisión: solo admin, la respuesta no incluye `before`/`after`, el lock no puede quedar tomado tras una excepción (`finally`), el log de la tarea en segundo plano no imprime filas — 0,5 h

## Orden de ejecución
1. T8 (pura en rojo)
2. T3
3. T1
4. T2
5. T9 (service en rojo)
6. T4
7. T10
8. T5
9. T6
10. T12 (router en rojo)
11. T7
12. T11
13. T13
14. T14, T15
15. T16
16. T17

## Dependencias técnicas
- US-015 · Tabla de auditoría y cadena de hashes: `chain_hash`, `canonical`, `record`, trigger `audit.forbid_mutation()`. Requisito: `record()` debe asignar `seq = seq_anterior + 1` bajo el mismo lock que toma el `prev_hash` (no por `nextval` de un `bigserial`), porque una transacción revertida consume valores de la secuencia y dejaría huecos que N-30 cuenta como ruptura.
- US-024 / US-025 · `core.crypto.bus.digest` (N-06).
- US-102 · Consultar auditoría: pantalla donde vive el botón.
- US-103 · Detalle: enlace al `seq` roto y orden de rutas.
- US-105 · Verificar por CLI: reutiliza `verify_chain` y `run_verification`.

## Endpoints
- `POST /api/v1/audit/verify` — roles: admin
- `GET /api/v1/audit/verify/last` — roles: admin

## Riesgos
- Huecos de `seq` por transacciones revertidas si US-015 usa `bigserial` con `nextval`: toda cadena real reportaría ruptura — mitigación: requisito explícito sobre US-015 (arriba) y prueba en T9 que revierte una transacción auditada y verifica que la cadena sigue íntegra.
- La entrada `verify` se escribe con el lock de cadena de `record()` mientras la verificación tiene su propio advisory lock; si se usara la misma clave habría interbloqueo — mitigación: claves distintas (`AUDIT_CHAIN_LOCK_KEY` y `AUDIT_VERIFY_LOCK_KEY`) y prueba T9.
- La tarea en segundo plano se pierde si el API se reinicia (aceptado por N-30; el resultado terminado sí persiste) — mitigación: el front muestra la última verificación terminada y permite pedir otra.
- Crecimiento de la cadena: la verificación completa se vuelve lenta con años de datos — mitigación: medida en T11; la firma de v0.3 (EP-17, N-32) permitirá verificar desde el último punto firmado.
- Front condicionado a D1.

## Estimación
- Backend: 12 h (T1 a T7)
- Front: 2 h (T14)
- Pruebas: 10,5 h (T8 a T13 y T15)
- DevOps / seguridad: 1,5 h (T16, T17)
- **Total: 26 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_verify_chain.py -q`
- [ ] `cd api && uv run pytest tests/audit/test_verify.py tests/audit/test_verify_concurrency.py -q`
- [ ] `cd api && uv run pytest tests/audit/test_verify_performance.py -q`
- [ ] `cd api && uv run pytest tests/audit/test_router_verify.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/system/components/VerifyChainButton.test.tsx`
- [ ] `curl -X POST /api/v1/audit/verify` con token de admin devuelve `ok: true`; `SELECT ok, through_seq, triggered_by FROM audit.verifications ORDER BY finished_at DESC LIMIT 1` muestra el mismo resultado; `SELECT action FROM audit.audit_log ORDER BY seq DESC LIMIT 1` devuelve `verify`
- [ ] Con una fila alterada en la base de prueba, `curl -X POST /api/v1/audit/verify` devuelve `ok: false` y `broken_at_seq` igual al `seq` alterado
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.audit --cov=app.core.audit --cov-fail-under=80`
