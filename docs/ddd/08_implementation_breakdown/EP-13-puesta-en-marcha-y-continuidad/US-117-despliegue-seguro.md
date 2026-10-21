# US-117 · Despliegue seguro — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-13-puesta-en-marcha-y-continuidad/US-117-despliegue-seguro.md`
- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context / módulo:** ninguno; operación (`infra/deploy.sh`, `docs/operacion/actualizar.md`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

El script solo orquesta Compose y reutiliza el backup de US-114 y el `/health` de US-020. El contrato de `/health` (`db: "ok"`, 200 solo con migraciones en `head`, US-118) y el destino del backup están decididos (N-16, N-50, P3 como supuesto aceptado). No toca código del api ni la base, salvo leerla para el `pg_dump`.

## Resumen

Se escribe `infra/deploy.sh` con `set -euo pipefail`. El script:

1. Verifica que existan `.env` y el archivo de KEK (`CRYPTO_LOCAL_KEK_PATH`).
2. Genera un dump previo cifrado con el mismo `run.sh` de US-114 (`--prefix pre-deploy`, que no toca `latest.json`). Comprueba que el archivo existe, que su encabezado es `age` y, si el operador montó la identidad de verificación, que se descifra.
3. Guarda las etiquetas e ids de imagen actuales.
4. Ejecuta `docker compose pull` y `docker compose up -d`.
5. Espera hasta 120 s a que `/health` responda 200 con `db: "ok"`.

Si `/health` no responde, imprime los últimos 100 renglones del log del api, escribe `rollback-<fecha>.txt` con las etiquetas anteriores y el comando para volver, conserva el dump y sale con código distinto de 0. Nunca borra volúmenes ni restaura la base sola. Se agrega `docs/operacion/actualizar.md`.

## Correcciones aplicadas por DECISIONES.md

- Destino y nombre del dump previo → mismo cifrado `age` (`BACKUP_AGE_RECIPIENT`) y volumen `backups` del backup nocturno; se suben a `BACKUP_RCLONE_REMOTE` solo si está definido: aceptado por DECISIONES N-50 y P3.
- "Legible por la identidad `age`" (criterio 2) → se verifica por descifrado solo si el operador montó la identidad de verificación; si no, se verifica el encabezado `age-encryption.org/v1` y el tamaño: DECISIONES N-50 (la identidad se monta para verificar, y es opcional según US-115).
- `/health` consultado → `GET /api/v1/health` (también existe en la raíz); el estado del backup es informativo y no decide el despliegue: DECISIONES N-16.
- Firma del dump previo → no se firma antes de v1.0: DECISIONES N-48.

## Validación contra el dominio

- Sin aggregates ni reglas de negocio.
- Regla de datos 7: el api aplica `alembic upgrade head` al arrancar (US-020). El script no corre migraciones ni las edita.
- `CLAUDE.md`: el script se detiene ante lo irreversible. No restaura (criterio 6) y lo dice en su salida.
- Confirmado: sin discrepancias.

## Validación contra la arquitectura

- Operación pura sobre Compose (`04_architecture_decision.md` sección 4): no agrega servicios ni código al api.
- Reutiliza `infra/backup/run.sh` (US-114) por `docker compose run --rm backup run.sh --prefix pre-deploy`, así el cifrado está en un solo lugar.
- `/health`: consumido; el contrato `{status, db, version, backup}` es de US-020, US-115 y US-118. La versión desplegada que se imprime sale de `version`.
- Secretos: el script carga `.env` solo para pasar variables a Compose. Nunca las imprime (sin `set -x`) y no hace `cat` de `.env`.
- No aplica la regla `banned-api` (shell).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `infra/deploy.sh`: verificación previa (`.env` existe; `CRYPTO_LOCAL_KEK_PATH` existe y es legible solo por el dueño; `docker compose config -q` válido) y salida con código 2 sin tocar contenedores si algo falta — 1 h
- [ ] T2 · `infra/deploy.sh`: dump previo con `docker compose run --rm backup run.sh --prefix pre-deploy`; comprobación de encabezado `age` y tamaño, y descifrado de prueba si existe la identidad de verificación; aborta sin `pull` ni `up` si falla — 1,5 h
- [ ] T3 · `infra/deploy.sh`: registro de `docker compose images --format json` (etiqueta e id de cada servicio) en una variable y en `deploy-<fecha>.state.json`; `docker compose pull`; `docker compose up -d`; espera con sondeo cada 3 s hasta 120 s (`DEPLOY_HEALTH_TIMEOUT`) de `curl -fsS http://localhost/api/v1/health` con `jq -e '.db == "ok"'` — 1,5 h
- [ ] T4 · `infra/deploy.sh`: rama de fallo con `docker compose logs --tail 100 api`, `rollback-<fecha>.txt` (etiquetas anteriores y el comando `IMAGE_TAG=<anterior> docker compose up -d`, más la ruta del dump previo y el aviso de que restaurar la base es manual con `restore.sh` de US-116) y código 1; rama de éxito que imprime `version` y código 0; mensaje fijo "este script no restaura la base" en ambas — 1 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T5 · `infra/tests/deploy_unit.bats`: sin `.env` o sin KEK sale con 2 y no llama a `docker` (con `docker` simulado en `PATH`); el script no contiene `down -v`, `volume rm` ni `set -x` (búsqueda en el archivo) — 1 h

### Tests de service con PostgreSQL
- No aplica (no hay código de service; la base se prueba en T6).

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T6 · `infra/tests/deploy_e2e.sh` en CI (Compose de prueba con Postgres y un registro local): camino feliz de `0.1.0` a `0.1.1` deja `pre-deploy-*.sql.age` nuevo, `/health` en 200 y código 0; con una imagen `0.1.1-broken` cuyo api falla al arrancar, sale con código distinto de 0, crea `rollback-*.txt` con la etiqueta `0.1.0` y conserva el dump; con la base detenida, aborta antes del `pull` (no cambia el id de imagen) — 3 h

### Front
- No aplica.

### DevOps
- [ ] T7 · Variables `IMAGE_TAG` y `DEPLOY_HEALTH_TIMEOUT` (por defecto 120) en `infra/compose.yml` y `.env.example`; las imágenes del api y de `web` usan `${IMAGE_TAG}` para que volver atrás sea cambiar una variable — 0,5 h
- [ ] T8 · `docs/operacion/actualizar.md`: pasos simples (antes de actualizar, ejecutar, qué significa cada salida, cómo volver con `rollback-*.txt`, cuándo hace falta restaurar la base y que eso es una decisión que se pregunta) — 1,5 h

### Seguridad
- [ ] T9 · `shellcheck infra/deploy.sh` en CI; revisión de que ningún comando imprime el `.env` ni variables con `PASSWORD`, `SECRET` o `TOKEN`; el archivo `rollback-*.txt` no contiene secretos — 0,5 h

## Orden de ejecución

1. T5 (en rojo), luego T1.
2. T7.
3. T6 (en rojo), luego T2, T3 y T4.
4. T8 y T9.

## Dependencias técnicas

- US-114 · Backup nocturno cifrado: `run.sh` con `--prefix`, volumen `backups` e identidad `age`.
- US-020 · `/health` con `db` y `version`.
- US-118 · Arranque ordenado: `/health` responde 200 solo con migraciones en `head`, y los healthchecks.
- US-115 · Identidad de verificación opcional (para el descifrado de prueba del dump previo).
- US-116 · `restore.sh` (se nombra en `rollback-*.txt`; no se ejecuta).
- US-005 · Compose de producción.

## Endpoints

- Ninguno.

## Riesgos

- Una migración nueva que ya se aplicó y una imagen anterior que no la conoce: volver a la etiqueta anterior con un esquema más nuevo puede fallar — mitigación: `rollback-*.txt` advierte que, si la migración ya corrió, volver exige restaurar el dump previo (decisión manual, `CLAUDE.md`).
- `/health` responde 200 aunque el worker o `web` no arranquen — mitigación: el script además revisa `docker compose ps --format json` y avisa (sin fallar) si `worker` o `web` no están `running`.
- Disco lleno por dumps previos acumulados — mitigación: la retención de `run.sh` aplica también al prefijo `pre-deploy`, con el mismo `BACKUP_KEEP_DAYS`.
- Correr el script desde otro directorio: las rutas relativas fallan — mitigación: el script hace `cd` a la raíz del repositorio a partir de su propia ruta.

## Estimación

- Backend: 5 h
- Front: 0 h
- Pruebas: 4 h
- DevOps / seguridad: 3 h
- **Total: 12 h**

## Definición de hecho

- [ ] `shellcheck infra/deploy.sh`
- [ ] `bats infra/tests/deploy_unit.bats`
- [ ] `bash infra/tests/deploy_e2e.sh` en CI (éxito, api roto y base caída)
- [ ] En un servidor de prueba: `infra/deploy.sh; echo $?` imprime la versión y `0`, y `ls backups/pre-deploy-*.sql.age` muestra el dump nuevo
- [ ] Con KEK ausente, `infra/deploy.sh; echo $?` imprime `2` y `docker compose ps` no cambia
- [ ] `grep -nE "down -v|volume rm|set -x" infra/deploy.sh` no devuelve nada
- [ ] `docs/operacion/actualizar.md` existe y está enlazado desde el README
