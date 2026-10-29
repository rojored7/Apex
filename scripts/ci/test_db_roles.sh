#!/usr/bin/env bash
# test_db_roles.sh
#
# Roles de aplicación contra un stack REAL (S4B-W0-3; S4B-D9, D61, D71, D100): corre `psql` dentro
# del servicio `db` como cada rol (`apex_api`, `apex_worker`, `apex_backup`) y comprueba que lo
# permitido funciona y lo prohibido falla con 42501. Las sentencias que escriben van dentro de
# `BEGIN; ... ROLLBACK;` (o con `WHERE false`): nunca deja datos. Las contraseñas salen del archivo
# de entorno (`.env.ops`, o `.env` si no existe: en desarrollo es la suma de los dos) y viajan solo
# en el entorno del comando (`PGPASSWORD` sin valor en `-e`); el script nunca las imprime.
#
# Corre en `prod-smoke` y en `e2e-stack` (que aplican `dbsetup`), nunca en `images` (S4B-D100).
# Variables: DC (comando compose; por defecto el de producción con los dos --env-file) y
# OPS_ENV_FILE (archivo con APEX_*_DB_PASSWORD y POSTGRES_DB). Hasta que existan los roles falla
# por rol inexistente (Rojo).
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
OPS_ENV_FILE="${OPS_ENV_FILE:-}"
if [ -z "$OPS_ENV_FILE" ]; then
  if [ -f .env.ops ]; then OPS_ENV_FILE=.env.ops; else OPS_ENV_FILE=.env; fi
fi
if [ -z "${DC:-}" ]; then
  if [ -f .env.ops ]; then
    DC="docker compose --env-file .env --env-file .env.ops -f infra/compose.yml"
  else
    DC="docker compose --env-file .env -f infra/compose.yml"
  fi
fi
[ -f "$OPS_ENV_FILE" ] || { echo "  FALLA no existe $OPS_ENV_FILE"; exit 1; }

valor() { # clave -> valor de OPS_ENV_FILE (sin comillas ni CR)
  grep -E "^$1=" "$OPS_ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '\r'
}
BASE="$(valor POSTGRES_DB)"
[ -n "$BASE" ] || BASE=apex
PW_API="$(valor APEX_API_DB_PASSWORD)"
PW_WORKER="$(valor APEX_WORKER_DB_PASSWORD)"
PW_BACKUP="$(valor APEX_BACKUP_DB_PASSWORD)"

fallas=0
ok() { echo "  ok   $1"; }
falla() { echo "  FALLA $1"; fallas=$((fallas + 1)); }

SALIDA=""
# psql_como <rol> <sql>: ejecuta como el rol; SALIDA = stdout+stderr con SQLSTATE; devuelve el código.
psql_como() {
  local rol="$1" sql="$2" pw
  case "$rol" in
    apex_api) pw="$PW_API" ;;
    apex_worker) pw="$PW_WORKER" ;;
    apex_backup) pw="$PW_BACKUP" ;;
    *) echo "rol desconocido $rol" >&2; return 2 ;;
  esac
  local rc
  SALIDA="$(PGPASSWORD="$pw" $DC exec -T -e PGPASSWORD db psql -X -At -h 127.0.0.1 \
    -v ON_ERROR_STOP=1 -v VERBOSITY=verbose -U "$rol" -d "$BASE" -c "$sql" 2>&1)"
  rc=$?
  SALIDA="${SALIDA//$'\r'/}"
  return "$rc"
}
transaccion() { printf 'BEGIN; %s; ROLLBACK;' "$1"; }

permitida() { # rol descripción sql
  if psql_como "$1" "$(transaccion "$3")"; then ok "$1 puede: $2"; else falla "$1 debía poder: $2 (${SALIDA:0:160})"; fi
}
prohibida() { # rol descripción sql
  if psql_como "$1" "$(transaccion "$3")"; then
    falla "$1 NO debía poder: $2"
  elif grep -q '42501' <<< "$SALIDA"; then
    ok "$1 no puede (42501): $2"
  else
    falla "$1 falló, pero no por privilegios (42501): $2 (${SALIDA:0:160})"
  fi
}

SYS='00000000-0000-0000-0000-000000000001'
AUDIT_INSERT="INSERT INTO audit.audit_log (id, seq, at, user_id, action, table_name, prev_hash, hash, created_at, updated_at, created_by) VALUES (gen_random_uuid(), (SELECT coalesce(max(seq), 0) + 1 FROM audit.audit_log), now(), '$SYS', 'login', 'auth.users', repeat('ab', 32), repeat('ab', 32), now(), now(), '$SYS')"
OPS_INSERT="INSERT INTO crypto.crypto_ops (id, created_by, user_id, verb, result) VALUES (gen_random_uuid(), '$SYS', '$SYS', 'encrypt', 'ok')"
JOB_INSERT="INSERT INTO worker.job_runs (id, created_by, job_name, run_date, started_at, result) VALUES (gen_random_uuid(), '$SYS', 'prueba_roles', current_date, now(), 'running')"

echo "test_db_roles: base $BASE, claves desde $OPS_ENV_FILE"
for rol in apex_api apex_worker apex_backup; do
  [ -n "$(valor "$(echo "$rol" | tr 'a-z' 'A-Z')_DB_PASSWORD")" ] || falla "$OPS_ENV_FILE sin la contraseña de $rol"
