#!/usr/bin/env bash
# run-gates.sh [numero-de-wave]
#
# Suite completa al cerrar una wave o un sprint: api con cobertura global de `app`
# de al menos 80 %, los scripts de infraestructura (scripts/ci/test_*.sh que existan) y,
# si existe web/package.json, el front con lint, tsc, pruebas con cobertura y build.
# Imprime qué gate falló. El argumento de wave es informativo.
#
# Cobertura (M-6): hasta el Sprint 3, `[tool.coverage.run] omit` de api/pyproject.toml
# excluye src/app/cli.py y src/app/worker/*; desde el Sprint 4A se quita esa exclusión.
#
# Política `perf` (S2-D27, revisión de Fase 4 del Sprint 2): las pruebas marcadas `perf`
# miden con reloj y no son gate; aquí corren con `-m "not perf"`. Se corren a mano con
# `cd api && uv run pytest -m perf -q` y en CI en un paso informativo.
set -euo pipefail

usage() {
  cat <<'EOF'
Uso: run-gates.sh [wave]

api (desde api/):  uv run ruff check . ; uv run ruff format --check . ; uv run mypy src ;
                   uv run pytest --cov=app --cov-fail-under=80 -q -m "not perf"
scripts (raíz, los que existan; necesitan Docker):
                   scripts/ci/test_check_key_files.sh ; scripts/ci/test_images_pinned.sh ;
                   scripts/ci/test_nginx_conf.sh ; scripts/ci/test_compose_config.sh
front (si existe web/package.json, desde web/):
                   npm run lint ; npx tsc --noEmit ; npm test -- --run --coverage ; npm run build
EOF
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
esac
WAVE="${1:-}"

ROOT="$(git rev-parse --show-toplevel)"

gate() {
  local nombre="$1"; shift
  echo "run-gates: [$nombre] $*"
  if ! "$@"; then
    echo "run-gates: FALLÓ el gate '$nombre'${WAVE:+ (wave $WAVE)}" >&2
    exit 1
  fi
}

cd "$ROOT/api"
gate "api lint"       uv run ruff check .
gate "api formato"    uv run ruff format --check .
gate "api tipos"      uv run mypy src
gate "api pruebas"    uv run pytest --cov=app --cov-fail-under=80 -q -m "not perf"

# Scripts de infraestructura (M1 de la revisión de Fase 4): los mismos que la CI corre en
# los jobs `secrets-scan`, `scripts` e `images`. Un script ausente se omite (repos de prueba).
# test_images_pinned (S3-D62) es grep puro: imágenes base por digest con fecha.
cd "$ROOT"
for prueba in test_check_key_files test_images_pinned test_nginx_conf test_compose_config; do
  if [ -f "$ROOT/scripts/ci/$prueba.sh" ]; then
    gate "scripts $prueba" bash "$ROOT/scripts/ci/$prueba.sh"
  else
    echo "run-gates: sin scripts/ci/$prueba.sh; se omite"
  fi
done

if [ -f "$ROOT/web/package.json" ]; then
  cd "$ROOT/web"
  gate "web lint"     npm run lint
  gate "web tipos"    npx tsc --noEmit
  gate "web pruebas"  npm test -- --run --coverage
  gate "web build"    npm run build
else
  echo "run-gates: sin web/package.json; se omite el front"
fi

echo "run-gates: todos los gates en verde${WAVE:+ (wave $WAVE)}"
