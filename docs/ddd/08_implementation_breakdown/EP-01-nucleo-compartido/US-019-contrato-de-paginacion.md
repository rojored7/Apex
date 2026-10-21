# US-019 · Contrato común de listas con `limit` y `offset` — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-01-nucleo-compartido/US-019-contrato-de-paginacion.md`
- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context / módulo:** core (`api/src/app/core/pagination.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

El contrato (`limit` de 1 a 200, 25 por defecto, `offset` mayor o igual a 0, respuesta `{items, total, limit, offset}`) está fijado por la regla de datos 6, D2/S2 y la especificación común. El supuesto de ubicar el helper en un archivo nuevo, `core/pagination.py`, se acepta: es un archivo de `core/` sin dependencias de módulos.

## Resumen

Esta historia entrega:
- en `core/pagination.py`, la dependencia `PageParams`, el genérico `Page[T]` y el tipo común `SearchQuery` (`q` de hasta 100 caracteres);
- el helper `paginate(session, stmt, params)`, que cuenta sobre la subconsulta y aplica `limit` y `offset` con orden estable, agregando siempre la clave primaria como desempate;
- una prueba de arquitectura que exige `PageParams` en toda ruta `GET` que responde `Page[...]`.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md (D2/S2, que sigue pendiente del gate y se trata como supuesto aceptado).

## Validación contra el dominio

- No define aggregates. La regla de datos 6 (toda lista pagina, con un máximo de 200, y acepta búsqueda) aplica a todas las listas de los módulos.
- Sin funciones puras de negocio. `paginate` se prueba con base real.
- Sin eventos.

## Validación contra la arquitectura

- `core/pagination.py` importa SQLAlchemy, FastAPI y Pydantic. No importa ningún módulo.
- Cada `service.py` de módulo construye su `select` sobre sus propios `models` y llama a `paginate`. Nunca pagina `models` de otro módulo (regla de módulos 2).
- El 422 de `limit`, `offset` y `q` sale con el envelope de US-017 (`field = "limit"`).
- El rol lo declara cada router. Bus de criptografía y auditoría: no aplican.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `DEFAULT_LIMIT: Final = 25` y `MAX_LIMIT: Final = 200`, y la dependencia `PageParams` como `@dataclass(frozen=True)` con `limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)` y `offset: int = Query(0, ge=0)`. Se usa con `Annotated[PageParams, Depends()]` — 1 h
- [ ] T2 · `async def paginate(session: AsyncSession, stmt: Select[tuple[T]], params: PageParams) -> tuple[list[T], int]`:
  - `total = await session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))`;
  - si el `select` no trae `ORDER BY`, ordena por la clave primaria de la primera entidad;
  - si lo trae, agrega siempre la clave primaria como último criterio, para que filas con la misma clave de orden no se repitan ni se omitan entre páginas (criterio 4);
  - aplica `.limit(params.limit).offset(params.offset)`.
  
  También `to_page(items, total, params) -> Page[T]` — 2 h

### Schemas
- [ ] T3 · `class Page(BaseModel, Generic[T])` con `items: list[T]`, `total: int`, `limit: int` y `offset: int`, con `extra="forbid"` (criterio 3), y `SearchQuery = Annotated[str | None, Query(max_length=100, description="Búsqueda libre; nunca se registra en logs")]` (criterio 6) — 1 h

### Router
- No aplica (cada módulo usa `PageParams` en sus listas).

### Tests unitarios puros
- No aplica.

### Tests de service con PostgreSQL
- [ ] T4 · `tests/core/test_pagination_db.py`, con un modelo de prueba de 30 filas, varias con la misma clave de orden:
  - sin parámetros da 25 items, `total = 30`, `limit = 25` y `offset = 0` (criterio 1, BDD 1);
  - las páginas `0..25` y `25..50` cubren las 30 filas sin repetidos aunque el orden empate (criterio 4, BDD 3);
  - `total` respeta el filtro y no depende de la página (criterio 3);
  - un `select` sin `ORDER BY` queda ordenado por id.
  
  — 2 h

### Tests de router
- [ ] T5 · `tests/core/test_pagination_router.py`, con una ruta de prueba `GET /items` que responde `Page[ItemOut]`:
  - `limit=0`, `limit=201` y `limit=500` dan 422 con `field = "limit"`;
  - `offset=-1` da 422 con `field = "offset"` (criterio 2, BDD 2);
  - `q` de 101 caracteres da 422 con `field = "q"` (criterio 6);
  - la respuesta tiene exactamente las cuatro claves.
  
  — 1,5 h

### Tests de arquitectura
- [ ] T6 · `api/tests/architecture/test_list_routes_use_page_params.py`: recorre `create_app().routes`; para cada `APIRoute` con `GET` cuyo `response_model` tenga origen `Page`, verifica que `PageParams` está entre las dependencias de `route.dependant`. Falla nombrando la ruta (criterio 5). Incluye el ajuste cuando US-020 registre los routers reales — 2 h

### Front
- No aplica (lo consume US-063, componente `Pagination`).

### DevOps
- No aplica.

### Seguridad
- [ ] T7 · Revisión:
  - el tope de 200 evita respuestas masivas;
  - `q` no se registra en el log de acceso (US-018);
  - `paginate` nunca recibe SQL armado con texto del usuario, solo `select` de SQLAlchemy con parámetros ligados.
  
  — 0,5 h

## Orden de ejecución
1. T4 y T5 (en rojo)
2. T1
3. T3
4. T2
5. T6
6. T7

## Dependencias técnicas
- US-017 · Envelope de errores: formato del 422 con `field`.
- US-012 · Base de datos: sesión y fixture para T4.
- US-020 · create_app: T6 recorre las rutas registradas en la app real.

## Endpoints
- Ninguno.

## Riesgos
- `count(*)` sobre una subconsulta con JOIN o DISTINCT puede contar de más si un service une tablas de forma incorrecta — mitigación: cada service pagina sobre su propia tabla (sin JOIN cruzado entre esquemas), y T4 cubre el conteo con filtro.
- Orden inestable con claves repetidas (por ejemplo `last_name`) — mitigación: la clave primaria se agrega siempre como desempate (T2).
- Una ruta de lista que no responde `Page[...]` se escapa de la prueba de arquitectura — mitigación: en la revisión de PR se exige `response_model=Page[...]` en toda lista. La regla queda en el docstring de `core/pagination.py`.

## Estimación
- Backend: 4 h
- Front: 0 h
- Pruebas: 5,5 h
- DevOps / seguridad: 0,5 h
- **Total: 10 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_pagination_db.py tests/core/test_pagination_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `curl -s "http://localhost:8000/api/v1/<lista>?limit=500"` responde 422 con `"field":"limit"` (en la primera lista real, por ejemplo `/members`)
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.pagination --cov-fail-under=80`
