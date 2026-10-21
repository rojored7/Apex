# US-035 · Prueba de arquitectura de rutas con rol — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-03-seguridad-de-la-plataforma/US-035-prueba-de-rutas-con-rol.md`
- **Épica:** EP-03 · Seguridad de la plataforma
- **Bounded context / módulo:** core/security (`api/src/app/core/security.py`, `api/tests/architecture/`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

La lista blanca, la marca que se busca (`__apex_roles__` de US-034) y el apagado de `/docs` en producción están definidos. DECISIONES N-14 acepta el supuesto de la documentación y N-16 agrega una entrada a la lista blanca. La entrada de la TV (v0.5) ya tiene mecanismo fijado por N-44. No hay contrato abierto.

## Resumen

`core/security.PUBLIC_ROUTES` es un `frozenset[tuple[str, str]]` de pares (método, ruta) y es la única fuente de la lista blanca. `route_has_role_dependency(route)` recorre el árbol de dependencias (`route.dependant`, incluidas las anidadas y las de `include_router`) buscando una función con `__apex_roles__`. `test_every_route_has_role.py` instancia `create_app()` con `ENV=prod`, recorre `app.routes` y falla con una lista de "MÉTODO ruta" si alguna ruta no está protegida ni en la lista blanca. Además, cualquier ruta que no sea `APIRoute` (un `Route` o un `Mount` de Starlette) falla, porque no pasaría por la dependencia. `create_app()` no publica `/docs`, `/redoc` ni `/openapi.json` con `ENV=prod`.

## Correcciones aplicadas por DECISIONES.md

- La lista blanca de la historia trae solo `GET /health` → se agrega `GET /api/v1/health`, porque `/health` se expone en la raíz y también bajo `/api/v1`: corregido por DECISIONES N-16.
- Supuesto "`/docs` y `/openapi.json` deshabilitados en producción" → aceptado; el contrato se publica como `docs/openapi.json` (US-021): corregido por DECISIONES N-14 (aceptado).
- `GET /api/v1/tv/today` "protegida por token de dispositivo desde v0.5" → el token viaja en la cabecera `X-Device-Token`, nunca por query. La prueba exige que, cuando esa ruta exista, tenga la dependencia de token de dispositivo (marca `__apex_device_token__`), así que la lista blanca nunca deja la TV abierta: corregido por DECISIONES N-44 (la dependencia la implementa US-175).

## Validación contra el dominio

- RN-15: nada sin rol salvo login, recuperación y health (más refresh, reset y TV con token de dispositivo, según `04_architecture_decision.md` sección 6 y la lista blanca de la épica). La prueba es la regla convertida en gate.
- Sin aggregates, sin eventos.
- Función pura: `route_has_role_dependency(route: APIRoute) -> bool` y `unprotected_routes(app) -> list[str]`.

## Validación contra la arquitectura

- `PUBLIC_ROUTES` vive en `core/security.py` (criterio 5) y lo leen la prueba, la documentación (US-021 la puede listar en `docs/openapi.json` como `security: []`) y nadie más.
- La comparación es por método y ruta exactos, con la plantilla de FastAPI (`/api/v1/members/{id}`), no por prefijo.
- Las rutas `HEAD` y `OPTIONS` automáticas no son `APIRoute`. El preflight de CORS lo responde el middleware, no una ruta, así que no hace falta lista blanca.
- `ENV` no existe en `Settings` de US-011, que tiene `extra="forbid"`: se agrega `ENV: Literal["dev", "test", "prod"] = "prod"` (cerrado por defecto) y se documenta en `.env.example`.
- Sin tablas, sin bus de criptografía, sin paginación.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `PUBLIC_ROUTES` en `api/src/app/core/security.py`: `("GET", "/health")`, `("GET", "/api/v1/health")`, `("POST", "/api/v1/auth/login")`, `("POST", "/api/v1/auth/refresh")`, `("POST", "/api/v1/auth/forgot")`, `("POST", "/api/v1/auth/reset")`, `("GET", "/api/v1/tv/today")`, con un comentario por entrada que dice por qué es pública — 0,5 h
- [ ] T2 · Funciones puras `route_has_role_dependency(route) -> bool` (recorrido recursivo de `route.dependant.dependencies` buscando `call.__apex_roles__`) y `unprotected_routes(app) -> list[str]` (devuelve "MÉTODO ruta" ordenado; cuenta como fallo cualquier `Route` o `Mount` que no sea de documentación en `ENV=dev`) en `core/security.py` — 1,5 h
- [ ] T3 · En `api/src/app/core/config.py` agregar `ENV: Literal["dev", "test", "prod"] = "prod"`; en `api/src/app/main.py`, `create_app()` pasa `docs_url=None`, `redoc_url=None`, `openapi_url=None` cuando `ENV == "prod"` — 1 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T4 · `api/tests/architecture/test_route_guard_unit.py` con apps sintéticas: ruta con `require_role` en el parámetro → protegida; con `dependencies=[Depends(require_role(...))]` en la ruta → protegida; en el `APIRouter(dependencies=...)` → protegida; anidada dentro de otra dependencia → protegida; sin nada → no protegida; `GET /api/v1/auth/login` sin rol → reportada (criterio 4); `GET /api/v1/tv/today` sin la marca de token de dispositivo → reportada (N-44); `Mount("/x", app=StaticFiles(...))` → reportada — 2 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- [ ] T5 · `api/tests/core/test_docs_disabled.py`: con `ENV=prod`, `GET /docs`, `/redoc` y `/openapi.json` responden 404; con `ENV=dev`, `/openapi.json` responde 200 — 0,5 h

### Tests de arquitectura
- [ ] T6 · `api/tests/architecture/test_every_route_has_role.py`: `create_app()` real con `ENV=prod`, `assert unprotected_routes(app) == []`, con mensaje que lista "MÉTODO ruta" (criterios 1 y 2); otra prueba que verifica que toda entrada de `PUBLIC_ROUTES` que esté registrada lo está con ese mismo método (criterio 3) — 1 h
- [ ] T7 · PR de control documentado en la descripción del PR: rama que agrega `GET /api/v1/prueba` sin rol; CI debe fallar con "GET /api/v1/prueba" en el mensaje — 0,5 h

### Front
- No aplica.

### DevOps
- [ ] T8 · `.env.example` con `ENV=prod` y comentario; `infra/compose.dev.yml` fija `ENV=dev`; la suite de arquitectura corre en el job de pruebas de `.github/workflows/ci.yml` — 0,5 h

### Seguridad
- [ ] T9 · Revisión: no existe forma de marcar una ruta como pública fuera de `PUBLIC_ROUTES` (ningún decorador `@public`); cambiar la lista blanca exige revisión de seguridad en el PR (CODEOWNERS sobre `core/security.py` si el repositorio lo usa) — 0,5 h

## Orden de ejecución
1. T4 (pruebas puras en rojo)
2. T1
3. T2
4. T3
5. T5
6. T6
7. T7
8. T8
9. T9

## Dependencias técnicas
- US-034 · current_user y require_role: la marca `__apex_roles__`.
- US-020 · create_app, migraciones y health: la app que se recorre y las dos rutas de health (N-16).
- US-011 · Configuración desde .env: campo `ENV`.
- US-021 · Exportación de OpenAPI: el contrato se publica como archivo porque `/openapi.json` en vivo se apaga en producción.
- US-175 · Token de dispositivo de la TV (v0.5): define la dependencia con `__apex_device_token__` sobre `X-Device-Token`.

## Endpoints
- Ninguno.

## Riesgos
- Una ruta con la marca de rol pero sin efecto (por ejemplo, `require_role` llamado y no usado en `Depends`) pasa la prueba — mitigación: la marca está en la función que devuelve la fábrica, no en la fábrica; solo cuenta si aparece en el árbol de dependencias.
- `POST /api/v1/auth/logout` exige rol (US-044); si EP-04 decide que debe funcionar con el access vencido, habría que tocar la lista blanca — mitigación: queda fuera de la lista blanca, como dice US-044; cualquier cambio pasa por T9.
- `ENV` con valor por defecto `prod` puede sorprender en desarrollo (no hay `/docs`) — mitigación: `compose.dev.yml` fija `ENV=dev`.

## Estimación
- Backend: 3 h
- Front: 0 h
- Pruebas: 4 h
- DevOps / seguridad: 1 h
- **Total: 8 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_docs_disabled.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] Con `ENV=prod`, `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/docs` devuelve `404`
- [ ] El PR de control (T7) falla en CI con "GET /api/v1/prueba"
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.security --cov-fail-under=80`
