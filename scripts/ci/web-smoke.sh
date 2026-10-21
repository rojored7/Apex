#!/usr/bin/env bash
# web-smoke.sh
#
# Smoke de Nginx con el stack levantado (US-006, T2). Lo invoca compose-smoke.sh
# después de `up -d web`. Lee WEB_PORT de .env (por defecto 80).
#   1. / contiene <div id="root">.
#   2. /socios/123 responde 200 con el mismo index.html (SPA).
#   3. /api/v1/health llega al api: 200 desde US-020; antes, un 404 JSON del api,
#      nunca el 404 HTML de Nginx.
#   4. Un cuerpo de 5 MB + 1 byte a /api/v1/... devuelve 413.
#   5. Server: nginx sin versión.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
PUERTO="$(grep -E '^WEB_PORT=' "$ROOT/.env" 2>/dev/null | cut -d= -f2 | tr -d '\r' || true)"
BASE="http://localhost:${PUERTO:-80}"
fallas=0
ok() { echo "  ok   $1"; }
falla() { echo "  FALLA $1"; fallas=$((fallas + 1)); }

raiz="$(curl -fsS --max-time 10 "$BASE/" || true)"
if grep -q '<div id="root">' <<< "$raiz"; then ok "/ sirve index.html con #root"; else falla "/ no contiene <div id=\"root\">"; fi

codigo="$(curl -sS -o /tmp/apex-spa.html -w '%{http_code}' --max-time 10 "$BASE/socios/123" || true)"
if [ "$codigo" = "200" ] && grep -q '<div id="root">' /tmp/apex-spa.html; then ok "/socios/123 responde 200 con index.html"; else falla "/socios/123 respondió $codigo"; fi

codigo="$(curl -sS -o /tmp/apex-health.out -D /tmp/apex-health.hdr -w '%{http_code}' --max-time 10 "$BASE/api/v1/health" || true)"
tipo="$(grep -i '^content-type:' /tmp/apex-health.hdr | tr -d '\r' | cut -d' ' -f2- || true)"
if [ "$codigo" = "200" ]; then
  ok "/api/v1/health responde 200 por el proxy"
elif [ "$codigo" = "404" ] && grep -qi 'application/json' <<< "$tipo"; then
  ok "/api/v1/health llega al api (404 JSON de FastAPI; 200 desde US-020)"
else
  falla "/api/v1/health respondió $codigo ($tipo): no llegó al api"
fi

codigo="$(head -c 5242881 /dev/zero | curl -sS -o /dev/null -w '%{http_code}' --max-time 30 -X POST -H 'Content-Type: application/octet-stream' --data-binary @- "$BASE/api/v1/members/1/attachments" || true)"
if [ "$codigo" = "413" ]; then ok "5 MB + 1 byte devuelve 413 en Nginx"; else falla "cuerpo de 5 MB + 1 respondió $codigo (se esperaba 413)"; fi

servidor="$(curl -sI --max-time 10 "$BASE/" | grep -i '^server:' | tr -d '\r' || true)"
if grep -Eqi '^server: *nginx *$' <<< "$servidor"; then ok "Server: nginx sin versión"; else falla "cabecera Server: '$servidor'"; fi

echo "web-smoke: $fallas fallas"
[ "$fallas" -eq 0 ]
