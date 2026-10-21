# US-125 · Como administrador quiero que los avisos por correo se envíen solos y que los fallos queden registrados para que nadie tenga que mandarlos uno por uno

- **Épica:** EP-14 · Avisos de vencimiento
- **Bounded context:** Notifications (esquema `notifications`, `channels/`)
- **Versión:** v0.2
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (el estado se ve en `PorAvisarHoy` y `Notif_Historial`)

## Historia

Como administrador
quiero que el worker envíe por correo los avisos pendientes de canal `email` y reintente los fallidos
para que los socios reciban su recordatorio a tiempo y yo vea cuáles no salieron y por qué

## Contexto de dominio

- **Aggregate / entidades:** `Notification`; puerto `NotificationChannel` con adaptador `EmailChannel` (SMTP con `aiosmtplib` o API de Brevo con `httpx`).
- **Reglas que aplica:** Q12 (secretos solo en `.env`); RN-13 (descifrado de contacto auditado con propósito `notify`, vía `members.service.contact_for_notification`); restricción no funcional: nada crítico depende de servicios externos.
- **Eventos que emite:** `NotificationSent`, `NotificationFailed` (ambos auditados)
- **Eventos que consume:** ninguno
- **Funciones puras:** `notifications.next_attempt_allowed(attempts, max_attempts) -> bool`

## Alcance

- **Backend:** `channels/base.py` (Protocol `NotificationChannel.send(notification, contact) -> SendResult`), `channels/email.py`, fase 2 del job `notify` (enviar pendientes de canales automáticos), suscripción de auditoría a `NotificationSent/Failed`.
- **Front:** No aplica.

## Criterios de aceptación

1. El job envía cada `Notification` con `status = pending` y `channel = email` del día; al éxito queda `status = sent`, `sent_at` en UTC, `attempts + 1`, y se emite `NotificationSent`.
2. Si el envío falla (timeout, rechazo SMTP, 4xx/5xx de Brevo, correo ausente), queda `status = failed`, `attempts + 1`, `last_error` con un mensaje sin datos personales ni credenciales, y se emite `NotificationFailed`.
3. Un fallo en un aviso no detiene el envío de los demás.
4. Los avisos `failed` con `attempts` menor que el máximo se reintentan en la siguiente corrida del job; al llegar al máximo quedan `failed` definitivos y siguen visibles en "por avisar hoy".
5. El contacto se obtiene con `members.service.contact_for_notification(member_id, purpose="notify")`, que deja auditoría por descifrado; el correo descifrado nunca se guarda en `notifications` ni se escribe en logs.
6. Todas las llamadas HTTP o SMTP tienen timeout explícito configurable (por defecto 10 s).
7. Con `email.enabled = false` en `settings.channels` o sin credenciales en `.env`, no se intenta enviar; el aviso queda `failed` con `last_error = "credenciales ausentes"` o `skipped` si el canal está deshabilitado (US-124).
8. Cada `NotificationSent` y `NotificationFailed` deja una fila de auditoría.
9. El asunto usa `template.subject` renderizado; el cuerpo, `rendered_body`.
10. El envío ocurre en el worker, nunca en una petición HTTP del panel.

## Escenarios BDD

```gherkin
# language: es
Característica: Envío de avisos por correo

  Escenario: Enviar un aviso pendiente
    Dado que el correo está habilitado y con credenciales
    Y hay un aviso pendiente por correo para Laura Gómez
    Cuando el worker corre la fase de envío
    Entonces el aviso queda "sent" con fecha de envío
    Y queda auditado el descifrado del correo con propósito "notify"

  Escenario: Un servidor de correo caído no detiene los demás
    Dado que hay dos avisos pendientes por correo
    Y el servidor SMTP rechaza el primero
    Cuando el worker corre la fase de envío
    Entonces el primer aviso queda "failed" con el error registrado
    Y el segundo aviso queda "sent"
```

## Endpoints

- Ninguno. Job `worker/jobs/notify.py` (fase enviar); `cli notify --send-only`.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no (usa `notifications` de US-124).
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** `next_attempt_allowed` en el límite.
- **Pruebas:** `EmailChannel` contra un servidor SMTP de prueba en `compose.dev.yml` (por ejemplo Mailpit, MIT) y Brevo con `httpx.MockTransport`; job con `FrozenClock`; prueba de que logs y `last_error` no contienen el correo.
- **Archivos principales:** `api/src/app/modules/notifications/channels/{base,email}.py`, `api/src/app/worker/jobs/notify.py`.
- Licencias: `aiosmtplib` (MIT) o `httpx` (BSD).

## Supuestos

- Supuesto: máximo de 3 intentos por aviso (configurable `NOTIFY_MAX_ATTEMPTS`); el número no está definido en ningún documento.
- Supuesto: el proveedor (SMTP o Brevo) se elige por `.env` (`EMAIL_PROVIDER=smtp|brevo`).
- Supuesto: los reintentos ocurren en la siguiente corrida del job, no inmediatamente (no hay corrida intermedia definida).

## Dependencias

- US-124 · Generar avisos del día
- US-122 · Configurar canales de aviso
- US-077 · Contacto para avisos auditado

## INVEST

- **Independiente:** un canal aislado tras el puerto.
- **Negociable:** proveedor y número de reintentos.
- **Valiosa:** primer canal automático real.
- **Estimable:** adaptador conocido.
- **Pequeña:** 5.
- **Testeable:** estados y auditoría con servidor de prueba.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service y del canal con servidor de prueba en verde; cobertura de 80 % o más en lo tocado
- [ ] Licencias verificadas en CI
- [ ] Auditoría verificada (descifrado y eventos)
- [ ] Revisión de PR aprobada
