# US-149 · Como administrador quiero registrar la autorización de tratamiento de datos de cada socio nuevo para demostrar su consentimiento ante un reclamo bajo la Ley 1581

- **Épica:** EP-19 · Adjuntos y autorización de tratamiento de datos
- **Bounded context:** Attachments + Members
- **Versión:** v0.3
- **Actor:** administrador, coach
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica de la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Socio_Form` (`/socios/nuevo`, sección autorización)

## Historia

Como administrador o coach
quiero registrar la fecha y la versión de la política aceptada por el socio y adjuntar el documento firmado
para que el gimnasio pueda probar que tiene su consentimiento

## Contexto de dominio

- **Aggregate / entidades:** `Member` (`data_consent_at`, `data_consent_version`), `Attachment(kind = consent, sensitive = true)`, `SettingsSection(privacy)`.
- **Reglas que aplica:** invariante de Member que se activa en v0.3: `data_consent_at` obligatorio para crear; `data_consent_version` se toma de la sección `privacy`; Q16 (los socios anteriores a v0.3 pueden seguir con `data_consent_at` nulo, no se bloquea nada); RN-13 (el documento de autorización va cifrado por `attachment.sensitive`); RN-15.
- **Eventos que emite:** `MemberCreated` (sin cambios), `MemberUpdated` al registrar una autorización tardía.
- **Eventos que consume:** ninguno
- **Funciones puras:** `members.validate_consent(data_consent_at, today) -> None | MemberError`

## Alcance

- **Backend:** `POST /api/v1/members` exige `data_consent_at`; el service asigna `data_consent_version` desde `settings.service.get_section("privacy")`; `PATCH /api/v1/members/{id}` permite registrar la autorización de un socio antiguo; `POST /api/v1/members/{id}/attachments` con `kind=consent` fuerza `sensitive = true`.
- **Front:** sección "Autorización de datos" en `Socio_Form` con fecha de aceptación (por defecto hoy en Bogotá), versión vigente visible y adjunto del documento.

## Criterios de aceptación

1. Desde v0.3, `POST /members` sin `data_consent_at` devuelve 422 con `field: "data_consent_at"`.
2. `data_consent_at` es una fecha-hora con zona en UTC; una fecha futura (posterior a ahora) devuelve 422.
3. `data_consent_version` no lo envía el cliente: el service lo copia de la versión vigente de `privacy`; si el cliente lo envía, se ignora; si la sección `privacy` no tiene versión configurada, la creación devuelve 409 `privacy_version_missing`.
4. Un adjunto con `kind=consent` se guarda siempre con `sensitive = true`, cifrado por `attachment.sensitive`, aunque el cliente envíe `sensitive=false`.
5. Un socio creado antes de v0.3 con `data_consent_at` nulo se sigue leyendo, editando y vendiendo sin errores (Q16).
6. Registrar la autorización de un socio antiguo por `PATCH` deja `data_consent_at`, la versión vigente y una fila de auditoría `update` con antes y después.
7. Solo admin y coach; socio recibe 403.

## Escenarios BDD

```gherkin
# language: es
Característica: Autorización de tratamiento de datos

  Antecedentes:
    Dado que la política de privacidad vigente es la versión "2026-09"

  Escenario: Alta de un socio con autorización
    Dado que inicié sesión como coach
    Cuando registro al socio "Andrés Ruiz" con fecha de autorización de hoy y adjunto el PDF firmado
    Entonces el socio queda con la versión de política "2026-09"
    Y el PDF queda guardado como adjunto sensible cifrado

  Escenario: Alta sin autorización
    Dado que inicié sesión como administrador
    Cuando intento registrar un socio sin fecha de autorización
    Entonces recibo 422 con field "data_consent_at"
    Y no se crea el socio
```

## Endpoints

- `POST /api/v1/members` — rol(es): admin, coach — entrada: datos del socio + `data_consent_at` — salida: `MemberOut` con `data_consent_at`, `data_consent_version` — códigos: 201, 401, 403, 409, 422
- `PATCH /api/v1/members/{id}` — rol(es): admin, coach — entrada: `data_consent_at?` — códigos: 200, 401, 403, 404, 422
- `POST /api/v1/members/{id}/attachments` (`kind=consent`) — rol(es): admin, coach — códigos: 201, 401, 403, 404, 413, 422

## Pantalla

- `Socio_Form`, sección autorización: fecha, versión vigente en solo lectura y campo de archivo. En edición de un socio sin autorización se muestra el aviso "sin autorización registrada".

## Notas técnicas

- **Migración:** no de esquema (las columnas existen desde v0.1 por S7); no se vuelve `NOT NULL` la columna para no romper a los socios antiguos (Q16): la obligatoriedad vive en `service.py`.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `validate_consent` (nulo, futuro, pasado válido).
- **Pruebas:** service con base real (versión copiada de settings, 409 sin versión), router (422, rol), front (campo obligatorio en alta, opcional en edición de antiguos).
- **Archivos principales:** `api/src/app/modules/members/service.py`, `api/src/app/modules/attachments/service.py`, `web/src/features/members/components/ConsentSection.tsx`.

## Supuestos

- Supuesto: el adjunto del documento firmado es recomendado pero no obligatorio para crear; lo obligatorio es `data_consent_at` (la épica solo exige "autorización", no el archivo).
- Supuesto: la sección `privacy` guarda `current_version` como texto (US-057); si cambia la versión, los socios existentes conservan la que aceptaron.

## Dependencias

- US-147 · Almacenamiento seguro de adjuntos
- US-057 · Versión de política de privacidad
- US-069 · Registrar socio

## INVEST

- **Independiente:** cambia la validación del alta sin tocar otros flujos.
- **Negociable:** si el archivo se vuelve obligatorio.
- **Valiosa:** cumplimiento legal demostrable.
- **Estimable:** validación + sección de formulario.
- **Pequeña:** sí.
- **Testeable:** 422 sin consentimiento y versión copiada.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `members`
- [ ] Revisión de PR aprobada
