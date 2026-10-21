# US-069 · Como recepción (administrador o coach) quiero registrar un socio nuevo con sus datos personales cifrados para tenerlo en el padrón sin exponer su cédula ni su teléfono

- **Épica:** EP-07 · Padrón de socios
- **Bounded context:** Members (esquema `members`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 8
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Socio_Form` (`/socios/nuevo`)

## Historia

Como administrador o coach en recepción
quiero registrar un socio con nombre, documento, teléfono, correo, fecha de nacimiento, sexo, contacto de emergencia y notas
para que quede en el padrón con sus datos sensibles cifrados y no se dupliquen socios por documento

## Contexto de dominio

- **Aggregate / entidades:** `Member` (raíz) con value objects cifrados `Document` (`member.document`, índice ciego), `Phone` (`member.phone`, índice ciego), `Email` (`member.email`, índice ciego), `BirthDate` (`member.birth_date`), `EmergencyContact` (`member.emergency_contact`, JSON con nombre y teléfono).
- **Reglas que aplica:** RN-13 (datos sensibles cifrados por clase de dato, búsqueda por índice ciego); RN-14 (socios con borrado lógico: la unicidad es entre no borrados); invariante de documento único entre socios no borrados (por `document_idx`); `first_name` y `last_name` no vacíos; `data_consent_at` opcional con aviso en v0.1 (obligatorio desde v0.3, US-149); S7 (`sex` y `data_consent_at` existen desde v0.1); regla de datos 3 (`id`, `created_at`, `updated_at`, `created_by`).
- **Eventos que emite:** `MemberCreated(member_id)`
- **Eventos que consume:** ninguno
- **Funciones puras:** `members.validate_member_input(data) -> None | MemberError` (nombres no vacíos, `sex` en `f`/`m`/`x`/null, fecha de nacimiento no futura); usa `crypto.normalize_for_index` (US-026)

## Alcance

- **Backend:** modelo `members.members` con columnas `first_name`, `last_name`, `sex`, `status` (`active` por defecto), `notes`, `document` (`Encrypted("member.document")`), `document_idx` (`BlindIndexed("member.document")`), `phone`, `phone_idx`, `email`, `email_idx`, `birth_date`, `emergency_contact`, `data_consent_at`, `data_consent_version`, `deleted_at` y columnas comunes; `__audited__ = True`; índice único parcial `(document_idx) WHERE deleted_at IS NULL`; índices en `phone_idx` y `email_idx`; `members.service.create(data, by)`; router `POST /members`.
- **Front:** `web/src/features/members/pages/MemberFormPage.tsx` en modo crear, con React Hook Form + Zod (`schemas.ts`), campos de `Socio_Form` sin foto ni adjuntos, casilla "El socio autorizó el tratamiento de datos" (registra `data_consent_at`) con aviso si queda sin marcar, enlace al socio existente cuando el documento está repetido, redirección a la ficha al guardar.

## Criterios de aceptación

1. `POST /api/v1/members` con rol `admin` o `coach` crea el socio y responde 201 con `id`, `first_name`, `last_name`, `status = "active"`, los campos sensibles enmascarados y `created_at` en UTC ISO 8601.
2. Un usuario con rol `member` recibe 403 y una petición sin token recibe 401.
3. `document`, `phone`, `email`, `birth_date` y `emergency_contact` se guardan como blob `apx1.<key_id>.A256GCM.<nonce>.<ct>` con `aad = id del socio`; `SELECT document, phone, email FROM members.members` no contiene ningún valor en claro (prueba de arquitectura).
4. `document_idx`, `phone_idx` y `email_idx` se calculan con el índice ciego sobre el valor normalizado (minúsculas, sin espacios ni puntos): `"1.020.304"` y `"1020304"` producen el mismo índice.
5. Crear un socio con un documento que ya tiene otro socio no borrado responde 409 con `code = "member_document_duplicated"`, `field = "document"` y `existing_id` del socio existente; no se crea nada.
6. Un documento que solo pertenece a un socio dado de baja (`deleted_at` no nulo) no bloquea la creación.
7. `first_name` o `last_name` vacíos o con solo espacios responden 422 con `field`; `sex` fuera de `f`, `m`, `x` o nulo responde 422; `birth_date` futura responde 422.
8. Si `data_consent_at` no viene, el socio se crea igual y la respuesta incluye `warnings: ["data_consent_missing"]`; el formulario muestra el aviso "Falta la autorización de tratamiento de datos".
9. `created_by` es el usuario autenticado; la creación deja una fila de auditoría `insert` en `members` donde los campos cifrados aparecen como blob, nunca en claro.
10. Se emite `MemberCreated` en la misma transacción; si el handler falla, el socio no queda creado.
11. Ningún log contiene el documento, el teléfono, el correo ni el token (prueba de captura de logs).
12. El formulario valida en el cliente los mismos campos obligatorios, muestra los errores del API en el campo indicado por `field` y, ante 409, muestra el enlace "Ver socio existente" a `/socios/{existing_id}`.

## Escenarios BDD

```gherkin
# language: es
Característica: Registrar socio

  Antecedentes:
    Dado un usuario autenticado con rol "coach"

  Escenario: Registro con datos completos
    Cuando registra a "Laura Gómez" con documento "1.020.304", teléfono "300 123 4567" y la autorización marcada
    Entonces el socio queda creado con estado "active"
    Y el documento se guarda cifrado y su índice ciego corresponde a "1020304"
    Y queda una entrada de auditoría de creación sin datos en claro
    Y se emite el evento MemberCreated

  Escenario: Documento repetido
    Dado un socio activo con documento "1020304"
    Cuando registra a otro socio con documento "1020304"
    Entonces recibe un error 409 con el campo "document"
    Y el error trae el identificador del socio existente
    Y el formulario muestra el enlace "Ver socio existente"

  Escenario: Documento de un socio dado de baja
    Dado un socio dado de baja con documento "1020304"
    Cuando registra un socio nuevo con documento "1020304"
    Entonces el socio nuevo queda creado

  Escenario: Nombre vacío
    Cuando registra un socio con nombre "   "
    Entonces recibe un error 422 con el campo "first_name"

  Escenario: Sin autorización de datos en v0.1
    Cuando registra un socio sin marcar la autorización
    Entonces el socio queda creado
    Y la respuesta trae el aviso "data_consent_missing"

  Escenario: Rol socio denegado
    Dado un usuario autenticado con rol "member"
    Cuando intenta registrar un socio
    Entonces recibe un error 403
```

## Endpoints

- `POST /api/v1/members` — rol(es): admin, coach — entrada: `first_name`, `last_name`, `document`, `phone?`, `email?`, `birth_date?` (AAAA-MM-DD), `sex?`, `emergency_contact? { name, phone }`, `notes?`, `data_consent_at?` — salida: `MemberDetail` con campos sensibles enmascarados y `warnings` — códigos: 201, 401, 403, 409, 422.

## Pantalla

- `Socio_Form` en `/socios/nuevo`: todos los campos del diseño excepto foto y adjuntos (EP-19). Estados: enviando, error por campo, 409 con enlace. `// DESIGN-GAP:` el diseño no muestra el aviso de autorización faltante ni la casilla de autorización sin adjunto.

## Notas técnicas

- **Migración:** sí. Crea el esquema `members` y la tabla `members.members` con todas las columnas del aggregate (incluye `sex`, `data_consent_at`, `data_consent_version` por S7), índice único parcial sobre `document_idx` y no únicos sobre `phone_idx` y `email_idx`.
- **Trigger / restricciones:** índice único parcial `WHERE deleted_at IS NULL`; `CHECK (sex IN ('f','m','x'))`.
- **Funciones puras a probar:** `validate_member_input` (nombres vacíos, sexo inválido, fecha futura, fecha de hoy válida).
- **Pruebas:** service con base real (creación, duplicado, duplicado contra borrado, carrera con dos inserciones simultáneas resuelta por el índice único que se traduce a 409), router (rol, 422, envelope con `existing_id`), arquitectura (no claro en base), logs sin datos; front (formulario, errores por campo, enlace 409); E2E Playwright "crear socio, buscarlo por teléfono y abrir su ficha" (junto con US-070 y US-073).
- **Archivos principales:** `api/src/app/modules/members/{models,schemas,service,router,exceptions}.py`, `api/migrations/versions/<rev>_members.py`, `web/src/features/members/{api.ts,schemas.ts,pages/MemberFormPage.tsx}`.

## Supuestos

- Supuesto: el documento es obligatorio para crear un socio (es la base de la unicidad y de la importación por documento, Q17); el teléfono y el correo son opcionales.
- Supuesto: la casilla de autorización en v0.1 solo registra `data_consent_at = ahora` y `data_consent_version` vacío hasta que exista la sección `privacy` (US-057); si ya existe, se toma su versión vigente.
- Supuesto: para mostrar valores enmascarados sin descifrar (US-073), la migración incluye columnas `document_hint`, `phone_hint` y `email_hint` con los últimos 4 dígitos o el dominio enmascarado; si el gate rechaza guardar esos fragmentos en claro, se omiten y la ficha muestra "Registrado".
- Supuesto: la respuesta usa una lista `warnings` para el aviso de autorización faltante; el contrato no la define.

## Dependencias

- US-028 · Tipos de columna Encrypted y BlindIndexed (cifrado e índice ciego).
- US-034 · Dependencias current_user y require_role (rol y `created_by`).
- US-016 · Hook de auditoría after_flush (tabla auditada).
- US-061 · Panel layout (marco de la pantalla).
- US-060 · Formato de dinero y fechas (fecha de nacimiento).

## INVEST

- **Independiente:** no necesita membresías ni pagos.
- **Negociable:** obligatoriedad de teléfono y correo, texto del aviso.
- **Valiosa:** es la primera pieza del padrón y cumple RN-13 desde el primer socio.
- **Estimable:** modelo, service, router y un formulario.
- **Pequeña:** 8 puntos por cifrado, índice único y formulario; no se parte para no dejar un socio sin cifrar.
- **Testeable:** cada criterio tiene prueba de service, router o arquitectura.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales (si aplica)
- [ ] Migración aplicada con `alembic upgrade head` y reversible (si aplica)
- [ ] `docs/openapi.json` regenerado (si cambia el contrato)
- [ ] Auditoría verificada para las tablas tocadas (si aplica)
- [ ] Revisión de PR aprobada
