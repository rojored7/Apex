#!/usr/bin/env bash
# openbao-smoke.sh
#
# Humo de OpenBao sobre un stack de producción YA levantado (S5-D22, S5-D103, S5-D104; W0-2).
# Lo corre prod-smoke.sh --provider openbao (job prod-smoke de la CI y proyecto apex-smoke de este
# equipo) y, a mano, el ensayo. Nunca toca los proyectos `apex` ni `apex-ensayo` salvo que DC los
# apunte a propósito. Entra con el comando de Compose completo en DC (una cadena), por ejemplo:
#   DC="docker compose -p apex-smoke --env-file S/.env --env-file S/.env.ops -f infra/compose.yml" \
#     bash scripts/ci/openbao-smoke.sh
#
# Comprueba, con un OpenBao vacío (sin inicializar):
#   1. el servicio openbao está healthy aun sin inicializar y sellado (sealedcode/uninitcode);
#   2. init 5/3 con las llaves SOLO en memoria de este proceso (nunca un archivo), desello con
#      tres por la API (wget --post-file=/dev/stdin, S5-D103);
#   3. bootstrap.sh en modo no interactivo (APEX_ENV=dev solo para este humo) crea transit,
#      apex-kek, apex-sign-audit, las políticas y los tokens, y revoca la raíz;
#   4. los tres archivos de token: modo 600 y dueño 10001, legibles solo por su servicio;
#   5. el token del api cifra y descifra con apex-kek y NO puede rotarla;
#   6. un reinicio de openbao lo deja sellado y el api sigue healthy (healthcheck tolerante, S5-D15);
#   7. tres llaves lo desellan de nuevo.
# Estado sellado del api (S5-B3, US-136; S5-D22, S5-D69, S5-D70). Solo si el api corre con
# CRYPTO_PROVIDER=openbao (overlay compose.openbao.yml; si no, lo dice y lo omite). Exige además
# OPENBAO_SMOKE_ADMIN_EMAIL y OPENBAO_SMOKE_ADMIN_PASSWORD (un admin real, para GET /members/{id}):
#   a. con openbao sellado, /health responde HTTP 503 con "crypto": "sealed";
#   b. con el api aún arriba, GET /members/{id} sigue en 200 (la DEK está en memoria);
#   c. tras `restart api worker` el api arranca sin keyring: GET /members/{id} da 503
#      crypto_unavailable, y web y worker siguen healthy;
#   d. con tres llaves el api se recupera solo (sin reiniciar) en RECUPERACION_MAX_S = 40 s o menos.
# Evidencia de cada estado, incluido el cuerpo de /health, en OPENBAO_SMOKE_EVIDENCE (por omisión
# docs/scratch/ensayo/openbao/, ignorada por git). Sale con 0 si todo está en verde.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

case "${1:-}" in
  -h|--help) sed -n '2,32p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  "") ;;
  *) echo "openbao-smoke: argumento desconocido: $1" >&2; exit 2 ;;
esac

[ -n "${DC:-}" ] || { echo "openbao-smoke: falta DC (el comando de docker compose del stack, ver --help)" >&2; exit 2; }
read -r -a COMPOSE <<< "$DC"
EVIDENCE="${OPENBAO_SMOKE_EVIDENCE:-$ROOT/docs/scratch/ensayo/openbao}"
mkdir -p "$EVIDENCE"

fallas=0
ok() { printf '  ok   %s\n' "$1"; }
falla() { printf '  FALLA %s\n' "$1" >&2; fallas=$((fallas + 1)); }
muere() { printf 'openbao-smoke: ERROR %s\n' "$1" >&2; exit 1; }
paso() { printf 'openbao-smoke: %s\n' "$*"; }

