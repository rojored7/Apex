# US-080 · Editar plan sin afectar vendidas — desglose técnico

> **Corregido en S4A-W0-1** (`docs/ddd/blueprints/sprint-04a-plan.md`, sección 1 y enmiendas E1 a E10; registro en `docs/ddd/DECISIONES.md`, "Sprint 4A"). Donde el texto de abajo choque con estas notas, mandan las notas:
> - Sin parámetro `by: Actor`: el actor sale de `get_actor()` (contextvar de `core/context.py`); la firma es `update(session, plan_id, patch)` (S4A-D41, S4A-D22).
> - `update` toma `SELECT ... FOR UPDATE` del plan vivo (serializa dos PATCH; `sell` toma `FOR SHARE`); sin `version` ni bloqueo optimista y precio vigente al vender (riesgo aceptado, `SellMembershipIn` sin `expected_price_cop`); `PlanUpdated(plan_id, changed_fields)` lleva nombres de campo, nunca valores (S4A-D22, S4A-D60).
> - `is_active` en el cuerpo da 422 por `extra="forbid"`: activar y desactivar van por `POST /plans/{plan_id}/activate` y `/deactivate`, no por PATCH `active` (S4A-D23).
> - `PATCH /plans/{plan_id}` consume la cubeta `admin-write` (`enforce_user_limit(request, "admin-write", principal.user_id)` después del rol), declara 429 por ruta y entra en `CON_LIMITE` (S4A-D26).
> - `PlanOut` gana `active_members_count: int`, que `plans.service` llena con `_out_with_counts` llamando `memberships.service.counts_active_by_plans(session, plan_ids)` por import perezoso (par `plans` ↔ `memberships` de `LAZY_IMPORT_WHITELIST` en `tests/architecture/test_service_import_graph.py`, no `test_service_import_cycles.py` ni `ALLOWED_LAZY`); "no llama a `memberships`" queda corregido en ese punto (S4A-D25, S4A-D41).
> - La prueba conjunta de RN-04 vive en `tests/integration/`, que nace en S4A-B7 con `__init__.py` y `conftest.py` vacío (S4A-D67).
> - `plans/service.py` se parte en `plans/changes.py` solo si pasa de 600 líneas; ninguna función nueva supera 50 líneas (S4A-D72).

