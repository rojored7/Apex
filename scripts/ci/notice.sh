#!/usr/bin/env bash
# notice.sh
#
# Regenera NOTICE en la raíz (US-004, T6): dependencias directas del api con su
# licencia (desde el entorno de runtime), dependencias directas de producción del
# front si existe web/package.json, y un bloque fijo para las fuentes OFL-1.1 y las
# herramientas MPL-2.0 de desarrollo. La CI falla si NOTICE quedó desactualizado:
# `bash scripts/ci/notice.sh && git diff --exit-code NOTICE`.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
API="$ROOT/api"
SALIDA="$ROOT/NOTICE"

(cd "$API" && UV_PROJECT_ENVIRONMENT=.venv-runtime uv sync --frozen --no-dev --quiet)
if [ -x "$API/.venv-runtime/bin/python" ]; then PY="$API/.venv-runtime/bin/python"; else PY="$API/.venv-runtime/Scripts/python.exe"; fi

# Nombres de las dependencias directas de [project.dependencies], sin extras ni versiones.
mapfile -t DIRECTAS < <(cd "$API" && uv run --quiet python - <<'EOF'
import re
import tomllib

with open("pyproject.toml", "rb") as f:
    deps = tomllib.load(f)["project"]["dependencies"]
for dep in deps:
    print(re.split(r"[\[<>=!~; ]", dep, maxsplit=1)[0].lower())
EOF
)

{
  echo "APEX · avisos de licencias de terceros"
  echo
  echo "Generado con scripts/ci/notice.sh. No editar a mano: la CI compara este archivo"
  echo "con el resultado del script. Las reglas de licencias están en CLAUDE.md."
  echo
  echo "== api (Python, dependencias directas de runtime) =="
  echo
  (cd "$API" && uv run --quiet pip-licenses --python "$PY" --from=mixed --format=plain-vertical --order=name --packages "${DIRECTAS[@]}")
  echo
  echo "== web (dependencias directas de producción) =="
  echo
  if [ -f "$ROOT/web/package.json" ] && [ -d "$ROOT/web/node_modules" ]; then
    (cd "$ROOT/web" && npx --no-install license-checker --production --direct --excludePrivatePackages --csv 2>/dev/null || echo "(license-checker no disponible)")
  else
    echo "(sin web/package.json o sin node_modules; se completa con US-009)"
  fi
  echo
  echo "== recursos que no son paquetes =="
  echo
  echo "Michroma (fuente) · SIL Open Font License 1.1 · web/public/fonts/"
  echo "Titillium Web (fuente) · SIL Open Font License 1.1 · web/public/fonts/"
  echo "Lucide (iconos) · ISC · paquete lucide-react en web/"
  echo
  echo "== herramientas de desarrollo con MPL-2.0, sin modificar (no se distribuyen) =="
  echo
  echo "axe-core · MPL-2.0 · pruebas de accesibilidad del front (US-010)"
  echo "certifi · MPL-2.0 · certificados raíz, transitiva de httpx (runtime del api; ver scripts/ci/licenses-exceptions.txt)"
} | tr -d '\r' > "$SALIDA"

echo "notice.sh: NOTICE regenerado ($(wc -l < "$SALIDA") líneas)"
