# US-026 · Índice ciego HMAC-SHA-256 — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-02-bus-de-criptografia/US-026-indice-ciego-hmac.md`
- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context / módulo:** Crypto (`api/src/app/core/crypto/normalize.py`, `api/src/app/core/crypto/bus.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

La normalización, que era el supuesto bloqueante de la historia, quedó decidida por DECISIONES N-02 (NFKD sin diacríticos, sin guiones; reglas propias para teléfono y correo). La llave HMAC por clase, el formato hexadecimal y los errores están en la historia. Varios criterios de aceptación cambian sus valores esperados por esa decisión y se reescriben aquí.

## Resumen

Se implementa la función pura `normalize_for_index(value, kind)` con tres variantes (`generic` para documento, `phone`, `email`), `blind_index(data_class, value) -> str` (HMAC-SHA-256 en hexadecimal con la llave `index` activa de la clase) y la creación idempotente al arrancar de una llave `index` envuelta para `member.document`, `member.phone` y `member.email`.

## Correcciones aplicadas por DECISIONES.md

- La historia normaliza solo con minúsculas, sin espacios ni puntos, y conserva tildes y guiones → `generic` aplica NFKD, quita marcas diacríticas (categoría Unicode `Mn`), pasa a minúsculas y elimina todo espacio en blanco, puntos y guiones (`-`, `‐`, `–`, `—`): corregido por DECISIONES N-02. "1020-304" y "1020304" producen el mismo índice.
- Teléfono → solo dígitos y sin el prefijo `57` o `+57` inicial: corregido por DECISIONES N-02. Interpretación que se fija en ADR-002: tras dejar solo dígitos, se quita `57` inicial únicamente si quedan 12 dígitos (código de país más un número colombiano de 10), para no recortar números que no traen el prefijo.
- Correo → minúsculas y sin espacios, conservando puntos, guiones y tildes: corregido por DECISIONES N-02. El criterio 1 de la historia (`"Ana.Perez@Mail.com"` → `"anaperez@mailcom"`) se reemplaza por `"ana.perez@mail.com"` para `member.email`.
- La firma pura del modelo `crypto.normalize_for_index(value) -> str` → `normalize_for_index(value, kind) -> str`; quien llama al bus no cambia, porque `blind_index(data_class, value)` toma el `kind` del registro de US-025: corregido por DECISIONES N-02 (y N-04 para el registro).
- Búsqueda con `q` en listas: el cálculo del índice cuenta como operación individual con `record_id` nulo (supuesto de US-029, sin cambio).

## Validación contra el dominio

- `CryptoKey` con `purpose = index`, `algorithm = HMAC-SHA256`, una `active` por clase (índice de US-024).
- RN-13 (búsqueda por índice ciego sin descifrar): `blind_index` nunca usa la DEK ni descifra nada.
- Invariante del aggregate `Member` (documento único entre no borrados por índice ciego): depende de que la normalización sea estable; lo aplica US-069 con el índice único parcial de `0006_members`.
- Función pura `normalize_for_index` coincide con la sección 4 del modelo, corregida por N-02.
- Sin eventos.

## Validación contra la arquitectura

- `hmac` y `hashlib` solo dentro de `core/crypto/mac.py` (lint `banned-api`); `normalize.py` usa solo `unicodedata` y `re`.
- Única puerta: los módulos llaman `bus.blind_index`; nunca eligen llave.
- `core/crypto` no depende de `app.modules`: el `kind` de cada clase vive en `registry.py`.
- Sin router, sin rol, sin paginación, sin tablas auditadas.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `api/src/app/core/crypto/normalize.py`: `normalize_for_index(value: str, kind: Literal["generic","phone","email"]) -> str`; `generic`: `unicodedata.normalize("NFKD", v)`, quitar caracteres `Mn`, minúsculas con `lower()` (no `casefold()`, que expande `ß`), eliminar `\s` Unicode (incluye tabulador y espacio no separable), `.`, `-` y los guiones tipográficos; `phone`: solo `str.isdigit()` ASCII, quitar `57` inicial si quedan 12 dígitos; `email`: `lower()` y sin `\s`. Resultado vacío → `CryptoError("valor vacío")` — 2,5 h
- [ ] T2 · `api/src/app/core/crypto/mac.py`: `hmac_sha256_hex(key: bytes, data: bytes) -> str` (`hmac.new(..., hashlib.sha256).hexdigest()`) — 0,5 h
- [ ] T3 · `bus.blind_index(data_class: str, value: str) -> str`: `get_spec`, exige `index_kind` no nulo (si no, `CryptoError("data_class sin índice")`), normaliza, toma la llave `index` activa del keyring y devuelve 64 caracteres hexadecimales; llama a `oplog.record(verb="index", ...)` de US-029 — 1,5 h
- [ ] T4 · `bootstrap.ensure_keys` (de US-025): también crea una llave `purpose = index`, `algorithm = HMAC-SHA256` de 32 bytes envuelta por clase con `index_kind`, con el mismo `ON CONFLICT ... DO NOTHING`; el keyring carga las llaves `index` `active` — 1 h
- [ ] T5 · Sección "Normalización del índice ciego" en `docs/adr/ADR-002-criptografia.md` con las tres reglas, la interpretación del prefijo 57 y la advertencia de irreversibilidad — 0,5 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T6 · `api/tests/crypto/test_normalize.py` parametrizado: `generic` `" 1.020.304 "` → `"1020304"`, `"1020-304"` → `"1020304"`, `"José Pérez"` → `"joseperez"`, tabulador y ` `, `"Ana.Perez@Mail.com"` → `"anaperez@mailcom"`; `phone` `"300 123 4567"`, `"+57 300 123 4567"`, `"573001234567"`, `"(300) 123-4567"` → `"3001234567"`, `"6011234567"` se conserva; `email` `" Ana.Perez@Mail.com "` → `"ana.perez@mail.com"`; `" . . "` y `"- -"` en `generic` lanzan `CryptoError("valor vacío")` — 2 h

### Tests de service con PostgreSQL
- [ ] T7 · `api/tests/crypto/test_blind_index.py`: `"1.020.304"`, `"1020304"`, `" 1020304 "` y `"1020-304"` dan el mismo índice en `member.document`; el mismo valor en `member.document` y `member.phone` da índices distintos; determinismo entre dos llamadas; `member.birth_date` lanza `CryptoError`; el índice tiene 64 caracteres hexadecimales; arranque con base vacía crea tres llaves `index` envueltas y un segundo arranque no crea más; `wrapped_material` de la llave `index` difiere de la llave abierta — 2,5 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T8 · `test_banned_imports.py` (US-031) sigue verde: `hmac` y `hashlib` solo en `core/crypto/mac.py` (y en `digest.py` de US-027) — 0,5 h

### Front
- No aplica.

### DevOps
- No aplica.

### Seguridad
- [ ] T9 · Revisión: la llave `index` es distinta por clase (evita correlación entre documento y teléfono), el índice no se registra en logs, la normalización no filtra el valor en mensajes de error, el índice nunca se devuelve por el API (lo verifica US-070) — 1 h

## Orden de ejecución
1. T6 (prueba pura), luego T1
2. T2
3. T7 escrita, luego T3 y T4
4. T5
5. T8, T9

## Dependencias técnicas
- US-023 · KeyProvider y proveedor local: envoltura de la llave HMAC.
- US-024 · Tablas crypto: llave `index` en `crypto_keys`.
- US-025 · Registro y keyring: `index_kind` por clase y carga de llaves.
- US-029 · Bitácora crypto_ops: registro del verbo `index`.

## Endpoints
- Ninguno.

## Riesgos
- La normalización es irreversible una vez haya `_idx` guardados; cambiarla exige recalcular todos los índices y puede ocultar duplicados — mitigación: se fija en ADR-002 y en pruebas con vectores exactos antes de US-069; cualquier cambio exige parar y preguntar (`CLAUDE.md`).
- Recortar el `57` de un número que no lo traía como prefijo — mitigación: solo se recorta con 12 dígitos; los números colombianos de 10 dígitos empiezan por 3 o por 60.
- US-070 (búsqueda) y US-069 (duplicados) deben usar la misma clase para normalizar; si la búsqueda por `q` no sabe si es documento o teléfono, debe calcular ambos índices — mitigación: se anota como contrato hacia EP-07 (calcular `blind_index` en las tres clases con índice y buscar en las tres columnas).

## Estimación
- Backend: 6 h
- Front: 0 h
- Pruebas: 5 h
- DevOps / seguridad: 1 h
- **Total: 12 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/crypto/test_normalize.py tests/crypto/test_blind_index.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `SELECT data_class FROM crypto.crypto_keys WHERE purpose = 'index' AND state = 'active'` devuelve exactamente `member.document`, `member.email` y `member.phone`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.crypto --cov-fail-under=80`
