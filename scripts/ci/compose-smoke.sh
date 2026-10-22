#!/usr/bin/env bash
# compose-smoke.sh
#
# Smoke del stack (US-005, T14; US-006, T10). Levanta db, db_test y api con build,
# espera db y db_test en healthy, exige api en ejecución y, salvo que
# SMOKE_ALLOW_UNHEALTHY=1 (solo mientras no exista /health, US-020), api en healthy.
# Si existe web/Dockerfile levanta web y corre scripts/ci/web-smoke.sh. Al final
# baja el stack con sus volúmenes, salvo SMOKE_KEEP=1.
# S2-W0-1: con api healthy corre `tools seed` leyendo ADMIN_* de .env.seed (si no existe,
# crea uno efímero con una contraseña aleatoria y lo borra al salir; uno existente no se
# toca) y comprueba que web tiene la IP fija de TRUSTED_PROXIES.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
[ -f .env ] || cp .env.example .env
DC=(docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml)

SEED_EFIMERO=0
bajar() {
  if [ "$SEED_EFIMERO" = "1" ]; then rm -f "$ROOT/.env.seed"; fi
  if [ "${SMOKE_KEEP:-0}" = "1" ]; then
    echo "compose-smoke: SMOKE_KEEP=1, el stack queda arriba"
  else
    if [ "${CI:-}" != "" ]; then
      "${DC[@]}" down -v --remove-orphans > /dev/null 2>&1 || true
    else
      # Fuera de CI nunca se borran los volúmenes del proyecto apex (pgdata, uploads, keys).
      "${DC[@]}" down --remove-orphans > /dev/null 2>&1 || true
    fi
  fi
}
trap bajar EXIT

estado() { "${DC[@]}" ps --format json "$1" 2>/dev/null | tr -d '\r' | head -1; }
campo() { estado "$1" | sed -n "s/.*\"$2\":\"\([^\"]*\)\".*/\1/p"; }

esperar_healthy() {
  local svc="$1" limite="$2" t=0
  while [ "$t" -lt "$limite" ]; do
    [ "$(campo "$svc" Health)" = "healthy" ] && { echo "compose-smoke: $svc healthy a los ${t}s"; return 0; }
    sleep 3; t=$((t + 3))
  done
  echo "compose-smoke: $svc no llegó a healthy en ${limite}s (estado: $(campo "$svc" State)/$(campo "$svc" Health))" >&2
  "${DC[@]}" logs --tail 40 "$svc" >&2 || true
  return 1
}

inicio=$(date +%s)
"${DC[@]}" build api
"${DC[@]}" up -d --build db db_test
esperar_healthy db 120
esperar_healthy db_test 120
# US-023: sin KEK, llave de firma y par JWT en el volumen keys, el api no arranca.
# init-keys es idempotente: en un volumen ya poblado no toca nada.
"${DC[@]}" --profile tools run --rm tools init-keys
"${DC[@]}" up -d api
[ "$(campo api State)" = "running" ] || { echo "compose-smoke: api no está en ejecución" >&2; "${DC[@]}" logs --tail 40 api >&2; exit 1; }
echo "compose-smoke: api en ejecución"

if [ "${SMOKE_ALLOW_UNHEALTHY:-0}" = "1" ]; then
  echo "compose-smoke: SMOKE_ALLOW_UNHEALTHY=1, no se exige api healthy (hasta US-020)"
else
  esperar_healthy api 90
fi

# M-8: ADMIN_* solo llegan a tools por .env.seed. Seed idempotente: con un admin activo
# responde "omitido".
if [ ! -f .env.seed ]; then
  SEED_EFIMERO=1
  ( umask 077
    printf 'ADMIN_EMAIL=admin@smoke.apex.local\nADMIN_INITIAL_PASSWORD=%s\n' "$(head -c 24 /dev/urandom | base64 | tr -d '/+=\n')" > .env.seed )
  echo "compose-smoke: .env.seed efímero creado (se borra al salir)"
fi
"${DC[@]}" --profile tools run --rm tools seed
if "${DC[@]}" exec -T api sh -c 'env | grep -q "^ADMIN_[A-Z_]*=."'; then
  echo "compose-smoke: el api recibe ADMIN_* con valor (deben ir solo en .env.seed)" >&2; exit 1
fi
echo "compose-smoke: api sin ADMIN_*"

if [ -f web/Dockerfile ] && [ -f scripts/ci/web-smoke.sh ]; then
  "${DC[@]}" up -d --build web
  esperar_healthy web 60
  # M-1: la IP de web es la única de TRUSTED_PROXIES.
  ip_web="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$("${DC[@]}" ps -q web)" | tr -d '\r')"
  confianza="$(grep -E '^TRUSTED_PROXIES=' .env | cut -d= -f2 | tr -d '\r')"
  if [ "$confianza" != "$ip_web/32" ]; then
    echo "compose-smoke: web está en $ip_web y TRUSTED_PROXIES=$confianza (deben coincidir)" >&2; exit 1
  fi
  echo "compose-smoke: web en $ip_web = TRUSTED_PROXIES"
  bash scripts/ci/web-smoke.sh
  # US-038: cabeceras de seguridad y CSP con nonce contra el stack construido.
  [ -f scripts/smoke/headers.sh ] && bash scripts/smoke/headers.sh
fi
echo "compose-smoke: verde en $(( $(date +%s) - inicio ))s"
