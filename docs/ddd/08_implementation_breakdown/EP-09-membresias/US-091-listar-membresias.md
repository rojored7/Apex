# US-091 · Listar membresías — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-09-membresias/US-091-listar-membresias.md`
- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context / módulo:** Memberships (`api/src/app/modules/memberships/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

Lectura paginada sobre la tabla propia con filtros cerrados; la búsqueda y los nombres se resuelven por services (`members.service.search_ids` y `names_for`, `plans.service.names_for`) sin joins entre esquemas, tal como quedó al consolidar. El detalle suma `paid_cop`, el contrato que US-095 necesita para la advertencia de Q5. Q3 fija cómo se ve "Pendiente de pago".

## Resumen

Casos de uso `memberships.service.list(...)` y `get(id)` con endpoints `GET /api/v1/memberships` (filtros `status` múltiple, `q`, `plan_id`, `ends_from`, `ends_to`, `member_id`, `limit`, `offset`; orden por `end_date` ascendente) y `GET /api/v1/memberships/{id}` (detalle con congelaciones, cancelación y `paid_cop`). Página `Membresias` en `/membresias` con chips, filtros en la URL, tabla, paginación y acciones Renovar, Congelar y Anular (esta solo admin).

## Correcciones aplicadas por DECISIONES.md

- Ninguna sobre el comportamiento; la historia ya es coherente con DECISIONES.md (Q3 para el chip, Q28 para las fechas, D2 para `limit`/`offset`).
- Contrato agregado al consolidar y exigido por US-095: `GET /memberships/{id}` incluye `paid_cop` (suma de pagos no anulados) además de `agreed_price_cop`.
- El detalle incluye `freezes` (lista de congelaciones) en vez de una sola ventana: consecuencia de DECISIONES N-25.

## Validación contra el dominio

- Aggregate `Membership` en modo lectura; estados de RN-06/Q11 tal como están guardados (el job de US-094 y las escrituras los mantienen al día).
- Q3: `pending_payment` es filtrable y visible.
- Q1: la lista incluye vigentes, futuras y pasadas; las canceladas solo si se piden (`status` incluye `cancelled`) o en el detalle.
- No emite ni consume eventos; ninguna función pura nueva salvo el parseo del filtro.
- Sin discrepancias.

## Validación contra la arquitectura

- Módulo dueño: `memberships`; todas las consultas son sobre `memberships.memberships` y `memberships.membership_freezes`.
- Búsqueda `q` por `members.service.search_ids(q) -> list[UUID]` (índice ciego o `ILIKE` en nombre, del lado de Members; nunca se descifra la tabla) y nombres por `members.service.names_for(ids)` y `plans.service.names_for(ids)` en lote: sin `JOIN` entre esquemas ni imports de `models` ajenos.
- `paid_cop` por `payments.service.sum_not_voided(session, membership_id)` (dirección permitida por el cierre de la brecha de US-085).
- Paginación con la dependencia común de US-019 (`limit` 1 a 200, 25 por defecto) y respuesta `{ items, total, limit, offset }`.
- Rol `require_role("admin", "coach")`.
- Lectura sin auditoría (solo se auditan escrituras y `reveal`); no hay datos cifrados en la respuesta (`member_name` es nombre y apellido en claro, RN-13).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (los índices `(status, end_date)` y `(member_id, status, start_date)` entran en `0008_memberships`).

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `parse_status_filter(raw: str | None) -> frozenset[MembershipStatus] | None` (coma separada, sin repetidos; valor desconocido → error con `field = "status"`) y validación `ends_from <= ends_to` (`field = "ends_to"`) — 0.5 h
- [ ] T2 · `async def list(session, *, statuses, q, plan_id, ends_from, ends_to, member_id, page: Pagination) -> Page[MembershipRow]`: si hay `q`, `ids = await members.service.search_ids(q)` y filtra `member_id = ANY(:ids)` (vacío → página vacía sin consultar más); `count(*)` y `SELECT` ordenado por `end_date, id` con `limit`/`offset`; completa `member_name` y `plan_name` con `names_for` en dos llamadas por página — 3 h
- [ ] T3 · `async def get(session, membership_id) -> MembershipDetail` con congelaciones (`_load_freezes`), datos de cancelación, `plan_name`, `member_name` y `paid_cop = await payments_service.sum_not_voided(...)`; 404 `MembershipNotFound` — 1.5 h

### Schemas
- [ ] T4 · `MembershipRow(id, member_id, member_name, plan_id, plan_name, agreed_price_cop: int, start_date, end_date, classes_remaining, status)`, `MembershipDetailOut(MembershipOut)` con `member_name` y `paid_cop: int`, `Page[MembershipRow]` del contrato común — 0.75 h

### Router
- [ ] T5 · `GET /api/v1/memberships` (query `status`, `q` con máximo 100 caracteres, `plan_id: UUID`, `ends_from: date`, `ends_to: date`, `member_id: UUID`, paginación) y `GET /api/v1/memberships/{membership_id}` (`UUID`), ambos `require_role("admin", "coach")`; declarar `/memberships/summary` (US-092) antes que `/{membership_id}` — 1.25 h

### Tests unitarios puros
- [ ] T6 · `test_rules.py::test_parse_status_filter` (uno, varios, repetidos, vacío, `vigente` → error) — 0.5 h

### Tests de service con PostgreSQL
- [ ] T7 · `api/tests/memberships/test_list_service.py`: filtro por `expiring` y rango de fin (3 de 3, orden por fin), `pending_payment` (2), combinación con `plan_id` y `member_id`, búsqueda `q` con doble de `members.service.search_ids` y con el real cuando exista, `q` sin coincidencias, nombres completados en lote (contar llamadas: una por service por página), `total` correcto con `offset`; detalle con `paid_cop` ignorando anulados y con congelaciones — 2.5 h
- [ ] T8 · Prueba de rendimiento marcada `@pytest.mark.slow`: 1.000 socios y 3.000 membresías; `GET /memberships?status=expiring` en menos de 500 ms — 0.75 h

### Tests de router
- [ ] T9 · `api/tests/memberships/test_list_router.py`: 200 con forma `{ items, total, limit, offset }`, `limit` 0 y 201 → 422, `status=vigente` → 422 `field = "status"`, rango invertido → 422, detalle 404, 403 `member`, 401 — 1.5 h

### Tests de arquitectura
- [ ] T10 · Confirmar `test_no_cross_models.py` y agregar en `api/tests/architecture/test_no_cross_schema_sql.py` (si US-022 no lo tiene) la verificación de que ningún `select`/`text` de `memberships` nombra tablas de `members.` o `plans.` — 0.25 h

### Front
- [ ] T11 · `web/src/features/memberships/pages/MembershipsPage.tsx` en `/membresias`: `Chips` de estado (Al día, Por vencer, Vencidas, Congeladas, Pendiente de pago con tokens `--warning`, Canceladas), selector de plan, rango "Vence entre", búsqueda, `DataTable` con `StatusTag` con texto, fecha `31 oct 2026` y precio `$ 120.000`, `Pagination`; filtros en la URL; acciones por fila: Renovar (enlace a `/membresias/vender?socio=:id&renovar=1`), Congelar (`FreezeModal`, US-089), Anular (`CancelModal`, US-090, solo admin); estados de carga, vacío ("No hay membresías con estos filtros") y error; comentario `// DESIGN-GAP:` del chip de Q3; hooks `useMemberships(filters)` y `useMembership(id)` en `api.ts` — 4 h
- [ ] T12 · Vitest `MembershipsPage.test.tsx`: filtros se reflejan en la URL, chip de pendiente con texto, Anular oculto para coach, vacío y error — 1 h

### DevOps
- [ ] T13 · Regenerar `docs/openapi.json` y `web/src/core/api/types.ts` — 0.25 h

### Seguridad
- [ ] T14 · Revisar: `q` acotado en longitud y nunca interpolado en SQL; la respuesta no trae campos cifrados ni enmascarados (N-01: las listas nunca muestran datos cifrados); rol en ambas rutas — 0.25 h

## Orden de ejecución
1. T6 (rojo), T1
2. T7 (rojo), T2, T3 (verde)
3. T4, T9 (rojo), T5 (verde)
4. T8, T10, T13
5. T12 (rojo), T11 (verde)
6. T14

## Dependencias técnicas
- US-084 · Vender membresía (tabla, índices, `MembershipOut`).
- US-089 · Congelaciones (detalle y modal de la fila).
- US-090 · Anular (modal de la fila).
- US-019 · Contrato de paginación.
- US-069 / US-070 · `members.service.search_ids(q)` y `members.service.names_for(ids)` (agregados en consolidación; no están escritos en los criterios de EP-07).
- US-078 / US-110 · `plans.service.names_for(ids)`.
- US-095 · `payments.service.sum_not_voided`.
- US-063 · `DataTable`, `Pagination`, `FilterBar`, `Chips` (front).

## Endpoints
- `GET /api/v1/memberships` — roles: admin, coach
- `GET /api/v1/memberships/{id}` — roles: admin, coach

## Riesgos
- `search_ids` puede devolver muchos ids con un `q` corto (por ejemplo "a") — impacto: `ANY(:ids)` grande — mitigación: Members acota `search_ids` (mínimo 2 caracteres o tope de ids) y aquí se documenta el tope; con 1.000 socios el peor caso es aceptable.
- Estado guardado desfasado entre la medianoche y las 07:00 de Bogotá (lo corrige el job de US-094) — mitigación: aceptado; el filtro "Vence entre" usa `end_date`, que no depende del job.
- Front condicionado a D1.

## Estimación
- Backend: 7 h
- Front: 4 h
- Pruebas: 6.5 h
- DevOps / seguridad: 0.5 h
- **Total: 18 h**

Supera el rango de 3 puntos (10 a 15 h) porque la página reúne filtros en URL y las tres acciones por fila; el backend está dentro del rango.

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/memberships/test_rules.py -q`
- [ ] `cd api && uv run pytest tests/memberships/test_list_service.py -q`
- [ ] `cd api && uv run pytest tests/memberships/test_list_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run pytest -m slow tests/memberships/test_list_service.py -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/memberships`
- [ ] `curl "/api/v1/memberships?status=expiring&ends_from=2026-10-26&ends_to=2026-11-01"` devuelve solo membresías con `end_date` en ese rango, ordenadas; `curl /api/v1/memberships/<id>` trae `paid_cop` entero
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.memberships --cov-fail-under=80`
