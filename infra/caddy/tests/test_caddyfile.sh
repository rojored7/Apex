#!/usr/bin/env bash
# test_caddyfile.sh
#
# Rojo S6-W0-4 (S6-D63, D64, D77, M-7, M-8, E8, M1; paso 27 del plan del Sprint 6).
# Prueba infra/caddy/Caddyfile sin levantar ningún servicio: grep puro sobre el texto (aplanado, así
# que da igual el sangrado y si un bloque va en una o en varias líneas) y `caddy validate` dentro de un
# contenedor DESECHABLE de la imagen fijada por digest (nunca toca los proyectos apex ni apex-ensayo).
#
# Contrato que fija este archivo (lo implementa el Verde, paso 28):
#   - bloque global: `admin off`, `auto_https disable_redirects` (la redirección es explícita),
#     `skip_install_trust` (paso 26: con `read_only` Caddy no puede instalar su CA en /tmp),
#     `acme_ca {$APEX_ACME_CA:https://acme-v02.api.letsencrypt.org/directory}`; el correo ACME no puede romper la validación si la variable llega vacía (paso 26);
#   - sitio `http://` (puerto 80): `handle /_caddy_health` con `respond "ok" 200`, DESPUÉS
#     `handle /.well-known/acme-challenge/*` sin redirección y al final `redir https://{$APEX_DOMAIN}{uri} 308`;
#   - sitio `https://{$APEX_DOMAIN}`: `tls {$APEX_TLS_ISSUER}` con `curves x25519mlkem768 x25519` y
#     `protocols tls1.2 tls1.3`; HSTS `max-age={$APEX_HSTS_MAX_AGE:300}` sin includeSubDomains ni preload;
#     `reverse_proxy web:80`; sin `/_caddy_health`; sin `trusted_proxies`;
#   - el healthcheck de compose.yml apunta a /_caddy_health;
#   - el emisor `internal` solo existe en desarrollo (compose.dev.yml, host *.localhost), nunca como
#     valor por defecto de compose.yml ni de compose.tls.yml (S6-D77).
# Fallo esperado en el Rojo: infra/caddy/Caddyfile no existe.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
CF="$ROOT/infra/caddy/Caddyfile"
# Imagen de Caddy por digest (2026-11-11, W0-1.1; la misma de infra/compose.yml); renovar
# (docs/RUNBOOK.md §7): docker buildx imagetools inspect caddy:2.11.3 --format '{{json .Manifest.Digest}}'
CADDY_IMAGE="caddy:2.11.3@sha256:ec18ee54aab3315c22e25f3b2babda73ff8007d39b13b3bd1bfffa2f0444c7d9"
export MSYS_NO_PATHCONV=1
fallas=0
ok() { echo "  ok   $1"; }
falla() { echo "  FALLA $1"; fallas=$((fallas + 1)); }

# Texto sin líneas de comentario, y aplanado a una sola línea con espacios simples.
TXT="$(grep -Ev '^[[:space:]]*#' "$CF" 2> /dev/null | tr -d '\r' || true)"
FLAT="$(printf '%s' "$TXT" | tr '\n\t' '  ' | tr -s ' ')"
pos() { awk -v s="$1" -v t="$FLAT" 'BEGIN { print index(t, s) }'; } # posición (1 = primero; 0 = ausente)
contiene() { # descripcion literal
  if [ "$(pos "$2")" -gt 0 ]; then ok "$1"; else falla "$1 (falta: $2)"; fi
}
antes() { # descripcion literal-a literal-b: a existe y va antes que b
  local a b
  a="$(pos "$2")"; b="$(pos "$3")"
  if [ "$a" -gt 0 ] && [ "$b" -gt 0 ] && [ "$a" -lt "$b" ]; then ok "$1"; else falla "$1 (posiciones $a y $b)"; fi
}
sin() { # descripcion regex (insensible a mayúsculas)
  if printf '%s' "$FLAT" | grep -Eiq "$2"; then falla "$1"; else ok "$1"; fi
}

if [ -f "$CF" ]; then ok "existe infra/caddy/Caddyfile"; else falla "no existe infra/caddy/Caddyfile"; fi

# --- bloque global ---------------------------------------------------------------------------------
HTTP_POS="$(printf '%s' "$FLAT" | grep -Eob '(^| )(http://[^ ]*|:80) \{' | head -1 | cut -d: -f1 || true)"
HTTP_POS="${HTTP_POS:-0}"
GLOBAL="$( [ "$HTTP_POS" -gt 0 ] && printf '%s' "${FLAT:0:$HTTP_POS}" || true)"
for d in 'admin off' 'auto_https disable_redirects' 'skip_install_trust' \
  'acme_ca {$APEX_ACME_CA:https://acme-v02.api.letsencrypt.org/directory}'; do
  if [ -n "$GLOBAL" ] && [[ "$GLOBAL" == *"$d"* ]]; then ok "bloque global: $d"; else falla "bloque global sin: $d"; fi
