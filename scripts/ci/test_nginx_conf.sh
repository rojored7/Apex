#!/usr/bin/env bash
# test_nginx_conf.sh
#
# Prueba de infra/nginx/ (US-006 T1, US-038 T9): `nginx -t` dentro de la imagen
# oficial (default.conf y snippets/ entran por un tar en stdin para no depender de bind
# mounts en Git Bash) y presencia de las directivas que fijan el contrato: 5 MB de
# cuerpo, server_tokens off, X-Forwarded-For sobrescrito con $remote_addr, proxy a
# api:8000 sin URI, fallback del SPA, log sin query strings, cabeceras de seguridad en
# cada location, CSP con nonce y sin unsafe-*, sub_filter del marcador y no-store.
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

NGINX_T='mkdir -p /tmp/n && tar -x -C /tmp/n && cp /tmp/n/default.conf /etc/nginx/conf.d/default.conf && cp -r /tmp/n/snippets /etc/nginx/snippets && nginx -t'
if tar -C "$DIR" -c default.conf snippets | docker run --rm -i --add-host api:127.0.0.1 nginx:stable-alpine sh -c "$NGINX_T" > /dev/null 2>&1; then
  ok "nginx -t acepta la configuración"
else
  falla "nginx -t rechaza la configuración"
  tar -C "$DIR" -c default.conf snippets | docker run --rm -i --add-host api:127.0.0.1 nginx:stable-alpine sh -c "$NGINX_T" 2>&1 | tail -5 || true
fi

directiva() { # patrón descripción (busca en default.conf y en los snippets)
  if grep -Eqh "$1" "$CONF" "$SNIP"/*.conf; then ok "$2"; else falla "$2"; fi
}
directiva '^\s*client_max_body_size\s+5m;' "client_max_body_size 5m"
directiva '^\s*server_tokens\s+off;' "server_tokens off"
directiva '^\s*proxy_set_header\s+X-Forwarded-For\s+\$remote_addr;' "X-Forwarded-For sobrescrito con \$remote_addr"
directiva '^\s*proxy_set_header\s+X-Request-ID\s+\$request_id;' "X-Request-ID propagado"
directiva '^\s*proxy_pass\s+http://api:8000;' "proxy_pass a api:8000 sin URI (conserva /api/v1/...)"
directiva 'try_files\s+\$uri\s+\$uri/\s+/index\.html;' "fallback del SPA a index.html"
directiva '^\s*log_format\s+apex' "log_format apex propio"
if grep -Eqh '\$args|\$request_uri|\$http_authorization|\$http_cookie' "$CONF" "$SNIP"/*.conf; then falla "el log no debe incluir query strings ni cabeceras con tokens"; else ok "log sin query strings ni cabeceras sensibles"; fi
if grep -Eqh 'proxy_add_x_forwarded_for' "$CONF" "$SNIP"/*.conf; then falla "proxy_add_x_forwarded_for concatenaría la IP del cliente"; else ok "sin proxy_add_x_forwarded_for"; fi

# US-038: cabeceras de seguridad.
for h in 'X-Content-Type-Options "nosniff" always' 'X-Frame-Options "DENY" always' 'Referrer-Policy "strict-origin-when-cross-origin" always' 'Permissions-Policy "camera=\(\), microphone=\(\), geolocation=\(\)" always'; do
  if grep -Eq "^\s*add_header\s+$h;" "$SNIP/security-headers.conf"; then ok "snippet: add_header $h"; else falla "snippet sin add_header $h"; fi
done
# Cada location de default.conf incluye el snippet de cabeceras (directo o vía proxy-api).
sin_include="$(awk '
  /^\s*location\b/ { loc=$0; inc=0; next }
  loc && /include\s+snippets\/(security-headers|proxy-api)\.conf;/ { inc=1 }
  loc && /^\s*}/ { if (!inc) print loc; loc="" }
' "$CONF")"
if [ -z "$sin_include" ]; then ok "todos los location incluyen snippets/security-headers.conf"; else falla "location sin cabeceras de seguridad:$sin_include"; fi
grep -q 'include snippets/security-headers.conf;' "$SNIP/proxy-api.conf" && ok "proxy-api.conf incluye las cabeceras" || falla "proxy-api.conf no incluye security-headers.conf"
directiva "add_header Content-Security-Policy \"default-src 'self'; script-src 'self' 'nonce-\\\$request_id'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'\" always;" "CSP del HTML exacta con nonce-\$request_id"
directiva "add_header Content-Security-Policy \"default-src 'none'; frame-ancestors 'none'\" always;" "CSP mínima en /api/"
if grep -Eqh "unsafe-inline|unsafe-eval" "$CONF" "$SNIP"/*.conf; then falla "la CSP no debe contener unsafe-inline ni unsafe-eval"; else ok "sin unsafe-inline ni unsafe-eval"; fi
directiva "^\s*sub_filter\s+'__CSP_NONCE__'\s+'\\\$request_id';" "sub_filter del marcador __CSP_NONCE__"
directiva '^\s*sub_filter_once\s+off;' "sub_filter_once off"
directiva 'add_header Cache-Control "no-store" always;' "index.html con Cache-Control no-store"
if grep -Eq 'gzip_static\s+on' "$CONF"; then falla "gzip_static on rompería sub_filter"; else ok "sin gzip_static"; fi
if grep -q 'location /api/v1/tv/' "$CONF"; then ok "location /api/v1/tv/ preparado (N-44)"; else falla "falta location /api/v1/tv/ (N-44)"; fi
if grep -q 'COPY infra/nginx/snippets/' "$ROOT/web/Dockerfile"; then ok "web/Dockerfile copia los snippets"; else falla "web/Dockerfile no copia infra/nginx/snippets/"; fi

echo "test_nginx_conf: $fallas fallas"
[ "$fallas" -eq 0 ]
