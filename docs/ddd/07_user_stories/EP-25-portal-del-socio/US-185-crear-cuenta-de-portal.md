# US-185 · Como administrador quiero crear la cuenta de portal de un socio desde su ficha para que reciba por correo el enlace de activación

- **Épica:** EP-25 · Portal del socio
- **Bounded context:** Auth (esquema `auth`) en Partnership con Members
- **Versión:** v1.0
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Socio_Ficha` (`/socios/:id`, acción "Crear acceso al portal") y `Login` (`/restablecer/:token`, activación)

## Historia

Como administrador
quiero habilitar el acceso al portal de un socio con un clic desde su ficha
para que el socio active su cuenta con el enlace que le llega al correo y consulte lo suyo sin preguntar en recepción

## Contexto de dominio

- **Aggregate / entidades:** `User` (`role = member`, `member_id` obligatorio), `OneTimeToken(activate)`; Member.
- **Reglas que aplica:** invariante de User (`member_id` obligatorio si `role = member`), P5 (correo de login en claro en `auth.users.email`), RN-15, RN-14 (baja lógica), un usuario por socio.
- **Eventos que emite:** `UserCreated`
- **Eventos que consume:** ninguno (la creación es explícita; ver Supuesto sobre `MemberCreated`)
- **Funciones puras:** ninguna nueva

## Alcance

- **Backend:** `POST /members/{id}/portal-account` que llama a `auth.service.create_user(role=member, member_id, email)`; el correo lo pide Members por `members.service.contact_for_notification(id, purpose="portal_account")` (descifrado auditado) y Auth lo guarda en claro (P5); el enlace se envía por `EmailChannel` (US-131).
- **Front:** acción en la ficha visible solo para admin; muestra estado "Sin acceso", "Invitación enviada" o "Activo"; botón "Reenviar invitación" que usa `POST /users/{id}/resend-link`.

## Criterios de aceptación

1. `POST /api/v1/members/{id}/portal-account` con rol admin crea un `User` con `role = member`, `member_id = id`, `email` igual al correo descifrado del socio, sin contraseña utilizable, y responde 201 con `user_id` y `status = invited`.
2. En la misma transacción se crea un `OneTimeToken(purpose = activate)` y se encola un correo con el enlace `/restablecer/<token>`; si el envío falla, la cuenta queda creada y el aviso queda `failed` visible en el historial de avisos.
3. El descifrado del correo deja una fila de auditoría con propósito `portal_account`.
4. Un socio sin correo registrado devuelve 422 con `field = email`; un socio dado de baja devuelve 404.
5. Un socio que ya tiene usuario `member` no borrado devuelve 409 con `existing_id` del usuario.
6. Un correo ya usado por otro usuario devuelve 409.
7. Activar con el token fija la contraseña con argon2id; el token es de un solo uso y vence según la configuración de EP-04; un token usado o vencido devuelve error sin cambiar nada.
8. Tras activar, el login con rol `member` redirige a `/mi`.
9. Coach y member reciben 403; sin token, 401.
10. La creación queda auditada en `auth.users` sin `password_hash` en `after`.

## Escenarios BDD

```gherkin
# language: es
Característica: Crear cuenta de portal del socio

  Escenario: El administrador invita a un socio al portal
    Dado que la socia "Laura Gómez" tiene correo registrado y no tiene acceso al portal
    Cuando el administrador pulsa "Crear acceso al portal" en su ficha
    Entonces la ficha muestra "Invitación enviada"
    Y Laura recibe un correo con el enlace de activación
    Y al activar la cuenta con una contraseña nueva entra a "/mi"

  Escenario: Socio que ya tiene cuenta
    Dado que "Laura Gómez" ya tiene acceso al portal
    Cuando el administrador intenta crearle otra cuenta
    Entonces el sistema responde que ya existe y enlaza a la cuenta existente
```

## Endpoints

- `POST /api/v1/members/{id}/portal-account` — rol(es): admin — entrada: vacía — salida: `{ user_id, status }` — códigos: 201, 401, 403, 404, 409, 422
- `POST /api/v1/users/{id}/resend-link` — rol(es): admin — (existente, US-052)
- `POST /api/v1/auth/reset` — público — (existente, US-048)

## Pantalla

- `Socio_Ficha`: bloque "Acceso al portal" en el encabezado con el estado y la acción. `Login`: tarjeta "Activar cuenta" (US-048). `// DESIGN-GAP:` si el diseño no tiene el bloque de acceso al portal.

## Notas técnicas

- **Migración:** no (`auth.users.member_id` existe desde v0.1, S7); índice único parcial `users(member_id) WHERE deleted_at IS NULL AND role = 'member'` si no existe.
- **Trigger / restricciones:** índice único parcial anterior.
- **Funciones puras a probar:** ninguna nueva.
- **Pruebas:** service con base real (transacción, auditoría con propósito, 409); router; E2E Playwright del criterio de éxito de EP-25 (activar, entrar, ver plan, recibo y enviar resultado) empieza aquí.
- **Archivos principales:** `api/src/app/modules/members/router.py`, `auth/service.py`, `web/src/features/members/components/PortalAccess.tsx`.

## Supuestos

- Supuesto: la cuenta se crea solo por acción explícita del admin; no se crea automáticamente en `MemberCreated` para no enviar correos a socios que no la quieren.
- Supuesto: el endpoint `POST /members/{id}/portal-account` no está en el contrato; se define aquí.
- Supuesto: si el socio cambia su correo en el padrón, el correo de login no cambia solo (P5 los separa); se actualiza desde Usuarios.

## Dependencias

- US-047 · Crear usuario con enlace de activación
- US-131 · Recuperar y activar cuenta por correo
- US-073 · Ver ficha del socio

## INVEST

- **Independiente:** reutiliza usuarios y correo existentes.
- **Negociable:** creación explícita o automática.
- **Valiosa:** abre el portal al socio.
- **Estimable:** un endpoint y un bloque de ficha.
- **Pequeña:** cabe en un sprint.
- **Testeable:** 201, 409, 422, correo encolado.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para las tablas tocadas
- [ ] Revisión de PR aprobada
