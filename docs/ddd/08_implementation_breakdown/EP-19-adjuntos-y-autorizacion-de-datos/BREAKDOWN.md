# EP-19 · Adjuntos y autorización de tratamiento de datos — desglose técnico de épica

- **Épica:** `docs/ddd/06_epics/EP-19-adjuntos-y-autorizacion-de-datos.md`
- **Versión:** v0.3
- **Historias:** US-147 a US-151 (5 historias, 18 puntos)

## Resumen

La épica crea el módulo `attachments` (esquema `attachments`) con el puerto `StorageProvider` y dos adaptadores (`LocalDiskStorage` sobre `/data/uploads` y `S3CompatibleStorage`). Valida cada archivo por bytes mágicos y por tamaño (5 MB), lo guarda con nombre aleatorio y cifra los sensibles por el bus con `attachment.sensitive` (US-147).

Sobre esa base, Members ofrece la foto del socio (US-148), la autorización de tratamiento de datos con fecha, versión de política y documento firmado (US-149), la pestaña Adjuntos con descarga auditada (US-150) y el conteo y filtro de socios sin autorización en el tablero y la ficha (US-151).

La dirección de dependencia es Members → Attachments, como en el mapa de contextos ("Attachments ← Members, Customer/Supplier"). Las rutas bajo `/members/{id}/attachments` viven en el router de `members`: `members.service` valida el socio y delega en `attachments.service`. `attachments` nunca llama a `members`, así no se forma un ciclo de imports entre services.

## Correcciones aplicadas por DECISIONES.md

- US-147 audita la lectura como `reveal` (sensible) o `export` (no sensible), y US-150 emite además `SensitiveFieldRevealed` → toda descarga de un adjunto deja una sola fila de auditoría con acción `download` (usuario, `attachment_id`, `owner_id`, `sensitive`), escrita con `audit.record` en la misma transacción; el evento `SensitiveFieldRevealed` se sigue emitiendo para los sensibles, pero ningún suscriptor escribe una segunda fila: corregido por DECISIONES N-08 (y por la nota de consolidación de US-074, que escribe la fila directamente).
- La épica y US-149 dicen "desde v0.3 crear un socio sin autorización devuelve 422", y Q16 dice que `data_consent_at` puede ser nulo y no se bloquea nada → las dos reglas se reparten así:
  - la columna sigue nula y sin `NOT NULL` (Q16);
  - los socios anteriores se leen, editan, venden y hacen check-in sin errores;
  - la obligación vive solo en `members.service.create`.
  
  Se usa `privacy.consent_required_from` de N-18 como fecha de corte, con la función pura `members.consent_required(today, consent_required_from)`:
  - si es nulo, la obligación aplica desde el despliegue de v0.3 (el valor por defecto cumple el criterio 1 de US-149);
  - si es una fecha futura, hasta esa fecha se crea con `warnings: ["data_consent_missing"]` como en v0.1 (N-19);
  - si es hoy o pasada, sin `data_consent_at` responde 422.
  
  Corregido por DECISIONES Q16 y N-18. Confirmar en el gate (ver riesgos).
- US-149 lee `current_version` con `settings.service.get_section("privacy")` → se usa el campo `policy_version` y la función `settings.service.current_privacy_version()` de US-057, según la definición de la sección `privacy` (`policy_version`, `policy_text`, `retention_years`, `consent_required_from`): corregido por DECISIONES N-18.
- US-147 criterio 8 valida el dueño "pidiendo a `members.service`" desde `attachments` → la validación ocurre en `members.service` antes de llamar a `attachments.service.store`; `attachments` solo valida `owner_table` contra la lista blanca. Así la dependencia es en un solo sentido, como en `03_context_map.md`. Es una precisión de arquitectura y no cambia el comportamiento.
- Los socios dados de baja se ven en modo solo lectura para admin y coach, y sus adjuntos siguen descargables (evidencia legal); subir a un socio dado de baja devuelve 404: coherente con DECISIONES N-20.
- Las llaves y variables de S3 van solo en `.env`, nunca en la base: coherente con DECISIONES Q12 (por analogía con secretos de canales) y con `CLAUDE.md`.

## Validación contra el dominio y la arquitectura

