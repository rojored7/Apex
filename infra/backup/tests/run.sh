#!/usr/bin/env bash
# Corre todas las pruebas de infra/backup (S4B-W0-1, S4B-D19). Sale distinto de 0 si alguna
# falla. Sin dependencias: Bash puro. Funciona en el host y dentro de apex-backup:local:
#   docker run --rm -v "$PWD/infra/backup:/opt/backup-src:ro" --entrypoint bash apex-backup:local \
#     /opt/backup-src/tests/run.sh
set -euo pipefail
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
echo "infra/backup/tests: $((total - fallas)) de $total archivos en verde"
[ "$fallas" -eq 0 ]
