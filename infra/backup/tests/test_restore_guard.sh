#!/usr/bin/env bash
# Pruebas de las guardas de infra/backup/restore.sh (S4B-B3a, US-116; S4B-D42, D57, D97).
#
# Rojo: restore.sh es un stub que sale con 99. Bash puro; en el host con `psql`, `pg_restore`,
# `age` y `minisign` FALSOS (carpeta bin del caso, primera en el PATH) y `tar` REAL; en CI los
# binarios de apex-backup:ci reemplazan a los falsos. Cada caso copia restore.sh y lib.sh a
# `opt/` y pone un run.sh falso al lado (restore.sh lo busca junto a sí mismo).
#
# Contrato que fija este archivo (lo implementa el Verde):
#   restore.sh <manifiesto.json> -i <identidad> -P <pubkey> --confirm-database <nombre>
#              [--i-know-this-overwrites] [--i-know-unsigned --sha256-db <hex> --sha256-uploads <hex>]
#   - la firma es <manifiesto>.minisig; los dos archivos están en la carpeta del manifiesto;
#   - la base y la credencial salen del entorno (PGDATABASE, PGHOST, PGUSER, PGPASSWORD); la
#     credencial nunca va en argv ni en la salida;
#   - APEX_RESTORE_DATA_ROOT (por defecto /data) recibe uploads/ y APEX_RESTORE_TMP (por defecto
#     /tmp, un tmpfs en el contenedor) es el directorio de trabajo;
#   - orden: argumentos y confirmaciones -> firma (minisign) -> sha256 de los archivos ->
#     inspección del tar (age -d | tar -tv) -> guarda de filas -> run.sh --prefix pre-restore ->
#     pg_restore -> extracción de uploads. Toda negativa sale con 2 SIN llamar a pg_restore;
#   - la guarda de filas consulta con psql `count(*)` sobre members.members, payments.payments y
#     audit.audit_log (el psql falso devuelve el contenido de fake/rows, por defecto 0).
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"
LIB="$BACKUP_DIR_SRC/lib.sh"
RESTORE_SRC="$BACKUP_DIR_SRC/restore.sh"
SENTINELA="S3NT1NELA-credencial-del-propietario"

echo "test_restore_guard"
if [ ! -f "$RESTORE_SRC" ]; then
  _fail "existe $RESTORE_SRC"
  finish
  exit
fi
# shellcheck source=/dev/null
source "$LIB"
if ! have_python; then
  echo "  (sin Python no se construyen los tar de prueba: caso omitido)"
  finish
  exit
fi

NOMBRE="apex-20261021-070005"

make_tar() { # <salida> ok|dotdot|symlink|absoluta|fuera
  py - "$1" "$2" << 'PYEOF'
import sys, tarfile, io
salida, modo = sys.argv[1], sys.argv[2]
contenido = b"foto"
with tarfile.open(salida, "w", format=tarfile.USTAR_FORMAT) as t:
    def archivo(nombre):
        info = tarfile.TarInfo(nombre)
        info.size = len(contenido)
        t.addfile(info, io.BytesIO(contenido))
    archivo("uploads/ok.txt")
    if modo == "dotdot":
        archivo("uploads/../fuera.txt")
    elif modo == "absoluta":
        archivo("/etc/apex-fuera.txt")
    elif modo == "fuera":
        archivo("otro/x.txt")
    elif modo == "symlink":
        info = tarfile.TarInfo("uploads/enlace")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        t.addfile(info)
PYEOF
}

REAL_SHA="$(command -v sha256sum)"
REAL_TAR="$(command -v tar)"
sha() { sha256sum "$1" | cut -d' ' -f1; }

