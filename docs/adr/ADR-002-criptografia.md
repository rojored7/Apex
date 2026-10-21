# ADR-002 · Criptografía: formatos irreversibles del bus

- Estado: **borrador** (lo completa US-119 en el Sprint 4B; estas secciones las fijan US-023, US-025 y US-026 en el Sprint 1).
- Alcance: todo lo que no se puede cambiar una vez haya datos reales cifrados o indexados.

## 1. Envoltura de la DEK (`apxw1`)

El proveedor local envuelve cada DEK con la KEK así: `b"apxw1" || nonce(12 bytes) || AES-256-GCM(kek, nonce, dek, aad = b"apx-dek-wrap")`. El prefijo autodescribe la envoltura; la columna `crypto_keys.algorithm` describe la llave envuelta (`A256GCM`, `HMAC-SHA256`, `Ed25519`), no la envoltura. La columna `wrap_algorithm` llega con EP-26. Con OpenBao (v0.2) la envoltura es lo que devuelva Transit.

La KEK son 32 bytes crudos en un archivo con modo 600 del volumen `keys`, fuera del repositorio y de la imagen. **Si se pierde la KEK se pierden todos los datos cifrados.**

## 2. Formato del blob y AAD

`apx1.<key_id>.<alg>.<nonce_b64url>.<ciphertext_b64url>`

- Exactamente cinco partes separadas por punto.
- `key_id`: UUID de `crypto_keys` en minúsculas con guiones.
- `alg`: en v0.1 solo `A256GCM`. El algoritmo va en el dato, no en el código.
- `nonce`: 12 bytes aleatorios por operación (`os.urandom`, nunca un contador por proceso), en base64url sin relleno.
- `ciphertext`: salida de AES-256-GCM (incluye la etiqueta de 16 bytes), en base64url sin relleno.
- AAD: el `id` del registro en texto canónico (`str(uuid).lower()`, ASCII). Un blob copiado a otro registro no abre.
- `decrypt` da el mismo error para AAD equivocado y para ciphertext alterado (sin oráculo). Una llave `decrypt_only` abre; una `retired` nunca.

## 3. Normalización del índice ciego (N-02)

El índice ciego es `HMAC-SHA-256(llave_index_de_la_clase, normalizado)` en hexadecimal (64 caracteres). La llave `index` es distinta por clase de dato para que documento y teléfono no se correlacionen. La normalización por tipo:

- `generic` (documento): NFKD, se quitan las marcas diacríticas (categoría Unicode `Mn`), minúsculas con `lower()` (no `casefold()`), se elimina todo espacio en blanco Unicode (incluye tabulador y espacio no separable), los puntos y los guiones (`-` y los tipográficos U+2010 a U+2015). `"1.020.304"`, `"1020-304"` y `" 1020304 "` dan el mismo índice; `"José Pérez"` → `"joseperez"`.
- `phone`: solo dígitos ASCII; se quita el `57` inicial únicamente si quedan 12 dígitos (código de país más número colombiano de 10). `"+57 300 123 4567"`, `"573001234567"` y `"(300) 123-4567"` → `"3001234567"`; `"6011234567"` se conserva.
- `email`: minúsculas y sin espacios en blanco; conserva puntos, guiones y tildes. `" Ana.Perez@Mail.com "` → `"ana.perez@mail.com"`.
- Un resultado vacío es un error (`empty_value`), nunca un índice.

**Advertencia:** cambiar cualquiera de estas reglas con datos reales invalida los índices guardados y exige reindexar toda la tabla con un job de `crypto_jobs`.

## 4. Pendiente para US-119

Serialización canónica de la auditoría (`core/audit.canonical`, ya fijada en su docstring), formato de la firma (`apx1.<key_id>.<alg>.<sig_b64url>`, US-027), política de rotación y el plan post-cuántico (EP-26).
