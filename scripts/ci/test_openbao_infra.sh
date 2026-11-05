#!/usr/bin/env bash
# test_openbao_infra.sh [raíz]
#
# Revisión estática de la infraestructura de OpenBao (S5-W0-2, paso 7; S5-D10, D11, D12, D75,
# D76, D103, D104; M-1, M-2, M-3 de sprint-05-seguridad-diseno.md). Bash puro, sin Docker ni
# OpenBao: grep y awk sobre infra/openbao/, scripts/dev/openbao-seal.sh y scripts/ci/openbao-smoke.sh.
# Las pruebas de Compose viven en test_compose_config.sh; las de deploy.sh, en test_deploy_script.sh.
#
# Contrato de las políticas (lo implementa el Verde, W0-2.2). Un bloque por ruta:
#   path "transit/encrypt/apex-kek" { capabilities = ["update"] }
#   api     = encrypt/apex-kek y decrypt/apex-kek (update) + auth/token/renew-self (update)
#   worker  = decrypt/apex-kek + renew-self
#   tools   = api + transit/rewrap/apex-kek + transit/keys/apex-kek/rotate + transit/keys/apex-kek/config
#   backup-snapshot = sys/storage/raft/snapshot (read), la única ruta sys/ (S5-D75)
# Fallo esperado en el Rojo: los scripts son stubs con exit 99 y las políticas están vacías.
set -euo pipefail

usage() {
  sed -n '2,15p' "$0" | sed 's/^# \{0,1\}//'
}
case "${1:-}" in
  -h|--help) usage; exit 0 ;;
esac

ROOT="${1:-$(git rev-parse --show-toplevel)}"
cd "$ROOT"
fallas=0
total=0
ok() { total=$((total + 1)); echo "  ok   $1"; }
falla() { total=$((total + 1)); fallas=$((fallas + 1)); echo "  FALLA $1"; }
resumen() { echo "  resumen: $((total - fallas)) ok, $fallas fallas"; echo "test_openbao_infra: $fallas fallas"; }

OB=infra/openbao
POL=$OB/policies
SEAL=scripts/dev/openbao-seal.sh
SMOKE=scripts/ci/openbao-smoke.sh

# codigo <archivo>: el archivo sin saltos CR y sin líneas que son solo comentario.
codigo() { tr -d '\015' < "$1" | grep -vE '^[[:space:]]*#' || true; }
# linea_de <archivo> <regex ERE>: número de la primera línea de código que coincide (0 si ninguna).
linea_de() { tr -d '\015' < "$1" | awk -v re="$2" '!/^[[:space:]]*#/ && $0 ~ re { print NR; f = 1; exit } END { if (!f) print 0 }'; }
# ultima_linea_de <archivo> <regex ERE>: número de la última línea de código que coincide (0 si ninguna).
ultima_linea_de() { tr -d '\015' < "$1" | awk -v re="$2" '!/^[[:space:]]*#/ && $0 ~ re { n = NR } END { print n + 0 }'; }
tiene() { codigo "$1" | grep -Eq -- "$2"; }

# requiere_script <archivo>: existe y es legible (los stubs del Rojo existen; sin ellos solo falla esto).
requiere_script() {
  if [ -f "$1" ]; then ok "existe $1"; return 0; fi
  falla "no existe $1"
  return 1
}

