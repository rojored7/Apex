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
#   tools   = api + leer transit/keys/apex-kek + rotate + config (solo min_decryption_version; S5-D191)
#   backup-snapshot = sys/storage/raft/snapshot (read), la única ruta sys/ (S5-D75)
# Fallo esperado en el Rojo: los scripts son stubs con exit 99 y las políticas están vacías.
set -euo pipefail
# Las aserciones con tildes (pol[ií]ticas) necesitan un locale UTF-8; Git Bash en Windows arranca sin él.
export LC_ALL=C.UTF-8

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
      done | LC_ALL=C sort || true
}

NL=$'\n'
esperado_api="auth/token/renew-self	update${NL}transit/decrypt/apex-kek	update${NL}transit/encrypt/apex-kek	update${NL}transit/verify/apex-sign-audit	update"  # Rojo S6-W0-3 (S6-D6, D41): el api solo verifica
esperado_worker="auth/token/renew-self	update${NL}transit/decrypt/apex-kek	update${NL}transit/sign/apex-sign-audit	update${NL}transit/verify/apex-sign-audit	update"  # Rojo S6-W0-3: el worker firma y verifica
esperado_tools="auth/token/renew-self	update${NL}transit/decrypt/apex-kek	update${NL}transit/encrypt/apex-kek	update${NL}transit/keys/apex-kek	read${NL}transit/keys/apex-kek/config	update${NL}transit/keys/apex-kek/rotate	update${NL}transit/keys/apex-sign-audit	read${NL}transit/sign/apex-sign-audit	update${NL}transit/verify/apex-sign-audit	update"  # Rojo S6-W0-3: tools firma, verifica y lee la llave de firma
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

# S5-B2 (S5-D19, S5-D55a): `rotate()` y `key_info()` leen transit/keys/apex-kek, así que apex-tools
# necesita `read` exactamente en esa ruta; nunca `trim` ni `delete` (el recorte es `config`).
f="$POL/apex-tools.hcl"
if [ -f "$f" ]; then
  caps_kek="$(pares "$f" | awk -F'	' '$1 == "transit/keys/apex-kek" { print $2 }')"
  if [ "$caps_kek" = "read" ]; then ok "apex-tools: read en transit/keys/apex-kek (rotate y key_info, B2)"; else falla "apex-tools: transit/keys/apex-kek debe tener solo read (tiene: ${caps_kek:-nada})"; fi
  if pares "$f" | cut -f1 | grep -Eq '/(trim|delete)'; then falla "apex-tools con una ruta trim o delete"; else ok "apex-tools sin rutas trim ni delete"; fi
  if pares "$f" | cut -f1 | grep -q 'rewrap'; then falla "apex-tools conserva transit/rewrap (S5-D191)"; else ok "apex-tools sin transit/rewrap"; fi
  cfg="$(tr -d '\015' < "$f" | sed -E 's/#.*$//' | tr '\n' ' ' | grep -oE 'path[[:space:]]*"transit/keys/apex-kek/config"[^}]*\{[^}]*\}' || true)"
  if printf '%s' "$cfg" | grep -Eq 'allowed_parameters[[:space:]]*=[[:space:]]*\{[[:space:]]*"min_decryption_version"[[:space:]]*=[[:space:]]*\[\]'; then ok "apex-tools: config solo admite min_decryption_version"; else falla "apex-tools: config sin allowed_parameters = min_decryption_version (S5-D191)"; fi
fi

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

