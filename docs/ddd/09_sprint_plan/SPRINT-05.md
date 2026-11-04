# Sprint 5 · v0.2: OpenBao, avisos de vencimiento, recibos y exportaciones

> **Corregido en S5-W0-1** (`docs/ddd/blueprints/sprint-05-plan.md`, sección 1, "Contradicciones de contrato cerradas en T-DOC", y decisiones S5-D64 a S5-D101; registro en `docs/ddd/DECISIONES.md`, "Sprint 5"). Donde el texto de abajo choque con estas notas, mandan las notas:
> - Migraciones `0015` a `0019` (S5-D66), no `0020`-`0039` ni `0030`/`0031`/`0035`; la guarda de `crypto_keys` se reemplaza en `0015` con `CREATE OR REPLACE FUNCTION`.
> - Slices y orden (S5-D67): W0-1, W0-2, W0-3, W0-4, B1, B13, B2, B3, B4, B5, B6, B7, B8, B9, B10, B11, B12; front F1, F2, F3, F5, F4 (S5-D84); validación V1 a V12. La sección "Slices y orden de ejecución" de abajo los lista.
> - Una sola llave de Transit, `apex-kek` (S5-D2); el puerto `KeyProvider` es `async` y conserva `wrap(dek)` y `unwrap(wrapped)`, sin `key_ref` (S5-D3).
> - Correo con `smtplib` en `asyncio.to_thread` (S5-D64) y PDF propio en `core/pdf.py` (S5-D65): sin `aiosmtplib`, `reportlab` ni `pillow`; `pypdf` solo en desarrollo.
> - `wa-link` es `POST /api/v1/notifications/{id}/wa-link` (S5-D59, M-9).
> - `/health` suma `crypto` (y ya lleva `migrations`); el sondeo cada 20 s con caché de 5 s (S5-D70); el healthcheck del api tolera el sellado (S5-D15).
> - Los comandos de CLI corren con `docker compose run --rm tools <comando>`; no hay `uv` en la imagen.
> - Las historias US-123 y US-126 pasan a READY (N-33 refinado y G-08 resueltos en el plan).

- Versión: v0.2.
- Épicas: EP-15 (custodia de llaves con OpenBao), EP-14 (avisos de vencimiento) y EP-16 (recibos y exportaciones).
- Tamaño: 20 historias, 78 puntos y 323 h relativas (EP-14, 186 h; EP-15, 83 h; EP-16, 54 h).
- Nivel de detalle: bloques en orden de ejecución y, desde S5-W0-1, los slices del plan de implementación (sección "Slices y orden de ejecución").
- Historias del sprint: US-120, US-121, US-122, US-123, US-124, US-125, US-126, US-127, US-128, US-129, US-130, US-131, US-132, US-133, US-134, US-135, US-136, US-137, US-138, US-139.

## Objetivo

Sacar la KEK del proceso del api y dejarla custodiada por OpenBao (Transit), con un estado degradado explícito cuando OpenBao está sellado.

Con eso, el box empieza a avisar los vencimientos con el consentimiento de Ley 1581:
- "por avisar hoy", con enlace de WhatsApp;
- correo automático solo con opt-in;
- resumen diario al chat interno del equipo por Telegram.

Además el sistema entrega recibos PDF y exportaciones CSV auditadas.

## Demo al final del sprint

1. **OpenBao.**
   - `docker compose up -d` levanta `openbao` sin puertos publicados, en la red interna `custody`.
   - `docker compose run --rm tools migrate-provider --as admin@...` mueve las DEK de `LocalFileProvider` a Transit y se puede reanudar; exige un snapshot firmado y verificado de OpenBao de menos de 24 h (S5-D49).
   - Al reiniciar el servidor (`restart openbao` y luego `restart api worker`, S5-D69), OpenBao queda sellado: `/health` muestra `crypto: sealed` y un `GET /members/{id}` responde 503 `crypto_unavailable`.
   - Después de desellar con 3 de las 5 llaves, todo vuelve en 25 s o menos.
   - `retire-local-kek` retira `kek.bin` y `compose.openbao.yml` deja api y worker sin la KEK local (S5-D50, S5-D73).
2. **Avisos.**
   - El job `notify` genera los avisos del día para `membership_expiring` y `membership_expired`, sin duplicar (RN-17).
   - "Por avisar hoy" lista los socios. "Enviar por WhatsApp" (`POST wa-link`) abre el enlace con el teléfono descifrado bajo el propósito `notify` y marca el aviso como enviado una sola vez.
   - "Omitir" pide un motivo.
   - Un socio con opt-in de correo y `data_consent_at` recibe el correo. Uno sin opt-in no lo recibe (N-33, refinamiento de US-123). Sin `data_consent_at` no se avisa por ningún canal y esos socios se listan aparte (S5-D31).
   - El chat interno de Telegram recibe el resumen diario, con conteos y sin nombres (N-34, G-08).
