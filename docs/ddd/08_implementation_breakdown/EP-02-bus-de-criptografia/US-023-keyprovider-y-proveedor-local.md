# US-023 · KeyProvider y proveedor local de KEK — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-02-bus-de-criptografia/US-023-keyprovider-y-proveedor-local.md`
- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context / módulo:** Crypto (`api/src/app/core/crypto/provider.py`, `api/src/app/core/crypto/local_provider.py`, `api/src/app/cli.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

El puerto, sus seis métodos, el proveedor local y el comando `init-keys` están definidos por la historia, `CLAUDE.md` (bus, puntos 3 y 6) y DECISIONES N-03, que fija la envoltura con AES-256-GCM. No hay tablas ni endpoints. La única decisión de diseño que se toma aquí (métodos `async` para que OpenBao entre en v0.2 sin cambiar el contrato) no cambia el alcance.

## Resumen

Se crea el `Protocol` `KeyProvider` (`wrap`, `unwrap`, `sign`, `verify`, `rotate`, `key_info`), la implementación `LocalFileProvider` (KEK de 32 bytes en archivo 600 fuera del repo y llave Ed25519 de firma en archivo aparte), la fábrica por `CRYPTO_PROVIDER` y el comando `cli init-keys`, que crea ambos archivos sin sobrescribir nunca uno existente. El arranque del API falla con mensaje claro si la KEK falta o tiene permisos abiertos.

## Correcciones aplicadas por DECISIONES.md

- La historia acepta "AES Key Wrap si se documenta" → se usa solo AES-256-GCM con nonce aleatorio de 12 bytes y la KEK como llave: corregido por DECISIONES N-03 (aceptado tal cual el supuesto de la historia, se descarta la alternativa de Key Wrap).
- La historia supone que el algoritmo de envoltura queda en `crypto_keys.algorithm` → `algorithm` describe la llave envuelta (A256GCM, HMAC-SHA256, Ed25519), no la envoltura; la envoltura se autodescribe con el prefijo `apxw1` dentro de `wrapped_material` y se documenta en ADR-002. La columna `wrap_algorithm` la agrega EP-26 (US-199). Coherente con DECISIONES N-03 ("con OpenBao, lo que Transit devuelva").
- `init-keys` sin actor → el comando acepta `--as <email>` como todo CLI: corregido por DECISIONES N-15. Como `init-keys` no escribe en la base, el actor solo se anota en el log estructurado.

## Validación contra el dominio

- Aggregate consumidor: `CryptoKey` (02_domain_model 2.13); esta historia no lo persiste, solo provee `wrap`/`unwrap` para su `wrapped_material`.
- Invariante "el material en claro nunca se persiste": la KEK solo existe en el archivo del volumen `keys`; las DEK salen del proveedor solo envueltas.
- RN-13 (datos sensibles cifrados por clase de dato): habilitada por el envelope KEK → DEK.
- Eventos: ninguno emitido ni consumido. Funciones puras: ninguna (I/O y primitivas); se prueba el formato `apxw1` del envoltorio como función de parseo.
- Sin discrepancias con el modelo.

## Validación contra la arquitectura

- Dueño: `core/crypto/`. Es uno de los dos únicos lugares donde se permite importar `cryptography` (lint `banned-api`, `CLAUDE.md` bus punto 8).
- Puerto con intercambio real (`LocalFileProvider` hoy, `OpenBaoProvider` en US-134): cumple la regla de módulos 5 (interfaces solo donde hay algo que intercambiar).
- Los métodos del `Protocol` son `async def`: `OpenBaoProvider` usa `httpx.AsyncClient` (US-134) y un contrato síncrono obligaría a romperlo en v0.2. `LocalFileProvider` implementa con `async` triviales.
- `core/crypto` no importa nada de `app.modules` ni de `core/audit`; solo `core/config`.
- Sin router, sin rol, sin paginación, sin tablas auditadas.
- Llaves por volumen nombrado (`04_architecture_decision.md` sección 6), nunca en imagen ni en `.env`.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `api/src/app/core/crypto/errors.py`: `CryptoError(Exception)` con `code` (`kek_missing`, `kek_insecure_permissions`, `unwrap_failed`, `unknown_provider`, `unsupported`) y mensaje sin material; `__repr__` y `__str__` nunca incluyen bytes — 1 h
- [ ] T2 · `api/src/app/core/crypto/provider.py`: `KeyInfo` (dataclass congelada: `key_ref`, `algorithm`, `provider`, `version`, `created_at`) y `Protocol` `KeyProvider` con `async wrap(dek: bytes) -> bytes`, `async unwrap(wrapped: bytes) -> bytes`, `async sign(key_ref: str, data: bytes) -> bytes`, `async verify(key_ref: str, data: bytes, signature: bytes) -> bool`, `async rotate(key_ref: str) -> KeyInfo`, `async key_info(key_ref: str) -> KeyInfo`; validado con `mypy --strict` — 1,5 h
- [ ] T3 · `api/src/app/core/crypto/local_provider.py`: `LocalFileProvider(kek_path, signing_key_path)`; `wrap` = `b"apxw1" || nonce(12) || AESGCM(kek).encrypt(nonce, dek, b"apx-dek-wrap")`; `unwrap` valida prefijo y longitud y convierte `InvalidTag` en `CryptoError("unwrap_failed")`; `sign`/`verify` con `Ed25519PrivateKey` cargada del archivo (semilla cruda de 32 bytes); `verify` devuelve `False` ante `InvalidSignature`; `key_info` devuelve metadatos; `rotate` de la KEK local lanza `CryptoError("unsupported")` en v0.1 (la rotación de DEK es US-030, no del proveedor) — 4 h
- [ ] T4 · Función pura `parse_wrapped(wrapped: bytes) -> tuple[bytes, bytes]` (nonce, ciphertext) en `local_provider.py`, sin primitivas, para probar prefijo y longitudes — 0,5 h
- [ ] T5 · Comprobación de arranque `check_local_key_files(path)`: existe, es archivo regular, `stat.S_IMODE(st_mode) & 0o077 == 0`, tamaño exacto 32 bytes; mensajes "KEK no encontrada en <ruta>" y "permisos de la KEK inseguros" sin leer ni imprimir contenido — 1,5 h
- [ ] T6 · Fábrica `get_key_provider(settings) -> KeyProvider` en `provider.py`: `local` → `LocalFileProvider`; cualquier otro valor → `CryptoError("unknown_provider")` al arrancar (el valor `openbao` lo registra US-134) — 1 h
- [ ] T7 · `api/src/app/core/config.py`: campos `CRYPTO_PROVIDER: Literal["local"]` (ampliable), `CRYPTO_LOCAL_KEK_PATH` (por defecto `/run/apex/keys/kek.bin`), `CRYPTO_LOCAL_SIGNING_KEY_PATH` (por defecto `/run/apex/keys/sign-ed25519.key`) y entradas en `.env.example` — 1 h
- [ ] T8 · `api/src/app/cli.py`: comando `init-keys [--as <email>]` que crea KEK (32 bytes de `os.urandom`) y llave Ed25519 con `os.open(path, O_CREAT | O_EXCL | O_WRONLY, 0o600)`; si cualquiera existe, código 1 y "la KEK ya existe" (o "la llave de firma ya existe") sin tocar nada; crea el directorio con 0o700 si falta. Deja el gancho `--data-class` para US-140 sin implementarlo — 2,5 h
- [ ] T9 · Gancho de arranque en `api/src/app/main.py` (lifespan): instancia el proveedor con la fábrica y ejecuta T5 antes de abrir las llaves; si falla, el proceso termina con código distinto de 0 y log JSON sin contenido de la KEK — 1 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T10 · `api/tests/crypto/test_local_provider.py::test_parse_wrapped_*`: prefijo correcto, prefijo distinto, longitud corta, longitud exacta — 0,5 h

### Tests de service con PostgreSQL
- [ ] T11 · `api/tests/crypto/test_local_provider.py` (sin base; directorio temporal con `tmp_path`): ida y vuelta `unwrap(wrap(dek)) == dek` con DEK aleatoria de 32 bytes; un byte alterado lanza `CryptoError`; dos `wrap` de la misma DEK difieren; `sign`/`verify` verdadero y falso con datos alterados — 2 h
- [ ] T12 · `api/tests/crypto/test_init_keys.py`: `init-keys` crea KEK de 32 bytes y llave de firma con modo `0o600` (`os.stat`); segunda ejecución termina con código 1 y el `sha256` del archivo (calculado en el test con `hashlib`, permitido en tests) no cambia; directorio inexistente se crea — 1,5 h
- [ ] T13 · `api/tests/crypto/test_provider_startup.py`: KEK ausente y KEK con 0o644 hacen fallar el arranque con el mensaje exacto; `CRYPTO_PROVIDER=foo` falla; `caplog`/`capsys` no contienen los bytes de la KEK ni su base64 — 1,5 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T14 · `api/tests/architecture/test_banned_imports.py` (lo crea US-031) debe seguir verde: `cryptography` solo aparece en `core/crypto/local_provider.py` — 0,5 h

### Front
- No aplica.

### DevOps
- [ ] T15 · `.gitignore` y `.dockerignore`: `keys/`, `*.kek`, `kek.bin`, `sign-ed25519.key`; `infra/compose.yml`: volumen nombrado `keys` montado en `/run/apex/keys` para `api` y `worker` (de US-005), dueño UID `apex`; README con `docker compose run --rm api python -m app.cli init-keys` y la advertencia de respaldo (US-116) — 1 h

### Seguridad
- [ ] T16 · Revisión: la KEK nunca sale de `LocalFileProvider` (sin getter público), ningún log ni excepción incluye bytes, permisos 600 verificados en arranque, WSL2/NTFS no se usa para el volumen (riesgo de permisos), `init-keys` no acepta la KEK por argumento — 1 h

## Orden de ejecución
1. T1, T2 (error y contrato)
2. T10 y T4 (prueba pura antes de la implementación)
3. T11, luego T3
4. T7, T13, luego T5, T6 y T9
5. T12, luego T8
6. T14, T15, T16

## Dependencias técnicas
- US-011 · Configuración desde .env: `Settings` donde se agregan las rutas y `CRYPTO_PROVIDER`.
- US-005 · Dockerfile del api y Compose: volumen nombrado `keys` y usuario no root.
- US-002 · Regla `banned-api` de ruff: debe permitir `cryptography` en `core/crypto`.

## Endpoints
- Ninguno.

## Riesgos
- Perder la KEK equivale a perder todos los datos cifrados: impacto total sobre RN-13 — mitigación: advertencia en README y en la salida de `init-keys`; respaldo fuera del servidor con `cli export-kek` (US-116).
- Permisos 600 no se respetan en NTFS bajo WSL2: el arranque fallaría o, peor, aceptaría un archivo legible — mitigación: volumen nombrado de Docker, nunca bind mount desde Windows; la comprobación T5 corre siempre.
- Contrato `async` del puerto: si se escribiera síncrono, OpenBao (US-134) rompería el contrato — mitigación: `async` desde v0.1 y prueba de contrato común que US-134 reutiliza.

## Estimación
- Backend: 14 h
- Front: 0 h
- Pruebas: 6 h
- DevOps / seguridad: 2 h
- **Total: 22 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/crypto/test_local_provider.py tests/crypto/test_init_keys.py tests/crypto/test_provider_startup.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `docker compose -f infra/compose.yml run --rm api python -m app.cli init-keys` crea `/run/apex/keys/kek.bin` con `stat -c %a` = `600` y tamaño 32; una segunda ejecución sale con código 1
- [ ] `git check-ignore keys/kek.bin` confirma que la KEK está ignorada
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.crypto --cov-fail-under=80`
