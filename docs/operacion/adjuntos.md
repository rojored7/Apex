# Adjuntos

Alcance: almacén de archivos adjuntos del api (volumen `uploads` o S3) y su revisión. Decisiones: ADR-007 y `docs/ddd/DECISIONES.md`, «Sprint 6». La ruta para subir (la foto del socio, C2) y listar existe; la descarga llega con S6-C3 y S6-C4. Esta guía cubre: tabla, almacenamiento, cifrado, recifrado y `attachments-check`.

## Qué se guarda y dónde

- **Metadatos** en `attachments.attachments` (base de datos): dueño (`owner_table`, solo `members`, y `owner_id`), `kind`, tipo, tamaño, quién lo subió, `sensitive`, `key_id` y el nombre del objeto (`filename_random`). La tabla es de solo inserción: no hay `DELETE` ni `TRUNCATE`, y el `UPDATE` solo admite `key_id` y `updated_at` (triggers `ENABLE ALWAYS` de la migración `0023`).
- **Contenido** en el almacenamiento de objetos, nunca en la base: por omisión `UPLOADS_DIR/attachments` (volumen `uploads`), un archivo por nombre aleatorio de 32 hexadecimales en minúscula. El nombre original del archivo no se guarda.
- **Sin llaves foráneas** hacia otros esquemas: `owner_id` y `key_id` son referencias lógicas.

## Foto del socio (S6-C2, US-148)

- **Subir.** `POST /members/{id}/attachments?kind=photo|consent|other` con el archivo como cuerpo crudo (sin formulario). Admin y coach suben `photo`; `consent` y `other` solo el admin (el coach recibe 403 sin que se lea el cuerpo). Un socio dado de baja no admite subidas (404 `member_not_found`). Tope de 5.242.880 bytes (413 `file_too_large` también si el `Content-Length` declarado lo supera, sin leer), solo JPEG o PNG para la foto, 10 subidas por minuto por usuario (cubeta `attachments-upload`, 429).
- **Reemplazo.** La foto nueva pasa a ser la vigente (la más reciente por fecha); la anterior no se borra y sigue en el listado.
- **Listar.** `GET /members/{id}/attachments` (admin y coach, paginado) incluye a los socios dados de baja. Cada adjunto trae metadatos, nunca el nombre del archivo.
- **`photo_attachment_id`.** La ficha (`GET /members/{id}`) y cada fila de `GET /members` traen el id de la foto vigente o `null`, con una sola consulta por página.

## La autorización subida fija la autorización de datos (S6-C3, US-149)

- Subir `kind=consent` a un socio con `data_consent_at` nulo guarda el adjunto y, en la misma petición, fija `data_consent_at` con el reloj del servidor y `data_consent_version` con la versión vigente de la política; deja una fila `update` en `audit_log` con el antes y el después. Con autorización previa no cambia nada (ni fecha, ni versión, ni fila). `photo` y `other` nunca tocan el consentimiento.
- Si el corte `consent_required_from` ya llegó y no hay política publicada, la subida responde 409 `privacy_version_missing` **antes de leer el cuerpo**: no se guarda adjunto ni objeto. Publica la política (`PATCH /settings/privacy`) y repite. Orden de los errores: socio 404, rol 403, 409, `Content-Length` 413, cubeta 429, cuerpo.

## Descargar (S6-C4, US-150)

- **Ruta.** `GET /attachments/{id}` (admin y coach). El admin baja todo; el coach solo `photo` (403 `forbidden` en `consent` y `other`, sin descifrar y sin dejar fila). Socio: 403; sin sesión: 401; id mal formado: 422.
- **Orden de los errores.** Fila (404 `attachment_not_found`), rol (403), cubeta (429), cupo (503 `busy` con `Retry-After: 1`), descifrado (503 `crypto_unavailable` con `Retry-After: 30` si el custodio está sellado), fila de auditoría confirmada y por último el cuerpo.
- **Auditoría.** Un sensible deja UNA fila `download` en `audit_log` por descarga (con el dueño como socio afectado) y un `decrypt` en `crypto_ops`; ambos quedan confirmados antes del primer byte. Con el custodio sellado no queda ninguna. La foto no deja fila por vista ni pasa por el bus de cifrado (ADR-007); se sirve por streaming desde el disco, también con el custodio sellado.
- **Cubetas por usuario.** Sensibles: `attachments-download` (30 por minuto) y `attachments-download-hour` (200 por hora). Foto: `attachments-photo` (600 por minuto). Son contadores distintos y se cobran antes de descifrar.
- **Cabeceras.** `Content-Disposition: attachment; filename=adjunto-<8 hex>.<ext>` (nunca el nombre del objeto ni el id completo), `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` y `Content-Security-Policy: default-src 'none'; sandbox`. Un PDF con JavaScript se sirve igual, como adjunto.
- **Huérfano.** Si la fila existe y el objeto no, la respuesta es 404 `attachment_not_found` (foto y sensible) con una línea `WARNING` sin el nombre del archivo; `attachments-check` lo lista. Un fallo del disco a mitad de la foto corta la respuesta con otra línea `WARNING`.
- **Socio de baja.** Sus adjuntos siguen descargables (N-20).
- **Memoria.** Descargar un sensible de 5 MiB llega a unos 34 MiB de pico (S6-D115); por eso solo caben cuatro a la vez.

