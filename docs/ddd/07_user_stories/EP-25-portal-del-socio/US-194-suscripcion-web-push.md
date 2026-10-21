# US-194 · Como socio quiero activar las notificaciones push del portal en mi celular para recibir los avisos sin depender del correo o de WhatsApp

- **Épica:** EP-25 · Portal del socio
- **Bounded context:** Notifications (esquema `notifications`) y Members (`PushSubscription`)
- **Versión:** v1.0
- **Actor:** socio
- **Tamaño:** 5
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Portal_Avisos` (`/mi/avisos`, interruptor "Notificaciones en este dispositivo")

## Historia

Como socio
quiero aceptar las notificaciones del navegador en mi celular
para que el aviso de vencimiento me llegue como push

## Contexto de dominio

- **Aggregate / entidades:** `PushSubscription` (entidad interna de Member: endpoint, llaves, `channel_enabled`), `NotificationRule` con `channel = push`, `Notification`.
- **Reglas que aplica:** Q14 (`WebPushChannel` y `push_subscriptions` se mueven a v1.0), Q12 (llaves VAPID solo en `.env`), RN-17, licencias (pywebpush MPL-2.0 sin modificar), RN-15.
- **Eventos que emite:** `NotificationSent`, `NotificationFailed` (por envíos push)
- **Eventos que consume:** ninguno nuevo (el job de avisos ya consume los de vencimiento)
- **Funciones puras:** ninguna nueva

## Alcance

- **Backend:** migración de `members.push_subscriptions`; `POST /me/push-subscription` y `DELETE /me/push-subscription`; `WebPushChannel` en `notifications/channels/` con pywebpush; el canal `push` se habilita en `notification-rules`; `GET /me/push-public-key` entrega la llave pública VAPID.
- **Front:** registro de service worker y suscripción con la Push API desde `Portal_Avisos`.

## Criterios de aceptación

1. `POST /api/v1/me/push-subscription` con `{ endpoint, keys: { p256dh, auth } }` guarda la suscripción del socio de la sesión (una por `endpoint`, idempotente) y responde 201; un endpoint que no es `https` devuelve 422.
2. Las llaves de la suscripción se guardan cifradas por el bus o como dato no sensible según Supuesto; el `endpoint` nunca aparece en logs.
3. `DELETE /api/v1/me/push-subscription` con `{ endpoint }` la elimina y responde 204 (es una preferencia, no un dato con prohibición de borrado).
4. Las reglas de aviso admiten `channel = push`; el job de avisos envía por `WebPushChannel` a todas las suscripciones activas del socio; una respuesta 404 o 410 del servicio push desactiva esa suscripción.
5. Un fallo de envío deja el aviso `failed` con `last_error` y no detiene los demás (mismo comportamiento de EP-14).
6. Las llaves VAPID privadas se leen solo de `.env`; `GET /api/v1/me/push-public-key` entrega solo la pública.
7. El chequeo de licencias de CI acepta pywebpush (MPL-2.0) y falla si se modifica su código.
8. Ninguna ruta acepta `member_id`; anti IDOR probado. Admin y coach reciben 403; sin token, 401.

## Escenarios BDD

```gherkin
# language: es
Característica: Suscripción web push

  Escenario: El socio activa push y recibe su aviso
    Dado que existe una regla de aviso por push tres días antes del vencimiento
    Y que "Laura" activó las notificaciones en su celular
    Cuando el job de avisos corre tres días antes de que venza su membresía
    Entonces "Laura" recibe una notificación push con el texto de la plantilla
    Y el aviso queda como enviado

  Escenario: Suscripción vencida en el navegador
    Dado que el servicio push responde que la suscripción de "Laura" ya no existe
    Cuando el job intenta enviarle un aviso
    Entonces el aviso queda fallido con el error
    Y la suscripción queda desactivada
```

## Endpoints

- `GET /api/v1/me/push-public-key` — rol(es): member — códigos: 200, 401, 403
- `POST /api/v1/me/push-subscription` — rol(es): member — entrada: `{ endpoint, keys }` — códigos: 201, 401, 403, 422
- `DELETE /api/v1/me/push-subscription` — rol(es): member — entrada: `{ endpoint }` — códigos: 204, 401, 403, 404

## Pantalla

- `Portal_Avisos`: interruptor "Notificaciones en este dispositivo" con estados "Activas", "Bloqueadas por el navegador" y "No compatibles".

## Notas técnicas

- **Migración:** sí; `members.push_subscriptions` (`member_id`, `endpoint` único, `p256dh`, `auth`, `channel_enabled`, columnas comunes).
- **Trigger / restricciones:** único por `endpoint`.
- **Funciones puras a probar:** mapeo de respuesta del servicio push a `sent`/`failed`/desactivar.
- **Pruebas:** canal con servidor push simulado (respx); job con `FrozenClock`; router con anti IDOR; Vitest del interruptor; licencias.
- **Archivos principales:** `api/src/app/modules/notifications/channels/webpush.py`, `members/models.py`, `web/src/features/portal/`, `web/public/sw.js`.

## Supuestos

- Supuesto: las llaves `p256dh` y `auth` de la suscripción se guardan en claro porque no son datos personales del padrón; si el gate las considera sensibles, se cifran con una `data_class` nueva.
- Supuesto: el portal se usa con TLS (EP-20); la Push API exige contexto seguro.

## Dependencias

- US-193 · Mis avisos y canales
- US-125 · Enviar avisos por correo (puerto de canal y job de envío)
- US-121 · reglas de aviso (el canal push entra en las reglas; agregado en consolidación)

## INVEST

- **Independiente:** agrega un adaptador al puerto existente.
- **Negociable:** cifrado de las llaves de suscripción.
- **Valiosa:** aviso inmediato en el celular.
- **Estimable:** un adaptador, una tabla y un interruptor.
- **Pequeña:** cabe en un sprint.
- **Testeable:** envío simulado y desactivación por 410.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, anti IDOR, validación y envelope de error
- [ ] Front: pruebas de componente; sin colores literales
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] `docs/openapi.json` regenerado
- [ ] Chequeo de licencias en verde
- [ ] Revisión de PR aprobada
