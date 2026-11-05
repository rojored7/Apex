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

# Archivo de prueba inexistente o con ruta no permitida.
assert_nonzero "archivo de prueba inexistente falla" bash "$GATE" core/config tests/core/no_existe.py
assert_nonzero "ruta con .. falla" bash "$GATE" core/config tests/../src/app/core/config.py
assert_nonzero "ruta que empieza por - falla" bash "$GATE" core/config -tests/core/test_config.py

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


# Mapeo de cli (S4B-D28): cli.py obligatorio; cli_base.py, cli_ops/, seed/ e imports/ si existen.
mkdir -p "$REPO/api/tests/cli"
assert_nonzero "cli sin cli.py falla" bash "$GATE" cli tests/core/test_config.py
printf 'X = 1\n' > "$REPO/api/src/app/cli.py"
clear_log
assert_exit 0 "cli solo con cli.py" bash "$GATE" cli tests/core/test_config.py
assert_log_has "ruff check src/app/cli.py"
assert_log_lacks "cli_base.py"
printf 'Y = 1\n' > "$REPO/api/src/app/cli_base.py"
mkdir -p "$REPO/api/src/app/cli_ops"
printf 'Z = 1\n' > "$REPO/api/src/app/cli_ops/__init__.py"
clear_log
assert_exit 0 "cli con cli_base.py y cli_ops/" bash "$GATE" cli tests/core/test_config.py
assert_log_has "ruff check src/app/cli.py src/app/cli_base.py src/app/cli_ops"
assert_log_has "ruff format --check src/app/cli.py src/app/cli_base.py src/app/cli_ops"
assert_log_has "mypy src/app/cli.py src/app/cli_base.py src/app/cli_ops"
assert_log_lacks "src/app/seed"

# S5-D72 (B13): cli_manifest.py entra al caso cli cuando existe y no antes.
assert_log_lacks "cli_manifest.py"
printf 'W = 1
' > "$REPO/api/src/app/cli_manifest.py"
clear_log
assert_exit 0 "cli con cli_manifest.py" bash "$GATE" cli tests/core/test_config.py
assert_log_has "ruff check src/app/cli.py src/app/cli_base.py src/app/cli_ops src/app/cli_manifest.py"
assert_log_has "mypy src/app/cli.py src/app/cli_base.py src/app/cli_ops src/app/cli_manifest.py"

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
# S4B-V9: el tsconfig temporal incluye los archivos de soporte de las pruebas (jest-dom, vitest-axe),
# si existen, para que tsc vea los matchers; un stub de npx copia el tsconfig antes de que el gate lo borre.
mkdir -p "$REPO/web/src/test"
printf 'import "@testing-library/jest-dom/vitest";
' > "$REPO/web/src/test/setup.ts"
printf 'declare module "vitest-axe/matchers";
' > "$REPO/web/src/test/vitest-axe.d.ts"
# confirmados en el repo de prueba: no deben entrar por "archivos nuevos" sino por la regla del gate
git -C "$REPO" add -A > /dev/null 2>&1 && git -C "$REPO" -c user.email=t@t -c user.name=t commit -q -m "soporte de pruebas" > /dev/null 2>&1
{
  echo '#!/usr/bin/env bash'
  echo "echo \"npx \$*\" >> \"$STUB_LOG\""
  echo "[ \"\$1\" = tsc ] && cp tsconfig.slice.json \"$REPO/tsconfig.slice.copia.json\""
  echo 'exit 0'
} > "$STUB_BIN/npx"
chmod +x "$STUB_BIN/npx"
clear_log
SLICE_BASE="$(git -C "$REPO" rev-parse HEAD)" assert_exit 0 "web/shared con archivos de soporte de pruebas" bash "$GATE" web/shared src/shared/shared.test.ts
assert_file_exists "$REPO/tsconfig.slice.copia.json"
assert_true grep -q '"src/test/setup.ts"' "$REPO/tsconfig.slice.copia.json"
assert_true grep -q '"src/test/vitest-axe.d.ts"' "$REPO/tsconfig.slice.copia.json"
rm -f "$REPO/tsconfig.slice.copia.json"
stub_tool npx 0
clear_log
assert_exit 0 "web/members mapea a src/features/members" bash "$GATE" web/members tests/unit/app.test.ts
assert_log_has "src/features/members/index.ts"
assert_nonzero "web/fantasma falla" bash "$GATE" web/fantasma
stub_tool_fail_on npx "tsc" 1
assert_nonzero "tsc en rojo falla" bash "$GATE" web/app tests/unit/app.test.ts
assert_file_missing "$REPO/web/tsconfig.slice.json"

cd "$REPO_ROOT"
finish
