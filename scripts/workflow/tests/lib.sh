#!/usr/bin/env bash
# Utilidades de prueba para los scripts de gate (US-008, T1). Sin dependencias
# externas: repositorios git temporales y herramientas simuladas en PATH.
# Cada archivo test_*.sh hace `source lib.sh` y llama a `finish` al final.
set -euo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKFLOW_DIR="$(cd "$TESTS_DIR/.." && pwd)"
REPO_ROOT="$(cd "$WORKFLOW_DIR/../.." && pwd)"
TMP_ROOT="$TESTS_DIR/tmp"
REAL_GIT="$(command -v git)"
ORIGINAL_PATH="$PATH"
PASSES=0
FAILS=0

mkdir -p "$TMP_ROOT"
STUB_BIN="$(mktemp -d "$TMP_ROOT/bin.XXXXXX")"
STUB_LOG="$STUB_BIN/calls.log"
: > "$STUB_LOG"

# Activa las herramientas simuladas: se anteponen a PATH.
use_stubs() {
  export PATH="$STUB_BIN:$ORIGINAL_PATH"
}

# Repositorio temporal con rama feat/x, un commit y un esqueleto de api/.
# Imprime la ruta.
mk_repo() {
  local dir
  dir="$(mktemp -d "$TMP_ROOT/repo.XXXXXX")"
  (
    cd "$dir"
    "$REAL_GIT" init -q -b main .
    "$REAL_GIT" config user.email "pruebas@apex.local"
    "$REAL_GIT" config user.name "pruebas"
    "$REAL_GIT" config commit.gpgsign false
    "$REAL_GIT" config core.hooksPath /dev/null
    "$REAL_GIT" config core.autocrlf false
    mkdir -p api/src/app/core api/tests/core api/tests/architecture
    printf 'VALOR = 1\n' > api/src/app/core/config.py
    printf 'def test_config() -> None:\n    assert True\n' > api/tests/core/test_config.py
    printf 'def test_arquitectura() -> None:\n    assert True\n' > api/tests/architecture/test_a.py
    printf '[project]\nname = "apex-api"\n' > api/pyproject.toml
    "$REAL_GIT" add -A
    "$REAL_GIT" commit -q -m "chore: inicio"
    "$REAL_GIT" switch -q -c feat/x
  )
  echo "$dir"
}

# Agrega un esqueleto de web/ al repositorio temporal dado.
add_web() {
  local dir="$1"
  mkdir -p "$dir/web/src/features/members" "$dir/web/src/shared" "$dir/web/tests/unit"
  printf '{ "name": "apex-web", "private": true }\n' > "$dir/web/package.json"
  printf '{ "compilerOptions": { "strict": true } }\n' > "$dir/web/tsconfig.json"
  printf 'export const app = 1;\n' > "$dir/web/src/App.tsx"
  printf 'export const m = 1;\n' > "$dir/web/src/features/members/index.ts"
  printf 'export const s = 1;\n' > "$dir/web/src/shared/index.ts"
  printf 'import { test } from "vitest";\ntest("x", () => {});\n' > "$dir/web/tests/unit/app.test.ts"
  printf 'import { test } from "vitest";\ntest("y", () => {});\n' > "$dir/web/src/shared/shared.test.ts"
  (cd "$dir" && "$REAL_GIT" add -A && "$REAL_GIT" commit -q -m "chore: web")
}

# stub_tool <nombre> <codigo>: ejecutable falso que registra sus argumentos y
# termina siempre con <codigo>.
stub_tool() {
  local name="$1" code="$2"
  cat > "$STUB_BIN/$name" <<EOF
#!/usr/bin/env bash
echo "$name \$*" >> "$STUB_LOG"
exit $code
EOF
  chmod +x "$STUB_BIN/$name"
}

# stub_tool_fail_on <nombre> <patron> <codigo>: termina con <codigo> solo cuando
# sus argumentos contienen <patron>; si no, con 0.
stub_tool_fail_on() {
  local name="$1" pattern="$2" code="$3"
  cat > "$STUB_BIN/$name" <<EOF
#!/usr/bin/env bash
echo "$name \$*" >> "$STUB_LOG"
case "\$*" in
  *"$pattern"*) exit $code ;;
esac
exit 0
EOF
  chmod +x "$STUB_BIN/$name"
}

# Envoltorio de git que registra el subcomando y delega en el git real.
stub_git_wrapper() {
  cat > "$STUB_BIN/git" <<EOF
#!/usr/bin/env bash
echo "git \$1" >> "$STUB_LOG"
exec "$REAL_GIT" "\$@"
EOF
  chmod +x "$STUB_BIN/git"
}

clear_log() { : > "$STUB_LOG"; }

log_has() { grep -q -- "$1" "$STUB_LOG"; }

_ok() { PASSES=$((PASSES + 1)); echo "  ok   $1"; }
_fail() { FAILS=$((FAILS + 1)); echo "  FALLA $1"; }

# assert_exit <esperado> <descripcion> <comando...>
assert_exit() {
  local expected="$1" desc="$2"; shift 2
  local code=0
  "$@" > /dev/null 2>&1 || code=$?
  if [ "$code" -eq "$expected" ]; then _ok "$desc"; else _fail "$desc (código $code, se esperaba $expected)"; fi
}

# assert_nonzero <descripcion> <comando...>
assert_nonzero() {
  local desc="$1"; shift
  local code=0
  "$@" > /dev/null 2>&1 || code=$?
  if [ "$code" -ne 0 ]; then _ok "$desc"; else _fail "$desc (terminó con 0)"; fi
}

assert_true() { if "$@" > /dev/null 2>&1; then _ok "$*"; else _fail "$*"; fi; }

assert_log_has() { if log_has "$1"; then _ok "registro contiene: $1"; else _fail "registro no contiene: $1"; fi; }

assert_log_lacks() { if log_has "$1"; then _fail "registro contiene (no debía): $1"; else _ok "registro no contiene: $1"; fi; }

assert_file_exists() { if [ -e "$1" ]; then _ok "existe $1"; else _fail "no existe $1"; fi; }

assert_file_missing() { if [ -e "$1" ]; then _fail "existe (no debía) $1"; else _ok "no existe $1"; fi; }

head_of() { (cd "$1" && "$REAL_GIT" rev-parse HEAD); }

# assert_no_new_commit <repo> <head_previo> <descripcion>
assert_no_new_commit() {
  if [ "$(head_of "$1")" = "$2" ]; then _ok "$3: sin commit nuevo"; else _fail "$3: se creó un commit"; fi
}

finish() {
  echo "  resumen: $PASSES ok, $FAILS fallas"
  [ "$FAILS" -eq 0 ]
}
