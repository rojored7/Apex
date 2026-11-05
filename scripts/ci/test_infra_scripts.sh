#!/usr/bin/env bash
# test_infra_scripts.sh
#
# Envoltorio de las pruebas de shell de infra/backup (S4B-W0-1, S4B-D19) y, desde S4B-B4, de
# scripts/ci/test_deploy_script.sh y scripts/ci/test_check_release_version.sh. Bash puro: sin
# bats ni shellcheck.
# S4B-B3a: infra/backup/tests/run.sh recorre test_*.sh, así que incluye test_restore_guard.sh
# (psql, pg_restore, age y minisign falsos en el host; los reales en la CI). Esta comprobación
# explícita evita que un renombrado lo saque del envoltorio sin que nadie lo note.
# S4B-B4: test_deploy_script.sh usa los falsos de scripts/ci/fakes (docker, git, curl, sleep, stat);
# infra/tests/deploy_e2e.sh y scripts/ci/prod-smoke.sh NO corren aquí (solo apex-smoke y la CI).
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
fallas=0
if [ ! -f infra/backup/tests/test_restore_guard.sh ]; then
  echo "test_infra_scripts: falta infra/backup/tests/test_restore_guard.sh" >&2
  fallas=$((fallas + 1))
fi
# S5-B13: test_snapshot.sh (instantánea raft de OpenBao en el respaldo) también debe seguir aquí.
if [ ! -f infra/backup/tests/test_snapshot.sh ]; then
  echo "test_infra_scripts: falta infra/backup/tests/test_snapshot.sh" >&2
  fallas=$((fallas + 1))
fi
bash infra/backup/tests/run.sh || fallas=$((fallas + 1))
for prueba in test_deploy_script test_check_release_version; do
  if [ -f "scripts/ci/$prueba.sh" ]; then
    bash "scripts/ci/$prueba.sh" || fallas=$((fallas + 1))
  else
    echo "test_infra_scripts: falta scripts/ci/$prueba.sh" >&2
    fallas=$((fallas + 1))
  fi
done
echo "test_infra_scripts: $fallas fallas"
[ "$fallas" -eq 0 ]