ob_exec() { "${COMPOSE[@]}" exec -T openbao "$@"; }
estado() { # <campo>: valor de /v1/sys/seal-status
  ob_exec wget -q -O - http://127.0.0.1:8200/v1/sys/seal-status | tr ',' '\n' | sed -n "s/.*\"$1\": *\"\{0,1\}\([^\",}]*\).*/\1/p"
}
salud() { # <servicio>: estado de salud del contenedor
  local id
  id="$("${COMPOSE[@]}" ps -q "$1" 2> /dev/null | head -1 | tr -d '\r')"
  [ -n "$id" ] || { echo ausente; return 0; }
  docker inspect -f '{{.State.Health.Status}}' "$id" 2> /dev/null | tr -d '\r' || echo ausente
}
espera_healthy() { # <servicio> <segundos>
  local t=0
  while [ "$t" -lt "$2" ]; do
    [ "$(salud "$1")" = healthy ] && return 0
    sleep 3
    t=$((t + 3))
  done
  return 1
}
evidencia() { # <etiqueta>: estado de openbao y del api en este momento
  {
    printf 'openbao seal-status: '
    ob_exec wget -q -O - http://127.0.0.1:8200/v1/sys/seal-status || true
    printf '\nsalud openbao=%s api=%s\n' "$(salud openbao)" "$(salud api)"
  } > "$EVIDENCE/$1.txt" 2>&1 || true
}
evidencia_health() { # <etiqueta>: guarda en $EVIDENCE el cuerpo de /health del api (HEALTH_CUERPO)
  printf '%s\n' "$HEALTH_CUERPO" > "$EVIDENCE/$1-health.json"
}
# api_http <método> <ruta> [token]: "<código> <cuerpo>" desde DENTRO del api (stdlib, sin curl). El
# login toma el correo y la clave del entorno del contenedor (-e), nunca de argv.
API_HTTP='import json, os, sys, urllib.error, urllib.request
metodo, ruta = sys.argv[1], sys.argv[2]
token = sys.argv[3] if len(sys.argv) > 3 else ""
cuerpo = None
if ruta == "/api/v1/auth/login":
    cuerpo = json.dumps({"email": os.environ["SMOKE_EMAIL"], "password": os.environ["SMOKE_PASS"]}).encode()
cab = {"Content-Type": "application/json"}
if token:
    cab["Authorization"] = "Bearer " + token
r = urllib.request.Request("http://127.0.0.1:8000" + ruta, data=cuerpo, method=metodo, headers=cab)
try:
    x = urllib.request.urlopen(r, timeout=10)
    estado, texto = x.status, x.read().decode()
except urllib.error.HTTPError as e:
    estado, texto = e.code, e.read().decode()
print(estado, texto)'
api_http() {
  SMOKE_EMAIL="${OPENBAO_SMOKE_ADMIN_EMAIL:-}" SMOKE_PASS="${OPENBAO_SMOKE_ADMIN_PASSWORD:-}" \
    "${COMPOSE[@]}" exec -T -e SMOKE_EMAIL -e SMOKE_PASS api python -c "$API_HTTP" "$@" 2> /dev/null | tr -d '\r' || true
}
# sesion_admin: access token del admin (el login no usa el bus: funciona también sellado).
sesion_admin() { api_http POST /api/v1/auth/login | sed -n 's/^200 .*"access_token": *"\([^"]*\)".*/\1/p'; }
# socio_de <token>: id del primer socio de la lista (la lista no descifra nada).
socio_de() { api_http GET '/api/v1/members?limit=1' "$1" | grep -o '"id": *"[0-9a-f-]\{36\}"' | head -1 | grep -o '[0-9a-f-]\{36\}'; }
# espera_health <código> <crypto> <segundos>: espera /health del api con ese código HTTP y ese crypto.
espera_health() {
  local t=0
  while [ "$t" -le "$3" ]; do
    HEALTH_CUERPO="$(api_http GET /health)"
    case "$HEALTH_CUERPO" in
      "$1 "*"\"crypto\": \"$2\""* | "$1 "*"\"crypto\":\"$2\""*) return 0 ;;
    esac
    sleep 2
    t=$((t + 2))
  done
  return 1
}
# unseal_con <llaves>: envía cada llave (una por línea) a sys/unseal por stdin; nunca por argumento.
unseal_con() {
  local k
  while IFS= read -r k; do
    printf '{"key":"%s"}' "$k" | ob_exec wget -q -O /dev/null --header 'Content-Type: application/json' --post-file=/dev/stdin http://127.0.0.1:8200/v1/sys/unseal
  done <<< "$1"
}

