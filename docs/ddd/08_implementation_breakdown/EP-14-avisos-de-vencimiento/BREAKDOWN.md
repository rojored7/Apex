# EP-14 · Avisos de vencimiento — desglose técnico de épica

- **Épica:** `docs/ddd/06_epics/EP-14-avisos-de-vencimiento.md`
- **Versión:** v0.2
- **Historias:** US-120 a US-132 (13 historias, 44 puntos)

## Resumen

- Crea el módulo `api/src/app/modules/notifications/` (router, schemas, models, service, `channels/`) con tres aggregates: `NotificationTemplate`, `NotificationRule` y `Notification`.
- Cada mañana, después del job de vencimientos, el job `worker/jobs/notify.py` hace tres cosas. Genera los avisos del día sin duplicados (RN-17). Envía los de correo. Le manda al chat interno del equipo, por Telegram, el resumen de "por avisar hoy".
- Las personas resuelven el resto desde "Por avisar hoy": abren el enlace `wa.me` (y el aviso queda `sent` con su usuario) u omiten el aviso con un motivo.
- Agrega las preferencias de canal del socio en `members` (US-123), el envío directo de los correos de activación y recuperación de EP-04 (US-131) y el campo de avisos del tablero (US-132).
- DECISIONES.md cambia la forma de la épica en tres puntos:
  - web push sale a v1.0 (Q14);
  - `telegram` deja de ser canal al socio y pasa a ser un canal interno del equipo (N-34);
  - sin opt-in explícito, el socio solo recibe `whatsapp_link`, más correo si tiene `data_consent_at` (N-33).
- El N-34 deja una brecha arquitectónica en US-126: no existe `core/alerts.py` y, si se implementa a la ligera, `core` quedaría dependiendo de un módulo. Se propone un puerto que se registra al arrancar.

## Correcciones aplicadas por DECISIONES.md

- EP-14 y el modelo de dominio 2.10 incluyen `push`, `WebPushChannel` y `PushSubscription` en v0.2. En v0.2 los canales al socio son solo `email` y `whatsapp_link`; `push` y `push_subscriptions` se van a EP-25: corregido por DECISIONES Q14.
- La épica dice que el módulo se suscribe a `MembershipActivated` (aviso de confirmación). No hay handler ni regla para ese evento en v0.2; los disparadores son solo `membership_expiring` y `membership_expired`: corregido por DECISIONES Q13.
- US-121 (criterio 2), US-123 (criterio 1), US-124 (criterios 4 y 5), US-126 y US-127 (criterio 7) tratan `telegram` como canal al socio:
  - `NotificationRule.channel`, `Notification.channel` y `MemberChannelPreference.channel` solo admiten `email` y `whatsapp_link` (con un CHECK en la base);
  - `telegram` responde 422 igual que `push`;
  - Telegram solo lleva el resumen diario al chat del gimnasio y las alertas internas, a través de `core/alerts.py`.
  
  Corregido por DECISIONES N-34.
- US-123 (criterio 1 y supuesto) dice que un socio sin filas de preferencias acepta todos los canales. Sin preferencia guardada, el socio recibe `whatsapp_link` siempre y correo solo si tiene `data_consent_at`; los canales automáticos exigen opt-in explícito: corregido por DECISIONES N-33. La lectura exacta del caso "sin fila pero con consentimiento" queda como pregunta (ver US-123).
- US-123 (criterio 3) responde 404 para un socio dado de baja. Al socio dado de baja se le ve la ficha en solo lectura: `GET /members/{id}/channels` responde 200, y `PATCH` responde 409 `member_deleted` hasta que se reactive: corregido por DECISIONES N-20.
- US-077, que aquí se consume, dice que `user_id` va nulo cuando la llamada la hace el worker. Worker y CLI usan `SYSTEM_USER_ID` (`00000000-0000-0000-0000-000000000001`) como `user_id` en auditoría y en `crypto_ops`: corregido por DECISIONES N-15.
- `contact_for_notification` acepta los propósitos `notify`, `auth_link` y `mask`, y el propósito va en `after` de la auditoría `reveal`. Los avisos usan siempre `notify`: aplicado según DECISIONES N-21.
- Las credenciales del correo (SMTP o Brevo) y el token del bot de Telegram viven solo en `.env`. `settings.channels` guarda solo lo no secreto, con esquema cerrado: aplicado según DECISIONES Q12. Las llaves VAPID no entran en v0.2 (Q14).
- Supuestos de US-124 y US-125 que quedan como están: 3 intentos (`NOTIFY_MAX_ATTEMPTS`), recuperación de hasta 15 días sin correr y no avisar "vencido" a quien ya renovó: aceptados por DECISIONES N-35.
- Supuesto de US-131 que queda como está: los correos de activación y recuperación salen directo, no por la cola de avisos, y su texto es fijo en código: aceptado por DECISIONES N-36.
- N-37 hace opcional `Notification.membership_id`, pero eso es de v1.0. En v0.2 la columna se crea `NOT NULL`, y la migración que la vuelve nula le corresponde a EP-25 (rango 0090-0094): anotado según DECISIONES N-37.
- El "hoy" del generador, de "por avisar hoy" y del KPI es `today_bogota()`: aplicado según DECISIONES Q28.
- Esta corrección no viene de DECISIONES. US-132 llama al campo del tablero `to_notify_today`, pero el contrato de US-108 lo fija como `notifications_today`. US-132 misma dice que en ese caso manda US-108, así que se usa `notifications_today`.

