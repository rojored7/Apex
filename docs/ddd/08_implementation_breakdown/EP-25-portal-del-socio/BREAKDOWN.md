# EP-25 · Portal del socio — desglose técnico de épica

- **Épica:** `docs/ddd/06_epics/EP-25-portal-del-socio.md`
- **Versión:** v1.0
- **Historias:** US-185 a US-195 (11 historias, 45 puntos)

## Resumen

La épica abre el sistema al socio. Tiene cuatro bloques:

- Cuenta de portal creada por el admin (US-185), con enlace de activación por correo directo.
- Módulo de lectura `portal`, sin models, con todas las rutas `/me/*` bajo `require_role("member")` y el `member_id` sacado del usuario autenticado, nunca del cliente (US-186). Sobre él van inicio, pagos con recibo, WODs con envío de resultado, progreso, datos y contraseña, y avisos y canales (US-187 a US-193).
- Validación de resultados enviados en el panel (US-190), que alimenta RN-12.
- Web push: `members.push_subscriptions`, `WebPushChannel` y aviso de récord nuevo (US-194, US-195; Q14).

Cada ruta `/me/*` delega en un solo service dueño para escribir. Las lecturas compuestas (inicio) son las únicas que juntan varios services, como permite el mapa de contextos para `portal`.

## Correcciones aplicadas por DECISIONES.md

- US-185 encola el correo de activación y deja un aviso `failed` en el historial si falla → el enlace sale por correo directo con texto fijo, fuera de la cola de avisos (`auth.service` con `EmailChannel`, US-131); si el envío falla, la cuenta queda creada y la respuesta trae `email_sent = false` para que el admin use "Reenviar invitación": corregido por DECISIONES N-36.
- US-185 descifra el correo con propósito `portal_account` → usa el propósito existente `auth_link` de `members.service.contact_for_notification`: corregido por DECISIONES N-21.
- US-185: la cuenta la crea solo el admin y el correo de login no sigue al del padrón: aceptado por DECISIONES N-47 y P5 (supuesto del gate).
- US-186: un recurso ajeno pedido por id responde 404: aceptado por DECISIONES N-47.
- US-188: la descarga del recibo se audita como acción `download`, no `export`: corregido por DECISIONES N-08.
- US-189: el socio envía resultados del WOD de hoy y hasta 7 días atrás, sin asistencia obligatoria: aceptado por DECISIONES N-47. El índice único parcial `(wod_id, member_id) WHERE is_current` aplica también al envío: DECISIONES Q18.
- US-191 y US-192: el socio ve sus datos y medidas sin enmascarar y cada lectura se audita como `reveal`: confirmado por DECISIONES Q6. Todas las medidas cifradas: DECISIONES Q21.
- US-191 recibe `?wod=` en `/me/benchmarks` → recibe `?benchmark_id=`: corregido por DECISIONES N-46.
- US-192: campos editables solo teléfono, correo y contacto de emergencia (más canales en US-193 y contraseña); nunca documento, nombres, apellidos, sexo ni fecha de nacimiento: confirmado por DECISIONES Q24. Cambiar la contraseña revoca las demás sesiones: DECISIONES N-13. La normalización del índice de teléfono y correo es la de N-02.
- US-193 lista `telegram` entre los canales del socio → los canales al socio son `email`, `whatsapp_link` y `push`; `telegram` es solo canal interno del equipo: corregido por DECISIONES N-34. Sin preferencia guardada, el socio recibe solo `whatsapp_link` y `email` si tiene `data_consent_at`; activar un canal automático en el portal es el opt-in explícito: corregido por DECISIONES N-33.
- US-194: `WebPushChannel` y `push_subscriptions` entran en v1.0: DECISIONES Q14. Las llaves `p256dh` y `auth` se guardan en claro: aceptado por DECISIONES N-09. Llaves VAPID privadas solo en `.env`: DECISIONES Q12.
- US-195 crea el aviso de récord en un handler posterior al commit y con envío inmediato, sin revertir el récord si falla → el handler de `PersonalRecordSet` inserta la `Notification` en `pending` dentro de la misma transacción y el envío lo hace el job `notify` del worker; si el handler falla, se revierte la transacción completa (criterio 6 de la historia queda invertido): corregido por DECISIONES N-37. `Notification.membership_id` pasa a opcional: DECISIONES N-37. El aviso de récord es el que Q13 dejó para v1.0.

## Validación contra el dominio y la arquitectura