- **Dominio:** `Attachment` (`02_domain_model.md` 2.15) con `owner_table`, `owner_id`, `kind`, `filename_random`, `mime`, `size_bytes`, `sensitive`, `uploaded_by`. Las invariantes se cumplen:
  - máximo 5 MB;
  - validación por bytes mágicos;
  - nombre aleatorio de 128 bits o más (`uuid4().hex`; `secrets` no está en la lista prohibida);
  - descarga con rol y auditada;
  - sensibles por `attachment.sensitive` con `aad = attachment.id` (id asignado en Python antes del flush).
  
  No se borran en v0.3 (supuesto de US-147): una foto nueva deja la anterior en el historial y la vigente es la más reciente de `kind = photo`. `Member.data_consent_at` y `data_consent_version` existen desde v0.1 (S7); RN-13, RN-14 y RN-15 se respetan.
- **Funciones puras:** `attachments.detect_mime(head: bytes) -> str | None` (JPEG `FF D8 FF`, PNG `89 50 4E 47 0D 0A 1A 0A`, PDF `%PDF-`; detección propia, sin librería nueva), `attachments.validate_upload(size_bytes, mime, kind) -> None | AttachmentError` (foto solo imagen; autorización imagen o PDF), `members.validate_consent(data_consent_at, now) -> None | MemberError`, `members.consent_required(today, consent_required_from) -> bool`.
- **Arquitectura:**
  - `members.service` → `attachments.service` (`store`, `current_photo_id`, `list_for_owner`), `members.service` → `settings.service.current_privacy_version()` y `settings.service.get_section("privacy")`, `dashboard.service` → `members.service.count_without_consent()` (lectura compuesta permitida).
  - `attachments.service` → `core.crypto.bus.encrypt`/`decrypt`, `core.audit.record`, `core.events.emit`.
  - Ningún import de `models` ajenos. Ningún endpoint encadena tres services de escritura: subir una autorización toca `members` y `attachments`, y la versión se lee de `settings` (lectura).
- **Bus y lint:** `attachments` no importa `cryptography` ni `hashlib`; el cifrado del archivo es `bus.encrypt("attachment.sensitive", bytes, aad)`, que devuelve el blob textual `apx1...` que se escribe tal cual en el objeto. `S3CompatibleStorage` usa `boto3` (Apache 2.0); no se firma SigV4 a mano, porque necesitaría `hmac`.
- **Rol:** admin y coach en todas las rutas; socio 403; sin token 401.
- **Paginación:** `GET /members/{id}/attachments` y `GET /members?consent=missing` con `limit` 1 a 200.
- **Auditoría:** `attachments.attachments` es `__audited__ = True` (el `insert` queda con `uploaded_by`); `members` ya es auditada (el `PATCH` con autorización tardía deja `update` con antes y después); la descarga deja `download` (N-08).

## Tablas y migraciones

- `0050_attachments` (US-147): `CREATE SCHEMA attachments`; tabla `attachments.attachments` con:
  - `id` UUID;
  - `owner_table` text NOT NULL con CHECK (`members`);
  - `owner_id` UUID NOT NULL (sin FK entre esquemas);
  - `kind` text NOT NULL con CHECK (`photo`, `consent`, `other`);
  - `filename_random` text NOT NULL único;
  - `mime` text NOT NULL con CHECK (`image/jpeg`, `image/png`, `application/pdf`);
  - `size_bytes` int NOT NULL con CHECK `> 0 AND <= 5242880`;
  - `sensitive` bool NOT NULL;
  - `key_id` UUID nulo (llave del blob cuando `sensitive`; sirve para contar pendientes en una rotación, ver brecha de US-145 en EP-18);
  - `storage_provider` text NOT NULL (`local` | `s3`);
  - `uploaded_by` UUID NOT NULL;
  - `created_at`, `updated_at`, `created_by`.
  
  CHECK `kind <> 'consent' OR sensitive`. Índice `(owner_table, owner_id, kind, created_at DESC)`. Downgrade: borra tabla y esquema (solo en desarrollo).
- Sin migración en `members`: la columna `data_consent_at` sigue nula (Q16). El índice parcial `members(id) WHERE data_consent_at IS NULL AND deleted_at IS NULL` no hace falta con 1.000 socios; si la medición lo pide, `0051_members_consent_missing_idx`.

## Services y eventos

