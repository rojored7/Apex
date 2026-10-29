# US-081 · Activar y desactivar plan — desglose técnico

> **Corregido en S4A-W0-1** (`docs/ddd/blueprints/sprint-04a-plan.md`, sección 1 y enmiendas E1 a E10; registro en `docs/ddd/DECISIONES.md`, "Sprint 4A"). Donde el texto de abajo choque con estas notas, mandan las notas:
> - Sin parámetro `by: Actor`: el actor sale de `get_actor()`; la firma es `set_active(session, plan_id, active)` (S4A-D41, S4A-D23).
> - Las rutas son `POST /plans/{plan_id}/activate` y `/deactivate`, no PATCH `active`; `docs/design/ROUTES.md:39` se corrige a las dos rutas POST, la casilla Activo de la edición de `Planes.html` queda como `// DESIGN-GAP:` y la brecha va a `BRECHAS.md` §11 (S4A-D23).
> - Desactivar no consulta a `memberships` y se permite con membresías activas, incluidas las `pending_payment` (RN-08); la regla de `pending_payment` como activa solo bloquea la baja de US-082. `sell` ya traduce `plan_inactive` (422): aquí solo se agrega la prueba de integración (S4A-D23, S4A-D24).
> - `PlanOut` gana `active_members_count`; `set_active` lo llena con `_out_with_counts`, que llama `memberships.service.counts_active_by_plans` por import perezoso (par `plans` ↔ `memberships` de `LAZY_IMPORT_WHITELIST` en `tests/architecture/test_service_import_graph.py`, no `test_service_import_cycles.py` ni `ALLOWED_LAZY`); "no llama a `memberships`" se corrige en ese punto (S4A-D25, S4A-D41).
> - Las dos rutas consumen la cubeta `admin-write` después del rol, declaran 429 por ruta (`responses_for(404, 429)`) y entran en `CON_LIMITE` (S4A-D26).
> - `tests/integration/` nace en S4A-B7 con `__init__.py` y `conftest.py` vacío (S4A-D67); `plans/service.py` se parte en `plans/changes.py` solo si pasa de 600 líneas (S4A-D72).

