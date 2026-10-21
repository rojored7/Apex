# US-070 · Buscar y listar socios — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-07-padron-de-socios/US-070-buscar-y-listar-socios.md`
- **Épica:** EP-07 · Padrón de socios
- **Bounded context / módulo:** Members (`api/src/app/modules/members/`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

La búsqueda por índice ciego, la normalización (N-02), la paginación (US-019) y quién ve a los dados de baja (N-20) están decididos. La corrección de N-01 simplifica la fila de la lista: no lleva ningún dato sensible, ni enmascarado. No queda ningún supuesto abierto que cambie contrato o esquema.

## Resumen

- `GET /api/v1/members` paginado (`limit`/`offset`, máximo 200) con una sola caja `q` que busca a la vez por `document_idx`, `phone_idx`, `email_idx` (igualdad contra el índice ciego del término) y por `ILIKE` sobre nombre y apellido.
- Filtro `status` (`active`, `inactive`, `deleted`) y `sort` (`last_name`, `first_name`, `created_at`, con `-` para descendente).
- La lista nunca descifra: calcula índices del término, no lee blobs.
- Deja los contratos internos `members.service.search_ids(q)` y `members.service.names_for(ids)` que usan US-091 (membresías) y US-110 (tablero).
- Front: `MembersListPage` con `FilterBar`, `DataTable`, `Pagination` y estado en la URL.

## Correcciones aplicadas por DECISIONES.md

- La historia pone en `MemberRow` el teléfono enmascarado y en la tabla las columnas "documento enmascarado" y "teléfono enmascarado" (criterio 7) → la fila de lista no trae ningún campo cifrado ni enmascarado; la tabla muestra nombre, estado del socio y membresía: corregido por DECISIONES N-01.
- El criterio 6 y el supuesto dicen que `status=deleted` es solo para admin y el coach recibe 403 → admin y coach ven a los dados de baja con `status=deleted` (el chip lo pinta US-071): corregido por DECISIONES N-20.
- El criterio 3 asume la normalización "minúsculas, sin espacios ni puntos" → se usa la de N-02 por `data_class` (teléfono: solo dígitos y sin `57`/`+57` inicial; documento: sin espacios, puntos, guiones ni tildes; correo: minúsculas y sin espacios), implementada en `core/crypto` (US-026): corregido por DECISIONES N-02.

## Validación contra el dominio

- Lectura del aggregate `Member`; sin invariantes nuevas ni eventos.
- RN-13: el filtro compara índices ciegos; solo nombre y apellido (en claro por diseño, van al leaderboard) se comparan como texto.
- RN-14: por defecto se excluyen los socios con `deleted_at` no nulo.
- Función pura nueva: `classify_query(q) -> QueryPlan` (decide qué índices tiene sentido calcular). Coincide con el modelo; sin discrepancias.

## Validación contra la arquitectura

- Módulo dueño: `members`; solo `service.py`, `schemas.py` y `router.py`.
- Bus: el término se indexa con `core.crypto.bus.blind_index(data_class, term)` dentro de `bus.batch("index", ...)` para que `crypto_ops` reciba una fila agregada por búsqueda (US-029). La normalización previa usa `core.crypto.normalize_for_index(data_class, value)` (función pura exportada por `core/crypto`, no es primitiva prohibida). Ninguna llamada a `decrypt`.
- Paginación con `PageParams` y `paginate` de US-019; `q` máximo 100 caracteres.
- Rol: `require_role("admin", "coach")`.
- Sin llamadas a otros services en esta historia (`membership_status` va `null` hasta US-071).
- Contratos expuestos a otros módulos devuelven dataclasses, nunca el ORM.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `classify_query(q: str) -> QueryPlan` (dataclass con `name_term`, `document_term`, `phone_term | None`, `email_term | None`): `name_term` siempre (recortado, con `%` y `_` escapados para `ILIKE`); `document_term` si `normalize_for_index("member.document", q)` no queda vacío; `phone_term` solo si el término tiene al menos 7 dígitos; `email_term` solo si contiene `@` — 1.5 h
- [ ] T2 · Caso de uso `async def list(session, filters: MemberListFilters, page: PageParams) -> Page[MemberRowOut]`: arma `UNION` de cuatro subconsultas de ids (una por índice y una por `ILIKE` sobre `first_name || ' ' || last_name`) para que la rama de documento use `uq_members_document_idx_alive`; aplica `status` (`deleted` = `deleted_at IS NOT NULL`; sin filtro = `deleted_at IS NULL`), orden estable (`sort` más `id`) y `paginate`; calcula los índices en un solo `bus.batch("index")` — 4 h
- [ ] T3 · Contratos internos `async def search_ids(session, q: str, include_deleted: bool = False) -> set[UUID]` (misma lógica de T2 sin paginar; lo usa US-091) y `async def names_for(session, ids: Iterable[UUID]) -> dict[UUID, MemberName]` (incluye dados de baja; lo usan US-091 y US-110); una consulta por llamada, sin N+1 — 1.5 h

### Schemas
- [ ] T4 · `MemberRowOut` (`id`, `first_name`, `last_name`, `sex`, `status`, `deleted_at`, `membership_status: str | None`, `plan_name: str | None`), sin ningún campo sensible; `MemberListQuery` con `q: str | None` (máx. 100), `status: Literal["active","inactive","deleted"] | None`, `sort: Literal["last_name","-last_name","first_name","-first_name","created_at","-created_at"] = "last_name"` — 1 h

### Router
- [ ] T5 · `GET /api/v1/members` con `Depends(require_role("admin", "coach"))`, `PageParams`, `response_model=Page[MemberRowOut]`; códigos 200, 401, 403, 422 (`limit`, `offset`, `sort`, `status`, `q`) — 1 h

### Tests unitarios puros
- [ ] T6 · `api/tests/members/test_classify_query.py`: documento con puntos y guiones, teléfono con espacios y `+57`, correo con mayúsculas, texto con tildes, cadena vacía, término con `%` y `_` — 1.5 h

### Tests de service con PostgreSQL
- [ ] T7 · `api/tests/members/test_service_list.py` con 1.000 socios sembrados por factory: encuentra por `"1.020.304"`, por `"300 123 4567"` y `"+57 300 123 4567"`, por correo en mayúsculas, por `"góm"`; excluye dados de baja por defecto y los muestra con `status=deleted`; orden por cada `sort`; ninguna fila nueva en `crypto_ops` con `verb = 'decrypt'` tras listar; `EXPLAIN` de la rama de documento usa `uq_members_document_idx_alive`; `search_ids` y `names_for` — 3.5 h

### Tests de router
- [ ] T8 · `api/tests/members/test_router_list.py`: 200 admin y coach (también con `status=deleted`, N-20), 403 `member`, 401 sin token, 422 para `limit` 0, 201 y -1, `offset` -1, `sort` inválido con `field = "sort"`; ningún `item` contiene las claves `document`, `phone`, `email`, `birth_date` ni `emergency_contact` — 2 h

### Tests de arquitectura
- [ ] T9 · `api/tests/architecture/test_list_rows_without_sensitive_fields.py`: recorre los `response_model` `Page[...]` del módulo `members` y falla si el esquema de fila declara un campo sensible (N-01); sigue en verde la prueba de `PageParams` de US-019 — 1 h

### Front
- [ ] T10 · `web/src/features/members/api.ts`: `useMembers(params)` con clave de consulta derivada de `q`, `status`, `sort`, `limit`, `offset` — 1 h
- [ ] T11 · `web/src/features/members/pages/MembersListPage.tsx`: `PageHeader` con "Nuevo socio" (`useCan("member.create")`), `FilterBar` con búsqueda (debounce 300 ms), `DataTable` (nombre, estado, membresía) y `Pagination` que traduce páginas a `offset`; parámetros en la URL; cambiar la búsqueda reinicia `offset` a 0; estados de carga, vacío ("No hay socios que coincidan con la búsqueda") y error; `// DESIGN-GAP:` paginación `limit`/`offset` (S2) — 4 h
- [ ] T12 · Vitest en `web/src/features/members/pages/MembersListPage.test.tsx` (URL, reinicio de offset, tres estados) y ampliación del E2E `web/tests/e2e/members.spec.ts` con la búsqueda por teléfono — 2 h

### DevOps
- [ ] T13 · Prueba de rendimiento marcada `@pytest.mark.perf` (`api/tests/members/test_list_perf.py`): búsqueda por documento con 1.000 socios en menos de 500 ms, corrida en CI; `docs/openapi.json` regenerado — 1 h

### Seguridad
- [ ] T14 · El término `q` puede ser un documento o un teléfono: el filtro de logs del API redacta el parámetro `q` en las líneas de acceso de Uvicorn y `infra/nginx/default.conf` usa un `log_format` sin query string para `/api/v1/members`; revisar el escape de `ILIKE` (sin inyección de comodines) — 1 h

## Orden de ejecución

1. T6 (en rojo) y T1.
2. T4.
3. T7 (en rojo), T2 y T3.
4. T5, luego T8 y T9.
5. T13 y T14.
6. T10, T11 y T12.

## Dependencias técnicas

- US-069 · Registrar socio: tabla, índices e índice único parcial.
- US-019 · Contrato de paginación: `PageParams`, `Page[T]`, `paginate`.
- US-026 · Índice ciego HMAC: `normalize_for_index` por `data_class` (N-02).
- US-029 · Bitácora crypto_ops por lote: `bus.batch("index")`.
- US-034 · Dependencias current_user y require_role.
- US-063 · Tabla, paginación, filtros y chips (front).

## Endpoints

- `GET /api/v1/members` — roles: admin, coach

## Riesgos

- El documento o el teléfono viajan en la query string y pueden quedar en logs de acceso: exposición de datos personales en claro — mitigación: T14 (redacción en Uvicorn y Nginx) y prueba de captura de logs.
- Un `OR` con `ILIKE` haría que PostgreSQL ignore el índice de `document_idx`: el criterio de `EXPLAIN` fallaría — mitigación: `UNION` de subconsultas por rama (T2).
- El `ILIKE` sin índice recorre la tabla: con 1.000 socios es despreciable — mitigación: T13 vigila los 500 ms; si un día falla, se agrega `pg_trgm` con una migración nueva a partir de `0014_` (no se crea ahora).
- Front condicionado a D1: si el gate no aprueba el front en `web/`, T10 a T12 salen de este repositorio — mitigación: contrato en `docs/openapi.json`.

## Estimación

- Backend: 9 h
- Front: 7 h
- Pruebas: 8 h
- DevOps / seguridad: 2 h
- **Total: 26 h**

Está en el borde alto de 5 puntos por la prueba de rendimiento y la redacción de logs del término de búsqueda.

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/members/test_classify_query.py -q`
- [ ] `cd api && uv run pytest tests/members/test_service_list.py -q`
- [ ] `cd api && uv run pytest tests/members/test_router_list.py -q`
- [ ] `cd api && uv run pytest tests/members/test_list_perf.py -q -m perf`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/members`
- [ ] `curl "/api/v1/members?q=1.020.304"` encuentra al socio guardado como `1020304` y la respuesta no contiene la clave `document`.
- [ ] `psql -c "SELECT count(*) FROM crypto.crypto_ops WHERE verb='decrypt' AND at > now() - interval '1 minute'"` sigue en 0 después de listar.
- [ ] El log de acceso de la petición anterior no contiene `1.020.304`.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.members --cov-fail-under=80`
