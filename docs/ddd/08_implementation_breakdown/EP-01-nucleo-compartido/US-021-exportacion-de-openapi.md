# US-021 · Exportación de `docs/openapi.json` verificada en CI — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-01-nucleo-compartido/US-021-exportacion-de-openapi.md`
- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context / módulo:** core, contrato HTTP (`api/src/app/cli.py`, `docs/openapi.json`, `.github/workflows/ci.yml`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

El comando, el formato determinista y el paso de CI están definidos. El supuesto de no ejecutar el `lifespan` se acepta, y es viable porque `app.openapi()` no lo dispara. Hay un ajuste técnico: el documento usa una versión fija, porque `APP_VERSION` cambia con cada commit (es el SHA) y rompería la comparación en CI.

## Resumen

Esta historia entrega:
- el subcomando `export-openapi <ruta>` en `cli.py`, que construye `create_app()` con una configuración de exportación (sin `.env`, sin base y sin llaves), llama a `app.openapi()` y escribe JSON con claves ordenadas, sangría de 2 espacios y salto de línea final;
- un paso de CI que regenera el archivo y falla con `git diff --exit-code` si el versionado está desactualizado, indicando el comando a correr;
- `docs/openapi.json` versionado por primera vez.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md. N-14 (`/docs` y `/openapi.json` apagados en producción) no afecta la exportación, porque se genera desde el código y no desde la ruta HTTP.

## Validación contra el dominio

- No toca el dominio. Publica el contrato HTTP de `05_service_design.md` sección 4, con las correcciones de DECISIONES que cada historia incorpora.
- Sin eventos ni funciones puras.

## Validación contra la arquitectura

- `cli.py` es el punto de comandos que fija `CLAUDE.md`. La exportación solo importa `app.main.create_app` y no abre conexiones.
- La configuración de exportación se arma con `Settings.model_construct(...)`, sin validación y con valores de marcador no secretos. No exige archivos `FilePath` ni la KEK (criterio 5). No se loguea ni se escribe en el documento.
- El documento contiene `ErrorResponse` (US-017) y las rutas `/api/v1/...` (US-020), lo que cubre el criterio 4.
- Rol, paginación, bus de criptografía y auditoría: no aplican. Este comando no escribe en tablas, así que no necesita actor.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `cli.py`: aplicación `typer` (MIT), si aún no existe, con el subcomando `export-openapi(output: Path)`, invocable como `uv run python -m app.cli export-openapi ../docs/openapi.json` desde `api/` — 1 h
- [ ] T2 · Función `build_openapi_document() -> dict[str, Any]`:
  - llama a `create_app(settings=export_settings())`, donde `export_settings()` arma un `Settings.model_construct(...)` con marcadores;
  - devuelve `app.openapi()`, sin entrar al `lifespan`;
  - fija `info.version` con la versión del paquete (`importlib.metadata.version("apex-api")`) y no con `APP_VERSION`, para que la salida no cambie con cada commit.
  
  — 1,5 h
- [ ] T3 · `write_openapi(doc, output) -> None` con `json.dumps(doc, sort_keys=True, indent=2, ensure_ascii=False) + "\n"`, en UTF-8 y con fin de línea `\n` también en Windows (`newline="\n"`) (criterio 1) — 0,5 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T4 · `tests/core/test_openapi_export.py`:
  - dos exportaciones seguidas a archivos temporales son idénticas byte a byte (criterio 1, BDD 3);
  - con `monkeypatch.delenv` de todas las variables del api y sin base disponible, la exportación termina bien (criterio 5);
  - el documento tiene `components.schemas.ErrorResponse` y todas las rutas de módulos empiezan por `/api/v1` (criterio 4);
  - `info.version` no depende de `APP_VERSION`.
  
  — 2 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- No aplica nueva. Debe seguir verde `test_error_responses_in_openapi.py` (US-017).

### Front
- No aplica (US-059 genera `web/src/core/api/types.ts` desde este archivo con `openapi-typescript`).

### DevOps
- [ ] T5 · El paso `openapi` en el job `api` de `.github/workflows/ci.yml`:
  - ejecuta `cd api && uv run python -m app.cli export-openapi ../docs/openapi.json`;
  - luego `git diff --exit-code docs/openapi.json`;
  - si falla, emite `::error::docs/openapi.json está desactualizado. Corra: cd api && uv run python -m app.cli export-openapi ../docs/openapi.json` y sale con 1 (criterios 2 y 3, BDD 1 y 2).
  
  — 1 h
- [ ] T6 · Generar y versionar el `docs/openapi.json` inicial. Agregar `docs/openapi.json text eol=lf` a `.gitattributes`, para que Windows no altere los finales de línea — 0,5 h

### Seguridad
- [ ] T7 · Revisión:
  - los marcadores de `export_settings()` no son secretos reales y no aparecen en el documento;
  - el documento no publica rutas internas de diagnóstico;
  - el paso de CI no necesita secretos.
  
  — 0,5 h

## Orden de ejecución
1. T4 (en rojo)
2. T2
3. T3
4. T1
5. T6
6. T5
7. T7

## Dependencias técnicas
- US-020 · create_app, migraciones y health: `create_app(settings=...)` y `app.main` perezoso.
- US-017 · Envelope de errores: `ErrorResponse` en el documento.
- US-003 · Pipeline CI: el job `api` donde va el paso.
- US-011 · Configuración: `Settings.model_construct` con los campos actuales; cada campo nuevo debe tener un marcador en `export_settings()`.

## Endpoints
- Ninguno.

## Riesgos
- Salida no determinista por la versión, el orden de las rutas o los finales de línea — mitigación: versión del paquete, `sort_keys`, `newline="\n"` y `.gitattributes` (T2, T3, T6), con la prueba byte a byte de T4.
- Un campo obligatorio nuevo en `Settings` sin marcador en `export_settings()` rompe la exportación en CI — mitigación: `model_construct` no valida; la prueba T4 corre sin entorno y detecta cualquier acceso a un campo faltante.
- `create_app` con efectos al construirse (conexión, lectura de llaves) rompería el criterio 5 — mitigación: todo efecto va en el `lifespan` o en pasos de arranque (US-020); T4 lo prueba sin base.

## Estimación
- Backend: 3 h
- Front: 0 h
- Pruebas: 2 h
- DevOps / seguridad: 2 h
- **Total: 7 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_openapi_export.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run python -m app.cli export-openapi ../docs/openapi.json && git diff --exit-code ../docs/openapi.json` termina con 0
- [ ] `cd api && uv run python -m app.cli export-openapi /tmp/a.json && uv run python -m app.cli export-openapi /tmp/b.json && cmp /tmp/a.json /tmp/b.json` no muestra diferencias
- [ ] El paso de CI falla en un PR de prueba que agrega un campo a un schema sin regenerar el archivo
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.cli --cov-fail-under=80`