# Rojo S6-W0-3 (S6-D6, S6-D41, M-2c): aserciones nominales sobre la llave de firma `apex-sign-audit`.
echo "-- políticas · apex-sign-audit (Rojo S6-W0-3)"
SIGN=transit/sign/apex-sign-audit
VERIFY=transit/verify/apex-sign-audit
caps_de() { pares "$1" | awk -F'	' -v r="$2" '$1 == r { print $2 }'; }
fw="$POL/apex-worker.hcl"; fa="$POL/apex-api.hcl"; ft="$POL/apex-tools.hcl"
if [ -f "$fw" ] && [ "$(caps_de "$fw" "$SIGN")" = update ] && [ "$(caps_de "$fw" "$VERIFY")" = update ]; then ok "apex-worker: update en $SIGN y $VERIFY"; else falla "apex-worker sin update en $SIGN y $VERIFY (Rojo S6-W0-3)"; fi
if [ -f "$fa" ] && [ "$(caps_de "$fa" "$VERIFY")" = update ]; then ok "apex-api: update en $VERIFY"; else falla "apex-api sin update en $VERIFY (Rojo S6-W0-3)"; fi
if [ -f "$fa" ] && pares "$fa" | cut -f1 | grep -q 'transit/sign/'; then falla "apex-api con una ruta transit/sign/: el api no firma (S6-D6)"; else ok "apex-api no firma (ninguna ruta transit/sign/)"; fi
if [ -f "$ft" ] && [ "$(caps_de "$ft" "$SIGN")" = update ] && [ "$(caps_de "$ft" "$VERIFY")" = update ] && [ "$(caps_de "$ft" transit/keys/apex-sign-audit)" = read ]; then ok "apex-tools: sign y verify (update) y read en transit/keys/apex-sign-audit"; else falla "apex-tools sin sign, verify y read de la llave de firma (Rojo S6-W0-3)"; fi
for nombre in apex-api apex-worker apex-tools apex-backup-snapshot; do
  f="$POL/$nombre.hcl"
  [ -f "$f" ] || continue
  # M-2c: ninguna política toca rotate, config, trim, export, backup ni delete de apex-sign-audit.
  if pares "$f" | cut -f1 | grep -Eq 'apex-sign-audit/'; then falla "$nombre con subruta de apex-sign-audit (rotate, config, trim, export...): M-2c"; else ok "$nombre sin subrutas de apex-sign-audit (rotate, config, trim, export; M-2c)"; fi
  if pares "$f" | cut -f1 | grep -Eq '^transit/(sign|verify)/[*+]'; then falla "$nombre con comodín en transit/sign o transit/verify"; else ok "$nombre sin comodín en transit/sign ni transit/verify"; fi
done
if [ -f "$POL/apex-backup-snapshot.hcl" ] && pares "$POL/apex-backup-snapshot.hcl" | cut -f1 | grep -Eq '^transit/'; then falla "apex-backup-snapshot con rutas transit/"; else ok "apex-backup-snapshot sin rutas transit/"; fi
for nombre in apex-api apex-worker apex-tools; do
  f="$POL/$nombre.hcl"
  [ -f "$f" ] || continue
  otras="$(pares "$f" | cut -f1 | grep -E '^transit/(sign|verify|keys)/' | grep -vE 'apex-(kek|sign-audit)(/|$)' || true)"
  if [ -z "$otras" ]; then ok "$nombre: sign/verify/keys solo sobre apex-kek y apex-sign-audit"; else falla "$nombre con sign/verify/keys sobre otra llave: $otras"; fi
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
  # Rojo S6-W0-3 (S6-D51, S6-D41): apex-sign-audit solo Ed25519, no exportable; --reissue-tokens reaplica las cuatro políticas.
  if grep -qiE 'ml-?dsa' "$B"; then falla "bootstrap.sh menciona ml-dsa (v0.3 firma con Ed25519; D51)"; else ok "bootstrap.sh sin ml-dsa (D51)"; fi
  linea_firma="$(codigo "$B" | grep -E 'transit/keys/apex-sign-audit' || true)"
  if printf '%s' "$linea_firma" | grep -q 'type=ed25519' && printf '%s' "$linea_firma" | grep -q 'exportable=false' && printf '%s' "$linea_firma" | grep -q 'allow_plaintext_backup=false'; then ok "bootstrap.sh: apex-sign-audit ed25519, exportable=false y allow_plaintext_backup=false"; else falla "bootstrap.sh: apex-sign-audit sin type=ed25519, exportable=false y allow_plaintext_backup=false"; fi
  # La cabecera documenta que --reissue-tokens reaplica las políticas (Verde: comentario de --reissue-tokens).
  cab_reissue="$(tr -d '\015' < "$B" | sed -n '2,27p' | sed 's/^# \{0,1\}//' | awk '/^--reissue-tokens:/ { d = 1; print; next } d && /^--/ { exit } d && /^[A-Za-z]/ { exit } d { print }')"
  if printf '%s' "$cab_reissue" | grep -Eiq 'pol[ií]ticas.*(reaplic|reescrib|escrib|aplic)|(reaplic|reescrib|escrib|aplic).*pol[ií]ticas'; then ok "bootstrap.sh: la cabecera de --reissue-tokens dice que reaplica las políticas"; else falla "bootstrap.sh: la cabecera de --reissue-tokens no dice que reaplica las políticas (Rojo S6-W0-3)"; fi
  for pol in apex-api apex-worker apex-tools apex-backup-snapshot; do
    if codigo "$B" | grep -E '^for POL in' | grep -q "$pol"; then ok "bootstrap.sh recorre $pol al escribir políticas"; else falla "bootstrap.sh no incluye $pol en el bucle de políticas"; fi
  done
  l_bucle="$(linea_de "$B" '^for POL in ')"
  l_emitir="$(linea_de "$B" '^emitir_token api')"
  if [ "$l_bucle" -gt 0 ] && [ "$l_emitir" -gt 0 ] && [ "$l_bucle" -lt "$l_emitir" ]; then ok "bootstrap.sh escribe las políticas (línea $l_bucle) antes de emitir tokens (línea $l_emitir), también con --reissue-tokens"; else falla "bootstrap.sh: las políticas (línea $l_bucle) deben escribirse antes de emitir tokens (línea $l_emitir)"; fi
  # «sin sonda»: el bootstrap no firma ni verifica nada para probar la política.
  if codigo "$B" | grep -Eq 'transit/(sign|verify)/'; then falla "bootstrap.sh sondea transit/sign o transit/verify (la sonda va en openbao-smoke.sh)"; else ok "bootstrap.sh sin sonda de firma (la prueba es del humo)"; fi
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
  if cfg | grep -Eq '^[[:space:]]*tls_disable[[:space:]]*=[[:space:]]*(true|1)'; then ok "config.hcl: tls_disable activo (Caddy no cifra custody; residual v0.4)"; else falla "config.hcl sin tls_disable = true"; fi
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