done
sin "sin API de administración publicada (admin :2019 / admin localhost)" 'admin +[^o]|:2019'

# --- sitio http:// (E8, M1) --------------------------------------------------------------------------
if [ "$HTTP_POS" -gt 0 ]; then ok "hay un sitio http:// en el puerto 80"; else falla "falta el sitio http:// (o :80)"; fi
contiene "handle /_caddy_health responde 200 por HTTP (E8)" 'handle /_caddy_health { respond "ok" 200 }'
contiene "redirección explícita 308 a https://{\$APEX_DOMAIN}{uri}" 'redir https://{$APEX_DOMAIN}{uri} 308'
antes "/_caddy_health va antes del redir (la salud nunca redirige)" '/_caddy_health' 'redir https://'
antes "/.well-known/acme-challenge/* va antes del redir (M1)" 'handle /.well-known/acme-challenge/*' 'redir https://'
antes "/_caddy_health y el acme-challenge viven en el sitio http://" 'http://' '/_caddy_health'
ACME_TAIL=""
if [ "$(pos 'handle /.well-known/acme-challenge/*')" -gt 0 ]; then
  ACME_TAIL="${FLAT:$(($(pos 'handle /.well-known/acme-challenge/*') - 1))}"
  ACME_TAIL="${ACME_TAIL#handle /.well-known/acme-challenge/*}"
  ACME_TAIL="${ACME_TAIL%%handle*}"
fi
if [ "$(pos 'handle /.well-known/acme-challenge/*')" -gt 0 ] && [[ "$ACME_TAIL" != *redir* ]]; then ok "el handle del acme-challenge no redirige"; else falla "el handle del acme-challenge redirige o no existe"; fi

# --- sitio https (D64) -------------------------------------------------------------------------------
HTTPS_POS="$(pos 'https://{$APEX_DOMAIN} {')"
if [ "$HTTPS_POS" -gt 0 ]; then ok "hay un sitio https://{\$APEX_DOMAIN}"; else falla "falta el sitio https://{\$APEX_DOMAIN}"; fi
HTTPS_TXT=""
[ "$HTTPS_POS" -gt 0 ] && HTTPS_TXT="${FLAT:$((HTTPS_POS - 1))}"
en_https() { # descripcion literal
  if [ -n "$HTTPS_TXT" ] && [[ "$HTTPS_TXT" == *"$2"* ]]; then ok "$1"; else falla "$1 (no está en el sitio https: $2)"; fi
}
en_https "tls {\$APEX_TLS_ISSUER} (emisor por variable)" 'tls {$APEX_TLS_ISSUER}'
en_https "curves x25519mlkem768 x25519 (híbrido poscuántico con caída a x25519)" 'curves x25519mlkem768 x25519'
en_https "protocols tls1.2 tls1.3" 'protocols tls1.2 tls1.3'
en_https "HSTS con max-age={\$APEX_HSTS_MAX_AGE:300}" 'Strict-Transport-Security "max-age={$APEX_HSTS_MAX_AGE:300}"'
en_https "reverse_proxy web:80" 'reverse_proxy web:80'
if [ -n "$HTTPS_TXT" ] && [[ "$HTTPS_TXT" != *_caddy_health* ]]; then ok "el sitio https no expone /_caddy_health (E8)"; else falla "el sitio https expone /_caddy_health o no existe"; fi
sin "sin includeSubDomains (M-8: escalonado, solo el host)" 'includeSubDomains'
sin "sin preload (M-8)" 'preload'
sin "sin trusted_proxies (Caddy escribe su propio X-Forwarded-For)" 'trusted_proxies'
if [ "$(pos 'Strict-Transport-Security')" -gt 0 ] && [ "$(pos 'Strict-Transport-Security')" -gt "$HTTPS_POS" ]; then ok "HSTS solo en el sitio https"; else falla "HSTS fuera del sitio https o ausente"; fi

# --- compose: healthcheck y emisor internal solo en desarrollo ---------------------------------------
if grep -Eq '_caddy_health' "$ROOT/infra/compose.yml"; then ok "compose.yml: el healthcheck de caddy apunta a /_caddy_health"; else falla "compose.yml: sin healthcheck a /_caddy_health"; fi
if grep -Eq '^[[:space:]]*image:[[:space:]]*caddy:2\.11\.3@sha256:ec18ee54aab3315c22e25f3b2babda73ff8007d39b13b3bd1bfffa2f0444c7d9' "$ROOT/infra/compose.yml"; then ok "compose.yml fija la misma imagen de Caddy que esta prueba"; else falla "compose.yml sin image: $CADDY_IMAGE"; fi
for rel in infra/compose.yml infra/compose.tls.yml; do
  if [ -f "$ROOT/$rel" ] && grep -Ev '^[[:space:]]*#' "$ROOT/$rel" | grep -Eq 'APEX_TLS_ISSUER[^#]*internal'; then
    falla "$rel usa el emisor internal (solo en smoke y desarrollo, S6-D77)"
  else
    ok "$rel no usa el emisor internal"
  fi