## Validación contra el dominio y la arquitectura

Aggregates y reglas:
- Los tres aggregates (`NotificationTemplate`, `NotificationRule` y `Notification`) coinciden con el dominio 2.10, quitando `push` y `telegram` de los canales.
- RN-17 se cumple con un índice único (`rule_id`, `membership_id`, `target_date`) y una inserción con `ON CONFLICT DO NOTHING`. El evento `NotificationQueued` se emite solo para las filas que de verdad se insertaron (`RETURNING`).

Funciones puras, todas en `notifications/service.py` salvo la de members:
- `target_dates(rule, membership) -> list[date]`
- `render(template, context) -> str`
- `validate_template_vars(text) -> None | TemplateError`
- `validate_rule(trigger, offset_days, channel) -> None | RuleError`
- `next_attempt_allowed(attempts, max_attempts) -> bool`
- `can_skip(status) -> bool`
- `whatsapp.build_link(country_code, phone, text) -> str`
- `members.effective_channels(preferences, has_consent) -> set[Channel]`, en `members/service.py`.

Dependencias entre módulos:
- No se importa `models` de otro módulo. Notifications consulta a otros solo por sus services, y todas esas dependencias están en el mapa de contextos (Notifications → Members, Settings y Memberships):
  - `memberships.service.notification_candidates(...)` y `memberships.service.has_current_or_future(...)`;
  - `members.service.names_for(...)`, `members.service.channels_for(...)`, `members.service.contact_for_notification(...)` y `members.service.exists(...)`;
  - `settings.service.get_section("channels")`.
- La única escritura de cada operación cae en el esquema `notifications`. Los demás services se consultan por lotes, en un solo nivel y solo para leer. Es el mismo patrón que fijaron US-091 y US-098, así que no cuenta como encadenar services en una escritura.
- Auth → Notifications (US-131) es una dependencia nueva. Auth llama a `notifications.service.send_transactional_email(...)` y Notifications no conoce a Auth, así que no se forma ciclo.
- Settings no llama a Notifications. `credentials_present` lo calcula `settings.service` con una función pura sobre `core.config.Settings`; así se evita el ciclo Settings ↔ Notifications que sugería el alcance de US-122.
- Dashboard → `notifications.service.today_count(today)`. Es una composición de solo lectura, permitida.

Criptografía:
- Notifications nunca importa `core.crypto.bus` ni ninguna primitiva. El contacto llega en claro solo como valor de retorno de `members.service.contact_for_notification(member_id, purpose="notify")`, que audita `reveal` y escribe en `crypto_ops`. El test de US-077 lo vigila.
- El lint `banned-api` no cambia. Telegram y Brevo se llaman con `httpx` y el SMTP con `aiosmtplib`; ninguno es primitiva prohibida.