- Dominio: `User(role = member, member_id)` con `OneTimeToken(activate)` (2.11); `PushSubscription` y `MemberChannelPreference` como entidades internas de `Member` (2.1), por eso `push_subscriptions` vive en el esquema `members`; `WodResult` con `pending` y `validate` (2.8, RN-11); `Notification` con disparador `personal_record_set` y `membership_id` opcional (2.10, N-37).
- Módulo `portal`: `router.py`, `schemas.py`, `service.py`, sin `models.py` (mapa 1.15). Dependencia `current_member_id` que exige `require_role("member")`, carga el usuario por el `sub` firmado y comprueba que el usuario y su socio están activos (401 si no). Ningún esquema de entrada `/me/*` tiene `member_id` y todos usan `extra = "forbid"`. Escrituras: cada ruta `/me/*` que escribe llama a un solo service dueño (`results.submit`, `athletes.add_metric`, `members.update_own`, `members.set_channel_preferences`, `members.add_push_subscription`, `auth.change_password`); no se encadenan escrituras.
- Prevención de IDOR: los services de lectura reciben `member_id` como filtro obligatorio (`payments.service.list(member_id=...)`, `payments.service.receipt_pdf_for_member(id, member_id, by)` que responde NotFound si el pago no es del socio, `results.service.list_by_member`, `athletes.service.*`, `notifications.service.list(member_id=...)`). Prueba anti IDOR parametrizada por cada ruta `/me/*`.
- US-185, ubicación de la ruta: `POST /members/{id}/portal-account` se define en `auth/router.py` y lo atiende `auth.service.create_portal_account(member_id, by)`. Si viviera en `members`, `members.service` llamaría a `auth.service` y `auth.service` ya llama a `members.service` para validar `member_id`: ciclo de imports. Así solo existe `auth` → `members`, que es la dirección del mapa (Auth → Members, Partnership). Mismo patrón de US-173 (la ruta vive en el módulo que responde).
- US-185, estado en la ficha: el bloque "Acceso al portal" necesita leer el estado; se sirve con `GET /members/{id}/portal-account` en `auth/router.py` (lectura implícita en el alcance de front de la historia).
- US-190: `POST /results/{id}/validate` es del módulo `results` (Training), no de `portal`.
- Bus de criptografía: `GET /me` descifra por `members.service.get_own(member_id, by)` (una fila `reveal` con la lista de campos); `PATCH /me` recifra por el bus y recalcula `phone_idx` y `email_idx`; `/me/metrics` descifra por `athletes.service`. `portal` no importa `core.crypto`.
- Lint banned-api: `WebPushChannel` usa `pywebpush` (MPL-2.0 sin modificar), que internamente usa `cryptography`; el import directo de `cryptography` no aparece en `notifications`. Si `pywebpush` exige construir llaves con `cryptography` en nuestro código, ese paso vive en `core/crypto` (función `vapid_sign_headers` o carga de la llave VAPID) y el canal la llama.
- Roles: `/me/*` solo `member` (admin y coach reciben 403, P6); `member` recibe 403 en todas las rutas de panel (prueba de rutas con rol ampliada); `GET /wods/today` se abre a `member`.
- Paginación en todas las listas `/me/*`.
- Auditoría: `auth.users` (sin `password_hash` en `after`), `members.members`, `members.member_channel_preferences`, `members.push_subscriptions` (excluyendo `endpoint`, `p256dh` y `auth` del diff de auditoría), `results.wod_results`, `notifications.notifications`; descargas como `download` (N-08).

## Tablas y migraciones

- `0090_members_push_subscriptions` (US-194): `members.push_subscriptions` (`member_id` uuid, `endpoint` text, `p256dh` text, `auth` text, `channel_enabled` bool por defecto true, `user_agent` text nulo, `disabled_at` timestamptz nulo, columnas comunes); índice único sobre `endpoint`; índice `(member_id) WHERE channel_enabled`; CHECK `endpoint LIKE 'https://%'`.
- `0091_members_channel_preferences_push` (US-193, US-194): amplía el CHECK de `members.member_channel_preferences.channel` para admitir `push` (y sin `telegram`, si EP-14 no lo quitó ya al aplicar N-34).
- `0092_notification_rules_push_record` (US-194, US-195): amplía los CHECK de `notifications.notification_rules`: `channel` admite `push`, `trigger` admite `personal_record_set`; CHECK adicional de que `trigger = personal_record_set` exige `channel = push` y `offset_days = 0`.
- `0093_notifications_optional_membership_record` (US-195, N-37): `notifications.notifications.membership_id` pasa a nulo; columna `record_id` uuid nula; índice único parcial nuevo `(rule_id, membership_id, target_date) WHERE membership_id IS NOT NULL` creado antes de borrar la restricción única anterior (RN-17), en la misma migración; índice único parcial `(rule_id, record_id) WHERE record_id IS NOT NULL`; CHECK de que al menos uno de `membership_id` y `record_id` no es nulo.
- `0094_auth_users_member_unique` (US-185): índice único parcial `auth.users(member_id) WHERE deleted_at IS NULL AND role = 'member'` (no está en `0004_auth`).
- El rango 0090 a 0094 queda completo; si EP-14 ya dejó `push` en algún CHECK, la migración correspondiente se omite y se anota.

