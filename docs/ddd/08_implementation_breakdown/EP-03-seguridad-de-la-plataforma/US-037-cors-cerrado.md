# US-037 · CORS cerrado a CORS_ORIGINS — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-03-seguridad-de-la-plataforma/US-037-cors-cerrado.md`
- **Épica:** EP-03 · Seguridad de la plataforma
- **Bounded context / módulo:** core (`api/src/app/main.py`, `api/src/app/core/config.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 1

## Estado de preparación

**READY**

La fuente de orígenes, los métodos, las cabeceras, la prohibición del comodín y el comportamiento con la variable vacía están definidos. Ninguna decisión de DECISIONES.md lo contradice. La cookie de refresh de N-13 no exige `allow_credentials` porque el front se sirve por el mismo origen. No hay tablas ni endpoints propios.

## Resumen

`parse_origins(value)` convierte `CORS_ORIGINS` (lista separada por comas) en una lista de orígenes exactos (`esquema://host[:puerto]`, sin ruta ni barra final). Falla con `*`, `null` o cualquier valor que no sea un origen. `create_app()` instala `CORSMiddleware` solo si la lista no está vacía, con `allow_origins` exactos, métodos `GET, POST, PATCH, PUT, DELETE` y cabeceras `Authorization, Content-Type`. Con la variable vacía no hay middleware, y un preflight ajeno no recibe `Access-Control-Allow-Origin`.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md. Nota: N-13 pone el refresh en cookie HttpOnly. Como el front y el API comparten origen (Nginx en producción, proxy de Vite en desarrollo), `allow_credentials` queda en `False` y no hace falta cambiar la historia.

## Validación contra el dominio

- Sin aggregates ni eventos. Protege la sesión del personal (RN-15, indirecto).
- Función pura: `parse_origins(value: str) -> list[str]`.

## Validación contra la arquitectura

- `CORS_ORIGINS` está en `Settings` (US-011) como `list[AnyHttpUrl]`. Pydantic normaliza `AnyHttpUrl` con barra final (`http://apex.local/`), y eso rompería la comparación exacta del encabezado `Origin`. Se declara como `Annotated[list[str], NoDecode]`, con un validador que llama a `parse_origins`. Es un ajuste de tipo sobre US-011, no de alcance.
- El middleware vive en `main.py` (`create_app`), no en un módulo.
- US-153 (v0.3) agrega después la regla de no mezclar `http:` con `APEX_DOMAIN`; `parse_origins` deja el gancho (devuelve orígenes ya validados).
- Sin tablas, sin bus, sin rol, sin paginación.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `parse_origins(value: str) -> list[str]` en `api/src/app/core/config.py`: separa por comas, recorta espacios, ignora vacíos, exige esquema `http` o `https`, host y puerto opcional, sin ruta, query ni fragmento. Lanza `ValueError("CORS_ORIGINS no admite '*'")` con `*` o `null`, y quita duplicados conservando el orden — 1 h
- [ ] T2 · Cambiar el campo `CORS_ORIGINS` de `Settings` a `Annotated[list[str], NoDecode] = []` con `field_validator` que usa `parse_origins`; un error de validación hace fallar el arranque con el nombre de la variable — 0,5 h
- [ ] T3 · En `create_app()`: si la lista no está vacía, `app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type"], allow_credentials=False, max_age=600)` — 0,5 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T4 · `api/tests/core/test_cors.py::test_parse_origins`: `"http://apex.local"` → `["http://apex.local"]`; `" http://a.local , https://b.local:8443 "` → dos orígenes; `""` → `[]`; `"*"`, `"null"`, `"http://a.local/ruta"` y `"apex.local"` → `ValueError` — 0,5 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- [ ] T5 · `api/tests/core/test_cors.py` con `create_app()` y `CORS_ORIGINS=http://apex.local`: preflight `OPTIONS /api/v1/health` con `Origin: http://apex.local` y `Access-Control-Request-Method: POST` → `Access-Control-Allow-Origin: http://apex.local`; con `Origin: https://evil.example` → sin esa cabecera; con `CORS_ORIGINS=""` → ningún preflight recibe la cabecera; con `CORS_ORIGINS="*"` construir `Settings` lanza el error explícito — 1,5 h

### Tests de arquitectura
- No aplica (la suite `tests/architecture` debe seguir verde).

### Front
- No aplica.

### DevOps
- [ ] T6 · `.env.example`: `CORS_ORIGINS=` vacío por defecto, con el comentario "solo si el front se sirve desde otro origen; nunca *"; confirmar que el proxy de Vite (US-009) envía `/api` al API para que el desarrollo no necesite CORS — 0,5 h

### Seguridad
- [ ] T7 · Revisión: no se usa `allow_origin_regex`; `allow_credentials` en `False`; el log de arranque muestra los orígenes permitidos (no son secretos) — 0,5 h

## Orden de ejecución
1. T4 (prueba pura en rojo)
2. T1
3. T2
4. T5 (en rojo)
5. T3
6. T6
7. T7

## Dependencias técnicas
- US-020 · create_app, migraciones y health: lugar del middleware.
- US-011 · Configuración desde .env: campo `CORS_ORIGINS` (ajuste de tipo en T2).
- US-009 · Esqueleto del front: proxy de Vite en desarrollo.

## Endpoints
- Ninguno.

## Riesgos
- Si un día el front se sirve desde otro origen, el refresh por cookie (N-13) necesitaría `allow_credentials=True` y `SameSite=None; Secure`, lo que exige TLS — mitigación: queda fuera de v0.1; se revisa con EP-20.
- Cambiar el tipo de `CORS_ORIGINS` choca con lo que escriba US-011 — mitigación: T2 lo hace en el mismo PR y con prueba.

## Estimación
- Backend: 2 h
- Front: 0 h
- Pruebas: 2 h
- DevOps / seguridad: 1 h
- **Total: 5 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_cors.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `curl -s -i -X OPTIONS http://localhost:8000/api/v1/health -H 'Origin: https://evil.example' -H 'Access-Control-Request-Method: POST'` no trae `access-control-allow-origin`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.config --cov-fail-under=80`