Auditoría, paginación y roles:
- Llevan `__audited__ = True` las tablas `notification_templates`, `notification_rules`, `notifications` y `member_channel_preferences`.
- `NotificationSent`, `NotificationFailed` y `NotificationSkipped` quedan auditados porque cambian una fila auditada en la misma transacción; no hace falta un handler de auditoría aparte.
- `rendered_body` contiene el nombre y el plan, pero ningún dato cifrado.
- Paginación con `limit` de 1 a 200 (25 por defecto) y `offset`, y respuesta `{items, total, limit, offset}` en las tres listas.
- Roles: admin escribe plantillas y reglas; admin y coach leen y gestionan avisos; el rol `member` recibe 403 en todo el módulo (su vista llega en EP-25).

Ajustes y brechas:
- Columna `rendered_subject` (nula para `whatsapp_link`). No está en el dominio 2.10, pero hace falta para el criterio 9 de US-125: el asunto se renderiza al generar el aviso, para que el correo no dependa de una plantilla editada después. Es un detalle de persistencia, no una regla nueva.
- Brecha en US-126 (N-34): las alertas internas tienen que salir de `core/alerts.py` → Telegram. Si `TelegramChannel` vive en `modules/notifications/channels/` y `core/alerts.py` lo importa, `core` depende de un módulo, y eso viola la regla 4 de módulos de `CLAUDE.md`. Además, el chat de destino está en `settings.channels`, que es un módulo. La propuesta está en "Estado y estimación por historia".

## Tablas y migraciones

- `0020_notifications_templates` (US-120):
  - `CREATE SCHEMA notifications`;
  - tabla `notifications.notification_templates`: `id` UUID, `name` texto, `subject` texto, `body` texto y columnas comunes (`created_at`, `updated_at`, `created_by`);
  - índice único en `name`;
  - sin `deleted_at`, porque las plantillas no se borran (supuesto de US-120, coherente con RN-14);
  - el downgrade borra la tabla y el esquema.
- `0021_notification_rules` (US-121):
  - tabla `notifications.notification_rules`: `id`, `name`, `trigger` (CHECK `membership_expiring` o `membership_expired`), `offset_days` int, `channel` (CHECK `email` o `whatsapp_link`, por N-34 y Q14), `template_id` (FK a `notification_templates`, mismo esquema), `is_active` bool y columnas comunes;
  - CHECK `(trigger = 'membership_expiring' AND offset_days <= 0) OR (trigger = 'membership_expired' AND offset_days >= 1)`;
  - índice único parcial (`trigger`, `offset_days`, `channel`) `WHERE is_active`.
- `0022_notifications` (US-124, con los índices de US-129):
  - tabla `notifications.notifications`: `id`, `rule_id` (FK a `notification_rules`), `member_id` UUID (sin FK entre esquemas), `membership_id` UUID `NOT NULL` (sin FK entre esquemas; N-37 la vuelve nula en EP-25), `target_date` DATE, `channel` (CHECK `email` o `whatsapp_link`), `status` (CHECK `pending`, `sent`, `failed` o `skipped`), `rendered_subject` texto nulo, `rendered_body` texto, `attempts` int default 0 (CHECK >= 0), `last_error` texto nulo, `sent_at` TIMESTAMPTZ nulo, `sent_by` UUID nulo, `skip_reason` texto nulo y columnas comunes;
  - único (`rule_id`, `membership_id`, `target_date`) para RN-17;
  - índices (`status`, `target_date`), (`member_id`, `target_date` DESC) y (`status`);
  - CHECK `status <> 'skipped' OR skip_reason IS NOT NULL`;
  - no hay trigger de inmutabilidad: las filas cambian de estado pero no se borran, y no hay endpoint `DELETE`.
- `0023_member_channel_preferences` (US-123):
  - tabla `members.member_channel_preferences`: `id`, `member_id` (FK a `members.members`, mismo esquema), `channel` (CHECK `email` o `whatsapp_link`), `active` bool y columnas comunes;
  - único (`member_id`, `channel`);
  - sin datos cifrados ni contacto.
- Sin migración:
  - la sección `channels` de Settings, que se crea con su valor por defecto en el primer `GET` (patrón de US-054);
  - las reglas y plantillas por defecto, que son un comando de CLI idempotente y auditado (regla de datos 8), no una migración.
- Para EP-25 (no se hace aquí): agregar `push` al CHECK de `channel` en reglas, avisos y preferencias, y volver nula `notifications.membership_id`.

## Services y eventos

