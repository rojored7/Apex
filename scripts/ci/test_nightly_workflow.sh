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

# S9-X3 (S9-D24, L-6): job `tv-soak-real`, la prueba de la TV en tiempo real (hasta 5,5 h, sin `page.clock`).
# Solo por `workflow_dispatch` con `real_hours` distinto de 0 (no corre con `schedule`), el valor entra por
# `env:` (nunca interpolado en `run:`), permisos de solo lectura propios y tope de 350 minutos.
job_real="$(awk '/^  tv-soak-real:/ { d=1; print; next } d && /^  [A-Za-z0-9_-]+:/ { d=0 } d' "$WF")"
if [ -n "$job_real" ]; then ok "define el job tv-soak-real"; else falla "falta el job tv-soak-real"; fi
if grep -Eq '^\s+real_hours:' <<< "$on_block"; then ok "workflow_dispatch declara la entrada real_hours"; else falla "falta la entrada real_hours en workflow_dispatch"; fi
if grep -Eq '^\s+default:\s+"0"' <<< "$on_block"; then ok "real_hours vale 0 por defecto (S9-D38)"; else falla "real_hours debe valer \"0\" por defecto (S9-D38): un disparo manual normal no gasta 5 h"; fi
if grep -Eq "^\s+if:.*github\.event_name\s*==\s*'workflow_dispatch'" <<< "$job_real" && grep -Eq '^\s+if:.*real_hours' <<< "$job_real"; then ok "tv-soak-real corre solo por workflow_dispatch y con real_hours"; else falla "tv-soak-real necesita if: con workflow_dispatch y real_hours distinto de 0"; fi
if grep -Eq '^\s+timeout-minutes:\s+350\s*$' <<< "$job_real"; then ok "tv-soak-real con timeout-minutes 350"; else falla "tv-soak-real debe tener timeout-minutes: 350"; fi
if grep -Eq '^\s+permissions:' <<< "$job_real" && grep -Eq '^\s+contents:\s+read\s*$' <<< "$job_real"; then ok "tv-soak-real declara permissions: contents: read"; else falla "tv-soak-real debe declarar permissions: contents: read"; fi
if grep -Eq '^\s+REAL_HOURS:\s+\$\{\{\s*inputs\.real_hours\s*\}\}' <<< "$job_real"; then ok "real_hours entra por env:"; else falla "real_hours debe entrar por env: REAL_HOURS"; fi
# Ninguna línea fuera de `env:` ni de `if:` puede mencionar `inputs` ni `github.event.inputs` ni volcar el contexto
# (`toJSON(inputs)`, `toJSON(github)`, `inputs['x']`): es la vía de la inyección de guion en run:.
inter="$(grep -E '(inputs\.|inputs\[|github\.event\.inputs|toJSON\(\s*(inputs|github))' "$WF" | grep -Ev '^\s*#' | grep -Ev '^\s+(if|[A-Z][A-Z0-9_]*):\s' || true)"
if [ -z "$inter" ]; then ok "inputs solo aparece en env: e if:"; else falla "inputs fuera de env:/if:: $inter"; fi
# M-1: ningún bloque `run:` del archivo entero (entre `run:` y la siguiente clave del paso) usa `${{ ... }}`: ni inputs,
# ni env, ni github.ref_name. Lo que necesite un guion entra por `env:` y se lee como variable de la shell.
if awk '/^[[:space:]]+(- )?run:/ { r=1; if ($0 ~ /\$\{\{/) bad=1; next } /^[[:space:]]+(- )?(name|uses|with|env|if|working-directory|shell|id):/ { r=0 } r && /\$\{\{/ { bad=1 } END { exit bad }' "$WF"; then ok "ningún run: usa \${{ }}"; else falla "hay \${{ }} dentro de un bloque run:"; fi
# M-2 (L-6): los tres controles que no se pueden quitar sin que el guion lo note.
if grep -Fq 'name: validar real_hours' <<< "$job_real" && grep -Eq '=~ \^\[0-9\]\+\(\[\.\]\[0-9\]\+\)\?\$' <<< "$job_real" && grep -Eq 'h > 0 && h <= 5\.5' <<< "$job_real"; then ok "paso que valida real_hours (regex numérica y tope 5,5)"; else falla "falta el paso que valida real_hours con la regex numérica y el tope 5,5"; fi
checkouts="$(grep -Ec '^\s*-?\s*uses:\s+actions/checkout@' "$WF" || true)"
persist="$(grep -Ec '^\s+persist-credentials:\s+false\s*$' "$WF" || true)"
if [ "$checkouts" -gt 0 ] && [ "$checkouts" -eq "$persist" ]; then ok "cada actions/checkout lleva persist-credentials: false ($checkouts)"; else falla "checkout: $checkouts, persist-credentials: false: $persist"; fi
if grep -Fq "if: github.event_name == 'workflow_dispatch' && inputs.real_hours != '0'" <<< "$job_real"; then ok "if: literal con && y != '0'"; else falla "el if: de tv-soak-real debe ser literal: github.event_name == 'workflow_dispatch' && inputs.real_hours != '0'"; fi
# L-1: validar real_hours es el primer paso del job, antes de checkout.
primer="$(awk '/^    steps:/ { s=1; next } s && /^      - / { print; exit }' <<< "$job_real")"
if grep -Fq 'name: validar real_hours' <<< "$primer"; then ok "validar real_hours es el primer paso"; else falla "el primer paso de tv-soak-real debe ser validar real_hours (primero: $primer)"; fi
# L-2: grupo de concurrencia propio (job y, a nivel de flujo, por evento) para no dejar en espera al tv-soak nocturno.
if grep -Eq '^\s+concurrency:' <<< "$job_real" && grep -Eq '^\s+group:\s+nightly-real' <<< "$job_real"; then ok "tv-soak-real con su propio grupo de concurrencia"; else falla "tv-soak-real debe declarar concurrency: con group: nightly-real..."; fi
if grep -Eq '^\s+group:\s+nightly-.*github\.event_name' "$WF"; then ok "el grupo del flujo distingue el evento"; else falla "el group: del flujo debe incluir github.event_name"; fi

echo "test_nightly_workflow: $fallas fallas"
[ "$fallas" -eq 0 ]