## Services y eventos

- `auth.service`: `create_portal_account(member_id, by) -> {user_id, status, email_sent}` (pide `members.service.contact_for_notification(member_id, purpose="auth_link")`; 422 `field = email` sin correo; 404 dado de baja; 409 `existing_id` si ya hay usuario `member`; 409 si el correo ya es de otro usuario; crea `User` sin contraseña utilizable y `OneTimeToken(activate)`; envía con `EmailChannel` directo); `portal_account_status(member_id) -> none | invited | active | locked`; `change_password(user, current, new)` reutilizado por `POST /me/password`.
- `portal.service`, función pura: `summary(current, future, last_payment, wod_today, balance_cop) -> MeSummary`.
- `portal.service`, lecturas compuestas: `summary(member_id)` con `memberships.service.current_and_future(member_id)` (consulta nueva), `payments.service.last_for_member(member_id)` (consulta nueva) y `wods.service.today()`.
- `results.service` (Training): `submit(member_id, data, by)` (nace `pending`, `is_current = true`; ventana `can_submit(wod_date, today_bogota())` de 0 a 7 días; 409 si hay vigente; emite solo `WodResultRecorded`); `validate(id, by)` (solo `pending` e `is_current`, 409 si no; fija `validated_by` y `validated_at`; emite `WodResultValidated` con el payload completo); `list_for_wod(..., status="pending")` para la bandeja. Funciones puras `can_submit` y `can_validate`.
- `members.service`: `get_own(member_id, by)` (descifra todos los campos propios y audita un `reveal` con la lista de campos), `update_own(member_id, data, by)` (lista blanca `phone`, `email`, `emergency_contact`; recifra e indexa; emite `MemberUpdated`), `channel_preferences(member_id)` y `set_channel_preferences(member_id, changes, by)`, `add_push_subscription(member_id, endpoint, keys, by)` (idempotente por `endpoint`), `remove_push_subscription(member_id, endpoint)`, `push_subscriptions_for(member_id)` y `disable_push_subscription(endpoint)` (para Notifications).
- `athletes.service` (de EP-24): `list_metrics_revealed(member_id, by)` (una fila `reveal` por petición con el número de registros), `add_metric(member_id, data, by, allowed_fields={"weight_kg", "notes"})`, `list_records`, `rms`, `benchmarks`.
- `payments.service`: `list(member_id=...)` existente, `receipt_pdf_for_member(payment_id, member_id, by)` (audita `download`).
- `notifications.service`: `list(member_id=...)` sin `skip_reason` en la proyección del portal; `vapid_public_key()`; `WebPushChannel` en `notifications/channels/webpush.py` (respuesta 404 o 410 llama a `members.service.disable_push_subscription`); handler `on_personal_record_set(event)` que, por cada regla activa con `trigger = personal_record_set`, inserta `Notification(pending, record_id, target_date = fecha Bogotá de achieved_at)` o `skipped` con `skip_reason = "sin canal"` si no hay suscripción activa o el canal está apagado; función pura `render` con `{movimiento}` y `{marca}`.
- Eventos emitidos: `UserCreated`, `MemberUpdated`, `PasswordChanged`, `SensitiveFieldRevealed`, `WodResultRecorded`, `WodResultValidated`, `NotificationQueued`, `NotificationSent`, `NotificationFailed`. Consumidos: `PersonalRecordSet` (notifications), `WodResultValidated` (athletes, EP-24).

## Endpoints