Funciones puras, todas con prueba unitaria:
- `notifications.render(template, context) -> str`:
  - variables `{nombre}`, `{plan}`, `{vence}` (formato `20 oct 2026`) y `{dias}` (entero);
  - `{{` y `}}` sirven para escribir llaves literales;
  - una variable que falta en el contexto lanza `TemplateError`.
- `notifications.validate_template_vars(text)`: 422 con `field` igual a `subject` o `body`.
- `notifications.validate_rule(trigger, offset_days, channel)`: valida el signo del desfase según el disparador y el canal permitido.
- `notifications.target_dates(rule, membership) -> [end_date + offset_days]`.
- `notifications.days_value(end_date, target_date) -> int`: el valor absoluto de la diferencia, usado en `{dias}`.
- `notifications.next_attempt_allowed(attempts, max_attempts)`.
- `notifications.can_skip(status)`: verdadero solo para `pending` y `failed`.
- `notifications.channels.whatsapp_link.build_link(country_code, phone, text)`:
  - el teléfono queda en solo dígitos, sin anteponer el indicativo si ya viene;
  - el texto va con `quote`.
- `members.effective_channels(preferences, has_consent) -> set[Channel]` (N-33).
- `settings.channels_credentials_present(config) -> dict[channel, bool]`: no devuelve ningún valor secreto.

Casos de uso de `notifications.service`:
- Plantillas: `list_templates(q, limit, offset)`, `get_template(id)`, `create_template(data, by)` (409 `template_name_taken`), `update_template(id, data, by)` y `preview(subject, body)`, que usa un contexto fijo de ejemplo.
- Reglas: `list_rules(is_active, channel, trigger, limit, offset)`, `get_rule(id)`, `create_rule(data, by)` y `update_rule(id, data, by)` (409 `duplicate_active_rule`).
- `seed_defaults(by)`, que es idempotente:
  - crea las plantillas "Vence pronto" y "Venció" si no existen;
  - crea las cinco reglas: -3 y 0 con `membership_expiring`, y 1, 7 y 15 con `membership_expired`, todas por `whatsapp_link`.
- `generate_for(today, by=SYSTEM_USER_ID) -> GenerateResult`:
  - recorre las fechas desde `today - 15` hasta `today` (N-35);
  - pide `memberships.service.notification_candidates(on_dates)` → lista de (`membership_id`, `member_id`, `plan_name`, `end_date`, `status_on(date)`);
  - pide `memberships.service.has_current_or_future(member_ids, today)` para suprimir el aviso de vencido a quien ya renovó;
  - pide `members.service.names_for(ids)` (solo `first_name`) y `members.service.channels_for(member_ids)`;
  - lee `settings.service.get_section("channels")`;
  - renderiza el texto e inserta con `ON CONFLICT DO NOTHING ... RETURNING id`;
  - deja `skipped` con su motivo cuando el canal está desactivado por el socio o deshabilitado en Settings.
- `send_pending(today, by=SYSTEM_USER_ID)`: canal `email` en estado `pending`, y en estado `failed` con `next_attempt_allowed`. Cada aviso va en su propia transacción, para que un fallo no detenga los demás.
- `today_list(channel, status, limit, offset)`: avisos de hoy en `pending` o `failed`, más los `failed` de días anteriores sin resolver. Completa nombre, plan y `end_date` con consultas por lote a members y memberships.
- `today_count(today) -> int`: la misma consulta que `today_list`, contada.
- `wa_link(id, by) -> str`:
  - 409 si el aviso está `skipped`;
  - 422 `member_without_phone` si el socio no tiene teléfono;
  - pide `contact_for_notification(member_id, "notify", fields={"phone"})`;
  - marca `sent`, `sent_at` y `sent_by` solo la primera vez (idempotente) y conserva el `channel` original.
- `skip(id, reason, by)`: el motivo va de 3 a 500 caracteres después de recortar espacios; responde 409 si el aviso no está `pending` ni `failed`.
- `list(member_id, from, to, rule_id, channel, status, limit, offset)` y `get(id)`, que agrega `rendered_body`.
- `list_for_member(member_id, status, limit, offset)`: valida con `members.service.exists(member_id, include_deleted=True)`.
- `send_transactional_email(to, subject, body) -> bool` (N-36):
  - es directo, con timeout y sin pasar por la tabla `notifications`;
  - devuelve `False` si el correo está deshabilitado o falla;
  - deja un log sin datos personales.
