#!/usr/bin/env bash
# tls-smoke.sh [--dc "<comando de docker compose>"] [--lan] [--dry-run]
#
# Humo del perfil `tls` (S6-D63, D64, D82, D83; P-TLS del plan del Sprint 6). Con el stack ya levantado
# (`-f infra/compose.tls.yml --profile tls` en el ensayo y en prod-smoke --tls; el perfil `tls` de
# desarrollo en la CI) y SIN credenciales, desde contenedores `alpine:3.22` desechables fijados por digest
# (con `openssl=3.5.9-r0` y `curl`) en la red del stack comprueba: intercambio X25519MLKEM768 y caída a
# X25519, TLS 1.1 rechazado y 1.2 aceptado, 308 de /login, /_caddy_health 200 por HTTP, el desafío ACME
# sin 308, HSTS escalonado solo en HTTPS, /api/v1/health por Caddy y el limitador por IP real con dos
# clientes. La CA interna de Caddy se confía solo para el host apex.localhost (se copia del volumen de
# Caddy a un temporal). `--lan` comprueba el stack sin perfil (sin Caddy, sin HSTS, puerto por HTTP).
# `--dry-run` no levanta nada: renderiza `docker compose config` con y sin el perfil tls y lista las
# comprobaciones. `--dc` por omisión: el desarrollo (`-f infra/compose.dev.yml`, más `--profile tls`
# salvo con --lan). Sale con 0 en verde, 1 con fallas, 2 si el uso es inválido.
# Cookie y CORS (S6-E1, US-153): con TLS_SMOKE_ADMIN_EMAIL y TLS_SMOKE_ADMIN_PASSWORD_FILE (archivo de una
# línea, modo 600; nunca se imprime) hace login real y exige 200, Access-Control-Allow-Origin igual al origen
# público y la cookie apex_refresh con HttpOnly, SameSite=strict y Secure (con --lan, sin Secure); con
# Origin http://<dominio> exige 403 y sin Access-Control-Allow-Origin. Sin ellas: «omitida». Con
# TLS_SMOKE_ALLOW_SEALED=1, /api/v1/health acepta 503 con "crypto":"sealed" como aviso (por omisión, 200).
set -euo pipefail

usage() { sed -n '2,19p' "$0" | sed 's/^# \{0,1\}//'; }

# alpine:3.22 por digest (2026-11-11, W0-1.1); renovar (docs/RUNBOOK.md §7):
#   docker buildx imagetools inspect alpine:3.22 --format '{{json .Manifest.Digest}}'
ALPINE_IMAGE="alpine:3.22@sha256:49340b346798875b5592e5d420241f2f9cfba5f47e62ebb1446a1b34734e898f"
OPENSSL_PKG="openssl=3.5.9-r0"
export MSYS_NO_PATHCONV=1

DRY_RUN=0
LAN=0
DC_CMD=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --lan) LAN=1; shift ;;
    --dc)
      [ "$#" -ge 2 ] || { echo "tls-smoke: --dc necesita un comando de docker compose" >&2; exit 2; }
      DC_CMD="$2"; shift 2 ;;
    *) echo "tls-smoke: argumento desconocido: $1" >&2; exit 2 ;;
  esac
done

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

# Entorno de Compose para los renders y para el DC por omisión: .env y .env.ops si existen; si no, los ejemplos.
ENVS=()
if [ -f .env ]; then ENVS+=(--env-file .env); else ENVS+=(--env-file .env.example); fi
if [ -f .env.ops ]; then ENVS+=(--env-file .env.ops); else ENVS+=(--env-file .env.ops.example); fi

# Servicios de un render y si `web` publica puertos (YAML normalizado de `docker compose config`).
render_servicios() { # <args extra de compose antes de config...>
  docker compose "${ENVS[@]}" "$@" config --services 2> /dev/null | tr -d '\r'
}
web_publica_puertos() { # idem: 0 si el bloque web del render trae `ports:`
  docker compose "${ENVS[@]}" "$@" config 2> /dev/null | tr -d '\r' \
    | awk '/^  [a-z_-]+:/ { en_web = ($1 == "web:") } en_web && /^    ports:/ { found = 1 } END { exit found ? 0 : 1 }'
}

