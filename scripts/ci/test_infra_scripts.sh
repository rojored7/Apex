#!/usr/bin/env bash
# test_infra_scripts.sh
#
# Envoltorio de las pruebas de shell de infra/backup (S4B-W0-1, S4B-D19) y, desde S4B-B4,
# de scripts/ci/test_deploy_script.sh. Bash puro: sin bats ni shellcheck.
# S4B-B3a: infra/backup/tests/run.sh recorre test_*.sh, así que incluye test_restore_guard.sh
# (psql, pg_restore, age y minisign falsos en el host; los reales en la CI). Esta comprobación
# explícita evita que un renombrado lo saque del envoltorio sin que nadie lo note.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
fallas=0
if [ ! -f infra/backup/tests/test_restore_guard.sh ]; then
  echo "test_infra_scripts: falta infra/backup/tests/test_restore_guard.sh" >&2
  fallas=$((fallas + 1))
fi
bash infra/backup/tests/run.sh || fallas=$((fallas + 1))
if [ -f scripts/ci/test_deploy_script.sh ]; then
  bash scripts/ci/test_deploy_script.sh || fallas=$((fallas + 1))
fi
echo "test_infra_scripts: $fallas fallas"
[ "$fallas" -eq 0 ]
