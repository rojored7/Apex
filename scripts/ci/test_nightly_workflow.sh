#!/usr/bin/env bash
# test_nightly_workflow.sh
#
# Rojo S8-W0-2 (S8-D20): .github/workflows/nightly.yml existe para la prueba de resistencia de 12 h de
# la TV (job `tv-soak`). Corre a diario y a mano, nunca en `pull_request` ni en `push` (no es gate de
# PR), con permisos de solo lectura y cada acción fijada por el SHA de su commit. Grep puro, sin Docker.
# Con un argumento revisa ese archivo en lugar del del repositorio.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
WF="${1:-$ROOT/.github/workflows/nightly.yml}"
fallas=0
ok() { echo "  ok   $1"; }
falla() { echo "  FALLA $1"; fallas=$((fallas + 1)); }

if [ ! -f "$WF" ]; then
  echo "  FALLA no existe $WF"
  echo "test_nightly_workflow: 1 fallas"
  exit 1
fi

# El bloque `on:` va desde su línea hasta la siguiente clave de primer nivel.
on_block="$(awk '/^on:/ { d=1; print; next } d && /^[^ #]/ { d=0 } d' "$WF")"
if grep -Eq '^\s+schedule:' <<< "$on_block" && grep -Eq '^\s+-\s+cron:' <<< "$on_block"; then ok "tiene schedule con cron"; else falla "falta on.schedule con cron"; fi
if grep -Eq '^\s+workflow_dispatch:' <<< "$on_block"; then ok "tiene workflow_dispatch"; else falla "falta on.workflow_dispatch"; fi
if grep -Eq '^\s+(pull_request|pull_request_target|push):' <<< "$on_block"; then falla "no debe correr en pull_request ni en push (no es gate de PR)"; else ok "no corre en pull_request ni en push"; fi
if grep -Eq '^permissions:' "$WF" && grep -Eq '^\s+contents:\s+read\s*$' "$WF"; then ok "permisos de solo lectura"; else falla "falta permissions: contents: read"; fi
if grep -Eq '^\s+tv-soak:' "$WF"; then ok "define el job tv-soak"; else falla "falta el job tv-soak"; fi
sin_sha="$(grep -E '^\s*-?\s*uses:' "$WF" | grep -Ev 'uses:\s+\S+@[0-9a-f]{40}(\s|$)' || true)"
if [ -z "$sin_sha" ]; then ok "toda acción va fijada por SHA"; else falla "acción sin SHA de commit: $sin_sha"; fi
# S8-W0b (L5): ningún permiso de escritura en todo el archivo y nada de `workflow_run` (encadenaría
# este flujo a otro con permisos distintos).
if grep -Eq ':[[:space:]]*write([[:space:]]|$)' "$WF"; then falla "no debe declarar ningún permiso write"; else ok "sin permisos write"; fi
if grep -Eq '^[[:space:]]+workflow_run:' <<< "$on_block"; then falla "no debe dispararse con workflow_run"; else ok "sin workflow_run"; fi
if grep -Eq 'secrets\.' "$WF"; then falla "el flujo nocturno no debe usar secretos"; else ok "sin secretos"; fi

echo "test_nightly_workflow: $fallas fallas"
[ "$fallas" -eq 0 ]
