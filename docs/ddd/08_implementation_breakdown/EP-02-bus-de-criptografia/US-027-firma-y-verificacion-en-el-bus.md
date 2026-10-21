# US-027 · Firma y verificación en el bus — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-02-bus-de-criptografia/US-027-firma-y-verificacion-en-el-bus.md`
- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context / módulo:** Crypto (`api/src/app/core/crypto/bus.py`, `api/src/app/core/crypto/signature.py`, `api/src/app/core/crypto/digest.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

El formato de la firma lo fija DECISIONES N-04 (`apx1.<key_id>.<alg>.<sig_b64url>`) y la verificación con llaves viejas la respalda Q27. El verbo `digest` del bus (N-06), que no estaba en ninguna historia, se ubica aquí porque comparte superficie (integridad sin cifrado) y es la pieza que US-015 necesita para no importar `hashlib`.

## Resumen

Se implementan `sign(data_class, data) -> str` y `verify(data_class, data, signature) -> bool`, delegando en `KeyProvider.sign`/`verify` con la llave registrada para la clase, el parseo puro del formato de firma de cuatro partes y `digest(data) -> str` (SHA-256 en hexadecimal, sin llave). En v0.1 no hay clases de firma de negocio: las pruebas registran una clase de prueba con `override_registry`.

## Correcciones aplicadas por DECISIONES.md

- La historia supone que la firma usa "el mismo prefijo y estructura de partes que el blob" → la firma tiene cuatro partes, `apx1.<key_id>.<alg>.<sig_b64url>`, sin nonce: confirmado por DECISIONES N-04.
- El bus de la historia tiene solo `sign` y `verify` → se agrega `digest(data: bytes) -> str` (SHA-256) para que `core/audit.py` calcule la cadena sin importar `hashlib`: corregido por DECISIONES N-06. `digest` no usa llave, así que no deja fila en `crypto_ops` (no hay `key_id` que registrar y duplicaría cada escritura de auditoría); el verbo no se agrega al CHECK de `crypto_ops`.
- Verificar con una llave que ya no es `active` → `verify` acepta llaves `active`, `decrypt_only` y `retired` de propósito `sign` (la llave pública sigue verificando firmas viejas): corregido por DECISIONES Q27, que amplía el criterio 4 de la historia también a `retired`.

## Validación contra el dominio

- `CryptoKey` con `purpose = sign`, `algorithm = Ed25519` en v0.1; `ML-DSA-65` llega con EP-17/EP-26 sin cambiar a quien firma (Q27).
- La llave privada nunca sale del proveedor: `wrapped_material` de una llave `sign` local guarda una referencia (`b"local:sign-ed25519"`), no material, como permite US-024 ("bytes envueltos o referencia del proveedor").
- `AuditEntry` (RN-16) depende de `digest` para `hash = SHA-256(prev_hash || canonical(row))`.
- Sin eventos. Función pura: `parse_signature(sig) -> SignatureParts`.

## Validación contra la arquitectura

- `hashlib` solo en `core/crypto/digest.py` y `core/crypto/mac.py`; Ed25519 vive en `local_provider.py` (US-023).
- Dirección de dependencias: `core/audit` → `core/crypto` (N-06), nunca al revés. `digest.py` no importa nada de `core/` para que `core/audit` lo pueda importar sin arrastrar el keyring ni la base (evita ciclos; ver la brecha de US-029).
- `sign`/`verify` son `async` porque el proveedor lo es (OpenBao firma remoto en v0.2).
- Sin router, sin rol, sin paginación.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `api/src/app/core/crypto/digest.py`: `digest(data: bytes) -> str` = `hashlib.sha256(data).hexdigest()`, sin dependencias de `core/`; reexportado como `bus.digest`. Se entrega primero y por separado porque US-015 lo necesita antes que el resto del bus — 1 h
- [ ] T2 · `api/src/app/core/crypto/signature.py`: `SignatureParts` (`key_id: UUID`, `alg`, `sig: bytes`); `format_signature(key_id, alg, sig) -> str` y `parse_signature(s) -> SignatureParts` (cuatro partes, prefijo `apx1`, `alg` en `{"Ed25519", "ML-DSA-65"}`, base64url válido); fallo → `CryptoError("firma_invalida")` — 1,5 h
- [ ] T3 · `bus.sign(data_class, data) -> str` (`async`): `get_spec` exige `sign=True`; toma la llave `sign` `active` del keyring (si no hay, `CryptoError("data_class sin llave de firma")`); `await provider.sign(key_ref, data)`; devuelve `format_signature`. `bus.verify(data_class, data, signature) -> bool` (`async`): `parse_signature`, la llave del `key_id` debe ser `purpose = sign` y de la misma `data_class` (si no, `CryptoError`), acepta `active`, `decrypt_only` y `retired`; datos alterados → `False` sin excepción. Ambos llaman a `oplog.record` (US-029) con verbos `sign` y `verify` — 2 h
- [ ] T4 · `bootstrap.ensure_keys` (US-025): crea la fila `purpose = sign`, `algorithm = Ed25519`, `wrapped_material = b"local:sign-ed25519"` solo para clases con `sign=True` (ninguna de negocio en v0.1) — 0,5 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T5 · `api/tests/crypto/test_signature_format.py`: ida y vuelta; `"abc"`; tres y cinco partes; `alg` desconocido; base64url inválido; `api/tests/crypto/test_digest.py`: vector conocido de SHA-256 (`b"abc"` → `ba7816bf…`) — 1 h

### Tests de service con PostgreSQL
- [ ] T6 · `api/tests/crypto/test_sign.py` con clase de prueba `test.signature` registrada por `override_registry` y proveedor local en `tmp_path`: firmar y verificar es `True`; `"hash-de-la-cadenA"` da `False`; firma `"abc"` lanza `CryptoError`; tras pasar la llave a `decrypt_only` y luego a `retired`, la firma vieja verifica; `sign` con `member.document` lanza `CryptoError`; una firma de otra clase no verifica para esta (lanza `CryptoError`) — 2 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T7 · `test_banned_imports.py` (US-031) sigue verde; `core/audit.py` (US-015) importa `core.crypto.digest` y no `hashlib` — 0,5 h

### Front
- No aplica.

### DevOps
- No aplica.

### Seguridad
- [ ] T8 · Revisión: el bus no tiene método que exponga la llave privada ni la pública en bruto, `verify` compara en tiempo constante (lo hace la primitiva), una firma de otra clase de dato no se acepta (evita reutilizar la firma de backups como firma de auditoría) — 0,5 h

## Orden de ejecución
1. T1 y su prueba de T5 (adelantable antes de US-015)
2. T5 (formato), luego T2
3. T6 escrita, luego T3 y T4
4. T7, T8

## Dependencias técnicas
- US-023 · KeyProvider y proveedor local: `sign`/`verify` Ed25519 y archivo de llave de firma.
- US-024 · Tablas crypto: fila `purpose = sign`.
- US-025 · Registro, keyring y bootstrap: `sign=True` por clase.
- US-029 · Bitácora crypto_ops: verbos `sign` y `verify`.
- US-015 · Tabla de auditoría y cadena de hashes (EP-01): consume `digest`; por eso T1 se entrega antes que US-015 aunque esta historia vaya después en la épica.

## Endpoints
- Ninguno.

## Riesgos
- US-015 está antes en la ruta crítica que EP-02 y necesita `digest` — impacto: bloqueo de la cadena de auditoría — mitigación: T1 es un archivo sin dependencias que se integra en el sprint de EP-01.
- En v0.1 solo hay una llave Ed25519 local para todas las clases de firma: dos clases compartirían llave — mitigación: no hay clases de firma de negocio en v0.1; US-140 (`init-keys --data-class`) crea una llave por clase antes de `audit.signature`.

## Estimación
- Backend: 5 h
- Front: 0 h
- Pruebas: 3,5 h
- DevOps / seguridad: 0,5 h
- **Total: 9 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/crypto/test_signature_format.py tests/crypto/test_digest.py tests/crypto/test_sign.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `grep -rn "import hashlib" api/src/app` solo muestra archivos dentro de `api/src/app/core/crypto/`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.crypto --cov-fail-under=80`
