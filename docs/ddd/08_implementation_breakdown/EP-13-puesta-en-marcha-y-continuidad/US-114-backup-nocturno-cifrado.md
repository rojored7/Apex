# US-114 · Backup nocturno cifrado — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-13-puesta-en-marcha-y-continuidad/US-114-backup-nocturno-cifrado.md`
- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context / módulo:** ninguno; contenedor `backup` (`infra/backup/`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

Los tres supuestos de la historia los acepta N-50: 02:00 America/Bogota, 14 días de retención e inclusión de `uploads` desde v0.1. El destino es S3 compatible por `.env`, o local si no hay (P3, pendiente del gate, que se trata como supuesto aceptado). N-48 confirma que antes de v1.0 los backups no se firman. Las licencias de `age` (BSD-3-Clause) y `rclone` (MIT) están permitidas. La historia no toca código Python ni la base.

## Resumen

Se crea la imagen `infra/backup/Dockerfile`, basada en `postgres:16-alpine` para tener `pg_dump` 16, con `age`, `rclone` y `supercronic` (MIT) como programador. El script `infra/backup/run.sh` (`set -euo pipefail`):

1. Genera un `pg_dump --format=custom` de toda la base.
2. Empaqueta el dump y una copia de solo lectura de `/data/uploads` en un tar.
3. Cifra el tar con la llave pública `BACKUP_AGE_RECIPIENT` hacia un archivo temporal `.partial`.
4. Lo renombra a `apex-AAAAMMDD-HHMMSS.sql.age` solo si todo salió bien.
5. Calcula el sha256.
6. Lo sube con `rclone` si `BACKUP_RCLONE_REMOTE` está definido.
7. Aplica la retención local de `BACKUP_KEEP_DAYS` sin borrar nunca el último exitoso.
8. Escribe `latest.json` de forma atómica.

Las funciones puras del script (`backup_name`, `retention_to_delete`) se prueban con `bats`. El mismo script acepta `--prefix pre-deploy` para que US-117 lo reutilice.

## Correcciones aplicadas por DECISIONES.md

- Supuesto de la historia "hora 02:00 America/Bogota" → aceptado y fijo como valor por defecto de `BACKUP_CRON="0 2 * * *"` con `CRON_TZ=America/Bogota`: DECISIONES N-50.
- Supuesto "retención local de 14 días" → aceptado como `BACKUP_KEEP_DAYS=14`: DECISIONES N-50.
- Supuesto "`uploads` desde v0.1 aunque esté vacío" → aceptado: DECISIONES N-50.
- Destino S3 compatible por `.env`, o local si no hay → se mantiene como supuesto aceptado del gate: DECISIONES P3.
- Firma del backup → no se firma en v0.1; queda para v1.0 (EP-26, `backup.signature`): DECISIONES N-48.
- Alerta si el backup falla → en v0.1 solo el log del contenedor y `latest.json` (que lee US-115 para `/health`); Telegram interno llega en v0.2: DECISIONES N-34 y N-16.
- Licencias de `age` y `rclone` → se registran en `NOTICE` y en la lista permitida: DECISIONES N-49 (lista ampliada) y `CLAUDE.md`.

## Validación contra el dominio

- Sin aggregates. RN-13: los campos sensibles ya van cifrados por campo dentro del dump. El backup agrega una segunda capa de cifrado completa con `age`.
- Restricción no funcional "sin servicios en la nube obligatorios": sin `BACKUP_RCLONE_REMOTE` el backup queda local y el manifiesto marca `upload: "skipped"`.
- El backup no contiene la KEK: sin la KEK respaldada (US-116), los campos cifrados del dump no se pueden leer. Es correcto y se documenta.
- Funciones puras del script: `backup_name(now_utc) -> "apex-AAAAMMDD-HHMMSS.sql.age"` y `retention_to_delete(files, keep_days, now) -> lista`. Confirmado: sin discrepancias.

## Validación contra la arquitectura

- Contenedor aparte, según `04_architecture_decision.md` sección 4 ("backup: pg_dump nocturno, cifrado con age, subida con rclone"). No tiene código Python: no aplica la regla `banned-api`, y el cifrado con `age` vive fuera del api, que nunca ve la identidad privada.
- Secretos:
  - la contraseña de la base entra por `PGPASSWORD` desde `.env` o por un `PGPASSFILE` montado;
  - las credenciales de rclone, por `RCLONE_CONFIG_*` en `.env` o por un `rclone.conf` montado en solo lectura;
  - `BACKUP_AGE_RECIPIENT` es una llave pública y no es secreto;
  - nada se copia a la imagen (US-039).
- Volúmenes: `backups` (lectura y escritura), `uploads` (solo lectura), `pgdata` no se monta (el dump va por la red interna de Compose).
- Formato: un solo archivo por corrida. El nombre conserva `.sql.age` (criterio 2) aunque dentro hay un tar con `db.dump` y `uploads/`. `restore.sh` (US-116) conoce esta estructura.
- Manifiesto `latest.json` con `name`, `size_bytes`, `sha256`, `created_at` (UTC, ISO 8601 con `Z`), `upload` (`ok`, `skipped` o `failed`), `upload_error` y `format_version: 1`. Es el contrato con US-115 y US-117.
- Licencias: `age` BSD-3-Clause, `rclone` MIT, `supercronic` MIT, `postgres` (imagen base) PostgreSQL License, MinIO (Apache-2.0) solo en CI. El crond de busybox (GPL-2.0) no se usa.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `infra/backup/lib.sh`: funciones puras de shell `backup_name` (fecha UTC) y `retention_to_delete` (recibe la lista de archivos con fecha, `keep_days` y la fecha actual, y nunca devuelve el último exitoso del manifiesto) — 2 h
- [ ] T2 · `infra/backup/run.sh` con `set -euo pipefail` y `trap` que borra `*.partial`: `pg_dump --format=custom --no-owner` a un directorio temporal en `tmpfs`, `tar` de `db.dump` y `/data/uploads`, `age -r "$BACKUP_AGE_RECIPIENT" -o <nombre>.partial`, `mv` atómico al nombre final, `sha256sum`, escritura atómica de `latest.json` (`.tmp` y luego `mv`), y código distinto de 0 si `pg_dump`, `tar` o `age` fallan; opción `--prefix <p>` para US-117 (no actualiza `latest.json` cuando el prefijo no es `apex`) — 4 h
- [ ] T3 · `infra/backup/run.sh`: subida con `rclone copyto` si `BACKUP_RCLONE_REMOTE` no está vacío (`upload: "ok"` o `"failed"` con el error saneado), o `upload: "skipped"` si está vacío; retención local con `retention_to_delete` después de la subida — 1,5 h

### Schemas
- [ ] T4 · `infra/backup/manifest.schema.json`: JSON Schema de `latest.json` (`format_version` 1) versionado, contra el que se validan las pruebas de este script y de US-115 — 0,5 h

### Router
- No aplica.

### Tests unitarios puros
- [ ] T5 · `infra/backup/tests/lib.bats`: `backup_name` con `2026-10-21T07:00:05Z` → `apex-20261021-070005.sql.age`; `retention_to_delete` con 20 archivos y `keep_days=14` borra solo los de más de 14 días y nunca el último exitoso aunque sea viejo — 1,5 h

### Tests de service con PostgreSQL
- [ ] T6 · `infra/backup/tests/integration.bats` en CI (Compose de prueba con Postgres 16 y MinIO): backup con remoto produce el archivo local y el remoto con el mismo sha256 y `upload: "ok"`; sin remoto, `upload: "skipped"`; con remoto caído, el archivo local queda y `upload: "failed"`; `latest.json` valida contra T4 — 3 h
- [ ] T7 · `infra/backup/tests/integration.bats`: con la base detenida, `run.sh` sale con código distinto de 0 y no queda ningún archivo con nombre final ni `.partial`; el archivo producido no se descifra sin la identidad (`age -d` sin `-i` falla) y sí con la identidad de prueba; dentro están `db.dump` y `uploads/` — 2 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T8 · `shellcheck infra/backup/*.sh` en CI (US-003) y prueba de que la imagen no contiene archivos `*.key`, `rclone.conf` ni identidades `age` (`docker run --rm backup sh -c 'find / -name "*.age-identity" -o -name rclone.conf'` vacío) — 1 h

### Front
- No aplica.

### DevOps
- [ ] T9 · `infra/backup/Dockerfile`: `FROM postgres:16-alpine` con versión fijada, `age` y `rclone` desde paquetes de Alpine con versión fijada, `supercronic` descargado con checksum verificado, usuario no root, `ENTRYPOINT` con `supercronic /etc/backup/crontab` y `CRON_TZ=America/Bogota` — 2 h
- [ ] T10 · `infra/compose.yml`: servicio `backup` con `depends_on: db: condition: service_healthy`, volúmenes `backups` y `uploads:ro`, sin `ports`, `restart: unless-stopped`; variables `BACKUP_AGE_RECIPIENT`, `BACKUP_RCLONE_REMOTE`, `BACKUP_KEEP_DAYS=14`, `BACKUP_CRON="0 2 * * *"` y `RCLONE_CONFIG_*` documentadas en `.env.example`; `docker compose run --rm backup run.sh` funciona igual que la corrida programada — 1,5 h
- [ ] T11 · `NOTICE`: `age` (BSD-3-Clause), `rclone` (MIT), `supercronic` (MIT) y la imagen `postgres` (PostgreSQL License); regla en el chequeo de licencias de US-004 para binarios del contenedor de backup — 1 h

### Seguridad
- [ ] T12 · Revisión: `set -x` prohibido en los scripts; ningún `echo` de variables con credenciales; los mensajes de error de `rclone` se sanean (sin URL con credenciales); la llave privada `age` nunca se monta en este contenedor; el directorio temporal del dump es `tmpfs` y se borra en el `trap` — 1 h

## Orden de ejecución

1. T5 (en rojo), luego T1.
2. T4.
3. T9 y T10 (imagen y servicio).
4. T6 y T7 (en rojo), luego T2 y T3.
5. T8 y T11.
6. T12.

## Dependencias técnicas

- US-005 · Dockerfile del api y Compose: red interna, volúmenes `pgdata`, `uploads` y `backups`, healthcheck de `db`.
- US-003 · Pipeline de CI: jobs de `shellcheck` y de integración con Compose.
- US-004 · Chequeo de licencias y `NOTICE`.
- US-007 · `.env.example`.
- US-039 · Gestión de secretos (nada en la imagen).

## Endpoints

- Ninguno.

## Riesgos

- Respaldar la base sin respaldar la KEK es como no respaldar: el dump trae los campos cifrados — mitigación: US-116 (`export-kek` y prueba de restauración) es requisito para dar el backup por útil, y el documento de operación lo dice primero.
- Perder la identidad privada `age`: ningún backup se puede abrir — mitigación: US-116 documenta dos copias fuera del servidor.
- Disco lleno por la retención o por un `uploads` grande en v0.3: el backup falla — mitigación: el script sale con código distinto de 0, US-115 lo marca `missing` o `stale` en `/health`, y la retención corre después de cada backup exitoso.
- El nombre `.sql.age` no describe un tar — mitigación: `format_version` en el manifiesto y `restore.sh` validan la estructura; se conserva el nombre para no cambiar el criterio 2.
- Herramientas del sistema base de la imagen (por ejemplo `tar` y `sh` de Alpine) con licencias GPL — mitigación: son parte del sistema operativo de la imagen y no dependencias del proyecto; se anota en `NOTICE` y se confirma el criterio con US-004.

## Estimación

- Backend: 8 h
- Front: 0 h
- Pruebas: 7 h
- DevOps / seguridad: 6 h
- **Total: 21 h**

## Definición de hecho

- [ ] `shellcheck infra/backup/*.sh`
- [ ] `bats infra/backup/tests/lib.bats`
- [ ] `bats infra/backup/tests/integration.bats` (CI con Postgres 16 y MinIO)
- [ ] `docker compose -f infra/compose.yml run --rm backup run.sh` termina con código 0 y deja `apex-*.sql.age` y `latest.json` en el volumen `backups`
- [ ] `jq -e '.upload == "skipped"' latest.json` con `BACKUP_RCLONE_REMOTE` vacío
- [ ] `age -d -i <identidad de prueba> apex-*.sql.age | tar -t` lista `db.dump` y `uploads/`
- [ ] `docker compose logs backup | grep -Ei "password|secret|AGE-SECRET-KEY"` no devuelve nada
- [ ] `NOTICE` incluye `age`, `rclone` y `supercronic`, y el chequeo de licencias de US-004 pasa
