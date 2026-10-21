# US-017 · Envelope único de errores — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-01-nucleo-compartido/US-017-envelope-de-errores.md`
- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context / módulo:** core (`api/src/app/core/errors.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

El contrato `{ "error": { "code", "message", "field"?, "existing_id"? } }` está fijado en `05_service_design.md` sección 4 y en la especificación común. La historia define la jerarquía, los handlers y los casos de borde. No hay supuestos abiertos.

## Resumen

Esta historia entrega:
- en `core/errors.py`, `DomainError` con sus subclases 400, 401, 403, 404, 409 y 422;
- los schemas Pydantic `ErrorBody` y `ErrorResponse`;
- la función pura `validation_field`, que convierte el `loc` de Pydantic en una ruta legible;
- cuatro handlers (dominio, validación, `HTTPException` y excepción genérica);
- `register_error_handlers(app)`;
- la publicación de `ErrorResponse` en OpenAPI para todas las respuestas 4xx y 5xx, en lugar del `HTTPValidationError` de FastAPI.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md. Los códigos que fijan otras decisiones, como `version_conflict` (N-17), `invalid_token` (N-11), `crypto_unavailable` (N-16) y `overlaps_future_membership` (N-25), los agrega cada historia como subclase o como `code` de `DomainError`, sin tocar el envelope.

## Validación contra el dominio

- No define aggregates. Cada módulo define sus errores de dominio en `exceptions.py`, heredando de `DomainError` (regla de módulos 1).
- Función pura: `validation_field(errors: Sequence[Mapping[str, Any]]) -> str | None`. Toma el primer error, quita el prefijo `body`, `query` o `path` y une las partes con `.`; un índice de lista se escribe `items[0]`.
- Sin eventos.

## Validación contra la arquitectura

- `core/errors.py` solo importa FastAPI, Starlette, Pydantic, `logging` y `core/context.py` (`request_id_var`). No importa módulos.
- `exceptions.py` de cada módulo → `core.errors`. Esa dirección está permitida.
- El handler genérico loguea con `logger.exception`, que se envía al formateador con redacción de US-018, junto con el `request_id`. El cuerpo de la respuesta nunca lleva traza, SQL ni valores de la petición.
- Rol: `UnauthorizedError` y `ForbiddenError` son las que usa `require_role` (US-034), con los códigos `unauthorized` y `forbidden`.
- Paginación: el 422 de `limit` y `offset` (US-019) sale por este handler con `field = "limit"`.
- Bus de criptografía y auditoría: no aplican.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Jerarquía de errores en `core/errors.py`:
  - `class DomainError(Exception)` con `code: str`, `message: str`, `field: str | None = None`, `existing_id: UUID | None = None` y `status: int = 400`;
  - subclases con su estado por defecto: `UnauthorizedError` (401, `unauthorized`), `ForbiddenError` (403, `forbidden`), `NotFoundError` (404), `ConflictError` (409) y `ValidationFailed` (422).
  
  — 1 h
- [ ] T2 · Función pura `validation_field(errors) -> str | None`, con estos casos:
  - `("body", "first_payment", "amount_cop")` da `first_payment.amount_cop`;
  - `("query", "limit")` da `limit`;
  - `("body", "items", 0, "amount_cop")` da `items[0].amount_cop`;
  - una lista vacía da `None`.
  
  — 1 h
- [ ] T3 · Handlers:
  - `DomainError`: su `status` y el envelope; omite `field` y `existing_id` si son `None` (`exclude_none`).
  - `RequestValidationError`: 422, `code = "validation_error"`, `field = validation_field(exc.errors())` y el mensaje "El campo {field} no es válido".
  - `StarletteHTTPException`: el status de la excepción y un código estable por status (`not_found`, `method_not_allowed`, `unauthorized`, `forbidden` o `http_error`), con mensaje en español.
  - `Exception`: 500, `code = "internal_error"` y el mensaje "Ocurrió un error inesperado. Intente de nuevo."; loguea `logger.exception` con `request_id_var.get()`.
  
  Todos responden `JSONResponse` con `application/json` (criterio 4) — 1,5 h
- [ ] T4 · `register_error_handlers(app: FastAPI) -> None` y `ERROR_RESPONSES: dict[int | str, dict]`, que asigna a 400, 401, 403, 404, 409, 422 y 500 el modelo `ErrorResponse`. También una función que en `app.openapi()` reemplaza el `HTTPValidationError` por defecto por `ErrorResponse` y la agrega a cada operación (criterio 5) — 1,5 h

### Schemas
- [ ] T5 · `ErrorBody(BaseModel)` con `code: str`, `message: str`, `field: str | None = None` y `existing_id: UUID | None = None`; `ErrorResponse(BaseModel)` con `error: ErrorBody`, y ejemplo en `model_config` — 0,5 h

### Router
- No aplica (el registro en la app real lo hace `create_app()` de US-020).

### Tests unitarios puros
- [ ] T6 · `tests/core/test_errors_field.py`: los casos de `validation_field` de T2, más los parámetros de ruta y de cabecera — 1 h

### Tests de router
- [ ] T7 · `tests/core/test_errors_router.py`, con `httpx.AsyncClient` sobre una app de prueba con rutas que lanzan cada tipo:
  - `ConflictError("member_duplicate", "Ya existe un socio con este documento", field="document", existing_id=...)` da 409 con exactamente ese envelope (criterio 1);
  - un cuerpo con `amount_cop = 12.5` da 422, `validation_error` y `field = "amount_cop"` (criterio 2);
  - un `RuntimeError` con texto SQL en el mensaje da 500 `internal_error`, y el cuerpo no contiene la traza, el SQL ni los valores enviados (criterio 3);
  - una ruta inexistente da 404 con el envelope;
  - todas las respuestas son `application/json` con la raíz `error` (criterio 4);
  - los mensajes están en español (criterio 6).
  
  — 2 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de arquitectura
- [ ] T8 · `api/tests/architecture/test_error_responses_in_openapi.py`: construye `create_app()` (cuando exista US-020; mientras tanto, la app de prueba) y verifica que cada operación del OpenAPI declara `ErrorResponse` en sus respuestas 4xx y 5xx, y que `HTTPValidationError` no aparece en `components.schemas` (criterio 5) — 1 h

### Front
- No aplica (lo consume US-059 en `web/src/core/api/client.ts`).

### DevOps
- No aplica.

### Seguridad
- [ ] T9 · Revisión:
  - el 500 nunca incluye `str(exc)`;
  - el 422 no repite el valor recibido (Pydantic incluye `input` en `errors()`, y no se devuelve);
  - `existing_id` solo se llena en conflictos de unicidad donde el actor ya puede ver ese registro (la regla la aplica cada módulo);
  - el log del 500 pasa por la redacción de US-018.
  
  — 0,5 h

## Orden de ejecución
1. T6 y T7 (en rojo)
2. T5
3. T1
4. T2
5. T3
6. T4
7. T8
8. T9

## Dependencias técnicas
- US-002 · Proyecto api con uv, ruff, mypy y pytest.
- US-016 · Hook de auditoría: crea `core/context.py` con `request_id_var`. Si esta historia va antes, T3 lo lee con un valor por defecto `None` y el archivo se crea aquí con solo esa variable.
- US-018 · Logging JSON: asigna el `request_id` y redacta el log del 500.
- US-020 · create_app: llama a `register_error_handlers` y publica `ERROR_RESPONSES`.

## Endpoints
- Ninguno.

## Riesgos
- FastAPI publica por defecto `HTTPValidationError` en el 422, y el front generaría dos tipos de error distintos — mitigación: reemplazarlo en OpenAPI (T4) y verificarlo en T8.
- Errores lanzados durante el commit, en el teardown de `get_session`, que no pasan por los handlers si el commit corre después de enviar la respuesta — mitigación: US-012 fija el commit antes de la respuesta, y US-020 agrega una prueba de commit fallido que debe responder con el envelope.
- Fuga de valores del usuario en el 422 (Pydantic incluye `input`) — mitigación: el handler solo usa `loc` y un mensaje fijo (T3), cubierto en T7.

## Estimación
- Backend: 5,5 h
- Front: 0 h
- Pruebas: 4 h
- DevOps / seguridad: 0,5 h
- **Total: 10 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_errors_field.py tests/core/test_errors_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `curl -s http://localhost:8000/api/v1/no-existe` devuelve `{"error":{"code":"not_found","message":...}}` con `Content-Type: application/json`
- [ ] `jq '.components.schemas | has("ErrorResponse")' docs/openapi.json` devuelve `true` (tras US-021)
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.errors --cov-fail-under=80`
