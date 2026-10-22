#!/usr/bin/env bash
# Pruebas de run-gates.sh (US-008, T4; cobertura global M-6).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
RUN="$WORKFLOW_DIR/run-gates.sh"

echo "test_run_gates"
REPO="$(mk_repo)"
cd "$REPO"
use_stubs

assert_exit 0 "-h sale con 0" bash "$RUN" -h

# Sin web/package.json no invoca npm ni npx.
stub_tool uv 0
stub_tool npm 0
stub_tool npx 0
clear_log
assert_exit 0 "api en verde sin front" bash "$RUN"
assert_log_has "ruff check ."
assert_log_has "ruff format --check ."
assert_log_has "mypy src"
assert_log_has "pytest --cov=app --cov-fail-under=80"
assert_log_has "-m not perf"
assert_log_lacks "npm"
assert_log_lacks "npx"

# Scripts de infraestructura (M1, revisión de Fase 4): corren los que existan y un fallo
# detiene la suite.
mkdir -p scripts/ci
printf '#!/usr/bin/env bash\necho "script test_nginx_conf" >> "%s"\nexit 0\n' "$STUB_LOG" > scripts/ci/test_nginx_conf.sh
clear_log
assert_exit 0 "script de infraestructura en verde" bash "$RUN"
assert_log_has "script test_nginx_conf"
printf '#!/usr/bin/env bash\nexit 1\n' > scripts/ci/test_nginx_conf.sh
assert_nonzero "script de infraestructura en rojo falla" bash "$RUN"
rm -rf scripts

# Con uv que falla en la cobertura termina distinto de 0.
stub_tool_fail_on uv "cov-fail-under" 1
assert_nonzero "cobertura insuficiente falla" bash "$RUN"

# Con web/package.json corre lint, tsc, test con cobertura y build.
stub_tool uv 0
add_web "$REPO"
clear_log
assert_exit 0 "api y front en verde" bash "$RUN"
assert_log_has "npm run lint"
assert_log_has "npx tsc --noEmit"
assert_log_has "npm test -- --run --coverage"
assert_log_has "npm run build"

stub_tool_fail_on npm "build" 1
assert_nonzero "build del front en rojo falla" bash "$RUN"

cd "$REPO_ROOT"
finish
