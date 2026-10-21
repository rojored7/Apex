# EP-19 · Adjuntos y autorización de tratamiento de datos

- **Versión del plan:** v0.3 (punto 3 de la versión 0.3; `BRECHAS.md` sección 3, foto y autorización).
- **Bounded context:** Attachments (soporte, esquema `attachments`), con Members como cliente (Customer/Supplier).
- **Estimación relativa:** M.

## Objetivo de negocio

Que la foto del socio y su autorización firmada de tratamiento de datos estén guardadas junto a su ficha, protegidas y con rastro de quién las vio. Así el gimnasio puede demostrar, ante un reclamo bajo la Ley 1581, que tiene el consentimiento del socio.

## Actores

- Administrador y coach: suben la foto y la autorización al crear o editar un socio, y las consultan.
- Administrador: configura la versión vigente del texto de privacidad (sección `privacy` de Settings).

## Capacidades incluidas

### Backend
- Aggregate `Attachment`: `owner_table`, `owner_id`, `kind` (`photo`, `consent`, `other`), `filename_random`, `mime`, `size_bytes`, `sensitive`, `uploaded_by`.
- Puerto `StorageProvider` con `LocalDiskStorage` (volumen `/data/uploads`) y `S3CompatibleStorage`.
- Invariantes: máximo 5 MB, validación por bytes mágicos (no por extensión), nombre aleatorio, descarga solo con rol y auditada.
- Los adjuntos marcados como sensibles se cifran por el bus con la clase `attachment.sensitive`.
- Endpoints de subida y descarga (`POST /members/{id}/attachments`, `GET` del adjunto) servidos solo por el API.
- Invariante de Member que se activa en esta versión: `data_consent_at` obligatorio para crear un socio, junto con `data_consent_version` tomado de la sección `privacy`.

### Front
- Foto y autorización en el formulario del socio; pestaña Adjuntos de la ficha.

## Fuera de alcance

- Firma electrónica de la autorización dentro del sistema.
- Galería o gestión documental general.

## Criterios de éxito medibles

- Un archivo de 5 MB más un byte es rechazado; un ejecutable renombrado a `.jpg` es rechazado por bytes mágicos.
- Un adjunto sensible en disco no se puede abrir sin pasar por el bus (no aparece en claro en el volumen).
- Cada descarga deja auditoría con usuario y adjunto.
- Desde esta versión, crear un socio sin autorización devuelve 422.
- El nombre del archivo en disco no revela el nombre del socio ni el original.

## Dependencias

- EP-07 Padrón de socios.
- EP-02 Bus de criptografía (`attachment.sensitive`).
- EP-05 Configuración del gimnasio (sección `privacy`).
- EP-11 Auditoría y trazabilidad.

## Riesgos

- Socios creados antes de v0.3 no tienen autorización; la regla nueva no puede aplicarse hacia atrás sin un plan de recolección (ver preguntas abiertas).
- El volumen de uploads entra en el backup; si el backup no lo incluye, se pierden los consentimientos.
- Validar bytes mágicos requiere una librería con licencia permitida (verificar en CI).

## Pantallas del diseño que habilita

- Foto y autorización en `Socio_Form`; pestaña Adjuntos de `Socio_Ficha`.