# S5-B2 (H-2.3): con --provider openbao el smoke comprueba que api y worker no tienen kek.bin.
PSMOKE=scripts/ci/prod-smoke.sh
if tiene "$PSMOKE" "test ! -e /run/apex/keys/kek.bin" && tiene "$PSMOKE" "for SVC in api worker"; then ok "prod-smoke.sh comprueba que api y worker no tienen kek.bin (openbao)"; else falla "prod-smoke.sh sin la comprobación de kek.bin ausente en api y worker"; fi

# S5-B3 (S5-D22, S5-D69, S5-D70): el humo comprueba el estado sellado del api y la recuperación.
echo "-- openbao-smoke.sh · S5-B3"
if tiene "$SMOKE" '"crypto"[^|]*sealed|crypto.{0,12}sealed'; then ok "openbao-smoke.sh comprueba /health con crypto sealed"; else falla "openbao-smoke.sh no comprueba crypto sealed en /health"; fi
if tiene "$SMOKE" '503'; then ok "openbao-smoke.sh espera HTTP 503 con el custodio sellado"; else falla "openbao-smoke.sh no espera el 503 de /health"; fi
if tiene "$SMOKE" 'restart[[:space:]]+openbao' && tiene "$SMOKE" 'restart[[:space:]]+api[[:space:]]+worker'; then ok "openbao-smoke.sh reinicia openbao y después api y worker (D69)"; else falla "openbao-smoke.sh sin restart openbao y restart api worker"; fi
if tiene "$SMOKE" 'crypto_unavailable' && tiene "$SMOKE" '/members/'; then ok "openbao-smoke.sh pide GET /members/{id} y espera 503 crypto_unavailable"; else falla "openbao-smoke.sh sin la prueba de GET /members/{id} con crypto_unavailable"; fi
if tiene "$SMOKE" 'salud[[:space:]]+web' && tiene "$SMOKE" 'salud[[:space:]]+worker'; then ok "openbao-smoke.sh comprueba que web y worker siguen healthy"; else falla "openbao-smoke.sh no comprueba web y worker healthy con el custodio sellado"; fi
if tiene "$SMOKE" 'espera_(healthy|crypto|ok)[^#]*[[:space:]]40|(-le|<=|-lt)[[:space:]]*(40|41)|RECUPERACION_MAX_S=40|40[[:space:]]*(s|seg)'; then ok "openbao-smoke.sh fija la recuperación en 40 s o menos"; else falla "openbao-smoke.sh sin el límite de 40 s de recuperación"; fi
if tiene "$SMOKE" 'OPENBAO_SMOKE_EVIDENCE|EVIDENCE' && tiene "$SMOKE" 'health.*(EVIDENCE|evidencia)|evidencia.*health'; then ok "openbao-smoke.sh guarda la evidencia de /health en cada estado"; else falla "openbao-smoke.sh no guarda la evidencia de /health por estado"; fi
if tiene "$SMOKE" 'desell|unseal'; then ok "openbao-smoke.sh desella y espera el crypto ok"; else falla "openbao-smoke.sh sin el desellado final"; fi
if tiene "$SMOKE" 'run --rm -T worker python -m app.worker.main --run-once expirations'; then ok "openbao-smoke.sh corre el worker --run-once expirations tras el desello (L7)"; else falla "openbao-smoke.sh no corre el worker tras el desello"; fi
if tiene "$SMOKE" 'CI:-' && tiene "$SMOKE" 'CI definida'; then ok "openbao-smoke.sh: con CI, faltar el admin del humo es FALLA (L7)"; else falla "openbao-smoke.sh no falla con CI y sin admin del humo"; fi
if tr -d '\015' < "$SMOKE" | grep -Eq 'llega con B1 y B2'; then falla "openbao-smoke.sh aún dice que el estado sellado llega con B1 y B2 (actualizar el comentario)"; else ok "openbao-smoke.sh ya no pospone el estado sellado"; fi

