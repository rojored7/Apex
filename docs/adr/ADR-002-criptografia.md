# ADR-002 · Criptografía: formatos irreversibles del bus

## Estado

Aceptado. Los formatos de las secciones 1 a 3 de la decisión están vigentes desde el Sprint 1 (US-023, US-025, US-026); el respaldo de la KEK, la rotación y el retiro desde el Sprint 4B. Todo lo que sigue no se puede cambiar una vez haya datos reales cifrados o indexados: cambiarlo exige detenerse y preguntar.

## Contexto

APEX guarda datos personales sensibles de los socios (documento, teléfono, correo, contacto de emergencia, fecha de nacimiento; Ley 1581) y una bitácora de auditoría inmutable. Una base filtrada o un respaldo robado no deben revelar esos datos, y la búsqueda por documento, teléfono o correo debe seguir funcionando sin descifrar toda la tabla. Hay un solo servidor y un equipo pequeño: la solución debe ser simple de operar, sin perder la posibilidad de pasar a un KMS (OpenBao en v0.2) ni a algoritmos post-cuánticos (EP-26) sin reescribir los datos.

## Decisión

Única puerta: `core/crypto/bus.py` (`encrypt`, `decrypt`, `blind_index`, `sign`, `verify`, `digest`). El que llama pasa un `data_class` (por ejemplo `member.document`), que decide la llave; nunca elige llave ni algoritmo. Envelope: KEK en el `KeyProvider`; una DEK por `data_class`, envuelta en `crypto.crypto_keys` y abierta en memoria al arrancar.

### 1. Envoltura de la DEK (`apxw1`)

El proveedor local envuelve cada DEK con la KEK así: `b"apxw1" || nonce(12 bytes) || AES-256-GCM(kek, nonce, dek, aad = b"apx-dek-wrap")`. El prefijo autodescribe la envoltura; la columna `crypto_keys.algorithm` describe la llave envuelta (`A256GCM`, `HMAC-SHA256`, `Ed25519`), no la envoltura. Con OpenBao (v0.2) la envoltura es lo que devuelva Transit.

La KEK son 32 bytes crudos en un archivo con modo 600 del volumen `keys`, fuera del repositorio y de la imagen. **Si se pierde la KEK se pierden todos los datos cifrados.**

### 2. Formato del blob y AAD

`apx1.<key_id>.<alg>.<nonce_b64url>.<ciphertext_b64url>`

- Exactamente cinco partes separadas por punto.
- `key_id`: UUID de `crypto_keys` en minúsculas con guiones.
- `alg`: en v0.1 solo `A256GCM`. El algoritmo va en el dato, no en el código.
- `nonce`: 12 bytes aleatorios por operación (`os.urandom`, nunca un contador por proceso), en base64url sin relleno.
- `ciphertext`: salida de AES-256-GCM (incluye la etiqueta de 16 bytes), en base64url sin relleno.
- AAD: el `id` del registro en texto canónico (`str(uuid).lower()`, ASCII). Un blob copiado a otro registro no abre.
- `decrypt` da el mismo error para AAD equivocado y para ciphertext alterado (sin oráculo). Una llave `decrypt_only` abre; una `retired` nunca.
- La firma usa el formato de cuatro partes `apx1.<key_id>.<alg>.<sig_b64url>` (`Ed25519` en v0.1; `ML-DSA-65` queda reservado).

### 3. Normalización del índice ciego (N-02, `normalize_for_index`)

El índice ciego es `HMAC-SHA-256(llave_index_de_la_clase, normalizado)` en hexadecimal (64 caracteres), guardado en la columna `<campo>_idx`. La llave `index` es distinta por clase de dato para que documento y teléfono no se correlacionen. La normalización por tipo:

- `generic` (documento): NFKD, se quitan las marcas diacríticas (categoría Unicode `Mn`), minúsculas con `lower()` (no `casefold()`), se elimina todo espacio en blanco Unicode, los puntos y los guiones (`-` y los tipográficos U+2010 a U+2015). `"1.020-304"`, `"1020-304"` y `" 1020304 "` dan `1020304`; `"José Pérez"` da `"joseperez"`.
- `phone`: solo dígitos ASCII; se quita el `57` inicial únicamente si quedan 12 dígitos. `"+57 300 123 4567"`, `"573001234567"` y `"(300) 123-4567"` dan `3001234567`; `"6011234567"` se conserva.
- `email`: minúsculas y sin espacios en blanco; conserva puntos, guiones y tildes. `" Ana.Perez@Mail.com "` da `"ana.perez@mail.com"`.
- Un resultado vacío es un error (`empty_value`), nunca un índice.
- Ningún fragmento de un dato cifrado se guarda en claro: no existen columnas `*_hint`; el enmascarado se calcula en memoria al leer.

**Advertencia:** cambiar cualquiera de estas reglas con datos reales invalida los índices guardados y exige reindexar toda la tabla.

### 4. Imports prohibidos

Fuera de `core/crypto/` y `core/security.py` está prohibido importar `cryptography`, `oqs`, `hashlib`, `hmac`, `jwt` y `argon2` (regla `flake8-tidy-imports.banned-api` de `pyproject.toml`, más una prueba de arquitectura). El SHA-256 de la cadena de auditoría pasa por `core/crypto/digest.py`.

