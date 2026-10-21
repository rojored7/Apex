# US-094 · Job diario de vencimientos — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-09-membresias/US-094-job-diario-de-vencimientos.md`
- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context / módulo:** Memberships (`api/src/app/modules/memberships/service.py`) y worker (`api/src/app/worker/jobs/expirations.py`), con comando en `api/src/app/cli.py`
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

El actor técnico lo unifica N-15 (`SYSTEM_USER_ID`), el "hoy" lo fija Q28, `expiring_days` sale de `settings.memberships` (Q11) y las congelaciones entran como lista (N-25). El worker, el registro de jobs y la tabla `worker.job_runs` los entrega US-113 (dependencia, no bloqueo). El comando a demanda es alcance de la propia historia y sigue la regla de N-15 de aceptar `--as`.

## Resumen

Caso de uso `memberships.service.recompute_statuses(today)` que recorre en lotes de 500 las membresías `active`, `expiring` y `frozen`, recalcula `compute_status` con `expiring_days` y las congelaciones, actualiza solo las que cambian (cada lote en su propia transacción) y emite `MembershipExpiring` o `MembershipExpired` solo en la transición. Job `expirations` registrado en el scheduler de US-113 a las 07:00 `America/Bogota` con actor `SYSTEM_USER_ID`, y comando `cli recompute-memberships [--date AAAA-MM-DD] [--as <email>]`.

## Correcciones aplicadas por DECISIONES.md

- Supuesto "el worker actúa con un usuario técnico `system` cuyo id va en `created_by` y en la auditoría" → el actor es el único usuario técnico `SYSTEM_USER_ID` = `00000000-0000-0000-0000-000000000001` (`system@apex.local`, rol admin, `is_active = false`), creado por `0004_auth`; el comando de CLI acepta `--as <email>` para atribuir la corrida a una persona: corregido por DECISIONES N-15.
- `compute_status(m, today, expiring_days)` → `compute_status(m, today, expiring_days, freezes)` con las congelaciones del lote cargadas en una consulta: corregido por DECISIONES N-25.
- `expiring_days` de `settings.memberships` (por defecto 7) y `today = today_bogota()`: DECISIONES Q11 y Q28.
- Antes de v0.4 el job solo cambia estados por fecha (`classes_remaining` no baja): DECISIONES Q4.
- Precisión: el alcance de la historia dice que "el estado también se recalcula al leer"; en este diseño se recalcula al escribir (vender, congelar, pagos, anulaciones) y las lecturas devuelven el estado guardado, para que las listas filtren en SQL; el job corrige lo que cambió por el paso del tiempo.

## Validación contra el dominio

- RN-06 corregida por Q11 y RN-07 (entrar y salir de `frozen` por fecha, criterio 5) vía `compute_status`.
- `pending_payment` y `cancelled` nunca se tocan (criterio 6): no entran en la consulta.
- Eventos emitidos solo en la transición (función pura nueva `transition_event(old, new) -> Literal["expiring", "expired"] | None`): a `expiring` desde `active` o `frozen` → `MembershipExpiring`; a `expired` desde cualquiera → `MembershipExpired`; `active`↔`frozen` no emite (la congelación ya emitió `MembershipFrozen`). Con días sin correr, `active` → `expired` emite solo `MembershipExpired` (criterio 4).
- Consumidores: Notifications (v0.2, EP-14) se suscribe a ambos eventos.
- Sin discrepancias con el dominio.

## Validación contra la arquitectura

- `04_architecture_decision.md` 5: el worker no recibe eventos; consulta la tabla y emite eventos dentro de la transacción de cada lote (los handlers corren en esa misma transacción).
- El job vive en `worker/jobs/expirations.py` y solo llama a `memberships.service.recompute_statuses`; nunca importa `memberships.models` (US-022 debe incluir `app/worker` en su barrido).
- `settings.service.memberships_policy()` para `expiring_days` (lectura).
- Actor: `current_actor` fijado en `SYSTEM_USER_ID` por el envoltorio del job (US-113) o por `--as` en el CLI; sin actor el `flush` falla (US-016, criterio 7), lo que evita auditar con `user_id` vacío.
- Auditoría: cada cambio deja `update` con `status` antes y después (hook de US-016).
- Logs JSON sin datos personales (solo ids de lote, conteos y tipo de error).
- Sin endpoints (sin rol), sin bus de criptografía.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (`worker.job_runs` es `0012_worker_job_runs`, de US-113).

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `transition_event(old: MembershipStatus, new: MembershipStatus) -> Literal["expiring", "expired"] | None` y dataclasses públicas `MembershipExpiring(membership_id, member_id, end_date, on_date)` y `MembershipExpired(membership_id, member_id, end_date, on_date)` en `memberships/service.py` — 0.75 h
- [ ] T2 · `async def recompute_statuses(session_factory: async_sessionmaker, *, today: date, batch_size: int = 500) -> RecomputeSummary`: lee `memberships_policy()`; recorre por llave (`WHERE status IN ('active','expiring','frozen') AND id > :last ORDER BY id LIMIT :batch FOR UPDATE`) abriendo una transacción por lote; carga congelaciones del lote con `_load_freezes_for`; por fila calcula `compute_status`, actualiza si cambió y emite según `transition_event`; si un lote lanza, lo revierte, registra `log.error("expirations.batch_failed", batch=n, error=type(e).__name__)` y sigue con el siguiente (el cursor avanza con el último id leído); devuelve `RecomputeSummary(revisadas, cambiadas, por_vencer, vencidas, errores)` — 4 h
- [ ] T3 · `api/src/app/worker/jobs/expirations.py`: `async def run(ctx: JobContext) -> JobResult` que fija `current_actor = SYSTEM_USER_ID`, llama `recompute_statuses(ctx.session_factory, today=ctx.clock.today_bogota())`, registra el resumen en el log JSON y lo devuelve para `worker.job_runs.details`; `result = "ok"` si `errores == 0`, si no `"error"` (re-ejecutable el mismo día, es idempotente); registro en `worker/jobs/__init__.py` a las 07:00 `America/Bogota` — 1.5 h
- [ ] T4 · `cli.py`: comando `recompute-memberships` con `--date AAAA-MM-DD` (por defecto `today_bogota()`) y `--as <email>` (por defecto `SYSTEM_USER_ID`, N-15; el email se resuelve con `auth.service`); imprime el resumen; código de salida distinto de 0 si hubo errores — 1.5 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T5 · `test_rules.py::test_transition_event` con todas las parejas relevantes (`active→expiring`, `active→expired`, `expiring→expired`, `frozen→expiring`, `frozen→active`, `active→frozen`, sin cambio) — 0.5 h

