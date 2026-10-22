#!/usr/bin/env bash
# check-key-files.sh [archivos...]
#
# Falla si algún archivo versionado (o pasado por argumento, en pre-commit) es material de
# llave por su nombre: kek.bin, sign-ed25519.key, jwt_ed25519.pem, jwt_ed25519.pub, *.kek,
# o un .env que no sea .env.example ni .env.seed.example (US-039; M-5 de la revisión del
# Sprint 1; .env.seed de S2-W0-1). gitleaks no detecta bytes crudos sin cabecera PEM, así
# que el nombre es la única señal. Casos en scripts/ci/test_check_key_files.sh.
set -euo pipefail

if [ "$#" -gt 0 ]; then
  archivos=("$@")
else
  mapfile -t archivos < <(git ls-files)
fi
malos=()
for f in "${archivos[@]}"; do
  base="$(basename "$f")"
  case "$base" in
    kek.bin|sign-ed25519.key|jwt_ed25519.pem|jwt_ed25519.pub|*.kek) malos+=("$f") ;;
    .env.example|.env.seed.example) ;;
    .env|.env.*) malos+=("$f") ;;
  esac
done
if [ "${#malos[@]}" -gt 0 ]; then
  echo "check-key-files: material de llave o .env en el repositorio:" >&2
  printf '  %s\n' "${malos[@]}" >&2
  exit 1
fi
echo "check-key-files: sin archivos de llave ni .env versionados"