3. **Cuentas por correo.** `forgot` y la activación de cuentas envían el correo con texto fijo (N-36).
4. **Recibos y exportaciones.**
   - Descargar el recibo PDF de un pago (sin documento ni datos cifrados): dice "Comprobante interno de pago. No es factura electrónica." y queda auditado como `download` (N-08).
   - El admin exporta socios y pagos a CSV, con `;` y BOM, las columnas de N-29 y las fórmulas escapadas, auditado como `export` con el filtro y el número de filas.
   - El CSV de pagos del mes cuadra con `GET /payments/summary`.
5. **Inicio** muestra el KPI `notifications_today` y `members_without_consent` calculado (S5-D80).

## Dependencias de sprints anteriores

- **Sprints 4A y 4B (v0.1 cerrada):**
  - US-113 (worker y `job_runs`);
  - US-094 (vencimientos);
  - US-115 (campo `backup` de `/health`);
  - US-116 (respaldo de la KEK, que se exige antes de migrar de proveedor);
  - US-077 (`contact_for_notification`);
  - US-108 y US-109 (contrato del tablero);
  - US-102 (auditoría visible).
- **Sprint 3:**
  - US-084 y US-092 (membresías y estados);
  - US-095 a US-100 (pagos, filtros, detalle y `summary(month)`);
  - US-071 (filtros de socios);
  - US-073 (ficha).
- **Sprint 2:** US-036 (rate limit de `forgot`), US-047, US-048 y US-052 (tokens), US-054 y US-055 (Settings) y US-069 y US-070 (socios).
- **Sprint 1:** US-023 a US-029 (bus, `KeyProvider` y bitácora), US-020 (`register_health_check`) y US-034 (`require_role`).

## Historias en orden de ejecución (por bloques)

1. **Bloque A · OpenBao (EP-15).** Va primero, porque EP-14 y EP-16 usan el estado sellado de US-136.
   - US-133 · Servicio OpenBao con Transit:
     - Compose, `config.hcl` y `bootstrap.sh` con `--first-install` (S5-D76);
     - Shamir 5/3 (N-50), custodia 2/2/1 (S5-D106);
     - una sola llave `apex-kek` no exportable (S5-D2) y tokens por servicio con políticas mínimas (S5-D52).
   - US-134 · Proveedor OpenBao: `OpenBaoProvider` `async` con el puerto `KeyProvider` sin cambiar `wrap(dek)` ni `unwrap(wrapped)` (S5-D3), `rewrap`, `status` y la suite de contrato común.
   - US-135 · Migrar proveedor de llaves: `docker compose run --rm tools migrate-provider` reanudable, con una transacción por llave; precondiciones de H-1 y `retire-local-kek` (S5-D49, S5-D73).
   - US-136 · Estado degradado: 503 `crypto_unavailable`, campo `crypto` en `/health`, healthcheck del api tolerante, sondeo cada 20 s y caché de 5 s (S5-D70).
2. **Bloque B · Avisos (EP-14).**
   - US-120 · Plantillas de aviso.
   - US-121 · Reglas de aviso: CHECK de canal `email` o `whatsapp_link` (N-34).
   - US-122 · Configurar canales: `settings.channels`, sin secretos (Q12).
   - US-123 · Preferencias de canal del socio: refinamiento aceptado; el correo exige opt-in explícito además de `data_consent_at`.
   - US-124 · Generar avisos del día: idempotente con recuperación de 15 días, y sin avisar a quien ya renovó (N-35).
   - US-125 · Enviar avisos por correo: `smtplib` en `asyncio.to_thread` (S5-D64), 3 intentos.
   - US-126 · Telegram como canal interno: G-08 (`core/alerts.py`, `AlertSink`, `TelegramAlertSink` registrado en `main.py` y en `worker/main.py`).
   - US-127 · Por avisar hoy y enlace de WhatsApp.
   - US-128 · Omitir aviso con motivo.
   - US-129 · Historial de envíos.
   - US-130 · Pestaña Avisos de la ficha.
   - US-131 · Recuperar y activar cuenta por correo.
   - US-132 · KPI por avisar en Inicio.
3. **Bloque C · Recibos y exportaciones (EP-16).**
   - US-137 · Recibo PDF propio en `core/pdf.py`, sin documento (S5-D65).
   - US-138 · Exportar socios a CSV: descifra en lotes de 500, con streaming, tope de 20.000 filas y fila de cierre (S5-D82).
   - US-139 · Exportar pagos a CSV: usa `core/export.py`, compartido con US-138.

