#!/usr/bin/env bash
# athletes-smoke.sh
#
# Humo del módulo `athletes` (Sprint 9, S9-V3) sobre el stack real de prod-smoke: la llave de cifrado de
# `athlete.metric` nace con el arranque del api (sin init-keys), el alta de una medida exige la
# autorización de datos del socio, el valor solo se ve con `reveal`, la base guarda blobs `apx1.`, una
# medida anulada no impide rotar la llave y el `reveal` sigue sirviendo después de la rotación.
#
# Lo llama prod-smoke.sh después del cambio de contraseña del admin. Variables obligatorias:
#   DC (comando compose del humo, como en test_db_roles.sh), ATHLETES_SMOKE_ADMIN_EMAIL,
#   ATHLETES_SMOKE_ADMIN_PASSWORD, ATHLETES_SMOKE_BASE (por ejemplo http://127.0.0.1:8380),
#   ATHLETES_SMOKE_ORIGIN (por ejemplo http://localhost:8380).
# Opcionales: ATHLETES_SMOKE_CA (raíz de la CA, con --tls), OPS_ENV_FILE (POSTGRES_USER y POSTGRES_DB).
# Ningún token, contraseña ni valor revelado se imprime: los cuerpos y la cabecera viajan por archivos
# 600 en un directorio temporal propio y la cabecera Authorization por `-H @archivo`.
set -uo pipefail

: "${DC:?athletes-smoke: falta DC}"
: "${ATHLETES_SMOKE_ADMIN_EMAIL:?athletes-smoke: falta ATHLETES_SMOKE_ADMIN_EMAIL}"
: "${ATHLETES_SMOKE_ADMIN_PASSWORD:?athletes-smoke: falta ATHLETES_SMOKE_ADMIN_PASSWORD}"
: "${ATHLETES_SMOKE_BASE:?athletes-smoke: falta ATHLETES_SMOKE_BASE}"
: "${ATHLETES_SMOKE_ORIGIN:?athletes-smoke: falta ATHLETES_SMOKE_ORIGIN}"

