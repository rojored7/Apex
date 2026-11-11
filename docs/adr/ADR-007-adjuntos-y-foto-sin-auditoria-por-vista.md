# ADR-007 · Adjuntos y foto sin auditoría por vista

## Estado

Aceptado el 2026-11-11 (Sprint 6, v0.3; S6-D24, S6-D37, S6-D38, S6-D45, S6-D49, S6-D53, S6-D59 y S6-D76). Cambiar qué descargas se auditan, cómo se cifran los adjuntos sensibles o quitar el tope de tamaño exige detenerse y preguntar: el formato del blob cifrado en disco es irreversible con datos reales (ADR-002).

## Contexto

La v0.3 permite adjuntar archivos a un socio: la foto de perfil, la autorización de tratamiento de datos firmada y otros documentos. La Ley 1581 de 2012 y su Decreto 1377 de 2013 tratan los documentos de identidad y las autorizaciones como datos personales; la foto, además, identifica a la persona. Hay dos fuerzas opuestas: toda lectura de un dato sensible debe dejar rastro, y una miniatura en la lista de socios se pide una vez por fila y por render.

## Decisión

**Almacenamiento.** Los archivos viven fuera de la base, en el volumen `uploads` (`LocalDiskStorage`, raíz `UPLOADS_DIR/attachments`), con nombre aleatorio de 128 bits (32 hexadecimales; el nombre original no se guarda), escritura atómica y modo 600. `STORAGE_PROVIDER` elige `local` (por defecto) o `s3`. El adaptador S3 existe pero está **apagado**: con `ENV=production` exige `S3_ENABLE_PRODUCTION=true`, credenciales explícitas, `https`, verificación de certificado y reintentos acotados; `boto3` es una dependencia opcional (grupo `s3`) que la imagen del api no instala. La fila (`attachments.attachments`) es append-only: no hay `DELETE` y el `UPDATE` solo admite `key_id` y `updated_at`.

**Subida.** `POST /members/{id}/attachments?kind=photo|consent|other` con el archivo como cuerpo crudo: `kind` y el socio se validan antes de leer un solo byte, la lectura se corta en 5.242.880 bytes (413 `file_too_large`), el tipo lo deciden los bytes mágicos (JPEG, PNG o PDF) y nunca el `Content-Type` ni la extensión. El rol decide por `kind`: el coach solo sube y ve fotos; `consent` y `other` son del administrador.

**Cifrado por el bus.** `consent` y `other` son sensibles: el servidor lo decide (el cliente no envía `sensitive`) y el archivo se cifra con el bus (`attachment.sensitive`, AES-256-GCM con `aad` = id de la fila) antes de tocar el disco; el contenido en reposo es un blob `apx1.` y la DEK sale del keyring. El descifrado ocurre en una sola puerta (`modules/attachments/files.py`), con semáforo global de 4 operaciones simultáneas.

**Descarga auditada.** `GET /attachments/{id}` descifra, **escribe una fila `download` en `audit_log` y la confirma antes de transmitir** el cuerpo, de modo que una descarga cortada queda registrada completa; los sensibles dejan además `crypto_ops(decrypt)`. Cabeceras: `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Content-Disposition: attachment` y una CSP que no ejecuta nada. No existe un evento `SensitiveFieldRevealed`: la fila `download` es la única señal.

**La foto no se audita por vista.** Cada render de la lista de socios o de la ficha pediría la foto; una fila de auditoría por miniatura llenaría `audit_log` de ruido, sin contenido de información (igual que el nombre en claro no se audita al listar). Por eso `kind = photo` se sirve sin fila `download`, con una cubeta de límite propia (`attachments-photo`, 600/min por usuario), `no-store` y el archivo mantenido solo en memoria del navegador (`blob:`). La **subida** de la foto sí se audita (fila `insert`). Es un desvío consciente de «toda descarga se audita» (N-08), limitado a la foto.

**Foto sin cifrar en disco.** La foto no es sensible en el modelo y se guarda sin cifrar en el volumen. Es un dato personal bajo la Ley 1581: su protección en reposo es el modo 600 del archivo, el nombre aleatorio, el acceso solo por el api con rol y el cifrado del volumen y del respaldo del operador. Es el riesgo residual que este ADR acepta.

**Retención y supresión.** En v0.3 no hay borrado: ni comando ni ruta. Ante una solicitud de supresión bajo la Ley 1581, el operador aplica el procedimiento manual de `docs/operacion/adjuntos.md` (guardar la evidencia de la solicitud, `attachments-check` antes y después, borrar el objeto del volumen y dejar la constancia con una fila de auditoría); la fila de la base se conserva y el respaldo guarda el archivo hasta que rote. Dueño del residual: el titular del tratamiento (el responsable del gimnasio). Fecha: el comando `attachments purge`, con la columna `purged_at`, se entrega en v0.4.

## Alternativas descartadas

- **Auditar cada vista de la foto:** convierte `audit_log` en un registro de renders; el dato que aporta (que alguien con rol vio una foto) no compensa el ruido ni el costo de la cadena.
- **Cifrar también la foto:** exigiría descifrar en cada miniatura (hasta 12 MiB de memoria por petición) con el semáforo de 4; se descarta mientras el tope de pico mande.
- **Multipart con `python-multipart`:** el archivo cae en un `SpooledTemporaryFile` sin tope y el análisis ocurre antes de poder validar `kind`; el cuerpo crudo acotado cierra ambos problemas y no añade dependencia.
- **Guardar los archivos en la base (`bytea`):** infla el respaldo y la memoria del api, y mezcla datos binarios con la cadena de auditoría.
- **S3 encendido por defecto:** añade un tercero y credenciales al servidor sin que el titular lo haya pedido.
- **Borrado en v0.3:** exigiría relajar el trigger append-only de la fila y diseñar la política de retención; se difiere con dueño y fecha.

## Consecuencias

- Quien tenga acceso al volumen `uploads` puede ver las fotos, no los documentos: los sensibles son ilegibles sin la DEK de `attachment.sensitive`.
- Rotar la clase `attachment.sensitive` recifra los objetos del disco (reemplazo atómico con la misma clave de archivo) y actualiza `key_id`; un corte entre ambos pasos es idempotente.
- Un archivo huérfano (objeto sin fila, o fila sin objeto) se detecta con `attachments-check`, no se repara solo.
- La CSP de la aplicación admite `blob:` en `img-src` para mostrar la foto descargada con el token.
- Una solicitud de supresión depende de un procedimiento manual del operador hasta v0.4.

## Cómo se verifica

- `api/tests/architecture/test_adr_docs.py` comprueba el formato de este documento.
- `api/tests/core/test_chain_hash_vector.py` fija la serialización de la cadena en la que quedan las filas `insert` y `download` de los adjuntos. Las pruebas de almacenamiento, subida, descarga, cifrado en reposo, cubetas y `attachments-check` llegan con los slices S6-C1 a S6-C4 y se citan aquí cuando existan.
- Cambiar cualquier decisión de este documento exige detenerse y preguntar.
