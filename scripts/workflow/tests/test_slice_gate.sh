#!/usr/bin/env bash
# Pruebas de slice-gate.sh (US-008, T2; ajuste A-01 del plan de sprints).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
GATE="$WORKFLOW_DIR/slice-gate.sh"

echo "test_slice_gate"
REPO="$(mk_repo)"
cd "$REPO"
use_stubs
stub_tool uv 0

assert_exit 2 "sin argumento muestra ayuda y sale con 2" bash "$GATE"
assert_exit 0 "-h sale con 0" bash "$GATE" -h
assert_nonzero "nombre inválido con mayúsculas" bash "$GATE" Core/Config
assert_nonzero "nombre inválido con ruta relativa" bash "$GATE" ../core
assert_nonzero "módulo inexistente falla" bash "$GATE" fantasma

# Con lista de archivos: corre solo esos archivos más tests/architecture.
clear_log
assert_exit 0 "core/config con lista en verde" bash "$GATE" core/config tests/core/test_config.py
assert_log_has "ruff check src/app/core/config.py"
assert_log_has "ruff format --check src/app/core/config.py"
assert_log_has "mypy src/app/core/config.py"
assert_log_has "pytest tests/core/test_config.py tests/architecture"
assert_file_exists "$REPO/.git/apex/slice-gate.ok"
assert_true grep -q "core/config" "$REPO/.git/apex/slice-gate.ok"

# Sin lista: la carpeta de pruebas del módulo más tests/architecture.
clear_log
rm -f "$REPO/.git/apex/slice-gate.ok"
assert_exit 0 "core/config sin lista en verde" bash "$GATE" core/config
assert_log_has "pytest tests/core tests/architecture"

# Archivo de prueba inexistente.
assert_nonzero "archivo de prueba inexistente falla" bash "$GATE" core/config tests/core/no_existe.py

# Mapeo: architecture no tiene ruta de código; main apunta a main.py.
printf 'def create_app() -> None:\n    pass\n' > "$REPO/api/src/app/main.py"
clear_log
assert_exit 0 "architecture solo corre pruebas" bash "$GATE" architecture
assert_log_lacks "ruff check"
assert_log_has "pytest tests/architecture"
clear_log
assert_exit 0 "main mapea a src/app/main.py" bash "$GATE" main tests/core/test_config.py
assert_log_has "mypy src/app/main.py"

# Regex: guiones y varios niveles.
mkdir -p "$REPO/api/src/app/modules/notification-rules" "$REPO/api/tests/notification-rules"
printf 'X = 1\n' > "$REPO/api/src/app/modules/notification-rules/service.py"
assert_exit 0 "nombre con guiones es válido" bash "$GATE" notification-rules tests/core/test_config.py

# Con mypy en rojo: falla y no escribe sello.
rm -f "$REPO/.git/apex/slice-gate.ok"
stub_tool_fail_on uv "mypy" 1
assert_nonzero "uv falla en mypy" bash "$GATE" core/config tests/core/test_config.py
assert_file_missing "$REPO/.git/apex/slice-gate.ok"

# Rama web/: eslint acotado, tsc con tsconfig.slice.json temporal y vitest.
stub_tool uv 0
stub_tool npx 0
add_web "$REPO"
printf 'export const m = 2;\n' > "$REPO/web/src/features/members/index.ts"
clear_log
assert_exit 0 "web/shared con lista en verde" bash "$GATE" web/shared src/shared/shared.test.ts
assert_log_has "eslint"
assert_log_has "src/shared/shared.test.ts"
assert_log_has "tsc --noEmit -p tsconfig.slice.json"
assert_log_has "vitest run src/shared/shared.test.ts"
assert_file_missing "$REPO/web/tsconfig.slice.json"
clear_log
assert_exit 0 "web/members mapea a src/features/members" bash "$GATE" web/members tests/unit/app.test.ts
assert_log_has "src/features/members/index.ts"
assert_nonzero "web/fantasma falla" bash "$GATE" web/fantasma
stub_tool_fail_on npx "tsc" 1
assert_nonzero "tsc en rojo falla" bash "$GATE" web/app tests/unit/app.test.ts
assert_file_missing "$REPO/web/tsconfig.slice.json"

cd "$REPO_ROOT"
finish