if [ "$DRY_RUN" -eq 1 ]; then
  modo="TLS (CA interna, perfil tls)"
  [ "$LAN" -eq 0 ] || modo="LAN (stack sin perfil tls)"
  echo "tls-smoke: comprobaciones (modo $modo)"
  cat <<'LISTA'
  comprobacion: openssl s_client -help lista -groups (grep -cE '^ *-groups ' = 1)
  comprobacion: -groups X25519MLKEM768 -> Negotiated TLS1.3 group: X25519MLKEM768 y Verify return code: 0
  comprobacion: -groups X25519 -> Negotiated TLS1.3 group: X25519 (caida)
  comprobacion: -tls1_1 rechazado
  comprobacion: -tls1_2 aceptado
  comprobacion: http://caddy/login -> 308 con Location https://apex.localhost
  comprobacion: http://caddy/.well-known/acme-challenge/x no responde 308
  comprobacion: http://caddy/_caddy_health -> 200
  comprobacion: Strict-Transport-Security max-age=300 por HTTPS y ausente por HTTP y con --lan
  comprobacion: login real (TLS_SMOKE_ADMIN_EMAIL y TLS_SMOKE_ADMIN_PASSWORD_FILE): 200, Access-Control-Allow-Origin igual al origen, cookie apex_refresh HttpOnly + SameSite=strict + Secure (con --lan sin Secure); Origin http:// -> 403 sin Access-Control-Allow-Origin (omitida sin TLS_SMOKE_ADMIN_*)
  comprobacion: con TLS_SMOKE_ALLOW_SEALED=1 /api/v1/health acepta 503 con "crypto":"sealed" (aviso: custodio sellado)
  comprobacion: limitador por IP real con dos clientes (el primero recibe 429; el segundo, desde otra IP, sigue pasando)
  comprobacion: docker compose config con y sin perfil tls (web sin ports con el overlay; caddy ausente sin perfil)
LISTA
  base=(-f infra/compose.yml)
  if [ "$(render_servicios "${base[@]}" | grep -cx caddy || true)" = "0" ]; then
    echo "  render sin perfil tls: caddy ausente"
  else
    echo "  FALLA render sin perfil tls: caddy aparece" >&2; exit 1
  fi
  if render_servicios "${base[@]}" --profile tls | grep -qx caddy && [ -f infra/compose.tls.yml ] \
    && ! web_publica_puertos "${base[@]}" -f infra/compose.tls.yml --profile tls; then
    echo "  render con perfil tls: caddy presente, web sin puertos (compose.tls.yml)"
  else
    echo "  FALLA render con perfil tls: sin caddy, sin compose.tls.yml o web con puertos" >&2; exit 1
  fi
  exit 0
fi

# --- ejecución real ----------------------------------------------------------------------------------------
if [ -n "$DC_CMD" ]; then
  read -r -a DC <<< "$DC_CMD"
else
  DC=(docker compose "${ENVS[@]}" -f infra/compose.yml -f infra/compose.dev.yml)
  [ "$LAN" -eq 1 ] || DC+=(--profile tls)
fi

fallas=0
ok() { printf '  ok   %s\n' "$1"; }
falla() { printf '  FALLA %s\n' "$1" >&2; fallas=$((fallas + 1)); }
muere() { printf 'tls-smoke: ERROR %s\n' "$1" >&2; exit 1; }
nativa() { if command -v cygpath > /dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }

# Temporales propios (S6-D82): nada se escribe dentro del árbol del repositorio.
TMP="$(mktemp -d)"
CLIENTES=()
limpiar() {
  local c
  for c in ${CLIENTES[@]+"${CLIENTES[@]}"}; do docker rm -f "$c" > /dev/null 2>&1 || true; done
  rm -rf "$TMP"
}
trap limpiar EXIT

# --- cookie y CORS con el login real (S6-E1, US-153) ---------------------------------------------------------
# Solo con TLS_SMOKE_ADMIN_EMAIL y TLS_SMOKE_ADMIN_PASSWORD_FILE. La clave sale de un archivo (modo 600) a un
# cuerpo temporal 600 dentro de $TMP; el token y la cookie viven en variables y nunca se imprimen (solo se
# comprueban sus atributos).
ADMIN_EMAIL="${TLS_SMOKE_ADMIN_EMAIL:-}"
ADMIN_PW_FILE="${TLS_SMOKE_ADMIN_PASSWORD_FILE:-}"
ALLOW_SEALED="${TLS_SMOKE_ALLOW_SEALED:-0}"

