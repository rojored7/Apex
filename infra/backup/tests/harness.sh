#!/usr/bin/env bash
# Arnés de las pruebas de infra/backup (S4B-W0-1, S4B-D19). Bash puro, sin bats ni
# shellcheck: cada test_*.sh hace `source harness.sh` y termina con `finish`.
# Corre igual en el host (Git Bash, WSL, CI) y dentro de apex-backup:local.
set -euo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR_SRC="$(cd "$TESTS_DIR/.." && pwd)"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/apex-backup-tests.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT
PASSES=0
FAILS=0

_ok() { PASSES=$((PASSES + 1)); echo "  ok   $1"; }
_fail() { FAILS=$((FAILS + 1)); echo "  FALLA $1"; }

# assert_eq <descripcion> <esperado> <obtenido>
assert_eq() {
  if [ "$2" = "$3" ]; then _ok "$1"; else _fail "$1 (esperado '$2', obtenido '$3')"; fi
}

# assert_ok <descripcion> <comando...>: el comando termina con 0.
assert_ok() {
  local desc="$1"; shift
  if "$@" > /dev/null 2>&1; then _ok "$desc"; else _fail "$desc"; fi
}

# assert_fails <descripcion> <comando...>: el comando termina distinto de 0.
assert_fails() {
  local desc="$1"; shift
  if "$@" > /dev/null 2>&1; then _fail "$desc (terminó con 0)"; else _ok "$desc"; fi
}

# assert_contains <descripcion> <texto> <fragmento>
assert_contains() {
  case "$2" in *"$3"*) _ok "$1" ;; *) _fail "$1 (no contiene '$3')" ;; esac
}

# assert_lacks <descripcion> <texto> <fragmento>
assert_lacks() {
  case "$2" in *"$3"*) _fail "$1 (contiene '$3')" ;; *) _ok "$1" ;; esac
}

# Intérprete de Python para validar JSON: el del sistema o el del entorno del api.
# Dentro de apex-backup:local no hay ninguno y las pruebas que lo necesitan se saltan.
py() {
  if command -v python3 > /dev/null 2>&1 && python3 -c 'import sys' > /dev/null 2>&1; then
    python3 "$@"
  elif command -v python > /dev/null 2>&1 && python -c 'import sys' > /dev/null 2>&1; then
    python "$@"
  elif command -v uv > /dev/null 2>&1; then
    uv run --directory "$BACKUP_DIR_SRC/../../api" --quiet python "$@"
  else
    return 127
  fi
}

have_python() { command -v python3 > /dev/null 2>&1 || command -v python > /dev/null 2>&1 || command -v uv > /dev/null 2>&1; }

finish() {
  echo "  resumen: $PASSES ok, $FAILS fallas"
  [ "$FAILS" -eq 0 ]
}