# --- 1. sin inicializar ----------------------------------------------------------------------
paso "openbao vacío"
"${COMPOSE[@]}" up -d openbao > /dev/null
espera_healthy openbao 90 && ok "openbao healthy sin inicializar (sealedcode=200, uninitcode=200)" || muere "openbao no llegó a healthy"
[ "$(estado initialized)" = "false" ] && ok "openbao sin inicializar al empezar" || muere "openbao ya estaba inicializado: use un proyecto con volúmenes nuevos"
evidencia 1-vacio

# --- 2. init 5/3 en memoria y desello con tres --------------------------------------------------
paso "init 5/3 y desello"
INIT_OUT="$(ob_exec bao operator init -key-shares=5 -key-threshold=3 | tr -d '\r')"
LLAVES="$(printf '%s\n' "$INIT_OUT" | sed -n 's/^Unseal Key [0-9]*: //p')"
BAO_TOKEN="$(printf '%s\n' "$INIT_OUT" | sed -n 's/^Initial Root Token: //p')"
INIT_OUT=""
[ "$(printf '%s\n' "$LLAVES" | grep -c .)" = "5" ] && ok "init devolvió 5 llaves" || muere "init no devolvió 5 llaves"
unseal_con "$(printf '%s\n' "$LLAVES" | sed -n '1,3p')"
[ "$(estado sealed)" = "false" ] && ok "desellado con 3 de 5 por sys/unseal (stdin)" || muere "sigue sellado tras tres llaves"
[ "$(estado t)" = "3" ] && [ "$(estado n)" = "5" ] && ok "umbral 3 de 5" || falla "el umbral no es 3 de 5"
evidencia 2-desellado

# --- 3. bootstrap no interactivo ---------------------------------------------------------------
# La raíz viaja por el ENTORNO del cliente (-e BAO_TOKEN sin valor): no queda en argv ni en archivos.
paso "bootstrap.sh"
if BAO_TOKEN="$BAO_TOKEN" "${COMPOSE[@]}" --profile bootstrap run --rm -T -e BAO_TOKEN -e BOOTSTRAP_NONINTERACTIVE=1 -e APEX_ENV=dev openbao-bootstrap --first-install; then
  ok "bootstrap.sh --first-install (transit, apex-kek, apex-sign-audit, políticas, tokens, raíz revocada)"
else
  muere "bootstrap.sh falló"
fi
BAO_TOKEN=""

# --- 4. archivos de token: 600 y dueño 10001 --------------------------------------------------------
paso "tokens"
for quien in api worker tools; do
  perm="$("${COMPOSE[@]}" run --rm -T --no-deps --entrypoint stat "$quien" -c '%a %u' /run/apex/openbao/token 2> /dev/null | tr -d '\r' | tail -1 || true)"
  [ "$perm" = "600 10001" ] && ok "token de $quien: modo 600, dueño 10001" || falla "token de $quien: '$perm' (se esperaba '600 10001')"
done

