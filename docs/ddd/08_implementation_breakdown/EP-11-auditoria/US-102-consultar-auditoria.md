# US-102 · Consultar auditoría — desglose técnico

> **Corregido en S4A-W0-1** (`docs/ddd/blueprints/sprint-04a-plan.md`, sección 1 y enmiendas E1 a E10; registro en `docs/ddd/DECISIONES.md`, "Sprint 4A"). Donde el texto de abajo choque con estas notas, mandan las notas:
> - Filtros reales de `GET /audit`: `from`, `to`, `user_id`, `table`, `record_id`, `subject_member_id`, `action`, `q`, `limit` y `offset`; `AuditRow` suma `subject_member_id`; `ROUTES.md:89` se corrige a este contrato (S4A-D16).
> - `table` se compara con el `table_name` real `esquema.tabla` (`members.members`, `memberships.memberships`, `memberships.membership_freezes`, `payments.payments`, `plans.plans`, `auth.users`, `settings.settings_sections`, `audit.verifications`) con patrón `^[a-z_]{1,63}\.[a-z_]{1,63}$` y `max_length=127` (S4A-D16, S4A-D46).
> - `q` por correo parcial se resuelve con la función nueva `auth.service.search_user_ids(session, term, *, local_part_only=False, limit=200) -> set[UUID]`, no con un `ids_by_email(q)` parcial (`ids_by_email` exacta no cambia: la usa `resolve_actor`); buscar por nombre de socio no entra (`// DESIGN-GAP:` en F1) (S4A-D16, S4A-D41).
> - El correo y el nombre de quien actuó salen de `auth.service.user_refs_for(session, user_ids) -> dict[UUID, UserRef]` con `UserRef(id, email, display_name)`, no de `names_for -> UserRef`; `names_for` no cambia; solo `audit` importa `user_refs_for` (prueba AST `test_user_refs_scope.py`) (S4A-D19, S4A-D54).
> - `GET /audit` consume la cubeta `staff-read` (120/min, `USER_READ_LIMIT_PER_MIN`), declara 429 y entra en `CON_LIMITE` (S4A-D45).
> - `from` y `to` acotados entre `2020-01-01T00:00Z` y `now + 1 día`, con `from < to` y 422 con `field`; la regla vive en `core/validators.py` como `check_instant_range` (S4A-D46, S4A-D66).
> - `MAX_AUDIT_OFFSET = 100_000`: un `offset` mayor da 422 con `field="offset"` (S4A-D45).
> - La consulta vive en `audit/queries.py` (privado; `PRIVATE_HELPERS["audit"]`); no hay migración `0014_audit_indexes` (los índices ya existen) (S4A-D16, S4A-D18).
> - La lectura de la auditoría no se audita: el log de acceso del api (ruta y estado, sin parámetros) es el único rastro (S4A-D61).
> - La prueba de rendimiento se marca `perf`, no `slow`: `uv run pytest -m perf tests/audit/test_list_performance.py -q`, fuera del gate (S4A-D41, S4A-D68).

