# US-031 · Pruebas de arquitectura criptográfica — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-02-bus-de-criptografia/US-031-pruebas-de-arquitectura-criptografica.md`
- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context / módulo:** Crypto (`api/tests/architecture/`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

Las dos pruebas, los seis módulos prohibidos, las carpetas permitidas y el recorrido automático de columnas `Encrypted` están definidos por la historia y por `CLAUDE.md` (bus, punto 8). DECISIONES N-01 agrega una comprobación barata (ninguna columna `*_hint`) que no cambia el alcance. Para detectar una columna sensible declarada como texto normal (escenario 3) se cruza el descubrimiento automático con las columnas esperadas que declara el registro de US-025.

## Resumen

`test_banned_imports.py` recorre el AST de todo `api/src/app` y falla, con archivo y línea, si un archivo fuera de `core/crypto/` o de `core/security` importa `cryptography`, `oqs`, `hashlib`, `hmac`, `jwt` o `argon2`, también con `importlib.import_module("...")` o `__import__("...")` literales. `test_no_plaintext_at_rest.py` descubre todas las columnas `Encrypted` de `Base.metadata`, crea filas con valores conocidos usando la fábrica de cada tabla y verifica con SQL crudo que ninguna columna de la fila contiene el valor en claro ni su forma normalizada; además comprueba que cada columna que el registro espera cifrada exista como `Encrypted` de su clase.

## Correcciones aplicadas por DECISIONES.md

- La historia permite primitivas en `core/security/` → se permiten en `core/security.py` (archivo, como lo nombra `CLAUDE.md`) y en `core/security/` si llegara a ser paquete; no es corrección de DECISIONES sino de la estructura de `CLAUDE.md`.
- Ningún fragmento de un dato cifrado se guarda en claro → la prueba "sin claro" también falla si una tabla con columnas `Encrypted` tiene alguna columna que termine en `_hint`: corregido por DECISIONES N-01.
- `core/audit.py` calcula SHA-256 sin `hashlib` (lo pide a `core/crypto/digest.py`), así que no necesita excepción: confirmado por DECISIONES N-06; la prueba no tiene lista de excepciones fuera de las dos carpetas.

## Validación contra el dominio

- Protege los value objects cifrados de `Member` (y luego `athlete.metric`, `attachment.sensitive`) sin introducir entidades.
- RN-13 se vuelve verificable en cada PR: ningún valor sensible en claro en la base.
- Normalización de N-02 usada para la forma normalizada que se busca en la fila.
- Sin eventos ni funciones de negocio. Función pura de prueba: `find_banned_imports(source, path) -> list[Violation]`.

## Validación contra la arquitectura

- Complementa la regla `banned-api` de ruff (US-002): ruff cubre `import`, la prueba cubre además imports dinámicos literales y sirve de segunda barrera si alguien cambia la configuración de ruff.
- La prueba "sin claro" no importa modelos de un módulo a mano: importa la aplicación (`app.main`) para poblar `Base.metadata` y usa fábricas de prueba por tabla (`api/tests/factories/`), así cumple el criterio "no una lista escrita a mano".
- Corre en el job de pytest de CI (US-003) y bloquea el merge.
- Sin router, sin rol, sin paginación.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `api/tests/architecture/_imports.py`: `BANNED = {"cryptography","oqs","hashlib","hmac","jwt","argon2"}`; `find_banned_imports(source: str, path: str) -> list[Violation]` con `ast.walk` sobre `Import`, `ImportFrom` (módulo raíz, ignora imports relativos de nivel > 0 dentro de `app`) y `Call` a `importlib.import_module` o `__import__` con argumento literal; `is_allowed(path)` para `app/core/crypto/`, `app/core/security.py` y `app/core/security/` — 2 h
- [ ] T2 · `api/tests/factories/__init__.py`: registro `FACTORIES: dict[str, Callable[[], object]]` por nombre de tabla (`esquema.tabla`) y valores conocidos por `value_type` (`"7319582046"` para documento, `"+57 300 765 4321"` para teléfono, `"Lucia.Gomez@Correo.co"` para correo, `date(1991, 7, 23)`, `{"name": "Rosa", "phone": "3115550199"}`) — 1 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T3 · `api/tests/architecture/test_import_analyzer.py` con fragmentos de código: `import hashlib` y `from cryptography.hazmat.primitives import hashes` en `app/modules/members/service.py` se reportan con línea; `importlib.import_module("hmac")` y `__import__("jwt")` se reportan; los mismos en `app/core/crypto/aead.py` y `app/core/security.py` no; `import hashlibx` no — 1 h

### Tests de service con PostgreSQL
- [ ] T4 · `api/tests/architecture/test_no_plaintext_at_rest.py`: importa `app.main`; descubre las columnas `Encrypted` con `discovery.encrypted_columns` (US-030) o un recorrido equivalente de `Base.metadata`; por cada tabla exige una fábrica (si falta, falla con "agregue una fábrica para <tabla>"); inserta una fila por ORM con los valores conocidos; `SELECT row_to_json(t)::text FROM <tabla> t WHERE id = :id` no contiene el valor en claro ni `normalize_for_index` de él; falla con tabla y columna. Mientras no exista una tabla de negocio con cifrado (antes de US-069) corre sobre el modelo de prueba de US-028 — 2 h
- [ ] T5 · En el mismo archivo, `test_registry_columns_are_encrypted`: cada entrada de `registry.columns` cuya tabla exista en los metadatos debe ser `Encrypted` de esa `data_class` (detecta el escenario "columna sensible declarada como texto normal"); las entradas cuya tabla aún no existe se informan con `warnings.warn`; ninguna tabla con columnas `Encrypted` tiene columnas `*_hint` (N-01) — 1 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T6 · `api/tests/architecture/test_banned_imports.py`: recorre `api/src/app/**/*.py` con T1 y falla listando `archivo:línea: módulo`; prueba de control en CI que copia un archivo con `import hashlib` a un directorio temporal bajo un `app/modules/` simulado y verifica que el analizador falla — 1 h

### Front
- No aplica.

### DevOps
- [ ] T7 · `.github/workflows/ci.yml` (US-003): `uv run pytest tests/architecture -q` como paso obligatorio del job de pytest con el servicio PostgreSQL; marcado como check requerido en la protección de `main` — 0,5 h

### Seguridad
- [ ] T8 · Revisión: la lista de módulos coincide con la de ruff `banned-api` en `pyproject.toml`; ninguna excepción por archivo fuera de `core/crypto` y `core/security`; los valores de prueba no son datos reales — 0,5 h

## Orden de ejecución
1. T3 (prueba pura), luego T1
2. T6
3. T2, luego T4 y T5
4. T7, T8

## Dependencias técnicas
- US-028 · Tipos Encrypted y BlindIndexed: columnas a descubrir y modelo de prueba.
- US-025 · Registro de clases de dato: `columns` esperadas y `value_type`.
- US-026 · Normalización: forma normalizada que se busca en la fila.
- US-002 · Regla `banned-api` de ruff (EP-00): misma lista de módulos.
- US-003 · CI (EP-00): job de pytest donde corre la suite.
- US-069 · Registrar socio (EP-07): primera tabla real que la prueba recorre; necesita su fábrica en `api/tests/factories/`.

## Endpoints
- Ninguno.

## Riesgos
- Una tabla nueva con campos cifrados sin fábrica rompe la suite — impacto: fricción al agregar módulos — mitigación: el mensaje de error dice qué fábrica falta; es intencional (obliga a probar el cifrado de cada tabla).
- Imports dinámicos no literales (`import_module(nombre)`) no se detectan — mitigación: se acepta; la revisión de PR y ruff cubren el resto; queda anotado en la prueba.
- Entradas del registro sin tabla todavía solo avisan — mitigación: al cerrar US-069 la advertencia se vuelve error para `members.members`.

## Estimación
- Backend: 3 h
- Front: 0 h
- Pruebas: 5 h
- DevOps / seguridad: 1 h
- **Total: 9 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/architecture/test_import_analyzer.py tests/architecture/test_banned_imports.py tests/architecture/test_no_plaintext_at_rest.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] PR de control con `import hashlib` en `api/src/app/modules/members/service.py` falla en CI con el archivo y la línea
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest tests/architecture --cov=tests.architecture --cov-fail-under=80`
