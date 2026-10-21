#!/usr/bin/env bash
# Prueba de control del chequeo de licencias (US-004, T1).
#
# 1. Un entorno con fpdf2 (LGPL) debe fallar y la salida debe nombrar fpdf2 y LGPL.
# 2. Un entorno con un paquete sin metadatos de licencia debe fallar (criterio 6).
# 3. El entorno de runtime real del api debe pasar.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
CHECK="$ROOT/scripts/ci/check-licenses-api.sh"
TMP="$(mktemp -d "$ROOT/scripts/ci/tmp.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
fallas=0

python_de() {
  if [ -x "$1/bin/python" ]; then echo "$1/bin/python"; else echo "$1/Scripts/python.exe"; fi
}

echo "test_licenses: 1. fpdf2 (LGPL) debe fallar"
uv venv --quiet --python 3.12 "$TMP/venv-lgpl"
uv pip install --quiet --python "$(python_de "$TMP/venv-lgpl")" fpdf2
codigo=0
salida="$(bash "$CHECK" "$(python_de "$TMP/venv-lgpl")" 2>&1)" || codigo=$?
if [ "$codigo" -ne 0 ] && grep -qi "fpdf2" <<< "$salida" && grep -qi "LGPL" <<< "$salida"; then
  echo "  ok   fpdf2 rechazado (código $codigo)"
else
  echo "  FALLA fpdf2 no fue rechazado como se esperaba (código $codigo)"; echo "$salida" | tail -5; fallas=$((fallas + 1))
fi

echo "test_licenses: 2. paquete sin licencia debe fallar"
uv venv --quiet --python 3.12 "$TMP/venv-sin"
uv pip install --quiet --python "$(python_de "$TMP/venv-sin")" "$ROOT/scripts/ci/fixtures/sin-licencia"
codigo=0
salida="$(bash "$CHECK" "$(python_de "$TMP/venv-sin")" 2>&1)" || codigo=$?
if [ "$codigo" -ne 0 ] && grep -qi "sin-licencia\|sin_licencia" <<< "$salida"; then
  echo "  ok   paquete sin licencia rechazado (código $codigo)"
else
  echo "  FALLA el paquete sin licencia no fue rechazado (código $codigo)"; echo "$salida" | tail -5; fallas=$((fallas + 1))
fi

echo "test_licenses: 3. runtime real del api debe pasar"
if bash "$CHECK" > "$TMP/runtime.log" 2>&1; then
  echo "  ok   runtime en verde"
else
  echo "  FALLA runtime rechazado"; tail -8 "$TMP/runtime.log"; fallas=$((fallas + 1))
fi

echo "test_licenses: $fallas fallas"
[ "$fallas" -eq 0 ]