### Tests de service con PostgreSQL
- [ ] T6 · `api/tests/worker/test_expirations.py` con `FrozenClock` y base real: 2026-10-24 `active→expiring` con un `MembershipExpiring`; 2026-11-01 `expiring→expired` con un `MembershipExpired`; dos corridas el mismo día → un solo evento y una sola fila de auditoría; 2026-11-03 sobre `active` con fin 2026-10-31 → `expired` y solo `MembershipExpired`; congelación que empieza hoy → `frozen`, que terminó ayer → `active` o `expiring` según el nuevo fin; `pending_payment` y `cancelled` intactos; `FrozenClock` en 2026-11-01 02:00 UTC → sigue `expiring`; auditoría con `user_id = SYSTEM_USER_ID`; `expiring_days = 3` desde settings — 4 h
- [ ] T7 · Error por lote: con `batch_size = 2` y un handler de prueba de `MembershipExpiring` que lanza solo para el segundo lote, los lotes 1 y 3 quedan actualizados, el 2 no, y el resumen informa `errores = 1`; el log del error no contiene nombres ni documentos — 1.5 h
- [ ] T8 · Rendimiento `@pytest.mark.slow`: 1.000 socios y 3.000 membresías en menos de 60 s — 0.75 h
- [ ] T9 · `api/tests/cli/test_recompute_memberships.py` con base real: `--date` y `--as` (actor de auditoría = el usuario indicado), código de salida con y sin errores — 1 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T10 · Confirmar que `test_no_cross_models.py` barre `app/worker` y `app/cli.py` (ninguno importa `memberships.models`) y que la prueba de reloj de US-013 sigue verde (el job usa `ctx.clock`) — 0.5 h

### Front
- No aplica.

### DevOps
- [ ] T11 · Verificar en `infra/compose.yml` que el servicio `worker` (US-113) carga el job; documentar en el runbook de operación cómo correr `--run-once expirations` y `cli recompute-memberships` — 0.5 h

### Seguridad
- [ ] T12 · Revisar: `SYSTEM_USER_ID` no puede iniciar sesión (`is_active = false`); `--as` solo acepta usuarios activos con rol admin; los logs del job no incluyen datos personales ni ids de socio — 0.5 h

## Orden de ejecución
1. T5 (rojo), T1
2. T6, T7 (rojo), T2 (verde)
3. T3, T9 (rojo), T4 (verde)
4. T8, T10
5. T11, T12

## Dependencias técnicas
- US-113 · Proceso worker programado: scheduler a las 07:00 `America/Bogota`, registro de jobs, `JobContext` con `session_factory` y `clock`, tabla `worker.job_runs` (`0012_worker_job_runs`) y `--run-once`. Debe permitir que el job abra varias transacciones (una por lote) en lugar de una sola por job.
- US-083 · `compute_status`. US-084 · tabla y modelo. US-089 · `_load_freezes_for`.
- US-058 · `memberships_policy()`.
- US-016 · `current_actor` y hook de auditoría. US-041 · `0004_auth` con `SYSTEM_USER_ID`.
- US-013 · `FrozenClock`, `today_bogota()`.

## Endpoints
- Ninguno.

## Riesgos
- US-113 describe "una sesión de base y transacción propia por job", pero esta historia exige revertir solo el lote fallido — impacto: con una única transacción un error revertiría todo — mitigación: el `JobContext` entrega `session_factory` y el job maneja sus transacciones; coordinar con el desglose de US-113.
- Entre medianoche y las 07:00 de Bogotá los estados guardados van un día atrás — mitigación: aceptado (la frase guía es "al abrir"); el worker corre al arrancar si se perdió el ciclo (misfire de US-113).
- Bloqueos con el API por `FOR UPDATE` sobre 500 filas — mitigación: lotes cortos y a las 07:00 casi no hay actividad; si hiciera falta, `SKIP LOCKED` y la fila se recalcula al día siguiente.

## Estimación
- Backend: 7.75 h
- Front: 0 h
- Pruebas: 8.25 h
- DevOps / seguridad: 1 h
- **Total: 17 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/memberships/test_rules.py -q`
- [ ] `cd api && uv run pytest tests/worker/test_expirations.py -q`
- [ ] `cd api && uv run pytest tests/cli/test_recompute_memberships.py -q`
- [ ] `cd api && uv run pytest -m slow tests/worker/test_expirations.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `docker compose -f infra/compose.yml -f infra/compose.dev.yml run --rm worker uv run python -m app.worker.main --run-once expirations` termina con código 0 y deja una fila en `worker.job_runs` con `job_name = 'expirations'` y el resumen en `details`
- [ ] Correrlo dos veces seguidas no agrega filas nuevas a `audit.audit_log` para `memberships` en la segunda corrida
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.memberships --cov=app.worker.jobs.expirations --cov-fail-under=80`