# --- 5. el token del api cifra y descifra, no rota -----------------------------------------------------
# La imagen del api no trae la CLI de OpenBao: se prueba por la API con python (stdlib).
PRUEBA='import json, sys, urllib.request, urllib.error
t = open("/run/apex/openbao/token").read().strip()
def llamar(ruta, cuerpo=None):
    r = urllib.request.Request("http://openbao:8200/v1/" + ruta, data=json.dumps(cuerpo or {}).encode(), method="PUT", headers={"X-Vault-Token": t, "Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(r, timeout=5))
    except urllib.error.HTTPError as e:
        return {"http": e.code}
c = llamar("transit/encrypt/apex-kek", {"plaintext": "aG9sYQ=="})["data"]["ciphertext"]
p = llamar("transit/decrypt/apex-kek", {"ciphertext": c})["data"]["plaintext"]
print("cifra-descifra", "ok" if p == "aG9sYQ==" else "mal")
print("rotar", llamar("transit/keys/apex-kek/rotate").get("http"))'
RES="$("${COMPOSE[@]}" run --rm -T --no-deps --entrypoint python api -c "$PRUEBA" 2> /dev/null | tr -d '\r' || true)"
case "$RES" in *"cifra-descifra ok"*) ok "el token del api cifra y descifra con apex-kek" ;; *) falla "el token del api no cifra/descifra: $RES" ;; esac
case "$RES" in *"rotar 403"*) ok "el token del api NO puede rotar apex-kek (403)" ;; *) falla "el token del api pudo rotar o falló distinto: $RES" ;; esac

# --- 6. reinicio de openbao: sellado --------------------------------------------------------------------
# El estado sellado del api solo se prueba si el api corre con CRYPTO_PROVIDER=openbao.
API_OPENBAO=0
if [ "$("${COMPOSE[@]}" exec -T api printenv CRYPTO_PROVIDER 2> /dev/null | tr -d '\r')" = "openbao" ]; then
  if [ -n "${OPENBAO_SMOKE_ADMIN_EMAIL:-}" ] && [ -n "${OPENBAO_SMOKE_ADMIN_PASSWORD:-}" ]; then
    API_OPENBAO=1
  elif [ -n "${CI:-}" ]; then
    # S5-B3 (revisión, L7): en la CI faltar el admin del humo es una FALLA, no una omisión silenciosa.
    falla "CI definida: faltan OPENBAO_SMOKE_ADMIN_EMAIL y OPENBAO_SMOKE_ADMIN_PASSWORD para probar el estado sellado"
  fi
fi
RECUPERACION_MAX_S=40
if [ "$API_OPENBAO" = 1 ]; then
  TOKEN="$(sesion_admin)"
  [ -n "$TOKEN" ] || muere "no se pudo iniciar sesión como admin para probar GET /members/{id}"
  SOCIO="$(socio_de "$TOKEN")"
  [ -n "$SOCIO" ] || muere "no hay socios para probar GET /members/{id} (¿seed --demo?)"
  [ "$(api_http GET "/api/v1/members/$SOCIO" "$TOKEN" | cut -d' ' -f1)" = 200 ] && ok "GET /members/{id} responde 200 con openbao desellado" || falla "GET /members/{id} no responde 200 antes del sellado"
