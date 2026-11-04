#!/bin/sh
# dev-entrypoint.sh: arranque de OpenBao SOLO PARA DESARROLLO (S5-D12, M-3).
#
# Lo usa compose.dev.yml (perfil `openbao`) como entrypoint del servicio openbao. Arranca el
# servidor, y con el volumen vacío lo inicializa con UNA llave (1 de 1), lo desella, corre
# bootstrap.sh en modo no interactivo (transit, apex-kek, apex-sign-audit y políticas; sin
# volúmenes de token en desarrollo) y deja la llave de desello en el volumen openbao-dev-data,
# con modo 600, para desellar solo en cada reinicio. Nunca escribe la llave en el log. También
# deja un token mínimo que solo puede sellar (scripts/dev/openbao-seal.sh).
#
# NUNCA va a producción: aborta si APEX_ENV no es dev, y compose.yml no lo menciona. En
# producción la llave se parte en 5 (umbral 3) y se desella a mano (docs/operacion/openbao.md).
set -euo pipefail
umask 077

if [ "${APEX_ENV:-}" != "dev" ]; then
  echo "dev-entrypoint: ERROR solo para desarrollo (APEX_ENV=dev); en producción se instala con bootstrap.sh" >&2
  exit 1
fi

export BAO_ADDR="http://127.0.0.1:8200"
DEV_DIR=/openbao/file
KEY_FILE="$DEV_DIR/.dev-unseal-key"
SEAL_TOKEN_FILE="$DEV_DIR/.dev-seal-token"

bao server -config=/openbao/config/config.hcl &
SERVER_PID=$!
trap 'kill -TERM "$SERVER_PID" 2> /dev/null || true' TERM INT

n=0
until wget -q -O /dev/null "$BAO_ADDR/v1/sys/health?sealedcode=200&uninitcode=200" 2> /dev/null; do
  n=$((n + 1))
  [ "$n" -le 60 ] || { echo "dev-entrypoint: ERROR el servidor no arrancó" >&2; exit 1; }
  sleep 1
done

estado() { wget -q -O - "$BAO_ADDR/v1/sys/seal-status" | tr ',' '\n' | sed -n "s/.*\"$1\": *\"\{0,1\}\([^\",}]*\).*/\1/p"; }

# Envía a sys/unseal la llave que llega por stdin (S5-D103: nunca por argumento).
unseal_stdin() {
  read -r K_LINE
  printf '{"key":"%s"}' "$K_LINE" | wget -q -O /dev/null --header 'Content-Type: application/json' --post-file=/dev/stdin "$BAO_ADDR/v1/sys/unseal"
  K_LINE=""
}

if [ "$(estado initialized)" != "true" ]; then
  INIT_OUT="$(bao operator init -key-shares=1 -key-threshold=1)"
  BAO_TOKEN="$(printf '%s\n' "$INIT_OUT" | sed -n 's/^Initial Root Token: //p')"
  export BAO_TOKEN
  printf '%s\n' "$INIT_OUT" | sed -n 's/^Unseal Key 1: //p' > "$KEY_FILE"
  INIT_OUT=""
  chmod 600 "$KEY_FILE"
  unseal_stdin < "$KEY_FILE"
  # Token que solo puede sellar, para scripts/dev/openbao-seal.sh (la raíz se revoca abajo).
  printf '%s\n' 'path "sys/seal" { capabilities = ["update", "sudo"] }' 'path "auth/token/renew-self" { capabilities = ["update"] }' | bao policy write apex-dev-seal - > /dev/null
  # 768h es el tope del sistema (max_ttl); cada arranque lo renueva.
  bao token create -policy=apex-dev-seal -orphan -no-default-policy -period=768h -field=token > "$SEAL_TOKEN_FILE"
  chmod 600 "$SEAL_TOKEN_FILE"
  BOOTSTRAP_NONINTERACTIVE=1 sh /bootstrap.sh --first-install
else
  if [ "$(estado sealed)" = "true" ]; then
    [ -f "$KEY_FILE" ] || { echo "dev-entrypoint: ERROR sellado y sin llave de desarrollo; borre el volumen openbao-dev-data" >&2; exit 1; }
    unseal_stdin < "$KEY_FILE"
  fi
fi
# Renueva el token de sellado (periódico de 768 h); si ya expiró, hay que recrear el volumen.
if [ -f "$SEAL_TOKEN_FILE" ]; then
  BAO_TOKEN="$(cat "$SEAL_TOKEN_FILE")" bao write -f auth/token/renew-self > /dev/null 2>&1 \
    || echo "dev-entrypoint: aviso: el token de sellado expiró; borre el volumen openbao-dev-data para recrearlo" >&2
fi
echo "dev-entrypoint: OpenBao de desarrollo listo (1/1, llave en el volumen openbao-dev-data)" >&2

wait "$SERVER_PID"