# --- Rojo S6-W0-3 · L-6: cap_drop [ALL] en todos los servicios de la red custody ------------------
echo "-- compose.yml · custody cap_drop (Rojo S6-W0-3, L-6)"
COMPOSE_YML=infra/compose.yml
if [ -f "$COMPOSE_YML" ]; then
  # Una línea "servicio cap_drop(0|1)" por servicio en custody; openbao-bootstrap comparte la red de openbao (network_mode).
  resultado="$(tr -d '\015' < "$COMPOSE_YML" | awk '
    /^services:/ { s = 1; next }
    /^[a-z]/ { s = 0 }
    s && /^  [a-z][a-z0-9_-]*:[[:space:]]*$/ { n = $1; sub(/:$/, "", n); orden[++k] = n; next }
    s && n != "" { blk[n] = blk[n] $0 "\n" }
    END { for (i = 1; i <= k; i++) { n = orden[i]; b = blk[n]
      custodia = (b ~ /(^|\n)      - custody[[:space:]]*\n/ || b ~ /network_mode:[[:space:]]*"?service:openbao"?/) ? 1 : 0
      cd = (b ~ /cap_drop:[[:space:]]*\[[[:space:]]*"?ALL"?[[:space:]]*\]/) ? 1 : 0
      if (custodia) print n, cd } }')"
  n_cust="$(printf '%s\n' "$resultado" | grep -c . || true)"
  if [ "$n_cust" -ge 6 ]; then ok "compose.yml: $n_cust servicios en custody"; else falla "compose.yml: se esperaban al menos 6 servicios en custody y se leyeron $n_cust"; fi
  while read -r srv cd; do
    [ -n "$srv" ] || continue
    if [ "$cd" = 1 ]; then ok "compose.yml: $srv (custody) con cap_drop: [ALL]"; else falla "compose.yml: $srv (custody) sin cap_drop: [ALL] (L-6)"; fi
  done <<< "$resultado"
else
  falla "no existe $COMPOSE_YML"
fi

