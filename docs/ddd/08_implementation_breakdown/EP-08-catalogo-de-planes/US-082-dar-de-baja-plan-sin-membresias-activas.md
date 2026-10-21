# US-082 · Dar de baja plan sin membresías activas — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-08-catalogo-de-planes/US-082-dar-de-baja-plan-sin-membresias-activas.md`
- **Épica:** EP-08 · Catálogo de planes
- **Bounded context / módulo:** Plans, con consulta a Memberships (`api/src/app/modules/plans/`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

N-22 confirma los dos supuestos de la historia: `DELETE /plans/{id}` es borrado lógico y "membresía activa" significa `pending_payment`, `active`, `expiring` o `frozen`. El contrato `memberships.service.count_active_by_plan` está en el alcance de US-092 con esa misma definición. El ciclo de imports plans ↔ memberships tiene solución documentada (import perezoso más prueba de arquitectura) y queda como riesgo, no como brecha.

## Resumen

- `DELETE /api/v1/plans/{id}` (solo admin): bloquea la fila del plan, pregunta a `memberships.service.count_active_by_plan(plan_id)` y, si el conteo es 0, fija `deleted_at` (UTC) e `is_active = false`; responde 204.
- Si hay membresías activas, responde 409 `plan_has_active_memberships` con el conteo en `message` y el plan no cambia.
- Un plan dado de baja desaparece de listas y de `GET /plans/{id}` (404), pero las membresías vendidas siguen mostrando su nombre por `plans.service.get_including_deleted` (US-079). Su nombre queda libre para un plan nuevo (N-22).
- Front: acción "Dar de baja" con `ConfirmModal`; ante 409 ofrece "Desactivar" (US-081).

## Correcciones aplicadas por DECISIONES.md

- El supuesto "el contrato no tiene endpoint de baja; se agrega `DELETE /api/v1/plans/{id}` como borrado lógico" → confirmado; deja de ser supuesto: aceptado en DECISIONES N-22.
- El supuesto "membresía activa = `pending_payment`, `active`, `expiring` o `frozen`" → confirmado como definición de RN-08: aceptado en DECISIONES N-22.
- Consecuencia de DECISIONES N-22 (nombre único entre no borrados): al dar de baja, el nombre queda libre; se prueba creando un plan nuevo con el mismo nombre.

## Validación contra el dominio

- Aggregate `Plan` (`deleted_at`); RN-08 (con membresías activas no se borra), RN-14 (borrado lógico), RN-15 (solo admin).
- Evento emitido: `PlanDeactivated(plan_id)` solo si el plan estaba activo al darlo de baja (de US-081).
- Sin funciones puras nuevas. Sin discrepancias.

## Validación contra la arquitectura

- Plans → Memberships es la única llamada en sentido contrario documentada en `03_context_map.md` 2. `plans.service` llama a `memberships.service.count_active_by_plan`; nunca importa `memberships.models` (US-022).
- Ciclo de imports: `memberships.service` importa `plans.service` a nivel de módulo (leer el plan al vender, US-084). Para no cerrar el ciclo, `plans.service` importa `memberships.service` de forma perezosa dentro de `deactivate_or_fail`, con comentario `# lazy: ciclo documentado plans↔memberships` y `# noqa: PLC0415` si la regla está activa. La prueba `test_service_import_cycles.py` (US-071) agrega el par `("plans", "memberships")` a la lista blanca y sigue exigiendo que el grafo de nivel de módulo sea acíclico. Es un riesgo controlado.
- Concurrencia: el plan se bloquea con `SELECT ... FOR UPDATE` antes de contar; para que una venta simultánea no se cuele, `sell` debe leer el plan con bloqueo compartido (`plans.service.get(plan_id, for_share=True)`), que esta historia agrega al contrato y que US-084 debe usar.
- Rol: `require_role("admin")`. Auditoría por hook: la baja lógica es `update` (US-016).
- Ningún `DELETE FROM plans.plans`: lo vigila `test_no_physical_delete.py` (US-076).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (`deleted_at` e índice único parcial del nombre existen desde `0007_plans`).

### Models
- No aplica.

### Service
- [ ] T1 · Caso de uso `async def deactivate_or_fail(session, plan_id: UUID, by: Actor) -> None`: lee el plan con `SELECT ... FOR UPDATE` (`PlanNotFound` si no existe o ya tiene `deleted_at`); import perezoso de `memberships.service`; `count = await memberships_service.count_active_by_plan(session, plan_id)`; si `count > 0` lanza `PlanHasActiveMemberships(count)`; si no, fija `deleted_at = clock.now()`, `is_active = False`, hace `flush` y emite `PlanDeactivated` si estaba activo — 2.5 h
- [ ] T2 · Excepción `PlanHasActiveMemberships(count)` en `exceptions.py` traducida a 409 `plan_has_active_memberships` con `message = "Este plan tiene N membresías activas. Desactívalo en su lugar."` — 0.5 h
- [ ] T3 · Ampliar el contrato `plans.service.get(session, plan_id, *, for_share: bool = False)` de US-079 con `SELECT ... FOR SHARE` opcional, para que `memberships.service.sell` (US-084) no venda un plan que se está dando de baja en la misma ventana — 0.5 h

### Schemas
- No aplica (sin cuerpo de entrada ni de salida).

### Router
- [ ] T4 · `DELETE /api/v1/plans/{id}` con `Depends(require_role("admin"))`, `status_code=204`; códigos 204, 401, 403, 404, 409 — 0.5 h

### Tests unitarios puros
- No aplica (sin funciones puras nuevas).

### Tests de service con PostgreSQL
- [ ] T5 · `api/tests/plans/test_service_deactivate_or_fail.py` con el `count_active_by_plan` real (o un doble inyectado mientras no exista US-092): plan con solo membresías `expired` y `cancelled` → baja con `deleted_at` e `is_active = false`, fila `update` en auditoría y `PlanDeactivated`; con 12 `active` → `PlanHasActiveMemberships(12)` y el plan intacto; con 1 `pending_payment` → bloquea; con 1 `frozen` → bloquea; baja repetida → `PlanNotFound`; después de la baja, `get_including_deleted` devuelve el nombre y un plan nuevo con el mismo nombre se crea — 2 h

### Tests de router
- [ ] T6 · `api/tests/plans/test_router_delete.py`: 204 admin; 409 con `code = "plan_has_active_memberships"`; 404 inexistente y ya dado de baja; 403 coach; 401 sin token — 1 h

### Tests de arquitectura
- [ ] T7 · Agregar `("plans", "memberships")` a `ALLOWED_LAZY` en `api/tests/architecture/test_service_import_cycles.py` (US-071) y confirmar que `test_no_physical_delete.py` (US-076) cubre `plans`; `test_no_cross_models.py` verifica que `plans` no importa `memberships.models` — 0.5 h

### Front
- [ ] T8 · Acción "Dar de baja" en el menú de cada fila de `PlansPage.tsx` con `ConfirmModal`; `useDeletePlan(id)` en `api.ts`; ante 409 el modal muestra el mensaje del API y un botón "Desactivar" que llama a `useSetPlanActive` (US-081); `// DESIGN-GAP:` mensaje de bloqueo por membresías activas — 1.5 h
- [ ] T9 · Vitest `web/src/features/plans/pages/PlansPage.delete.test.tsx`: baja exitosa quita la fila, 409 muestra el mensaje y "Desactivar", acción oculta al coach — 1 h

### DevOps
- [ ] T10 · `docs/openapi.json` regenerado con `DELETE /plans/{id}` — 0.5 h

### Seguridad
- [ ] T11 · Revisión: el conteo del 409 solo lo ve el admin; ningún camino borra físicamente; el bloqueo `FOR UPDATE` se libera al terminar la transacción (sin bloqueos largos) — 0.5 h

## Orden de ejecución

1. T2 y T3.
2. T7 (prueba de ciclos con el par nuevo, en rojo).
3. T5 (en rojo), luego T1.
4. T4 y T6.
5. T10 y T11.
6. T9 (en rojo), luego T8.

## Dependencias técnicas

- US-081 · Activar y desactivar plan: evento `PlanDeactivated` y acción "Desactivar".
- US-079 · Listar planes: `get`, `get_including_deleted`.
- US-092 · Resumen y consultas de estado: `count_active_by_plan(plan_id)`.
- US-084 · Vender membresía: debe leer el plan con `get(plan_id, for_share=True)` para cerrar la carrera.
- US-071 · Filtrar socios: prueba `test_service_import_cycles.py`.
- US-076 · Dar de baja socio: prueba `test_no_physical_delete.py`.

## Endpoints

- `DELETE /api/v1/plans/{id}` — roles: admin

## Riesgos

- Ciclo de imports plans ↔ memberships: un import de nivel de módulo en `plans.service` rompería el arranque — mitigación: import perezoso documentado y prueba de ciclos en CI.
- Carrera entre la baja y una venta simultánea del mismo plan — mitigación: `FOR UPDATE` en la baja y `FOR SHARE` en la lectura de `sell`; si US-084 no usa `for_share`, la carrera queda abierta (anotado en sus dependencias).
- La dependencia inversa Plans → Memberships puede crecer — mitigación: la lista blanca de la prueba de ciclos solo admite este par para `count_active_by_plan`; cualquier otra llamada nueva falla en CI.
- Front condicionado a D1.

## Estimación

- Backend: 4 h
- Front: 2.5 h
- Pruebas: 3.5 h
- DevOps / seguridad: 1 h
- **Total: 11 h**

Supera en 1 h la referencia de 2 puntos por el bloqueo de concurrencia con `sell`.

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/plans/test_service_deactivate_or_fail.py -q`
- [ ] `cd api && uv run pytest tests/plans/test_router_delete.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/plans/pages/PlansPage.delete.test.tsx`
- [ ] `grep -rn "memberships.models" api/src/app/modules/plans` no devuelve nada.
- [ ] `curl -X DELETE /api/v1/plans/<id_con_membresias>` responde 409 `plan_has_active_memberships`; `psql -c "SELECT deleted_at FROM plans.plans WHERE id='<id_con_membresias>'"` sigue nulo.
- [ ] `cd api && uv run python -I -c "import app.modules.plans.service, app.modules.memberships.service"` termina sin error en los dos órdenes.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.plans --cov-fail-under=80`
