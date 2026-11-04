#!/usr/bin/env bash
# test_check_release_version.sh: casos de scripts/ci/check-release-version.sh (S4B-B4, US-119,
# paso 78; S4B-D43 precisada). Bash puro.
#
# Contrato (lo implementa el Verde, paso 80):
#   check-release-version.sh --check vX.Y.Z
#   - compara la etiqueta (sin la v) con la `version` de api/pyproject.toml, la de web/package.json
#     y el encabezado de la PRIMERA seccion de CHANGELOG.md (`## [X.Y.Z]`);
#   - salidas: 0 coincide en los tres; 1 alguno no coincide (el mensaje nombra el archivo);
#     2 uso (sin --check, sin valor, etiqueta que no es vX.Y.Z);
#   - la raiz es el padre de scripts/ (se calcula desde la ruta del script);
#   - NO lee ni exige ningun SHA (S4B-D43): un CHANGELOG sin SHA o con otro SHA sigue valiendo.
# Fallo esperado en el Rojo: el stub sale con 99.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
SRC="$ROOT/scripts/ci/check-release-version.sh"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/apex-relver-tests.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT
FAILS=0
PASSES=0
_ok() { PASSES=$((PASSES + 1)); echo "  ok   $1"; }
_fail() { FAILS=$((FAILS + 1)); echo "  FALLA $1"; }
assert_eq() { if [ "$2" = "$3" ]; then _ok "$1"; else _fail "$1 (esperado '$2', obtenido '$3')"; fi; }
assert_contains() { case "$2" in *"$3"*) _ok "$1" ;; *) _fail "$1 (no contiene '$3')" ;; esac; }

echo "test_check_release_version"
if [ ! -f "$SRC" ]; then
  _fail "existe scripts/ci/check-release-version.sh"
  echo "test_check_release_version: $FAILS fallas"
  exit 1
fi

N=0
R=""
# mk <pyproject> <package.json> <primera seccion del CHANGELOG> [cuerpo]: repo de prueba.
mk() {
  N=$((N + 1))
  R="$TMP_ROOT/r$N"
  mkdir -p "$R/scripts/ci" "$R/api" "$R/web"
  cp "$SRC" "$R/scripts/ci/check-release-version.sh"
  printf '[project]\nname = "apex-api"\nversion = "%s"\n' "$1" > "$R/api/pyproject.toml"
  printf '{\n  "name": "apex-web",\n  "version": "%s",\n  "private": true\n}\n' "$2" > "$R/web/package.json"
  printf '# Changelog\n\n## [%s]\n\n%s\n\n## [0.0.1]\n\nantes.\n' "$3" "${4:-Primera version.}" > "$R/CHANGELOG.md"
}
RC=0; OUT=""
chk() { RC=0; OUT="$(cd "$R" && bash scripts/ci/check-release-version.sh "$@" 2>&1)" || RC=$?; }

mk 0.1.0 0.1.0 0.1.0; chk --check v0.1.0
assert_eq "v0.1.0 coincide en los tres: 0" 0 "$RC"
mk 0.1.0 0.1.0 0.1.0; chk --check v0.2.0
assert_eq "v0.2.0 contra 0.1.0: 1" 1 "$RC"
mk 0.2.0 0.1.0 0.1.0; chk --check v0.1.0
assert_eq "pyproject.toml distinto: 1" 1 "$RC"
assert_contains "pyproject.toml distinto: nombra el archivo" "$OUT" "pyproject.toml"
mk 0.1.0 0.2.0 0.1.0; chk --check v0.1.0
assert_eq "package.json distinto: 1" 1 "$RC"
assert_contains "package.json distinto: nombra el archivo" "$OUT" "package.json"
mk 0.1.0 0.1.0 0.2.0; chk --check v0.1.0
assert_eq "primera seccion del CHANGELOG distinta: 1" 1 "$RC"
assert_contains "CHANGELOG distinto: nombra el archivo" "$OUT" "CHANGELOG.md"
# La version solo esta en una seccion vieja (no la primera): no vale.
mk 0.1.0 0.1.0 0.3.0; printf '\n## [0.1.0]\n\nvieja.\n' >> "$R/CHANGELOG.md"; chk --check v0.1.0
assert_eq "0.1.0 solo en una seccion posterior del CHANGELOG: 1" 1 "$RC"
# S4B-D43: sin SHA en el CHANGELOG, o con cualquier SHA, sigue valiendo.
mk 0.1.0 0.1.0 0.1.0 "Primera version."; chk --check v0.1.0
assert_eq "CHANGELOG sin SHA: 0" 0 "$RC"
mk 0.1.0 0.1.0 0.1.0 "SHA de cierre: 0123456789abcdef0123456789abcdef01234567"; chk --check v0.1.0
assert_eq "CHANGELOG con un SHA que no es el de HEAD: 0" 0 "$RC"
# Uso.
mk 0.1.0 0.1.0 0.1.0; chk
assert_eq "sin argumentos: 2" 2 "$RC"
mk 0.1.0 0.1.0 0.1.0; chk --check
assert_eq "--check sin valor: 2" 2 "$RC"
mk 0.1.0 0.1.0 0.1.0; chk --check 0.1.0
assert_eq "etiqueta sin v: 2" 2 "$RC"
mk 0.1.0 0.1.0 0.1.0; chk --check main
assert_eq "etiqueta que no es vX.Y.Z: 2" 2 "$RC"
# Falta un archivo.
mk 0.1.0 0.1.0 0.1.0; rm "$R/CHANGELOG.md"; chk --check v0.1.0
assert_eq "sin CHANGELOG.md: distinto de 0" 1 "$([ "$RC" -ne 0 ] && echo 1 || echo 0)"
# El script no invoca git ni red (no lee SHA): se comprueba en su texto.
sin_git="$(grep -nE '(^|[^[:alnum:]_])(git|curl|wget)([^[:alnum:]_]|$)' "$SRC" | grep -vE '^[0-9]+:[[:space:]]*#' || true)"
assert_eq "el script no llama a git, curl ni wget (no lee SHA)" "" "$sin_git"

# Contra el repositorio real: la etiqueta del release debe coincidir (lo exige la CI, paso 82).
RC=0; (cd "$ROOT" && bash scripts/ci/check-release-version.sh --check v0.1.0 > /dev/null 2>&1) || RC=$?
assert_eq "repositorio real: --check v0.1.0 sale con 0" 0 "$RC"

echo "  resumen: $PASSES ok, $FAILS fallas"
echo "test_check_release_version: $FAILS fallas"
[ "$FAILS" -eq 0 ]