# --- Rojo S6-W0-3 · openbao-smoke.sh: cuatro pasos de firma, verificación y 403 ---------------------
echo "-- openbao-smoke.sh · S6-W0-3 (Rojo)"
if [ -f "$SMOKE" ]; then
  for fn in firma_worker_200 verifica_api_valid firma_api_403 rota_tools_403; do
    if tiene "$SMOKE" "^${fn}\\(\\)"; then ok "openbao-smoke.sh define la función $fn"; else falla "openbao-smoke.sh sin la función $fn (Rojo S6-W0-3)"; fi
    llamadas="$(codigo "$SMOKE" | grep -Ec "^[[:space:]]*${fn}([[:space:]]|$)" || true)"
    if [ "$llamadas" -ge 1 ]; then ok "openbao-smoke.sh llama a $fn"; else falla "openbao-smoke.sh no llama a $fn"; fi
  done
  # Orden: tras comprobar los tokens (paso 5) y antes del reinicio de openbao (paso 6).
  l_cuatro="$(linea_de "$SMOKE" '^firma_worker_200[[:space:]]*$')"
  l_reinicio="$(linea_de "$SMOKE" 'paso "reinicio de openbao"')"
  if [ "$l_cuatro" -gt 0 ] && [ "$l_reinicio" -gt 0 ] && [ "$l_cuatro" -lt "$l_reinicio" ]; then ok "openbao-smoke.sh corre los pasos de firma antes de reiniciar openbao"; else falla "openbao-smoke.sh: los pasos de firma (línea $l_cuatro) deben ir antes del reinicio (línea $l_reinicio)"; fi
  if tiene "$SMOKE" 'bao write[^#]*transit/sign/apex-sign-audit[^#]*input='; then ok "openbao-smoke.sh firma con bao write transit/sign/apex-sign-audit input=<b64>"; else falla "openbao-smoke.sh sin 'bao write transit/sign/apex-sign-audit input='"; fi
  if tiene "$SMOKE" 'bao write[^#]*transit/verify/apex-sign-audit[^#]*signature=' && tiene "$SMOKE" 'valid[^#]*true'; then ok "openbao-smoke.sh verifica con transit/verify y espera valid: true"; else falla "openbao-smoke.sh sin verificación (signature=) con valid: true"; fi
  if tiene "$SMOKE" 'transit/keys/apex-sign-audit/rotate'; then ok "openbao-smoke.sh intenta rotar apex-sign-audit con el token de tools"; else falla "openbao-smoke.sh no intenta transit/keys/apex-sign-audit/rotate"; fi
  # cuerpo_de <función>: el cuerpo de una función del humo (de «nombre() {» al «}» de columna 0).
  cuerpo_de() { tr -d '\015' < "$SMOKE" | awk -v n="$1" 'index($0, n "() {") == 1 { d = 1; next } d && /^}/ { exit } d { print }'; }
  for fn in firma_api_403 rota_tools_403; do
    if cuerpo_de "$fn" | grep -q '403' && ! cuerpo_de "$fn" | grep -q 'pendiente del Verde'; then ok "openbao-smoke.sh: $fn comprueba el 403"; else falla "openbao-smoke.sh: $fn no comprueba el 403 (sigue en rojo)"; fi
  done
  if cuerpo_de firma_worker_200 | grep -q '200' && ! cuerpo_de firma_worker_200 | grep -q 'pendiente del Verde'; then ok "openbao-smoke.sh: firma_worker_200 comprueba el 200"; else falla "openbao-smoke.sh: firma_worker_200 no comprueba el 200 (sigue en rojo)"; fi
  if ! cuerpo_de verifica_api_valid | grep -q 'pendiente del Verde' && cuerpo_de verifica_api_valid | grep -q 'valid'; then ok "openbao-smoke.sh: verifica_api_valid comprueba valid"; else falla "openbao-smoke.sh: verifica_api_valid no comprueba valid (sigue en rojo)"; fi
  if tr -d '\015' < "$SMOKE" | grep -q 'pendiente del Verde'; then falla "openbao-smoke.sh conserva marcas «pendiente del Verde» (Rojo S6-W0-3)"; else ok "openbao-smoke.sh sin marcas de Rojo"; fi
  # Los tokens se leen del volumen de cada servicio y viajan por el entorno (-e BAO_TOKEN), nunca por argv ni impresos.
  if tiene "$SMOKE" '/run/apex/openbao/token' && tiene "$SMOKE" 'exec[^#]*-e BAO_TOKEN[^#]*openbao'; then ok "openbao-smoke.sh lee el token del volumen y lo pasa con exec -e BAO_TOKEN"; else falla "openbao-smoke.sh sin lectura del token del volumen ni exec -e BAO_TOKEN"; fi
  if codigo "$SMOKE" | grep -E '(echo|printf)[^|#]*\$\{?[A-Za-z_]*TOK' | grep -Eq .; then falla "openbao-smoke.sh imprime una variable de token"; else ok "openbao-smoke.sh no imprime variables de token"; fi
  if codigo "$SMOKE" | grep -Eq 'BAO_TOKEN=[A-Za-z0-9]|X-Vault-Token: *[A-Za-z0-9]|-token[= ]'; then falla "openbao-smoke.sh con un token en argv"; else ok "openbao-smoke.sh sin tokens literales ni -token en argv"; fi
  if tr -d '\015' < "$SMOKE" | sed -n '2,45p' | grep -q 'apex-sign-audit'; then ok "openbao-smoke.sh documenta los pasos de firma en la cabecera"; else falla "openbao-smoke.sh no documenta los pasos de firma en la cabecera"; fi
else
  falla "no existe $SMOKE"
fi

# --- Rojo S6-W0-3 · ci.yml: la política del token de CI cubre firma y verificación (S5-D264) --------
echo "-- ci.yml · S6-W0-3 (Rojo)"
CIYML=.github/workflows/ci.yml
if [ -f "$CIYML" ]; then
  if tiene "$CIYML" 'transit/sign/\*'; then ok "ci.yml: la política de apex-ci concede transit/sign/*"; else falla "ci.yml sin transit/sign/* en la política de apex-ci (Rojo S6-W0-3)"; fi
  if tiene "$CIYML" 'transit/verify/\*'; then ok "ci.yml: la política de apex-ci concede transit/verify/*"; else falla "ci.yml sin transit/verify/* en la política de apex-ci (Rojo S6-W0-3)"; fi
  if tiene "$CIYML" 'apex-sign-audit'; then ok "ci.yml crea apex-sign-audit"; else falla "ci.yml no crea apex-sign-audit"; fi
else
  falla "no existe $CIYML"
fi

resumen
[ "$fallas" -eq 0 ]
