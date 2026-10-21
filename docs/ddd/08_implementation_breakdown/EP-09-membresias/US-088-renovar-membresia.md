# US-088 · Renovar membresía — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-09-membresias/US-088-renovar-membresia.md`
- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context / módulo:** Memberships (`api/src/app/modules/memberships/`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

Q1 (una vigente y una futura, sin solape), Q2 (renovar es `POST /members/{id}/memberships` con `renew: true`) y N-24 (se ignora `start_date` y existe `GET /members/{id}/memberships/renewal-preview`) cierran todo lo que la historia dejaba como supuesto. Reutiliza la operación `sell` de US-084 y la rama de pago de US-085.

## Resumen

Agregar la rama `renew = true` a `memberships.service.sell`: busca la vigente del socio, rechaza si ya hay una futura, calcula `start_date = next_start_for_renewal(vigente, today_bogota())` sobre el `end_date` ya extendido por congelaciones, ignora el `start_date` recibido y aplica las mismas validaciones y el mismo primer pago opcional. Agregar la vista previa `GET /members/{id}/memberships/renewal-preview?plan_id=` y el modo renovar de `SellPage`.

## Correcciones aplicadas por DECISIONES.md

- Supuesto "con `renew: true` el `start_date` enviado se ignora": aceptado por DECISIONES N-24.
- Supuesto "`GET /api/v1/members/{id}/memberships/renewal-preview?plan_id=` con rol admin y coach que devuelve `{ start_date, end_date, agreed_price_cop }`": aceptado por DECISIONES N-24; la alternativa "el front calcula una fecha aproximada" se descarta.
- No existe `POST /memberships/{id}/renew`; el `renew(member_id, plan_id, first_payment, by)` de `05_service_design.md` no es función pública aparte sino la rama `renew` de `sell`: corregido por DECISIONES Q2.
- La membresía futura puede nacer `active` con `start_date > hoy` si el primer pago cubre: DECISIONES Q1.
- El límite de `max_retroactive_days` (N-24) no aplica a la renovación: su `start_date` es siempre hoy o posterior.

## Validación contra el dominio

- `02_domain_model.md` 2.3, invariante corregida por Q1: como máximo una vigente y una futura; renovar crea la futura al día siguiente del fin de la vigente, o hoy si ya venció o no hay.
- RN-04 y RN-05: precio copiado y fin calculado con el plan elegido (puede ser distinto del actual, criterio 8).
- RN-07: si la vigente está `frozen`, su `end_date` ya incluye la extensión; `next_start_for_renewal` usa ese valor (criterio 6).
- Eventos: `MembershipSold(renewal = True)`; si hay primer pago que cubre, `MembershipActivated` por US-086.
- Funciones puras: `next_start_for_renewal` (US-083), `compute_end_date`, `classify_open` (US-084) y una nueva `plan_renewal(current, plan, today) -> RenewalPlan(start_date, end_date, agreed_price_cop)` que comparten `sell` y la vista previa.
- Q3 (criterio 11): mientras la futura esté `pending_payment`, el estado resuelto del socio sigue siendo el de la vigente; lo garantiza `resolve_member_status` de US-092.
- Sin discrepancias.

## Validación contra la arquitectura

- Módulo dueño: `memberships`. Mismas lecturas de validación que US-084 (`members.service.ref`, `plans.service.get`); el pago, por `payments.service.register` (US-085).
- Las dos rutas viven en `memberships/router.py` bajo `/members/{id}/memberships`.
- Roles: `require_role("admin", "coach")` en ambas.
- La vigente no se modifica (criterio 10); solo hay `insert` de la nueva, auditada.
- El no solape lo garantiza la `EXCLUDE` de `0008_memberships` además del cálculo.
- Sin bus de criptografía, sin listas.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `plan_renewal(current: MembershipSnapshot | None, plan: PlanTerms, price_cop: int, today: date) -> RenewalPlan` (`start = next_start_for_renewal(current, today)`, `end = compute_end_date(start, plan)`) — 1 h
- [ ] T2 · Rama `renew = True` de `sell`: tras validar socio y plan y tomar el `pg_advisory_xact_lock`, `classify_open`; si hay futura → `FutureMembershipExists` (409 `future_membership_exists`, `existing_id`); `start_date` recibido se descarta; `plan_renewal(vigente, ...)`; crea la fila igual que la venta; `MembershipSold(renewal=True)`; si viene `first_payment`, la misma rama de US-085 — 2.5 h
- [ ] T3 · `async def renewal_preview(session, *, member_id: UUID, plan_id: UUID, clock: Clock) -> RenewalPlan` con las mismas validaciones (404, 422 `plan_inactive`, 409 `future_membership_exists`) y sin escribir nada; excepción `FutureMembershipExists` en `exceptions.py` — 1.5 h

### Schemas
- [ ] T4 · `RenewalPreviewOut(start_date: date, end_date: date, agreed_price_cop: int)`; documentar en `SellMembershipIn` que `start_date` se ignora con `renew = true` — 0.5 h

### Router
- [ ] T5 · `GET /api/v1/members/{member_id}/memberships/renewal-preview?plan_id=` con `require_role("admin", "coach")`, 200, 401, 403, 404, 409, 422; la ruta se declara antes que cualquier `/{membership_id}` para que no la capture otra plantilla — 1 h

### Tests unitarios puros
- [ ] T6 · `api/tests/memberships/test_rules.py::test_plan_renewal`: vigente sin vencer (2026-10-28, fin 2026-10-31 → 2026-11-01 a 2026-12-01), vencida (2026-11-05 → 2026-11-05 a 2026-12-05), sin membresía, vigente congelada con fin ya extendido, plan por clases — 1 h

### Tests de service con PostgreSQL
- [ ] T7 · `api/tests/memberships/test_renew_service.py`: renovar antes de vencer (fechas exactas, `pending_payment`, la vigente no cambia ni tiene auditoría nueva); después de vencer con pago completo → `active` desde hoy; antes de vencer con pago completo → futura `active` con `start_date > hoy`; ya hay futura → 409 con `existing_id`; `start_date` enviado ignorado; plan distinto e inactivo; vigente congelada; no solape (consulta de rangos); la vista previa devuelve lo mismo que crea `sell` y no escribe filas — 3 h

### Tests de router
- [ ] T8 · `api/tests/memberships/test_renew_router.py`: 201 de renovación, 409 `future_membership_exists`, 403 `member`, 401; vista previa 200, 404, 409, 422 por `plan_id` ausente — 2 h

### Tests de arquitectura
- [ ] T9 · Confirmar `test_every_route_has_role.py` con la ruta de vista previa — 0.5 h

### Front
- [ ] T10 · `api.ts`: `useRenewalPreview(memberId, planId)` (`useQuery`, se habilita con plan elegido) y uso de `useSellMembership` con `renew: true`; `SellPage` en modo renovar con `?socio=:id&renovar=1`: socio fijo, plan precargado con el de la vigente si sigue activo, fecha de inicio de solo lectura con el texto "Empieza el 1 nov 2026, al día siguiente de que termine la actual" (o "hoy" si venció), bloque de primer pago de US-085, botón "Renovar"; 409 `future_membership_exists` con enlace a la ficha — 3.5 h
- [ ] T11 · Vitest `SellPage.renew.test.tsx`: fecha calculada visible y no editable, cambio de plan refresca la vista previa, 409 — 1.5 h

### DevOps
- [ ] T12 · Regenerar `docs/openapi.json` y `web/src/core/api/types.ts` — 0.5 h

### Seguridad
- [ ] T13 · Revisar: rol en la vista previa; la vista previa no revela datos de otro socio (solo fechas y precio del plan); `start_date` manipulado no tiene efecto — 0.5 h

## Orden de ejecución
1. T6 (rojo), T1
2. T7 (rojo), T2, T3 (verde)
3. T4, T8 (rojo), T5 (verde)
4. T9, T12
5. T11 (rojo), T10 (verde)
6. T13

## Dependencias técnicas
- US-084 · Vender membresía: `sell`, `classify_open`, endpoint y `SellPage`.
- US-085 · Vender con primer pago (rama `first_payment` y cierre de la brecha con Payments).
- US-086 · Activar por cobertura (renovar con pago completo).
- US-083 · `next_start_for_renewal`, `compute_end_date`.
- US-089 · Congelaciones (caso de vigente congelada con fin extendido).
- US-091 y US-093 · Ponen el botón "Renovar" que lleva a `?socio=:id&renovar=1`.

## Endpoints
- `POST /api/v1/members/{id}/memberships` — roles: admin, coach
- `GET /api/v1/members/{id}/memberships/renewal-preview` — roles: admin, coach

## Riesgos
- La vista previa y la venta pueden diferir si entre las dos cambia el día o alguien congela la vigente — mitigación: la respuesta de `POST` es la fuente de verdad y el front muestra las fechas devueltas.
- Una futura `pending_payment` olvidada bloquea renovar (409) — mitigación: el 409 trae `existing_id`; desde la ficha se cobra o se anula.
- Front condicionado a D1.

## Estimación
- Backend: 6.5 h
- Front: 5 h
- Pruebas: 6.5 h
- DevOps / seguridad: 1 h
- **Total: 19 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/memberships/test_rules.py -q`
- [ ] `cd api && uv run pytest tests/memberships/test_renew_service.py -q`
- [ ] `cd api && uv run pytest tests/memberships/test_renew_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/memberships`
- [ ] `curl "/api/v1/members/<id>/memberships/renewal-preview?plan_id=<plan>"` con la vigente que termina el 2026-10-31 y hoy 2026-10-28 devuelve `start_date = 2026-11-01`
- [ ] Tras renovar, `SELECT start_date, end_date FROM memberships.memberships WHERE member_id = '<id>' AND status <> 'cancelled' ORDER BY start_date` muestra rangos contiguos sin solape
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.memberships --cov-fail-under=80`
