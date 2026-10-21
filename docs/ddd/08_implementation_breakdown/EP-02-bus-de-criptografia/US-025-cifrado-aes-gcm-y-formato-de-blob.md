# US-025 · Cifrado AES-256-GCM y formato de blob — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-02-bus-de-criptografia/US-025-cifrado-aes-gcm-y-formato-de-blob.md`
- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context / módulo:** Crypto (`api/src/app/core/crypto/bus.py`, `registry.py`, `blob.py`, `keyring.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

El formato del blob, el algoritmo, el AAD y el registro de clases de dato están fijados por `CLAUDE.md` (bus, puntos 1 a 4) y DECISIONES N-04. La creación idempotente de DEK al arrancar y la lectura con llaves `decrypt_only` están en la historia. Lo único que se fija aquí, por ser irreversible, es la codificación exacta del AAD; se registra en ADR-002.

## Resumen

Se implementan `encrypt(data_class, plaintext, aad) -> str` y `decrypt(blob, aad) -> bytes` en el bus, el registro de clases de dato como constante en `core/crypto/registry.py`, las funciones puras `format_blob` y `parse_blob`, y el keyring en memoria que al arrancar crea una DEK `active` por clase sin llave (idempotente incluso con API y worker arrancando a la vez), desenvuelve las `active` y `decrypt_only` y carga bajo demanda una llave nueva creada por otro proceso (rotación de US-030).

## Correcciones aplicadas por DECISIONES.md

- Registro de `data_class` como constante en código y no como tabla → `core/crypto/registry.py`: confirmado por DECISIONES N-04 (el supuesto de la historia queda aceptado).
- El registro de la historia solo lista las cinco clases → cada entrada declara además su `index_kind` para el índice ciego (`generic`, `phone`, `email`) porque la normalización depende de la clase: corregido por DECISIONES N-02 (lo usa US-026).
- Actor de la creación de llaves al arrancar → `created_by = SYSTEM_USER_ID`: corregido por DECISIONES N-15.

## Validación contra el dominio

- `CryptoKey` con `purpose = encrypt`, `algorithm = A256GCM`, una `active` por clase (índice de US-024).
- Invariante "rotar deja la anterior en `decrypt_only`": `decrypt` toma el `key_id` del blob y acepta llaves `active` y `decrypt_only`; rechaza `retired` con `CryptoError("key_retired")`.
- "El material en claro nunca se persiste": la DEK se guarda solo envuelta (`KeyProvider.wrap`) y la prueba compara `wrapped_material != dek`.
- RN-13: las cinco clases de v0.1 (`member.document`, `member.phone`, `member.email`, `member.birth_date`, `member.emergency_contact`) coinciden con la tabla de clases de dato del modelo (sección 5).
- Funciones puras: `format_blob(key_id, alg, nonce, ct) -> str` y `parse_blob(blob) -> BlobParts`, como pide la historia. Sin eventos.

## Validación contra la arquitectura

- Única puerta: los módulos solo llaman `bus.encrypt`/`bus.decrypt`; nunca eligen llave ni algoritmo (`CLAUDE.md` bus, punto 2).
- `cryptography` (AESGCM) solo en `core/crypto/aead.py`; `bus.py`, `blob.py` y `registry.py` no importan primitivas directamente, lo que reduce la superficie que revisa el lint.
- `core/crypto` no importa `app.modules` ni `core/audit`. El registro guarda nombres de columnas esperadas como texto (`"members.members.document"`) para la prueba de US-031 y la rotación de US-030, sin importar modelos de ningún módulo.
- `encrypt`/`decrypt` son síncronas (solo CPU con la DEK en memoria) para poder usarse desde los tipos de columna de US-028; la carga de llaves (`keyring.load_all`, `keyring.refresh_if_stale`) es `async` porque usa el proveedor y la base.
- Sin router, sin rol, sin paginación. Las tablas crypto no son auditadas.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (usa `0003_crypto` de US-024).

### Models
- No aplica (usa `CryptoKey` de US-024).

### Service
- [ ] T1 · `api/src/app/core/crypto/registry.py`: `DataClassSpec` (dataclass congelada: `name`, `encrypt: bool`, `index_kind: Literal["generic","phone","email"] | None`, `sign: bool`, `value_type: Literal["str","date","json"]`, `columns: tuple[str, ...]` con la forma `esquema.tabla.columna`) y `REGISTRY: Mapping[str, DataClassSpec]` con las cinco clases de v0.1 (`member.document`, `member.phone`, `member.email` con índice; `member.birth_date` tipo `date`; `member.emergency_contact` tipo `json`); `get_spec(name)` lanza `CryptoError("data_class desconocida")`; `override_registry()` solo para tests — 2 h
- [ ] T2 · `api/src/app/core/crypto/blob.py`: `BlobParts` (dataclass: `version`, `key_id: UUID`, `alg`, `nonce: bytes`, `ciphertext: bytes`); `format_blob(key_id, alg, nonce, ct) -> str` con base64url sin relleno; `parse_blob(blob) -> BlobParts` que exige exactamente cinco partes, prefijo `apx1`, `key_id` UUID válido, `alg` en `SUPPORTED_ALGS = {"A256GCM"}`, base64url válido y nonce de 12 bytes; cualquier fallo lanza `CryptoError("blob_invalido")` sin incluir el blob en el mensaje — 2 h
- [ ] T3 · `api/src/app/core/crypto/aead.py`: `seal(dek, nonce, plaintext, aad) -> bytes` y `open_(dek, nonce, ct, aad) -> bytes` sobre `AESGCM`; `InvalidTag` → `CryptoError("decrypt_failed")` — 1 h
- [ ] T4 · `api/src/app/core/crypto/keyring.py`: `Keyring` en memoria con `dict[UUID, LoadedKey]` (`key_id`, `purpose`, `data_class`, `version`, `state`, material abierto en `bytearray` sin `__repr__`) y `active_for(purpose, data_class)`; `async load_all(session, provider)` desenvuelve `active` y `decrypt_only`; `async refresh_if_stale(session, provider)` compara `SELECT count(*), max(updated_at) FROM crypto.crypto_keys` con lo cargado y recarga solo lo nuevo; `async ensure_loaded(session, provider, key_id)` para un `key_id` desconocido. El gancho que llama `refresh_if_stale` al inicio de cada unidad de trabajo se cablea en US-029 (`core/wiring.py`) — 4 h
- [ ] T5 · `api/src/app/core/crypto/bootstrap.py`: `async ensure_keys(session, provider)` que por cada clase con `encrypt=True` sin llave `active` genera 32 bytes con `os.urandom`, los envuelve y ejecuta `INSERT ... ON CONFLICT (purpose, data_class) WHERE state = 'active' DO NOTHING` con `version = 1`, `provider = 'local'`, `created_by = SYSTEM_USER_ID`; luego vuelve a leer, de modo que dos procesos arrancando a la vez terminan con una sola llave. Llamado desde el lifespan de `main.py`, desde `worker/main.py` y desde los comandos de CLI que usan el bus — 3 h
- [ ] T6 · `api/src/app/core/crypto/bus.py`: `encrypt(data_class: str, plaintext: bytes, aad: bytes) -> str` (valida registro y `encrypt=True`, toma la llave `active`, nonce de 12 bytes de `os.urandom`, devuelve `format_blob`); `decrypt(blob: str, aad: bytes) -> bytes` (`parse_blob`, busca `key_id` en el keyring, rechaza `retired`, abre); `aad_for(record_id: UUID) -> bytes` = `str(record_id).encode("ascii")` (forma canónica en minúsculas con guiones, fijada en ADR-002); si el keyring no está cargado, `CryptoError("crypto_unavailable")`. Cada operación llama al punto de registro `oplog.record(...)` que implementa US-029. El bus no expone ningún método que devuelva una DEK — 3 h
- [ ] T7 · Sección "Formato del blob y AAD" en `docs/adr/ADR-002-criptografia.md` (borrador; el ADR completo es de US-119): cinco partes, base64url sin relleno, nonce de 12 bytes, AAD = UUID en texto canónico, prefijo `apxw1` de la envoltura; advertencia de irreversibilidad — 1 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T8 · `api/tests/crypto/test_blob.py`: `format_blob`/`parse_blob` ida y vuelta; 4 y 6 partes; prefijo `apx2`; `alg` `DES`; base64url inválido; nonce de 11 bytes; `key_id` no UUID; el mensaje de error no contiene el blob — 1,5 h
- [ ] T9 · `api/tests/crypto/test_registry.py`: las cinco clases existen con su `value_type` e `index_kind`; clase desconocida lanza `CryptoError("data_class desconocida")` — 0,5 h

### Tests de service con PostgreSQL
- [ ] T10 · `api/tests/crypto/test_bus_encrypt.py`: ida y vuelta para las cinco clases; dos cifrados del mismo texto difieren; el blob tiene cinco partes y contiene `A256GCM`; `aad` de otro registro lanza `CryptoError`; ciphertext alterado lanza `CryptoError`; `encrypt("member.foo", ...)` lanza `CryptoError("data_class desconocida")`; blob con llave `decrypt_only` descifra; blob con llave `retired` falla — 2,5 h
- [ ] T11 · `api/tests/crypto/test_bootstrap.py`: base sin llaves → una `active` por clase de cifrado; segundo arranque no crea más; dos `ensure_keys` concurrentes en dos sesiones dejan una sola por clase; `wrapped_material != dek` para cada llave; `created_by = SYSTEM_USER_ID`; una llave creada por otra sesión se carga con `refresh_if_stale` — 2,5 h
- [ ] T12 · `api/tests/crypto/test_bus_no_leak.py`: `caplog` tras cifrar, descifrar y fallar no contiene el texto en claro ni la DEK; `repr(keyring)` no contiene material — 1 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T13 · `test_banned_imports.py` (US-031) sigue verde: `cryptography` solo en `core/crypto/aead.py` y `local_provider.py` — 0,5 h

### Front
- No aplica.

### DevOps
- No aplica.

### Seguridad
- [ ] T14 · Revisión: nonce siempre aleatorio (nunca contador por proceso), DEK en `bytearray` sin getter, sin `DEK` en logs ni excepciones, `decrypt` no distingue en el mensaje entre AAD y alteración (evita oráculo), `retired` nunca descifra — 1,5 h

## Orden de ejecución
1. T8 y T9 (pruebas puras primero), luego T1 y T2
2. T3
3. T10, T11 y T12 escritas, luego T4, T5 y T6
4. T7
5. T13, T14

## Dependencias técnicas
- US-023 · KeyProvider y proveedor local: `wrap`/`unwrap`.
- US-024 · Tablas crypto: `crypto_keys` y su índice único parcial.
- US-029 · Bitácora crypto_ops: implementa `oplog.record` y el gancho que llama `refresh_if_stale`; mientras tanto `oplog.record` es un punto de extensión sin efecto.
- US-041 · Tabla de usuarios (`0004_auth`): crea la fila de `SYSTEM_USER_ID`; la constante se usa antes sin llave foránea.

## Endpoints
- Ninguno.

## Riesgos
- Formato del blob y codificación del AAD irreversibles con datos: cambiarlos exige recifrar todo el padrón — mitigación: se fijan en ADR-002 y en una prueba que compara un blob de referencia generado con una DEK fija; `CLAUDE.md` exige parar y preguntar antes de cambiarlos.
- API y worker arrancando a la vez sobre una base vacía crean dos DEK — mitigación: `ON CONFLICT ... DO NOTHING` sobre el índice parcial y relectura (T5, prueba concurrente en T11).
- Un proceso con keyring viejo tras una rotación hecha por CLI no conoce la llave nueva — mitigación: `refresh_if_stale` al inicio de cada unidad de trabajo y `ensure_loaded` por `key_id` desconocido (cableado en US-029).

## Estimación
- Backend: 16 h
- Front: 0 h
- Pruebas: 8,5 h
- DevOps / seguridad: 1,5 h
- **Total: 26 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/crypto/test_blob.py tests/crypto/test_registry.py tests/crypto/test_bus_encrypt.py tests/crypto/test_bootstrap.py tests/crypto/test_bus_no_leak.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] Tras arrancar el API dos veces: `SELECT data_class, count(*) FROM crypto.crypto_keys WHERE purpose = 'encrypt' AND state = 'active' GROUP BY 1` devuelve cinco filas con `count = 1`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.crypto --cov-fail-under=80`
