#!/usr/bin/env bash
# test_images_pinned.sh [raíz]
#
# Imágenes base por digest (S3-D62; deuda L3 de la revisión de Fase 4 del Sprint 2).
# Grep puro, sin Docker. Falla si alguna de estas referencias no va como
# `imagen:tag@sha256:<64 hex>` o si no lleva, en el bloque de comentarios justo encima,
# la fecha de la consulta (AAAA-MM-DD) y el comando de renovación
# (`docker buildx imagetools inspect`):
#   - cada `FROM` de api/Dockerfile y web/Dockerfile;
#   - cada `image:` de infra/compose.yml e infra/compose.dev.yml, salvo las imágenes
#     propias `apex-*:local`;
#   - la imagen de Nginx de scripts/ci/test_nginx_conf.sh (toda mención `nginx:<tag>`);
#   - cada `image:` de .github/workflows/ci.yml (L2 de la revisión de Fase 4 del Sprint 3),
#     y el digest de `postgres:16` de ese archivo debe ser el de infra/compose.yml.
# Renovación: docs/RUNBOOK.md, sección 7. Con un argumento, revisa esa raíz en lugar del
# repositorio (para probar el script sobre una copia).
set -euo pipefail

usage() {
  sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
}
case "${1:-}" in
  -h|--help) usage; exit 0 ;;
esac

ROOT="${1:-$(git rev-parse --show-toplevel)}"
fallas=0
archivos_con_falla=""
ok() { echo "  ok   $1"; }
falla() {
  echo "  FALLA $2"
  fallas=$((fallas + 1))
  case " $archivos_con_falla " in
    *" $1 "*) ;;
    *) archivos_con_falla="$archivos_con_falla $1" ;;
  esac
}

DIGEST_RE='@sha256:[0-9a-f]{64}([^0-9a-f]|$)'
FECHA_RE='20[0-9][0-9]-[01][0-9]-[0-3][0-9]'

# comentario_con_fecha <archivo> <número de línea>: el bloque de líneas de comentario
# contiguas justo encima de la línea lleva una fecha y el comando de renovación.
comentario_con_fecha() {
  local archivo="$1" linea="$2" bloque
  bloque="$(awk -v n="$linea" '
    NR < n { if ($0 ~ /^[[:space:]]*#/) { b = b $0 "\n" } else { b = "" } }
    NR == n { printf "%s", b; exit }
  ' "$archivo")"
  printf '%s' "$bloque" | grep -Eq "$FECHA_RE" && printf '%s' "$bloque" | grep -q 'imagetools inspect'
}

# revisa <archivo relativo> <número de línea> <referencia>
revisa() {
  local rel="$1" n="$2" ref="$3"
  if ! printf '%s' "$ref" | grep -Eq "$DIGEST_RE"; then
    falla "$rel" "$rel:$n $ref sin @sha256:<digest>"
  elif ! comentario_con_fecha "$ROOT/$rel" "$n"; then
    falla "$rel" "$rel:$n $ref sin comentario con fecha y comando de renovación encima"
  else
    ok "$rel:$n ${ref%%@*} por digest con fecha"
  fi
}

existe() {
  if [ -f "$ROOT/$1" ]; then return 0; fi
  falla "$1" "no existe $1"
  return 1
}

for rel in api/Dockerfile web/Dockerfile; do
  existe "$rel" || continue
  vistos=0
  while IFS=: read -r n resto; do
    ref="$(printf '%s' "$resto" | awk '{print $2}')"
    vistos=$((vistos + 1))
    revisa "$rel" "$n" "$ref"
  done < <(grep -nE '^[[:space:]]*FROM[[:space:]]' "$ROOT/$rel" || true)
  [ "$vistos" -gt 0 ] || falla "$rel" "$rel sin ningún FROM"
done

for rel in infra/compose.yml infra/compose.dev.yml .github/workflows/ci.yml; do
  existe "$rel" || continue
  while IFS=: read -r n resto; do
    ref="$(printf '%s' "$resto" | sed -E 's/^[[:space:]]*image:[[:space:]]*//; s/[[:space:]]+#.*$//; s/^["'\'']//; s/["'\'']$//')"
    case "$ref" in
      apex-*:local) continue ;;
    esac
    revisa "$rel" "$n" "$ref"
  done < <(grep -nE '^[[:space:]]*image:' "$ROOT/$rel" || true)
done

rel=scripts/ci/test_nginx_conf.sh
if existe "$rel"; then
  menciones=0
  while IFS=: read -r n resto; do
    sin_sangria="${resto#"${resto%%[![:space:]]*}"}"
    case "$sin_sangria" in
      '#'*) continue ;;
    esac
    while read -r ref; do
      [ -n "$ref" ] || continue
      menciones=$((menciones + 1))
      revisa "$rel" "$n" "$ref"
    done < <(printf '%s\n' "$resto" | grep -oE 'nginx:[A-Za-z0-9._-]+(@sha256:[0-9a-f]+)?' || true)
  done < <(grep -nE 'nginx:[A-Za-z0-9._-]+' "$ROOT/$rel" || true)
  [ "$menciones" -gt 0 ] || falla "$rel" "$rel sin imagen de Nginx"
fi

# digest_postgres <archivo relativo>: el digest de la primera `image: postgres:16@sha256:...`.
digest_postgres() {
  grep -oE 'image:[[:space:]]*postgres:16@sha256:[0-9a-f]{64}' "$ROOT/$1" | head -n 1 | sed 's/.*@//' || true
}

rel=.github/workflows/ci.yml
if [ -f "$ROOT/$rel" ] && [ -f "$ROOT/infra/compose.yml" ]; then
  del_ci="$(digest_postgres "$rel")"
  del_compose="$(digest_postgres infra/compose.yml)"
  if [ -n "$del_ci" ] && [ "$del_ci" = "$del_compose" ]; then
    ok "$rel postgres:16 con el mismo digest de infra/compose.yml"
  else
    falla "$rel" "$rel postgres:16 con un digest distinto del de infra/compose.yml"
  fi
fi

if [ "$fallas" -gt 0 ]; then
  echo "test_images_pinned: $fallas fallas en$archivos_con_falla"
else
  echo "test_images_pinned: 0 fallas"
fi
[ "$fallas" -eq 0 ]