# --- bash -n -----------------------------------------------------------------------------------
echo "-- bash -n"
scripts=()
for f in "$OB"/*.sh "$SEAL" "$SMOKE"; do
  [ -f "$f" ] && scripts+=("$f")
done
for esperado in "$OB/bootstrap.sh" "$OB/dev-entrypoint.sh" "$SEAL" "$SMOKE"; do
  requiere_script "$esperado" || true
done
for f in ${scripts[@]+"${scripts[@]}"}; do
  if bash -n "$f" 2> /dev/null; then ok "bash -n $f"; else falla "bash -n $f"; fi
done
# Un stub del Rojo (exit 99) no es una implementación.
for f in ${scripts[@]+"${scripts[@]}"}; do
  if grep -q 'no implementado' "$f"; then falla "$f sigue siendo un stub (no implementado)"; else ok "$f implementado"; fi
done

# --- políticas ---------------------------------------------------------------------------------
echo "-- políticas"
# pares <archivo>: una línea "ruta<TAB>capacidades ordenadas y separadas por coma" por bloque path.
pares() {
  tr -d '\015' < "$1" | sed -E 's/#.*$//; s,//.*$,,' | tr '\n' ' ' \
    | grep -oE 'path[[:space:]]*"[^"]*"[[:space:]]*\{[^}]*\}' \
    | while IFS= read -r b; do
        ruta="$(printf '%s' "$b" | sed -E 's/^path[[:space:]]*"([^"]*)".*/\1/')"
        caps="$(printf '%s' "$b" | grep -oE 'capabilities[[:space:]]*=[[:space:]]*\[[^]]*\]' | grep -oE '"[^"]*"' | tr -d '"' | sort | paste -sd, - || true)"
        printf '%s\t%s\n' "$ruta" "$caps"
      done | sort || true
}

NL=$'\n'
esperado_api="auth/token/renew-self	update${NL}transit/decrypt/apex-kek	update${NL}transit/encrypt/apex-kek	update"
esperado_worker="auth/token/renew-self	update${NL}transit/decrypt/apex-kek	update"
esperado_tools="auth/token/renew-self	update${NL}transit/decrypt/apex-kek	update${NL}transit/encrypt/apex-kek	update${NL}transit/keys/apex-kek/config	update${NL}transit/keys/apex-kek/rotate	update${NL}transit/rewrap/apex-kek	update"
esperado_snapshot="sys/storage/raft/snapshot	read"

for par in "apex-api:$esperado_api" "apex-worker:$esperado_worker" "apex-tools:$esperado_tools" "apex-backup-snapshot:$esperado_snapshot"; do
  nombre="${par%%:*}"
  esperado="${par#*:}"
  f="$POL/$nombre.hcl"
  if [ ! -f "$f" ]; then falla "no existe $f"; continue; fi
  obtenido="$(pares "$f")"
  if [ "$obtenido" = "$esperado" ]; then
    ok "$nombre: exactamente las rutas y capacidades del plan"
  else
    falla "$nombre: rutas distintas de las del plan (obtenidas: $(printf '%s' "$obtenido" | tr '\t\n' ': ' | sed 's/ $//' | sed 's/^$/ninguna/'))"
  fi
done

# Reglas generales sobre las cuatro políticas (aunque estén vacías no hay nada que reprochar:
# lo que obliga a que no estén vacías son las aserciones exactas de arriba).
for nombre in apex-api apex-worker apex-tools apex-backup-snapshot; do
  f="$POL/$nombre.hcl"
  [ -f "$f" ] || continue
  limpio="$(tr -d '\015' < "$f" | sed -E 's/#.*$//; s,//.*$,,')"
  for cap in delete sudo trim; do
    if printf '%s' "$limpio" | grep -Eq "\"$cap\""; then falla "$nombre usa la capacidad $cap"; else ok "$nombre sin capacidad $cap"; fi
  done
  # Comodines: solo `apex-*` al final de la ruta; nunca `+` ni `*` suelto.
  malas="$(pares "$f" | cut -f1 | grep -E '[*+]' | grep -vE '/apex-\*$' || true)"
  if [ -z "$malas" ]; then ok "$nombre sin comodines fuera de apex-*"; else falla "$nombre con comodín fuera de apex-: $malas"; fi
  if printf '%s' "$limpio" | grep -Eq 'capabilities[^]]*"\*"'; then falla "$nombre con capacidad *"; else ok "$nombre sin capacidad *"; fi
  # sys/: solo la ruta exacta de S5-D75 y solo en apex-backup-snapshot.
  sys="$(pares "$f" | cut -f1 | grep -E '^/?sys/' || true)"
  if [ "$nombre" = apex-backup-snapshot ]; then
    if [ "$sys" = "sys/storage/raft/snapshot" ]; then ok "$nombre: única ruta sys/ y exacta (S5-D75)"; else falla "$nombre: ruta sys/ distinta de sys/storage/raft/snapshot (${sys:-ninguna})"; fi
  else
    if [ -z "$sys" ]; then ok "$nombre sin rutas sys/"; else falla "$nombre toca sys/: $sys"; fi
  fi