- **Historia:** `docs/ddd/07_user_stories/EP-08-catalogo-de-planes/US-081-activar-y-desactivar-plan.md`
- **Épica:** EP-08 · Catálogo de planes
- **Bounded context / módulo:** Plans (`api/src/app/modules/plans/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

Las dos rutas están en el contrato de `05_service_design.md` sección 4, RN-08 permite desactivar siempre y el supuesto de idempotencia no cambia contrato ni esquema. El rechazo de vender un plan inactivo es criterio de US-084 y aquí solo se verifica en conjunto.

## Resumen

- `POST /api/v1/plans/{id}/deactivate` pone `is_active = false`; `POST /api/v1/plans/{id}/activate` pone `is_active = true`. Ambos solo admin, responden 200 con `PlanOut` y son idempotentes (sin cambio, sin auditoría ni evento).
- Desactivar se permite aunque el plan tenga membresías activas; esas membresías no cambian.
- Un plan inactivo deja de aparecer en `GET /plans?active=true` y `memberships.service.sell` lo rechaza con `plan_inactive` (US-084).
- Un plan inexistente o dado de baja responde 404.
- Front: acción por fila "Desactivar" (con `ConfirmModal`) y "Activar".

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md.
- Nota de consistencia con DECISIONES N-22: desactivar (esta historia) y dar de baja (`DELETE /plans/{id}`, US-082) son operaciones distintas; solo la baja consulta membresías activas.

## Validación contra el dominio

- Aggregate `Plan` (`is_active`); RN-08 (con membresías activas se desactiva, no se borra), RN-04 (lo vendido no cambia).
- Eventos: `PlanDeactivated(plan_id)` al desactivar y `PlanUpdated(plan_id, changed_fields=("is_active",))` al activar, como dice la historia (el catálogo no tiene `PlanActivated`).
- Sin funciones puras nuevas. Sin discrepancias.

## Validación contra la arquitectura

- Módulo dueño: `plans`. No llama a `memberships` (desactivar no depende de conteos).
- Rol: `require_role("admin")` en las dos rutas.
- Auditoría por hook: `update` con `is_active` antes y después, solo si cambia.
- La verificación de `plan_inactive` es de `memberships.service.sell`, que lee el plan con `plans.service.get` (US-079).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Caso de uso `async def set_active(session, plan_id: UUID, active: bool) -> PlanOut`: `PlanNotFound` si no existe o tiene `deleted_at`; si `is_active` ya es el pedido, devuelve sin `flush` (idempotente); si cambia, asigna, hace `flush` y emite `PlanDeactivated` (al desactivar) o `PlanUpdated` (al activar) — 2 h
- [ ] T2 · Evento `PlanDeactivated(DomainEvent)` con `plan_id` en `service.py` (US-082 lo reutiliza) — 0.5 h

### Schemas
- No aplica (sin cuerpo de entrada; la salida es `PlanOut` de US-078).

### Router
- [ ] T3 · `POST /api/v1/plans/{id}/activate` y `POST /api/v1/plans/{id}/deactivate` con `Depends(require_role("admin"))`; códigos 200, 401, 403, 404 — 1 h

### Tests unitarios puros
- No aplica (sin funciones puras nuevas).

### Tests de service con PostgreSQL
- [ ] T4 · `api/tests/plans/test_service_set_active.py`: desactivar deja `is_active = false`, una fila `update` y `PlanDeactivated`; desactivar otra vez no agrega auditoría ni evento; activar emite `PlanUpdated`; dado de baja → `PlanNotFound`; el plan desactivado no sale en `list(active=True)`. Y en `api/tests/integration/test_plan_deactivation_with_memberships.py`: con 4 membresías activas de "Promo Octubre" (factory mientras no exista US-084), desactivar no cambia estado, precio ni fechas; vender con el plan inactivo responde `plan_inactive` cuando exista US-084 — 3 h

### Tests de router
- [ ] T5 · `api/tests/plans/test_router_set_active.py`: 200 admin en las dos rutas; 200 idempotente; 403 coach; 401; 404 inexistente y dado de baja — 1 h

### Tests de arquitectura
- No aplica (siguen en verde `test_every_route_has_role.py` y `test_no_cross_models.py`).

### Front
- [ ] T6 · Acciones por fila en `PlansPage.tsx` según `is_active`: "Desactivar" con `ConfirmModal` ("Las membresías vigentes con este plan siguen igual; el plan deja de aparecer al vender") y "Activar"; hooks `useSetPlanActive(id)` en `api.ts` que actualizan el `StatusTag` de la fila — 2.5 h
- [ ] T7 · Vitest `web/src/features/plans/pages/PlansPage.actions.test.tsx`: modal al desactivar, cambio de etiqueta, acciones ocultas al coach — 1 h

### DevOps
- [ ] T8 · `docs/openapi.json` regenerado — 0.5 h

### Seguridad
- [ ] T9 · Revisión: el coach no cambia el estado por el API; la idempotencia no oculta errores (un 404 sigue siendo 404) — 0.5 h

## Orden de ejecución

1. T2.
2. T4 (en rojo), luego T1.
3. T3 y T5.
4. T8 y T9.
5. T7 (en rojo), luego T6.

## Dependencias técnicas

- US-079 · Listar planes: `PlanSnapshot`, filtro `active` y página.
- US-078 · Crear plan: tabla y `PlanOut`.
- US-084 · Vender membresía: rechazo `plan_inactive` (prueba conjunta).
- US-065 · SidePanel y ConfirmModal (front).

## Endpoints

- `POST /api/v1/plans/{id}/activate` — roles: admin
- `POST /api/v1/plans/{id}/deactivate` — roles: admin

## Riesgos

- Un coach con la pantalla de venta abierta vende un plan recién desactivado — mitigación: `sell` relee el plan y responde `plan_inactive` (US-084).
- La idempotencia sin auditoría puede confundirse con una petición perdida — mitigación: la respuesta 200 siempre trae el estado actual del plan.
- Front condicionado a D1.

## Estimación

- Backend: 3.5 h
- Front: 3.5 h
- Pruebas: 4 h
- DevOps / seguridad: 1 h
- **Total: 12 h**

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/plans/test_service_set_active.py -q`
- [ ] `cd api && uv run pytest tests/integration/test_plan_deactivation_with_memberships.py -q`
- [ ] `cd api && uv run pytest tests/plans/test_router_set_active.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/plans/pages/PlansPage.actions.test.tsx`
- [ ] Desactivar dos veces seguidas con `curl` y verificar `psql -c "SELECT count(*) FROM audit.audit_log WHERE table_name='plans' AND record_id='<id>' AND action='update'"` igual a 1.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.plans --cov-fail-under=80`