done

# --- atributos: ninguno es superusuario ni crea nada --------------------------------------------
for rol in apex_api apex_worker apex_backup; do
  if psql_como "$rol" "SELECT rolsuper, rolcreaterole, rolcreatedb, rolbypassrls FROM pg_roles WHERE rolname = current_user" \
    && [ "$SALIDA" = "f|f|f|f" ]; then
    ok "$rol sin superusuario, CREATEROLE, CREATEDB ni BYPASSRLS"
  else
    falla "$rol con atributos peligrosos o inexistente (${SALIDA:0:120})"
  fi
done

# --- apex_api -----------------------------------------------------------------------------------
permitida apex_api "SELECT en members.members" "SELECT count(*) FROM members.members"
permitida apex_api "INSERT en audit.audit_log" "$AUDIT_INSERT"
permitida apex_api "INSERT en crypto.crypto_ops" "$OPS_INSERT"
permitida apex_api "SELECT en public.alembic_version" "SELECT version_num FROM public.alembic_version"
permitida apex_api "SELECT en worker.job_runs" "SELECT count(*) FROM worker.job_runs"
permitida apex_api "SELECT ... FOR SHARE en crypto.crypto_keys" "SELECT id FROM crypto.crypto_keys FOR SHARE"
permitida apex_api "UPDATE (updated_at) en crypto.crypto_keys" "UPDATE crypto.crypto_keys SET updated_at = updated_at WHERE false"
permitida apex_api "DELETE en auth.refresh_tokens" "DELETE FROM auth.refresh_tokens WHERE false"
prohibida apex_api "ALTER TABLE audit.audit_log DISABLE TRIGGER ALL" "ALTER TABLE audit.audit_log DISABLE TRIGGER ALL"
prohibida apex_api "SET session_replication_role = replica" "SET session_replication_role = replica"
prohibida apex_api "TRUNCATE audit.audit_log" "TRUNCATE audit.audit_log"
prohibida apex_api "DELETE FROM payments.payments" "DELETE FROM payments.payments"
prohibida apex_api "UPDATE audit.audit_log" "UPDATE audit.audit_log SET action = 'x'"
prohibida apex_api "UPDATE crypto.crypto_keys SET state" "UPDATE crypto.crypto_keys SET state = 'retired'"
prohibida apex_api "UPDATE payments.payments SET amount_cop" "UPDATE payments.payments SET amount_cop = 1"
prohibida apex_api "UPDATE public.alembic_version" "UPDATE public.alembic_version SET version_num = 'x'"
prohibida apex_api "INSERT en worker.job_runs" "$JOB_INSERT"
prohibida apex_api "CREATE TABLE public.x()" "CREATE TABLE public.x()"

# --- apex_worker --------------------------------------------------------------------------------
prohibida apex_worker "UPDATE members.members SET first_name" "UPDATE members.members SET first_name = 'x'"
prohibida apex_worker "UPDATE members.members SET updated_at" "UPDATE members.members SET updated_at = now() WHERE false"
permitida apex_worker "UPDATE memberships.memberships SET status" "UPDATE memberships.memberships SET status = status"
prohibida apex_worker "SELECT ... FOR UPDATE en members.members" "SELECT id FROM members.members FOR UPDATE"
permitida apex_worker "SELECT ... FOR UPDATE en memberships.memberships" "SELECT id FROM memberships.memberships FOR UPDATE"
permitida apex_worker "INSERT en worker.job_runs" "$JOB_INSERT"
permitida apex_worker "INSERT en audit.audit_log" "$AUDIT_INSERT"
prohibida apex_worker "SELECT en payments.payments" "SELECT count(*) FROM payments.payments"
prohibida apex_worker "SELECT en crypto.crypto_keys" "SELECT count(*) FROM crypto.crypto_keys"
prohibida apex_worker "DELETE en worker.job_runs" "DELETE FROM worker.job_runs"

# --- apex_backup: lee todo, no escribe nada -----------------------------------------------------
for tabla in audit.audit_log auth.users crypto.crypto_keys members.members memberships.memberships payments.payments plans.plans settings.settings_sections worker.job_runs public.alembic_version; do
  permitida apex_backup "SELECT en $tabla" "SELECT count(*) FROM $tabla"
done
prohibida apex_backup "INSERT en audit.audit_log" "$AUDIT_INSERT"
prohibida apex_backup "INSERT en worker.job_runs" "$JOB_INSERT"
prohibida apex_backup "UPDATE members.members" "UPDATE members.members SET updated_at = now() WHERE false"
prohibida apex_backup "DELETE en auth.refresh_tokens" "DELETE FROM auth.refresh_tokens WHERE false"

# --- el script nunca imprime una contraseña -----------------------------------------------------
for pw in "$PW_API" "$PW_WORKER" "$PW_BACKUP"; do
  if [ -n "$pw" ] && grep -qF -- "$pw" <<< "$SALIDA"; then falla "la salida contiene una contraseña de rol"; fi
done

echo "test_db_roles: $fallas fallas"
[ "$fallas" -eq 0 ]
