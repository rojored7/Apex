#!/usr/bin/env bash
# test_backup_apk_pins.sh [Dockerfile]
#
# Los pins `paquete=version` de `apk add` en infra/backup/Dockerfile deben existir HOY en el índice de
# Alpine de la imagen base (S4B-D190: rclone=1.74.1-r3 desapareció y el caché de buildx lo ocultó
# hasta el humo de producción). Usa Docker y red: corre en el job `images` de la CI, nunca en
# run-gates. Para cada pin ejecuta `apk update && apk policy <paquete>` dentro de la imagen del
# primer `FROM` y exige que la versión pinneada aparezca en la salida.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
DOCKERFILE="${1:-$ROOT/infra/backup/Dockerfile}"
[ -f "$DOCKERFILE" ] || { echo "test_backup_apk_pins: no existe $DOCKERFILE" >&2; exit 2; }

BASE="$(sed -n 's/^FROM[[:space:]]\{1,\}\([^[:space:]]\{1,\}\).*/\1/p' "$DOCKERFILE" | head -1)"
[ -n "$BASE" ] || { echo "test_backup_apk_pins: sin FROM en $DOCKERFILE" >&2; exit 2; }
PINS="$(grep -E 'apk add' "$DOCKERFILE" | tr ' ' '\n' | grep -E '^[a-z0-9][a-z0-9._+-]*=[0-9][^[:space:]]*$' || true)"
[ -n "$PINS" ] || { echo "test_backup_apk_pins: no hay pins paquete=version en $DOCKERFILE" >&2; exit 2; }

echo "test_backup_apk_pins (base $BASE)"
paquetes="$(printf '%s\n' "$PINS" | cut -d= -f1 | tr '\n' ' ')"
politica="$(docker run --rm "$BASE" sh -c "apk update > /dev/null && for p in $paquetes; do apk policy \"\$p\"; done" 2>&1 | tr -d '\r')" \
  || { echo "  FALLA no se pudo consultar apk policy"; exit 1; }

fallas=0
while IFS= read -r pin; do
  pkg="${pin%%=*}"; ver="${pin#*=}"
  # La salida de `apk policy` es "<pkg> policy:" seguido de "  <version>:" y los repositorios.
  if printf '%s\n' "$politica" | awk -v p="$pkg policy:" -v v="  $ver:" '
      $0 == p { dentro = 1; next }
      /^[^ ]/ { dentro = 0 }
      dentro && $0 == v { hallado = 1 }
      END { exit hallado ? 0 : 1 }'; then
    echo "  ok   $pin existe en el índice"
  else
    echo "  FALLA $pin no existe en el índice de Alpine de la imagen base (renueve el pin; docs/RUNBOOK.md §7)"
    fallas=$((fallas + 1))
  fi
done <<< "$PINS"
echo "test_backup_apk_pins: $fallas fallas"
[ "$fallas" -eq 0 ]