Waves:
- **Wave 0:** el servicio `openbao`, su volumen, los tokens periódicos por servicio en archivos 600 de solo lectura y el procedimiento de desellado en `docs/operacion/openbao.md`; la migración `0015`, `Settings`, los grants por columna y `apex_owner` NOSUPERUSER.
- **Waves 3a y 3b:** los bloques A, B y C en ese orden.
- **Waves 5a y 5b:** `PorAvisarHoy`, `Notif_Reglas`, `Notif_Historial`, la pestaña Avisos y la de Canales en `Config`, el botón de recibo en Pagos y la exportación en `Socios_Lista` y en `Pagos`.

## Slices y orden de ejecución (S5-D67)

Detalle, pasos y gates en `docs/ddd/blueprints/sprint-05-plan.md`. Un slice no empieza hasta el checkpoint del anterior en la misma rama.

- **Wave 0:**
  - W0-1 · Decisiones, T-DOC, licencias y ADR-005.
  - W0-2 · Infra OpenBao, redes, bootstrap, healthcheck tolerante y despliegue (US-133).
  - W0-3 · `0015`, `Settings`, entorno por servicio, redacción y grants por columna.
  - W0-4 · `apex_owner` NOSUPERUSER (M-12).
- **Backend, en este orden:**
  - B1 · `OpenBaoProvider` y puerto ampliado (US-134).
  - B13 · Respaldo de OpenBao y firma del manifiesto verificada (H-1); va antes de B2 porque `migrate-provider` lo exige.
  - B2 · `migrate-provider`, `rotate-kek` y `retire-local-kek` (US-135).
  - B3 · Estado sellado, `/health.crypto`, 503 `crypto_unavailable` y keyring del worker (US-136).
  - B4 · Canales: `core/mail.py`, `TelegramAlertSink` y `settings.channels` (US-122, US-125 parcial, US-126).
  - B5 · Preferencias de canal y contacto con `fields` (US-123), migración `0016`.
  - B6 · `notifications`: plantillas, reglas y siembra (US-120, US-121), migraciones `0017` y `0018`.
  - B7 · Generar, hoy, WhatsApp, omitir e historial (US-124, US-127 a US-130), migración `0019`.
  - B8 · Job `notify`, envío de correo y resumen (US-124, US-125, US-126).
  - B9 · Correos de cuenta (US-131).
  - B10 · KPI `notifications_today` y `members_without_consent` (US-132).
  - B11 · Recibo PDF propio (US-137).
  - B12 · Exportaciones CSV (US-138, US-139).
- **Front (worktree, S5-D84):** F1 Por avisar hoy (US-127, US-128); F2 reglas, plantillas, historial y pestaña Canales; F3 ficha, preferencias e Inicio; F5 cuentas por correo y aviso de custodio; F4 recibo y exportaciones (tras el checkpoint de B12).
- **Validación:** V1 fusión y documentos; V2 stack de cero y Alembic; V3 OpenBao (demo 1); V4 avisos y cuentas (demos 2 y 3); V5 E2E; V6 recibo y CSV (demo 4); V7 rendimiento; V8 revisión de base de datos; V9 gates completos; V10 revisiones; V11 `verify-delivery`; V12 limpieza y release (etiqueta `v0.2.0` local, S5-D93).

## Migraciones que aplica

Cinco migraciones, en este orden (S5-D66; la última antes del sprint es `0014_audit_log_triggers_always`). Los rangos reservados de los desgloses (0020 a 0039) se abandonan en favor de la secuencia real:
- `0015_crypto_provider_migration` (W0-3, US-134 y US-135): reemplaza con `CREATE OR REPLACE FUNCTION crypto.guard_keys_update()` la guarda de `0003` para permitir el cambio de `provider` y de `wrapped_material` (solo el par `local`/`openbao`, solo filas `encrypt` e `index`), con `downgrade` al texto de `0003`. No hace falta `crypto_jobs_single_running`: el índice único de jobs en curso ya existe.
- `0016_member_channel_preferences` (B5, US-123).
- `0017_notification_templates` (B6, US-120), con `CREATE SCHEMA notifications`.
- `0018_notification_rules` (B6, US-121).
- `0019_notifications` (B6, US-124; `membership_id NOT NULL`, N-37).
- Sin `0020`. EP-16 no necesita migración: `download` ya está en el CHECK de `0002` (N-08).

## Endpoints que expone

- **Notification templates:**
  - `GET /api/v1/notification-templates` y `POST /api/v1/notification-templates`;
  - `GET /api/v1/notification-templates/{id}` y `PATCH /api/v1/notification-templates/{id}`;
  - `POST /api/v1/notification-templates/preview`.