done
if grep -Ev '^[[:space:]]*#' "$ROOT/infra/compose.dev.yml" | grep -Eq 'APEX_TLS_ISSUER[^#]*internal' \
  && grep -Ev '^[[:space:]]*#' "$ROOT/infra/compose.dev.yml" | grep -Eq 'APEX_DOMAIN[^#]*[A-Za-z0-9-]+\.localhost'; then
  ok "compose.dev.yml: internal solo junto a un host *.localhost"
else
  falla "compose.dev.yml sin APEX_TLS_ISSUER=internal junto a APEX_DOMAIN=<host>.localhost"
fi

# --- caddy validate en la imagen fijada (contenedor desechable) --------------------------------------
# Paso 26 (verificado por el Rojo con la imagen fijada): con `email {$APEX_ACME_EMAIL}` y la variable
# vacía o sin definir Caddy NO valida («wrong argument count ... after email»), y `acme_ca` con la
# variable vacía tampoco (una variable vacía no usa el valor por defecto). Compose pasa las variables
# a caddy, así que la prueba valida el Caddyfile con el entorno TAL COMO LO RENDERIZA
# `docker compose config` (el del ensayo: emisor internal y correo vacío), no con valores escritos a mano.
env_de_compose() { # APEX_DOMAIN APEX_TLS_ISSUER APEX_ACME_EMAIL APEX_HSTS_MAX_AGE -> K=V del servicio caddy
  (cd "$ROOT" && APEX_DOMAIN="$1" APEX_TLS_ISSUER="$2" APEX_ACME_EMAIL="$3" APEX_HSTS_MAX_AGE="$4" \
    docker compose --env-file .env.example --env-file .env.ops.example --profile tls -f infra/compose.yml config --format json 2> /dev/null) \
    | uv run --directory "$ROOT/api" --quiet python -c '
import json, sys
try:
    env = json.load(sys.stdin)["services"]["caddy"].get("environment") or {}
except Exception:
    sys.exit(3)
for k, v in env.items():
    print(k + "=" + ("" if v is None else str(v)))
' 2> /dev/null | tr -d '\r' || true
}
valida() { # descripcion APEX_DOMAIN APEX_TLS_ISSUER APEX_ACME_EMAIL APEX_HSTS_MAX_AGE
  local salida entorno args=() kv
  if [ ! -f "$CF" ]; then falla "$1 (sin Caddyfile)"; return; fi
  entorno="$(env_de_compose "$2" "$3" "$4" "$5")"
  if [ -z "$entorno" ]; then falla "$1 (compose no renderiza el servicio caddy con --profile tls)"; return; fi
  while IFS= read -r kv; do [ -z "$kv" ] || args+=(-e "$kv"); done <<< "$entorno"
  salida="$(docker run --rm -i "${args[@]}" "$CADDY_IMAGE" \
    sh -c 'cat > /tmp/Caddyfile && caddy validate --config /tmp/Caddyfile --adapter caddyfile' < "$CF" 2>&1 | tr -d '\r' || true)"
  if grep -q 'Valid configuration' <<< "$salida"; then ok "$1"; else falla "$1: $(tail -2 <<< "$salida" | tr '\n' ' ' | cut -c1-260)"; fi
}
valida "caddy validate con el entorno del ensayo renderizado por compose (apex.localhost:8443, internal, correo vacío)" \
  apex.localhost:8443 internal "" 300
valida "caddy validate con el entorno de producción renderizado por compose (dominio, correo ACME, HSTS 604800)" \
  apex.ejemplo.test ops@ejemplo.test ops@ejemplo.test 604800
if [ -f "$CF" ]; then
  salida="$(docker run --rm -i -e APEX_DOMAIN=apex.ejemplo.test -e APEX_TLS_ISSUER=ops@ejemplo.test -e APEX_ACME_EMAIL=ops@ejemplo.test \
    -e APEX_ACME_CA=https://acme-staging-v02.api.letsencrypt.org/directory -e APEX_HSTS_MAX_AGE=300 "$CADDY_IMAGE" \
    sh -c 'cat > /tmp/Caddyfile && caddy validate --config /tmp/Caddyfile --adapter caddyfile' < "$CF" 2>&1 | tr -d '\r' || true)"
  if grep -q 'Valid configuration' <<< "$salida"; then ok "caddy validate con las cinco variables a mano (CA de staging)"; else falla "caddy validate con las cinco variables a mano: $(tail -2 <<< "$salida" | tr '\n' ' ' | cut -c1-260)"; fi
else
  falla "caddy validate con las cinco variables a mano (sin Caddyfile)"
fi

echo "test_caddyfile: $fallas fallas"
[ "$fallas" -eq 0 ]
