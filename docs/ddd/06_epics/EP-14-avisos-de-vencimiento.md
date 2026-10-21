# EP-14 · Avisos de vencimiento

- **Versión del plan:** v0.2 (puntos 3, 4 y 5 de la versión 0.2; `BRECHAS.md` sección 2, "Avisos" y "Recuperación y activación de cuenta").
- **Bounded context:** Notifications (negocio, esquema `notifications`). Toca Members (preferencias de canal y suscripciones push) y Auth (envío de enlaces por correo).
- **Estimación relativa:** XL.

## Objetivo de negocio

Dejar de mandar los recordatorios de vencimiento uno por uno por WhatsApp cuando alguien se acuerda. El sistema genera cada día la lista de a quién avisar, envía solo lo que puede enviar (push, correo, Telegram) y deja listo el enlace de WhatsApp para lo demás. Menos socios entrenando vencidos y más renovaciones a tiempo.

## Actores

- Administrador: configura reglas, plantillas y canales; envía, omite y consulta el historial.
- Coach: ve "por avisar hoy", envía y omite (`ROUTES.md`: Avisos), no edita reglas.
- Worker: genera y envía los avisos a las 7:00.
- Socio: destinatario; sus preferencias de canal se respetan.

## Capacidades incluidas

### Backend
- Aggregates `NotificationRule` (`trigger` `membership_expiring` o `membership_expired`, `offset_days` -3, 0, 1, 7 y 15, `channel`, plantilla, `is_active`), `NotificationTemplate` (variables `{nombre}`, `{plan}`, `{vence}`, `{dias}`) y `Notification` (estados `pending`, `sent`, `failed`, `skipped`; intentos, último error, quién lo envió).
- Funciones puras `notifications.target_dates(rule, membership)` y `notifications.render(template, context)`.
- RN-17: un aviso único por regla, membresía y fecha objetivo (restricción en la base).
- Puerto `NotificationChannel` con `WebPushChannel` (pywebpush, MPL-2.0 sin modificar), `EmailChannel` (SMTP o API de Brevo), `TelegramChannel` (httpx directo, nunca python-telegram-bot por LGPL) y `WhatsAppLinkChannel` (genera el `wa.me`, no envía nada).
- Suscripción a `MembershipExpiring`, `MembershipExpired` y `MembershipActivated`.
- Job `worker/jobs/notify.py`: crea los avisos del día, envía los `pending` de canales automáticos, registra cada intento; si un canal falla, el aviso queda `failed` con `last_error` y aparece en "por avisar hoy". Correrlo dos veces no duplica (RN-17).
- Contacto vía `members.service.contact_for_notification(member_id, purpose)`, que audita el descifrado con propósito `notify`.
- Entidades de Members de v0.2: `PushSubscription` y `MemberChannelPreference`.
- Endpoints: CRUD de `/notification-rules` y `/notification-templates` (admin edita), `GET /notifications` (historial con filtros), `GET /notifications/today`, `GET /notifications/{id}/wa-link` (devuelve el enlace y marca `sent`), `POST /notifications/{id}/skip` con motivo obligatorio.
- Envío por correo de los enlaces de activación y recuperación de EP-04 a través de `EmailChannel`.
- Eventos `NotificationQueued`, `NotificationSent`, `NotificationFailed`, `NotificationSkipped`, todos auditados.
- Campo "por avisar hoy" del tablero (EP-12) con `notifications.today_count()`.
- Sección `channels` de Settings (EP-05) con su esquema.

### Front
- Pantalla "Por avisar hoy" con abrir WhatsApp, enviar y omitir con motivo.
- Pantalla de reglas y plantillas (edición solo admin) y pantalla de historial de envíos.
- Pestaña Avisos de la ficha del socio.
- Tarjetas "Olvidé mi contraseña" y "Nueva contraseña / Activar cuenta" del login con envío real por correo.
- KPI "Por avisar" de Inicio.

## Fuera de alcance

- Avisos de bienvenida, de confirmación de activación y de récords personales (no hay regla de negocio que los defina; ver preguntas abiertas).
- Envío desde el número de WhatsApp del gimnasio (API de WhatsApp Business): solo enlace.
- Suscripción del socio a web push desde el portal (EP-25).

## Criterios de éxito medibles

- Con `FrozenClock`, una membresía que vence el 20 de octubre genera avisos el 17, 20, 21 y 27 de octubre y el 4 de noviembre, según las reglas activas.
- Correr el job dos veces el mismo día no crea avisos duplicados (RN-17).
- Un canal caído deja el aviso en `failed` con el error y no detiene los demás envíos.
- Abrir el enlace de WhatsApp marca el aviso como `sent` con el usuario que lo envió; omitir sin motivo devuelve 422.
- Un socio con el correo desactivado como canal no recibe correo.
- Cada descifrado de contacto para avisar deja auditoría con propósito `notify`.
- E2E de Playwright: el coach abre "por avisar hoy", envía uno por WhatsApp y omite otro con motivo.

## Dependencias

- EP-09 Membresías (eventos de vencimiento y activación).
- EP-07 Padrón de socios (contacto y preferencias).
- EP-05 Configuración del gimnasio (sección `channels`).
- EP-13 Puesta en marcha y continuidad (proceso worker).
- EP-04 Identidad y acceso (tokens de un solo uso para enviar por correo).
- EP-12 Tablero de inicio (campo "por avisar").

## Riesgos

- El envío depende de servicios externos (SMTP, Brevo, Telegram) con internet intermitente; nada crítico debe depender de ellos (restricción no funcional).
- Credenciales de canales: si se guardan en Settings auditados pueden quedar en claro en la auditoría.
- Web push no tiene suscriptores hasta que exista el portal (EP-25).
- Si el envío síncrono bloquea peticiones, se mueve al worker con la tabla como cola (`04_architecture_decision.md` sección 3).

## Pantallas del diseño que habilita

- `PorAvisarHoy`, `Notif_Reglas`, `Notif_Historial`, pestaña Avisos de `Socio_Ficha`, tarjetas de recuperar y activar cuenta de `Login`, KPI "Por avisar" de `Inicio`.