preparar_login() { # 0 si hay credenciales y dejó $TMP/login.json; 1 si se omite
  [ -n "$ADMIN_EMAIL" ] && [ -n "$ADMIN_PW_FILE" ] || return 1
  [ -f "$ADMIN_PW_FILE" ] || muere "TLS_SMOKE_ADMIN_PASSWORD_FILE no es un archivo"
  local clave esc_c esc_e
  clave="$(head -1 "$ADMIN_PW_FILE" | tr -d '\r\n')"
  [ -n "$clave" ] || muere "TLS_SMOKE_ADMIN_PASSWORD_FILE está vacío"
  esc_c="$(printf '%s' "$clave" | sed 's/\\/\\\\/g; s/"/\\"/g')"
  esc_e="$(printf '%s' "$ADMIN_EMAIL" | sed 's/\\/\\\\/g; s/"/\\"/g')"
  ( umask 077; printf '{"email":"%s","password":"%s"}' "$esc_e" "$esc_c" > "$TMP/login.json" )
  chmod 644 "$TMP/login.json"  # el cliente alpine (root) lo lee por el montaje ro; vive solo en $TMP
  return 0
}

# comprobar_cookie_y_cors <origen público> <origen http o vacío> <con Secure: 1|0> <función de POST>
# La función de POST recibe el Origin e imprime las cabeceras y, al final, __CODE__<código>.
comprobar_cookie_y_cors() {
  local origen="$1" origen_http="$2" con_secure="$3" post="$4" salida cod cab linea attrs acao
  salida="$("$post" "$origen" | tr -d '\r' || true)"
  cod="${salida##*__CODE__}"; cab="${salida%__CODE__*}"
  if [ "$cod" = "200" ]; then ok "login real con Origin $origen responde 200"; else falla "login real con Origin $origen respondió '$cod'"; fi
  acao="$(grep -i '^access-control-allow-origin:' <<< "$cab" | head -1 | cut -d: -f2- | tr -d ' ' || true)"
  if [ "$acao" = "$origen" ]; then ok "Access-Control-Allow-Origin igual al origen público"
  elif [ "$con_secure" = "1" ]; then falla "Access-Control-Allow-Origin distinto del origen público"
  else echo "  aviso: sin Access-Control-Allow-Origin en modo LAN (CORS_ORIGINS no incluye el origen; mismo origen no lo necesita)"; fi
  linea="$(grep -i '^set-cookie: apex_refresh=' <<< "$cab" | head -1 || true)"
  if [ -z "$linea" ]; then falla "el login no puso la cookie apex_refresh"
  else
    attrs="$(sed 's/^[^;]*;//' <<< "$linea")" # sin nombre ni valor de la cookie
    if grep -qi 'httponly' <<< "$attrs"; then ok "cookie apex_refresh con HttpOnly"; else falla "cookie apex_refresh sin HttpOnly"; fi
    if grep -qi 'samesite=strict' <<< "$attrs"; then ok "cookie apex_refresh con SameSite=strict"; else falla "cookie apex_refresh sin SameSite=strict"; fi
    if grep -qiE '(^|;) *secure *(;|$)' <<< "$attrs"; then
      if [ "$con_secure" = "1" ]; then ok "cookie apex_refresh con Secure"; else falla "cookie apex_refresh con Secure en modo LAN"; fi
    else
      if [ "$con_secure" = "1" ]; then falla "cookie apex_refresh sin Secure"; else ok "cookie apex_refresh sin Secure (modo LAN)"; fi
    fi
  fi
  if [ -n "$origen_http" ]; then
    salida="$("$post" "$origen_http" | tr -d '\r' || true)"
    cod="${salida##*__CODE__}"; cab="${salida%__CODE__*}"
    if [ "$cod" = "403" ]; then ok "login con Origin http:// responde 403"; else falla "login con Origin http:// respondió '$cod'"; fi
    if grep -qi '^access-control-allow-origin:' <<< "$cab"; then falla "Access-Control-Allow-Origin con Origin http://"; else ok "sin Access-Control-Allow-Origin con Origin http://"; fi
  fi
}