## Tipos, tamaños y bytes mágicos

- Tipos admitidos: JPEG (`FF D8 FF`), PNG (`89 50 4E 47 0D 0A 1A 0A`) y PDF (`%PDF-`). El tipo lo deciden **solo los primeros bytes**: ni la extensión ni el `Content-Type` cuentan. Un ejecutable (ELF, PE) con nombre `.jpg` se rechaza con 422 `unsupported_type`.
- `kind`: `photo` (solo JPEG o PNG; no sensible), `consent` (autorización de tratamiento de datos) y `other`, estos dos con imagen o PDF y siempre sensibles. Lo sensible lo decide el servidor.
- Tamaño: de 1 a 5.242.880 bytes. El lector corta al llegar al byte 5.242.881 sin seguir leyendo (413 `file_too_large`) y, si el cliente deja de enviar más de 30 s en total, responde 408 `upload_timeout`. Nunca se usa `tempfile` ni `multipart`: el cuerpo se acumula en memoria acotada.

## Cifrado en reposo

- Los sensibles (`consent`, `other`) se cifran con el bus (`attachment.sensitive`, AES-256-GCM) con `aad` = id de la fila antes de tocar el disco. El objeto guardado es el blob de texto `apx1.<key_id>.A256GCM.<nonce>.<texto cifrado>`; el contenido en claro no aparece en el volumen. Un objeto copiado sobre otra fila no se abre (el `aad` no coincide).
- La foto va **sin cifrar** en el volumen (modo 600, nombre aleatorio, solo el api con rol): es el residual que acepta ADR-007.
- La DEK de la clase la crea el arranque del api (`ensure_keys`) o, a mano, `docker compose --profile tools run --rm tools init-keys --data-class attachment.sensitive --as <correo>` (idempotente: si ya existe dice «ya existe»; audita un `insert` sobre `crypto.crypto_keys` sin material).
- Descargar un sensible: se descifra, se escribe la fila `download` en `audit_log`, se confirma y solo entonces se entrega el cuerpo. Con el custodio de llaves sellado la descarga da 503 `crypto_unavailable` y **no** deja fila `download`. Como mucho cuatro operaciones sensibles (subir o abrir) corren a la vez; la quinta recibe 503 `busy` con `Retry-After: 1`.

## Rotar la llave de los adjuntos

`tools rotate-key attachment.sensitive --reason "..." --as <correo>` (o la pantalla Llaves) crea una DEK nueva y recifra los objetos de a 10 (S6-D111): descifra con la llave anterior, cifra con la activa, **reemplaza el objeto de forma atómica** (misma clave de archivo) y después actualiza `key_id`. Si el proceso se corta entre el objeto y la base, el siguiente lote lo recifra otra vez sin error. La llave anterior queda `decrypt_only`; `retire-key` se niega mientras queden objetos con ella (cuenta por `key_id`, sin leer archivos).

## Huérfanos: `attachments-check`

`docker compose --profile tools run --rm tools attachments-check --as <correo>` (solo lectura; con `ENV=production` `--as` es obligatorio). Imprime:

```
attachments-check: filas sin objeto: N
attachments-check: objetos sin fila: N
  fila sin objeto: <id de la fila>
  objeto sin fila: <nombre hexadecimal>
```

Además compara, por cada fila sensible cuyo objeto existe, el `key_id` de la fila con el de la cabecera del blob en reposo (`apx1.<key_id>.…`; lee solo los primeros 64 bytes del objeto y no descifra nada). Si alguna difiere (o el objeto no empieza como un blob `apx1`), agrega una tercera categoría, solo cuando hay casos:

```
attachments-check: key_id distinto del blob: N
  key_id distinto del blob: <id de la fila>
```