- `modules/attachments/storage/base.py`: `StorageProvider` (`Protocol`) con `put(key, data) -> None`, `get(key) -> bytes`, `delete_object(key) -> None` (este último sin uso en v0.3). Adaptadores en `storage/local.py` (escritura atómica con archivo temporal y `os.replace`, permisos 600, sin extensión) y `storage/s3.py` (`boto3`, credenciales de `.env`). Se elige con `STORAGE_PROVIDER=local|s3`.
- `modules/attachments/service.py`:
  - `store(owner_table, owner_id, kind, stream, sensitive, by) -> Attachment`: lee hasta 5 MB más 1 byte (corta antes de escribir), aplica `detect_mime` y `validate_upload` y fuerza `sensitive = true` si `kind = consent`. Asigna el id, cifra si es sensible, hace `put` y guarda la fila. Si `put` falla, no queda fila; si el flush falla después de `put`, se intenta borrar el objeto huérfano.
  - `open(id, by) -> (Attachment, bytes)`: lee el objeto, descifra si es sensible, llama `audit.record(action="download")` y emite `SensitiveFieldRevealed(member_id=owner_id, field=f"attachment:{id}", user_id)` si es sensible.
  - `current_photo_id(owner_table, owner_ids) -> dict[UUID, UUID | None]`, en lote para la lista y la ficha.
  - `list_for_owner(owner_table, owner_id, kind, limit, offset) -> Page[AttachmentOut]`: nunca devuelve `filename_random` ni contenido.
- `modules/members/service.py`:
  - `attach(member_id, kind, upload, sensitive, by)`: 404 si no existe o está dado de baja y delega en `attachments.service.store`.
  - `list_attachments(member_id, kind, limit, offset)`: 404 si no existe; un socio dado de baja sigue visible (N-20).
  - `create(data, by)` con `consent_required` y `validate_consent`. Copia `data_consent_version` de `current_privacy_version()` e ignora el valor del cliente. Si no hay versión, 409 `privacy_version_missing`.
  - `update(id, data, by)`: permite registrar `data_consent_at` a un socio antiguo; al registrarla copia la versión vigente y emite `MemberUpdated`.
  - `count_without_consent() -> int` y el filtro `consent=missing` en `list`.
  - `get(id)` agrega `photo_attachment_id`.
- `modules/dashboard/service.py`: llena `members_without_consent` (campo reservado en `null` desde US-108).
- Eventos: emitidos `SensitiveFieldRevealed` (descarga sensible) y `MemberUpdated` (autorización tardía); `MemberCreated` sin cambios. Consumidos: ninguno.

## Endpoints

- `POST /api/v1/members/{id}/attachments` — roles: admin, coach
- `GET /api/v1/members/{id}/attachments` — roles: admin, coach
- `GET /api/v1/attachments/{id}` — roles: admin, coach
- `POST /api/v1/members` — roles: admin, coach
- `PATCH /api/v1/members/{id}` — roles: admin, coach
- `GET /api/v1/members/{id}` — roles: admin, coach
- `GET /api/v1/members` — roles: admin, coach
- `GET /api/v1/dashboard` — roles: admin, coach

Notas de contrato:
- Subida: multipart (`file`, `kind`, `sensitive?`). Responde 201 con `AttachmentOut`, 404 si el socio no existe o está dado de baja, y 422 `file_too_large` o `unsupported_type` con `field: "file"`.
- Descarga: responde con `Content-Type` del `mime` guardado, `Content-Disposition: attachment`, `Cache-Control: no-store` y `X-Content-Type-Options: nosniff`.
- Alta de socio: responde 422 con `field: "data_consent_at"` cuando aplica la obligación, y 409 `privacy_version_missing`.
- Lista de socios: acepta `consent=missing`.
- Tablero: agrega `members_without_consent: int`.

## Componentes de front

- `web/src/features/members/components/PhotoField.tsx`: vista previa, validación previa en el cliente (tipo y 5 MB) y mensaje "La foto supera 5 MB" sin perder el formulario. Al crear, sube la foto después del `POST /members` exitoso; si la subida falla, informa que el socio quedó creado sin foto.
- `web/src/features/members/components/ConsentSection.tsx`: fecha de aceptación (por defecto ahora en Bogotá), versión vigente en solo lectura y archivo del documento firmado. Es obligatoria en el alta cuando aplica y opcional en la edición de socios antiguos, con el aviso "sin autorización registrada".
- `web/src/features/members/components/AttachmentsTab.tsx`: tabla con tipo, fecha, tamaño y quién subió, y botón Descargar (descarga con `fetch` y blob, sin URL pública). Estados de carga, vacío ("este socio no tiene adjuntos") y error.
- Encabezado de `Socio_Ficha`: miniatura de la foto (pedida al API con el token) y `StatusTag` "Sin autorización registrada" con texto.
- `web/src/features/dashboard/components/ConsentKpi.tsx`: `KpiCard` "Sin autorización" que enlaza a `/socios?consent=missing` (`// DESIGN-GAP:` la tarjeta no está en el diseño).
- `web/src/features/members/api.ts` y `schemas.ts` (Zod de `data_consent_at` y del archivo). Pruebas Vitest de cada componente. Sin colores literales.