OPS_ENV_FILE="${OPS_ENV_FILE:-.env.ops}"
valor() { if [ -f "$OPS_ENV_FILE" ]; then grep -E "^$1=" "$OPS_ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '\r' || true; fi; }
SUPER="$(valor POSTGRES_USER)"; [ -n "$SUPER" ] || SUPER=apex
BASE="$(valor POSTGRES_DB)"; [ -n "$BASE" ] || BASE=apex

fallas=0
ok() { printf '  ok   %s\n' "$1"; }
falla() { printf '  FALLA %s\n' "$1" >&2; fallas=$((fallas + 1)); }

T="$(mktemp -d)"
chmod 700 "$T"
trap 'rm -rf "$T"' EXIT
umask 077

CURL_CA=()
[ -z "${ATHLETES_SMOKE_CA:-}" ] || CURL_CA=(--cacert "$ATHLETES_SMOKE_CA")

# sql <consulta>: una sola celda, como el propietario del clúster por el socket local de `db`.
sql() { $DC exec -T db psql -X -At -v ON_ERROR_STOP=1 -U "$SUPER" -d "$BASE" -c "$1" 2> /dev/null | tr -d '\r' || true; }

# http <MÉTODO> <ruta> [archivo-cuerpo]: imprime el código; el cuerpo queda en $T/resp.
http() {
  local args=(-sS ${CURL_CA[@]+"${CURL_CA[@]}"} --max-time 60 -o "$T/resp" -w '%{http_code}' -X "$1" -H "Origin: $ATHLETES_SMOKE_ORIGIN")
  [ ! -f "$T/auth" ] || args+=(-H "@$T/auth")
  [ -z "${3:-}" ] || args+=(-H 'Content-Type: application/json' --data-binary "@$3")
  curl "${args[@]}" "$ATHLETES_SMOKE_BASE$2" 2> /dev/null | tr -d '\r' || true
}
# cuerpo <nombre> <json>: escribe el JSON en un archivo 600 y devuelve su ruta.
cuerpo() { printf '%s' "$2" > "$T/$1.json"; printf '%s' "$T/$1.json"; }
id_de() { sed -n 's/.*"id" *: *"\([0-9a-f-]\{36\}\)".*/\1/p' "$T/resp" | head -1; }
doc_aleatorio() { printf '9%09d' $(( (RANDOM * 32768 + RANDOM) % 1000000000 )); }

echo "athletes-smoke: base $BASE"

# --- 1. la llave de la clase nace con el arranque del api, sin init-keys --------------------------------------------
ACTIVAS="$(sql "SELECT count(*) FROM crypto.crypto_keys WHERE data_class = 'athlete.metric' AND purpose = 'encrypt' AND state = 'active'")"
if [ "$ACTIVAS" = "1" ]; then ok "athlete.metric: una fila encrypt activa en crypto_keys tras el primer arranque (sin init-keys)"; else falla "athlete.metric: filas encrypt activas = '$ACTIVAS' (se esperaba 1)"; fi

# --- 2. sesión del admin ---------------------------------------------------------------------------------------------
printf '{"email":"%s","password":"%s"}' "$ATHLETES_SMOKE_ADMIN_EMAIL" "$ATHLETES_SMOKE_ADMIN_PASSWORD" > "$T/login.json"
codigo="$(http POST /api/v1/auth/login "$T/login.json")"
TOKEN="$(sed -n 's/.*"access_token" *: *"\([^"]*\)".*/\1/p' "$T/resp" | head -1)"
rm -f "$T/login.json"
if [ "$codigo" = "200" ] && [ -n "$TOKEN" ]; then
  printf 'Authorization: Bearer %s\n' "$TOKEN" > "$T/auth"
  ok "login del admin"
else
  falla "login del admin respondió '$codigo'"
  echo "athletes-smoke: $fallas fallas"; exit 1
fi
unset TOKEN

# --- 3. dos socios: con y sin autorización de datos ------------------------------------------------------------------
SUFIJO="$(date +%s)"
codigo="$(http POST /api/v1/members "$(cuerpo m1 "{\"first_name\":\"Atleta\",\"last_name\":\"Humo$SUFIJO\",\"document_type\":\"CC\",\"document\":\"$(doc_aleatorio)\",\"data_consent\":true}")")"
CON="$(id_de)"
if [ "$codigo" = "201" ] && [ -n "$CON" ]; then ok "socio con autorización de datos creado"; else falla "POST /members con autorización respondió '$codigo'"; fi
codigo="$(http POST /api/v1/members "$(cuerpo m2 "{\"first_name\":\"Atleta\",\"last_name\":\"Sin$SUFIJO\",\"document_type\":\"CC\",\"document\":\"$(doc_aleatorio)\",\"data_consent\":false}")")"
SIN="$(id_de)"
if [ "$codigo" = "201" ] && [ -n "$SIN" ]; then ok "socio sin autorización de datos creado"; else falla "POST /members sin autorización respondió '$codigo'"; fi
if [ -z "$CON" ] || [ -z "$SIN" ]; then echo "athletes-smoke: $fallas fallas"; exit 1; fi

HOY="$(date -u -d "@$(( $(date +%s) - 86400 ))" +%F)"
NOTA="nota-humo-$SUFIJO"

# --- 4. alta de la medida: 201 con autorización, 409 consent_required sin ella ---------------------------------------
codigo="$(http POST "/api/v1/athletes/$CON/metrics" "$(cuerpo met "{\"measured_on\":\"$HOY\",\"weight_g\":82500,\"height_cm\":175,\"body_fat_pct\":18,\"notes\":\"$NOTA\"}")")"
METRIC="$(id_de)"
if [ "$codigo" = "201" ] && [ -n "$METRIC" ]; then ok "alta de una medida con autorización: 201"; else falla "alta de la medida respondió '$codigo'"; fi
codigo="$(http POST "/api/v1/athletes/$SIN/metrics" "$T/met.json")"
if [ "$codigo" = "409" ] && grep -q 'consent_required' "$T/resp"; then ok "alta sin autorización de datos: 409 consent_required"; else falla "alta sin autorización respondió '$codigo'"; fi
FILAS_SIN="$(sql "SELECT count(*) FROM athletes.body_metrics WHERE member_id = '$SIN'")"
if [ "$FILAS_SIN" = "0" ]; then ok "el socio sin autorización no tiene filas en athletes.body_metrics"; else falla "el socio sin autorización tiene '$FILAS_SIN' filas"; fi

# --- 5. reveal: valor correcto sin imprimirlo ------------------------------------------------------------------------
revela() { # <campo> <regex del valor esperado>: 200 y el valor esperado, sin imprimir nada
  local c
  c="$(http POST "/api/v1/athletes/$CON/metrics/$METRIC/reveal" "$(cuerpo rev "{\"field\":\"$1\"}")")"
  [ "$c" = "200" ] && grep -Eq "\"value\" *: *$2" "$T/resp"
}
if revela weight_g '82500 *[,}]'; then ok "reveal de weight_g devuelve el valor guardado"; else falla "reveal de weight_g sin el valor esperado"; fi
if revela notes "\"$NOTA\""; then ok "reveal de notes devuelve el texto guardado"; else falla "reveal de notes sin el texto esperado"; fi

# --- 6. en la base solo hay blobs apx1 y ningún valor en claro --------------------------------------------------------
BLOBS="$(sql "SELECT count(*) FROM athletes.body_metrics WHERE id = '$METRIC' AND left(weight_g::text, 5) = 'apx1.' AND left(height_cm::text, 5) = 'apx1.' AND left(body_fat_pct::text, 5) = 'apx1.' AND left(notes::text, 5) = 'apx1.'")"
if [ "$BLOBS" = "1" ]; then ok "las cuatro columnas cifradas empiezan por apx1."; else falla "columnas cifradas sin el formato apx1. (filas='$BLOBS')"; fi
CLARO="$(sql "SELECT count(*) FROM athletes.body_metrics WHERE id = '$METRIC' AND (notes::text LIKE '%$NOTA%' OR weight_g::text LIKE '%82500%')")"
if [ "$CLARO" = "0" ]; then ok "ningún valor en claro en athletes.body_metrics"; else falla "hay valores en claro en athletes.body_metrics"; fi

# --- 7. anular una medida ---------------------------------------------------------------------------------------------
codigo="$(http POST "/api/v1/athletes/$CON/metrics" "$(cuerpo met2 "{\"measured_on\":\"$HOY\",\"weight_g\":90000}")")"
ANULAR="$(id_de)"
if [ "$codigo" != "201" ] || [ -z "$ANULAR" ]; then falla "segunda medida respondió '$codigo'"; fi
codigo="$(http POST "/api/v1/athletes/$CON/metrics/$ANULAR/void")"
ANULADA="$(sql "SELECT count(*) FROM athletes.body_metrics WHERE id = '$ANULAR' AND voided_at IS NOT NULL AND voided_by IS NOT NULL")"
if [ "$codigo" = "200" ] && [ "$ANULADA" = "1" ]; then ok "anular una medida: 200 y voided_at/voided_by en la base"; else falla "anulación respondió '$codigo' (filas anuladas='$ANULADA')"; fi

# --- 8. rotate-key con una medida anulada, y reveal después ----------------------------------------------------------
ANTES="$(sql "SELECT id FROM crypto.crypto_keys WHERE data_class = 'athlete.metric' AND purpose = 'encrypt' AND state = 'active'")"
if $DC --profile tools run --rm -T tools rotate-key athlete.metric --reason "humo S9-V3" --as "$ATHLETES_SMOKE_ADMIN_EMAIL" > "$T/rot.log" 2>&1; then
  ok "rotate-key athlete.metric --as admin termina con 0 (hay una medida anulada)"
else
  falla "rotate-key athlete.metric falló: $(tail -3 "$T/rot.log" | tr '\n' ' ' | cut -c1-240)"
fi
DESPUES="$(sql "SELECT id FROM crypto.crypto_keys WHERE data_class = 'athlete.metric' AND purpose = 'encrypt' AND state = 'active'")"
if [ -n "$DESPUES" ] && [ "$DESPUES" != "$ANTES" ]; then ok "la llave activa cambió tras rotate-key"; else falla "la llave activa no cambió tras rotate-key"; fi
VIEJOS="$(sql "SELECT count(*) FROM athletes.body_metrics WHERE member_id = '$CON' AND weight_g::text LIKE 'apx1.${ANTES}.%'")"
if [ "$VIEJOS" = "0" ]; then ok "ningún blob de weight_g conserva la llave anterior"; else falla "'$VIEJOS' blobs de weight_g siguen con la llave anterior"; fi
if revela weight_g '82500 *[,}]'; then ok "reveal de weight_g sigue funcionando tras la rotación"; else falla "reveal de weight_g falló tras la rotación"; fi
if revela notes "\"$NOTA\""; then ok "reveal de notes sigue funcionando tras la rotación"; else falla "reveal de notes falló tras la rotación"; fi

# --- 9. nada sensible en los logs ------------------------------------------------------------------------------------
EN_LOG="$($DC logs api web 2>&1 | grep -c -F "$NOTA" || true)"
if [ "$EN_LOG" = "0" ]; then ok "el texto de la medida no aparece en los logs de api ni web"; else falla "el texto de la medida aparece '$EN_LOG' veces en los logs"; fi
if grep -qF "$NOTA" "$T/rot.log" 2> /dev/null; then falla "el texto de la medida aparece en la salida de rotate-key"; fi

echo "athletes-smoke: $fallas fallas"
[ "$fallas" -eq 0 ]
