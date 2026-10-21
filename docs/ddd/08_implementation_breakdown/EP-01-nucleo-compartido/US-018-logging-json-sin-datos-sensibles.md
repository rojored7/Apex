# US-018 · Logs JSON a stdout sin datos sensibles — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-01-nucleo-compartido/US-018-logging-json-sin-datos-sensibles.md`
- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context / módulo:** core (`api/src/app/core/logging.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

Los campos del log, la lista de claves redactadas, los patrones de valor (`apx1.` y JWT) y la configuración de Uvicorn y SQLAlchemy están completos en la historia. No hay supuestos abiertos. La prueba de extremo a extremo depende de historias posteriores y se deja marcada para activarse cuando existan.

## Resumen

Esta historia entrega:
- en `core/logging.py`, un formateador JSON de una línea;
- la función pura `redact`, por clave y por forma del valor, que también se aplica dentro del texto del mensaje y de la traza;
- `configure_logging(settings)`;
- un middleware ASGI que asigna el `request_id`, lo deja en `request_id_var` (`core/context.py`) y escribe una línea de acceso por petición, sin cuerpo, sin query string y sin cabeceras;
- la configuración de Uvicorn (log de acceso propio desactivado) y de SQLAlchemy, que nunca muestra parámetros.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md. N-44 (Nginx no registra query strings de `/api/v1/tv/`) es complementario y lo resuelve EP-23 en Nginx.

## Validación contra el dominio

- RN-13: un dato sensible nunca aparece en claro fuera del bus. Los logs redactan documento, teléfono, correo, fecha de nacimiento, contacto de emergencia y blobs `apx1.`.
- Función pura: `redact(record: Mapping[str, Any]) -> dict[str, Any]`.
- Sin aggregates ni eventos.

## Validación contra la arquitectura

- `core/logging.py` importa `core/config.py` (`LOG_LEVEL`) y `core/context.py` (`request_id_var`). No importa módulos ni `core/audit`.
- El nombre `logging.py` dentro del paquete `app.core` no tapa la biblioteca estándar, porque los imports son absolutos (`from app.core import logging as app_logging`). Se documenta para evitar `import logging` relativo.
- La línea de acceso usa la ruta de la plantilla (`/api/v1/members/{id}`) cuando existe, y si no `scope["path"]` sin query. No registra `q`, que puede contener un documento.
- El engine ya nace con `echo=False` y `hide_parameters=True` (US-012). Aquí solo se verifica.
- Rol, paginación, bus de criptografía y auditoría: no aplican.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `class JsonFormatter(logging.Formatter)`:
  - campos `timestamp`, en ISO 8601 UTC con `Z`, derivado de `record.created` con `datetime.fromtimestamp(record.created, UTC)`;
  - `level`, `logger`, `message` y `request_id`, este último de `request_id_var`;
  - los extras `path`, `method`, `status` y `duration_ms`;
  - `exception` con la traza formateada.
  
  Todo pasa por `redact` antes de `json.dumps(..., ensure_ascii=False)`, en una sola línea (criterio 1) — 1,5 h
- [ ] T2 · Función pura `redact(record) -> dict`:
  - es recursiva sobre `dict` y `list`;
  - las claves se comparan sin distinguir mayúsculas contra `SENSITIVE_KEYS = {"password", "token", "refresh_token", "access_token", "authorization", "document", "phone", "email", "birth_date", "emergency_contact", "kek", "dek", "secret"}` y su valor pasa a `"[redacted]"`;
  - un valor de texto que empieza por `apx1.` o que coincide con un JWT pasa a `"[redacted]"`;
  - dentro de textos largos (mensaje, traza) reemplaza las subcadenas que coinciden con `apx1\.[A-Za-z0-9._-]+` y `eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*` (criterios 2 y 3).
  
  — 1 h
- [ ] T3 · `configure_logging(settings: Settings) -> None`:
  - un handler a `sys.stdout` con `JsonFormatter` y el nivel de `settings.LOG_LEVEL`;
  - `uvicorn.access` desactivado (lo reemplaza el middleware);
  - `uvicorn.error` con el mismo formateador;
  - `sqlalchemy.engine` en `WARNING`.
  
  Es idempotente — 1 h
- [ ] T4 · `RequestLogMiddleware`, ASGI puro (no `BaseHTTPMiddleware`, para que el `ContextVar` sea visible en el endpoint):
  - genera el `request_id` con `uuid4().hex`, lo fija en `request_id_var` y lo devuelve en la cabecera `X-Request-ID`;
  - mide `duration_ms` con `time.perf_counter()`;
  - escribe una línea `http_request` con `method`, `path` (la plantilla de la ruta o la ruta sin query), `status`, `duration_ms` y `request_id`;
  - nunca registra el cuerpo, la query string ni las cabeceras (criterio 4).
  
  — 1,5 h

### Schemas
- No aplica.

### Router
- No aplica (el registro del middleware lo hace `create_app()` de US-020).

### Tests unitarios puros
- [ ] T5 · `tests/core/test_logging_redact.py`:
  - `{"password": "x", "document": "1020304"}` da los dos valores como `[redacted]` (criterio 2, BDD 1);
  - las claves anidadas, las de listas y las escritas en mayúsculas (`Authorization`) se redactan;
  - `apx1.k1.A256GCM.n.c` y `eyJhbGciOi...x.y` bajo cualquier clave se redactan (criterio 3);
  - un JWT dentro del texto de un mensaje desaparece (BDD 2);
  - `JsonFormatter` produce JSON válido en una sola línea, incluso con una traza de varias líneas (criterio 1).
  
  — 1 h

### Tests de service con PostgreSQL
- [ ] T6 · `tests/core/test_logging_sql.py`: con `configure_logging` en `DEBUG`, una consulta con el parámetro `"1020304"` que falla a propósito no deja `1020304` en la salida capturada (criterio 5) — 1 h

### Tests de router
- [ ] T7 · `tests/core/test_logging_access.py`, con `capsys` sobre una app mínima con el middleware:
  - `GET /api/v1/members?q=1020304`, con cabecera `Authorization: Bearer eyJ...`, deja una línea JSON con `path` igual a `/api/v1/members` y sin `1020304` ni `eyJ` (BDD 3, criterio 4);
  - la respuesta trae `X-Request-ID`;
  - un log emitido dentro del endpoint lleva el mismo `request_id`.
  
  — 1,5 h

### Tests de arquitectura
- [ ] T8 · `api/tests/architecture/test_no_sensitive_in_logs.py`: un flujo de login (US-042), creación de socio (US-069) y `reveal` (US-074), con captura de stdout, verifica que no aparecen el token, el documento ni el blob. Queda con `pytest.mark.skipif` hasta que existan esas rutas (criterio 6) — 1 h

### Front
- No aplica.

### DevOps
- No aplica (stdout ya es el destino por defecto de Docker; US-005 no necesita cambios).

### Seguridad
- [ ] T9 · Revisión:
  - lista de claves completa frente a los campos cifrados de v0.1 (`members.document`, `phone`, `email`, `birth_date`, `emergency_contact`);
  - el log del 500 de US-017 pasa por `redact`;
  - `Settings` nunca se loguea entero;
  - el `X-Request-ID` no reutiliza un valor enviado por el cliente, para evitar inyectar texto en los logs.
  
  — 0,5 h

## Orden de ejecución
1. T5 (en rojo)
2. T2
3. T1
4. T3
5. T7 (en rojo)
6. T4
7. T6
8. T8
9. T9

## Dependencias técnicas
- US-011 · Configuración desde .env: `LOG_LEVEL`.
- US-012 · Base de datos: engine con `hide_parameters=True` y `echo=False` (criterio 5).
- US-016 · Hook de auditoría: `core/context.py` con `request_id_var`. Si esta historia va antes, crea el archivo con solo esa variable.
- US-020 · create_app: registra `RequestLogMiddleware` y llama a `configure_logging`.
- US-042, US-069 y US-074: activan la prueba T8.

## Endpoints
- Ninguno.

## Riesgos
- Un dato sensible con una clave no listada (por ejemplo `cedula` en un `extra`) se escaparía — mitigación: la redacción por forma (`apx1.`, JWT) y la regla de revisión de que los services nunca pasan valores descifrados a los logs. La lista se amplía en cada historia que agregue datos cifrados (EP-24, EP-19).
- `BaseHTTPMiddleware` rompe la propagación del `ContextVar` hacia el endpoint — mitigación: middleware ASGI puro (T4) y prueba del mismo `request_id` en T7.
- Redactar `email` oculta también correos útiles para diagnosticar el login — mitigación: se acepta; el diagnóstico usa `user_id` y `request_id`.

## Estimación
- Backend: 5 h
- Front: 0 h
- Pruebas: 4,5 h
- DevOps / seguridad: 0,5 h
- **Total: 10 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_logging_redact.py tests/core/test_logging_sql.py tests/core/test_logging_access.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `docker compose -f infra/compose.yml logs api | tail -n 20 | jq -c .` parsea cada línea como JSON
- [ ] `curl -s "http://localhost:8000/api/v1/health?q=1020304" >/dev/null && docker compose -f infra/compose.yml logs api | grep -c 1020304` devuelve 0
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.logging --cov-fail-under=80`
