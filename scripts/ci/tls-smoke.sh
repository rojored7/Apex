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
# La cookie de refresh con Secure llega con el login real (E1, S6-W1): hoy se omite y se dice.
set -euo pipefail

usage() { sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; }

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
  comprobacion: cookie de refresh con Secure por HTTPS y sin Secure con --lan (desde E1)
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
  cod="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$base/api/v1/health" || true)"
  if [ "$cod" = "200" ]; then ok "/api/v1/health por HTTP responde 200"; else falla "/api/v1/health respondió '$cod'"; fi
  cab="$(curl -sI --max-time 10 "$base/" | tr -d '\r' || true)"
  if grep -qi '^strict-transport-security:' <<< "$cab"; then falla "modo LAN con Strict-Transport-Security"; else ok "modo LAN sin Strict-Transport-Security"; fi
  echo "  omitida: cookie de refresh sin Secure en LAN (llega con el login real, E1)"
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
  if [ -z "$("${DC[@]}" port web 80 2> /dev/null | tr -d '\r')" ]; then ok "web no publica puertos con compose.tls.yml"; else falla "web publica el 80 con compose.tls.yml"; fi
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
if grep -qE 'Negotiated TLS1.3 group: X25519$' <<< "$x"; then ok "caída a Negotiated TLS1.3 group: X25519"; else falla "sin caída a X25519"; fi
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
if grep -qi '^strict-transport-security:' /tmp/hc.hdr; then falla "HSTS en /_caddy_health por HTTP"; else ok "sin HSTS por HTTP"; fi

CURL_TLS=(--cacert /ca/root.crt --resolve "$HOST:$PORT:$CIP" --tlsv1.3 --max-time 15)
sc="$(curl -s -D /tmp/h.hdr -o /tmp/h.body -w '%{http_code}' "${CURL_TLS[@]}" "https://$HOST$SUF/api/v1/health")"
if [ "$sc" = "200" ]; then ok "https /api/v1/health por Caddy responde 200"; else falla "https /api/v1/health responde '$sc'"; fi
if grep -qi "^strict-transport-security: max-age=$HSTS_AGE\$" /tmp/h.hdr; then ok "Strict-Transport-Security: max-age=$HSTS_AGE por HTTPS"; else falla "HSTS distinto de max-age=$HSTS_AGE: $(grep -i '^strict-transport-security:' /tmp/h.hdr)"; fi
if grep -qiE '^strict-transport-security:.*(includeSubDomains|preload)' /tmp/h.hdr; then falla "HSTS con includeSubDomains o preload"; else ok "HSTS sin includeSubDomains ni preload"; fi
CLIENTE

# Un cliente desechable con openssl y curl; dos de ellos (IP distinta) para el limitador.
cliente_nuevo() { # nombre
  docker run -d --name "$1" --network "$NET" -v "$(nativa "$TMP"):/ca:ro" "$ALPINE_IMAGE" \
    sh -c "apk add --no-cache $OPENSSL_PKG curl > /tmp/apk.log 2>&1 && touch /tmp/listo; sleep 900" > /dev/null \
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

salida="$(docker exec -e CIP="$CIP" -e HOST="$HOST" -e PORT="$PORT" -e SUF="$SUF" -e HSTS_AGE="$HSTS_AGE" "$A" sh -c 'sh /ca/cliente.sh' 2>&1 | tr -d '\r' || true)"
printf '%s\n' "$salida"
n_mal="$(grep -c '^  FALLA ' <<< "$salida" || true)"
fallas=$((fallas + n_mal))
[ -n "$salida" ] || falla "el cliente no produjo salida"

# Limitador por IP real (S6-D29, M-7a): el cliente A agota su cupo de intentos; el B, desde otra IP del
# mismo Caddy, sigue pasando. Si Nginx contara a Caddy, B recibiría el 429 de A. Credenciales inventadas
# (un correo inexistente): ningún dato real.
intento() { # contenedor
  docker exec "$1" sh -c "curl -s -o /dev/null -w '%{http_code}' --cacert /ca/root.crt --resolve $HOST:$PORT:$CIP --tlsv1.3 --max-time 15 -X POST -H 'Content-Type: application/json' -d '{\"email\":\"tls-smoke@invalid.test\",\"password\":\"incorrecta-tls-smoke\"}' https://$HOST$SUF/api/v1/auth/login" 2> /dev/null | tr -d '\r'
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
echo "  omitida: cookie de refresh con Secure por HTTPS (llega con el login real, E1)"

if [ "$fallas" -ne 0 ]; then echo "tls-smoke: $fallas fallas" >&2; exit 1; fi
echo "tls-smoke: todo en verde"