# ------------------------------- modo LAN: stack sin perfil tls ---------------------------------------------
if [ "$LAN" -eq 1 ]; then
  echo "tls-smoke: modo LAN (sin perfil tls)"
  if [ -z "$("${DC[@]}" ps -q caddy 2> /dev/null | tr -d '\r')" ]; then ok "caddy no está en marcha"; else falla "caddy está en marcha en modo LAN"; fi
  publicado="$("${DC[@]}" port web 80 2> /dev/null | tr -d '\r' | head -1 || true)"
  puerto="${publicado##*:}"
  if [[ "$puerto" =~ ^[0-9]{2,5}$ ]]; then ok "web publica el puerto $puerto por HTTP"; else muere "web no publica el 80 (¿stack sin web?)"; fi
  base="http://127.0.0.1:$puerto"
  cod="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$base/" || true)"
  if [ "$cod" = "200" ]; then ok "GET / por HTTP responde 200"; else falla "GET / por HTTP respondió '$cod'"; fi
  cod="$(curl -s -o "$(nativa "$TMP")/health.body" -w '%{http_code}' --max-time 10 "$base/api/v1/health" || true)"
  if [ "$cod" = "200" ]; then ok "/api/v1/health por HTTP responde 200"
  elif [ "$cod" = "503" ] && [ "$ALLOW_SEALED" = "1" ] && grep -q '"crypto" *: *"sealed"' "$TMP/health.body"; then echo "  aviso: custodio sellado (/api/v1/health 503 aceptado con TLS_SMOKE_ALLOW_SEALED=1)"
  else falla "/api/v1/health respondió '$cod'"; fi
  cab="$(curl -sI --max-time 10 "$base/" | tr -d '\r' || true)"
  if grep -qi '^strict-transport-security:' <<< "$cab"; then falla "modo LAN con Strict-Transport-Security"; else ok "modo LAN sin Strict-Transport-Security"; fi
  if preparar_login; then
    origen_lan="$("${DC[@]}" exec -T api printenv FRONT_BASE_URL 2> /dev/null | tr -d '\r' || true)"
    origen_lan="${origen_lan:-$base}"
    post_lan() { # Origin -> cabeceras y __CODE__<código>; el cuerpo (token) se descarta
      curl -s -D - -o /dev/null -w '\n__CODE__%{http_code}' --max-time 15 -X POST -H "Origin: $1" \
        -H 'Content-Type: application/json' --data "@$(nativa "$TMP")/login.json" "$base/api/v1/auth/login" || true
    }
    comprobar_cookie_y_cors "$origen_lan" "" 0 post_lan
  else
    echo "  omitida: cookie y CORS (sin TLS_SMOKE_ADMIN_*)"
  fi
  if [ "$fallas" -ne 0 ]; then echo "tls-smoke: $fallas fallas" >&2; exit 1; fi
  echo "tls-smoke: todo en verde (LAN)"
  exit 0
fi

