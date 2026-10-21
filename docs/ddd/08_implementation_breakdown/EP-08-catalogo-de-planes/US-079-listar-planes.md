# US-079 · Listar planes — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-08-catalogo-de-planes/US-079-listar-planes.md`
- **Épica:** EP-08 · Catálogo de planes
- **Bounded context / módulo:** Plans (`api/src/app/modules/plans/`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

La lista, los filtros, la paginación y la matriz de roles (coach solo `GET /plans?active=true`, `05_service_design.md` sección 4) están definidos y no contradicen DECISIONES.md. El supuesto del 403 para el coach es coherente con el contrato. Los contratos internos que consumen otras épicas quedan fijados aquí.

## Resumen

- `GET /api/v1/plans` paginado (`limit`/`offset`, máximo 200), con `q` por nombre sin distinguir mayúsculas ni tildes, filtro `active` y orden por nombre ascendente.
- `GET /api/v1/plans/{id}`.
- Admin ve todo; el coach solo puede pedir `active=true` (otro valor o sin el parámetro: 403) y solo puede leer un plan activo por id (inactivo: 403). Los planes con `deleted_at` nunca aparecen (404 por id).
- Contratos internos: `plans.service.get(plan_id)` para vender (US-084), `get_including_deleted(plan_id)` para mostrar el nombre en membresías de planes dados de baja (US-082) y `names_for(plan_ids)` (US-110 y la propuesta de US-071).
- Front: página `Planes` con `DataTable`, `FilterBar` y `Pagination`; hook `usePlans` que reutiliza el selector de la venta.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md.
- Consecuencia de DECISIONES N-22 (borrado lógico en US-082): `get_including_deleted` existe para que las membresías vendidas sigan mostrando el nombre de un plan dado de baja.

## Validación contra el dominio

- Lectura del aggregate `Plan`; RN-01 (precio entero), RN-14 (dados de baja fuera), RN-15 (rol).
- Sin eventos ni invariantes nuevas.
- Función pura nueva: `ensure_list_scope(role, active)` y `ensure_read_scope(role, plan)` para la regla del coach.
- Sin discrepancias.

## Validación contra la arquitectura

- Módulo dueño: `plans`. Sin llamadas a otros módulos.
- Los contratos internos devuelven la dataclass congelada `PlanSnapshot(id, name, price_cop, kind, duration_days, class_count, is_active, deleted_at)`, nunca el ORM, para que `memberships` no dependa de `plans.models` (US-022).
- Rol: `require_role("admin", "coach")` en la ruta más la regla de alcance del coach en el service (la ruta sigue declarando rol, como exige US-035).
- Paginación con `PageParams` de US-019.
- Búsqueda sin tildes con `translate(lower(name), 'áéíóúüñ', 'aeiouun')` aplicado a columna y término: función nativa de PostgreSQL, sin extensión nueva.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (el índice `ix_plans_active_alive` va en `0007_plans`, US-078).

### Models
- No aplica.

### Service
- [ ] T1 · Funciones puras `ensure_list_scope(role: Role, active: bool | None) -> None` (coach con `active` distinto de `True` lanza `PlanScopeForbidden`) y `ensure_read_scope(role: Role, plan: PlanSnapshot) -> None` (coach sobre un plan inactivo lanza `PlanScopeForbidden`) — 0.5 h
- [ ] T2 · Caso de uso `async def list(session, q: str | None, active: bool | None, page: PageParams, by: Actor) -> Page[PlanOut]`: excluye `deleted_at IS NOT NULL`, filtra `active`, busca con `translate(lower(name), ...) LIKE '%' || translate(lower(:q), ...) || '%'` con comodines escapados, orden `name, id` — 1.5 h
- [ ] T3 · Contratos internos `async def get(session, plan_id: UUID) -> PlanSnapshot` (lanza `PlanNotFound` si no existe o tiene `deleted_at`), `async def get_including_deleted(session, plan_id: UUID) -> PlanSnapshot` y `async def names_for(session, plan_ids: Iterable[UUID]) -> dict[UUID, str]` (incluye dados de baja; una sola consulta) — 1.5 h

### Schemas
- [ ] T4 · `PlanListQuery` con `q: str | None` (máximo 100) y `active: bool | None`; `PlanScopeForbidden` traducida a 403 en `exceptions.py` — 0.5 h

### Router
- [ ] T5 · `GET /api/v1/plans` y `GET /api/v1/plans/{id}` con `Depends(require_role("admin", "coach"))` y la regla de alcance de T1; códigos 200, 401, 403, 404, 422 — 1 h

### Tests unitarios puros
- [ ] T6 · `api/tests/plans/test_scope_rules.py`: admin con cualquier `active`; coach con `True` permitido, con `False` y `None` prohibido; coach sobre plan inactivo prohibido — 0.5 h

### Tests de service con PostgreSQL
- [ ] T7 · `api/tests/plans/test_service_list.py`: con "Mensual" y "Trimestral" activos y "Promo 2025" inactivo, admin sin filtro recibe 3 ordenados por nombre; `active=true` y `active=false`; `q = "TRIMES"` y `q = "promo"`; un plan con tilde se encuentra sin tilde; un dado de baja no aparece y `get` lanza `PlanNotFound`; `get_including_deleted` y `names_for` lo devuelven — 1.5 h

### Tests de router
- [ ] T8 · `api/tests/plans/test_router_list.py`: matriz admin, coach y sin token (coach 200 con `active=true`, 403 con `active=false` y sin parámetro); 422 para `limit` 500 con `field = "limit"` y `offset` -1; `GET /plans/{id}` 200 admin, 403 coach sobre inactivo, 404 inexistente y dado de baja; `price_cop` sale entero — 1.5 h

### Tests de arquitectura
- No aplica (siguen en verde `test_no_cross_models.py`, `test_every_route_has_role.py` y la prueba de `PageParams` de US-019).

### Front
- [ ] T9 · `web/src/features/plans/api.ts`: `usePlans({ q, active, limit, offset })` y `usePlan(id)`; `web/src/features/plans/pages/PlansPage.tsx` con `DataTable` (nombre, tipo, precio con `format.ts`, duración, clases, `StatusTag` "Activo"/"Inactivo" con texto), `FilterBar` (búsqueda y Activos/Inactivos/Todos), `Pagination` con `offset`, parámetros en la URL y estados de carga, vacío ("No hay planes") y error; entrada de menú oculta al coach — 3 h
- [ ] T10 · Vitest `web/src/features/plans/pages/PlansPage.test.tsx`: filtros, formato del precio, tres estados — 1.5 h

### DevOps
- [ ] T11 · `docs/openapi.json` regenerado — 0.5 h

### Seguridad
- [ ] T12 · Revisión: el coach no puede enumerar planes inactivos ni dados de baja por ninguna ruta (lista ni id); la regla vive en el API, no solo en el menú — 0.5 h

## Orden de ejecución

1. T6 (en rojo) y T1.
2. T4.
3. T7 (en rojo), luego T2 y T3.
4. T5 y T8.
5. T11 y T12.
6. T10 (en rojo) y T9.

## Dependencias técnicas

- US-078 · Crear plan: tabla, modelo, `PlanOut` e índice `ix_plans_active_alive`.
- US-019 · Contrato de paginación.
- US-034 · Dependencias current_user y require_role.
- US-063 · DataTable, Pagination, FilterBar y Chips (front).
- Consumidores: US-084 (`get`), US-082 (`get_including_deleted`), US-110 y US-071 (`names_for`).

## Endpoints

- `GET /api/v1/plans` — roles: admin, coach
- `GET /api/v1/plans/{id}` — roles: admin, coach

## Riesgos

- `translate` solo cubre las tildes del español (á, é, í, ó, ú, ü, ñ): un nombre con otro diacrítico no se encuentra sin él — mitigación: suficiente para el catálogo del gimnasio; si no, se evalúa la extensión `unaccent` en una migración nueva.
- Un coach que vende con un plan que se desactiva entre listar y vender — mitigación: `memberships.service.sell` vuelve a leer el plan con `get` y rechaza `plan_inactive` (US-084).
- Front condicionado a D1.

## Estimación

- Backend: 5 h
- Front: 4.5 h
- Pruebas: 3.5 h
- DevOps / seguridad: 1 h
- **Total: 14 h**

Supera la referencia de 2 puntos (6 a 10 h) porque fija tres contratos internos que usan EP-09, EP-12 y EP-07, además de la página completa.

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/plans/test_scope_rules.py -q`
- [ ] `cd api && uv run pytest tests/plans/test_service_list.py -q`
- [ ] `cd api && uv run pytest tests/plans/test_router_list.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/plans/pages/PlansPage.test.tsx`
- [ ] `curl "/api/v1/plans"` con token de coach responde 403 y `curl "/api/v1/plans?active=true"` responde 200 solo con planes activos.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.plans --cov-fail-under=80`
