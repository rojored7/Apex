#!/usr/bin/env bash
# check-licenses-api.sh [--extra <grupo>] [python]
# check-licenses-api.sh --from-list <archivo>
#
# Lista blanca estricta de licencias del api (CLAUDE.md, "Licencias"; US-004, T3).
# Sin argumento, construye el entorno de runtime (sin grupo dev) en api/.venv-runtime
# con `uv sync --frozen --no-dev` y revisa lo que de verdad va en la imagen. Con
# `--extra s3` suma el grupo opcional (boto3, S6-D21) y revisa también sus licencias.
# Con un intérprete como argumento, revisa ese entorno (lo usan las pruebas de control).
# Con `--from-list <archivo>` revisa una lista ficticia en el formato `plain` de pip-licenses
# (`Name Version License`, con encabezado), sin entorno ni red (pruebas de control).
#
# Además de la licencia, rechaza por NOMBRE `oqs` y `liboqs-python` (S6-D51: la firma de v0.3
# es Ed25519; los paquetes post-cuánticos llegan con EP-26 y no se instalan por accidente).
#
# Permitidas (coincidencia parcial): MIT, BSD, Apache, PostgreSQL, ISC, 0BSD, PSF.
# MPL-2.0 solo sin modificar y por paquete, en scripts/ci/licenses-exceptions.txt.
# Prohibidas por omisión: GPL, LGPL, AGPL, BSL, SSPL y cualquier licencia desconocida.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
API="$ROOT/api"
EXCEPCIONES="$ROOT/scripts/ci/licenses-exceptions.txt"
PERMITIDAS="MIT;BSD;Apache;PostgreSQL;ISC;0BSD;PSF;Python Software Foundation"
PROHIBIDOS_POR_NOMBRE="oqs liboqs-python"

case "${1:-}" in
  -h|--help) sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
esac

if [ "${1:-}" = "--from-list" ]; then
  LISTA="${2:?--from-list necesita un archivo}"
  rc=0
  while read -r nombre _version licencia; do
    case "$nombre" in Name|"") continue ;; esac
    nombre_n="$(tr 'A-Z_' 'a-z-' <<< "$nombre")"
    for prohibido in $PROHIBIDOS_POR_NOMBRE; do
      if [ "$nombre_n" = "$prohibido" ]; then
        echo "check-licenses-api: paquete prohibido por nombre: $nombre (S6-D51, llega con EP-26)" >&2; rc=1
      fi
    done
    ok=0
    IFS=';' read -ra parciales <<< "$PERMITIDAS"
    for parcial in "${parciales[@]}"; do
      if grep -qiF -- "$parcial" <<< "$licencia"; then ok=1; fi
    done
    if [ "$ok" -eq 0 ]; then
      echo "check-licenses-api: licencia no permitida: $nombre ($licencia)" >&2; rc=1
    fi
  done < "$LISTA"
  exit "$rc"
fi

EXTRA=""
if [ "${1:-}" = "--extra" ]; then
  EXTRA="${2:?--extra necesita el nombre del grupo}"
  shift 2
fi

PY="${1:-}"
if [ -z "$PY" ]; then
  EXTRA_ARGS=()
  if [ -n "$EXTRA" ]; then EXTRA_ARGS=(--extra "$EXTRA"); fi
  (cd "$API" && UV_PROJECT_ENVIRONMENT=.venv-runtime uv sync --frozen --no-dev --quiet "${EXTRA_ARGS[@]}")
  if [ -x "$API/.venv-runtime/bin/python" ]; then
    PY="$API/.venv-runtime/bin/python"
  else
    PY="$API/.venv-runtime/Scripts/python.exe"
  fi
fi

mapfile -t EXC < <(sed -E 's/#.*$//; s/[[:space:]]+$//' "$EXCEPCIONES" | grep -v '^$' || true)
IGNORAR=()
if [ "${#EXC[@]}" -gt 0 ]; then IGNORAR=(--ignore-packages "${EXC[@]}"); fi

echo "check-licenses-api: intérprete $PY${EXTRA:+ (grupo opcional $EXTRA)}"
echo "check-licenses-api: excepciones MPL-2.0 sin modificar: ${EXC[*]:-ninguna}"
cd "$API"
# Rechazo por nombre (decisión, no licencia): sale antes de revisar licencias.
instalados="$(uv pip freeze --python "$PY" | sed -E 's/[=@ ].*$//' | tr 'A-Z_' 'a-z-')"
for nombre in $PROHIBIDOS_POR_NOMBRE; do
  if grep -qx "$nombre" <<< "$instalados"; then
    echo "check-licenses-api: paquete prohibido por nombre: $nombre (S6-D51, llega con EP-26)" >&2
    exit 1
  fi
done
uv run --quiet pip-licenses \
  --python "$PY" \
  --from=mixed \
  --partial-match \
  --allow-only="$PERMITIDAS" \
  "${IGNORAR[@]}" \
  --format=plain \
  --order=name
echo "check-licenses-api: todas las licencias del runtime están en la lista permitida"