- `daily_team_summary(today)`: resumen al chat interno a través de `core.alerts` (ver US-126).

Casos de uso de `members.service` (US-123):
- `get_channels(member_id)`.
- `set_channels(member_id, items, by)`: emite `MemberUpdated` y responde 409 `member_deleted` si el socio está dado de baja.
- `channels_for(member_ids) -> dict[member_id, set[Channel]]`: aplica `effective_channels` con `data_consent_at`.

Contratos nuevos que esta épica le pide a otras:
- `memberships.service.notification_candidates(on_dates: list[date]) -> list[Candidate]`: membresías no canceladas con `end_date + offset` en las fechas pedidas, y el estado calculado en cada fecha con `compute_status(..., expiring_days, freezes)`.
- `memberships.service.has_current_or_future(member_ids, today) -> set[UUID]`.
- `members.service.exists(id, include_deleted)`.
- Un parámetro opcional `fields` en `members.service.contact_for_notification`. Es compatible con lo anterior (por defecto, todos los campos) y evita descifrar el correo cuando solo se necesita el teléfono, y al revés.

Eventos (dataclasses congeladas en `notifications/service.py`):
- Emitidos: `NotificationQueued(notification_id, member_id, channel)`, `NotificationSent(notification_id, by)`, `NotificationFailed(notification_id, attempts)` y `NotificationSkipped(notification_id, by)`.
- Consumidos: ninguno en v0.2. El generador corre por tiempo y consulta el estado ya recalculado (`04_architecture_decision.md` sección 5); `MembershipExpiring` y `MembershipExpired` no hacen falta para que el resultado sea correcto (lo dice la nota de US-124). Es una discrepancia con el catálogo de eventos del dominio y se resuelve a favor de la arquitectura.

Puerto `NotificationChannel` (`channels/base.py`), con `send(notification, contact) -> SendResult(ok, error)`:
- `EmailChannel` (`channels/email.py`): SMTP con `aiosmtplib` (MIT) o la API de Brevo con `httpx` (BSD), según `EMAIL_PROVIDER=smtp|brevo`. Timeout por `NOTIFY_HTTP_TIMEOUT_S` (10 s por defecto). `last_error` se sanea para que no lleve correo, host ni credencial.
- `WhatsAppLinkChannel` (`channels/whatsapp_link.py`): no envía nada.
- `TelegramChannel` deja de ser adaptador de este puerto (N-34) y pasa a ser `TelegramAlertSink` (ver US-126).

## Endpoints

- `GET /api/v1/notification-templates` — roles: admin, coach
- `POST /api/v1/notification-templates` — roles: admin
- `GET /api/v1/notification-templates/{id}` — roles: admin, coach
- `PATCH /api/v1/notification-templates/{id}` — roles: admin
- `POST /api/v1/notification-templates/preview` — roles: admin
- `GET /api/v1/notification-rules` — roles: admin, coach
- `POST /api/v1/notification-rules` — roles: admin
- `GET /api/v1/notification-rules/{id}` — roles: admin, coach
- `PATCH /api/v1/notification-rules/{id}` — roles: admin
- `GET /api/v1/settings/channels` — roles: admin
- `PATCH /api/v1/settings/channels` — roles: admin
- `GET /api/v1/members/{id}/channels` — roles: admin, coach
- `PATCH /api/v1/members/{id}/channels` — roles: admin, coach
- `GET /api/v1/notifications/today` — roles: admin, coach
- `GET /api/v1/notifications/{id}/wa-link` — roles: admin, coach
- `POST /api/v1/notifications/{id}/skip` — roles: admin, coach
- `GET /api/v1/notifications` — roles: admin, coach
- `GET /api/v1/notifications/{id}` — roles: admin, coach
- `GET /api/v1/members/{id}/notifications` — roles: admin, coach
- `POST /api/v1/auth/forgot` — roles: público (lista blanca; cambia el envío, no el contrato)
- `POST /api/v1/users` — roles: admin (agrega `email_sent` a la salida)
- `POST /api/v1/users/{id}/resend-link` — roles: admin (agrega `email_sent` a la salida)
- `GET /api/v1/dashboard` — roles: admin, coach (`notifications_today` deja de ser `null`)