done

# --- bootstrap.sh -----------------------------------------------------------------------------
echo "-- bootstrap.sh"
B=$OB/bootstrap.sh
if [ -f "$B" ]; then
  if tiene "$B" '(^|[[:space:];&|])set[[:space:]]+(-[a-z]*x|-o[[:space:]]+xtrace)|xtrace|bash[[:space:]]+-[a-z]*x'; then falla "bootstrap.sh con set -x / xtrace"; else ok "bootstrap.sh sin set -x"; fi
  if tiene "$B" 'set -euo pipefail'; then ok "bootstrap.sh con set -euo pipefail"; else falla "bootstrap.sh sin set -euo pipefail"; fi
  if tiene "$B" 'umask 077'; then ok "bootstrap.sh con umask 077"; else falla "bootstrap.sh sin umask 077"; fi
  if tiene "$B" '(^|[^[:alnum:]_])--first-install'; then ok "bootstrap.sh acepta --first-install"; else falla "bootstrap.sh sin --first-install"; fi
  if tiene "$B" '(^|[^[:alnum:]_])--reissue-tokens'; then ok "bootstrap.sh acepta --reissue-tokens (S5-D76)"; else falla "bootstrap.sh sin --reissue-tokens"; fi
  l_inic="$(linea_de "$B" 'INICIALIZAR')"
  l_kek="$(linea_de "$B" 'transit/keys/apex-kek|keys/apex-kek')"
  if [ "$l_inic" -gt 0 ] && [ "$l_kek" -gt 0 ] && [ "$l_inic" -lt "$l_kek" ]; then ok "bootstrap.sh exige INICIALIZAR (línea $l_inic) antes de crear apex-kek (línea $l_kek)"; else falla "bootstrap.sh: INICIALIZAR (línea $l_inic) debe ir antes de crear apex-kek (línea $l_kek)"; fi
  if tiene "$B" 'key-shares=5' && tiene "$B" 'key-threshold=([3-9]|[1-9][0-9]+)([^0-9]|$)'; then ok "bootstrap.sh inicializa 5 llaves con umbral >= 3"; else falla "bootstrap.sh sin key-shares=5 y key-threshold >= 3"; fi
  if tiene "$B" '(-lt|-le)[[:space:]]+3|<[[:space:]]*3|(-ge|-gt)[[:space:]]+3|>=[[:space:]]*3'; then ok "bootstrap.sh comprueba el umbral de 3 o más"; else falla "bootstrap.sh no comprueba el umbral de 3 o más"; fi
  if tiene "$B" '(echo|printf)[^|#]*\$\{?[A-Za-z_]*([Rr][Oo][Oo][Tt])'; then falla "bootstrap.sh imprime la raíz con echo/printf"; else ok "bootstrap.sh no hace echo de la raíz"; fi
  if tiene "$B" '\$\{?[A-Za-z_]*([Rr][Oo][Oo][Tt])[A-Za-z_]*\}?"?[^|#]*[^>]>[^>&]|operator init[^|#]*[^>&]>[^>&]|operator init[^|#]*tee'; then falla "bootstrap.sh escribe la raíz o la salida de init a un archivo"; else ok "bootstrap.sh no escribe la raíz a archivo"; fi
  l_rev="$(ultima_linea_de "$B" 'token[[:space:]]+revoke([[:space:]]+-[A-Za-z-]+)*[[:space:]]+-self')"
  l_ult="$(ultima_linea_de "$B" 'policy[[:space:]]+write|token[[:space:]]+create|auth/token/create')"
  if [ "$l_rev" -gt 0 ] && [ "$l_rev" -ge "$l_ult" ]; then ok "bootstrap.sh revoca la raíz (token revoke -self) tras escribir políticas y tokens"; else falla "bootstrap.sh: token revoke -self (línea $l_rev) debe ir después de la última política/token (línea $l_ult)"; fi
  if { tiene "$B" 'chmod[^#]*(^|[^0-9])600' && tiene "$B" 'chown[^#]*10001'; } || tiene "$B" 'install[^#]*-m[[:space:]]*0?600[^#]*10001|install[^#]*10001[^#]*-m[[:space:]]*0?600'; then ok "bootstrap.sh escribe los tokens con modo 600 y dueño 10001"; else falla "bootstrap.sh sin modo 600 y dueño 10001 en los tokens"; fi
  if tiene "$B" 'read[[:space:]]+-[a-z]*r[a-z]*s|read[[:space:]]+-[a-z]*s[a-z]*r'; then ok "bootstrap.sh lee las llaves con read -rs"; else falla "bootstrap.sh no lee con read -rs"; fi
  if tiene "$B" 'operator[[:space:]]+unseal'; then falla "bootstrap.sh desella con 'operator unseal' (llave en argv; S5-D103)"; else ok "bootstrap.sh sin 'operator unseal' por argv"; fi
  if tiene "$B" 'sys/unseal' && tiene "$B" '--post-file=/dev/stdin'; then ok "bootstrap.sh desella por la API con --post-file=/dev/stdin (S5-D103)"; else falla "bootstrap.sh sin sys/unseal con --post-file=/dev/stdin"; fi
  if tiene "$B" "printf[[:space:]]+'?\\{\"key\":\"[^%]"; then falla "bootstrap.sh con la llave literal en printf"; else ok "bootstrap.sh sin printf con llave literal"; fi
  if tiene "$B" 'aes256-gcm96' && tiene "$B" 'exportable=false' && tiene "$B" 'allow_plaintext_backup=false'; then ok "bootstrap.sh crea apex-kek aes256-gcm96, no exportable y sin respaldo en claro"; else falla "bootstrap.sh: apex-kek sin aes256-gcm96, exportable=false y allow_plaintext_backup=false"; fi
  if tiene "$B" 'apex-sign-audit' && tiene "$B" 'ed25519'; then ok "bootstrap.sh crea apex-sign-audit ed25519"; else falla "bootstrap.sh sin apex-sign-audit ed25519"; fi
  if tiene "$B" 'period=768h'; then ok "bootstrap.sh crea tokens periódicos de 768h (M-2)"; else falla "bootstrap.sh sin period=768h"; fi
  # S5-B13 (S5-D8, S5-D76): el token del respaldo (apex-backup-snapshot) se emite siempre, también con
  # --reissue-tokens, en el volumen propio, y el token viejo se revoca como los demás.
  if tiene "$B" 'emitir_token[[:space:]]+backup'; then ok "bootstrap.sh emite el token de backup (S5-B13)"; else falla "bootstrap.sh no emite el token de backup (emitir_token backup)"; fi
  if tiene "$B" 'token-apex-backup'; then ok "bootstrap.sh revoca los tokens viejos de backup al reemitir (token-apex-backup)"; else falla "bootstrap.sh no revoca el token viejo de apex-backup al reemitir"; fi
  n_pol_bk="$(codigo "$B" | grep -E 'apex-backup-snapshot' | grep -vE 'for POL|info ' | wc -l | tr -d ' ' || true)"
  if [ "$n_pol_bk" -ge 1 ]; then ok "bootstrap.sh crea el token de backup con la política apex-backup-snapshot, no con apex-backup"; else falla "bootstrap.sh: el token de backup debe usar -policy=apex-backup-snapshot (no existe una política apex-backup)"; fi
  if tiene "$B" 'TOKENS_DIR/\$1|TOKENS_DIR/backup|openbao-token-backup'; then ok "bootstrap.sh escribe el token de backup bajo TOKENS_DIR"; else falla "bootstrap.sh no escribe el token de backup bajo TOKENS_DIR"; fi
  if codigo "$B" | awk '/^limpiar\(\)/ { d = 1 } d && /token revoke -self/ { f = 1 } d && /^}/ { exit } END { exit !f }'; then ok "bootstrap.sh: limpiar revoca la raíz temporal si el script muere (M2)"; else falla "bootstrap.sh: limpiar no hace token revoke -self (M2)"; fi
  if tiene "$B" "printf '.033c'"; then ok "bootstrap.sh limpia la terminal tras GUARDADAS (L1)"; else falla "bootstrap.sh no limpia la terminal tras GUARDADAS (L1)"; fi
  if tiene "$B" 'exec .*openbao bao delete sys/generate-root/attempt'; then ok "bootstrap.sh sugiere el comando real para cancelar un intento (exec openbao ... 8210)"; else falla "bootstrap.sh no sugiere 'exec openbao bao delete sys/generate-root/attempt'"; fi
  if tiene "$B" 'volumen de OpenBao vacío: restaurar snapshot'; then ok "bootstrap.sh aborta sin --first-install con 'volumen de OpenBao vacío: restaurar snapshot'"; else falla "bootstrap.sh sin el mensaje 'volumen de OpenBao vacío: restaurar snapshot'"; fi