Sin discrepancias la salida no cambia. El motivo de la comprobación: `attachments.key_id` no tiene llave foránea a `crypto.crypto_keys` y `apex_api` puede fijarlo; `count_pending`, `finish_rotation` y `retire-key` confían en esa columna, y una fila manipulada ocultaría un blob cifrado con la llave que se va a retirar. Repararlo es decisión de la persona (la columna solo admite `UPDATE` de `key_id` y `updated_at`).

Sale 0 sin hallazgos y 1 con alguno (huérfanos o `key_id` distinto del blob). Nunca imprime el `filename_random` de una fila (con S3 es la clave del objeto) ni borra, repara o crea nada, ni siquiera la carpeta del volumen. Las causas habituales: una subida cortada entre guardar el objeto y confirmar la fila (el servicio borra el objeto al fallar el `flush`, pero un corte del proceso puede dejarlo), una restauración parcial del volumen, o el `downgrade` de `0023` (RUNBOOK §6). Qué hacer con cada huérfano es decisión de la persona; no hay comando de reparación.

## S3 (apagado en v0.3)

El adaptador `S3CompatibleStorage` existe y se prueba con respuestas simuladas, pero **no se usa** salvo que el titular lo pida. `STORAGE_PROVIDER=s3` exige las cinco variables `S3_*`, `https` (salvo `ENV=dev`) y, con `ENV=production`, `S3_ENABLE_PRODUCTION=true`; sin ellas el api no arranca y el error nombra la variable, nunca su valor. El cliente usa solo las credenciales de `Settings` (nunca `AWS_*` ni `~/.aws`), `verify=True`, sin proxies del entorno y tres reintentos. `boto3` es opcional: la imagen del api no lo instala; para probarlo hay que construir con el extra `s3` (`uv sync --extra s3`), y sin él el mensaje es «instale el extra s3».

## Supresión a petición (Ley 1581): procedimiento manual

En v0.3 no hay comando de borrado (la tabla es de solo inserción). Ante una solicitud de supresión:

1. Guardar la evidencia de la solicitud (quién, cuándo, qué socio).
2. `attachments-check --as <correo>` antes, para tener la línea base.
3. Borrar el **objeto** del volumen `uploads/attachments` desde el contenedor `tools` (el nombre sale de la base: `SELECT filename_random FROM attachments.attachments WHERE id = '<id>'` con el rol de consulta). La fila **no** se toca: el trigger prohíbe `DELETE` y el `UPDATE` solo admite `key_id`.
4. Dejar la constancia con una fila de auditoría `delete` sobre `attachments.attachments` desde `tools` con `--as`.
5. `attachments-check --as <correo>` después: la fila aparecerá como «fila sin objeto», que es lo esperado. Desde ese momento el comando sale con 1 por ese huérfano (y por cada supresión posterior) hasta que exista `attachments purge` (v0.4): la constancia del paso 4 es el registro que explica cada uno.

El respaldo conserva el archivo hasta que rote. **Residual con dueño:** el comando `attachments purge`, con la columna `purged_at`, es del titular del tratamiento y llega en v0.4.

## Respaldo

Los adjuntos viajan en `<nombre>-uploads.tar.age` junto con el resto del volumen `uploads` (`respaldo-y-restauracion.md`). Para abrir un documento sensible restaurado hacen falta la base (que guarda la DEK envuelta) y la KEK del mismo respaldo.

## Variables

- `STORAGE_PROVIDER`: `local` (por defecto) o `s3` (apagado en v0.3). Va en `.env`.
- `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`: van en `.env`. Con `s3` las cinco variables `S3_*` son obligatorias; el endpoint es `https` salvo `ENV=dev`.
- `S3_SECRET_ACCESS_KEY`: va en `.env.ops` y solo la recibe el api. Nunca la pongas en `.env`: ese archivo lo leen `worker` y `tools` por `env_file` y heredarían el secreto (la prueba `test_env_example` prohíbe la clave en `.env.example` y `test_env_isolation.sh` la detecta en un stack vivo). El endpoint es solo esquema y host: una URL con usuario, contraseña, consulta o fragmento se rechaza al arrancar.
- `S3_ENABLE_PRODUCTION`: `false` por defecto. Con `s3` y `ENV=production` debe ser `true` o el api no arranca.
- Topes por usuario (en `.env`): `USER_ATTACHMENTS_UPLOAD_LIMIT_PER_MIN` (10), `USER_ATTACHMENTS_PHOTO_LIMIT_PER_MIN` (600), `USER_ATTACHMENTS_DOWNLOAD_LIMIT_PER_MIN` (30) y `USER_ATTACHMENTS_DOWNLOAD_LIMIT_PER_HOUR` (200).
