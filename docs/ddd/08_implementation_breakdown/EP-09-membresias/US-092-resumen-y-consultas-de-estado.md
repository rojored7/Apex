# US-092 · Resumen y consultas de estado — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-09-membresias/US-092-resumen-y-consultas-de-estado.md`
- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context / módulo:** Memberships (`api/src/app/modules/memberships/`), proveedor de consultas para Members, Plans, Dashboard y Classes
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

N-26 acepta los dos supuestos centrales (se cuentan socios por estado resuelto; una futura ya pagada cuenta como "al día") y N-22 fija qué es "activa" para `count_active_by_plan`. El tercer supuesto (excluir socios dados de baja pidiendo los ids a Members) es una llamada service a service permitida. Se agrega aquí el contrato `member_ids_by_status`, que US-071 consume y que se acordó al consolidar.

## Resumen

Función pura `resolve_member_status`, consultas internas `status_for(member_ids)`, `member_ids_by_status(statuses, plan_id)` y `count_active_by_plan(plan_id)`, caso de uso `summary()` y endpoint `GET /api/v1/memberships/summary` que cuenta socios no dados de baja por estado resuelto. En el front, solo el hook `useMembershipSummary` para Inicio y Socios.

## Correcciones aplicadas por DECISIONES.md

- Supuestos "el resumen cuenta socios, no filas" y "un socio cuya única membresía es una futura ya pagada cuenta como al día": aceptados por DECISIONES N-26.
- `count_active_by_plan` cuenta `pending_payment`, `active`, `expiring` y `frozen` (definición de "activa" para RN-08): aceptado por DECISIONES N-22.
- Vigente y futura según DECISIONES Q1; "hoy" = `today_bogota()` (Q28).
- Contrato agregado al consolidar: `member_ids_by_status(statuses, plan_id)` para US-071 (README, "Contratos entre services").

## Validación contra el dominio

- Consulta derivada `membership_status` del socio (`02_domain_model.md` 2.1), refinada por Q1 y N-26: ya no es "la última no cancelada" sino la prioridad de `resolve_member_status`.
- `resolve_member_status(memberships, today)`, literal de los criterios 2 a 4: se ignoran las `cancelled`; si hay vigente (`active`, `expiring` o `frozen` con `start_date <= today`) gana su estado; si no, `pending_payment` si hay una; si no, `expired` si hay una; si no, `active` si hay una futura `active` (`start_date > today`, N-26); si no, `none`.
- Q3: `pending_payment` es un estado resuelto visible.
- RN-08: `count_active_by_plan` es la única llamada de Plans hacia Memberships (mapa de contextos 2).
- No emite ni consume eventos.
- Sin discrepancias.

## Validación contra la arquitectura

- Módulo dueño: `memberships`. Consultas solo sobre su esquema.
- Llamada service a service: `members.service.active_ids() -> list[UUID]` (socios no dados de baja) para el resumen. Consumidores de este módulo: `members.service` (US-071: `status_for`, `member_ids_by_status`), `plans.service` (US-082: `count_active_by_plan`), `dashboard.service` (US-108/US-109: `summary`), `classes.service` (US-159, v0.4: `status_for`). Ninguno importa `memberships.models`.
- `status_for` sin N+1: una consulta por lote de hasta 200 ids (más ids se parten en lotes de 200).
- Rol del endpoint: `require_role("admin", "coach")`. Lectura sin auditoría. Sin datos cifrados.
- Ruta `/memberships/summary` declarada antes de `/memberships/{membership_id}` (US-091).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (índice `(member_id, status, start_date)` en `0008_memberships`).

### Models
- No aplica.

### Service
- [ ] T1 · Tipo `ResolvedStatus = Literal["active", "expiring", "expired", "frozen", "pending_payment", "none"]` y función pura `resolve_member_status(memberships: Sequence[MembershipSnapshot], today: date) -> ResolvedStatus` con la prioridad descrita — 1 h
- [ ] T2 · `async def status_for(session, member_ids: Sequence[UUID], *, today: date) -> dict[UUID, ResolvedStatus]`: una consulta `WHERE member_id = ANY(:ids) AND status <> 'cancelled'` por lote de 200; agrupa en memoria; `none` para los ids sin filas — 1.5 h
- [ ] T3 · `async def member_ids_by_status(session, statuses: frozenset[ResolvedStatus], plan_id: UUID | None, *, today: date) -> set[UUID]` (sin `none`: Members lo resuelve como complemento de todos los demás estados); `plan_id` filtra por el plan de la membresía que determina el estado resuelto; documentado en el docstring como contrato de US-071 — 1.5 h
- [ ] T4 · `async def count_active_by_plan(session, plan_id: UUID) -> int` (`status IN ('pending_payment','active','expiring','frozen')`) — 0.5 h
- [ ] T5 · `async def summary(session, *, today: date) -> MembershipSummary`: `ids = await members.service.active_ids()`, carga las no canceladas de esos socios en una consulta, resuelve con `resolve_member_status` y cuenta; devuelve los cinco contadores (los `none` no se devuelven pero se exponen en el DTO interno para la prueba de consistencia) — 2 h

