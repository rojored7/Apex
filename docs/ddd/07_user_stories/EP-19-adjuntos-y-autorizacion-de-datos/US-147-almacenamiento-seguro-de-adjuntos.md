# US-147 · Como administrador quiero que los archivos adjuntos se guarden validados, con nombre aleatorio y cifrados cuando son sensibles para que la foto y la autorización de un socio no puedan filtrarse ni suplantarse

- **Épica:** EP-19 · Adjuntos y autorización de tratamiento de datos
- **Bounded context:** Attachments (esquema `attachments`, módulo `attachments`)
- **Versión:** v0.3
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica de la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (historia sin front; la usan US-148, US-149 y US-150)

## Historia

Como administrador
quiero que todo archivo subido se valide por sus bytes, se guarde con un nombre aleatorio y se cifre cuando es sensible
para que ningún ejecutable disfrazado entre al servidor y ningún documento del socio quede legible en el disco

## Contexto de dominio

- **Aggregate / entidades:** `Attachment` (`owner_table`, `owner_id`, `kind` `photo` | `consent` | `other`, `filename_random`, `mime`, `size_bytes`, `sensitive`, `uploaded_by`).
- **Reglas que aplica:** máximo 5 MB; validación por bytes mágicos, no por extensión; nombre aleatorio; descarga solo con rol y auditada; los sensibles pasan por el bus con `attachment.sensitive` (RN-13); RN-14 (borrado lógico no aplica a adjuntos: ver supuesto).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `attachments.detect_mime(head_bytes) -> str | None`, `attachments.validate_upload(size_bytes, mime, kind) -> None | AttachmentError`

## Alcance

- **Backend:** modelo y migración del esquema `attachments`; puerto `StorageProvider` (`put`, `get`, `delete_object`) con `LocalDiskStorage` (volumen `/data/uploads`) y `S3CompatibleStorage`; `attachments.service.store(owner_table, owner_id, kind, stream, sensitive, by)` y `attachments.service.open(id, by)`; clase de dato `attachment.sensitive` registrada en el bus; tabla `attachments` con `__audited__ = True`.
- **Front:** No aplica.

## Criterios de aceptación

1. Un archivo de 5 MB (5.242.880 bytes) se acepta; uno de 5.242.881 bytes se rechaza con 413 o 422 `file_too_large` antes de escribir en disco.
2. El tipo se decide leyendo los primeros bytes; un ejecutable renombrado a `.jpg` se rechaza con 422 `unsupported_type`; la extensión y el `Content-Type` del cliente se ignoran.
3. El nombre en disco es aleatorio (al menos 128 bits, por ejemplo UUID4 o `token_hex(16)`), sin extensión del original y sin el nombre del socio; el nombre original no se guarda.
4. Un adjunto con `sensitive = true` se escribe cifrado con `bus.encrypt("attachment.sensitive", bytes, aad = attachment.id)`; leer el archivo del volumen directamente no muestra el contenido en claro (prueba que busca los bytes originales en el archivo).
5. Cada subida deja auditoría (`insert` en `attachments`) con `uploaded_by`; cada lectura por `open` deja una fila de auditoría con acción `reveal` si es sensible o `export` si no (ver supuesto), usuario y `attachment_id`.
6. `StorageProvider` se elige por `.env` (`STORAGE_PROVIDER=local|s3`); las credenciales S3 vienen de `.env`, nunca de la base.
7. `owner_table` solo admite valores de una lista blanca (`members` en v0.3); otro valor devuelve 422.
8. El módulo `attachments` no importa `models` de `members`; `owner_id` se valida pidiendo a `members.service` que el socio exista y no esté dado de baja.
9. Las librerías nuevas (detección de tipo) pasan el chequeo de licencias de CI.

## Escenarios BDD

```gherkin
# language: es
Característica: Almacenamiento seguro de adjuntos

  Escenario: Se guarda un PDF sensible cifrado
    Dado un socio activo
    Cuando se guarda un PDF de 800 KB marcado como sensible para ese socio
    Entonces existe un Attachment con mime "application/pdf" y un nombre aleatorio
    Y el archivo en el volumen no contiene el texto del PDF en claro
    Y abrirlo por el service devuelve exactamente los bytes originales

  Escenario: Un ejecutable disfrazado de foto
    Dado un archivo ejecutable renombrado "foto.jpg"
    Cuando se intenta guardar como foto de un socio
    Entonces se rechaza con "unsupported_type"
    Y no se escribe nada en el volumen

  Escenario: Archivo de más de 5 MB
    Dado un archivo JPEG de 5.242.881 bytes
    Cuando se intenta guardar
    Entonces se rechaza con "file_too_large"
```

## Endpoints

- Ninguno propio (los exponen US-148, US-149 y US-150).

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** sí; esquema `attachments`, tabla `attachments` con columnas comunes (`id`, `created_at`, `updated_at`, `created_by`) más las del aggregate.
- **Trigger / restricciones:** `size_bytes <= 5242880` como `CHECK`; `kind` y `owner_table` como `CHECK` de enumeración.
- **Funciones puras a probar:** `detect_mime` con cabeceras JPEG, PNG, PDF, ELF y PE; `validate_upload` con límites exactos.
- **Pruebas:** puras; service con base real y volumen temporal; prueba de "no claro en disco"; prueba de arquitectura de imports.
- **Archivos principales:** `api/src/app/modules/attachments/{models,service,schemas}.py`, `api/src/app/modules/attachments/storage/{base,local,s3}.py`.

## Supuestos

- Supuesto: tipos admitidos en v0.3: `image/jpeg`, `image/png` y `application/pdf`; la foto solo imagen, la autorización imagen o PDF.
- Supuesto: los adjuntos no se borran en v0.3 (no hay regla de borrado); reemplazar la foto crea un adjunto nuevo y el anterior queda en el historial.
- Supuesto: la descarga de un adjunto no sensible se audita con acción `export`; el catálogo de acciones no tiene `download`.

## Dependencias

- US-016 · Hook de auditoría (tabla auditada)
- US-025 · Cifrado AES-GCM (clase `attachment.sensitive`)
- Nota: requiere también US-034 (roles) y US-069 (socio existente) para los endpoints que lo usan.
- US-034 · roles y US-069 · socio existente (agregado en consolidación)

## INVEST

- **Independiente:** capa de almacenamiento sin pantalla.
- **Negociable:** tipos admitidos y proveedor S3.
- **Valiosa:** base legal (Ley 1581) para guardar consentimientos.
- **Estimable:** modelo, dos adaptadores y validaciones.
- **Pequeña:** cabe en un sprint.
- **Testeable:** límites y "no claro en disco" son binarios.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] Chequeo de licencias en verde
- [ ] Auditoría verificada para `attachments`
- [ ] Revisión de PR aprobada
