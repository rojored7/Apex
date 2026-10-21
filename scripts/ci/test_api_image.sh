#!/usr/bin/env bash
# test_api_image.sh [imagen]
#
# Prueba de la imagen del api (US-005, T4; CRITICA-2 O-2). Sin argumento construye
# apex-api:ci desde api/Dockerfile. Verifica: usuario no root (UID 10001), tzdata,
# alembic.ini y migrations/ dentro de la imagen, `alembic heads` con código 0, sin
# .env ni llaves bajo /app, y sin pytest, ruff ni mypy instalados.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
IMG="${1:-}"
if [ -z "$IMG" ]; then
  IMG="apex-api:ci"
  echo "test_api_image: construyendo $IMG"
  # DOCKER_BUILD_NETWORK=host cuando el bridge no tiene salida (Docker Desktop en WSL2).
  docker build -q ${DOCKER_BUILD_NETWORK:+--network "$DOCKER_BUILD_NETWORK"} -t "$IMG" -f "$ROOT/api/Dockerfile" "$ROOT/api" > /dev/null
fi
fallas=0
ok() { echo "  ok   $1"; }
falla() { echo "  FALLA $1"; fallas=$((fallas + 1)); }

uid="$(docker run --rm "$IMG" id -u)"
[ "$uid" = "10001" ] && ok "usuario apex con UID 10001" || falla "UID $uid (se esperaba 10001)"

docker run --rm "$IMG" sh -c 'test -f /usr/share/zoneinfo/America/Bogota' && ok "tzdata presente" || falla "falta tzdata"

docker run --rm "$IMG" sh -c 'test -f /app/alembic.ini && test -d /app/migrations && test -f /app/migrations/env.py' \
  && ok "alembic.ini y migrations/ en la imagen" || falla "faltan alembic.ini o migrations/"

if docker run --rm "$IMG" alembic heads > /dev/null 2>&1; then ok "alembic heads termina con 0"; else falla "alembic heads falla"; fi

# Fuera de site-packages (certifi trae cacert.pem y cryptography parsea llaves):
# ningún .env, .key, .pem ni .kek, y ningún archivo con una llave privada en claro.
hallazgos="$(docker run --rm "$IMG" sh -c 'find /app -xdev -path "/app/.venv/lib" -prune -o \( -name ".env" -o -name ".env.*" -o -name "*.key" -o -name "*.pem" -o -name "*.kek" \) -print 2>/dev/null; grep -rlsE --exclude-dir=lib -e "-----BEGIN (RSA |EC |OPENSSH |ENCRYPTED |)PRIVATE KEY-----" /app 2>/dev/null' || true)"
[ -z "$hallazgos" ] && ok "sin .env ni llaves bajo /app (fuera de site-packages)" || falla "archivos sensibles en la imagen: $hallazgos"

if docker run --rm "$IMG" python -c "import importlib.util, sys; sys.exit(1 if any(importlib.util.find_spec(m) for m in ['pytest', 'ruff', 'mypy']) else 0)"; then
  ok "sin herramientas de desarrollo"
else
  falla "pytest, ruff o mypy están en la imagen"
fi

docker run --rm "$IMG" python -c "import app.main; assert callable(app.main.create_app)" && ok "app.main importa" || falla "app.main no importa"

echo "test_api_image: $fallas fallas"
[ "$fallas" -eq 0 ]
