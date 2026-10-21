# US-193 · Como socio quiero ver los avisos que me ha enviado el gimnasio y elegir por qué canales recibirlos para enterarme de mis vencimientos por donde prefiero

- **Épica:** EP-25 · Portal del socio
- **Bounded context:** Portal (módulo `portal`), Notifications y Members
- **Versión:** v1.0
- **Actor:** socio
- **Tamaño:** 3
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Portal_Avisos` (`/mi/avisos`)

## Historia

Como socio
quiero ver mis avisos recientes y activar o desactivar los canales correo y WhatsApp
para recibir los recordatorios de vencimiento solo por donde me sirve

## Contexto de dominio

- **Aggregate / entidades:** `Notification` (lectura), `MemberChannelPreference`.
- **Reglas que aplica:** RN-17 (avisos idempotentes), "respeta las preferencias de canal del socio" (invariante de Notification), Q24 (preferencias de canal editables por el socio), RN-15.
- **Eventos que emite:** `MemberUpdated` (preferencias)
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna nueva

## Alcance

- **Backend:** `GET /me/notifications` delega en `notifications.service.list(member_id=...)`; `GET /me/channels` y `PATCH /me/channels` delegan en `members.service.channel_preferences` / `set_channel_preferences`.
- **Front:** `Portal_Avisos` con lista de avisos (fecha, canal, estado, texto) e interruptores por canal.

## Criterios de aceptación

1. `GET /api/v1/me/notifications?limit&offset` devuelve solo avisos del socio de la sesión con `target_date`, `channel`, `status` y `rendered_body`, ordenados por `target_date` descendente; paginado (`limit` 1 a 200, por defecto 25).
2. Los avisos `skipped` muestran el estado pero no el `skip_reason` (dato interno).
3. `GET /api/v1/me/channels` devuelve el estado de cada canal (`email`, `whatsapp_link`, y `push` cuando exista suscripción, US-194).
4. `PATCH /api/v1/me/channels` con `{ channel, active }` actualiza la preferencia y queda auditado; un canal fuera de la lista devuelve 422.
5. Desactivar `email` hace que el job de avisos no cree ni envíe avisos por correo a ese socio a partir de la siguiente corrida (prueba con `FrozenClock`).
6. Ninguna ruta acepta `member_id`; anti IDOR probado. Admin y coach reciben 403; sin token, 401.

## Escenarios BDD

```gherkin
# language: es
Característica: Mis avisos y canales

  Escenario: El socio desactiva el correo
    Dado que "Laura" tiene activo el canal correo
    Cuando desactiva el correo en "Mis avisos"
    Entonces su preferencia queda guardada
    Y el siguiente aviso de vencimiento no se le envía por correo

  Escenario: Canal inexistente
    Cuando "Laura" intenta activar el canal "sms"
    Entonces el sistema rechaza el cambio con error en "channel"
```

## Endpoints

- `GET /api/v1/me/notifications?limit&offset` — rol(es): member — códigos: 200, 401, 403, 422
- `GET /api/v1/me/channels` — rol(es): member — códigos: 200, 401, 403
- `PATCH /api/v1/me/channels` — rol(es): member — entrada: `{ channel, active }` — códigos: 200, 401, 403, 422

## Pantalla

- `Portal_Avisos`: lista de avisos e interruptores de 44 px con etiqueta de texto; estados de carga, vacío y error.

## Notas técnicas

- **Migración:** no (tabla de US-123).
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** ninguna nueva.
- **Pruebas:** service; router con anti IDOR; job con preferencia desactivada; Vitest de la página.
- **Archivos principales:** `api/src/app/modules/portal/router.py`, `web/src/features/portal/pages/PortalNotices.tsx`.

## Supuestos

- Supuesto: `GET /me/channels` no está en `ROUTES.md` (solo `PATCH`); se agrega para pintar el estado actual.
- Supuesto: el socio no ve `skip_reason` por ser un dato interno de recepción.

## Dependencias

- US-186 · Autorización propia en rutas me
- US-123 · Preferencias de canal del socio
- US-129 · Historial de envíos

## INVEST

- **Independiente:** delega en services existentes.
- **Negociable:** qué ve el socio de cada aviso.
- **Valiosa:** menos avisos ignorados.
- **Estimable:** tres rutas y una pantalla.
- **Pequeña:** pocos días.
- **Testeable:** preferencia respetada por el job.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, anti IDOR, validación y envelope de error
- [ ] Front: pruebas de página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada
- [ ] Revisión de PR aprobada