else
  falla "no existe $B"
fi

# --- dev-entrypoint.sh ------------------------------------------------------------------------
echo "-- dev-entrypoint.sh"
D=$OB/dev-entrypoint.sh
if [ -f "$D" ]; then
  l_guarda="$(linea_de "$D" 'APEX_ENV')"
  l_init="$(linea_de "$D" 'operator init|sys/init')"
  if tiene "$D" 'APEX_ENV[^[:space:]]*[[:space:]]*(!=|-ne)[[:space:]]*"?dev|APEX_ENV[^|;]*=[[:space:]]*"?dev"?[^|;]*\|\|' && tiene "$D" 'exit[[:space:]]+[1-9]'; then ok "dev-entrypoint.sh aborta si APEX_ENV != dev"; else falla "dev-entrypoint.sh sin guarda 'APEX_ENV != dev' con exit"; fi
  if [ "$l_guarda" -gt 0 ] && [ "$l_init" -gt 0 ] && [ "$l_guarda" -lt "$l_init" ]; then ok "dev-entrypoint.sh comprueba APEX_ENV antes de inicializar"; else falla "dev-entrypoint.sh: la guarda (línea $l_guarda) debe ir antes de init (línea $l_init)"; fi
  if tiene "$D" 'key-shares=1' && tiene "$D" 'key-threshold=1'; then ok "dev-entrypoint.sh inicializa 1/1"; else falla "dev-entrypoint.sh sin key-shares=1 y key-threshold=1"; fi
  if tiene "$D" 'BOOTSTRAP_NONINTERACTIVE'; then ok "dev-entrypoint.sh llama a bootstrap.sh no interactivo"; else falla "dev-entrypoint.sh sin BOOTSTRAP_NONINTERACTIVE"; fi
  if tiene "$D" '(^|[[:space:];&|])set[[:space:]]+(-[a-z]*x|-o[[:space:]]+xtrace)|xtrace'; then falla "dev-entrypoint.sh con set -x"; else ok "dev-entrypoint.sh sin set -x"; fi
