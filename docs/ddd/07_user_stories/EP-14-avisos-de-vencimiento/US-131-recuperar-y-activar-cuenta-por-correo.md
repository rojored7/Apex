# US-131 · Como coach quiero recibir por correo el enlace para activar mi cuenta o recuperar mi contraseña para no depender de que el administrador me lo pase a mano

- **Épica:** EP-14 · Avisos de vencimiento
- **Bounded context:** Auth (esquema `auth`) usando `EmailChannel` de Notifications
- **Versión:** v0.2
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Login` (`/recuperar`, `/restablecer/:token`)

## Historia

Como coach o administrador
quiero que el enlace de activación y el de recuperación lleguen a mi correo
para entrar al sistema o reponer mi contraseña sin que el enlace pase por chats inseguros

## Contexto de dominio

- **Aggregate / entidades:** `User`, `OneTimeToken` (`activate` | `reset`).
- **Reglas que aplica:** `forgot` siempre 204 (no revela si el correo existe); token de un solo uso con vencimiento (EP-04); Q12 (credenciales en `.env`); rate limit de `forgot` (US-036).
- **Eventos que emite:** ninguno nuevo (`UserCreated` ya existe)
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `auth.service.forgot` y `create_user` / `resend_link` envían el enlace con `EmailChannel` (envío directo, no por la cola de avisos).
- **Front:** tarjetas "Olvidé mi contraseña" y "Nueva contraseña / Activar cuenta" de `Login` con mensajes de envío real.

## Criterios de aceptación

1. `POST /api/v1/auth/forgot` con un correo de usuario activo genera `OneTimeToken(reset)` y envía un correo con el enlace `/restablecer/<token>`; con un correo inexistente, bloqueado o dado de baja no envía nada; en ambos casos responde 204 en tiempo comparable.
2. `POST /api/v1/users` y `POST /api/v1/users/{id}/resend-link` envían el enlace de activación al correo del usuario además de devolverlo al admin.
3. El token nunca aparece en logs ni en auditoría; solo su hash se guarda (`token_hash`).
4. Si el correo no está habilitado o falla, `forgot` igual responde 204 y deja un log de error sin datos personales; `create_user` responde 201 con `email_sent = false` para que el admin copie el enlace.
5. Un enlace usado o vencido muestra en `/restablecer/:token` el mensaje "El enlace ya no es válido" y ofrece pedir uno nuevo.
6. El sexto `forgot` en un minuto desde la misma IP responde 429.

## Escenarios BDD

```gherkin
# language: es
Característica: Recuperar contraseña por correo

  Escenario: Recuperar la contraseña con un correo registrado
    Dado que existe el coach "carlos@apex.co" activo
    Cuando pido recuperar la contraseña con "carlos@apex.co"
    Entonces la respuesta es 204
    Y llega un correo a "carlos@apex.co" con un enlace de restablecimiento

  Escenario: Correo no registrado
    Cuando pido recuperar la contraseña con "nadie@apex.co"
    Entonces la respuesta es 204
    Y no se envía ningún correo
```

## Endpoints

- `POST /api/v1/auth/forgot` — rol(es): público — códigos: 204, 422, 429
- `POST /api/v1/users` — rol(es): admin — salida agrega `email_sent` — códigos: 201, 401, 403, 409, 422
- `POST /api/v1/users/{id}/resend-link` — rol(es): admin — salida agrega `email_sent` — códigos: 200, 401, 403, 404

## Pantalla

- `Login`, tarjetas de recuperar y de nueva contraseña/activar: mensaje "Si el correo está registrado, te enviamos un enlace", estados de envío y de enlace inválido.

## Notas técnicas

- **Migración:** no.
- **Pruebas:** service con servidor SMTP de prueba (envía y no envía); prueba de tiempo comparable (sin diferencia mayor a un umbral razonable); router 204/429.
- **Archivos principales:** `api/src/app/modules/auth/service.py`, `web/src/features/auth/pages/`.
- Auth usa `notifications.service.send_transactional_email(...)` (llamada de service), no importa el canal directamente.

## Supuestos

- Supuesto: el envío transaccional es directo y síncrono con timeout, no pasa por la tabla `notifications` (no es un aviso de vencimiento).
- Supuesto: el texto del correo de activación y recuperación es fijo en código, no una `NotificationTemplate`.

## Dependencias

- US-125 · Enviar avisos por correo (`EmailChannel`)
- US-048 · Activar cuenta y restablecer contraseña

## INVEST

- **Independiente:** solo conecta el canal existente con Auth.
- **Negociable:** texto del correo.
- **Valiosa:** quita el paso manual inseguro.
- **Estimable:** cambios acotados.
- **Pequeña:** 3.
- **Testeable:** correo recibido o no.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service y router en verde; cobertura de 80 % o más en lo tocado
- [ ] Front: pruebas de las tarjetas; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
