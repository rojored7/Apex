# Sprint 5 · v0.2: OpenBao, avisos de vencimiento, recibos y exportaciones

- Versión: v0.2.
- Épicas: EP-15 (custodia de llaves con OpenBao), EP-14 (avisos de vencimiento) y EP-16 (recibos y exportaciones).
- Tamaño: 20 historias, 78 puntos y 323 h relativas (EP-14, 186 h; EP-15, 83 h; EP-16, 54 h).
- Nivel de detalle: bloques en orden de ejecución, sin slices. El sprint se refina al llegar: se cortan los slices sobre los `BREAKDOWN.md` y se agregan los BDD que faltan.
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
   - `docker compose up` levanta `openbao` sin puertos publicados.
   - `cli migrate-provider --as admin@...` mueve las DEK de `LocalFileProvider` a Transit y se puede reanudar.
   - Al reiniciar, OpenBao queda sellado: `/health` muestra `crypto: sealed` y un `GET /members/{id}` responde 503 `crypto_unavailable`.
   - Después de desellar con 3 de las 5 llaves, todo vuelve.
2. **Avisos.**
   - El job `notify` genera los avisos del día para `membership_expiring` y `membership_expired`, sin duplicar (RN-17).
   - "Por avisar hoy" lista los socios. "Enviar por WhatsApp" abre el enlace con el teléfono descifrado bajo el propósito `notify` y marca el aviso como enviado una sola vez.
   - "Omitir" pide un motivo.
   - Un socio con opt-in de correo y `data_consent_at` recibe el correo. Uno sin opt-in no lo recibe (N-33, refinamiento de US-123).
   - El chat interno de Telegram recibe el resumen diario, con conteos y sin nombres (N-34, G-08).
3. **Cuentas por correo.** `forgot` y la activación de cuentas envían el correo con texto fijo (N-36).
4. **Recibos y exportaciones.**
   - Descargar el recibo PDF de un pago: dice "Comprobante interno de pago. No es factura electrónica." y queda auditado como `download` (N-08).
   - El admin exporta socios y pagos a CSV, con `;` y BOM, las columnas de N-29 y las fórmulas escapadas, auditado como `export` con el filtro y el número de filas.
   - El CSV de pagos del mes cuadra con `GET /payments/summary`.
5. **Inicio** muestra el KPI `notifications_today`.

## Dependencias de sprints anteriores

- **Sprint 4 (v0.1 cerrada):**
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
     - Compose, `config.hcl` y `bootstrap.sh` idempotente;
     - Shamir 5/3 (N-50);
     - llaves por `data_class` no exportables.
   - US-134 · Proveedor OpenBao: ajusta `KeyProvider` a `wrap(key_ref, dek)` y `unwrap(key_ref, wrapped)`, y agrega la suite de contrato común.
   - US-135 · Migrar proveedor de llaves: `cli migrate-provider` reanudable, con una transacción por llave.
   - US-136 · Estado degradado: 503 `crypto_unavailable`, campo `crypto` en `/health` y sondeo cada 30 s.
2. **Bloque B · Avisos (EP-14).**
   - US-120 · Plantillas de aviso.
   - US-121 · Reglas de aviso: CHECK de canal `email` o `whatsapp_link` (N-34).
   - US-122 · Configurar canales: `settings.channels`, sin secretos (Q12).
   - US-123 · Preferencias de canal del socio: refinamiento aceptado; el correo exige opt-in explícito además de `data_consent_at`.
   - US-124 · Generar avisos del día: idempotente con recuperación de 15 días, y sin avisar a quien ya renovó (N-35).
   - US-125 · Enviar avisos por correo: SMTP o Brevo, 3 intentos.
   - US-126 · Telegram como canal interno: G-08 (`core/alerts.py`, `AlertSink`, `TelegramAlertSink` registrado en `main.py` y en `worker/main.py`).
   - US-127 · Por avisar hoy y enlace de WhatsApp.
   - US-128 · Omitir aviso con motivo.
   - US-129 · Historial de envíos.
   - US-130 · Pestaña Avisos de la ficha.
   - US-131 · Recuperar y activar cuenta por correo.
   - US-132 · KPI por avisar en Inicio.
