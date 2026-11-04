#!/bin/sh
# bootstrap.sh [--first-install | --reissue-tokens]
#
# Instalación y operación de OpenBao (S5-D10, D11, D76, D103, D104, D106; M-1, M-2). Corre DENTRO
# de la imagen de OpenBao (busybox ash: sin bash, sin jq), como servicio `openbao-bootstrap` del
# perfil `bootstrap`, siempre interactivo y sin log del contenedor (logging none):
#
#   docker compose --env-file .env --env-file .env.ops -f infra/compose.yml \
#     --profile bootstrap run --rm openbao-bootstrap --first-install
#
# Sin opciones: si OpenBao está inicializado y sellado, lo desella pidiendo tres llaves; si está
# inicializado y desellado no hace nada; si el volumen está vacío ABORTA (restaurar un snapshot).
# --first-install: volumen vacío. Pide escribir INICIALIZAR, inicializa 5 llaves con umbral 3,
#   MUESTRA LAS 5 LLAVES SOLO POR LA TERMINAL, UNA VEZ (nunca a un archivo, nunca al log), desella
#   con tres, habilita transit, crea apex-kek y apex-sign-audit, escribe las políticas, emite los
#   tokens y revoca la raíz.
# --reissue-tokens: reemite los tokens (rotación cada 90 días o tras un incidente). Pide tres
#   llaves de desello para generar una raíz temporal, que se revoca al terminar; los tokens
#   anteriores de apex-api, apex-worker y apex-tools se revocan después de emitir los nuevos.
#
# Las llaves de desello se leen con `read -rs` y viajan por stdin hasta la API (sys/unseal con
# wget --post-file=/dev/stdin): nunca por argumento, ni en una variable exportada, ni en un
# archivo. La raíz inicial nunca se imprime ni se guarda. El modo no interactivo existe SOLO para
# el entrypoint de desarrollo y se niega fuera de APEX_ENV=dev.
set -euo pipefail
umask 077

export BAO_ADDR="${BAO_ADDR:-http://openbao:8200}"
TOKENS_DIR="${BOOTSTRAP_TOKENS_DIR:-/tokens}"
POLICIES_DIR="${BOOTSTRAP_POLICIES_DIR:-/policies}"

MODE=normal
case "${1:-}" in
  "") ;;
  --first-install) MODE=first ;;
  --reissue-tokens) MODE=reissue ;;
  -h|--help) sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "bootstrap: opción desconocida (use --first-install o --reissue-tokens)" >&2; exit 2 ;;
esac

die() { echo "bootstrap: ERROR $*" >&2; exit 1; }
info() { echo "bootstrap: $*" >&2; }

NONINTERACTIVE=0
if [ -n "${BOOTSTRAP_NONINTERACTIVE:-}" ]; then
  [ "${APEX_ENV:-}" = "dev" ] || die "el modo no interactivo es solo de desarrollo (APEX_ENV=dev)"
  NONINTERACTIVE=1
fi

# --- utilidades -----------------------------------------------------------------------------
ATTEMPT_OPEN=0
limpiar() {
  # Si una generación de raíz quedó a medias, se cancela; el resto no deja nada que borrar.
  if [ "$ATTEMPT_OPEN" = 1 ]; then BAO_TOKEN="" bao delete sys/generate-root/attempt > /dev/null 2>&1 || true; fi
  # M2: si el script muere con una raíz (inicial o temporal) en el entorno, no queda viva.
  if [ -n "${BAO_TOKEN:-}" ]; then bao token revoke -self > /dev/null 2>&1 || true; fi
}
trap limpiar EXIT

esperar_api() {
  n=0
  until wget -q -O /dev/null "$BAO_ADDR/v1/sys/health?sealedcode=200&uninitcode=200" 2> /dev/null; do
    n=$((n + 1))
    [ "$n" -le 60 ] || die "OpenBao no responde en $BAO_ADDR (¿está en marcha el servicio openbao?)"
    sleep 2
  done
}

