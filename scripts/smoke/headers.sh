#!/usr/bin/env bash
# headers.sh
#
# Smoke de cabeceras de seguridad (US-038, T7) con el stack levantado. Lee WEB_PORT de
# .env (por defecto 80) o acepta la URL base como primer argumento.
#   1. / trae X-Content-Type-Options, X-Frame-Options, Referrer-Policy no-referrer y
#      Permissions-Policy (S2-W0-1, E9: la política se reparte por location).
#   2. / trae una Content-Security-Policy con 'nonce-<32 hex>', sin unsafe-inline ni unsafe-eval.
#   3. Dos peticiones seguidas reciben nonces distintos (sub_filter por petición).
#   4. El HTML servido no contiene el marcador __CSP_NONCE__ y sí el nonce de la cabecera.
#   5. index.html va con Cache-Control: no-store.
#   6. /api/v1/health vía Nginx trae nosniff, X-Frame-Options y su CSP mínima.
#   7. Un cuerpo de 6 MB a /api/v1/health devuelve 413 (client_max_body_size 5m).
#   S2-W0-1: form-action en las dos CSP, no-store y Pragma en /api/, Referrer-Policy
#   no-referrer en /restablecer/<token>, el access log de Nginx no contiene el token ni el
#   parámetro q, y una ráfaga de 45 POST a /api/v1/auth/login recibe al menos un 429 con
#   el envelope (va al final: deja la zona de limit_req de esta IP agotada unos segundos).
# Termina con código distinto de 0 nombrando cada comprobación que falló.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
if [ "${1:-}" != "" ]; then
  BASE="${1%/}"
else
  PUERTO="$(grep -E '^WEB_PORT=' "$ROOT/.env" 2>/dev/null | cut -d= -f2 | tr -d '\r' || true)"
  BASE="http://localhost:${PUERTO:-80}"
fi
fallas=0
ok() { echo "  ok   $1"; }
falla() { echo "  FALLA $1"; fallas=$((fallas + 1)); }
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cabecera() { { grep -i "^$2:" "$1" 2>/dev/null || true; } | head -1 | tr -d '\r' | cut -d' ' -f2-; }
exige() { # archivo nombre valor-esperado descripción
  local valor; valor="$(cabecera "$1" "$2")"
  if [ "$valor" = "$3" ]; then ok "$4: $2 = $3"; else falla "$4: $2 = '${valor:-<ausente>}' (se esperaba '$3')"; fi
}

curl -sS -D "$TMP/h1" -o "$TMP/b1" --max-time 10 "$BASE/" || true
curl -sS -D "$TMP/h2" -o "$TMP/b2" --max-time 10 "$BASE/" || true

exige "$TMP/h1" X-Content-Type-Options nosniff "/"
exige "$TMP/h1" X-Frame-Options DENY "/"
exige "$TMP/h1" Referrer-Policy no-referrer "/"
exige "$TMP/h1" Permissions-Policy "camera=(), microphone=(), geolocation=()" "/"
exige "$TMP/h1" Cache-Control no-store "/"

csp1="$(cabecera "$TMP/h1" Content-Security-Policy)"
csp2="$(cabecera "$TMP/h2" Content-Security-Policy)"
nonce1="$(grep -oE "nonce-[0-9a-f]{32}" <<< "$csp1" | head -1 | cut -d- -f2 || true)"
nonce2="$(grep -oE "nonce-[0-9a-f]{32}" <<< "$csp2" | head -1 | cut -d- -f2 || true)"
if [ -n "$nonce1" ]; then ok "/: CSP con nonce de 32 hex"; else falla "/: CSP sin nonce válido: '${csp1:-<ausente>}'"; fi
if grep -Eq "unsafe-inline|unsafe-eval" <<< "$csp1"; then falla "/: la CSP contiene unsafe-inline o unsafe-eval"; else ok "/: CSP sin unsafe-inline ni unsafe-eval"; fi
for directiva in "default-src 'self'" "frame-ancestors 'none'" "object-src 'none'" "base-uri 'self'" "form-action 'self'"; do
  if grep -Fq "$directiva" <<< "$csp1"; then ok "/: CSP incluye $directiva"; else falla "/: CSP sin $directiva"; fi
