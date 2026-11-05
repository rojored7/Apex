#!/usr/bin/env bash
# prod-smoke.sh [--no-build] [--provider local|openbao]
#
# Humo de producción sobre el proyecto Compose `apex-smoke` (S4B-B4, US-118; S4B-D46, D56, D65, D78,
# D100). Levanta el stack como en producción (migrate y dbsetup, api como apex_api, worker, web y
# backup con identidad de verificación), con contraseñas y llaves aleatorias que viven solo aquí, y
# comprueba de punta a punta: init-keys, seed y seed --demo, respaldo manual, backup_check, /health
# con backup y migrations en ok, roles de base, entorno del api, restauración en una segunda base y
# el despliegue (infra/tests/deploy_e2e.sh).
#
# Solo corre en la CI (job prod-smoke, release.yml) y en el proyecto apex-smoke de este equipo
# (SMOKE_WEB_PORT=8380 bash scripts/ci/prod-smoke.sh --no-build tras construir con buildx).
# Nunca toca el proyecto `apex` ni `apex-ensayo`. El stack solo se baja (con volúmenes) si hay CI o
# SMOKE_DOWN=1, y solo el proyecto apex-smoke.
#
# Variables: SMOKE_WEB_PORT (8380), SMOKE_DIR (por omisión docs/scratch/ensayo/smoke, ignorada por
# git; debe estar dentro del repositorio), GIT_SHA (versión de las imágenes; por omisión `smoke`),
# SMOKE_DOWN=1, CI. --no-build usa las imágenes apex-api:local, apex-web:local y apex-backup:local.
# S5-W0-2: el stack incluye openbao (red custody 172.31.13.0/24) y debe llegar a healthy sin inicializar.
# --provider openbao suma scripts/ci/openbao-smoke.sh (init 5/3, bootstrap, tokens, reinicio sellado y
# desello). La comprobación de kek.bin y del api con CRYPTO_PROVIDER=openbao queda para B2: hoy el
# proveedor del api sigue siendo local en ambos modos.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

NO_BUILD=0
PROVIDER=local
while [ "$#" -gt 0 ]; do
  case "$1" in
    --no-build) NO_BUILD=1; shift ;;
    --provider)
      [ "$#" -ge 2 ] || { echo "prod-smoke: --provider necesita local u openbao" >&2; exit 2; }
      case "$2" in local|openbao) PROVIDER="$2" ;; *) echo "prod-smoke: --provider debe ser local u openbao" >&2; exit 2 ;; esac
      shift 2 ;;
    *) echo "prod-smoke: argumento desconocido: $1" >&2; exit 2 ;;
  esac
done

PROJECT=apex-smoke
SUBNET=172.31.1.0/24
IP_RANGE=172.31.1.128/25
WEB_IP=172.31.1.10
CUSTODY_SUBNET=172.31.13.0/24
WEB_PORT="${SMOKE_WEB_PORT:-8380}"
SMOKE_DIR="${SMOKE_DIR:-$ROOT/docs/scratch/ensayo/smoke}"
export GIT_SHA="${GIT_SHA:-smoke}"
ADMIN_EMAIL=admin@smoke.apex.local
BACKUP_IMG=apex-backup:local

