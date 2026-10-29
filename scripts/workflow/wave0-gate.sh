#!/usr/bin/env bash
# wave0-gate.sh <slice> [archivos de prueba de Python...]
#
# Gate de un slice de Wave 0 del Sprint 4B (S4B-D52, S4B-D82). Corre las comprobaciones de
# infraestructura y TERMINA ejecutando `slice-gate.sh architecture [archivos...]`, que es quien
# escribe el sello que checkpoint-commit.sh conoce (así ningún script del flujo cambia de
# contrato). Orden: bash -n de cada .sh de infra/, scripts/ci y scripts/workflow; las pruebas
# de scripts/ci; docker compose config --quiet en cuatro combinaciones; y el sello.
# slice-gate.sh architecture no corre ruff ni mypy: todo slice de Wave 0 que toque Python corre
# antes `slice-gate.sh <modulo>` del módulo tocado (E6). Sin Docker no hay sello.
# WAVE0_SKIP_IMAGE=1 omite test_api_image.sh (solo para probar este script).
set -euo pipefail

usage() {
  cat <<'USO'
Uso: wave0-gate.sh <slice> [archivos de prueba de Python...]

  1. bash -n de cada .sh bajo infra/, scripts/ci/ y scripts/workflow/
  2. scripts/ci: test_check_key_files, test_images_pinned, test_nginx_conf,
     test_compose_config, test_infra_scripts y test_api_image.sh apex-api:local
  3. docker compose config --quiet: compose.yml, con --profile tools, con compose.verify.yml
     y con compose.dev.yml
  4. exec scripts/workflow/slice-gate.sh architecture [archivos...]  (escribe el sello)

Ejemplo: wave0-gate.sh W0-1 tests/core/test_env_example.py tests/core/test_config.py
Antes, para los slices que tocan Python: slice-gate.sh core/config <archivos>.
USO
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  "") usage >&2; exit 2 ;;
esac
SLICE="$1"
shift

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

fallo() { echo "wave0-gate: FALLÓ $*" >&2; exit 1; }

echo "wave0-gate: [$SLICE] bash -n"
while IFS= read -r f; do
  bash -n "$f" || fallo "bash -n $f"
done < <(find infra scripts/ci scripts/workflow -name '*.sh' -not -path '*/tmp/*' -not -path '*/node_modules/*' 2> /dev/null | sort)

for prueba in test_check_key_files test_images_pinned test_nginx_conf test_compose_config test_infra_scripts; do
  if [ -f "scripts/ci/$prueba.sh" ]; then
    echo "wave0-gate: [$SLICE] $prueba"
    bash "scripts/ci/$prueba.sh" || fallo "$prueba"
  fi
done
if [ "${WAVE0_SKIP_IMAGE:-0}" != "1" ] && [ -f scripts/ci/test_api_image.sh ]; then
  echo "wave0-gate: [$SLICE] test_api_image apex-api:local"
  bash scripts/ci/test_api_image.sh apex-api:local || fallo "test_api_image"
fi

ENVF=.env
[ -f "$ENVF" ] || ENVF=.env.example
TMP_ID="$(mktemp)"
trap 'rm -f "$TMP_ID"' EXIT
combos=(
  "-f infra/compose.yml"
  "--profile tools -f infra/compose.yml"
  "-f infra/compose.yml -f infra/compose.verify.yml"
  "-f infra/compose.yml -f infra/compose.dev.yml"
)
for c in "${combos[@]}"; do
  case "$c" in *compose.verify.yml*) [ -f infra/compose.verify.yml ] || continue ;; esac
  echo "wave0-gate: [$SLICE] docker compose $c config --quiet"
  # shellcheck disable=SC2086
  BACKUP_VERIFY_IDENTITY_FILE="$TMP_ID" docker compose --env-file "$ENVF" $c config --quiet || fallo "docker compose $c config --quiet"
done

echo "wave0-gate: [$SLICE] comprobaciones de infraestructura en verde; sellando con slice-gate.sh architecture"
exec bash scripts/workflow/slice-gate.sh architecture "$@"
