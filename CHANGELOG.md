# Changelog

Formato: una sección por versión, la más reciente primero. `scripts/ci/check-release-version.sh`
compara la etiqueta con el encabezado de la primera sección, con `api/pyproject.toml` y con
`web/package.json`. El SHA de cierre vive en el cuerpo de la sección (no lo exige ningún script) y
es el que se pasa a `infra/deploy.sh --expect-sha`.

## [0.1.0]

SHA de cierre: `<se completa en V12, cuando el orquestador crea la etiqueta v0.1.0>`

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