if [[ "/$SMOKE_DIR/" == */../* ]]; then
  echo "prod-smoke: SMOKE_DIR no puede tener componentes .." >&2; exit 2
fi
case "$SMOKE_DIR" in
  "$ROOT"/docs/scratch/?*) ;;
  *) echo "prod-smoke: SMOKE_DIR debe estar bajo $ROOT/docs/scratch/ (carpeta ignorada por git)" >&2; exit 2 ;;
esac
[[ "$WEB_PORT" =~ ^[0-9]{2,5}$ ]] || { echo "prod-smoke: SMOKE_WEB_PORT inválido" >&2; exit 2; }

fallas=0
paso() { printf 'prod-smoke: %s\n' "$*"; }
ok() { printf '  ok   %s\n' "$1"; }
falla() { printf '  FALLA %s\n' "$1" >&2; fallas=$((fallas + 1)); }
muere() { printf 'prod-smoke: ERROR %s\n' "$1" >&2; exit 1; }
nativa() { if command -v cygpath > /dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
mascara() { if [ -n "${CI:-}" ] || [ -n "${GITHUB_ACTIONS:-}" ]; then printf '::add-mask::%s\n' "$1"; fi; }
aleatorio() { head -c "$1" /dev/urandom | od -An -tx1 | tr -d ' \n'; }

# --- bajar solo apex-smoke, solo con CI o SMOKE_DOWN=1 ----------------------------------------------
DC=(docker compose -p "$PROJECT" --env-file "$SMOKE_DIR/.env" --env-file "$SMOKE_DIR/.env.ops" -f infra/compose.yml -f infra/compose.verify.yml)
bajar() {
  [ "${PROJECT}" = "apex-smoke" ] || muere "el proyecto a bajar no es apex-smoke"
  if [ -n "${CI:-}" ] || [ "${SMOKE_DOWN:-0}" = "1" ]; then
    docker compose -p apex-smoke down -v --remove-orphans > /dev/null 2>&1 || true
  fi
}
limpiar() {
  local rc=$?
  bajar
  rm -f "$SMOKE_DIR/.env.seed"
  # En la CI el runner es desechable: se borra todo el entorno del humo (contraseñas y llaves).
  if [ -n "${CI:-}" ]; then rm -rf "${SMOKE_DIR:?}"; fi
  exit "$rc"
}
trap limpiar EXIT

if [ -n "$(docker ps -a -q --filter "label=com.docker.compose.project=$PROJECT" 2> /dev/null)" ] \
  || [ -n "$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT" 2> /dev/null)" ]; then
  if [ -n "${CI:-}" ] || [ "${SMOKE_DOWN:-0}" = "1" ]; then
    paso "quedan restos de $PROJECT: se bajan con sus volúmenes"
    docker compose -p apex-smoke down -v --remove-orphans > /dev/null 2>&1 || true
  else
    muere "ya existe el proyecto $PROJECT; bájelo (docker compose -p apex-smoke down -v) o use SMOKE_DOWN=1"
  fi
fi

# --- entorno efímero: .env y .env.ops desde los ejemplos, contraseñas aleatorias y enmascaradas ---------
umask 077
rm -rf "$SMOKE_DIR"
mkdir -p "$SMOKE_DIR/keys"
cp .env.example "$SMOKE_DIR/.env"
cp .env.ops.example "$SMOKE_DIR/.env.ops"
chmod 700 "$SMOKE_DIR"

fijar() { # <archivo> <CLAVE> <valor>: reemplaza CLAVE=...
  local f="$SMOKE_DIR/$1"
  grep -q "^$2=" "$f" || muere "$f no tiene $2"
  sed -i "s|^$2=.*|$2=$3|" "$f"
}
for var in POSTGRES_PASSWORD APEX_API_DB_PASSWORD APEX_WORKER_DB_PASSWORD APEX_BACKUP_DB_PASSWORD APEX_OWNER_DB_PASSWORD; do
  valor="$(aleatorio 24)"
  mascara "$valor"
  fijar .env.ops "$var" "$valor"
  if [ "$var" = POSTGRES_PASSWORD ]; then
    fijar .env.ops DATABASE_URL "postgresql+asyncpg://apex:$valor@db:5432/apex_smoke"
  fi
done
fijar .env.ops POSTGRES_DB apex_smoke
# S5-D145: pila nueva; MIGRATE_DB_USER y TOOLS_DB_USER quedan en apex_owner (del ejemplo) y el script
# de initdb lo crea; migrate y tools usan APEX_OWNER_DB_PASSWORD (MIGRATE/TOOLS_DB_PASSWORD sin definir).
fijar .env.ops WEB_PORT "$WEB_PORT"
fijar .env.ops APEX_SUBNET "$SUBNET"
fijar .env.ops APEX_IP_RANGE "$IP_RANGE"
fijar .env.ops APEX_WEB_IP "$WEB_IP"
fijar .env.ops APEX_CUSTODY_SUBNET "$CUSTODY_SUBNET"
fijar .env.ops DEPLOY_HEALTH_TIMEOUT 150
fijar .env ENV production
fijar .env TRUSTED_PROXIES "$WEB_IP/32"
fijar .env ALLOW_INSECURE_COOKIE true
fijar .env FRONT_BASE_URL "http://localhost:$WEB_PORT"
# Los comentarios de cabecera de los ejemplos nombran 'cambiar-esto': solo cuentan las lineas que no son comentario.
[ "$(cat "$SMOKE_DIR/.env.ops" "$SMOKE_DIR/.env" | grep -v '^[[:space:]]*#' | grep -c 'cambiar-esto' || true)" = "0" ] || muere "quedó cambiar-esto en el entorno del humo"

# --- imágenes ------------------------------------------------------------------------------------
export APEX_ENV_DIR="../${SMOKE_DIR#"$ROOT"/}"
if [ "$NO_BUILD" -eq 0 ]; then
  paso "construcción de las imágenes (GIT_SHA=$GIT_SHA)"
  # build solo necesita que existan los env_file; el archivo de verificación se exige al levantar.
  : > "$SMOKE_DIR/keys/verify-placeholder"
  BACKUP_VERIFY_IDENTITY_FILE="$(nativa "$SMOKE_DIR/keys/verify-placeholder")" "${DC[@]}" build
else
  for img in apex-api:local apex-web:local "$BACKUP_IMG"; do
    docker image inspect "$img" > /dev/null 2>&1 || muere "falta la imagen $img (--no-build)"
  done
fi

# --- llaves efímeras: dos identidades age (restauración y verificación) y llave de firma -------------
KEYS="$SMOKE_DIR/keys"
chmod 777 "$KEYS"
MSYS_NO_PATHCONV=1 docker run --rm -v "$(nativa "$KEYS"):/k" --entrypoint sh "$BACKUP_IMG" -c '
  age-keygen -o /k/id.txt 2> /dev/null
  age-keygen -o /k/verify-id.txt 2> /dev/null
  grep "^# public key:" /k/id.txt | sed "s/^# public key: //" > /k/age.pub
  grep "^# public key:" /k/verify-id.txt | sed "s/^# public key: //" > /k/verify.pub
  minisign -G -W -f -p /k/sign.pub -s /k/sign.key > /dev/null
  chmod 644 /k/*' || muere "no se pudieron generar las llaves efímeras"
# Copia REAL de la KEK para deploy.sh --kek-file: 32 bytes aleatorios cifrados con `age -p` y una
# frase efímera enmascarada que no se guarda (age solo lee la frase de una terminal: pty en la imagen del api).
KEK_FRASE="$(aleatorio 16)"
mascara "$KEK_FRASE"
MSYS_NO_PATHCONV=1 docker run --rm -v "$(nativa "$KEYS"):/k" -v "$(nativa "$ROOT/scripts/ci/prod-smoke-pty.py"):/t/ptyrun.py:ro" \
  -e PTY_FRASE="$KEK_FRASE" \
  -e PTY_ARGV='["sh","-c","head -c 32 /dev/urandom > /tmp/kek.plano && age -p -o /k/kek-copy.age /tmp/kek.plano && rm -f /tmp/kek.plano"]' \
  --entrypoint python apex-api:local /t/ptyrun.py || muere "no se pudo fabricar la copia de la KEK con age -p"
unset KEK_FRASE
head -n 1 "$KEYS/kek-copy.age" | tr -d '\r' | grep -aqx 'age-encryption.org/v1' || muere "kek-copy.age no es un archivo de age"
chmod 755 "$KEYS"
if [ -n "${CI:-}" ] || [ -n "${GITHUB_ACTIONS:-}" ]; then
  for idf in id.txt verify-id.txt; do
    echo "::add-mask::$(grep '^AGE-SECRET-KEY-' "$KEYS/$idf" | tr -d '\r\n')"
  done
  echo "::add-mask::$(sed -n 2p "$KEYS/sign.key" | tr -d '\r\n')"
fi
fijar .env.ops BACKUP_AGE_RECIPIENT "$(tr -d '\r\n' < "$KEYS/age.pub")"
fijar .env.ops BACKUP_AGE_VERIFY_RECIPIENT "$(tr -d '\r\n' < "$KEYS/verify.pub")"
fijar .env.ops BACKUP_SIGN_PUBKEY "$(sed -n 2p "$KEYS/sign.pub" | tr -d '\r\n')"
fijar .env.ops BACKUP_SIGN_KEY_FILE "$(nativa "$KEYS/sign.key")"
fijar .env.ops BACKUP_VERIFY_IDENTITY_FILE "$(nativa "$KEYS/verify-id.txt")"

# --- arranque como en producción ---------------------------------------------------------------------
esperar_servicio() { # <servicio> <healthy|exited0> <segundos>
  local svc="$1" modo="$2" limite="$3" t=0 id estado
  while [ "$t" -lt "$limite" ]; do
    id="$("${DC[@]}" ps -a -q "$svc" 2> /dev/null | head -1 | tr -d '\r')"
    if [ -n "$id" ]; then
      if [ "$modo" = healthy ]; then
        estado="$(docker inspect -f '{{.State.Health.Status}}' "$id" 2> /dev/null | tr -d '\r' || true)"
        [ "$estado" = healthy ] && return 0
      else
        estado="$(docker inspect -f '{{.State.Status}} {{.State.ExitCode}}' "$id" 2> /dev/null | tr -d '\r' || true)"
        [ "$estado" = "exited 0" ] && return 0
        case "$estado" in "exited "[1-9]*) "${DC[@]}" logs --tail 60 "$svc" >&2 || true; return 1 ;; esac
      fi
    fi
    sleep 3
    t=$((t + 3))
  done
  "${DC[@]}" logs --tail 60 "$svc" >&2 || true
  return 1
}

paso "base de datos y llaves"
"${DC[@]}" up -d db
esperar_servicio db healthy 120 || muere "db no llegó a healthy"
"${DC[@]}" --profile tools run --rm -T tools init-keys || muere "init-keys falló"
paso "levantar el stack"
"${DC[@]}" up -d || muere "docker compose up -d falló"
for svc in migrate dbsetup; do
  if esperar_servicio "$svc" exited0 180; then ok "$svc completado"; else muere "$svc no terminó con 0"; fi
done
for svc in openbao api worker web backup; do
  if esperar_servicio "$svc" healthy 240; then ok "$svc healthy"; else muere "$svc no llegó a healthy"; fi
done

# --- seed del primer admin y datos de demostración (la base termina en _smoke, S4B-D65) ---------------
clave="$(aleatorio 16)"
mascara "$clave"
{
  printf 'ADMIN_EMAIL=%s\n' "$ADMIN_EMAIL"
  printf 'ADMIN_INITIAL_PASSWORD=%s\n' "$clave"
} > "$SMOKE_DIR/.env.seed"
"${DC[@]}" --profile tools run --rm -T tools seed > /dev/null || muere "seed falló"
"${DC[@]}" --profile tools run --rm -T tools seed --demo --as "$ADMIN_EMAIL" --allow-production > /dev/null || muere "seed --demo falló"
rm -f "$SMOKE_DIR/.env.seed"
ok "seed y seed --demo (base apex_smoke)"

# --- respaldo manual y backup_check ----------------------------------------------------------------------
salida="$("${DC[@]}" run --rm -T backup /opt/backup/run.sh < /dev/null 2>&1 | tr -d '\r')" || { printf '%s\n' "$salida" | tail -20 >&2; muere "run.sh falló"; }
case "$salida" in *"listo apex-"*) ok "respaldo manual (run.sh)" ;; *) printf '%s\n' "$salida" | tail -20 >&2; muere "run.sh no terminó con 'listo'" ;; esac
worker_cli() { "${DC[@]}" run --rm -T worker python -m app.worker.main "$@"; }
worker_cli --run-once backup_check > /dev/null && ok "--run-once backup_check sale con 0" || falla "--run-once backup_check no salió con 0"
estado_bc="$(worker_cli --status backup_check 2> /dev/null | tr -d '\r' | grep '^{"details": ' | tail -1 || true)"
case "$estado_bc" in *'"result": "ok"'*) ok "backup_check result ok" ;; *) falla "backup_check no dio ok: $(printf '%s' "$estado_bc" | cut -c1-200)" ;; esac

# --- /health: backup y migrations en ok (el caché de backup dura 30 s) ---------------------------------------
cuerpo=""
for _ in $(seq 1 20); do
  cuerpo="$(curl -fsS --max-time 5 "http://127.0.0.1:$WEB_PORT/api/v1/health" 2> /dev/null | tr -d '\r' || true)"
  if printf '%s' "$cuerpo" | grep -Eq '"backup": ?"ok"' && printf '%s' "$cuerpo" | grep -Eq '"migrations": ?"ok"'; then break; fi
  sleep 3
done
if printf '%s' "$cuerpo" | grep -Eq '"backup": ?"ok"' && printf '%s' "$cuerpo" | grep -Eq '"migrations": ?"ok"'; then
  ok "/health con backup ok y migrations ok"
else
  falla "/health sin backup ok y migrations ok: $(printf '%s' "$cuerpo" | cut -c1-200)"
fi

# --- roles de base y entorno por servicio (S4B-D56, D100) -------------------------------------------------------
DC_STR="docker compose -p $PROJECT --env-file $SMOKE_DIR/.env --env-file $SMOKE_DIR/.env.ops -f infra/compose.yml -f infra/compose.verify.yml"
if DC="$DC_STR" OPS_ENV_FILE="$SMOKE_DIR/.env.ops" bash scripts/ci/test_db_roles.sh; then ok "test_db_roles.sh"; else falla "test_db_roles.sh"; fi
if DC="$DC_STR" OPS_ENV_FILE="$SMOKE_DIR/.env.ops" bash scripts/ci/test_env_isolation.sh; then ok "test_env_isolation.sh (/proc/1/environ de api, worker y backup)"; else falla "test_env_isolation.sh"; fi

# --- despliegue de punta a punta (conserva su propio respaldo; antes de la restauración, que limpia el volumen) ----
if E2E_PROJECT="$PROJECT" E2E_ENV_DIR="$SMOKE_DIR" E2E_KEK_FILE="$KEYS/kek-copy.age" bash infra/tests/deploy_e2e.sh; then
  ok "deploy_e2e.sh"
else
  falla "deploy_e2e.sh"
fi

# --- restauración en una segunda base del mismo db (restore.sh con firma e inspección) ------------------------------
if E2E_DC="${DC[*]}" E2E_ENV_DIR="$SMOKE_DIR" E2E_ALLOW_PROJECT="$PROJECT" bash infra/tests/restore_e2e.sh; then
  ok "restore_e2e.sh (restore.sh en la base apex_restore)"
else
  falla "restore_e2e.sh"
fi

# --- instantánea de OpenBao en pareja con la base (S5-B13, S5-D95): recursos desechables apex-obe2e-* ----------
if bash infra/tests/openbao_restore_e2e.sh; then
  ok "openbao_restore_e2e.sh (instantánea raft cifrada, restauración en pareja y descifrado con las llaves originales)"
else
  falla "openbao_restore_e2e.sh"
fi

# --- OpenBao (S5-D22, W0-2): init 5/3, bootstrap, tokens, reinicio sellado y desello ----------------------------
if [ "$PROVIDER" = "openbao" ]; then
  if DC="$DC_STR" OPENBAO_SMOKE_EVIDENCE="$SMOKE_DIR/openbao" bash scripts/ci/openbao-smoke.sh; then ok "openbao-smoke.sh"; else falla "openbao-smoke.sh"; fi
fi

if [ "$fallas" -ne 0 ]; then
  echo "prod-smoke: $fallas fallas" >&2
  "${DC[@]}" logs --tail 80 api >&2 || true
  exit 1
fi
echo "prod-smoke: todo en verde"