fi
paso "reinicio de openbao"
"${COMPOSE[@]}" restart openbao > /dev/null
espera_healthy openbao 90 || muere "openbao no volvió a healthy tras el reinicio"
[ "$(estado sealed)" = "true" ] && ok "openbao queda sellado tras el reinicio" || falla "openbao no quedó sellado tras el reinicio"
if [ "$API_OPENBAO" = 1 ]; then
  if espera_health 503 sealed 30; then
    ok "/health responde HTTP 503 con crypto sealed (openbao sellado, api arriba)"
  else
    falla "/health no dio 503 con crypto sealed: $(printf '%s' "$HEALTH_CUERPO" | cut -c1-200)"
  fi
  evidencia_health 3-sellado-api-arriba
  [ "$(salud api)" = healthy ] && ok "el api sigue healthy con openbao sellado (S5-D15)" || falla "el api dejó de estar healthy con openbao sellado"
  [ "$(api_http GET "/api/v1/members/$SOCIO" "$TOKEN" | cut -d' ' -f1)" = 200 ] && ok "GET /members/{id} sigue en 200 mientras el api conserva las DEK en memoria" || falla "GET /members/{id} dejó de responder 200 con el api arriba"
  # D69: reiniciar api y worker con openbao sellado. El api arranca sin keyring; web y worker no caen.
  paso "reinicio del api y el worker con openbao sellado"
  "${COMPOSE[@]}" restart api worker > /dev/null
  espera_healthy api 120 || falla "el api no volvió a healthy sellado"
  espera_healthy worker 150 || falla "el worker no volvió a healthy sellado"
  TOKEN="$(sesion_admin)"
  [ -n "$TOKEN" ] && ok "el login funciona con el api sellado (no usa el bus)" || falla "el login falló con el api sellado"
  RESPUESTA="$(api_http GET "/api/v1/members/$SOCIO" "$TOKEN")"
  case "$RESPUESTA" in
    "503 "*crypto_unavailable*) ok "GET /members/{id} responde 503 crypto_unavailable con el api reiniciado y sellado" ;;
    *) falla "GET /members/{id} no dio 503 crypto_unavailable: $(printf '%s' "$RESPUESTA" | cut -c1-200)" ;;
  esac
  [ "$(salud web)" = healthy ] && ok "web sigue healthy con openbao sellado" || falla "web dejó de estar healthy con openbao sellado"
  [ "$(salud worker)" = healthy ] && ok "worker sigue healthy con openbao sellado (sin abortar)" || falla "worker dejó de estar healthy con openbao sellado"
  espera_health 503 sealed 30 || true
  evidencia_health 4-sellado-api-reiniciado
else
  echo "  omitida: el estado sellado del api exige CRYPTO_PROVIDER=openbao y OPENBAO_SMOKE_ADMIN_EMAIL/OPENBAO_SMOKE_ADMIN_PASSWORD" >&2
  sleep 20
  [ "$(salud api)" = healthy ] && ok "el api sigue healthy con openbao sellado (S5-D15)" || falla "el api dejó de estar healthy con openbao sellado"
fi
evidencia 3-sellado

# --- 7. desello con tres llaves y recuperación del api en <= 40 s --------------------------------------------
paso "desello tras el reinicio"
unseal_con "$(printf '%s\n' "$LLAVES" | sed -n '3,5p')"
LLAVES=""
[ "$(estado sealed)" = "false" ] && ok "openbao desellado con otras tres llaves (3, 4 y 5)" || falla "no se desselló con las llaves 3, 4 y 5"
if [ "$API_OPENBAO" = 1 ]; then
  INICIO="$SECONDS"
  if espera_health 200 ok "$RECUPERACION_MAX_S"; then
    ok "el api se recuperó sin reiniciar: /health 200 con crypto ok en $((SECONDS - INICIO)) s (máximo ${RECUPERACION_MAX_S} s)"
  else
    falla "el api no se recuperó en ${RECUPERACION_MAX_S} s: $(printf '%s' "$HEALTH_CUERPO" | cut -c1-200)"
  fi
  evidencia_health 5-recuperado
  # Revisión L7 (a): tras el desello el worker corre un job a mano y sale con 0.
  if "${COMPOSE[@]}" run --rm -T worker python -m app.worker.main --run-once expirations > /dev/null 2>&1; then
    ok "worker --run-once expirations sale con 0 tras el desello"
  else
    falla "worker --run-once expirations no salió con 0 tras el desello"
  fi
  TOKEN="$(sesion_admin)"
  [ "$(api_http GET "/api/v1/members/$SOCIO" "$TOKEN" | cut -d' ' -f1)" = 200 ] && ok "GET /members/{id} vuelve a responder 200 tras el desello" || falla "GET /members/{id} no volvió a 200 tras el desello"
fi
evidencia 4-desellado-otra-vez

if [ "$fallas" -ne 0 ]; then
  echo "openbao-smoke: $fallas fallas" >&2
  exit 1
fi
echo "openbao-smoke: todo en verde (evidencia en ${EVIDENCE#"$ROOT"/})"
