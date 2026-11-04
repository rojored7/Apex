#!/usr/bin/env bash
# deploy_e2e.sh [--solo-db-detenida]: despliegue de punta a punta (S4B-B4, US-117; S4B-D41, D46, D67).
#
# Solo corre sobre el proyecto `apex-smoke` (lo invoca scripts/ci/prod-smoke.sh, también en la CI) y,
# con --solo-db-detenida, sobre `apex-ensayo` (paso B4.10.3). Nunca contra `apex` ni contra otra
# cosa. No usa los falsos de scripts/ci/fakes: es el stack real.
#
# Cómo despliega sin una etiqueta de verdad: arma en una carpeta temporal un repositorio con una
# copia del árbol de trabajo actual (archivos versionados y nuevos, sin los ignorados), le pone una
# confirmación y la etiqueta v99.0.0, lo clona (el clon tiene `origin` y la etiqueta) y corre ahí el
# infra/deploy.sh real con `--ref v99.0.0 --expect-sha <sha>`. Los .env y .env.ops del humo se copian
# al clon (sin APEX_ENV_DIR). Así se prueba el script tal como está en el árbol, aunque aún no esté
# confirmado.
#
# Firma de etiquetas: v0.1 no tiene .github/allowed_signers y deploy.sh falla cerrado sin firma verificable
# (S4B-D181), asi que este script pasa --i-know-unsigned-ref en cada corrida: la etiqueta v99.0.0 es
# local y desechable. E2E_KEK_FILE debe ser un archivo de age real (prod-smoke.sh lo fabrica con age -p).
#
# Variables (las pone prod-smoke.sh): E2E_PROJECT (apex-smoke), E2E_ENV_DIR (carpeta con .env y
# .env.ops, dentro del repositorio), E2E_KEK_FILE (archivo legible que hace de copia de la KEK),
# BACKUP_IMG (apex-backup:local).
#
# Qué comprueba:
#   1. camino feliz: deploy.sh termina con 0; quedan `pre-deploy-<ts>-db.dump.age`,
#      `-uploads.tar.age`, `pre-deploy-<ts>.json` y su `.minisig`; `latest.json` no cambió; /health
#      responde 200 con "migrations":"ok"; existe deploy-<fecha>.state.json.
#   2. api roto (CRYPTO_LOCAL_KEK_PATH=/nonexistent en el .env del clon): deploy.sh termina distinto
#      de 0, escribe rollback-<fecha>.txt y el respaldo pre-deploy sigue ahí. Después se repone el
#      .env y se vuelve a desplegar (el stack queda sano; segunda corrida del script).
#   3. db detenida: deploy.sh termina con 2 en la preverificación, ANTES de construir, sin respaldo
#      ni estado nuevos; la db se vuelve a arrancar.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

SOLO_DB=0
case "${1:-}" in
  "") ;;
  --solo-db-detenida) SOLO_DB=1 ;;
  *) echo "deploy_e2e: argumento desconocido: $1" >&2; exit 2 ;;
esac
PROJECT="${E2E_PROJECT:-apex-smoke}"
ENV_DIR="${E2E_ENV_DIR:-}"
KEK_FILE="${E2E_KEK_FILE:-}"
BACKUP_IMG="${BACKUP_IMG:-apex-backup:local}"
case "$PROJECT" in
  apex-smoke) ;;
  apex-ensayo) [ "$SOLO_DB" -eq 1 ] || { echo "deploy_e2e: en apex-ensayo solo se permite --solo-db-detenida" >&2; exit 2; } ;;
  *) echo "deploy_e2e: el proyecto '$PROJECT' no está permitido (apex-smoke, o apex-ensayo con --solo-db-detenida)" >&2; exit 2 ;;
