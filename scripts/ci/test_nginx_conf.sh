#!/usr/bin/env bash
# test_nginx_conf.sh
#
# Prueba de infra/nginx/ (US-006 T1, US-038 T9, S2-W0-1): `nginx -t` dentro de la imagen
# oficial (default.conf y snippets/ entran por un tar en stdin para no depender de bind
# mounts en Git Bash) y presencia de las directivas que fijan el contrato: 5 MB de
# cuerpo, server_tokens off, X-Forwarded-For sobrescrito con $remote_addr, proxy a
# api:8000 sin URI, fallback del SPA, log sin query strings, cabeceras de seguridad en
# cada location, CSP con nonce y sin unsafe-*, sub_filter del marcador y no-store.
# S2-W0-1: limit_req en /api/v1/auth/ con 429 en envelope, 16k de cuerpo en auth,
# no-store y Pragma en /api/, form-action en las dos CSP, Referrer-Policy por location
# (fuera del snippet común) y una prueba funcional con Nginx real: el access log de
# /restablecer/<token> y de ?q= no contiene el token ni la búsqueda.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
DIR="$ROOT/infra/nginx"
CONF="$DIR/default.conf"
SNIP="$DIR/snippets"
fallas=0
ok() { echo "  ok   $1"; }
falla() { echo "  FALLA $1"; fallas=$((fallas + 1)); }

[ -f "$CONF" ] || { echo "  FALLA no existe infra/nginx/default.conf"; exit 1; }
[ -d "$SNIP" ] || { echo "  FALLA no existe infra/nginx/snippets/"; exit 1; }

PREPARA='mkdir -p /tmp/n && tar -x -C /tmp/n && cp /tmp/n/default.conf /etc/nginx/conf.d/default.conf && cp -r /tmp/n/snippets /etc/nginx/snippets'
NGINX_T="$PREPARA && nginx -t"
if tar -C "$DIR" -c default.conf snippets | docker run --rm -i --add-host api:127.0.0.1 nginx:stable-alpine sh -c "$NGINX_T" > /dev/null 2>&1; then
  ok "nginx -t acepta la configuración"
else
  falla "nginx -t rechaza la configuración"
  tar -C "$DIR" -c default.conf snippets | docker run --rm -i --add-host api:127.0.0.1 nginx:stable-alpine sh -c "$NGINX_T" 2>&1 | tail -5 || true
fi

