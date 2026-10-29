#!/usr/bin/env bash
# test_infra_scripts.sh
#
# Envoltorio de las pruebas de shell de infra/backup (S4B-W0-1, S4B-D19) y, desde S4B-B4,
# de scripts/ci/test_deploy_script.sh. Bash puro: sin bats ni shellcheck.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
fallas=0
bash infra/backup/tests/run.sh || fallas=$((fallas + 1))
if [ -f scripts/ci/test_deploy_script.sh ]; then
  bash scripts/ci/test_deploy_script.sh || fallas=$((fallas + 1))
fi
echo "test_infra_scripts: $fallas fallas"
[ "$fallas" -eq 0 ]
