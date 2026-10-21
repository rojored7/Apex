#!/usr/bin/env bash
# Pruebas de validate-impact-analysis.sh (US-008, T5; DECISIONES E, refinamiento US-008).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"
VALIDATE="$WORKFLOW_DIR/validate-impact-analysis.sh"
DIR="$(mktemp -d "$TMP_ROOT/impact.XXXXXX")"

echo "test_validate_impact"
caso() { printf '# Análisis\n\n%s\n\nTexto.\n' "$1" > "$DIR/caso.md"; echo "$DIR/caso.md"; }

assert_exit 0 "-h sale con 0" bash "$VALIDATE" -h
assert_exit 2 "sin archivo sale con 2" bash "$VALIDATE"
assert_nonzero "archivo inexistente falla" bash "$VALIDATE" "$DIR/no_existe.md"
printf '# Sin veredicto\n' > "$DIR/vacio.md"
assert_nonzero "sin línea de veredicto falla" bash "$VALIDATE" "$DIR/vacio.md"

assert_exit 0 "Veredicto: APROBADO pasa" bash "$VALIDATE" "$(caso 'Veredicto: APROBADO')"
assert_exit 0 "Veredicto: APROBADO CON OBSERVACIONES pasa" bash "$VALIDATE" "$(caso 'Veredicto: APROBADO CON OBSERVACIONES')"
assert_exit 0 "encabezado ## Veredicto: VERDE pasa" bash "$VALIDATE" "$(caso '## Veredicto: VERDE')"
assert_exit 0 "negrita **Veredicto: VERDE** pasa" bash "$VALIDATE" "$(caso '**Veredicto: VERDE**')"
assert_nonzero "Veredicto: RECHAZADO falla" bash "$VALIDATE" "$(caso 'Veredicto: RECHAZADO')"
assert_nonzero "Veredicto: ROJO falla" bash "$VALIDATE" "$(caso '## Veredicto: ROJO')"
assert_nonzero "Veredicto: AMARILLO falla sin --allow-amber" bash "$VALIDATE" "$(caso '## Veredicto: AMARILLO')"
assert_exit 0 "Veredicto: AMARILLO pasa con --allow-amber" bash "$VALIDATE" --allow-amber "$(caso '## Veredicto: AMARILLO')"
assert_nonzero "ROJO falla aunque haya --allow-amber" bash "$VALIDATE" --allow-amber "$(caso '## Veredicto: ROJO')"
assert_nonzero "valor desconocido falla" bash "$VALIDATE" "$(caso 'Veredicto: TAL VEZ')"

# Regresión: el análisis de impacto real del proyecto.
assert_exit 0 "00b_impact_analysis.md real pasa con --allow-amber" bash "$VALIDATE" --allow-amber "$REPO_ROOT/docs/ddd/00b_impact_analysis.md"
assert_nonzero "00b_impact_analysis.md real falla sin --allow-amber" bash "$VALIDATE" "$REPO_ROOT/docs/ddd/00b_impact_analysis.md"

finish