### 5. Respaldo de la KEK (`archive.py`, `kek.backup`)

La KEK se respalda cifrada con `age -p` (frase de paso; la pide `age` por la terminal y APEX no la ve): `export-kek --out kek.backup --as <correo>` escribe `kek.backup` con modo 600 y `O_EXCL`, y deja una fila de `crypto_ops` y una entrada de auditoría. `core/crypto/archive.py` es la única puerta de la KEK fuera del proveedor: lanza `age` con `Popen` por lista, sin shell y con entorno vacío; la KEK viaja por el `stdin` del hijo, nunca por `argv`, entorno ni archivos temporales. `verify-kek-backup` abre el respaldo en memoria y prueba que cada DEK `active` o `decrypt_only` se abre con ella (`kek_backup.py`); `restore-kek` lo descifra hacia un archivo nuevo. El respaldo de la KEK se guarda en dos copias fuera del servidor y separado del respaldo de la base: quien tiene ambos lo abre todo.

### 6. Rotación y retiro

`rotate-key` pasa la llave `active` a `decrypt_only`, crea la versión siguiente y recifra por lotes de 500 con SQL de Core (`updated_at` intacto), reanudable. `retire-key` es el único camino a `retired`: exige cero filas de negocio con esa llave, el conteo confirmado de blobs de `audit.audit_log` (los blobs de auditoría no se recifran: es inmutable) y un respaldo reciente de la KEK y del manifiesto. La rotación acota el uso futuro; no revoca respaldos ni protege ante una KEK comprometida (eso es de v0.2 con OpenBao). Guía: `docs/operacion/rotar-llave.md`.

### 1 bis. Proveedor por fila y envoltura `vault:v<n>:` (Sprint 5, S5-B1)

Cada fila de `crypto_keys` se abre con el proveedor que nombra su columna `provider` (`local` u `openbao`); el keyring resuelve el proveedor al pedirlo (`Keyring.provider_for`), de modo que `local` solo se construye si hay filas `encrypt|index` `local`. Las llaves nuevas nacen en el proveedor de creaciÃ³n (`CRYPTO_PROVIDER`). Con OpenBao la envoltura es el texto cifrado de Transit, `vault:v<n>:<base64>` (la versiÃ³n `n` de la KEK va en el dato, como el prefijo `apxw1` en el proveedor local), con `associated_data` = base64(`apx-dek-wrap`). El prefijo y la columna deben coincidir: si no, `unwrap_failed`. `OpenBaoProvider` habla con httpx, no sigue redirecciones ni usa proxies del entorno, no reintenta, y lee el token solo de `OPENBAO_TOKEN_FILE` (permisos 600, hasta 256 bytes).

## Alternativas descartadas

- **Cifrado de disco o de columna con `pgcrypto`:** la llave viviría en la base o en consultas SQL; un volcado la arrastra y los permisos de la base bastarían para leer.
- **Una sola llave para todo:** una filtración de la llave abre todas las clases y el índice ciego correlaciona documento con teléfono.
- **Índice ciego sin normalizar o con `casefold()`:** `1.020-304` y `1020304` serían personas distintas y la búsqueda fallaría.
- **Formato propio para el respaldo de la KEK:** `age -p` ya está auditado y trae autenticación; inventar un formato añade riesgo sin beneficio.
- **KMS externo desde v0.1:** un servicio más que operar en un servidor; se pasa a OpenBao en v0.2 sin cambiar el formato del blob porque el algoritmo y la llave viajan en el dato.

## Consecuencias

- El blob se descifra solo con la llave exacta y el `id` del registro: copiar un blob a otra fila lo invalida.
- Perder la KEK o su respaldo es perder los datos cifrados; el respaldo de la KEK es una obligación operativa, no opcional.
- Cambiar la normalización, el formato del blob o la envoltura exige una migración de datos con reindexado o recifrado, planificada y con respaldo previo.
- Los blobs de auditoría quedan atados a la llave con que se escribieron: una llave con filas de auditoría no pasa a `retired` sin confirmar el conteo.
- Añadir un algoritmo (post-cuántico) no rompe lo escrito: el campo `alg` lo identifica.

## Cómo se verifica

- `api/tests/crypto/test_blob.py` fija el formato `apx1` de cinco partes y `api/tests/crypto/test_bus_encrypt.py` el ida y vuelta con AAD.
- `api/tests/crypto/test_normalize.py` y `api/tests/crypto/test_blind_index.py` fijan la normalización (`1.020-304` a `1020304`, `+57 300 123 4567` a `3001234567`).
- `api/tests/crypto/test_local_provider.py` fija la envoltura `apxw1` y `api/tests/crypto/test_signature_format.py` el formato de la firma.
- `api/tests/crypto/test_archive_kek.py`, `api/tests/crypto/test_kek_backup.py` y `api/tests/cli/test_export_kek.py` prueban el respaldo con `age -p`; `api/tests/crypto/test_rotate.py` y `api/tests/crypto/test_retire_key.py` la rotación y el retiro.
- `api/tests/architecture/test_banned_imports.py` y `api/tests/architecture/test_crypto_bus_importers.py` vigilan los imports prohibidos y la puerta única.
- Cambiar cualquier formato de este documento exige detenerse y preguntar.