- `POST /api/v1/members/{id}/portal-account` — roles: admin
- `GET /api/v1/members/{id}/portal-account` — roles: admin
- `POST /api/v1/users/{id}/resend-link` — roles: admin
- `GET /api/v1/me/summary` — roles: member
- `GET /api/v1/me/payments` — roles: member
- `GET /api/v1/me/payments/{id}/receipt.pdf` — roles: member
- `GET /api/v1/wods/today` — roles: admin, coach, member
- `GET /api/v1/me/results` — roles: member
- `POST /api/v1/me/results` — roles: member
- `POST /api/v1/results/{id}/validate` — roles: admin, coach
- `GET /api/v1/wods/{id}/results` — roles: admin, coach
- `GET /api/v1/me/records` — roles: member
- `GET /api/v1/me/rms` — roles: member
- `GET /api/v1/me/benchmarks` — roles: member
- `GET /api/v1/me/metrics` — roles: member
- `POST /api/v1/me/metrics` — roles: member
- `GET /api/v1/me` — roles: member
- `PATCH /api/v1/me` — roles: member
- `POST /api/v1/me/password` — roles: member
- `GET /api/v1/me/notifications` — roles: member
- `GET /api/v1/me/channels` — roles: member
- `PATCH /api/v1/me/channels` — roles: member
- `GET /api/v1/me/push-public-key` — roles: member
- `POST /api/v1/me/push-subscription` — roles: member
- `DELETE /api/v1/me/push-subscription` — roles: member
- `POST /api/v1/notification-rules` — roles: admin
- `PATCH /api/v1/notification-rules/{id}` — roles: admin

## Componentes de front

- `web/src/features/members/components/PortalAccess.tsx` en `Socio_Ficha` (solo admin): estado "Sin acceso", "Invitación enviada", "Activo"; acción crear y "Reenviar invitación"; aviso si `email_sent = false`.
- `web/src/features/portal/`: `api.ts` (un hook por ruta `/me/*`), `schemas.ts` (Zod de envío de resultado por `score_type`, de medición con solo peso y notas, de datos editables y de contraseña), `pages/PortalHome.tsx`, `pages/PortalPayments.tsx` (descarga de recibo), `pages/PortalWods.tsx` (WOD de hoy, formulario adaptado, mis resultados con "Por validar"/"Validado"), `pages/PortalProgress.tsx` (récords, RMs, benchmarks, gráfica de peso con tokens, formulario "Registrar mi peso"), `pages/PortalData.tsx` (datos fijos con "Para corregirlos, acércate a recepción", editables, contraseña), `pages/PortalNotices.tsx` (avisos, interruptores por canal `email`, `whatsapp_link`, `push`), `components/PushToggle.tsx` ("Activas", "Bloqueadas por el navegador", "No compatibles"), todo en `PortalLayout` con menú inferior.
- `web/public/sw.js` (service worker de push) y su registro en `web/src/features/portal/lib/push.ts`.
- `web/src/features/results/components/PendingInbox.tsx` en `WOD_Detalle` y `Resultados_Registro` (contador con texto, "Validar" de 56 px en `GymLayout`, "Corregir" con US-170).
- Redirección por rol tras login: `member` va a `/mi` (`web/src/core/auth/`).
- `web/src/features/notifications/` (de EP-14): `Notif_Reglas` admite el disparador "Récord personal" y el canal push.
- Pruebas: Vitest por página; capturas en 390 × 844 en claro y oscuro; chequeo automático de accesibilidad (axe con Playwright); E2E `web/tests/e2e/portal.spec.ts` (activar cuenta, entrar, ver plan, descargar recibo, enviar resultado; coach valida y aparece en el leaderboard).

## Worker, CLI e infraestructura

- Worker: el job `notify` (EP-14) envía también por `WebPushChannel`; los avisos de récord salen en la siguiente corrida del job (N-37). Prueba con `FrozenClock` de que un canal desactivado deja de recibir desde la siguiente corrida.
- `.env.example`: `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT` (nunca en la base, Q12).
- Licencias: `pywebpush` (MPL-2.0) en la lista de permitidas sin modificar; `NOTICE` actualizado; `pip-licenses` en CI.
- Nginx: `sw.js` servido con `Service-Worker-Allowed: /` y sin caché agresiva; la CSP permite el registro del service worker.
- TLS (EP-20): la Push API exige contexto seguro; el portal fuera del local depende de EP-20.
- Pruebas de arquitectura: `api/tests/architecture/test_me_routes_owner_only.py` (toda ruta `/me/*` usa `current_member_id`, ningún esquema de entrada tiene `member_id`); `test_every_route_has_role.py` ampliada (un `member` recibe 403 en las rutas de panel); `test_no_cross_models.py` verde con `portal`.

## Dependencias