directiva() { # patrón descripción (busca en default.conf y en los snippets)
  if grep -Eqh "$1" "$CONF" "$SNIP"/*.conf; then ok "$2"; else falla "$2"; fi
}
bloque() { # imprime el cuerpo de "location <arg> {" en default.conf
  awk -v cab="location $1 {" 'index($0, cab) { d=1; next } d && /^\s*}/ { d=0 } d' "$CONF"
}
directiva '^\s*client_max_body_size\s+5m;' "client_max_body_size 5m"
directiva '^\s*server_tokens\s+off;' "server_tokens off"
directiva '^\s*proxy_set_header\s+X-Forwarded-For\s+\$remote_addr;' "X-Forwarded-For sobrescrito con \$remote_addr"
directiva '^\s*proxy_set_header\s+X-Request-ID\s+\$request_id;' "X-Request-ID propagado"
directiva '^\s*proxy_pass\s+http://api:8000;' "proxy_pass a api:8000 sin URI (conserva /api/v1/...)"
directiva 'try_files\s+\$uri\s+\$uri/\s+/index\.html;' "fallback del SPA a index.html"
directiva '^\s*log_format\s+apex' "log_format apex propio"
directiva '"uri":"\$uri"' "log_format apex registra \$uri (sin query string)"
if grep -Eqh '\$args|\$request_uri|\$query_string|\$arg_|\$request\b|\$http_authorization|\$http_cookie|\$http_referer' "$CONF" "$SNIP"/*.conf; then falla "el log no debe incluir query strings, Referer ni cabeceras con tokens"; else ok "log sin query strings ni cabeceras sensibles"; fi
if grep -Eqh 'proxy_add_x_forwarded_for' "$CONF" "$SNIP"/*.conf; then falla "proxy_add_x_forwarded_for concatenaría la IP del cliente"; else ok "sin proxy_add_x_forwarded_for"; fi
if grep -Eq '^\s*location[^{]*restablecer' "$CONF"; then falla "no debe existir un location de /restablecer/ (M-3: responde = /index.html)"; else ok "sin location especial de /restablecer/"; fi

# US-038: cabeceras de seguridad comunes. Referrer-Policy sale del snippet (E9).
for h in 'X-Content-Type-Options "nosniff" always' 'X-Frame-Options "DENY" always' 'Permissions-Policy "camera=\(\), microphone=\(\), geolocation=\(\)" always'; do
  if grep -Eq "^\s*add_header\s+$h;" "$SNIP/security-headers.conf"; then ok "snippet: add_header $h"; else falla "snippet sin add_header $h"; fi
done
if grep -Eq '^\s*add_header\s+Referrer-Policy' "$SNIP/security-headers.conf"; then falla "Referrer-Policy debe salir de security-headers.conf (cada location pone la suya)"; else ok "security-headers.conf sin Referrer-Policy"; fi
# Cada location de default.conf incluye el snippet de cabeceras (directo o vía proxy-api).
sin_include="$(awk '
  /^\s*location\b/ { loc=$0; inc=0; next }
  loc && /include\s+snippets\/(security-headers|proxy-api)\.conf;/ { inc=1 }
  loc && /^\s*}/ { if (!inc) print loc; loc="" }
' "$CONF")"
if [ -z "$sin_include" ]; then ok "todos los location incluyen snippets/security-headers.conf"; else falla "location sin cabeceras de seguridad:$sin_include"; fi
grep -q 'include snippets/security-headers.conf;' "$SNIP/proxy-api.conf" && ok "proxy-api.conf incluye las cabeceras" || falla "proxy-api.conf no incluye security-headers.conf"

# Referrer-Policy por location (E4/E9): toda location la declara o incluye proxy-api.conf.
sin_referrer="$(awk '
  /^\s*location\b/ { loc=$0; rp=0; next }
  loc && (/add_header\s+Referrer-Policy/ || /include\s+snippets\/proxy-api\.conf;/) { rp=1 }
  loc && /^\s*}/ { if (!rp) print loc; loc="" }
' "$CONF")"
if [ -z "$sin_referrer" ]; then ok "todos los location declaran Referrer-Policy"; else falla "location sin Referrer-Policy:$sin_referrer"; fi
politica() { # location política
  local p
  p="$(bloque "$1" | sed -n 's/^\s*add_header\s\+Referrer-Policy\s\+"\([^"]*\)".*/\1/p' | head -1)"
  if [ "$p" = "$2" ]; then ok "location $1: Referrer-Policy $2"; else falla "location $1: Referrer-Policy '${p:-<ausente>}' (se esperaba '$2')"; fi
}
politica "= /index.html" "no-referrer"
politica "/" "no-referrer"
politica "/assets/" "strict-origin-when-cross-origin"
politica "/fonts/" "strict-origin-when-cross-origin"
politica "/brand/" "strict-origin-when-cross-origin"
politica "@rate_limited" "strict-origin-when-cross-origin"
if grep -Eq '^\s*add_header\s+Referrer-Policy\s+"strict-origin-when-cross-origin"\s+always;' "$SNIP/proxy-api.conf"; then ok "proxy-api.conf: Referrer-Policy strict-origin-when-cross-origin"; else falla "proxy-api.conf sin Referrer-Policy strict-origin-when-cross-origin"; fi

