# US-093 · Pestaña Membresías de la ficha — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-09-membresias/US-093-pestana-membresias-de-la-ficha.md`
- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context / módulo:** Memberships (`api/src/app/modules/memberships/router.py`, ruta anidada bajo `/members/{id}`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

Es una vista de la lista de US-091 con un filtro fijo por socio y otro orden, más la pestaña del front. El supuesto de la historia (la ruta vive en el router de `memberships` para que `members` no dependa de `memberships`) es coherente con la arquitectura y con US-084. N-20 confirma que la ficha de un socio dado de baja se ve en solo lectura.

## Resumen

Endpoint `GET /api/v1/members/{id}/memberships` (admin y coach, paginado, orden por `start_date` descendente, incluye canceladas) que delega en `memberships.service.list(member_id=..., order="start_desc")`, y la pestaña Membresías de `Socio_Ficha` con la vigente destacada, la futura si existe, el historial y los botones Renovar, Vender, Congelar y Anular según rol y estado, decididos por una función pura del front.

## Correcciones aplicadas por DECISIONES.md

- Ninguna sobre el comportamiento; la historia ya es coherente con DECISIONES.md.
- Precisión: el criterio 2 (socio dado de baja devuelve sus membresías en solo lectura) coincide con DECISIONES N-20, que además hace visible la ficha del socio dado de baja a admin y coach.
- Cada membresía trae su lista `freezes` (N-25), para que la tarjeta muestre las congelaciones aunque el estado sea `pending_payment` (caso de US-087).

## Validación contra el dominio

- Q1: a lo sumo una vigente y una futura; la pestaña las separa con `classify_open` replicada en el front como parte de `membershipActions`.
- Q3: "Pendiente de pago" visible con texto. Q7: Congelar para admin y coach, solo sobre `active` o `expiring`. RN-15: Anular solo admin.
- Sin eventos ni reglas nuevas de dominio.
- Sin discrepancias.

## Validación contra la arquitectura

- Ruta en `memberships/router.py` con prefijo `/members/{member_id}`: `members` no importa nada de `memberships` para esta pestaña (la ficha la arma el front con dos llamadas).
- Existencia del socio por `members.service.ref(member_id)` (incluye dados de baja): 404 solo si no existe.
- Paginación común (`limit` 1 a 200, 25 por defecto; `{ items, total, limit, offset }`).
- Rol `require_role("admin", "coach")`. Lectura sin auditoría. Sin datos cifrados en la respuesta.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Parámetro interno `order: Literal["end_asc", "start_desc"]` en `memberships.service.list` (US-091) y caso de uso `list_for_member(session, member_id, page) -> Page[MembershipOut]`: `members.service.ref` → 404 `MemberNotFound` si no existe; incluye canceladas; congelaciones por lote con `_load_freezes_for` — 1 h

### Schemas
- No aplica (reutiliza `MembershipOut` y `Page` de US-084 y US-091).

### Router
- [ ] T2 · `GET /api/v1/members/{member_id}/memberships` con `require_role("admin", "coach")` y paginación común; 200, 401, 403, 404, 422 — 1 h

### Tests unitarios puros
- No aplica (la lógica de botones es del front, T6).

### Tests de service con PostgreSQL
- [ ] T3 · `api/tests/memberships/test_member_memberships_service.py`: orden por `start_date` descendente, incluye canceladas, socio dado de baja (doble de `members.service.ref`) devuelve sus membresías, socio inexistente → `MemberNotFound`, congelaciones cargadas sin N+1 — 1 h

### Tests de router
- [ ] T4 · `api/tests/memberships/test_member_memberships_router.py`: 200 con forma paginada, `limit=0` → 422, 404, 403 `member`, 401 — 1.5 h

### Tests de arquitectura
- [ ] T5 · Confirmar que `app/modules/members/` no importa `app.modules.memberships` por esta ruta (`test_service_import_graph.py`) y `test_every_route_has_role.py` — 0.25 h

### Front
- [ ] T6 · Función pura `membershipActions(memberships, role, today, memberDeleted) -> { renew, sell, freezeIds, cancelIds }` en `web/src/features/memberships/lib/rules.ts` con pruebas Vitest: Renovar si hay vigente o la última está vencida y no hay futura; Vender si no hay vigente ni futura; ninguno si el socio está dado de baja; Congelar para admin y coach sobre `active`/`expiring`; Anular solo admin — 1 h
- [ ] T7 · `web/src/features/memberships/components/MemberMembershipsTab.tsx` montada en la pestaña Membresías de `/socios/:id`: tarjeta de la vigente (plan, fechas `31 oct 2026`, días restantes, clases restantes si aplica, precio `$ 120.000`, `StatusTag` con texto, congelaciones), tarjeta de la futura, tabla paginada del historial, botones de T6 (Renovar a `/membresias/vender?socio=:id&renovar=1`, Vender, `FreezeModal`, `CancelModal`); estados de carga, vacío ("Este socio no tiene membresías. Vender") y error; `// DESIGN-GAP:` tarjeta de futura y chip "Pendiente de pago"; hook `useMemberMemberships(memberId, page)` — 3 h
- [ ] T8 · Vitest `MemberMembershipsTab.test.tsx`: escenario del BDD (vigente "Por vencer", futura "Pendiente de pago", historial, sin Renovar ni Anular para coach) — 0.75 h

### DevOps
- [ ] T9 · Regenerar `docs/openapi.json` y `web/src/core/api/types.ts` — 0.25 h

### Seguridad
- [ ] T10 · Revisar: rol en la ruta (no basta con ocultar botones); el `member_id` validado como UUID; respuesta sin datos cifrados — 0.25 h

## Orden de ejecución
1. T3 (rojo), T1 (verde)
2. T4 (rojo), T2 (verde)
3. T5, T9
4. T6 (pruebas primero), T8 (rojo), T7 (verde)
5. T10

## Dependencias técnicas
- US-091 · Listar membresías (`list`, `Page`, `MembershipOut`).
- US-084 · `members.service.ref` (contrato que se agrega a EP-07).
- US-088, US-089, US-090 · Destinos de los botones Renovar, Congelar y Anular.
- US-073 · Ver ficha del socio (contenedor de pestañas).
- US-064 · `Tabs` y `StatusTag` del kit (front).

## Endpoints
- `GET /api/v1/members/{id}/memberships` — roles: admin, coach

## Riesgos
- La regla de botones en el front puede divergir de la del backend (Q1) — mitigación: el backend sigue siendo la autoridad (409 si no procede) y `membershipActions` tiene pruebas con los mismos casos que `classify_open`.
- Front condicionado a D1.

## Estimación
- Backend: 2 h
- Front: 4 h
- Pruebas: 3.5 h
- DevOps / seguridad: 0.5 h
- **Total: 10 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/memberships/test_member_memberships_service.py -q`
- [ ] `cd api && uv run pytest tests/memberships/test_member_memberships_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/memberships`
- [ ] `curl "/api/v1/members/<id>/memberships?limit=25"` devuelve todas las membresías del socio, incluidas las canceladas, con la más reciente primero
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.memberships --cov-fail-under=80`