- EP-04 · US-041 (`auth.users.member_id`, S7), US-045 (cambiar contraseña), US-047 (crear usuario con activación), US-048 (`/auth/reset`), US-052 (`resend-link`, N-12).
- EP-07 · US-073 (ficha), US-074 (reveal), US-075 (editar socio con recifrado e índice), US-077 (`contact_for_notification`, propósito `auth_link`).
- EP-09 · US-092 (consultas de estado; se agrega `current_and_future`). EP-10 · US-095 (pagos; se agrega `last_for_member`).
- EP-14 · US-121 (reglas), US-123 (preferencias de canal), US-124 y US-125 (job `notify` y puerto de canal), US-129 (historial), US-131 (correo directo de activación).
- EP-16 · US-137 (recibo PDF).
- EP-20 · US-152 y US-153 (TLS para uso fuera del local y para push).
- EP-22 · US-168 (`GET /wods/today`), US-169 y US-170 (modelo, trigger, corrección), US-171 (leaderboard que solo muestra validados).
- EP-24 · US-179 (patrón de reveal), US-180 a US-184 (consultas de athletes), US-181 (emite `PersonalRecordSet`).
- EP-03 · US-034 y US-035. EP-06 · US-062 (`PortalLayout`).

## Riesgos

- Front condicionado a D1: si el gate no aprueba S1, salen las seis pantallas del portal, la bandeja y el service worker (unas 75 h).
- IDOR: una ruta `/me/*` nueva sin `current_member_id` expone datos de otros socios — mitigación: prueba de arquitectura que falla en CI y prueba anti IDOR parametrizada por ruta.
- P5 (supuesto del gate): correo de login en claro en `auth.users.email` mientras `members.email` va cifrado — mitigación: se documenta; si el gate lo revierte, US-185 cambia.
- Push de récord con retraso: con N-37 el aviso sale en la siguiente corrida del job `notify`; si ese job corre solo a las 07:00, el socio no "celebra en el momento" — mitigación: confirmar la frecuencia del job `notify` de EP-14 al planear v1.0 (no cambia el contrato).
- Validar resultados puede volverse trabajo pesado para el coach — mitigación: bandeja con contador en la tablet y en el detalle del WOD.
- Un envío `pending` del socio bloquea que el coach registre el mismo WOD en la tablet (409 por el índice parcial) — mitigación: la fila de la tablet muestra "Por validar" con acciones Validar y Corregir.
- La auditoría de `push_subscriptions` podría guardar el `endpoint` (URL con capacidad de envío) — mitigación: excluir `endpoint` y llaves del diff de auditoría y de los logs.
- Sin TLS (P7 y EP-20) el portal solo sirve dentro del local y la Push API no funciona fuera de `localhost`.

## Estado y estimación por historia

- US-185 · Crear cuenta de portal — **READY** — 20 h — Ruta en `auth/router.py` para evitar el ciclo `members` ↔ `auth`; correo directo con `email_sent` (corregido por N-36) y propósito `auth_link` (corregido por N-21).
- US-186 · Autorización propia en rutas me — **READY** — 12 h — `current_member_id`, `extra = "forbid"`, prueba de arquitectura y anti IDOR; ajeno 404 (N-47).
- US-187 · Inicio del portal — **READY** — 13 h — Lectura compuesta de memberships, payments y wods en `portal`, con dos consultas nuevas en los services dueños.
- US-188 · Mis pagos y recibos — **READY** — 11 h — Delegación a payments con filtro obligatorio; descarga auditada como `download` (corregido por N-08).
- US-189 · Mis WODs y enviar resultado — **READY** — 20 h — `results.submit` en `pending` con ventana de 7 días (N-47) e índice parcial (Q18).
- US-190 · Validar resultados enviados — **READY** — 18 h — `results.validate` con `WodResultValidated` en la transacción y bandeja en el panel.
- US-191 · Mi progreso — **READY** — 20 h — Rutas `/me/*` sobre athletes; medidas en claro auditadas (Q6); `benchmark_id` en vez de `wod` (corregido por N-46).
- US-192 · Mis datos y contraseña — **READY** — 20 h — Lista blanca de Q24, recifrado e índices (N-02), lectura auditada (Q6), revocación de sesiones (N-13).
- US-193 · Mis avisos y canales — **READY** — 12 h — Canales `email`, `whatsapp_link` y `push`, sin `telegram` (corregido por N-34) y con opt-in de N-33.
- US-194 · Suscripción web push — **READY** — 24 h — `members.push_subscriptions` con llaves en claro (N-09), `WebPushChannel` con pywebpush y canal push en reglas (Q14).
- US-195 · Aviso de récord nuevo — **READY** — 14 h — Handler de `PersonalRecordSet` que inserta `pending` en la misma transacción y envío por el job (corregido por N-37); `membership_id` opcional.

## Total de la épica

- **Total: 184 h**
