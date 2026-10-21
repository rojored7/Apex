#!/usr/bin/env bash
# test_nginx_conf.sh
#
# Prueba de infra/nginx/default.conf (US-006, T1): `nginx -t` dentro de la imagen
# oficial (la configuración entra por stdin para no depender de bind mounts en Git
# Bash) y presencia de las directivas que fijan el contrato: 5 MB de cuerpo,
# server_tokens off, X-Forwarded-For sobrescrito con $remote_addr, proxy a api:8000
# sin URI, fallback del SPA y log sin query strings.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
CONF="$ROOT/infra/nginx/default.conf"
fallas=0
ok() { echo "  ok   $1"; }
falla() { echo "  FALLA $1"; fallas=$((fallas + 1)); }

[ -f "$CONF" ] || { echo "  FALLA no existe infra/nginx/default.conf"; exit 1; }

if docker run --rm -i --add-host api:127.0.0.1 nginx:stable-alpine \
  sh -c 'cat > /etc/nginx/conf.d/default.conf && nginx -t' < "$CONF" > /dev/null 2>&1; then
  ok "nginx -t acepta la configuración"
else
  falla "nginx -t rechaza la configuración"
  docker run --rm -i --add-host api:127.0.0.1 nginx:stable-alpine sh -c 'cat > /etc/nginx/conf.d/default.conf && nginx -t' < "$CONF" 2>&1 | tail -5 || true
fi

directiva() {
  if grep -Eq "$1" "$CONF"; then ok "$2"; else falla "$2"; fi
}
directiva '^\s*client_max_body_size\s+5m;' "client_max_body_size 5m"
directiva '^\s*server_tokens\s+off;' "server_tokens off"
directiva '^\s*proxy_set_header\s+X-Forwarded-For\s+\$remote_addr;' "X-Forwarded-For sobrescrito con \$remote_addr"
directiva '^\s*proxy_set_header\s+X-Request-ID\s+\$request_id;' "X-Request-ID propagado"
directiva '^\s*proxy_pass\s+http://api:8000;' "proxy_pass a api:8000 sin URI (conserva /api/v1/...)"
directiva 'try_files\s+\$uri\s+\$uri/\s+/index\.html;' "fallback del SPA a index.html"
directiva '^\s*log_format\s+apex' "log_format apex propio"
if grep -Eq '\$args|\$request_uri|\$http_authorization|\$http_cookie' "$CONF"; then falla "el log no debe incluir query strings ni cabeceras con tokens"; else ok "log sin query strings ni cabeceras sensibles"; fi
if grep -Eq 'proxy_add_x_forwarded_for' "$CONF"; then falla "proxy_add_x_forwarded_for concatenaría la IP del cliente"; else ok "sin proxy_add_x_forwarded_for"; fi

echo "test_nginx_conf: $fallas fallas"
[ "$fallas" -eq 0 ]
