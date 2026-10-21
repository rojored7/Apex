#!/usr/bin/env bash
# slice-gate.sh <modulo> [archivos de prueba...]
#
# Gate de un slice (US-008, ajuste A-01). Corre lint, formato, tipos y pruebas del
# módulo y, si todo pasa, escribe el sello .git/apex/slice-gate.ok con una huella del
# árbol de trabajo. checkpoint-commit.sh solo confirma con un sello vigente.
#
# Con lista de archivos corre solo esos archivos más tests/architecture; sin lista,
# la carpeta de pruebas del módulo más tests/architecture. Nunca hace push.
set -euo pipefail

usage() {
  cat <<'EOF'
Uso: slice-gate.sh <modulo> [archivos de prueba...]

Módulos del api (rutas relativas a api/):
  core/<x>      src/app/core/<x>.py o src/app/core/<x>/   pruebas en tests/core
  crypto        src/app/core/crypto/                      pruebas en tests/crypto
  main          src/app/main.py                           pruebas en tests/core
  worker        src/app/worker/                           pruebas en tests/worker
  cli           src/app/cli.py                            pruebas en tests/cli
  architecture  sin código                                pruebas en tests/architecture
  <modulo>      src/app/modules/<modulo>/                 pruebas en tests/<modulo>
Módulos del front (rutas relativas a web/):
  web/<feature> src/features/<feature>    web/shared src/shared    web/core src/core
  web/layouts   src/layouts               web/app    src/App.tsx, src/routes*, src/config,
                                                     src/styles, index.html, tests/unit, tests/lint
tests/architecture corre siempre en el api. Los archivos de la lista deben existir bajo
api/tests/ o bajo web/.

Ejemplos:
  slice-gate.sh core/config tests/core/test_config.py
  slice-gate.sh members
  slice-gate.sh web/shared src/shared/ui/Button.test.tsx
EOF
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  "") usage >&2; exit 2 ;;
esac

MODULO="$1"
shift
ARCHIVOS=("$@")

if ! [[ "$MODULO" =~ ^(web/)?[a-z][a-z0-9_-]*(/[a-z][a-z0-9_-]*)*$ ]]; then
  echo "slice-gate: nombre de módulo inválido: '$MODULO'" >&2
  echo "slice-gate: debe cumplir ^(web/)?[a-z][a-z0-9_-]*(/[a-z][a-z0-9_-]*)*$" >&2
  exit 1
fi

ROOT="$(git rev-parse --show-toplevel)"
GIT_DIR="$(git rev-parse --absolute-git-dir)"
SELLO="$GIT_DIR/apex/slice-gate.ok"
API="$ROOT/api"
WEB="$ROOT/web"

fallo() { echo "slice-gate: $*" >&2; exit 1; }

huella() {
  (
    cd "$ROOT"
    {
      git diff HEAD --
      git ls-files --others --exclude-standard | sort | while IFS= read -r f; do
        printf '%s %s\n' "$f" "$(git hash-object -- "$f")"
      done
    } | git hash-object --stdin
  )
}