# ------------------------------- modo TLS ---------------------------------------------------------------------
CID="$("${DC[@]}" ps -q caddy 2> /dev/null | head -1 | tr -d '\r' || true)"
[ -n "$CID" ] || muere "caddy no está en marcha: levante el stack con el perfil tls (docs/operacion/tls.md)"
NET="$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{println $k}}{{end}}' "$CID" | tr -d '\r' | head -1)"
CIP="$(docker inspect -f "{{(index .NetworkSettings.Networks \"$NET\").IPAddress}}" "$CID" | tr -d '\r')"
[ -n "$NET" ] && [ -n "$CIP" ] || muere "no se pudo leer la red ni la IP de caddy"
ENV_CADDY="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$CID" | tr -d '\r')"
DOMAIN="$(sed -n 's/^APEX_DOMAIN=//p' <<< "$ENV_CADDY" | head -1)"
ISSUER="$(sed -n 's/^APEX_TLS_ISSUER=//p' <<< "$ENV_CADDY" | head -1)"
HSTS_AGE="$(sed -n 's/^APEX_HSTS_MAX_AGE=//p' <<< "$ENV_CADDY" | head -1)"; HSTS_AGE="${HSTS_AGE:-300}"
[ -n "$DOMAIN" ] || muere "caddy no tiene APEX_DOMAIN"
[ "$ISSUER" = "internal" ] || muere "este humo solo confía en la CA interna de Caddy (APEX_TLS_ISSUER=internal, host *.localhost); el ACME real es un paso humano (docs/operacion/tls.md)"
HOST="${DOMAIN%%:*}"
[ "$HOST" = "apex.localhost" ] || muere "la CA interna solo se confía para el host apex.localhost (APEX_DOMAIN=$DOMAIN)"
PORT=443
[[ "$DOMAIN" != *:* ]] || PORT="${DOMAIN##*:}"
SUF=""
[ "$PORT" = "443" ] || SUF=":$PORT"
echo "tls-smoke: caddy $CIP en la red $NET, host $HOST, HTTPS en el puerto $PORT, HSTS max-age=$HSTS_AGE"

# Raíz de la CA interna: del volumen de Caddy a un temporal propio.
docker cp "$CID:/data/caddy/pki/authorities/local/root.crt" "$(nativa "$TMP")/root.crt" > /dev/null 2>&1 \
  || muere "no se pudo copiar la raíz de la CA interna (¿Caddy aún no emitió su primer certificado?)"
chmod 644 "$TMP/root.crt"

# Overlay de producción: web no publica puertos (solo se exige si el overlay está en el comando).
if [[ " ${DC[*]} " == *compose.tls.yml* ]]; then
  WEB_CID="$("${DC[@]}" ps -q web 2> /dev/null | head -1 | tr -d '\r' || true)"
  PUB="$(docker port "$WEB_CID" 80 2> /dev/null | tr -d '\r' || true)"
  # Compose 5.6: un puerto sin publicar puede salir como ':0' o vacío.
  if [ -z "$PUB" ] || [[ "$PUB" == *:0 ]]; then ok "web no publica puertos con compose.tls.yml"; else falla "web publica el 80 con compose.tls.yml"; fi
fi

# Comprobaciones dentro de un cliente alpine desechable (sin credenciales, solo la raíz de la CA interna).
cat > "$TMP/cliente.sh" <<'CLIENTE'
# Variables: CIP HOST PORT SUF HSTS_AGE. Imprime «  ok   ...» o «  FALLA ...» por comprobación.
ok() { printf '  ok   %s\n' "$1"; }
falla() { printf '  FALLA %s\n' "$1"; }
s_client() { echo | openssl s_client -connect "$CIP:$PORT" -servername "$HOST" -CAfile /ca/root.crt -verify_hostname "$HOST" "$@" 2>&1 || true; }
n_groups="$(openssl s_client -help 2>&1 | grep -cE '^ *-groups ' || true)"
if [ "$n_groups" = "1" ]; then ok "openssl s_client lista -groups (grep -cE '^ *-groups ' = 1)"; else falla "openssl s_client no lista -groups exactamente una vez ($n_groups)"; fi
h="$(s_client -tls1_3 -groups X25519MLKEM768)"
if grep -q 'Negotiated TLS1.3 group: X25519MLKEM768' <<< "$h"; then ok "intercambio híbrido: Negotiated TLS1.3 group: X25519MLKEM768"; else falla "no se negoció X25519MLKEM768"; fi
if grep -q 'Verify return code: 0' <<< "$h"; then ok "certificado verificado con la CA interna (Verify return code: 0)"; else falla "el certificado no verifica con la CA interna"; fi
x="$(s_client -tls1_3 -groups X25519)"
if grep -qE 'Negotiated TLS1.3 group: X25519$|Peer Temp Key: X25519,' <<< "$x"; then ok "caída a Negotiated TLS1.3 group: X25519"; else falla "sin caída a X25519"; fi
t11="$(s_client -tls1_1)"
if grep -qE 'Protocol *: TLSv1(\.1)?$' <<< "$t11"; then falla "TLS 1.1 aceptado"; else ok "TLS 1.1 rechazado"; fi
t12="$(s_client -tls1_2)"
if grep -qE 'Protocol *: TLSv1.2' <<< "$t12"; then ok "TLS 1.2 aceptado"; else falla "TLS 1.2 rechazado"; fi

REDIR="https://$HOST$SUF/login"
cab="$(curl -sI --max-time 10 --resolve "$HOST:80:$CIP" "http://$HOST/login" | tr -d '\r')"
if head -1 <<< "$cab" | grep -q ' 308'; then ok "http /login responde 308"; else falla "http /login no responde 308: $(head -1 <<< "$cab")"; fi
if grep -qi "^location: $REDIR\$" <<< "$cab"; then ok "308 con Location $REDIR"; else falla "Location distinta de $REDIR: $(grep -i '^location:' <<< "$cab")"; fi
if grep -qi '^strict-transport-security:' <<< "$cab"; then falla "HSTS en la redirección HTTP"; else ok "sin HSTS en la redirección HTTP"; fi
ac="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 --resolve "$HOST:80:$CIP" "http://$HOST/.well-known/acme-challenge/tls-smoke")"
if [ "$ac" != "308" ] && [ -n "$ac" ] && [ "$ac" != "000" ]; then ok "acme-challenge no responde 308 (responde $ac)"; else falla "acme-challenge responde '$ac' (no debe redirigir)"; fi
hc="$(curl -s -D /tmp/hc.hdr -o /dev/null -w '%{http_code}' --max-time 10 --resolve "$HOST:80:$CIP" "http://$HOST/_caddy_health")"
if [ "$hc" = "200" ]; then ok "http /_caddy_health responde 200"; else falla "http /_caddy_health responde '$hc'"; fi
tr -d '\r' < /tmp/hc.hdr > /tmp/hc.h2
if grep -qi '^strict-transport-security:' /tmp/hc.h2; then falla "HSTS en /_caddy_health por HTTP"; else ok "sin HSTS por HTTP"; fi

CURL_TLS=(--cacert /ca/root.crt --resolve "$HOST:$PORT:$CIP" --tlsv1.3 --max-time 15)
sc="$(curl -s -D /tmp/h.hdr -o /tmp/h.body -w '%{http_code}' "${CURL_TLS[@]}" "https://$HOST$SUF/api/v1/health")"
tr -d '\r' < /tmp/h.hdr > /tmp/h.h2
if [ "$sc" = "200" ]; then ok "https /api/v1/health por Caddy responde 200"
elif [ "$sc" = "503" ] && [ "$ALLOW_SEALED" = "1" ] && grep -q '"crypto" *: *"sealed"' /tmp/h.body; then echo "  aviso: custodio sellado (https /api/v1/health 503 aceptado con TLS_SMOKE_ALLOW_SEALED=1)"
else falla "https /api/v1/health responde '$sc'"; fi
if grep -qi "^strict-transport-security: max-age=$HSTS_AGE\$" /tmp/h.h2; then ok "Strict-Transport-Security: max-age=$HSTS_AGE por HTTPS"; else falla "HSTS distinto de max-age=$HSTS_AGE: $(grep -i '^strict-transport-security:' /tmp/h.h2)"; fi
if grep -qiE '^strict-transport-security:.*(includeSubDomains|preload)' /tmp/h.h2; then falla "HSTS con includeSubDomains o preload"; else ok "HSTS sin includeSubDomains ni preload"; fi
# US-153.5 (V11): la CSP que se sirve con dominio no contiene orígenes http:.
cs="$(curl -s -D /tmp/s.hdr -o /dev/null -w '%{http_code}' "${CURL_TLS[@]}" "https://$HOST$SUF/")"
tr -d '\r' < /tmp/s.hdr > /tmp/s.h2
if ! grep -qi '^content-security-policy:' /tmp/s.h2; then falla "GET / por HTTPS sin Content-Security-Policy (código $cs)"
elif grep -i '^content-security-policy:' /tmp/s.h2 | grep -q 'http:'; then falla "la CSP servida por HTTPS contiene un origen http: (US-153.5)"
else ok "CSP servida por HTTPS sin orígenes http: (US-153.5)"; fi
CLIENTE

# Un cliente desechable con openssl y curl; dos de ellos (IP distinta) para el limitador.
cliente_nuevo() { # nombre
  docker run -d --name "$1" --network "$NET" -v "$(nativa "$TMP"):/ca:ro" "$ALPINE_IMAGE" \
    sh -c "apk add --no-cache $OPENSSL_PKG curl bash > /tmp/apk.log 2>&1 && touch /tmp/listo; sleep 900" > /dev/null \
    || muere "no se pudo crear el cliente $1"
  CLIENTES+=("$1")
  local t=0
  until docker exec "$1" test -f /tmp/listo > /dev/null 2>&1; do
    t=$((t + 2)); [ "$t" -lt 120 ] || { docker exec "$1" cat /tmp/apk.log >&2 || true; muere "el cliente $1 no instaló $OPENSSL_PKG y curl"; }
    sleep 2
  done
}
cliente_nuevo "tls-smoke-a-$$"
cliente_nuevo "tls-smoke-b-$$"
A="tls-smoke-a-$$"
B="tls-smoke-b-$$"

salida="$(docker exec -e CIP="$CIP" -e HOST="$HOST" -e PORT="$PORT" -e SUF="$SUF" -e HSTS_AGE="$HSTS_AGE" -e ALLOW_SEALED="$ALLOW_SEALED" "$A" bash /ca/cliente.sh 2>&1 | tr -d '\r' || true)"
printf '%s\n' "$salida"
n_mal="$(grep -c '^  FALLA ' <<< "$salida" || true)"
fallas=$((fallas + n_mal))
[ -n "$salida" ] || falla "el cliente no produjo salida"

# Limitador por IP real (S6-D29, M-7a): el cliente A agota su cupo de intentos; el B, desde otra IP del
# mismo Caddy, sigue pasando. Si Nginx contara a Caddy, B recibiría el 429 de A. Credenciales inventadas
# (un correo inexistente): ningún dato real.
ORIGIN="$("${DC[@]}" exec -T api printenv FRONT_BASE_URL 2> /dev/null | tr -d '\r' || true)"
ORIGIN="${ORIGIN:-https://$HOST$SUF}"
intento() { # contenedor
  docker exec "$1" sh -c "curl -s -o /dev/null -w '%{http_code}' --cacert /ca/root.crt --resolve $HOST:$PORT:$CIP --tlsv1.3 --max-time 15 -X POST -H 'Origin: $ORIGIN' -H 'Content-Type: application/json' -d '{\"email\":\"tls-smoke@invalid.test\",\"password\":\"incorrecta-tls-smoke\"}' https://$HOST$SUF/api/v1/auth/login" 2> /dev/null | tr -d '\r'
}
primero="$(intento "$A")"
n429=0
for _ in $(seq 1 45); do
  [ "$(intento "$A")" != "429" ] || n429=$((n429 + 1))
done
del_otro="$(intento "$B")"
case "$primero" in 401|422) ok "limitador: el primer intento del cliente A pasa ($primero)" ;; *) falla "limitador: el primer intento del cliente A respondió '$primero'" ;; esac
if [ "$n429" -ge 1 ]; then ok "limitador: el cliente A recibe 429 tras agotar su cupo ($n429 de 45)"; else falla "limitador: el cliente A nunca recibió 429 en 46 intentos"; fi
case "$del_otro" in 401|422) ok "limitador por IP real: el cliente B (otra IP) sigue pasando ($del_otro)" ;; *) falla "limitador por IP real: el cliente B respondió '$del_otro' (¿Nginx cuenta a Caddy?)" ;; esac
if preparar_login; then
  post_tls() { # Origin -> cabeceras y __CODE__<código>; el cuerpo (token) se descarta
    docker exec "$B" sh -c "curl -s -D - -o /dev/null -w '\n__CODE__%{http_code}' --cacert /ca/root.crt --resolve $HOST:$PORT:$CIP --tlsv1.3 --max-time 15 -X POST -H 'Origin: $1' -H 'Content-Type: application/json' --data @/ca/login.json https://$HOST$SUF/api/v1/auth/login" 2> /dev/null || true
  }
  comprobar_cookie_y_cors "https://$HOST$SUF" "http://$HOST$SUF" 1 post_tls
else
  echo "  omitida: cookie y CORS (sin TLS_SMOKE_ADMIN_*)"
fi

if [ "$fallas" -ne 0 ]; then echo "tls-smoke: $fallas fallas" >&2; exit 1; fi
echo "tls-smoke: todo en verde"