## Worker, CLI e infraestructura

- Volumen `uploads` montado en `/data/uploads` en `api` (lectura y escritura) e incluido en el backup nocturno (N-50).
- Variables nuevas en `.env.example`: `STORAGE_PROVIDER`, `UPLOADS_DIR`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`, `S3_REGION`.
- Nginx: `client_max_body_size` de 6 MB solo en `location ~ ^/api/v1/members/[^/]+/attachments$`. Con el límite global de 5 MB de US-006, un archivo de exactamente 5 MB más la cabecera multipart recibiría 413 de Nginx antes de llegar al API. El límite exacto de 5.242.880 bytes del archivo lo aplica el API.
- Nginx no sirve `/data/uploads` por ninguna ruta estática.
- `pip-licenses`: `boto3` y `botocore` (Apache 2.0) entran en `NOTICE`; la detección de tipo es propia, sin librería nueva.
- Clase de dato `attachment.sensitive` registrada en `core/crypto/registry.py` y llave creada con `cli init-keys --data-class attachment.sensitive`.

## Dependencias

- EP-01: US-016 (hook de auditoría), US-012 (mixin con id en Python).
- EP-02: US-025 (cifrado y registro de `data_class`), US-028 (tipos), US-029 (bitácora de `decrypt`).
- EP-03: US-034 (`require_role`), US-038 (cabeceras de seguridad).
- EP-05: US-054 (secciones), US-057 (versión de política; `current_privacy_version()`), con los campos de N-18 (`consent_required_from`).
- EP-07: US-069 (registrar socio, `warnings`), US-073 (ficha y pestañas), US-075 (editar socio), US-070 (lista y filtros).
- EP-11: US-102 (consulta de auditoría con acción `download`), migración `0002_audit_log` con `download` en el CHECK (N-08).
- EP-12: US-108 (contrato del tablero con `members_without_consent` reservado).
- EP-13: US-114 (backup incluye `uploads`).
- EP-00: US-006 (Nginx y límite de subida), US-004 (licencias).
- EP-18: la rotación de `attachment.sensitive` depende de la propuesta de brecha de US-145.

## Riesgos

- Interpretación de `consent_required_from` nulo como "obligatoria desde v0.3": si el desglose de US-057 (v0.1) le da otro significado al nulo (por ejemplo "no exigida"), el criterio 1 de US-149 no se cumple sin configurar la fecha. Mitigación: confirmar en el gate y probar los dos valores; si se invierte, el despliegue de v0.3 incluye fijar la fecha en Configuración.
- Socios anteriores a v0.3 sin autorización: no se pueden exigir hacia atrás (Q16). Mitigación: tarjeta del tablero, filtro `consent=missing` y marca en la ficha (US-151).
- Límite de 5 MB en Nginx contra multipart (ver infraestructura). Mitigación: excepción de 6 MB en la ruta de subida y prueba de borde con 5.242.880 y 5.242.881 bytes a través de Nginx.
- Volumen `uploads` fuera del backup: se perderían consentimientos. Mitigación: prueba de restauración de US-115 que incluya un adjunto.
- Objeto huérfano en el storage si la transacción falla después de `put`. Mitigación: borrado compensatorio y, más adelante, un job de limpieza de objetos sin fila.
- Memoria: un PDF sensible de 5 MB se cifra en memoria y el blob base64url crece cerca de un 33 %. Es aceptable con menos de 10 usuarios concurrentes.
- Front condicionado a D1.

## Estado y estimación por historia

- US-147 · Almacenamiento seguro de adjuntos — **READY** — 24 h — Módulo y migración `0050`, `StorageProvider` con dos adaptadores, bytes mágicos propios, cifrado por el bus y auditoría `download` (N-08).
- US-148 · Subir foto del socio — **READY** — 12 h — Ruta en el router de `members` con delegación a `attachments` (dirección del mapa de contextos) y `photo_attachment_id` en la ficha.
- US-149 · Registrar autorización de datos — **READY** — 18 h — Obligatoria en el alta por `members.service` con corte `consent_required_from` (Q16 y N-18), versión de `current_privacy_version()` y autorización tardía por `PATCH`.
- US-150 · Pestaña adjuntos y descarga auditada — **READY** — 13 h — Lista paginada y descarga con cabeceras `no-store`/`nosniff`, una sola fila `download` por descarga (N-08).
- US-151 · Socios sin autorización registrada — **READY** — 8 h — `count_without_consent`, filtro `consent=missing` y campo reservado del tablero, sin bloquear ninguna operación (Q16).

## Total de la épica

- **Total: 75 h**