escribir_sello() {
  mkdir -p "$(dirname "$SELLO")"
  {
    echo "modulo=$MODULO"
    echo "huella=$(huella)"
    echo "fecha=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  } > "$SELLO"
  echo "slice-gate: verde. Sello escrito en .git/apex/slice-gate.ok para '$MODULO'."
}

rm -f "$SELLO"

# ---------------------------------------------------------------- api
gate_api() {
  local codigo="" pruebas_dir=""
  case "$MODULO" in
    core/*)
      local x="${MODULO#core/}"
      [[ "$x" == */* ]] && fallo "core/<x> admite un solo nivel: '$MODULO'"
      if [ -f "$API/src/app/core/$x.py" ]; then codigo="src/app/core/$x.py"
      elif [ -d "$API/src/app/core/$x" ]; then codigo="src/app/core/$x"
      else fallo "módulo inexistente: ni src/app/core/$x.py ni src/app/core/$x/"; fi
      pruebas_dir="tests/core" ;;
    crypto)       codigo="src/app/core/crypto"; pruebas_dir="tests/crypto" ;;
    main)         codigo="src/app/main.py";     pruebas_dir="tests/core" ;;
    worker)       codigo="src/app/worker";      pruebas_dir="tests/worker" ;;
    cli)          codigo="src/app/cli.py";      pruebas_dir="tests/cli" ;;
    architecture) codigo="";                    pruebas_dir="tests/architecture" ;;
    */*)          fallo "módulo del api con varios niveles no mapeado: '$MODULO'" ;;
    *)            codigo="src/app/modules/$MODULO"; pruebas_dir="tests/$MODULO" ;;
  esac
  [ -n "$codigo" ] && [ ! -e "$API/$codigo" ] && fallo "módulo inexistente: api/$codigo"

  local pruebas=()
  if [ "${#ARCHIVOS[@]}" -eq 0 ]; then
    [ -d "$API/$pruebas_dir" ] || fallo "no existe api/$pruebas_dir; pasa una lista de archivos"
    pruebas=("$pruebas_dir")
  else
    local f rel
    for f in "${ARCHIVOS[@]}"; do
      rel="${f#api/}"
      [ -f "$API/$rel" ] || fallo "archivo de prueba inexistente: api/$rel"
      [[ "$rel" == tests/* ]] || fallo "los archivos de prueba del api deben vivir bajo api/tests/: $rel"
      pruebas+=("$rel")
    done
  fi
  local incluye_arch=0 p
  for p in "${pruebas[@]}"; do [ "$p" = "tests/architecture" ] && incluye_arch=1; done
  [ "$incluye_arch" -eq 1 ] || pruebas+=("tests/architecture")

  cd "$API"
  if [ -n "$codigo" ]; then
    echo "slice-gate: ruff check $codigo";            uv run ruff check "$codigo"
    echo "slice-gate: ruff format --check $codigo";   uv run ruff format --check "$codigo"
    echo "slice-gate: mypy $codigo";                  uv run mypy "$codigo"
  fi
  echo "slice-gate: pytest ${pruebas[*]}";            uv run pytest "${pruebas[@]}" -q
}

# ---------------------------------------------------------------- front
gate_web() {
  local feature="${MODULO#web/}"
  [[ "$feature" == */* ]] && fallo "web/<feature> admite un solo nivel: '$MODULO'"
  [ -f "$WEB/package.json" ] || fallo "no existe web/package.json"
  local candidatos=()
  case "$feature" in
    shared)  candidatos=(src/shared) ;;
    core)    candidatos=(src/core) ;;
    layouts) candidatos=(src/layouts) ;;
    app)     candidatos=(src/App.tsx src/routes.tsx src/routes src/config src/styles index.html tests/unit tests/lint) ;;
    *)       candidatos=("src/features/$feature") ;;
  esac
  local dirs=() c
  for c in "${candidatos[@]}"; do [ -e "$WEB/$c" ] && dirs+=("$c"); done
  [ "${#dirs[@]}" -gt 0 ] || fallo "módulo del front inexistente: '$MODULO' (ninguna de: ${candidatos[*]})"

  # Archivos que toca el slice: diff contra la base del slice, cambios sin confirmar,
  # archivos nuevos y la lista recibida.
  local base
  base="${SLICE_BASE:-$(git merge-base HEAD main 2>/dev/null || git rev-parse HEAD)}"
  local tocados=() f rel
  while IFS= read -r f; do
    [ -n "$f" ] || continue
    rel="${f#web/}"
    [ -f "$WEB/$rel" ] && tocados+=("$rel")
  done < <(
    (cd "$ROOT" && git diff --name-only "$base" -- web; git ls-files --others --exclude-standard -- web) | sort -u
  )
  local lista=()
  for f in "${ARCHIVOS[@]}"; do
    rel="${f#web/}"
    [ -f "$WEB/$rel" ] || fallo "archivo inexistente: web/$rel"
    lista+=("$rel"); tocados+=("$rel")
  done

  local lint=() ts=() pruebas=() seen=" "
  for f in "${tocados[@]}"; do
    case " $seen " in *" $f "*) continue ;; esac
    seen="$seen$f "
    case "$f" in
      *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs) lint+=("$f") ;;
    esac
    case "$f" in *.ts|*.tsx) ts+=("$f") ;; esac
  done
  for f in "${lista[@]}"; do
    case "$f" in *.test.*|*.spec.*|tests/*) pruebas+=("$f") ;; esac
  done
  [ "${#pruebas[@]}" -gt 0 ] || pruebas=("${dirs[@]}")

  cd "$WEB"
  local slice_tsconfig="tsconfig.slice.json"
  trap 'rm -f "$WEB/tsconfig.slice.json"' EXIT
  {
    echo '{'
    echo '  "extends": "./tsconfig.json",'
    echo '  "include": ['
    local primero=1 inc
    for inc in "${dirs[@]/%//**/*}" "${ts[@]}" src/vite-env.d.ts; do
      [ "$inc" = "src/vite-env.d.ts" ] && [ ! -f "$WEB/src/vite-env.d.ts" ] && continue
      [ "$primero" -eq 1 ] || echo ','
      primero=0
      printf '    "%s"' "${inc//\/\/\*\*/\/**}"
    done
    echo
    echo '  ]'
    echo '}'
  } > "$slice_tsconfig"

  if [ "${#lint[@]}" -gt 0 ]; then
    echo "slice-gate: eslint ${lint[*]}";                 npx eslint "${lint[@]}"
  else
    echo "slice-gate: eslint sin archivos que revisar"
  fi
  echo "slice-gate: tsc --noEmit -p $slice_tsconfig";    npx tsc --noEmit -p "$slice_tsconfig"
  echo "slice-gate: vitest run ${pruebas[*]}";           npx vitest run "${pruebas[@]}"
  rm -f "$slice_tsconfig"
}

case "$MODULO" in
  web/*) gate_web ;;
  *)     gate_api ;;
esac

escribir_sello
