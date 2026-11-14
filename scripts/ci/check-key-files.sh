#!/usr/bin/env bash
# check-key-files.sh [archivos...]
#
# Falla si algún archivo versionado (o pasado por argumento, en pre-commit) es material de
# llave por su nombre: kek.bin, sign-ed25519.key, jwt_ed25519.pem, jwt_ed25519.pub, *.kek,
# o un .env que no sea .env.example, .env.seed.example ni .env.ops.example (US-039; M-5 de la revisión del
# Sprint 1; .env.seed de S2-W0-1; S4B-W0-1: .env.ops, *.age, rclone.conf, age-identity*,
# backup-verify-identity* y backup-sign*). gitleaks no detecta bytes crudos sin cabecera PEM, así
# que el nombre es la única señal. Casos en scripts/ci/test_check_key_files.sh.
set -euo pipefail

# --- Modo `--layout <dir> [--provider local|openbao] [--only custody|api|all]` (S6-D58, S7-D4) ---
# Comprueba el volumen `keys` (nunca imprime contenido): custody/kek.bin, sign/sign-ed25519.key y
# jwt/jwt_ed25519.{pem,pub}, modo 600 y dueño 10001. Plano, mixto o la llave de firma aún en
# custody/ (layout de v0.3): error con la orden de migración. `--only custody` es la vista del
# worker (custody/ y sign/; si ve jwt/ es un error); `--only api` la del api (custody/ y jwt/; si
# ve sign/ o custody/sign-ed25519.key es un error, S7-D4).
check_layout() {
  local dir="" provider="local" only="all"
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --layout) dir="${2:-}"; shift 2 ;;
      --provider) provider="${2:-}"; shift 2 ;;
      --only) only="${2:-}"; shift 2 ;;
      *) echo "check-key-files: argumento desconocido con --layout: $1" >&2; exit 2 ;;
    esac
  done
  case "$only" in custody | api | all) ;; *) echo "check-key-files: --only admite custody|api|all" >&2; exit 2 ;; esac
  case "$provider" in local | openbao) ;; *) echo "check-key-files: --provider admite local|openbao" >&2; exit 2 ;; esac
  if [ ! -d "$dir" ]; then echo "check-key-files: la carpeta $dir no existe" >&2; exit 1; fi
  local errores=() f
  for f in kek.bin sign-ed25519.key jwt_ed25519.pem jwt_ed25519.pub; do
    if [ -e "$dir/$f" ]; then
      errores+=("$f sigue en la raíz del volumen (layout plano o mixto): corra init-keys --migrate-layout")
    fi
  done
  if [ -e "$dir/custody/sign-ed25519.key" ]; then
    errores+=("sign-ed25519.key sigue en custody/ (layout de v0.3): corra init-keys --migrate-layout")
  fi
  local requeridos=()
  if [ "$provider" = "local" ]; then requeridos+=(custody/kek.bin); fi
  if [ "$provider" = "local" ] && [ "$only" != "api" ]; then requeridos+=(sign/sign-ed25519.key); fi
  if [ "$only" != "custody" ]; then requeridos+=(jwt/jwt_ed25519.pem jwt/jwt_ed25519.pub); fi
  if [ "$only" = "custody" ] && [ -e "$dir/jwt" ]; then
    errores+=("jwt/ es visible en la vista del worker: nada del JWT debe montarse ahí")
  fi
  if [ "$only" = "api" ] && [ -e "$dir/sign" ]; then
    errores+=("sign/ es visible en la vista del api: la llave de firma no debe montarse ahí")
  fi
  for f in "${requeridos[@]}"; do
    if [ ! -f "$dir/$f" ]; then errores+=("falta ${f##*/} ($f)"); continue; fi
    local modo uid
    modo="$(stat -c %a "$dir/$f")"; uid="$(stat -c %u "$dir/$f")"
    [ "$modo" = "600" ] || errores+=("$f con modo $modo (se esperaba 600)")
    [ "$uid" = "10001" ] || errores+=("$f con dueño $uid (se esperaba 10001)")
  done
  if [ "${#errores[@]}" -gt 0 ]; then
    echo "check-key-files: layout del volumen keys incorrecto:" >&2
    printf '  %s\n' "${errores[@]}" >&2
    exit 1
  fi
  echo "check-key-files: layout del volumen keys correcto ($only, proveedor $provider)"
  exit 0
}
if [ "${1:-}" = "--layout" ]; then check_layout "$@"; fi

if [ "$#" -gt 0 ]; then
  archivos=("$@")
else
  mapfile -t archivos < <(git ls-files)
fi
malos=()
for f in "${archivos[@]}"; do
  base="$(basename "$f")"
  case "$base" in
    kek.bin|sign-ed25519.key|jwt_ed25519.pem|jwt_ed25519.pub|*.kek) malos+=("$f") ;;
    # S4B-D10, S4B-D78: respaldos cifrados, identidades age, rclone.conf y llaves de firma.
    *.age|rclone.conf|age-identity*|backup-verify-identity*|backup-sign*) malos+=("$f") ;;
    .env.example|.env.seed.example|.env.ops.example) ;;
    .env|.env.*) malos+=("$f") ;;
  esac
done
if [ "${#malos[@]}" -gt 0 ]; then
  echo "check-key-files: material de llave o .env en el repositorio:" >&2
  printf '  %s\n' "${malos[@]}" >&2
  exit 1
fi
echo "check-key-files: sin archivos de llave ni .env versionados"