directiva "add_header Content-Security-Policy \"default-src 'self'; script-src 'self' 'nonce-\\\$request_id'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'\" always;" "CSP del HTML exacta con nonce-\$request_id y form-action 'self' (L-1)"
directiva "add_header Content-Security-Policy \"default-src 'none'; frame-ancestors 'none'; form-action 'none'\" always;" "CSP mínima en /api/ con form-action 'none'"
if grep -Eqh "unsafe-inline|unsafe-eval" "$CONF" "$SNIP"/*.conf; then falla "la CSP no debe contener unsafe-inline ni unsafe-eval"; else ok "sin unsafe-inline ni unsafe-eval"; fi
directiva "^\s*sub_filter\s+'__CSP_NONCE__'\s+'\\\$request_id';" "sub_filter del marcador __CSP_NONCE__"
directiva '^\s*sub_filter_once\s+off;' "sub_filter_once off"
directiva 'add_header Cache-Control "no-store" always;' "index.html con Cache-Control no-store"
if grep -Eq 'gzip_static\s+on' "$CONF"; then falla "gzip_static on rompería sub_filter"; else ok "sin gzip_static"; fi
if grep -q 'location /api/v1/tv/' "$CONF"; then ok "location /api/v1/tv/ preparado (N-44)"; else falla "falta location /api/v1/tv/ (N-44)"; fi
if grep -q 'COPY infra/nginx/snippets/' "$ROOT/web/Dockerfile"; then ok "web/Dockerfile copia los snippets"; else falla "web/Dockerfile no copia infra/nginx/snippets/"; fi

# L-1: las respuestas del api no se guardan en caché.
if grep -Eq '^\s*add_header\s+Cache-Control\s+"no-store"\s+always;' "$SNIP/proxy-api.conf"; then ok "proxy-api.conf: Cache-Control no-store"; else falla "proxy-api.conf sin Cache-Control no-store"; fi
if grep -Eq '^\s*add_header\s+Pragma\s+"no-cache"\s+always;' "$SNIP/proxy-api.conf"; then ok "proxy-api.conf: Pragma no-cache"; else falla "proxy-api.conf sin Pragma no-cache"; fi

# M-3 / E5: limit_req en /api/v1/auth/ a 60r/m con burst 30 nodelay y 429 en envelope.
directiva '^\s*limit_req_zone\s+\$binary_remote_addr\s+zone=apex_auth:10m\s+rate=60r/m;' "limit_req_zone apex_auth a 60r/m por IP"
auth_loc="$(bloque /api/v1/auth/)"
if grep -Eq '^\s*limit_req\s+zone=apex_auth\s+burst=30\s+nodelay;' <<< "$auth_loc"; then ok "/api/v1/auth/: limit_req burst=30 nodelay"; else falla "/api/v1/auth/ sin limit_req zone=apex_auth burst=30 nodelay"; fi
if grep -Eq '^\s*client_max_body_size\s+16k;' <<< "$auth_loc"; then ok "/api/v1/auth/: client_max_body_size 16k (L-12)"; else falla "/api/v1/auth/ sin client_max_body_size 16k"; fi
if grep -Eq '^\s*error_page\s+429\s+=\s+@rate_limited;' <<< "$auth_loc"; then ok "/api/v1/auth/: error_page 429 = @rate_limited"; else falla "/api/v1/auth/ sin error_page 429 = @rate_limited"; fi
if grep -q 'include snippets/proxy-api.conf;' <<< "$auth_loc"; then ok "/api/v1/auth/ hace proxy al api"; else falla "/api/v1/auth/ no incluye proxy-api.conf"; fi
directiva '^\s*limit_req_status\s+429;' "limit_req_status 429"
directiva '^\s*limit_req_log_level\s+warn;' "limit_req_log_level warn (el error_log no registra la línea con query)"
lim_loc="$(bloque @rate_limited)"
if grep -Fq "return 429 '{\"error\":{\"code\":\"rate_limited\",\"message\":\"Demasiados intentos. Espera un momento.\"}}';" <<< "$lim_loc"; then ok "@rate_limited devuelve el envelope rate_limited"; else falla "@rate_limited sin el envelope de error"; fi
if grep -Eq '^\s*add_header\s+Retry-After\s+"60"\s+always;' <<< "$lim_loc"; then ok "@rate_limited con Retry-After 60"; else falla "@rate_limited sin Retry-After 60"; fi
if grep -Eq '^\s*default_type\s+application/json;' <<< "$lim_loc"; then ok "@rate_limited con application/json"; else falla "@rate_limited sin default_type application/json"; fi

# V4 del Sprint 2 (perfil E2E del borde): la zona de limit_req vive en snippets/auth-zone.conf,
# incluida en el contexto http por default.conf; la imagen lleva la de producción (60r/m) y
# solo infra/compose.e2e.yml monta encima infra/nginx/e2e/auth-zone.conf (fuera de snippets/,
# así que nunca entra en la imagen) con un tope alto para las specs del proyecto stack.
E2E_ZONE="$DIR/e2e/auth-zone.conf"
if grep -Eq '^include\s+snippets/auth-zone\.conf;' "$CONF"; then ok "default.conf incluye snippets/auth-zone.conf en el contexto http"; else falla "default.conf no incluye snippets/auth-zone.conf fuera de server"; fi
if grep -Eq '^\s*limit_req_zone\s+\$binary_remote_addr\s+zone=apex_auth:10m\s+rate=60r/m;' "$SNIP/auth-zone.conf" 2>/dev/null; then ok "snippets/auth-zone.conf: apex_auth a 60r/m (producción)"; else falla "snippets/auth-zone.conf sin limit_req_zone apex_auth a 60r/m"; fi
if grep -Eq 'limit_req_zone' "$CONF"; then falla "default.conf repite limit_req_zone (debe vivir solo en snippets/auth-zone.conf)"; else ok "default.conf sin limit_req_zone propia"; fi
if [ -f "$E2E_ZONE" ] && grep -Eq '^\s*limit_req_zone\s+\$binary_remote_addr\s+zone=apex_auth:10m\s+rate=[0-9]+r/m;' "$E2E_ZONE" && ! grep -Eq 'rate=60r/m' "$E2E_ZONE"; then ok "e2e/auth-zone.conf: misma zona apex_auth con otro tope"; else falla "infra/nginx/e2e/auth-zone.conf ausente o sin la zona apex_auth con un tope distinto de 60r/m"; fi
if grep -q 'infra/nginx/e2e' "$ROOT/web/Dockerfile"; then falla "web/Dockerfile copia infra/nginx/e2e (el perfil E2E no puede entrar en la imagen)"; else ok "web/Dockerfile no copia infra/nginx/e2e"; fi
NGINX_T_E2E="$PREPARA && cp /tmp/n/e2e/auth-zone.conf /etc/nginx/snippets/auth-zone.conf && nginx -t"
if [ -f "$E2E_ZONE" ] && tar -C "$DIR" -c default.conf snippets e2e | docker run --rm -i --add-host api:127.0.0.1 nginx:stable-alpine sh -c "$NGINX_T_E2E" > /dev/null 2>&1; then ok "nginx -t acepta la configuración con el perfil E2E del borde"; else falla "nginx -t rechaza la configuración con e2e/auth-zone.conf"; fi

# Prueba funcional con Nginx real (el api resuelve a 127.0.0.1:8000, cerrado: el proxy da
# 502, lo que basta para el log y el limitador). El token y la búsqueda no llegan al log.
TOKEN="TOKENPRUEBA${RANDOM}$$"
BUSQUEDA="BUSCADO${RANDOM}$$"
FUNCIONAL="$PREPARA && nginx && sleep 0.3"
FUNCIONAL+=" && curl -s -D - -o /dev/null http://127.0.0.1/restablecer/$TOKEN | sed 's/^/HDR /'"
FUNCIONAL+=" && curl -s -o /dev/null http://127.0.0.1/socios?q=$BUSQUEDA"
FUNCIONAL+=" && curl -s -o /dev/null http://127.0.0.1/api/v1/members?q=$BUSQUEDA"
FUNCIONAL+=" && head -c 20000 /dev/zero | curl -s -o /dev/null -w 'BIG %{http_code}\n' -X POST --data-binary @- http://127.0.0.1/api/v1/auth/forgot"
FUNCIONAL+=" && for i in \$(seq 1 45); do curl -s -o /dev/null -w 'CODE %{http_code}\n' -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1/api/v1/auth/login; done"
FUNCIONAL+=" && curl -s -D - -o /tmp/b429 -X POST -d '{}' http://127.0.0.1/api/v1/auth/login | sed 's/^/H429 /' && sed 's/^/B429 /' /tmp/b429 && echo"
FUNCIONAL+=" && sleep 0.3 && nginx -s quit; sleep 0.3"
salida="$(tar -C "$DIR" -c default.conf snippets | docker run --rm -i --add-host api:127.0.0.1 nginx:stable-alpine sh -c "$FUNCIONAL" 2>&1 | tr -d '\r' || true)"
if grep -q '"uri":"/index.html"' <<< "$salida"; then ok "funcional: /restablecer/<token> queda en el log como /index.html"; else falla "funcional: no apareció la línea de /restablecer/ en el access log"; fi
if grep -q "$TOKEN" <<< "$salida"; then falla "funcional: el token de /restablecer/ aparece en el log"; else ok "funcional: el token de /restablecer/ no aparece en el log"; fi
if grep -q "$BUSQUEDA" <<< "$salida"; then falla "funcional: el parámetro q aparece en el log"; else ok "funcional: el parámetro q no aparece en el log (ni del SPA ni de /api/)"; fi
if grep -qi '^HDR Referrer-Policy: no-referrer$' <<< "$salida"; then ok "funcional: /restablecer/<token> responde con Referrer-Policy no-referrer"; else falla "funcional: /restablecer/<token> sin Referrer-Policy no-referrer"; fi
n429="$(grep -c '^CODE 429$' <<< "$salida" || true)"
npass="$(grep -c '^CODE 502$' <<< "$salida" || true)"
if [ "$n429" -ge 1 ] && [ "$npass" -ge 31 ]; then ok "funcional: 45 POST a /auth/login: $npass pasan (burst 30) y $n429 reciben 429"; else falla "funcional: ráfaga a /auth/login con $npass pasados y $n429 con 429 (se esperaba >= 31 y >= 1)"; fi
if grep -Fq 'B429 {"error":{"code":"rate_limited","message":"Demasiados intentos. Espera un momento."}}' <<< "$salida"; then ok "funcional: el 429 de Nginx lleva el envelope"; else falla "funcional: el 429 de Nginx no lleva el envelope"; fi
if grep -qi '^H429 Retry-After: 60$' <<< "$salida" && grep -qi '^H429 Content-Type: application/json' <<< "$salida"; then ok "funcional: el 429 lleva Retry-After 60 y application/json"; else falla "funcional: el 429 sin Retry-After 60 o sin application/json"; fi
if grep -qi '^H429 Cache-Control: no-store$' <<< "$salida"; then ok "funcional: el 429 lleva Cache-Control no-store"; else falla "funcional: el 429 sin Cache-Control no-store"; fi

if grep -q '^BIG 413$' <<< "$salida"; then ok "funcional: 20 KB a /api/v1/auth/ devuelve 413 sin llegar al api (L-12)"; else falla "funcional: 20 KB a /api/v1/auth/ respondió '$(grep '^BIG' <<< "$salida" || true)' (se esperaba 413)"; fi

echo "test_nginx_conf: $fallas fallas"
[ "$fallas" -eq 0 ]