### Schemas
- [ ] T6 · `MembershipSummaryOut(active: int, expiring: int, expired: int, frozen: int, pending_payment: int)` — 0.5 h

### Router
- [ ] T7 · `GET /api/v1/memberships/summary` con `require_role("admin", "coach")` y `today = clock.today_bogota()`; 200, 401, 403 — 0.5 h

### Tests unitarios puros
- [ ] T8 · `test_rules.py::test_resolve_member_status` parametrizado: solo vigente, vigente `expiring` + futura `pending_payment` (→ `expiring`), solo futura `active` (→ `active`), solo vencida, solo cancelada (→ `none`), vigente congelada, pendiente + vencida (→ `pending_payment`), vencida + futura `active` (→ `expired`, lectura literal del criterio 2), lista vacía — 1 h

### Tests de service con PostgreSQL
- [ ] T9 · `api/tests/memberships/test_status_queries_service.py`: escenario del BDD (10, 4, 4, 1, 2 con "Laura Gómez" contando como por vencer); `status_for` de 3 socios con uno sin membresías (`none`); `status_for` de 200 ids emite una sola consulta (contador de `before_cursor_execute`); `member_ids_by_status({"expiring"}, plan_id)`; `count_active_by_plan` = 3 con 2 activas, 1 pendiente y 5 vencidas; socio dado de baja (doble de `members.service.active_ids`) no entra al resumen — 3 h
- [ ] T10 · Prueba de consistencia con datos de demo (US-111): `sum(resumen) + none == len(active_ids)` y cada contador coincide con `GET /memberships?status=...` agrupado por socio — 0.5 h
- [ ] T11 · Prueba de rendimiento `@pytest.mark.slow`: resumen con 1.000 socios en menos de 300 ms — 0.5 h

### Tests de router
- [ ] T12 · `api/tests/memberships/test_summary_router.py`: 200 con los cinco enteros, 403 `member`, 401 — 1 h

### Tests de arquitectura
- [ ] T13 · Confirmar `test_no_cross_models.py` con los consumidores (`members`, `plans`, `dashboard`) importando solo `memberships.service` — 0.25 h

### Front
- [ ] T14 · `useMembershipSummary()` en `web/src/features/memberships/api.ts` con Zod `membershipSummarySchema` y prueba Vitest del parseo; sin pantalla propia — 1 h

### DevOps
- [ ] T15 · Regenerar `docs/openapi.json` — 0.25 h

### Seguridad
- No aplica más allá del rol del endpoint (verificado en T12); la respuesta son solo conteos.

## Orden de ejecución
1. T8 (rojo), T1
2. T9 (rojo), T2, T3, T4, T5 (verde)
3. T10, T11
4. T6, T12 (rojo), T7 (verde)
5. T13, T15
6. T14

## Dependencias técnicas
- US-084 · Vender membresía (tabla e índices).
- US-083 · `MembershipSnapshot`, `MembershipStatus`.
- US-069 / US-071 · `members.service.active_ids()` (supuesto de esta historia; no está escrito en EP-07 y debe agregarse a su contrato). US-071 consume `status_for` y `member_ids_by_status`.
- US-082 · consume `count_active_by_plan`.
- US-108 / US-109 · consumen `summary` y `useMembershipSummary`.
- US-111 · Datos de demostración (prueba de consistencia).

## Endpoints
- `GET /api/v1/memberships/summary` — roles: admin, coach

## Riesgos
- Que US-071 espere `member_ids_by_status` con soporte de `none` — impacto: Members no podría filtrar "Sin membresía" — mitigación: el contrato documenta que `none` es el complemento y se avisa al desglose de US-071.
- La prioridad "vencida + futura activa → vencida" puede sorprender en el tablero — mitigación: es la lectura literal de los criterios 2 y 4 y está cubierta por una prueba; si el gate prefiere "al día", es un cambio de una línea.
- Estado guardado desfasado entre medianoche y las 07:00 (job de US-094) — mitigación: aceptado.

## Estimación
- Backend: 7.5 h
- Front: 1 h
- Pruebas: 6.25 h
- DevOps / seguridad: 0.25 h
- **Total: 15 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/memberships/test_rules.py -q`
- [ ] `cd api && uv run pytest tests/memberships/test_status_queries_service.py -q`
- [ ] `cd api && uv run pytest tests/memberships/test_summary_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/memberships`
- [ ] Con datos de demo, `curl /api/v1/memberships/summary` suma, junto con los socios sin membresía, el total de `SELECT count(*) FROM members.members WHERE deleted_at IS NULL`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.memberships --cov-fail-under=80`
