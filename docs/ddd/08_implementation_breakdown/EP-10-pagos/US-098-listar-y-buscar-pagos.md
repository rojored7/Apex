# US-098 · Listar y buscar pagos — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-10-pagos/US-098-listar-y-buscar-pagos.md`
- **Épica:** EP-10 · Registro inmutable de pagos
- **Bounded context / módulo:** Payments (`api/src/app/modules/payments/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

El contrato de lista, filtros, orden y roles está cerrado. La duda arquitectónica (enriquecer cada fila con nombre de socio, plan y usuario sin joins entre esquemas y sin encadenar tres services en un endpoint) se resuelve aquí como composición de lectura acotada, con la decisión documentada en "Validación contra la arquitectura" y protegida por una prueba de arquitectura. No cambia el alcance ni el contrato de la historia.

## Resumen

Implementa `payments.service.list(...)` con filtros de rango de `paid_at`, medio, `registered_by`, anulado, socio, membresía y búsqueda `q`, paginado `limit`/`offset` y orden `paid_at` descendente, y el endpoint `GET /payments` (admin y coach). Cada página se enriquece con tres lecturas por lote (una por servicio vecino), nunca por fila. En el front, la pantalla `Pagos` con `FilterBar`, `DataTable` y `Pagination`, con los filtros en la URL.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md.
- Ajuste de implementación (no de alcance): el filtro `member_id` se resuelve con la columna `payments.member_id` que agrega US-095 a `0010_payments`, en lugar de pedir a `memberships.service` los ids de membresía del socio. El supuesto de la historia ("nombres por `memberships.service` y `members.service`/`plans.service` desde `payments.service`, en una sola llamada por página") se conserva y se precisa abajo.

## Validación contra el dominio

- Lectura sobre el aggregate `Payment`; no hay invariantes nuevas.
- RN-01: montos enteros. Regla de datos 6: paginación con máximo 200 y búsqueda. Fechas en UTC en el API; el front convierte el día de Bogotá a UTC para `from` y `to`.
- `q`: coincidencia exacta de `reference` sin distinguir mayúsculas (`lower(reference) = lower(:q)`) o nombre o apellido parcial del socio, resuelto por `members.service.search_ids(q)` (contrato de US-069/US-070; nombre y apellido van en claro, así que no se descifra nada).
- Eventos: ninguno.

## Validación contra la arquitectura

- Módulo dueño: `payments`. El router llama a un solo service (`payments.service.list`).
- Decisión sobre la composición (pedida en la revisión de la épica): no es brecha. Razones:
  - La regla "no se encadenan services de tres módulos en un endpoint" (`CLAUDE.md`, regla de módulos 3; `03_context_map.md` sección 5) protege las acciones que interesan a varios módulos, que deben ir por eventos. Aquí no hay escritura ni evento; son lecturas de enriquecimiento.
  - El router no orquesta: llama a `payments.service.list`, que hace lecturas por lote a sus vecinos y devuelve filas listas.
  - Cada salto sigue una relación del mapa o un contrato de lectura ya publicado: `memberships.service.refs_for(membership_ids)` (Payments → Memberships, Customer/Supplier), `members.service.search_ids(q)` (contrato publicado en US-069/US-070, el mismo que usan US-091 y US-110), `auth.service.names_for(user_ids)` (contrato publicado en US-110).
  - Límites: como máximo tres llamadas por página, cada una por lote (nunca N+1), sin transacción de escritura, y `search_ids` solo cuando hay `q`.
  - Se pide al orquestador anotar en `03_context_map.md` las dos aristas de lectura Payments → Members (`search_ids`) y Payments → Auth (`names_for`).
- Sin imports de `models` ajenos; la prueba de arquitectura fija la lista de services que `payments` puede importar.
- `memberships.service.refs_for(ids) -> dict[UUID, MembershipRef(member_id, member_first_name, member_last_name, plan_name)]` es un contrato nuevo de Memberships: Memberships ya compone nombre de socio y de plan para su propia lista (US-091) con `members.service.names_for` y `plans.service`. Se informa como contrato entre épicas.
- Rol: `require_role("admin", "coach")`. Paginación con el contrato común de US-019 (`limit` 1 a 200, por defecto 25, `offset` ≥ 0, `{items, total, limit, offset}`).
- Ningún dato cifrado del socio en la respuesta (solo `member_id`, `first_name`, `last_name`).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (índices `paid_at DESC`, `membership_id` y `(member_id, paid_at DESC)` ya están en `0010_payments`; si la prueba de rendimiento lo exige, índice `registered_by` en `0014_payments_registered_by_idx` con migración propia).

### Models
- No aplica.

### Service
- [ ] T1 · `payments/service.py`: dataclass `PaymentFilters(q, from_, to, method, registered_by, voided, member_id, membership_id)` y función pura `build_filters(filters, member_ids_from_q) -> list[ColumnElement[bool]]` (rango `[from, to)`, `voided` tri-estado, `q` como `lower(reference) = lower(q) OR member_id = ANY(:ids)`) — 2 h
- [ ] T2 · Caso de uso `async def list(session, filters: PaymentFilters, page: PageParams) -> Page[PaymentRow]`: si hay `q`, `member_ids = await members_service.search_ids(session, q)`; consulta `SELECT ... ORDER BY paid_at DESC, id DESC LIMIT :limit OFFSET :offset` y `SELECT count(*)` con los mismos filtros; enriquecimiento por lote con `memberships_service.refs_for(session, {membership_id})` y `auth_service.names_for(session, {registered_by})`; arma `PaymentRow` — 3 h

### Schemas
- [ ] T3 · `PaymentListQuery` (con alias `from` → `from_`, `AwareDatetime`, `method: Literal[...] | None`, `voided: bool | None`, UUIDs) y `PaymentRow { id, paid_at, amount_cop, method, reference, voided, void_reason, registered_by, registered_by_name, membership_id, member_id, member_first_name, member_last_name, plan_name }`; `Page[PaymentRow]` del contrato común — 1 h

### Router
- [ ] T4 · `GET /payments` en `payments/router.py` con `Depends(require_role("admin", "coach"))` y `PageParams` común; registrado antes de `GET /payments/{id}`; códigos 200, 401, 403, 422 — 0,5 h

### Tests unitarios puros
- [ ] T5 · `api/tests/payments/test_list_filters.py`: `build_filters` con cada filtro aislado, `voided` en `true`, `false` y ausente, `q` sin coincidencias de socio, rango que excluye `to` — 1 h

### Tests de service con PostgreSQL
- [ ] T6 · `api/tests/payments/test_list.py` con 40 pagos de octubre (3 anulados): primera página de 25 en orden descendente y `total = 40`; cada filtro; `q` por referencia en minúsculas; `q` por apellido parcial; `member_id` y `membership_id`; sin `before`/`after` ni datos cifrados en la fila; nombres resueltos (los services vecinos se usan reales, no dobles) — 3 h
- [ ] T7 · `api/tests/payments/test_list_performance.py` (marca `slow`): 10.000 pagos de prueba, `limit=25`, menos de 500 ms medidos en el service; si falla, se agrega el índice de `registered_by` — 1 h

### Tests de router
- [ ] T8 · `api/tests/payments/test_router_list.py`: 200 admin y coach; 403 member; 401 sin token; 422 `field="limit"` para 0 y 201, `offset=-1`, `method="tarjeta"`; montos enteros en JSON — 1 h

### Tests de arquitectura
- [ ] T9 · `api/tests/architecture/test_payments_dependencies.py`: los únicos módulos de negocio que `app.modules.payments` importa son `memberships.service`, `members.service` y `auth.service` (lista blanca), y nunca sus `models` — 0,5 h

### Front
- [ ] T10 · `web/src/features/payments/api.ts`: `usePayments(filters)` con la clave de consulta derivada de los filtros; `web/src/features/payments/schemas.ts`: Zod de los filtros de la URL (`useSearchParams`) — 1 h
- [ ] T11 · `web/src/features/payments/pages/PaymentsPage.tsx`: `PageHeader` con "Registrar pago" (US-095), `FilterBar` (rango de fechas de Bogotá convertido a UTC con `web/src/core/i18n/format.ts`, medio, registrado por, incluir anulados, búsqueda), `DataTable` (fecha y hora de Bogotá, socio, plan, monto `$ 120.000`, medio, referencia, registrado por, `StatusTag` "Anulado" con texto), estados de carga, vacío "No hay pagos con estos filtros" y error, `Pagination` que traduce página a `offset`; ruta `/pagos` en `routes.tsx` — 3 h
- [ ] T12 · `web/src/features/payments/pages/PaymentsPage.test.tsx`: filtros en la URL, paginación, etiqueta "Anulado", estado vacío — 1,5 h

### DevOps
- [ ] T13 · Regenerar `docs/openapi.json` y tipos del front; agregar la marca `slow` de T7 a la configuración de pytest y al job de CI — 1 h

### Seguridad
- [ ] T14 · Revisión: rol en el endpoint, `q` parametrizado (sin interpolar en SQL), ningún campo cifrado en la respuesta, `limit` acotado — 0,5 h

## Orden de ejecución
1. T5 (pura en rojo)
2. T1
3. T6 (service en rojo)
4. T2
5. T3
6. T8 (router en rojo)
7. T4
8. T7
9. T9
10. T10, T11, T12
11. T13
12. T14

## Dependencias técnicas
- US-095 · Registrar pago: tabla con `member_id` e índices.
- US-019 · Contrato de paginación (`PageParams`, `Page[T]`).
- US-069 / US-070 · `members.service.search_ids(q)`.
- US-091 · Listar membresías: debe exponer `memberships.service.refs_for(membership_ids)` (contrato nuevo que esta historia pide).
- US-110 / US-041 · `auth.service.names_for(user_ids)`.
- US-063 · Tabla, paginación, filtros y chips (front).

## Endpoints
- `GET /api/v1/payments` — roles: admin, coach

## Riesgos
- `memberships.service.refs_for` no está en la historia de Memberships: si EP-09 no lo expone, la lista no tiene plan ni nombre — mitigación: se informa como contrato entre épicas; mientras tanto se prueba con la función real agregada en la misma iteración.
- `search_ids` con un `q` muy corto devuelve muchos socios (hasta 1.000) — mitigación: `= ANY(:ids)` sobre el índice `(member_id, paid_at)`; aceptable con el volumen del gimnasio.
- El orquestador podría leer la regla de tres services de forma estricta — mitigación: la decisión está razonada arriba y aislada en `payments.service`; si se rechaza, la alternativa es un módulo de lectura (como `dashboard`) sin cambiar el contrato HTTP.
- Front condicionado a D1.

## Estimación
- Backend: 6,5 h (T1 a T4)
- Front: 4 h (T10, T11)
- Pruebas: 8 h (T5 a T9 y T12)
- DevOps / seguridad: 1,5 h (T13, T14)
- **Total: 20 h**
- Desvío sobre la referencia de 3 puntos (10 a 15 h): la prueba de rendimiento, la composición por lote con tres vecinos y una pantalla de lista completa suben la suma; se mantiene el valor calculado.

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/payments/test_list_filters.py -q`
- [ ] `cd api && uv run pytest tests/payments/test_list.py -q`
- [ ] `cd api && uv run pytest tests/payments/test_list_performance.py -q`
- [ ] `cd api && uv run pytest tests/payments/test_router_list.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/payments/pages/PaymentsPage.test.tsx`
- [ ] `curl "/api/v1/payments?limit=201"` devuelve 422 con `field = "limit"`; `curl "/api/v1/payments?q=nq-778812"` devuelve el pago con referencia `NQ-778812`
- [ ] `EXPLAIN ANALYZE` de la consulta con 10.000 pagos usa `ix_payments_paid_at` y tarda menos de 500 ms
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.payments --cov-fail-under=80`
