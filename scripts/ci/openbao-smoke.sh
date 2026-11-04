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
# Lo que depende del proveedor en el api (migrate-provider, /health.crypto = sealed, el 503
# crypto_unavailable de GET /members/{id}, la recuperación en <= 40 s) llega con B1 y B2.
# Evidencia de cada estado en OPENBAO_SMOKE_EVIDENCE (por omisión docs/scratch/ensayo/openbao/,
# ignorada por git). Sale con 0 si todo está en verde.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

case "${1:-}" in
  -h|--help) sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
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

# --- 6. reinicio: sellado, y el api sigue healthy ------------------------------------------------------
paso "reinicio de openbao"
"${COMPOSE[@]}" restart openbao > /dev/null
espera_healthy openbao 90 || muere "openbao no volvió a healthy tras el reinicio"
[ "$(estado sealed)" = "true" ] && ok "openbao queda sellado tras el reinicio" || falla "openbao no quedó sellado tras el reinicio"
sleep 20
[ "$(salud api)" = healthy ] && ok "el api sigue healthy con openbao sellado (S5-D15)" || falla "el api dejó de estar healthy con openbao sellado"
evidencia 3-sellado

# --- 7. desello otra vez ---------------------------------------------------------------------------------
paso "desello tras el reinicio"
unseal_con "$(printf '%s\n' "$LLAVES" | sed -n '3,5p')"
LLAVES=""
[ "$(estado sealed)" = "false" ] && ok "openbao desellado con otras tres llaves (3, 4 y 5)" || falla "no se desselló con las llaves 3, 4 y 5"
evidencia 4-desellado-otra-vez

if [ "$fallas" -ne 0 ]; then
  echo "openbao-smoke: $fallas fallas" >&2
  exit 1
fi
echo "openbao-smoke: todo en verde (evidencia en ${EVIDENCE#"$ROOT"/})"