- **Notification rules:**
  - `GET /api/v1/notification-rules` y `POST /api/v1/notification-rules`;
  - `GET /api/v1/notification-rules/{id}` y `PATCH /api/v1/notification-rules/{id}`.
- **Notifications:**
  - `GET /api/v1/notifications`, `GET /api/v1/notifications/today` y `GET /api/v1/notifications/{id}`;
  - `POST /api/v1/notifications/{id}/wa-link`, con `no-store` (S5-D59: el front usa `useMutation` con `gcTime: 0`);
  - `POST /api/v1/notifications/{id}/skip`.
- **Settings:** `GET` y `PATCH /api/v1/settings/channels`.
- **Members:**
  - `GET /api/v1/members/{id}/channels` y `PATCH /api/v1/members/{id}/channels`;
  - `GET /api/v1/members/{id}/notifications`.
- **Exportaciones y recibos:**
  - `GET /api/v1/payments/{id}/receipt.pdf`;
  - `GET /api/v1/members/export`;
  - `GET /api/v1/payments/export`.
- **Cambios en endpoints de v0.1:**
  - `POST /api/v1/auth/forgot`, `POST /api/v1/users` y `POST /api/v1/users/{id}/resend-link` agregan el envío de correo y `email_sent`;
  - `GET /api/v1/dashboard` llena `notifications_today`;
  - `/health` agrega el campo `crypto` (`ok`, `sealed`, `unreachable` o `unknown`) junto a `migrations`.

## Tests de arquitectura que deben pasar

- Toda la suite de v0.1.
- La prueba de `core` sin módulos ya existe como `test_core_import_direction::test_core_no_importa_modulos`: `core/alerts.py` y `core/alerts_telegram.py` no importan `modules/notifications`.
- `test_every_route_has_role.py` sobre las rutas nuevas. `wa-link` es POST con efecto y requiere rol (admin o coach).
- La suite de contrato de `KeyProvider`, parametrizada para `LocalFileProvider` y `OpenBaoProvider`.
- `test_settings_no_secrets.py` sobre `settings.channels`.

## Riesgos y mitigación

1. [HIGH] Perder 3 de las 5 llaves de desellado equivale a perder todos los datos cifrados.
   - Mitigación:
     - guardarlas en dos lugares fuera del servidor;
     - ensayo de desellado documentado;
     - conservar el backup de la KEK local hasta verificar la migración.
2. [HIGH] Un reinicio deja OpenBao sellado y los datos ilegibles, con un operador no técnico.
   - Mitigación:
     - estado degradado explícito (US-136);
     - el healthcheck del api tolera el sellado (503 con `db` y `migrations` en `ok`), así que `web` y `worker` arrancan (S5-D15);
     - `deploy.sh` informa "api en estado sellado: desellar OpenBao";
     - procedimiento paso a paso.
3. [MEDIUM] Los canales externos (SMTP, Brevo, Telegram) son intermitentes.
   - Mitigación: una transacción por aviso, timeouts explícitos, reintento en la siguiente corrida, y el estado `failed` visible en "por avisar hoy".
4. [MEDIUM] Por diferencias de tiempo de respuesta en `forgot` se puede saber si un correo existe.
   - Mitigación: envío en `BackgroundTasks` después de responder 204, con prueba de que los tiempos son comparables.
5. [MEDIUM] Un CSV con datos en claro sale del sistema.
   - Mitigación: solo admin, confirmación, auditoría con filtro y número de filas, `no-store`, y escape de fórmulas.

## Definición de hecho del sprint

- La Definición de hecho común del README: `run-gates.sh`, suite de arquitectura, ciclo de Alembic, OpenAPI y licencias. La imagen de OpenBao se valida contra la lista de licencias (OpenBao: MPL-2.0 sin modificar); no hay dependencias de ejecución nuevas (`pypdf` solo en desarrollo, S5-D43).
- E2E:
  - "por avisar hoy" con WhatsApp y omitir (compartido entre US-127 y US-128);
  - recibo;
  - exportación.
- Smoke con OpenBao: migrar proveedor, "reinicio de servidor" (`restart openbao` y luego `restart api worker`, S5-D69), ver el 503, desellar y comprobar que todo vuelve. Se guarda la evidencia de `/health` en cada estado.
- `docker compose run --rm worker python -m app.worker.main --run-once notify` corre dos veces el mismo día sin duplicar avisos.
- Seguridad, revisada por `security-reviewer`:
  - el token de OpenBao no aparece en los logs ni en `crypto_ops`;
  - `last_error` sin secretos;
  - Telegram sin datos personales;
  - `wa-link` por POST y con `no-store`;
  - CSV con escape de fórmulas;
  - correo solo con opt-in y consentimiento.
- `verify-delivery` sobre el stack con OpenBao.