else
  falla "no existe $D"
fi

# --- config.hcl --------------------------------------------------------------------------------
echo "-- config.hcl"
C=$OB/config.hcl
if [ -f "$C" ]; then
  cfg() { tr -d '\015' < "$C" | grep -vE '^[[:space:]]*#' || true; }
  if cfg | grep -Eq '^[[:space:]]*ui[[:space:]]*=[[:space:]]*false'; then ok "config.hcl: ui = false"; else falla "config.hcl sin ui = false"; fi
  if cfg | grep -Eq '^[[:space:]]*disable_mlock[[:space:]]*=[[:space:]]*true'; then ok "config.hcl: disable_mlock = true"; else falla "config.hcl sin disable_mlock = true"; fi
  if cfg | grep -Eq '^[[:space:]]*storage[[:space:]]+"raft"'; then ok 'config.hcl: storage "raft"'; else falla 'config.hcl sin storage "raft"'; fi
  if cfg | grep -Eq '^[[:space:]]*listener[[:space:]]+"tcp"'; then ok 'config.hcl: listener "tcp"'; else falla 'config.hcl sin listener "tcp"'; fi
  # S5-D107: dos listeners. 0.0.0.0:8200 (red custody) con los endpoints sin token de generate-root y
  # rekey en su valor por omisión (cerrados); 127.0.0.1:8210 (solo el contenedor y el bootstrap) con ambos en false.
  n_listener="$(cfg | grep -Ec '^[[:space:]]*listener[[:space:]]' || true)"
  direcciones="$(cfg | grep -E '^[[:space:]]*address[[:space:]]*=' | sed -E 's/.*=[[:space:]]*"?([^"]*)"?.*/\1/' | sort | paste -sd, - || true)"
  if [ "$n_listener" = 2 ] && [ "$direcciones" = "0.0.0.0:8200,127.0.0.1:8210" ]; then ok "config.hcl: dos listeners, 0.0.0.0:8200 y 127.0.0.1:8210"; else falla "config.hcl: listeners=$n_listener direcciones='${direcciones:-ninguna}' (se esperan 0.0.0.0:8200 y 127.0.0.1:8210)"; fi
  # bloque_de <dirección>: el cuerpo del listener que tiene esa dirección.
  bloque_de() { cfg | awk -v d="$1" '/^[[:space:]]*listener[[:space:]]/ { b = ""; dentro = 1 } dentro { b = b $0 "\n" } /^}/ { if (dentro && index(b, d)) { printf "%s", b; exit } dentro = 0 }'; }
  pub="$(bloque_de '0.0.0.0:8200')"
  loc="$(bloque_de '127.0.0.1:8210')"
  if printf '%s' "$pub" | grep -Eq 'disable_unauthed_(generate_root|rekey)_endpoints[[:space:]]*=[[:space:]]*false'; then falla "config.hcl: el listener 0.0.0.0:8200 abre generate-root o rekey sin token"; else ok "config.hcl: 0.0.0.0:8200 con generate-root y rekey sin token cerrados (S5-D107)"; fi
  if printf '%s' "$loc" | grep -Eq 'disable_unauthed_generate_root_endpoints[[:space:]]*=[[:space:]]*false' && printf '%s' "$loc" | grep -Eq 'disable_unauthed_rekey_endpoints[[:space:]]*=[[:space:]]*false'; then ok "config.hcl: 127.0.0.1:8210 abre generate-root y rekey (solo ahí)"; else falla "config.hcl: 127.0.0.1:8210 sin los dos disable_unauthed_*=false"; fi
  if cfg | grep -Eq '^[[:space:]]*tls_disable[[:space:]]*=[[:space:]]*(true|1)'; then ok "config.hcl: tls_disable activo (TLS llega con Caddy/EP-20)"; else falla "config.hcl sin tls_disable = true"; fi
  motivo="$(tr -d '\015' < "$C" | grep -E '^[[:space:]]*#.*tls_disable' || true)"
  if [ "${#motivo}" -ge 30 ]; then ok "config.hcl: tls_disable comentado con el motivo"; else falla "config.hcl: sin comentario que explique tls_disable"; fi
else
  falla "no existe $C"
fi

# --- openbao-seal.sh --------------------------------------------------------------------------
echo "-- openbao-seal.sh"
if [ -f "$SEAL" ]; then
  if tiene "$SEAL" 'read[[:space:]]+-[a-z]*r[a-z]*s|read[[:space:]]+-[a-z]*s[a-z]*r'; then ok "openbao-seal.sh lee con read -rs"; else falla "openbao-seal.sh no lee con read -rs"; fi
  if codigo "$SEAL" | grep -v 'case' | grep -Eq '\$\{?[1-9@*#]'; then falla "openbao-seal.sh usa argumentos posicionales (nada de llaves por argv)"; else ok "openbao-seal.sh sin argumentos con llaves"; fi
  if tiene "$SEAL" "printf[[:space:]]+'?\\{\"key\":\"[^%]"; then falla "openbao-seal.sh con la llave literal en printf"; else ok "openbao-seal.sh sin printf con llave literal"; fi
  if tiene "$SEAL" '(^|[[:space:];&|])set[[:space:]]+(-[a-z]*x|-o[[:space:]]+xtrace)|xtrace'; then falla "openbao-seal.sh con set -x"; else ok "openbao-seal.sh sin set -x"; fi
else
  falla "no existe $SEAL"
fi

resumen
[ "$fallas" -eq 0 ]