esac
if [[ "/$ENV_DIR/" == */../* ]]; then echo "deploy_e2e: E2E_ENV_DIR no puede tener componentes .." >&2; exit 2; fi
case "$ENV_DIR" in "$ROOT"/docs/scratch/?*) ;; *) echo "deploy_e2e: E2E_ENV_DIR debe estar bajo $ROOT/docs/scratch/" >&2; exit 2 ;; esac
[ -f "$ENV_DIR/.env" ] && [ -f "$ENV_DIR/.env.ops" ] || { echo "deploy_e2e: E2E_ENV_DIR debe tener .env y .env.ops" >&2; exit 2; }
[ -n "$KEK_FILE" ] && [ -r "$KEK_FILE" ] || { echo "deploy_e2e: E2E_KEK_FILE debe ser un archivo legible" >&2; exit 2; }

fallas=0
ok() { printf '  ok   %s\n' "$1"; }
falla() { printf '  FALLA %s\n' "$1" >&2; fallas=$((fallas + 1)); }
muere() { printf 'deploy_e2e: ERROR %s\n' "$1" >&2; exit 1; }
valor() { { grep -hE "^$2=" "$1" || true; } | tail -1 | cut -d= -f2- | tr -d '\r'; }

# umask 022: el clon lo lee `dbsetup` (contenedor sin root) por el bind de ./db; un clon en 700 salia con 2.
# Los .env y .env.ops se copian mas abajo bajo su propio umask 077.
umask 022
WORK="$(mktemp -d "${TMPDIR:-/tmp}/deploy-e2e.XXXXXX")"
chmod 755 "$WORK"
STATE_DIR="$ENV_DIR/state"
mkdir -p "$STATE_DIR"
OPS_DIR_REL="../${ENV_DIR#"$ROOT"/}"
HOST_DC=(env "APEX_ENV_DIR=$OPS_DIR_REL" docker compose -p "$PROJECT" --env-file "$ENV_DIR/.env" --env-file "$ENV_DIR/.env.ops" -f infra/compose.yml)
DB_PARADA=0
limpiar() {
  local rc=$?
  if [ "$DB_PARADA" -eq 1 ]; then "${HOST_DC[@]}" start db > /dev/null 2>&1 || true; fi
  rm -rf "${WORK:?}"
  exit "$rc"
}
trap limpiar EXIT

[ -n "$("${HOST_DC[@]}" ps -q db 2> /dev/null | tr -d '\r')" ] || muere "el proyecto $PROJECT no tiene db: levante el stack antes (prod-smoke.sh)"

# --- repositorio temporal con la etiqueta v99.0.0 y su clon ---------------------------------------------
REF=v99.0.0
GIT=(git -c user.name=deploy-e2e -c user.email=deploy-e2e@apex.local -c commit.gpgsign=false -c tag.gpgsign=false)
mkdir -p "$WORK/origen"
"${GIT[@]}" -C "$WORK/origen" init -q
# Copia portable (sin tar GNU ni cpio): archivo por archivo, solo versionados y nuevos no ignorados.
git ls-files -z -co --exclude-standard | while IFS= read -r -d '' f; do
  if [ -f "$f" ]; then
    mkdir -p "$WORK/origen/$(dirname "$f")"
    cp -p "$f" "$WORK/origen/$f"
  fi
done
"${GIT[@]}" -C "$WORK/origen" add -A
"${GIT[@]}" -C "$WORK/origen" commit -q -m "copia del arbol para deploy_e2e"
"${GIT[@]}" -C "$WORK/origen" tag "$REF"
SHA="$("${GIT[@]}" -C "$WORK/origen" rev-parse "$REF^{commit}")"
"${GIT[@]}" clone -q --no-hardlinks "$WORK/origen" "$WORK/despliegue"
( umask 077
  cp "$ENV_DIR/.env" "$WORK/despliegue/.env"
  { grep -v '^APEX_ENV_DIR=' "$ENV_DIR/.env.ops" || true; } > "$WORK/despliegue/.env.ops" )
chmod 600 "$WORK/despliegue/.env" "$WORK/despliegue/.env.ops"
cp "$WORK/despliegue/.env" "$WORK/env.buena"
WEB_PORT="$(valor "$WORK/despliegue/.env.ops" WEB_PORT)"

# deploy <VAR=valor ...>: corre infra/deploy.sh del clon sobre el proyecto; deja RC y OUT.
RC=0; OUT=""
deploy() {
  RC=0
  OUT="$(cd "$WORK/despliegue" && env -u APEX_ENV_DIR COMPOSE_PROJECT_NAME="$PROJECT" DEPLOY_STATE_DIR="$STATE_DIR" \
    DEPLOY_COMPOSE_EXTRA="${DEPLOY_COMPOSE_EXTRA_E2E:-}" "$@" \
    bash infra/deploy.sh --ref "$REF" --expect-sha "$SHA" --kek-file "$KEK_FILE" --i-know-unsigned-ref 2>&1)" || RC=$?
}
en_backups() { # <comando sh>: corre en el volumen backups del proyecto
  local vol
  vol="$(docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT" --filter "label=com.docker.compose.volume=backups" | head -1 | tr -d '\r')"
  [ -n "$vol" ] || muere "no se encontró el volumen backups de $PROJECT"
  MSYS_NO_PATHCONV=1 docker run --rm -v "$vol:/b:ro" --entrypoint sh "$BACKUP_IMG" -c "$1" | tr -d '\r'
}
contar_estados() { find "$STATE_DIR" -maxdepth 1 -name "$1" 2> /dev/null | wc -l | tr -d ' '; }

if [ "$SOLO_DB" -eq 0 ]; then
  DEPLOY_COMPOSE_EXTRA_E2E=infra/compose.verify.yml

  echo "-- 1. camino feliz"
  latest_antes="$(en_backups 'sha256sum /b/latest.json 2> /dev/null || echo ninguno')"
  deploy
  if [ "$RC" -eq 0 ]; then ok "deploy.sh sale con 0"; else printf '%s\n' "$OUT" | tail -30 >&2; falla "deploy.sh sale con 0 (obtenido $RC)"; fi
  listado="$(en_backups 'ls /b')"
  for sufijo in '-db.dump.age' '-uploads.tar.age' '.json' '.json.minisig'; do
    if printf '%s\n' "$listado" | grep -Eq "^pre-deploy-[0-9]{8}-[0-9]{6}${sufijo//./\\.}\$"; then ok "queda pre-deploy-<ts>$sufijo"; else falla "falta pre-deploy-<ts>$sufijo"; fi
  done
  latest_despues="$(en_backups 'sha256sum /b/latest.json 2> /dev/null || echo ninguno')"
  if [ "$latest_antes" = "$latest_despues" ]; then ok "latest.json no cambió"; else falla "latest.json cambió con el respaldo pre-deploy"; fi
  codigo="$(curl -s -o "$WORK/health.json" -w '%{http_code}' --max-time 5 "http://127.0.0.1:$WEB_PORT/api/v1/health" || true)"
  if [ "$codigo" = 200 ] && grep -Eq '"migrations": ?"ok"' "$WORK/health.json"; then ok "/health 200 con migrations ok"; else falla "/health no dio 200 con migrations ok (código $codigo)"; fi
  [ "$(contar_estados 'deploy-*.state.json')" -ge 1 ] && ok "existe deploy-<fecha>.state.json" || falla "falta deploy-<fecha>.state.json"
  pre_antes="$(en_backups 'ls /b | grep -c "^pre-deploy-.*-db.dump.age$" || true')"
  rb_antes="$(contar_estados 'rollback-*.txt')"

  echo "-- 2. api roto"
  sed -i 's|^CRYPTO_LOCAL_KEK_PATH=.*|CRYPTO_LOCAL_KEK_PATH=/nonexistent|' "$WORK/despliegue/.env"
  deploy DEPLOY_SKIP_BUILD=1 DEPLOY_HEALTH_TIMEOUT=30
  if [ "$RC" -ne 0 ]; then ok "deploy.sh con el api roto sale distinto de 0 ($RC)"; else falla "deploy.sh con el api roto salió con 0"; fi
  [ "$(contar_estados 'rollback-*.txt')" -gt "$rb_antes" ] && ok "escribe rollback-<fecha>.txt" || falla "no escribió rollback-<fecha>.txt"
  ultimo_rb="$(find "$STATE_DIR" -maxdepth 1 -name 'rollback-*.txt' | sort | tail -1)"
  if [ -n "$ultimo_rb" ] && grep -q 'este script no restaura la base' "$ultimo_rb" && ! grep -Eq 'PASSWORD|SECRET' "$ultimo_rb"; then ok "rollback nombra la limitación y no lleva secretos"; else falla "rollback incompleto o con secretos"; fi
  pre_despues="$(en_backups 'ls /b | grep -c "^pre-deploy-.*-db.dump.age$" || true')"
  if [ "$pre_despues" -gt "$pre_antes" ] && [ "$pre_antes" -ge 1 ]; then ok "el respaldo pre-deploy se conservó (y el nuevo también)"; else falla "pre-deploy: antes $pre_antes, después $pre_despues"; fi
  cp "$WORK/env.buena" "$WORK/despliegue/.env"
  chmod 600 "$WORK/despliegue/.env"
  deploy DEPLOY_SKIP_BUILD=1
  if [ "$RC" -eq 0 ]; then ok "con el .env bueno el stack se recupera (segunda corrida)"; else printf '%s\n' "$OUT" | tail -30 >&2; falla "no se recuperó el stack (obtenido $RC)"; fi
fi

echo "-- 3. db detenida"
estados_antes="$(contar_estados 'deploy-*.state.json')"
"${HOST_DC[@]}" stop db > /dev/null
DB_PARADA=1
deploy
if [ "$RC" -eq 2 ]; then ok "con db detenida deploy.sh sale con 2"; else falla "con db detenida deploy.sh salió con $RC"; fi
case "$OUT" in *"servicio db no está en marcha"*) ok "el motivo es db detenida" ;; *) falla "el motivo no es db detenida: $(printf '%s' "$OUT" | tail -3)" ;; esac
case "$OUT" in *"construcción de las imágenes"*) falla "construyó con db detenida" ;; *) ok "aborta antes de construir" ;; esac
[ "$(contar_estados 'deploy-*.state.json')" = "$estados_antes" ] && ok "no creó estado nuevo" || falla "creó estado con db detenida"
"${HOST_DC[@]}" start db > /dev/null
DB_PARADA=0
for _ in $(seq 1 40); do
  id="$("${HOST_DC[@]}" ps -q db | head -1 | tr -d '\r')"
  [ "$(docker inspect -f '{{.State.Health.Status}}' "$id" 2> /dev/null | tr -d '\r')" = healthy ] && break
  sleep 3
done
ok "db arrancada de nuevo"

if [ "$fallas" -ne 0 ]; then
  echo "deploy_e2e: $fallas fallas" >&2
  exit 1
fi
echo "deploy_e2e: todo en verde"
