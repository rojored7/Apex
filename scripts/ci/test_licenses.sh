#!/usr/bin/env bash
# Prueba de control del chequeo de licencias (US-004, T1).
#
# 1. Un entorno con fpdf2 (LGPL) debe fallar y la salida debe nombrar fpdf2 y LGPL.
# 1b. Un entorno con python-telegram-bot (LGPL) debe fallar igual (S5-W0-1, CLAUDE.md:
#     Telegram se llama con httpx directo).
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

# caso_lgpl <etiqueta> <paquete>: un entorno con ese paquete LGPL debe fallar y la salida
# debe nombrar el paquete y LGPL.
caso_lgpl() {
  local etiqueta="$1" paquete="$2" venv="$TMP/venv-$2"
  uv venv --quiet --python 3.12 "$venv"
  uv pip install --quiet --python "$(python_de "$venv")" "$paquete"
  local codigo=0 salida
  salida="$(bash "$CHECK" "$(python_de "$venv")" 2>&1)" || codigo=$?
  if [ "$codigo" -ne 0 ] && grep -qi "$paquete" <<< "$salida" && grep -qi "LGPL" <<< "$salida"; then
    echo "  ok   $paquete rechazado (código $codigo)"
  else
    echo "  FALLA $paquete no fue rechazado como se esperaba (código $codigo)"; echo "$salida" | tail -5; fallas=$((fallas + 1))
  fi
}

echo "test_licenses: 1. fpdf2 (LGPL) debe fallar"
caso_lgpl 1 fpdf2

echo "test_licenses: 1b. python-telegram-bot (LGPL) debe fallar"
caso_lgpl 1b python-telegram-bot

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
