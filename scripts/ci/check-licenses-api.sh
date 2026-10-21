#!/usr/bin/env bash
# check-licenses-api.sh [python]
#
# Lista blanca estricta de licencias del api (CLAUDE.md, "Licencias"; US-004, T3).
# Sin argumento, construye el entorno de runtime (sin grupo dev) en api/.venv-runtime
# con `uv sync --frozen --no-dev` y revisa lo que de verdad va en la imagen. Con un
# intérprete como argumento, revisa ese entorno (lo usan las pruebas de control).
#
# Permitidas (coincidencia parcial): MIT, BSD, Apache, PostgreSQL, ISC, 0BSD, PSF.
# MPL-2.0 solo sin modificar y por paquete, en scripts/ci/licenses-exceptions.txt.
# Prohibidas por omisión: GPL, LGPL, AGPL, BSL, SSPL y cualquier licencia desconocida.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
API="$ROOT/api"
EXCEPCIONES="$ROOT/scripts/ci/licenses-exceptions.txt"
PERMITIDAS="MIT;BSD;Apache;PostgreSQL;ISC;0BSD;PSF;Python Software Foundation"

case "${1:-}" in
  -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
esac

PY="${1:-}"
if [ -z "$PY" ]; then
  (cd "$API" && UV_PROJECT_ENVIRONMENT=.venv-runtime uv sync --frozen --no-dev --quiet)
  if [ -x "$API/.venv-runtime/bin/python" ]; then
    PY="$API/.venv-runtime/bin/python"
  else
    PY="$API/.venv-runtime/Scripts/python.exe"
  fi
fi

mapfile -t EXC < <(sed -E 's/#.*$//; s/[[:space:]]+$//' "$EXCEPCIONES" | grep -v '^$' || true)
IGNORAR=()
if [ "${#EXC[@]}" -gt 0 ]; then IGNORAR=(--ignore-packages "${EXC[@]}"); fi

echo "check-licenses-api: intérprete $PY"
echo "check-licenses-api: excepciones MPL-2.0 sin modificar: ${EXC[*]:-ninguna}"
cd "$API"
uv run --quiet pip-licenses \
  --python "$PY" \
  --from=mixed \
  --partial-match \
  --allow-only="$PERMITIDAS" \
  "${IGNORAR[@]}" \
  --format=plain \
  --order=name
echo "check-licenses-api: todas las licencias del runtime están en la lista permitida"