# nuevo_caso <nombre> [modo-tar]: arma opt/, bin/ (falsos), backups/ (juego firmado), data/, work/.
nuevo_caso() {
  CASO="$TMP_ROOT/$1"
  mkdir -p "$CASO/opt" "$CASO/bin" "$CASO/backups" "$CASO/data" "$CASO/work" "$CASO/fake"
  FAKE="$CASO/fake"
  B="$CASO/backups"
  : > "$FAKE/calls.log"
  echo 0 > "$FAKE/rows"
  cp "$RESTORE_SRC" "$LIB" "$CASO/opt/"

  cat > "$CASO/opt/run.sh" << 'EOF'
#!/bin/bash
echo "run.sh $*" >> "$FAKE/calls.log"
if [ -f "$FAKE/run_fail" ]; then echo "run.sh: ERROR simulado" >&2; exit 1; fi
ts=20261021-080000
echo x > "$BACKUPS/pre-restore-$ts-db.dump.age"
echo x > "$BACKUPS/pre-restore-$ts-uploads.tar.age"
echo '{"name": "pre-restore-20261021-080000"}' > "$BACKUPS/pre-restore-$ts.json"
echo sig > "$BACKUPS/pre-restore-$ts.json.minisig"
exit 0
EOF
  cat > "$CASO/bin/psql" << 'EOF'
#!/bin/bash
echo "psql $*" >> "$FAKE/calls.log"
case "$*" in *count*) cat "$FAKE/rows" ;; esac
exit 0
EOF
  cat > "$CASO/bin/pg_restore" << 'EOF'
#!/bin/bash
echo "pg_restore $*" >> "$FAKE/calls.log"
cat > "$FAKE/pg_stdin"
exit 0
EOF
  cat > "$CASO/bin/age" << 'EOF'
#!/bin/bash
echo "age $*" >> "$FAKE/calls.log"
archivo=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -d) shift ;;
    -i) shift 2 ;;
    *) archivo="$1"; shift ;;
  esac
done
if [ -n "$archivo" ]; then cat "$archivo"; else cat; fi
EOF
  cat > "$CASO/bin/minisign" << 'EOF'
#!/bin/bash
echo "minisign $*" >> "$FAKE/calls.log"
archivo=""; firma=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -m | -Vm) archivo="$2"; shift 2 ;;
    -x) firma="$2"; shift 2 ;;
    *) shift ;;
  esac
done
[ -n "$firma" ] || firma="$archivo.minisig"
if [ -f "$FAKE/minisign_bad" ] || [ ! -f "$firma" ]; then echo "minisign: firma inválida" >&2; exit 1; fi
exit 0
EOF
  # sha256sum falso (M1): calcula con el real y, si existe fake/swap_after_sha, sustituye los .age
  # originales DESPUES de calcular; restore.sh debe seguir usando su copia.
  cat > "$CASO/bin/sha256sum" << EOF
