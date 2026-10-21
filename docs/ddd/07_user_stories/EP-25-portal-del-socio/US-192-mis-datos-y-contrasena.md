# US-192 · Como socio quiero ver y corregir mi teléfono, correo y contacto de emergencia y cambiar mi contraseña para mantener mis datos al día sin ir a recepción

- **Épica:** EP-25 · Portal del socio
- **Bounded context:** Portal (módulo `portal`), Members y Auth
- **Versión:** v1.0
- **Actor:** socio
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Portal_Datos` (`/mi/datos`)

## Historia

Como socio
quiero ver mis datos personales y editar los que me corresponden, y cambiar mi contraseña
para que el gimnasio pueda contactarme bien y mi cuenta siga segura

## Contexto de dominio

- **Aggregate / entidades:** `Member` (value objects cifrados `Phone`, `Email`, `EmergencyContact`), `User`.
- **Reglas que aplica:** Q24 (editables: teléfono, correo, contacto de emergencia, preferencias de canal y contraseña; nunca documento, nombres, apellidos, sexo ni fecha de nacimiento), Q6 (el socio ve sus datos sin enmascarar y se audita), RN-13, P5 (correo de login separado del correo del padrón), RN-15.
- **Eventos que emite:** `MemberUpdated`, `SensitiveFieldRevealed`, `PasswordChanged`
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna nueva (reutiliza `crypto.normalize_for_index`)

## Alcance

- **Backend:** `GET /me` (descifra los campos propios y audita), `PATCH /me` que llama a `members.service.update(member_id, data, by)` con una lista blanca de campos, `POST /me/password` que llama a `auth.service.change_password`.
- **Front:** `Portal_Datos` con datos de solo lectura (documento, nombres, fecha de nacimiento) y formulario de los editables; formulario de cambio de contraseña.

## Criterios de aceptación

1. `GET /api/v1/me` devuelve nombres, apellidos, sexo, documento, fecha de nacimiento, teléfono, correo y contacto de emergencia descifrados, y deja una fila de auditoría `reveal` con el usuario socio y la lista de campos.
2. `PATCH /api/v1/me` acepta solo `phone`, `email` y `emergency_contact` (nombre y teléfono); cualquier otro campo (`document`, `first_name`, `last_name`, `sex`, `birth_date`, `member_id`) devuelve 422 con `field`.
3. Los valores nuevos se cifran por el bus con su `data_class` y `aad = id` del socio, y se recalculan `phone_idx` y `email_idx`; la base no contiene el valor en claro.
4. Cambiar teléfono o correo a uno que ya usa otro socio no borrado se acepta (la unicidad del dominio es solo por documento).
5. El cambio queda auditado como `update` con `before` y `after` como blobs, y emite `MemberUpdated`.
6. Cambiar el correo del padrón no cambia el correo de login (`auth.users.email`, P5); la pantalla lo informa.
7. `POST /api/v1/me/password` con `{ current_password, new_password }` verifica la actual con argon2id, exige la política de contraseña de EP-04, revoca los demás refresh tokens del usuario y emite `PasswordChanged`; contraseña actual incorrecta devuelve 422 con `field = current_password`.
8. Ninguna ruta acepta `member_id`; anti IDOR probado (US-186). Admin y coach reciben 403; sin token, 401.
9. Teléfono con formato inválido (menos de 7 dígitos tras normalizar) o correo inválido devuelve 422.

## Escenarios BDD

```gherkin
# language: es
Característica: Mis datos

  Escenario: El socio actualiza su teléfono
    Dado que "Laura" está en "Mis datos"
    Cuando cambia su teléfono a "300 555 1234" y guarda
    Entonces ve el teléfono nuevo
    Y recepción encuentra a "Laura" buscando "3005551234"
    Y la auditoría registra el cambio sin el teléfono en claro

  Escenario: Intento de cambiar el documento
    Cuando "Laura" envía un cambio de documento
    Entonces el sistema rechaza el cambio con error en "document"
    Y el documento no cambia
```

## Endpoints

- `GET /api/v1/me` — rol(es): member — salida: `MeOut` — códigos: 200, 401, 403
- `PATCH /api/v1/me` — rol(es): member — entrada: `{ phone?, email?, emergency_contact? }` — códigos: 200, 401, 403, 422
- `POST /api/v1/me/password` — rol(es): member — entrada: `{ current_password, new_password }` — códigos: 204, 401, 403, 422

## Pantalla

- `Portal_Datos`: datos fijos con la nota "Para corregirlos, acércate a recepción", formulario de editables y tarjeta de contraseña; controles de 44 px; estados de carga, error y guardado.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** lista blanca de campos como constante probada.
- **Pruebas:** service (blob, índice, auditoría, `MemberUpdated`); router (lista blanca, anti IDOR, contraseña); Vitest de la página.
- **Archivos principales:** `api/src/app/modules/portal/`, `members/service.py`, `auth/service.py`, `web/src/features/portal/pages/PortalData.tsx`.

## Supuestos

- Supuesto: `POST /me/password` reutiliza la lógica de `POST /auth/me/password` (EP-04); ambas rutas conviven.
- Supuesto: el mínimo de 7 dígitos para teléfono no está definido en el dominio.

## Dependencias

- US-186 · Autorización propia en rutas me
- US-075 · Editar socio (re-cifrado e índice)
- US-045 · Ver mi cuenta y cambiar contraseña

## INVEST

- **Independiente:** reutiliza edición de socio y cambio de contraseña.
- **Negociable:** campos editables (decididos en Q24).
- **Valiosa:** datos de contacto correctos para los avisos.
- **Estimable:** tres rutas y una pantalla.
- **Pequeña:** cabe en un sprint.
- **Testeable:** 422 por campo prohibido, blob en base.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, anti IDOR, validación y envelope de error
- [ ] Front: pruebas de página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada
- [ ] Revisión de PR aprobada