- **Historia:** `docs/ddd/07_user_stories/EP-08-catalogo-de-planes/US-080-editar-plan-sin-afectar-vendidas.md`
- **Épica:** EP-08 · Catálogo de planes
- **Bounded context / módulo:** Plans (`api/src/app/modules/plans/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

La validación sobre el estado resultante, RN-04 y el rol están definidos. N-22 solo agrega que renombrar respeta la unicidad del nombre entre vivos. RN-04 se garantiza en `memberships` por la copia del precio (US-084); aquí se prueba en conjunto.

## Resumen

- `PATCH /api/v1/plans/{id}` (solo admin) acepta cualquier subconjunto de `name`, `price_cop`, `kind`, `duration_days` y `class_count`; valida el plan resultante con `validate_plan`.
- `is_active` y `deleted_at` no se aceptan en este endpoint (422).
- Un nombre ya usado por otro plan vivo responde 409 `plan_name_duplicated`.
- Ninguna membresía vendida cambia: prueba conjunta con `memberships` (precio pactado y fechas intactos).
- Auditoría `update` con `before` y `after`; emite `PlanUpdated`; un PATCH sin cambios no audita ni emite.
- Front: acción "Editar" que abre el `SidePanel` precargado con el aviso "Cambiar el precio no modifica las membresías ya vendidas".

## Correcciones aplicadas por DECISIONES.md

- La historia no dice nada del nombre repetido al editar → renombrar a un nombre que ya tiene otro plan no borrado responde 409 `plan_name_duplicated` con `field = "name"` y `existing_id`: corregido por DECISIONES N-22.

## Validación contra el dominio

- Aggregate `Plan`; RN-01 (precio entero mayor que 0), RN-04 (la membresía copia precio, fechas y `classes_total` al vender; cambiar el plan no la toca), invariantes de `validate_plan` sobre el estado final, P2.
- Evento emitido: `PlanUpdated(plan_id, changed_fields)`.
- Función pura nueva: `merge_plan(current, patch) -> PlanState` (estado resultante antes de validar).
- Sin discrepancias.

## Validación contra la arquitectura

- Módulo dueño: `plans`. No llama a `memberships`: RN-04 se cumple porque `memberships` nunca lee el precio después de vender.
- La prueba conjunta de RN-04 vive en `api/tests/integration/` y puede usar los services de los dos módulos (las reglas de imports cruzados aplican a `src/`, no a las pruebas).
- Rol: `require_role("admin")`. Auditoría por hook (`update` solo con columnas cambiadas).
- `CHECK` de `0007_plans` como última defensa del estado final.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `merge_plan(current: PlanSnapshot, patch: Mapping[str, object]) -> PlanState`: aplica solo las claves enviadas; si el resultado es `kind = days`, exige que el patch traiga `class_count: null` de forma explícita cuando el plan tenía clases (si no, `PlanValidationError("class_count")`); luego `validate_plan` sobre el resultado — 1.5 h
- [ ] T2 · Caso de uso `async def update(session, plan_id: UUID, patch: PlanPatch) -> PlanOut`: `PlanNotFound` si no existe o tiene `deleted_at`; `merge_plan`; si cambia el nombre, pre-chequeo entre vivos y traducción de la `IntegrityError` a `PlanNameDuplicated`; si no hay cambios efectivos devuelve sin `flush`; asigna, hace `flush` y emite `PlanUpdated` — 2.5 h
- [ ] T3 · Evento `PlanUpdated(DomainEvent)` con `plan_id` y `changed_fields: tuple[str, ...]` — 0.5 h

### Schemas
- [ ] T4 · `PlanPatch` con los cinco campos opcionales (`StrictInt` en los enteros), `extra="forbid"` para que `is_active` o `deleted_at` respondan 422, y `model_fields_set` para distinguir "no enviado" de `null` — 1 h

### Router
- [ ] T5 · `PATCH /api/v1/plans/{id}` con `Depends(require_role("admin"))`; códigos 200, 401, 403, 404, 409, 422 — 0.5 h

### Tests unitarios puros
- [ ] T6 · `api/tests/plans/test_merge_plan.py`: cambiar solo precio; pasar a `classes` sin `class_count` (error); pasar a `classes` con 12; pasar a `days` sin `class_count: null` (error) y con `null` (válido); precio negativo (error) — 1 h

### Tests de service con PostgreSQL
- [ ] T7 · `api/tests/plans/test_service_update.py`: cambio de precio con fila `update` en auditoría con `price_cop` antes y después y `updated_at` nuevo; `PlanUpdated` emitido; PATCH sin cambios sin auditoría ni evento; dado de baja → `PlanNotFound`; nombre repetido → `PlanNameDuplicated`. Y `api/tests/integration/test_rn04_plan_price_change.py`: vende "Mensual" a 120.000 del 2026-10-01 al 2026-10-31 con `memberships.service.sell` (con una factory de membresía mientras no exista US-084), sube el plan a 135.000 y verifica que `agreed_price_cop`, `end_date` y `classes_total` siguen iguales — 2.5 h

### Tests de router
- [ ] T8 · `api/tests/plans/test_router_update.py`: 200 admin; 403 coach con el plan intacto; 401; 404; 422 `class_count`, `price_cop` (-1000 y decimales), `is_active` en el cuerpo; 409 `plan_name_duplicated` — 1.5 h

### Tests de arquitectura
- No aplica (siguen en verde `test_no_cross_models.py` y `test_every_route_has_role.py`).

### Front
- [ ] T9 · Acción "Editar" por fila en `PlansPage.tsx`; `PlanForm.tsx` en modo edición precargado, aviso fijo "Cambiar el precio no modifica las membresías ya vendidas" y envío solo de los campos modificados; `useUpdatePlan(id)` en `api.ts` que actualiza la fila e invalida `usePlans` — 2 h
- [ ] T10 · Vitest `web/src/features/plans/components/PlanForm.edit.test.tsx`: precarga, aviso visible, solo envía modificados, error de campo del 422 — 1 h

### DevOps
- [ ] T11 · `docs/openapi.json` regenerado — 0.5 h

### Seguridad
- [ ] T12 · Revisión: el coach no edita por el API; `extra="forbid"` evita cambiar `is_active` o `deleted_at` por esta ruta — 0.5 h

## Orden de ejecución

1. T6 (en rojo), luego T1.
2. T3 y T4.
3. T7 (en rojo), luego T2.
4. T5 y T8.
5. T11 y T12.
6. T10 (en rojo), luego T9.

## Dependencias técnicas

- US-079 · Listar planes: `PlanSnapshot`, `get`, página `Planes`.
- US-078 · Crear plan: `validate_plan`, `PlanForm`, índice único de nombre.
- US-084 · Vender membresía: copia del precio para la prueba conjunta de RN-04 (factory mientras tanto).
- US-016 · Hook de auditoría after_flush.

## Endpoints

- `PATCH /api/v1/plans/{id}` — roles: admin

## Riesgos

- Si `memberships` llegara a leer el precio del plan después de vender (por ejemplo, para calcular cobertura), RN-04 se rompería sin tocar `plans` — mitigación: la prueba conjunta corre en CI y detecta cualquier lectura posterior.
- Cambiar `duration_days` o `kind` de un plan con membresías vigentes puede confundir a recepción aunque no cambie lo vendido — mitigación: el aviso del formulario.
- Front condicionado a D1.

## Estimación

- Backend: 6 h
- Front: 3 h
- Pruebas: 5 h
- DevOps / seguridad: 1 h
- **Total: 15 h**

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/plans/test_merge_plan.py -q`
- [ ] `cd api && uv run pytest tests/plans/test_service_update.py -q`
- [ ] `cd api && uv run pytest tests/integration/test_rn04_plan_price_change.py -q`
- [ ] `cd api && uv run pytest tests/plans/test_router_update.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/plans/components/PlanForm.edit.test.tsx`
- [ ] Tras subir el precio: `psql -c "SELECT agreed_price_cop FROM memberships.memberships WHERE plan_id='<id>'"` sigue mostrando 120000.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.plans --cov-fail-under=80`