# estado <campo>: valor de un campo de /v1/sys/seal-status (true/false o número).
estado() {
  wget -q -O - "$BAO_ADDR/v1/sys/seal-status" | tr ',' '\n' | sed -n "s/.*\"$1\": *\"\{0,1\}\([^\",}]*\).*/\1/p"
}

# unseal_stdin: envía a sys/unseal la llave que llega por stdin (S5-D103). La llave no pasa por argv.
unseal_stdin() {
  read -r K_LINE
  printf '{"key":"%s"}' "$K_LINE" | wget -q -O /dev/null --header 'Content-Type: application/json' --post-file=/dev/stdin "$BAO_ADDR/v1/sys/unseal" \
    || { K_LINE=""; die "la API rechazó la llave de desello"; }
  K_LINE=""
}

# comprobar_umbral: la política de custodia exige umbral 3 o más (S5-D76, S5-D106).
comprobar_umbral() {
  T="$(estado t)"
  case "$T" in ''|*[!0-9]*) die "no se pudo leer el umbral de desello" ;; esac
  if [ "$T" -lt 3 ]; then die "el umbral de desello es $T: se exige 3 o más"; fi
}

# desellar_con_llaves_tecleadas: pide llaves con read -rs hasta que OpenBao quede desellado.
desellar_con_llaves_tecleadas() {
  comprobar_umbral
  while [ "$(estado sealed)" = "true" ]; do
    echo "Llave de desello (no se muestra; progreso $(estado progress) de $(estado t)): " >&2
    read -rs K
    printf '%s\n' "$K" | unseal_stdin
    K=""
  done
  info "OpenBao desellado"
}

