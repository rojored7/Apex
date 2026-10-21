#!/usr/bin/env bash
# Corre todas las pruebas de los scripts de gate (US-008, T6). Sale distinto de 0
# si alguna falla. Limpia tests/tmp/ al terminar.
set -euo pipefail
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
rm -rf "$TESTS_DIR/tmp"
mkdir -p "$TESTS_DIR/tmp"
fallas=0
total=0
for t in "$TESTS_DIR"/test_*.sh; do
  total=$((total + 1))
  if bash "$t"; then
    echo "PASA  $(basename "$t")"
  else
    echo "FALLA $(basename "$t")"
    fallas=$((fallas + 1))
  fi
  echo
done
rm -rf "$TESTS_DIR/tmp"
echo "scripts/workflow/tests: $((total - fallas)) de $total archivos en verde"
[ "$fallas" -eq 0 ]