#!/bin/bash
salida="\$("$REAL_SHA" "\$@")"; rc=\$?
if [ -f "\$FAKE/swap_after_sha" ]; then
  for f in "\$BACKUPS"/*-db.dump.age; do echo TAMPERED > "\$f"; done
fi
printf '%s\n' "\$salida"
exit \$rc
EOF
  cat > "$CASO/bin/tar" << EOF
#!/bin/bash
echo "tar \$*" >> "\$FAKE/calls.log"
exec "$REAL_TAR" "\$@"
EOF
  # curl falso (S5-B13): registra la llamada y copia el archivo de configuracion de `-K` (restore.sh lo borra al salir).
  cat > "$CASO/bin/curl" << 'EOF'
#!/bin/bash
echo "curl $*" >> "$FAKE/calls.log"
cfg=""
while [ "$#" -gt 0 ]; do
  case "$1" in -K) cfg="$2"; shift 2 ;; *) shift ;; esac
done
n="$(grep -c '^curl' "$FAKE/calls.log")"
[ -z "$cfg" ] || cp "$cfg" "$FAKE/curl-$n.cfg"
[ -t 0 ] || cat > /dev/null
if [ -n "$cfg" ] && grep -q 'raft/snapshot' "$cfg" && [ -f "$FAKE/curl_fail_snapshot" ]; then echo "curl: (22) simulado" >&2; exit 22; fi
if [ -n "$cfg" ] && grep -q 'revoke-self' "$cfg" && [ -f "$FAKE/curl_fail_revoke" ]; then echo "curl: (22) simulado" >&2; exit 22; fi
exit 0
EOF
  chmod +x "$CASO/opt/run.sh" "$CASO/bin/"*

  # Juego de respaldo: dos archivos "cifrados" (el age falso es transparente) y manifiesto firmado.
  printf 'PGDMP-falso' > "$B/$NOMBRE-db.dump.age"
  make_tar "$B/$NOMBRE-uploads.tar.age" "${2:-ok}"
  printf 'db|%s-db.dump.age|%s|%s|%s\nuploads|%s-uploads.tar.age|%s|%s|%s\n' \
    "$NOMBRE" "$(wc -c < "$B/$NOMBRE-db.dump.age" | tr -d ' ')" "$(sha "$B/$NOMBRE-db.dump.age")" "$(sha "$B/$NOMBRE-db.dump.age")" \
    "$NOMBRE" "$(wc -c < "$B/$NOMBRE-uploads.tar.age" | tr -d ' ')" "$(sha "$B/$NOMBRE-uploads.tar.age")" "$(sha "$B/$NOMBRE-uploads.tar.age")" \
    | manifest_json "$NOMBRE" "2026-10-21T07:00:05Z" "apex_test" ok "2026-10-21T07:00:09Z" skipped "" > "$B/latest.json"
  echo firma > "$B/latest.json.minisig"
  echo identidad > "$CASO/identidad.txt"
  echo pubkey > "$CASO/pub.pub"
}

# correr_restore <args...>: deja el código en RC y la salida (stdout+stderr) en SALIDA.
correr_restore() {
  local rc=0
  SALIDA="$(
    cd "$CASO/work" \
      && env PATH="$CASO/bin:$PATH" FAKE="$FAKE" BACKUPS="$B" PGDATABASE=apex_test PGHOST=db PGUSER=apex \
        PGPASSWORD="$SENTINELA" APEX_RESTORE_DATA_ROOT="$CASO/data" APEX_RESTORE_TMP="$CASO/work" \
        bash "$CASO/opt/restore.sh" "$@" 2>&1
  )" || rc=$?
  RC="$rc"
}

args_ok() { echo "$B/latest.json -i $CASO/identidad.txt -P $CASO/pub.pub --confirm-database apex_test"; }
llamo() { grep -q "^$1" "$FAKE/calls.log"; }
linea() { grep -n "^$1" "$FAKE/calls.log" | head -1 | cut -d: -f1; }
no_toco_la_base() { ! llamo pg_restore && ! llamo run.sh; }

# --- 1. camino feliz sobre una base vacía ----------------------------------------------------
nuevo_caso feliz
LATEST_ANTES="$(sha "$B/latest.json")"
# shellcheck disable=SC2046
correr_restore $(args_ok)
assert_eq "base vacía: sale 0" "0" "$RC"
assert_ok "base vacía: llama a pg_restore" llamo pg_restore
assert_ok "base vacía: restaura los uploads bajo DATA_ROOT/uploads" test -f "$CASO/data/uploads/ok.txt"
assert_lacks "la credencial del propietario no aparece en la salida" "$SALIDA" "$SENTINELA"
assert_lacks "la credencial del propietario no aparece en argv de ningún binario" "$(cat "$FAKE/calls.log")" "$SENTINELA"
assert_lacks "no hay .minisig en la copia de uploads" "$(ls -R "$CASO/data" 2> /dev/null)" "minisig"

# --- 2. orden: firma antes de descifrar; pre-restore antes de pg_restore (S4B-D97) -----------
assert_ok "minisign se llama" llamo minisign
assert_ok "la firma se verifica antes de descifrar" test "$(linea minisign)" -lt "$(linea age)"
assert_ok "run.sh --prefix pre-restore se llama" llamo "run.sh --prefix pre-restore"
assert_ok "pre-restore se toma ANTES de pg_restore" test "$(linea 'run.sh')" -lt "$(linea pg_restore)"
assert_ok "el juego pre-restore deja su .json" test -f "$B/pre-restore-20261021-080000.json"
assert_ok "el juego pre-restore deja su .minisig" test -f "$B/pre-restore-20261021-080000.json.minisig"
assert_eq "latest.json no cambia" "$(printf 'firma')" "$(tr -d '\r\n' < "$B/latest.json.minisig")"
assert_contains "pg_restore con --clean --if-exists --no-owner" "$(grep '^pg_restore' "$FAKE/calls.log")" "--clean --if-exists --no-owner"

# --- 2b. M1: el restore usa su copia, no el original (TOCTOU); M3: pg_restore todo o nada ------
nuevo_caso toctou
: > "$FAKE/swap_after_sha"
# shellcheck disable=SC2046
correr_restore $(args_ok)
assert_eq "TOCTOU: sale 0 aunque el original cambie tras el sha256" "0" "$RC"
assert_eq "TOCTOU: pg_restore recibe la copia verificada, no el original sustituido" "PGDMP-falso" "$(cat "$FAKE/pg_stdin")"
assert_ok "uploads se extraen ANTES de pg_restore" test "$(linea 'tar -x')" -lt "$(linea pg_restore)"
assert_contains "pg_restore con --single-transaction" "$(grep '^pg_restore' "$FAKE/calls.log")" "--single-transaction"
assert_contains "pg_restore con --exit-on-error" "$(grep '^pg_restore' "$FAKE/calls.log")" "--exit-on-error"
assert_contains "pg_restore con --no-acl" "$(grep '^pg_restore' "$FAKE/calls.log")" "--no-acl"
case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*) echo "  (NTFS no guarda modos POSIX: la comprobación de permisos corre en Linux/CI)" ;;
  *) assert_fails "los uploads restaurados no son legibles por grupo ni otros" test -n "$(find "$CASO/data/uploads" -perm /077 2> /dev/null)" ;;
esac
assert_contains "la salida recuerda correr dbsetup" "$SALIDA" "dbsetup"

# --- 2c. L3: la guarda de filas mira las seis tablas ---------------------------------------------
consulta="$(grep '^psql' "$FAKE/calls.log" | grep count | head -1)"
for tabla in members.members payments.payments audit.audit_log auth.users crypto.crypto_keys settings.settings_sections 00000000-0000-0000-0000-000000000001; do
  assert_contains "la guarda de filas incluye $tabla" "$consulta" "$tabla"
done

# --- 3. la guarda de filas --------------------------------------------------------------------
nuevo_caso con_filas
echo 3 > "$FAKE/rows"
# shellcheck disable=SC2046
correr_restore $(args_ok)
assert_eq "base con filas sin --i-know-this-overwrites: sale 2" "2" "$RC"
assert_ok "base con filas: no toca la base ni toma pre-restore" no_toco_la_base
assert_contains "base con filas: lo dice" "$SALIDA" "--i-know-this-overwrites"

nuevo_caso con_filas_forzado
echo 3 > "$FAKE/rows"
# shellcheck disable=SC2046
correr_restore $(args_ok) --i-know-this-overwrites
assert_eq "base con filas y --i-know-this-overwrites: sale 0" "0" "$RC"
assert_ok "con la bandera sí restaura" llamo pg_restore
assert_ok "con la bandera también toma pre-restore antes" test "$(linea 'run.sh')" -lt "$(linea pg_restore)"

# --- 4. pre-restore obligatorio: si run.sh falla no se toca la base (E1, S4B-D97) -------------
nuevo_caso run_falla
: > "$FAKE/run_fail"
# shellcheck disable=SC2046
correr_restore $(args_ok)
assert_eq "run.sh falla: restore.sh sale 1 (fallo en ejecución)" "1" "$RC"
assert_fails "run.sh falla: no llama a pg_restore" llamo pg_restore

# --- 5. confirmaciones ------------------------------------------------------------------------
nuevo_caso sin_confirmar
correr_restore "$B/latest.json" -i "$CASO/identidad.txt" -P "$CASO/pub.pub"
assert_eq "sin --confirm-database: sale 2" "2" "$RC"
assert_ok "sin --confirm-database: no toca la base" no_toco_la_base

nuevo_caso confirmacion_distinta
correr_restore "$B/latest.json" -i "$CASO/identidad.txt" -P "$CASO/pub.pub" --confirm-database otra_base
assert_eq "--confirm-database distinto de PGDATABASE: sale 2" "2" "$RC"
assert_ok "--confirm-database distinto: no toca la base" no_toco_la_base

# --- 6. firma ---------------------------------------------------------------------------------
nuevo_caso sin_pubkey
correr_restore "$B/latest.json" -i "$CASO/identidad.txt" --confirm-database apex_test
assert_eq "sin -P ni --i-know-unsigned: sale 2" "2" "$RC"
assert_ok "sin -P: no toca la base" no_toco_la_base

nuevo_caso firma_ausente
rm -f "$B/latest.json.minisig"
# shellcheck disable=SC2046
correr_restore $(args_ok)
assert_eq ".minisig ausente: sale 2" "2" "$RC"
assert_ok ".minisig ausente: no toca la base" no_toco_la_base
assert_fails ".minisig ausente: no descifra nada" llamo age

nuevo_caso firma_invalida
: > "$FAKE/minisign_bad"
# shellcheck disable=SC2046
correr_restore $(args_ok)
assert_eq ".minisig inválida: sale 2" "2" "$RC"
assert_ok ".minisig inválida: no toca la base" no_toco_la_base
assert_fails ".minisig inválida: no descifra nada" llamo age

nuevo_caso sin_firma_con_hashes
rm -f "$B/latest.json.minisig"
SHA_DB="$(sha "$B/$NOMBRE-db.dump.age")"
SHA_UP="$(sha "$B/$NOMBRE-uploads.tar.age")"
correr_restore "$B/latest.json" -i "$CASO/identidad.txt" --confirm-database apex_test \
  --i-know-unsigned --sha256-db "$SHA_DB" --sha256-uploads "$SHA_UP"
assert_eq "--i-know-unsigned con los sha256 correctos: sale 0" "0" "$RC"
assert_fails "--i-know-unsigned no llama a minisign" llamo minisign

nuevo_caso sin_firma_hash_malo
rm -f "$B/latest.json.minisig"
correr_restore "$B/latest.json" -i "$CASO/identidad.txt" --confirm-database apex_test \
  --i-know-unsigned --sha256-db "$(printf '0%.0s' $(seq 1 64))" --sha256-uploads "$(sha "$B/$NOMBRE-uploads.tar.age")"
assert_eq "--i-know-unsigned con un sha256 equivocado: sale 2" "2" "$RC"
assert_ok "sha256 equivocado: no toca la base" no_toco_la_base

# --- 7. integridad de los archivos ------------------------------------------------------------
nuevo_caso archivo_alterado
printf 'alterado' >> "$B/$NOMBRE-db.dump.age"
# shellcheck disable=SC2046
correr_restore $(args_ok)
assert_eq "archivo con sha256 distinto al del manifiesto: sale 2" "2" "$RC"
assert_ok "archivo alterado: no toca la base" no_toco_la_base

# --- 8. el tar se inspecciona antes de tocar la base (listado con tar -tv) ---------------------
for modo in dotdot symlink absoluta fuera; do
  nuevo_caso "tar_$modo" "$modo"
  # shellcheck disable=SC2046
  correr_restore $(args_ok)
  assert_eq "tar '$modo': sale 2" "2" "$RC"
  assert_ok "tar '$modo': no toca la base" no_toco_la_base
  assert_fails "tar '$modo': no extrae nada a DATA_ROOT" test -e "$CASO/data/uploads/ok.txt"
done


# --- 10. --with-openbao (S5-B13; S5-D175, D179, D181) --------------------------------------------------
# caso_openbao: el juego trae openbao_snapshot y un archivo de token (modo 600).
caso_openbao() {
  nuevo_caso "$1"
  local snap="$NOMBRE-openbao.snap.age"
  printf 'instantanea-falsa' > "$B/$snap"
  printf 'db|%s-db.dump.age|%s|%s|%s\nuploads|%s-uploads.tar.age|%s|%s|%s\n' \
    "$NOMBRE" "$(wc -c < "$B/$NOMBRE-db.dump.age" | tr -d ' ')" "$(sha "$B/$NOMBRE-db.dump.age")" "$(sha "$B/$NOMBRE-db.dump.age")" \
    "$NOMBRE" "$(wc -c < "$B/$NOMBRE-uploads.tar.age" | tr -d ' ')" "$(sha "$B/$NOMBRE-uploads.tar.age")" "$(sha "$B/$NOMBRE-uploads.tar.age")" \
    | manifest_json "$NOMBRE" "2026-10-21T07:00:05Z" "apex_test" ok "2026-10-21T07:00:09Z" skipped "" \
      "$snap|$(wc -c < "$B/$snap" | tr -d ' ')|$(sha "$B/$snap")|true" > "$B/latest.json"
  printf 'hvs.raiz-efimera-0123' > "$CASO/token"
  chmod 600 "$CASO/token"
}
args_ob() { echo "$B/latest.json -i $CASO/identidad.txt -P $CASO/pub.pub --confirm-database apex_test --with-openbao --openbao-token-file $CASO/token"; }
curl_cfg_con() { grep -l "$1" "$FAKE"/curl-*.cfg 2> /dev/null | head -1; }

caso_openbao ob_feliz
# shellcheck disable=SC2046
correr_restore $(args_ob)
assert_eq "--with-openbao: sale 0" "0" "$RC"
assert_ok "--with-openbao: restaura la instantanea (snapshot-force) por curl -K" test -n "$(curl_cfg_con snapshot-force)"
assert_ok "--with-openbao: revoca la raiz efimera tras restaurar (revoke-self)" test -n "$(curl_cfg_con revoke-self)"
assert_contains "--with-openbao: avisa de las llaves originales" "$SALIDA" "llaves originales"
assert_fails "--with-openbao: el token no sale en la salida" grep -q "hvs.raiz" <<< "$SALIDA"
assert_fails "--with-openbao: el token no va en el argv de curl" grep -q "hvs.raiz" "$FAKE/calls.log"
assert_ok "--with-openbao: la instantanea se restaura DESPUES de pg_restore" test "$(linea pg_restore)" -lt "$(linea curl)"

caso_openbao ob_revoke_ignorado
touch "$FAKE/curl_fail_revoke"
# shellcheck disable=SC2046
correr_restore $(args_ob)
assert_eq "--with-openbao: si la revocacion final falla se ignora con nota (sale 0)" "0" "$RC"
assert_contains "--with-openbao: la nota de revocacion ignorada" "$SALIDA" "revocar la raíz"

caso_openbao ob_sin_firma
# shellcheck disable=SC2046
correr_restore $B/latest.json -i "$CASO/identidad.txt" --confirm-database apex_test --i-know-unsigned \
  --sha256-db "$(sha "$B/$NOMBRE-db.dump.age")" --sha256-uploads "$(sha "$B/$NOMBRE-uploads.tar.age")" \
  --with-openbao --openbao-token-file "$CASO/token"
assert_eq "--with-openbao con --i-know-unsigned: sale 2" "2" "$RC"
assert_contains "--with-openbao con --i-know-unsigned: mensaje fijo" "$SALIDA" "--with-openbao no es compatible con --i-know-unsigned"
assert_ok "--with-openbao con --i-know-unsigned: no toca la base" no_toco_la_base
assert_fails "--with-openbao con --i-know-unsigned: no llama a curl" llamo curl

caso_openbao ob_token_directorio
mkdir -p "$CASO/dirtoken"
# shellcheck disable=SC2046
correr_restore $B/latest.json -i "$CASO/identidad.txt" -P "$CASO/pub.pub" --confirm-database apex_test --with-openbao --openbao-token-file "$CASO/dirtoken"
assert_eq "--openbao-token-file que no es un archivo regular: sale 2" "2" "$RC"
assert_ok "token no regular: no toca la base" no_toco_la_base

caso_openbao ob_token_enlace
if ln -s "$CASO/token" "$CASO/token-enlace" 2> /dev/null && [ -L "$CASO/token-enlace" ]; then
  # shellcheck disable=SC2046
  correr_restore $B/latest.json -i "$CASO/identidad.txt" -P "$CASO/pub.pub" --confirm-database apex_test --with-openbao --openbao-token-file "$CASO/token-enlace"
  assert_eq "--openbao-token-file como enlace simbolico: sale 2" "2" "$RC"
  assert_ok "token como enlace: no toca la base" no_toco_la_base
else
  echo "  (sin enlaces simbolicos en este equipo: caso omitido)"
fi

if [ "$(uname -s)" = "Linux" ]; then
  caso_openbao ob_token_modo
  chmod 644 "$CASO/token"
  # shellcheck disable=SC2046
  correr_restore $(args_ob)
  assert_eq "--openbao-token-file con modo 644: sale 2" "2" "$RC"
  assert_contains "token con modo distinto de 600: mensaje fijo" "$SALIDA" "modo 600"
  assert_ok "token con modo 644: no toca la base" no_toco_la_base
else
  echo "  (la comprobacion de modo 600 solo corre en Linux: caso omitido)"
fi

caso_openbao ob_fallo_previo
touch "$FAKE/run_fail"
# shellcheck disable=SC2046
correr_restore $(args_ob)
assert_eq "--with-openbao: si el respaldo previo falla sale 1" "1" "$RC"
assert_ok "--with-openbao: el camino de fallo revoca la raiz del init nuevo" test -n "$(curl_cfg_con revoke-self)"
assert_fails "--with-openbao: el camino de fallo no restaura la instantanea" test -n "$(curl_cfg_con snapshot-force)"

caso_openbao ob_fallo_snapshot
touch "$FAKE/curl_fail_snapshot"
# shellcheck disable=SC2046
correr_restore $(args_ob)
assert_eq "--with-openbao: si la restauracion de la instantanea falla sale 1" "1" "$RC"
assert_ok "--with-openbao: tras el fallo de la instantanea tambien se revoca la raiz" test -n "$(curl_cfg_con revoke-self)"

caso_openbao ob_guarda_filas
echo 5 > "$FAKE/rows"
# shellcheck disable=SC2046
correr_restore $(args_ob)
assert_eq "--with-openbao: la guarda de filas (antes de tocar nada) sigue saliendo 2" "2" "$RC"
assert_fails "--with-openbao: una negativa previa no revoca la raiz (se puede reintentar)" test -n "$(curl_cfg_con revoke-self)"

# --- 9. estática: nunca set -x, sin credencial en la línea de comandos -------------------------
cuerpo="$(cat "$RESTORE_SRC")"
assert_ok "restore.sh pasa bash -n" bash -n "$RESTORE_SRC"
assert_contains "restore.sh con set -euo pipefail" "$cuerpo" "set -euo pipefail"
assert_fails "restore.sh sin set -x" grep -Eq '(^|[[:space:];])set -[a-z]*x' "$RESTORE_SRC"
assert_fails "restore.sh sin PGPASSWORD= en una línea de comandos" grep -Eq 'PGPASSWORD=' "$RESTORE_SRC"
assert_fails "restore.sh sin --password" grep -Eq -- '--password' "$RESTORE_SRC"
assert_contains "restore.sh extrae con --no-same-owner" "$cuerpo" "--no-same-owner"
assert_contains "restore.sh extrae con --no-same-permissions" "$cuerpo" "--no-same-permissions"

finish