Notas de rutas:
- `/notifications/today` se registra antes de `/notifications/{id}`.
- `GET /members/{id}/notifications` vive en el router de `notifications`, que es el dueño del dato.
- `GET .../wa-link` tiene efecto (marca enviado), como dice el contrato de `ROUTES.md`. Responde con `Cache-Control: no-store` y queda documentado en OpenAPI.

## Componentes de front

Front condicionado a D1. Rutas de archivo:
- `web/src/features/notifications/api.ts`: hooks de TanStack Query `useTemplates`, `useTemplateMutation`, `usePreview`, `useRules`, `useRuleMutation`, `useToday`, `useWaLink`, `useSkip`, `useHistory` y `useMemberNotifications`.
- `web/src/features/notifications/schemas.ts`: Zod para plantilla (variables permitidas, validadas en el cliente), regla (signo del desfase) y motivo de omisión (3 a 500).
- `web/src/features/notifications/pages/RulesPage.tsx`:
  - pestañas Reglas y Plantillas (`Notif_Reglas`);
  - `SidePanel` de edición con vista previa en vivo;
  - una descripción en lenguaje natural ("3 días antes del vencimiento");
  - el coach la ve en solo lectura (`useCan`).
- `web/src/features/notifications/pages/TodayPage.tsx` (`PorAvisarHoy`, `/avisos/hoy`):
  - lista agrupada por regla, con `StatusTag` (Pendiente, Falló, Enviado);
  - botón Abrir WhatsApp de 44 px, que abre `wa.me` en una pestaña nueva solo después del 200;
  - botón Omitir.
- `web/src/features/notifications/components/SkipModal.tsx`: `ConfirmModal` con el motivo obligatorio; el botón queda deshabilitado mientras el campo esté vacío.
- `web/src/features/notifications/pages/HistoryPage.tsx` (`Notif_Historial`, `/avisos/historial`): `FilterBar` sincronizada con la URL, `DataTable`, `Pagination` y un `SidePanel` de detalle con el texto enviado.
- `web/src/features/members/tabs/NotificationsTab.tsx`: carga diferida (solo al abrir la pestaña); trae dentro el bloque `web/src/features/members/components/ChannelPreferences.tsx`, con un interruptor por canal (`email`, `whatsapp_link`) y su etiqueta de texto.
- `web/src/features/system/` (pestaña Canales de `Config`): interruptores, campos no secretos y una insignia de texto "Credenciales listas" o "Faltan credenciales en .env".
- `web/src/features/auth/pages/`: tarjetas de recuperar contraseña y de nueva contraseña o activar cuenta, con el mensaje neutro "Si el correo está registrado, te enviamos un enlace" y el estado de enlace inválido.
- `web/src/features/dashboard/`: `KpiCard` "Por avisar" con enlace a `/avisos/hoy` y el texto "Nadie por avisar" cuando el número es 0.
- Pruebas:
  - Vitest por página y componente;
  - Playwright `web/tests/e2e/avisos.spec.ts`: el coach abre "por avisar hoy", envía uno por WhatsApp y omite otro con motivo;
  - todo con tokens, sin colores literales.

## Worker, CLI e infraestructura

- `worker/jobs/notify.py` corre a las 07:00 en America/Bogota, después de `expirations` (US-094), con tres fases:
  - `generate` llama a `notifications.service.generate_for(today_bogota())`;
  - `send` llama a `send_pending(...)`, solo para correo;
  - `summary` llama a `daily_team_summary(...)` y manda el resumen al chat interno.
- Cada fase deja su resultado en `worker.job_runs.details`. Se omite la fase `send` si el bus está sellado (US-136), porque necesita descifrar contacto.
- CLI:
  - `cli notify [--generate-only | --send-only] [--as <email>]`;
  - `cli seed-notifications [--as <email>]`, idempotente y auditado.
  
  Sin `--as`, el actor es `SYSTEM_USER_ID` (N-15).