- **Historia:** `docs/ddd/07_user_stories/EP-11-auditoria/US-102-consultar-auditoria.md`
- **Épica:** EP-11 · Auditoría y trazabilidad
- **Bounded context / módulo:** Audit (`api/src/app/modules/audit/`; modelo `AuditEntry` en `api/src/app/core/audit.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

Filtros, paginación, orden, rol (solo admin) y la exclusión de `before`/`after` en la lista están definidos. Los índices que pide el rendimiento ya vienen en `0002_audit_log`. La acción `download` se agrega a los valores aceptados por DECISIONES N-08. El único contrato externo que se necesita (correo del usuario y búsqueda por correo en `auth.service`) es una lectura por lote.

## Resumen

Implementa `audit.service.list(...)` sobre `audit.audit_log` con filtros de rango sobre `at`, `user_id`, `table`, `record_id`, `action` y `q` (record_id exacto o correo del usuario), orden `seq` descendente y paginación común, y el endpoint `GET /audit` solo para admin. En el front, la pantalla `Auditoria` en `/sistema/auditoria` con `FilterBar`, `DataTable` y `Pagination`, sin el ítem de menú para el coach. El detalle es de US-103 y la verificación de US-104.

## Correcciones aplicadas por DECISIONES.md

- La historia lista las acciones `insert`, `update`, `delete`, `reveal`, `export`, `login`, `verify` → se agrega `download` a los valores aceptados del filtro `action` y del enum de salida: corregido por DECISIONES N-08 (el `CHECK` de `0002_audit_log` ya la incluye).
- Las entradas del worker, de la CLI y de la importación tienen `user_id = SYSTEM_USER_ID` (o el usuario de `--as`) y se muestran como "Sistema": corregido por DECISIONES N-15 (la historia no lo trata).
- La nota técnica de la historia pide una migración de índices "si US-015 no los creó" → no aplica: `0002_audit_log` ya crea `at`, `(table_name, record_id)`, `user_id` y `(table_name, seq DESC)` según la numeración canónica.

## Validación contra el dominio

- Lectura del aggregate `AuditEntry` (append-only, RN-16). Esta historia nunca escribe.
- RN-13: la lista no incluye `before` ni `after`, así que no hay riesgo de exponer blobs; el detalle (US-103) los muestra como blob.
- RN-15: solo admin.
- Eventos: ninguno. Funciones puras: `build_audit_filters(...)` (nueva, para probar los filtros sin base).

## Validación contra la arquitectura

- Módulo dueño: `modules/audit` (router, schemas, service; sin `models.py`, el modelo vive en `core/audit.py` según `05_service_design.md`). Leer `core.audit.AuditEntry` desde `modules/audit` es leer `core`, no models de otro módulo.
- `audit.service.list` llama a `auth.service` para dos lecturas por lote: `ids_by_email(q)` (solo si `q` no es un UUID) y `names_for(user_ids)` con correo y nombre. Es una composición de lectura de dos módulos (audit y auth), sin escritura. `core/audit.py` sigue sin depender de nadie; la dependencia es de `modules/audit`.
- Contratos de Auth que se piden: `auth.service.names_for(user_ids) -> dict[UUID, UserRef(email, display_name)]` (US-110 lo define con nombre; aquí se necesita también el correo) y `auth.service.ids_by_email(q) -> list[UUID]` (coincidencia parcial sin distinguir mayúsculas). Se informan como contratos entre épicas.
- Rol `require_role("admin")`. Paginación común de US-019. Sin bus de criptografía.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (índices en `0002_audit_log`).

### Models
- No aplica (`AuditEntry` es de US-015 en `core/audit.py`).

### Service
- [ ] T1 · `modules/audit/service.py`: dataclass `AuditFilters(from_, to, user_id, table, record_id, action, q)`, constante `AUDIT_ACTIONS = ("insert","update","delete","reveal","export","download","login","verify")` importada de `core/audit.py` (fuente única con el `CHECK`), función pura `build_audit_filters(filters, user_ids_from_q) -> list[ColumnElement[bool]]` (`q` UUID → `record_id = q`; si no, `user_id = ANY(:ids)`) — 2 h
- [ ] T2 · `async def list(session, filters: AuditFilters, page: PageParams) -> Page[AuditRow]`: consulta `SELECT seq, at, user_id, action, table_name, record_id ... ORDER BY seq DESC LIMIT/OFFSET` (sin cargar `before`/`after`, con `load_only`), `count(*)` con los mismos filtros, enriquecimiento por lote con `auth.service.names_for`; `SYSTEM_USER_ID` se muestra como "Sistema" — 3 h

### Schemas
- [ ] T3 · `modules/audit/schemas.py`: `AuditListQuery` (alias `from` → `from_`, `AwareDatetime`, `table` con patrón `^[a-z_]{1,63}\.[a-z_]{1,63}$`, `record_id: UUID | None`, `action: Literal[...] | None`, `q: str | None` máx. 254) y `AuditRow { seq: int, at, user_id, user_email, user_name, action, table_name, record_id }` — 1 h

### Router
- [ ] T4 · `modules/audit/router.py`: `GET /audit` con `Depends(require_role("admin"))`; registro del router en `main.py`; códigos 200, 401, 403, 422 — 0,5 h

### Tests unitarios puros
- [ ] T5 · `api/tests/audit/test_filters.py`: `build_audit_filters` con cada filtro, `q` como UUID y como correo, rango `[from, to)`, acción fuera de la lista rechazada por el schema — 1 h

### Tests de service con PostgreSQL
- [ ] T6 · `api/tests/audit/test_list.py`: cada filtro; orden `seq` descendente; paginación y `total`; `q` por record_id y por correo parcial; filas sin `before`/`after`; la consulta no modifica `audit.audit_log` (conteo y hash de la última fila iguales antes y después) — 3 h
- [ ] T7 · `api/tests/audit/test_list_coverage_v01.py`: prueba de integración que crea una fila en `members`, `plans`, `memberships`, `payments`, `users` y `settings_sections` por sus services y encuentra cada `insert` con usuario y fecha en `audit.service.list` — 2 h
- [ ] T8 · `api/tests/audit/test_list_performance.py` (marca `perf`): 100.000 filas insertadas con `COPY` en la base de prueba (con el trigger append-only intacto: solo `INSERT`), `limit=25`, menos de 500 ms con y sin filtros de tabla y usuario (reutiliza la fábrica de cadena de 100.000 filas de US-104) — 1 h

### Tests de router
- [ ] T9 · `api/tests/audit/test_router_list.py`: 200 admin, 403 coach, 403 member, 401 sin token, 422 `field="action"` con `borrar`, 422 `limit=201` — 1 h

### Tests de arquitectura
- [ ] T10 · `test_every_route_has_role.py` cubre `GET /audit` con rol admin; `test_no_cross_models.py` verifica que `modules/audit` no importa `auth.models` — 0,5 h

### Front
- [ ] T11 · `web/src/features/system/api.ts`: `useAudit(filters)`; `web/src/features/system/schemas.ts`: Zod de filtros en la URL (el filtro de pantalla "entidad" se mapea uno a uno a `table`) — 1 h
- [ ] T12 · `web/src/features/system/pages/AuditPage.tsx`: `FilterBar` (rango de fechas de Bogotá a UTC, usuario, entidad, acción, búsqueda), `DataTable` (fecha y hora de Bogotá, usuario, acción, entidad, registro, `seq`), carga, vacío y error, `Pagination` por `offset`; punto de montaje del detalle (US-103) y del botón de verificación (US-104); ruta `/sistema/auditoria` protegida con la guarda de admin y el ítem de menú oculto para coach (US-053) — 3 h
- [ ] T13 · `web/src/features/system/pages/AuditPage.test.tsx`: filtros en la URL, paginación, coach no ve el ítem de menú — 1 h

### DevOps
- [ ] T14 · Regenerar `docs/openapi.json` y tipos del front; marca `perf` en CI — 0,5 h

### Seguridad
- [ ] T15 · Revisión: solo admin, sin `before`/`after` en la lista, `q` parametrizado, los correos de usuarios solo se exponen al admin — 0,5 h

## Orden de ejecución
1. T5 (pura en rojo)
2. T1
3. T6, T7 (service en rojo)
4. T2
5. T3
6. T9 (router en rojo)
7. T4
8. T8
9. T10
10. T11, T12, T13
11. T14
12. T15

## Dependencias técnicas
- US-015 · Tabla de auditoría y cadena de hashes: `AuditEntry`, índices de `0002_audit_log`, `AUDIT_ACTIONS`.
- US-016 · Hook de auditoría after_flush: las filas existen.
- US-034 · `current_user` y `require_role`.
- US-019 · Contrato de paginación.
- US-041 / US-110 · `auth.service.names_for` con correo y `auth.service.ids_by_email`.
- US-063 · Tabla, paginación, filtros y chips; US-053 · Guardas de ruta por rol (front).

## Endpoints
- `GET /api/v1/audit` — roles: admin

## Riesgos
- `names_for` de US-110 podría devolver solo el nombre — mitigación: se pide `UserRef(email, display_name)`; si EP-04 no lo acepta, se agrega `auth.service.emails_for` con el mismo patrón.
- `count(*)` sobre 100.000 filas con filtros poco selectivos puede pasar de 500 ms — mitigación: la prueba T8 lo mide; si falla, `total` se calcula con `count(*)` solo cuando hay filtros y con `max(seq)` cuando no los hay (la cadena no tiene huecos por N-30).
- Front condicionado a D1.

## Estimación
- Backend: 6,5 h (T1 a T4)
- Front: 4 h (T11, T12)
- Pruebas: 9,5 h (T5 a T10 y T13)
- DevOps / seguridad: 1 h (T14, T15)
- **Total: 21 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/audit/test_filters.py -q`
- [ ] `cd api && uv run pytest tests/audit/test_list.py tests/audit/test_list_coverage_v01.py -q`
- [ ] `cd api && uv run pytest tests/audit/test_list_performance.py -q`
- [ ] `cd api && uv run pytest tests/audit/test_router_list.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/system/pages/AuditPage.test.tsx`
- [ ] `curl "/api/v1/audit?table=payments.payments&action=update"` con token de admin devuelve solo esas filas y con token de coach devuelve 403; `curl "/api/v1/audit?action=download"` devuelve 200
- [ ] `EXPLAIN ANALYZE` con 100.000 filas y `limit=25` tarda menos de 500 ms
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.audit --cov-fail-under=80`
