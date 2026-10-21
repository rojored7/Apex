#!/usr/bin/env bash
# validate-impact-analysis.sh [--allow-amber] <archivo>
#
# Gate de la Fase 0 del flujo. Busca la primera línea `Veredicto: <valor>` (con o sin
# encabezado Markdown o negrita) y acepta VERDE, APROBADO y APROBADO CON OBSERVACIONES.
# AMARILLO pasa solo con --allow-amber. ROJO, RECHAZADO, cualquier otro valor o la
# ausencia de la línea fallan (DECISIONES E, refinamiento US-008).
set -euo pipefail

usage() {
  cat <<'EOF'
Uso: validate-impact-analysis.sh [--allow-amber] <archivo.md>

Códigos de salida: 0 veredicto aceptado; 1 rechazado, ausente o archivo inexistente; 2 uso.
EOF
}

ALLOW_AMBER=0
ARCHIVO=""
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --allow-amber) ALLOW_AMBER=1 ;;
    -*) echo "validate-impact-analysis: opción desconocida: $arg" >&2; usage >&2; exit 2 ;;
    *) ARCHIVO="$arg" ;;
  esac
done
if [ -z "$ARCHIVO" ]; then usage >&2; exit 2; fi
[ -f "$ARCHIVO" ] || { echo "validate-impact-analysis: no existe $ARCHIVO" >&2; exit 1; }

LINEA="$(grep -m1 -E '^[[:space:]]*(#+[[:space:]]*)?(\*\*)?Veredicto:' "$ARCHIVO" || true)"
if [ -z "$LINEA" ]; then
  echo "validate-impact-analysis: $ARCHIVO no tiene una línea 'Veredicto: ...'" >&2
  exit 1
fi

VEREDICTO="$(printf '%s' "$LINEA" \
  | sed -E 's/^[[:space:]]*(#+[[:space:]]*)?(\*\*)?Veredicto:[[:space:]]*//' \
  | sed -E 's/^([A-Z ]+).*$/\1/' \
  | sed -E 's/[[:space:]]+$//')"

case "$VEREDICTO" in
  VERDE|APROBADO|"APROBADO CON OBSERVACIONES")
    echo "validate-impact-analysis: veredicto '$VEREDICTO' aceptado ($ARCHIVO)"; exit 0 ;;
  AMARILLO)
    if [ "$ALLOW_AMBER" -eq 1 ]; then
      echo "validate-impact-analysis: veredicto 'AMARILLO' aceptado con --allow-amber ($ARCHIVO)"; exit 0
    fi
    echo "validate-impact-analysis: veredicto 'AMARILLO' requiere --allow-amber ($ARCHIVO)" >&2; exit 1 ;;
  ROJO|RECHAZADO)
    echo "validate-impact-analysis: veredicto '$VEREDICTO' bloquea ($ARCHIVO)" >&2; exit 1 ;;
  *)
    echo "validate-impact-analysis: veredicto desconocido '$VEREDICTO' en $ARCHIVO" >&2; exit 1 ;;
esac