3. **Bloque C · Recibos y exportaciones (EP-16).**
   - US-137 · Recibo PDF con `reportlab`.
   - US-138 · Exportar socios a CSV: descifra en lotes de 500, con streaming.
   - US-139 · Exportar pagos a CSV: usa `core/export.py`, compartido con US-138.

Waves:
- **Wave 0:** el servicio `openbao`, su volumen, el token periódico en un archivo 600 de solo lectura y el procedimiento de desellado en `docs/operacion/`.
- **Waves 3a y 3b:** los bloques A, B y C en ese orden.
- **Waves 5a y 5b:** `PorAvisarHoy`, `Notif_Reglas`, `Notif_Historial`, la pestaña Avisos y la de Canales en `Config`, el botón de recibo en Pagos y la exportación en `Socios_Lista` y en `Pagos`.

## Migraciones que aplica

Los rangos reservados (EP-14: 0020–0029; EP-15: 0030–0034; EP-16: 0035–0039) se ejecutan en el orden del sprint, con EP-15 primero. Como el número definitivo se fija al implementar (README del desglose), se numeran en orden de aplicación para que la secuencia quede ascendente:
- `crypto_jobs_single_running` (US-135) y `crypto_provider_openbao` (US-134), las del rango de EP-15. Si se respeta el número reservado, quedan como `0030` y `0031`; en ese caso EP-14 usa los números siguientes, `0032` en adelante. Se decide al refinar.
- `notifications_templates`, `notification_rules`, `notifications` (con `membership_id NOT NULL`, N-37) y `member_channel_preferences` (EP-14).
- EP-16 no necesita `0035_audit_action_download`: `download` ya está en el CHECK de `0002` (N-08).
- La función de guarda de `crypto_keys` de `0003` se extiende con una migración nueva, no se reemplaza (DECISIONES E), para permitir el cambio de `provider` y de `wrapped_material`.

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
  - `GET /api/v1/notifications/{id}/wa-link`, con `no-store`;
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
  - `/health` agrega el campo `crypto`.

## Tests de arquitectura que deben pasar

- Toda la suite de v0.1.
- La prueba de `core` sin módulos (`test_core_no_modules.py` en el desglose de EP-14), consolidada dentro de `test_core_import_direction.py`: `core/alerts.py` no importa `modules/notifications`.
- `test_every_route_has_role.py` sobre las rutas nuevas. `wa-link` es GET con efecto y sigue requiriendo rol.
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
     - Nginx no depende de la salud del api;
     - `deploy.sh` informa "api en estado sellado: desellar OpenBao";
     - procedimiento paso a paso.
3. [MEDIUM] Los canales externos (SMTP, Brevo, Telegram) son intermitentes.
   - Mitigación: una transacción por aviso, timeouts explícitos, reintento en la siguiente corrida, y el estado `failed` visible en "por avisar hoy".
4. [MEDIUM] Por diferencias de tiempo de respuesta en `forgot` se puede saber si un correo existe.
   - Mitigación: envío en `BackgroundTasks` después de responder 204, con prueba de que los tiempos son comparables.
5. [MEDIUM] Un CSV con datos en claro sale del sistema.
   - Mitigación: solo admin, confirmación, auditoría con filtro y número de filas, `no-store`, y escape de fórmulas.

## Definición de hecho del sprint

- La Definición de hecho común del README: `run-gates.sh`, suite de arquitectura, ciclo de Alembic, OpenAPI y licencias. `reportlab` y la imagen de OpenBao se validan contra la lista de licencias (OpenBao: MPL-2.0 sin modificar).
- E2E:
  - "por avisar hoy" con WhatsApp y omitir (compartido entre US-127 y US-128);
  - recibo;
  - exportación.
- Smoke con OpenBao: migrar proveedor, sellar, ver el 503, desellar y comprobar que todo vuelve. Se guarda la evidencia de `/health` en cada estado.
- El worker con `--run-once notify` corre dos veces el mismo día sin duplicar avisos.
- Seguridad, revisada por `security-reviewer`:
  - el token de OpenBao no aparece en los logs ni en `crypto_ops`;
  - `last_error` sin secretos;
  - Telegram sin datos personales;
  - `wa-link` con `no-store`;
  - CSV con escape de fórmulas;
  - correo solo con opt-in y consentimiento.
- `verify-delivery` sobre el stack con OpenBao.