- `.env.example` agrega estas variables, vacías y documentadas: `EMAIL_PROVIDER`, `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `BREVO_API_KEY`, `TELEGRAM_BOT_TOKEN`, `NOTIFY_MAX_ATTEMPTS=3` y `NOTIFY_HTTP_TIMEOUT_S=10`.
- `core/config.py` lee los secretos como `SecretStr`, que nunca se serializa.
- `infra/compose.dev.yml` agrega Mailpit (MIT) como servidor SMTP de pruebas.
- Pruebas de Telegram y Brevo con `httpx.MockTransport`.
- Licencias:
  - el chequeo de CI rechaza `python-telegram-bot` (LGPL);
  - `aiosmtplib` (MIT) se agrega a `NOTICE`;
  - `pywebpush` no entra en v0.2 (Q14).
- Tests de arquitectura que siguen en verde: `api/tests/architecture/test_no_cross_models.py`, `test_every_route_has_role.py` y `test_banned_imports.py`.
- Tests de arquitectura nuevos:
  - `api/tests/architecture/test_notifications_no_bus.py`: `notifications` no importa `core.crypto`;
  - `api/tests/architecture/test_core_no_modules.py`: nada en `app.core` importa `app.modules`. Es el guardián de la propuesta de US-126.

## Dependencias

De v0.1:
- US-012 (mixin con id en Python), US-016 (hook de auditoría), US-034 (`require_role`) y US-017 (envelope de error).
- US-054 (secciones de Settings y patrón del valor por defecto).
- US-069, US-070 y US-073 (socios, `names_for` y ficha) y US-077 (`contact_for_notification`).
- US-084, US-092 y US-094 (membresías, estados y job de vencimientos).
- US-036 (rate limit de `forgot`) y US-047, US-048 y US-052 (tokens de activación y recuperación, y `resend-link`).
- US-061 y US-063 (layout, tabla, filtros y paginación del front).
- US-108 y US-109 (contrato y KPI del tablero).
- US-113 (worker y `job_runs`).

Entre historias de la épica:
- US-121 → US-120.
- US-124 → US-121 y US-094, con US-122 y US-123 como dependencias suaves.
- US-125 → US-124, US-122 y US-077.
- US-126 → US-125 y US-122.
- US-127 → US-124 y US-077.
- US-128 → US-127.
- US-129 → US-124.
- US-130 → US-129 y US-123.
- US-131 → US-125 y US-048.
- US-132 → US-124 y US-109.

De otras épicas:
- US-136 (EP-15): estado sellado del bus, para que el worker omita la fase `send`.
- EP-25 hereda el CHECK de canales y la nulabilidad de `membership_id` (N-37).
- US-141 y US-115 consumirán `core.alerts` si se aprueba la propuesta de US-126.

## Riesgos

- Front condicionado a D1: si el gate no aprueba S1, sale el front de 10 historias (unas 45 h).
- Servicios externos con internet intermitente (SMTP, Brevo, Telegram): un canal caído deja el aviso en `failed` sin detener los demás — mitigación: una transacción por aviso, timeouts explícitos, reintentos en la siguiente corrida y visibilidad en "por avisar hoy".
- El GET con efecto (`wa-link`): un prefetch del navegador o un proxy podría marcarlo enviado — mitigación: `Cache-Control: no-store`, la llamada solo se hace al pulsar y la marca es idempotente (no cambia `sent_at` ni `sent_by`).
- Descifrado de contacto en masa por el worker: cada descifrado es un `reveal` auditado y la tabla de auditoría crece — mitigación: `fields` para descifrar solo el campo del canal, y solo para los avisos `email` que se van a enviar.
- Fuga de secretos en `last_error` o en logs — mitigación: `SecretStr`, una función de saneo con prueba que busca el correo, el token y el host en `last_error` y en la salida de logs.
- Cadena de "hoy": si `notify` corre antes que `expirations`, los estados del día salen viejos — mitigación: el generador calcula `status_on(date)` con la función pura `compute_status` en `memberships.service`, sin depender del orden, y el worker igual los corre en secuencia.
- Diferencia de tiempos en `forgot`, que permite saber si un correo existe — mitigación: el envío va en `BackgroundTasks` después de responder 204 en todos los casos, con prueba de tiempo comparable.
- N-33 sin cerrar (US-123): si se elige la lectura literal, saldrían correos automáticos sin opt-in — mitigación: la propuesta por defecto es la más protectora.
- La brecha de US-126: si se implementa sin el puerto, `core` importa un módulo y se rompe la regla 4 — mitigación: el test `test_core_no_modules.py` entra en esta épica.

## Estado y estimación por historia

- US-120 · Plantillas de aviso — **READY** — 22 h — Esquema `notifications`, CRUD de plantillas con `render` puro y vista previa; sin borrado.
- US-121 · Reglas de aviso — **READY** — 21 h — CRUD con validación pura del signo y CHECK de canal `email` o `whatsapp_link` (corregido por N-34); el seed idempotente crea también las plantillas por defecto que exige la FK.
- US-122 · Configurar canales de aviso — **READY** — 9 h — Esquema cerrado de `settings.channels` (Q12) con `credentials_present` calculado en `settings.service` desde `core.config` para no crear el ciclo Settings ↔ Notifications.
- US-123 · Preferencias de canal del socio — **NEEDS_REFINEMENT** — 13 h — N-33 se contradice en el caso de un socio sin fila de preferencias y con `data_consent_at`. Pregunta: ¿recibe correo automático, o el correo exige además una fila `active = true` (opt-in explícito en la ficha)? Propuesta por defecto: el correo exige opt-in explícito y `data_consent_at`, y sin filas solo `whatsapp_link`. El contrato HTTP no cambia; solo cambia `effective_channels`.
- US-124 · Generar avisos del día — **READY** — 23 h — `generate_for` idempotente con `ON CONFLICT DO NOTHING` sobre RN-17. Recupera 15 días y no avisa a quien renovó (N-35). Necesita `memberships.service.notification_candidates` y `has_current_or_future`.
- US-125 · Enviar avisos por correo — **READY** — 20 h — `EmailChannel` (SMTP o Brevo), una transacción por aviso, 3 intentos y contacto solo por `contact_for_notification` con `fields={"email"}` y `SYSTEM_USER_ID` (N-15).
- US-126 · Enviar avisos por Telegram — **ARCHITECTURAL_GAP_DETECTED** — 12 h — Brecha: N-34 convierte Telegram en canal interno y manda las alertas por `core/alerts.py`, que no existe en la estructura de `CLAUDE.md` y que ninguna historia crea; si importa el canal de `modules/notifications`, `core` depende de un módulo. Propuesta:
  - `core/alerts.py` define el `Protocol` `AlertSink` y las funciones `register_sink(sink)` y `alert(kind, text)`, con `LogAlertSink` por defecto;
  - `modules/notifications/channels/telegram.py` implementa `TelegramAlertSink` con `httpx` directo, el token de `.env` y el chat de `settings.channels`;
  - `main.py` y `worker/main.py`, que son la raíz de composición, lo registran al arrancar;
  - el resumen diario lleva solo conteos por estado y el enlace a `/avisos/hoy`, sin nombres;
  - el resultado de cada envío queda en `worker.job_runs.details`, sin fila en `notifications`.
- US-127 · Por avisar hoy y enlace de WhatsApp — **READY** — 23 h — Lista de hoy y fallidos anteriores, y `wa-link` que descifra solo el teléfono con propósito `notify` y marca `sent` de forma idempotente; incluye el E2E compartido con US-128.
- US-128 · Omitir aviso con motivo — **READY** — 8 h — `skip` con `can_skip` puro, motivo de 3 a 500 caracteres, 409 si el aviso ya está cerrado y evento `NotificationSkipped` auditado.
- US-129 · Historial de envíos — **READY** — 12 h — Lista filtrada y paginada sin contacto, ordenada por `target_date` descendente; los índices van en `0022_notifications`, así que no hace falta otra migración.
- US-130 · Pestaña avisos de la ficha — **READY** — 7 h — Alias `GET /members/{id}/notifications` en el router de `notifications`; muestra el historial también para los dados de baja (N-20).
- US-131 · Recuperar y activar cuenta por correo — **READY** — 12 h — `notifications.service.send_transactional_email` directo con texto fijo (N-36). En `forgot` va en `BackgroundTasks` para que el tiempo de respuesta sea el mismo; en `create_user` y `resend-link` es síncrono y devuelve `email_sent`.
- US-132 · KPI por avisar en Inicio — **READY** — 4 h — `today_count` llena `notifications_today` (nombre de US-108, que manda sobre `to_notify_today`) sin cambiar el resto del contrato del tablero.

## Total de la épica

- **Total: 186 h**