# decodificar_raiz <encoded_token> <otp>: la raíz temporal llega en base64 sin relleno, cifrada con
# XOR byte a byte contra la OTP. `bao operator generate-root -decode` consulta una ruta que pide
# token en OpenBao 2.7, así que se decodifica aquí con busybox (base64, od y aritmética de ash).
decodificar_raiz() {
  B64="$1"
  while [ $((${#B64} % 4)) -ne 0 ]; do B64="${B64}="; done
  CIFRADOS="$(printf '%s' "$B64" | base64 -d | od -An -v -tu1)"
  # shellcheck disable=SC2046
  set -- $(printf '%s' "$2" | od -An -v -tu1)
  TOKEN_DECODIFICADO=""
  for BYTE in $CIFRADOS; do
    OCTAL="$(printf '%03o' "$((BYTE ^ $1))")"
    TOKEN_DECODIFICADO="$TOKEN_DECODIFICADO$(printf "\\$OCTAL")"
    shift
  done
}

# --- 1. estado --------------------------------------------------------------------------------
esperar_api
INICIALIZADO="$(estado initialized)"

if [ "$INICIALIZADO" != "true" ] && [ "$MODE" != first ]; then
  die "volumen de OpenBao vacío: restaurar snapshot (docs/operacion/openbao.md) o, si es una instalación nueva, correr con --first-install"
fi
# En desarrollo el entrypoint ya inicializó (1/1) y desselló: solo allí --first-install parte de un OpenBao inicializado.
if [ "$INICIALIZADO" = "true" ] && [ "$MODE" = first ] && [ "$NONINTERACTIVE" = 0 ]; then
  die "OpenBao ya está inicializado: --first-install solo sirve sobre un volumen vacío (para reemitir tokens use --reissue-tokens)"
fi

# --- 2. instalación nueva ---------------------------------------------------------------------
if [ "$MODE" = first ]; then
  if [ "$NONINTERACTIVE" = 0 ]; then
    [ -t 0 ] && [ -t 2 ] || die "--first-install necesita una terminal (run sin -T): las llaves se muestran una sola vez por pantalla"
    echo "Se va a crear la llave maestra apex-kek sobre un volumen VACÍO." >&2
    echo "Las 5 llaves de desello se mostrarán UNA vez; con 3 se desella. Custodia 2/2/1: docs/operacion/openbao.md" >&2
    echo "Escriba INICIALIZAR para continuar: " >&2
    read -r CONFIRMA
    [ "$CONFIRMA" = "INICIALIZAR" ] || die "no se escribió INICIALIZAR: no se hizo nada"
    INIT_OUT="$(bao operator init -key-shares=5 -key-threshold=3)" || die "bao operator init falló"
    BAO_TOKEN="$(printf '%s\n' "$INIT_OUT" | sed -n 's/^Initial Root Token: //p')"
    export BAO_TOKEN
    [ -n "$BAO_TOKEN" ] || die "init no devolvió la raíz inicial"
    comprobar_umbral
    # Se desella con tres de las cinco, por stdin, sin pasar por argv.
    printf '%s\n' "$INIT_OUT" | sed -n 's/^Unseal Key [0-9]*: //p' | sed -n '1,3p' | while read -r UNA; do
      printf '%s\n' "$UNA" | unseal_stdin
    done
    [ "$(estado sealed)" = "false" ] || die "OpenBao sigue sellado tras tres llaves"
    # Las cinco llaves, SOLO por la terminal y una vez.
    {
      echo ""
      echo "=== LLAVES DE DESELLO: se muestran UNA SOLA VEZ, no quedan en ningún archivo ==="
      printf '%s\n' "$INIT_OUT" | sed -n 's/^\(Unseal Key [0-9]*: .*\)$/\1/p'
      echo "=== Reparta según docs/operacion/openbao.md (custodia 2/2/1). Sin 3 llaves no hay llave maestra. ==="
      echo ""
    } >&2
    INIT_OUT=""
    echo "Cuando las 5 llaves estén copiadas a sus sobres, escriba GUARDADAS: " >&2
    read -r CONFIRMA
    # L1: borra la pantalla (y el historial visible) de la terminal que mostró las llaves.
    printf '\033c' >&2
    [ "$CONFIRMA" = "GUARDADAS" ] || die "no se confirmó la custodia: las llaves ya se mostraron; reinicie el procedimiento con un volumen nuevo"
  else
    # Desarrollo (1/1): el entrypoint ya inicializó, desselló y exportó BAO_TOKEN.
    [ -n "${BAO_TOKEN:-}" ] || die "modo no interactivo sin BAO_TOKEN"
    [ "$(estado sealed)" = "false" ] || die "OpenBao sellado en modo no interactivo"
  fi

  bao secrets enable transit > /dev/null
  # apex-kek: AES-256-GCM, no exportable y sin respaldo en claro (la llave nunca sale de OpenBao).
  bao write -f transit/keys/apex-kek type=aes256-gcm96 exportable=false allow_plaintext_backup=false > /dev/null
  # apex-sign-audit: Ed25519 para la firma de auditoría (v0.3).
  bao write -f transit/keys/apex-sign-audit type=ed25519 exportable=false allow_plaintext_backup=false > /dev/null
  info "transit habilitado; apex-kek y apex-sign-audit creadas"
fi

# --- 3. reemisión de tokens: raíz temporal con tres llaves -------------------------------------
if [ "$MODE" = reissue ] || [ "$MODE" = normal ]; then
  if [ "$(estado sealed)" = "true" ]; then
    [ "$NONINTERACTIVE" = 0 ] || die "OpenBao sellado: desselle antes de reemitir"
    desellar_con_llaves_tecleadas
  fi
  if [ "$MODE" = normal ]; then
    info "OpenBao inicializado y desellado: nada más que hacer"
    exit 0
  fi
  comprobar_umbral
  [ -t 0 ] || die "--reissue-tokens necesita una terminal para teclear tres llaves"
  # Raíz temporal con tres llaves por los endpoints sin token de sys/generate-root (el listener los
  # abre con disable_unauthed_generate_root_endpoints = false). La CLI de OpenBao 2.7 usa otra ruta
  # que sí pide token, por eso aquí se habla con la API genérica y la raíz se decodifica a mano.
  INTENTO="$(BAO_TOKEN="" bao write -format=json -f sys/generate-root/attempt | tr -d ' \n')" || die "no se pudo iniciar la generación de la raíz temporal (¿hay otra en curso? Trátela como indicio de compromiso y cancélela con: \$DC exec -e BAO_ADDR=http://127.0.0.1:8210 openbao bao delete sys/generate-root/attempt)"
  ATTEMPT_OPEN=1
  NONCE="$(printf '%s' "$INTENTO" | sed -n 's/.*"nonce":"\([^"]*\)".*/\1/p')"
  OTP="$(printf '%s' "$INTENTO" | sed -n 's/.*"otp":"\([^"]*\)".*/\1/p')"
  INTENTO=""
  ENCODED=""
  PASO=0
  while [ "$PASO" -lt 3 ]; do
    PASO=$((PASO + 1))
    echo "Llave de desello $PASO de 3 (no se muestra): " >&2
    read -rs K
    # La llave llega a la API por stdin (key=-): nunca por argumento.
    SALIDA="$(printf '%s\n' "$K" | BAO_TOKEN="" bao write -format=json sys/generate-root/update key=- nonce="$NONCE" | tr -d ' \n')" || { K=""; die "la API rechazó la llave"; }
    K=""
    UNO="$(printf '%s' "$SALIDA" | sed -n 's/.*"encoded_token":"\([^"]*\)".*/\1/p')"
    [ -z "$UNO" ] || ENCODED="$UNO"
  done
  ATTEMPT_OPEN=0
  [ -n "$ENCODED" ] || die "no se completó la generación de la raíz temporal"
  decodificar_raiz "$ENCODED" "$OTP"
  BAO_TOKEN="$TOKEN_DECODIFICADO"
  export BAO_TOKEN
  TOKEN_DECODIFICADO=""
  OTP=""
  ENCODED=""
fi

# --- 4. políticas ------------------------------------------------------------------------------
for POL in apex-api apex-worker apex-tools apex-backup-snapshot; do
  [ -f "$POLICIES_DIR/$POL.hcl" ] || die "falta $POLICIES_DIR/$POL.hcl"
  bao policy write "$POL" "$POLICIES_DIR/$POL.hcl" > /dev/null
done
info "políticas apex-api, apex-worker, apex-tools y apex-backup-snapshot escritas"

# --- 5. tokens: periódicos de 768 h (32 días; el api los renueva con renew-self), huérfanos (sobreviven a la raíz), uno por servicio -----------------
# acc_viejos: accesores de los tokens apex-* vigentes, para revocarlos tras emitir los nuevos.
VIEJOS=""
if [ "$MODE" = reissue ]; then
  for ACC in $(bao list -format=json auth/token/accessors | tr -d '[]", ' | tr -s '\n' ' '); do
    NOMBRE="$(bao token lookup -accessor -field=display_name "$ACC" 2> /dev/null || true)"
    case "$NOMBRE" in token-apex-api|token-apex-worker|token-apex-tools) VIEJOS="$VIEJOS $ACC" ;; esac
  done
fi

emitir_token() { # <api|worker|tools>
  DIR="$TOKENS_DIR/$1"
  if [ ! -d "$DIR" ]; then
    [ "$NONINTERACTIVE" = 1 ] && { info "sin volumen de tokens en $DIR (desarrollo): se omite apex-$1"; return 0; }
    die "falta el volumen de tokens $DIR"
  fi
  bao token create -policy="apex-$1" -period=768h -orphan -renewable=true -no-default-policy -display-name="apex-$1" -field=token > "$DIR/token.new"
  chmod 600 "$DIR/token.new"
  chown 10001:10001 "$DIR/token.new"
  mv -f "$DIR/token.new" "$DIR/token"
  info "token de apex-$1 escrito en $DIR/token (modo 600, dueño 10001)"
}
emitir_token api
emitir_token worker
emitir_token tools
# El token de apex-backup-snapshot (política ya escrita) se emite en B13, cuando exista su volumen.

for ACC in $VIEJOS; do
  bao token revoke -accessor "$ACC" > /dev/null || info "aviso: no se pudo revocar el accesor $ACC"
done

# --- 6. la raíz se revoca al final (S5-D76) ------------------------------------------------------
bao token revoke -self > /dev/null
info "listo: la raíz quedó revocada"
