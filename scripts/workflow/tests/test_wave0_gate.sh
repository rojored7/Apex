#!/usr/bin/env bash
# Pruebas de wave0-gate.sh (S4B-W0-1, S4B-D52 y S4B-D82): orden de las comprobaciones, parada en
# el primer fallo y sello solo por medio de slice-gate.sh. `docker` y `uv` son falsos; los
# scripts de scripts/ci y slice-gate.sh del repositorio temporal también.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
GATE="$WORKFLOW_DIR/wave0-gate.sh"

echo "test_wave0_gate"
assert_file_exists "$GATE"
[ -f "$GATE" ] || { finish; exit; }

# Repositorio temporal con los scripts que wave0-gate.sh invoca, todos registrando su llamada.
preparar() {
  local dir
  dir="$(mk_repo)"
  mkdir -p "$dir/scripts/ci" "$dir/scripts/workflow" "$dir/infra/backup" "$dir/api/tests/core"
  cp "$GATE" "$dir/scripts/workflow/wave0-gate.sh"
  local t
  for t in test_check_key_files test_images_pinned test_nginx_conf test_compose_config test_infra_scripts test_api_image; do
    printf '#!/usr/bin/env bash\necho "script %s $*" >> "%s"\nexit 0\n' "$t" "$STUB_LOG" > "$dir/scripts/ci/$t.sh"
  done
  printf '#!/usr/bin/env bash\necho "slice-gate $*" >> "%s"\n[ ! -f "%s/slice.fail" ] || exit 1\nexit 0\n' "$STUB_LOG" "$dir" > "$dir/scripts/workflow/slice-gate.sh"
  printf '#!/usr/bin/env bash\necho ok\n' > "$dir/infra/backup/run.sh"
  printf 'def test_x() -> None:\n    assert True\n' > "$dir/api/tests/core/test_env_example.py"
  (cd "$dir" && "$REAL_GIT" add -A && "$REAL_GIT" commit -q -m "chore: scripts")
  echo "$dir"
}

use_stubs
stub_tool docker 0
stub_tool uv 0

REPO="$(preparar)"
cd "$REPO"
export WAVE0_SKIP_IMAGE=1

assert_exit 0 "-h sale con 0" bash scripts/workflow/wave0-gate.sh -h
assert_exit 2 "sin argumento sale con 2" bash scripts/workflow/wave0-gate.sh

clear_log
assert_exit 0 "gate en verde" bash scripts/workflow/wave0-gate.sh W0-1 tests/core/test_env_example.py
for t in test_check_key_files test_images_pinned test_nginx_conf test_compose_config test_infra_scripts; do
  assert_log_has "script $t"
done
assert_log_lacks "script test_api_image"
assert_log_has "docker compose"
assert_log_has "config --quiet"
assert_log_has "slice-gate architecture tests/core/test_env_example.py"
# slice-gate.sh es lo último que se ejecuta (el que sella).
ultima="$(grep -v '^docker' "$STUB_LOG" | tail -1)"
case "$ultima" in "slice-gate architecture"*) _ok "slice-gate.sh architecture es el último paso" ;; *) _fail "el último paso fue: $ultima" ;; esac

# Con la imagen: test_api_image.sh corre cuando no se omite.
clear_log
(unset WAVE0_SKIP_IMAGE; bash scripts/workflow/wave0-gate.sh W0-1 > /dev/null 2>&1) || true
assert_log_has "script test_api_image apex-api:local"

# Un fallo detiene la suite: no se llega a slice-gate.sh (sin sello).
printf '#!/usr/bin/env bash\necho "script test_nginx_conf" >> "%s"\nexit 1\n' "$STUB_LOG" > scripts/ci/test_nginx_conf.sh
clear_log
assert_nonzero "script de infraestructura en rojo falla" bash scripts/workflow/wave0-gate.sh W0-1
assert_log_lacks "slice-gate"
assert_log_lacks "script test_compose_config"

# docker compose config en rojo también detiene.
printf '#!/usr/bin/env bash\necho "script test_nginx_conf" >> "%s"\nexit 0\n' "$STUB_LOG" > scripts/ci/test_nginx_conf.sh
stub_tool_fail_on docker "config --quiet" 1
clear_log
assert_nonzero "docker compose config en rojo falla" bash scripts/workflow/wave0-gate.sh W0-1
assert_log_lacks "slice-gate"
stub_tool docker 0

# bash -n de un script roto detiene antes de todo.
printf 'if then fi (\n' > scripts/ci/roto.sh
clear_log
assert_nonzero "bash -n de un .sh roto falla" bash scripts/workflow/wave0-gate.sh W0-1
assert_log_lacks "slice-gate"
rm -f scripts/ci/roto.sh

# slice-gate.sh en rojo: el gate de Wave 0 también falla (nunca hay sello sin él).
touch slice.fail
assert_nonzero "slice-gate.sh en rojo hace fallar el gate" bash scripts/workflow/wave0-gate.sh W0-1
rm -f slice.fail

cd "$REPO_ROOT"
finish