done
if [ -n "$nonce1" ] && [ -n "$nonce2" ] && [ "$nonce1" != "$nonce2" ]; then ok "/: dos peticiones reciben nonces distintos"; else falla "/: nonces iguales o ausentes ('$nonce1' / '$nonce2')"; fi
if grep -q "__CSP_NONCE__" "$TMP/b1"; then falla "/: el HTML conserva el marcador __CSP_NONCE__"; else ok "/: el HTML no conserva el marcador"; fi
if [ -n "$nonce1" ] && grep -q "nonce=\"$nonce1\"" "$TMP/b1"; then ok "/: el HTML lleva el nonce de la cabecera"; else falla "/: el HTML no lleva nonce=\"$nonce1\""; fi

curl -sS -D "$TMP/ha" -o /dev/null --max-time 10 "$BASE/api/v1/health" || true
exige "$TMP/ha" X-Content-Type-Options nosniff "/api/v1/health"
exige "$TMP/ha" X-Frame-Options DENY "/api/v1/health"
exige "$TMP/ha" Referrer-Policy strict-origin-when-cross-origin "/api/v1/health"
exige "$TMP/ha" Content-Security-Policy "default-src 'none'; frame-ancestors 'none'; form-action 'none'" "/api/v1/health"
exige "$TMP/ha" Cache-Control no-store "/api/v1/health"
exige "$TMP/ha" Pragma no-cache "/api/v1/health"

codigo="$(head -c 6291456 /dev/zero | curl -sS -o /dev/null -w '%{http_code}' --max-time 30 -X POST -H 'Content-Type: application/octet-stream' --data-binary @- "$BASE/api/v1/health" || true)"
if [ "$codigo" = "413" ]; then ok "6 MB a /api/v1/health devuelve 413"; else falla "6 MB respondió $codigo (se esperaba 413)"; fi

# US-048 / M-3: el token de /restablecer/ y el parámetro q no llegan al access log.
TOKEN="TOKENPRUEBA${RANDOM}$$"
BUSQUEDA="BUSCADO${RANDOM}$$"
desde="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
curl -sS -D "$TMP/hr" -o /dev/null --max-time 10 "$BASE/restablecer/$TOKEN" || true
exige "$TMP/hr" Referrer-Policy no-referrer "/restablecer/<token>"
curl -sS -o /dev/null --max-time 10 "$BASE/socios?q=$BUSQUEDA" || true
curl -sS -o /dev/null --max-time 10 "$BASE/api/v1/members?q=$BUSQUEDA" || true
sleep 1
log="$(docker compose --env-file "$ROOT/.env" -f "$ROOT/infra/compose.yml" logs --no-log-prefix --since "$desde" web 2>&1 || true)"
if grep -q '"uri":"/index.html"' <<< "$log"; then ok "log de Nginx: /restablecer/<token> registrado como /index.html"; else falla "log de Nginx: no apareció la petición a /restablecer/ (¿docker compose logs web?)"; fi
if grep -q "$TOKEN" <<< "$log"; then falla "log de Nginx: contiene el token de /restablecer/"; else ok "log de Nginx: sin el token de /restablecer/"; fi
if grep -q "$BUSQUEDA" <<< "$log"; then falla "log de Nginx: contiene el parámetro q"; else ok "log de Nginx: sin el parámetro q"; fi

# M-3 / E5: limit_req en /api/v1/auth/ (60r/m, burst 30). Siempre la última comprobación.
n429=0
for _ in $(seq 1 45); do
  codigo="$(curl -sS -o "$TMP/rl" -D "$TMP/hrl" -w '%{http_code}' --max-time 10 -X POST -H 'Content-Type: application/json' -H "Origin: $BASE" -d '{}' "$BASE/api/v1/auth/login" || true)"
  if [ "$codigo" = "429" ]; then n429=$((n429 + 1)); cp "$TMP/rl" "$TMP/rl429"; cp "$TMP/hrl" "$TMP/hrl429"; fi
done
if [ "$n429" -ge 1 ]; then ok "ráfaga de 45 POST a /api/v1/auth/login: $n429 respuestas 429"; else falla "ráfaga de 45 POST a /api/v1/auth/login sin ningún 429"; fi
if [ -f "$TMP/rl429" ] && grep -Fq '{"error":{"code":"rate_limited"' "$TMP/rl429"; then ok "el 429 lleva el envelope rate_limited"; else falla "el 429 no lleva el envelope rate_limited"; fi
if [ -f "$TMP/hrl429" ]; then exige "$TMP/hrl429" Retry-After 60 "429 de /api/v1/auth/"; else falla "429 de /api/v1/auth/: sin respuesta 429 para revisar Retry-After"; fi

echo "headers: $fallas fallas"
[ "$fallas" -eq 0 ]
