#!/usr/bin/env bash
# openbao-seal.sh [seal|unseal]
#
# Sella o desella el OpenBao de DESARROLLO (compose.dev.yml, perfil openbao; S5-D12, S5-D103).
# Sirve para ensayar el estado sellado del api (`/health.crypto = sealed`, deploy.sh, avisos).
# No es una herramienta de producción: en producción se desella con docs/operacion/openbao.md.
#
#   bash scripts/dev/openbao-seal.sh seal     sella (usa el token de sellado del volumen de desarrollo)
#   bash scripts/dev/openbao-seal.sh unseal   pide la llave con `read -rs` y la envía por stdin a sys/unseal
#
# La llave de desarrollo vive en el volumen openbao-dev-data; para teclearla:
#   docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml --profile openbao \
#     exec -T openbao cat /openbao/file/.dev-unseal-key
# (Reiniciar el servicio openbao también lo desella solo: dev-entrypoint.sh.) La llave nunca va por
# argumento ni por printf literal, ni queda en un archivo.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"
ENV_FILE="${APEX_ENV_FILE:-.env}"
DC=(docker compose --env-file "$ENV_FILE" -f infra/compose.yml -f infra/compose.dev.yml --profile openbao)

case "${1:-seal}" in
  seal)
    "${DC[@]}" exec -T openbao sh -c 'BAO_ADDR=http://127.0.0.1:8200 BAO_TOKEN="$(cat /openbao/file/.dev-seal-token)" bao operator seal'
    echo "openbao-seal: OpenBao de desarrollo sellado"
    ;;
  unseal)
    printf 'Llave de desello de desarrollo (no se muestra): ' >&2
    read -rs LLAVE
    echo >&2
    printf '{"key":"%s"}' "$LLAVE" \
      | "${DC[@]}" exec -T openbao wget -q -O /dev/null --header 'Content-Type: application/json' --post-file=/dev/stdin http://127.0.0.1:8200/v1/sys/unseal
    LLAVE=""
    echo "openbao-seal: llave enviada"
    ;;
  *)
    sed -n '2,10p' "$0" | sed 's/^# \{0,1\}//' >&2
    exit 2
    ;;
esac
