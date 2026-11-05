# Changelog

Formato: una sección por versión, la más reciente primero. `scripts/ci/check-release-version.sh`
compara la etiqueta con el encabezado de la primera sección, con `api/pyproject.toml` y con
`web/package.json`. El SHA de cierre vive en el cuerpo de la sección (no lo exige ningún script) y
es el que se pasa a `infra/deploy.sh --expect-sha`.

## [0.2.0]

Fecha de cierre: 2026-11-05. SHA de cierre: el del commit etiquetado `v0.2.0` (`git rev-parse v0.2.0^{commit}`), publicado en el Release en borrador; es el valor que se pasa a `infra/deploy.sh --expect-sha`.

Segunda versión desplegable: custodia de llaves en OpenBao, avisos de vencimiento por correo y WhatsApp, cuentas por correo, recibo PDF y exportaciones CSV. El TLS sigue pendiente (riesgo aceptado P7).

### Sprint 5 · Custodia de llaves con OpenBao (EP-15)
- OpenBao (motor Transit, una llave `apex-kek`) como custodio de las DEK: `migrate-provider` reanudable, `rotate-kek` con `--trim` (unwrap + wrap, S5-D55a) y `retire-local-kek`, todos con pruebas de custodia (manifiesto firmado reciente con instantánea, S5-D72).
- Estado sellado: arranque degradado, `/health.crypto` crítico, 503 `crypto_unavailable` con `Retry-After: 30`, sondeo de recuperación cada 20 s; el worker arranca con el keyring mínimo.
- Instantánea raft de OpenBao en cada respaldo y `restore.sh --with-openbao`; `openbao-smoke.sh` y `openbao_restore_e2e.sh` en la CI y el smoke de producción.
- Roles de base de datos: `apex_owner` como propietario, `MIGRATE_DB_USER`/`TOOLS_DB_USER`, permisos por columna para `apex_api` y `apex_worker` (S5-D202 a D204, D256).

### Sprint 5 · Avisos de vencimiento (EP-14)
- Plantillas y reglas de aviso (`notification_templates`, `notification_rules`, `seed-notifications` idempotente), avisos del día generados por el job `notify` con candado por lote, envío por correo (SMTP con STARTTLS, al menos una vez, tope de 3 intentos) solo con consentimiento y opt-in del socio, enlace de WhatsApp por `POST /notifications/{id}/wa-link` auditado, omisión con motivo e historial por socio.
- Preferencias de canal por socio (`member_channel_preferences`) con consentimiento obligatorio; resumen diario del equipo por Telegram sin datos personales; KPI `notifications_today` y `members_without_consent` en el tablero.
- Correos de cuenta: activación y recuperación por SMTP (`email_sent` en el alta y el reenvío), `forgot` sin canal de tiempos (trabajo en segundo plano acotado, S5-D38, D91).
- Front: por avisar hoy, reglas y plantillas, historial, pestaña Canales de Config, pestaña Avisos de la ficha, KPI de Inicio, recuperar y activar cuenta por correo, aviso global de custodio no disponible.

### Sprint 5 · Recibos y exportaciones (EP-16)
- Recibo PDF propio (`core/pdf.py`, Courier sin incrustar, sin datos cifrados, auditado como `download`).
- Exportaciones CSV de socios y pagos en streaming (BOM, `;`, escape de fórmulas), un flujo por usuario (409), tope configurable, auditoría de apertura y cierre, `crypto_ops` por lote con `purpose=export`, cubetas `export*`; front con confirmación y descarga por `api.blob`.
- Migraciones 0015 a 0020 (proveedor de llaves, preferencias de canal, plantillas, reglas, avisos, índices).

### Deuda aceptada con dueño (v0.3)
- Índice `memberships(end_date)` y CHECK `sent ⇒ sent_at` en avisos; SMTP implícito (465); subruta del volumen `keys` para la llave JWT del worker; ADR-005 punto 2 (`rewrap`) por corregir.

## [0.1.0]

Fecha de cierre: 2026-11-04. SHA de cierre: el del commit etiquetado `v0.1.0` (`git rev-parse v0.1.0^{commit}`), publicado en el Release en borrador; es el valor que se pasa a `infra/deploy.sh --expect-sha` (ver `docs/operacion/actualizar.md`).

Primera versión desplegable: administración de un gimnasio de CrossFit (socios, planes,
membresías, pagos y vencimientos) con datos personales cifrados, auditoría verificable y
continuidad operativa. Despliegue de LAN sin TLS (riesgo aceptado P7); el TLS llega en v0.2.

### Sprint 0 · Terreno, gates y esqueleto ejecutable
- Repositorio, estructura de módulos, CI (lint, tipos, pruebas, licencias, imágenes) y los scripts de
  gate del flujo por slice.
- Stack de Compose con `db`, `api` y `web` (Nginx), `/health` y PostgreSQL 16 de prueba.

### Sprint 1 · Núcleo de auditoría, bus de criptografía y seguridad de plataforma
- Bitácora de auditoría con cadena de hashes y tablas inmutables.
- Bus de criptografía (`core/crypto`): AES-256-GCM por clase de dato, índices ciegos, llaves
  envueltas por una KEK local, `init-keys`.
- Argon2id, JWT Ed25519, roles, límites de intentos, cabeceras de seguridad.

### Sprint 2 · Identidad, configuración, socios y planes
- Login con refresh por cookie, usuarios del equipo con activación y recuperación por enlace.
- Configuración del gimnasio, alta y búsqueda de socios con los datos personales cifrados, planes.
- Shell del front (React 19) con las pantallas de acceso, usuarios, configuración, socios y planes.

### Sprint 3 · Núcleo comercial: membresías, pagos y ficha del socio
- Membresías (alta, renovación, congelamiento, cancelación) y pagos inmutables (anulación por
  `voided`, nunca borrado).
- Ficha del socio con revelado auditado de datos sensibles, límites por usuario, 503 `busy`.

### Sprint 4A · Worker, auditoría verificable, tablero y planes restantes
- Worker con APScheduler y `worker.job_runs`; vencimientos diarios.
- Verificación de la cadena de auditoría (`POST /audit/verify`, `verify-audit`), consulta de
  auditoría, tablero de inicio y `recompute-memberships`.

### Sprint 4B · Continuidad operativa y release
- Respaldo cifrado con `age` y manifiesto firmado con `minisign` (servicio `backup`), retención,
  subida opcional con `rclone copyto`; `backup_check` del worker y `backup` en `/health`.
- Respaldo de la KEK (`export-kek`, `verify-kek-backup`, `restore-kek`) y `restore.sh` con firma e
  inspección del tar.
- Rotación de llave reanudable (`rotate-key`) y `retire-key` con conteo confirmado.
- Datos de demostración (`seed --demo`) e importación de socios (`import-members`).
- Roles de base separados (`apex_api`, `apex_worker`, `apex_backup`), servicios `migrate` y
  `dbsetup`, entorno repartido en `.env` y `.env.ops`.
- `/health` con `migrations` (`ok|mismatch|unknown`).
- `infra/deploy.sh --ref vX.Y.Z --expect-sha <sha>` con respaldo previo, etiquetas `prev-*` y
  `rollback-*.txt`; `scripts/ci/prod-smoke.sh`, `release.yml`, ADR 001 a 004, guías de operación.
- Deuda del front de los sprints anteriores (F1).

### Fuera de esta versión
- TLS y Caddy (v0.2), firma de etiquetas con `.github/allowed_signers` (v0.2), OpenBao como KMS
  (v0.2), notificaciones al socio (v0.2), clases, WODs y portal (v0.4 en adelante).
