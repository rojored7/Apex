#!/usr/bin/env bash
# check-release-version.sh --check vX.Y.Z (S4B-B4, US-119; S4B-D43 precisada).
#
# Compara la etiqueta del release (sin la v) con tres fuentes del repositorio:
#   - api/pyproject.toml: `version` de la sección [project];
#   - web/package.json: la clave "version";
#   - CHANGELOG.md: el encabezado de la PRIMERA sección (`## [X.Y.Z]`).
# No lee ni exige ningún SHA: un commit posterior en main no debe tumbar la CI (S4B-D43).
# Salidas: 0 coincide en los tres; 1 alguno no coincide o falta un archivo (el mensaje nombra el
# archivo); 2 uso (sin --check, sin valor o etiqueta que no es vX.Y.Z).
# La raíz es el padre de scripts/, calculada desde la ruta de este archivo.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

uso() { echo "uso: check-release-version.sh --check vX.Y.Z" >&2; exit 2; }

[ "${1:-}" = "--check" ] || uso
TAG="${2:-}"
[ "$#" -eq 2 ] || uso
[[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || uso
VERSION="${TAG#v}"

fallas=0
comparar() { # <archivo> <version encontrada>
  if [ "$2" = "$VERSION" ]; then
    echo "check-release-version: $1 ok ($2)"
  else
    echo "check-release-version: $1 dice '${2:-<sin versión>}' y la etiqueta pide '$VERSION'" >&2
    fallas=$((fallas + 1))
  fi
}

PYPROJECT="$ROOT/api/pyproject.toml"
PACKAGE="$ROOT/web/package.json"
CHANGELOG="$ROOT/CHANGELOG.md"
for f in "$PYPROJECT" "$PACKAGE" "$CHANGELOG"; do
  if [ ! -f "$f" ]; then
    echo "check-release-version: falta ${f#"$ROOT"/}" >&2
    exit 1
  fi
done

py="$(awk '
  /^\[/ { en = ($0 == "[project]") ; next }
  en && /^version[[:space:]]*=/ { gsub(/^[^"]*"|".*$/, ""); print; exit }
' "$PYPROJECT" | tr -d '\r')"
js="$(sed -n 's/^[[:space:]]*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$PACKAGE" | head -1 | tr -d '\r')"
cl="$(sed -n 's/^## \[\([^]]*\)\].*/\1/p' "$CHANGELOG" | head -1 | tr -d '\r')"

comparar "api/pyproject.toml" "$py"
comparar "web/package.json" "$js"
comparar "CHANGELOG.md" "$cl"

[ "$fallas" -eq 0 ]
