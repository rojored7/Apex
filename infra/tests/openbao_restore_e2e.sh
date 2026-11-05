#!/usr/bin/env bash
# openbao_restore_e2e.sh: restauración de OpenBao desde su instantánea raft, de punta a punta
# (S5-B13; S5-D8, S5-D75, S5-D76, S5-D95, S5-D107, S5-D172; H-1).
#
# Prueba la PAREJA completa con las imágenes reales y el código real de run.sh y restore.sh:
#   1. OpenBao `raft` (infra/openbao/config.hcl) nuevo: init 5/3, desello, transit, `apex-kek`
#      (aes256-gcm96, no exportable), las políticas del repo y los tokens de `tools` y de `backup`
#      (apex-backup-snapshot); el token de backup entra por un volumen :ro como en compose.yml.
#   2. S5-D95 (sin `migrate-provider`, que nace en B2): se envuelve una cadena aleatoria con
#      `transit/encrypt/apex-kek` y el token de tools, y se guarda el texto cifrado.
#   3. `run.sh` del servicio backup deja `<name>-openbao.snap.age` y un `latest.json` con
#      `openbao_snapshot.verified=true` y su `.minisig` (verificado con `minisign -V`).
#   4. Desastre: se borra el contenedor y el volumen de OpenBao; arranca uno vacío.
#   5. Restauración: init de un clúster NUEVO (llaves distintas, raíz inicial EFÍMERA; es lo que
#      sustituye al `generate-root` cuando el volumen está vacío) y `restore.sh --with-openbao`
#      (la base `apex_restore` y la instantánea, en pareja) con esa raíz.
#   6. OpenBao queda sellado: las llaves NUEVAS no lo desellan; las ORIGINALES (paso 1, solo en
#      memoria) sí, y `transit/decrypt` con el token de tools devuelve EXACTAMENTE la cadena.
#   7. Negativos: el token de backup no descifra (403) y el de api no pide la instantánea (403);
#      sin `--openbao-token-file`, `restore.sh --with-openbao` sale con 2 sin tocar nada.
# Todo es desechable: red, volúmenes y contenedores llevan el prefijo apex-obe2e- y el sufijo del
# proceso; nunca toca `apex`, `apex-smoke` ni `apex-ensayo`. Variables: BACKUP_IMG (por omisión
# apex-backup:local), OPENBAO_IMG (la fijada en compose.yml), KEEP_WORK=1. Linux o Docker Desktop.
# Nunca imprime llaves, tokens ni la cadena de prueba; sin `set -x`.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
BACKUP_IMG="${BACKUP_IMG:-apex-backup:local}"
OPENBAO_IMG="${OPENBAO_IMG:-$(grep -m1 -oE 'openbao/openbao:[0-9.]+@sha256:[0-9a-f]{64}' infra/compose.yml)}"
[ -n "$OPENBAO_IMG" ] || { echo "openbao_restore_e2e: no se encontró la imagen de OpenBao en compose.yml" >&2; exit 1; }
P="apex-obe2e-$$"
NET="$P-net"; V_DATA="$P-data"; V_TOK="$P-tokbk"; V_BK="$P-backups"; V_UP="$P-uploads"; V_RT="$P-rt"
C_OB="$P-openbao"; C_DB="$P-db"
fallas=0
ok() { echo "  ok   $1"; }
falla() { echo "  FALLA $1" >&2; fallas=$((fallas + 1)); }
muere() { echo "openbao_restore_e2e: $1" >&2; exit 1; }
nativa() { if command -v cygpath > /dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
dk() { MSYS_NO_PATHCONV=1 docker "$@"; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/obe2e.XXXXXX")"
mkdir -p "$WORK/k"
chmod 755 "$WORK"; chmod 777 "$WORK/k"
limpiar() {
  if [ "${OBE2E_KEEP:-0}" = "1" ]; then echo "openbao_restore_e2e: OBE2E_KEEP=1, recursos $P conservados" >&2; return 0; fi
  docker rm -f "$C_OB" "$C_DB" > /dev/null 2>&1 || true
  docker volume rm -f "$V_DATA" "$V_TOK" "$V_BK" "$V_UP" "$V_RT" > /dev/null 2>&1 || true
  docker network rm "$NET" > /dev/null 2>&1 || true
  if [ "${KEEP_WORK:-0}" != "1" ]; then rm -rf "$WORK"; fi
}
trap limpiar EXIT

docker network create --internal "$NET" > /dev/null
for v in "$V_TOK" "$V_BK" "$V_UP" "$V_RT"; do
  docker volume create "$v" > /dev/null
  dk run --rm -v "$v:/d" --entrypoint chown "$BACKUP_IMG" -R 10001:10001 /d 2> /dev/null \
    || dk run --rm --user 0 -v "$v:/d" --entrypoint chown "$BACKUP_IMG" -R 10001:10001 /d
done

# --- claves efímeras: age (cifrado y verificación) y minisign ----------------------------------
dk run --rm -v "$(nativa "$WORK/k"):/k" --entrypoint sh "$BACKUP_IMG" -c \
  'age-keygen -o /tmp/id.txt 2>/dev/null && cp /tmp/id.txt /k/id.txt && grep "^# public key:" /tmp/id.txt | sed "s/^# public key: //" > /k/age.pub && minisign -G -W -f -p /k/sign.pub -s /k/sign.key >/dev/null && chmod 644 /k/*'
AGE_PUB="$(tr -d '\r\n' < "$WORK/k/age.pub")"

# --- helpers de OpenBao -----------------------------------------------------------------------
arrancar_openbao() {
  dk run -d --name "$C_OB" --network "$NET" --network-alias openbao --user 100:1000 --read-only --tmpfs /tmp \
    --cap-drop ALL --security-opt no-new-privileges:true -v "$V_DATA:/openbao/file" \
    -v "$(nativa "$ROOT/infra/openbao/config.hcl"):/openbao/config/config.hcl:ro" \
    -v "$(nativa "$ROOT/infra/openbao/policies"):/policies:ro" \
    --entrypoint bao "$OPENBAO_IMG" server -config=/openbao/config/config.hcl > /dev/null
  local n=0
  until dk exec "$C_OB" wget -q -O /dev/null "http://127.0.0.1:8200/v1/sys/health?sealedcode=200&uninitcode=200" 2> /dev/null; do
    n=$((n + 1)); [ "$n" -le 40 ] || { docker logs "$C_OB" 2>&1 | tail -5 >&2; muere "OpenBao no respondió"; }; sleep 1
  done
}
# bao_con <token> <args...>: el token entra por la primera línea de stdin (nunca por el argv); el
# resto de stdin llega a bao (p. ej. `plaintext=-`).
bao_con() {
  local tok="$1"; shift
  { printf '%s\n' "$tok"; cat; } | dk exec -i -e BAO_ADDR=http://127.0.0.1:8200 "$C_OB" \
    sh -c 'read -r BAO_TOKEN; export BAO_TOKEN; exec bao "$@"' _ "$@"
}
inicializar() { # deja KEYS (una por línea) y RAIZ
  local salida
  salida="$(dk exec -e BAO_ADDR=http://127.0.0.1:8200 "$C_OB" bao operator init -key-shares=5 -key-threshold=3 -format=json | tr -d ' \n')"
  KEYS="$(printf '%s' "$salida" | sed -n 's/.*"unseal_keys_b64":\[\([^]]*\)\].*/\1/p' | tr ',' '\n' | tr -d '"')"
  RAIZ="$(printf '%s' "$salida" | sed -n 's/.*"root_token":"\([^"]*\)".*/\1/p')"
  salida=""
  [ "$(printf '%s\n' "$KEYS" | wc -l | tr -d ' ')" = "5" ] && [ -n "$RAIZ" ] || muere "init no devolvió 5 llaves y una raíz"
}
desellar() { # <llaves> -> 0 si queda desellado
  local k n=0
  while IFS= read -r k; do
    [ -n "$k" ] || continue
    n=$((n + 1)); [ "$n" -le 3 ] || break
    # sys/unseal por la API con la llave en stdin (como bootstrap.sh); `bao operator unseal -` no lee stdin.
    printf '{"key":"%s"}' "$k" | dk exec -i "$C_OB" wget -q -O /dev/null --header 'Content-Type: application/json' --post-file=/dev/stdin http://127.0.0.1:8200/v1/sys/unseal > /dev/null 2>&1 || true
  done <<< "$1"
  [ "$(dk exec "$C_OB" wget -q -O - http://127.0.0.1:8200/v1/sys/seal-status | tr -d ' ' | sed -n 's/.*"sealed":\([a-z]*\).*/\1/p')" = "false" ]
}

# --- 1. OpenBao nuevo, transit, políticas y tokens -------------------------------------------
echo "openbao_restore_e2e: proyecto $P (desechable)"
docker volume create "$V_DATA" > /dev/null
arrancar_openbao
inicializar; KEYS_ORIG="$KEYS"; RAIZ_ORIG="$RAIZ"; KEYS=""; RAIZ=""
desellar "$KEYS_ORIG" && ok "OpenBao inicializado (5/3) y desellado" || muere "no se pudo desellar"
echo -n | bao_con "$RAIZ_ORIG" secrets enable transit > /dev/null
echo -n | bao_con "$RAIZ_ORIG" write -f transit/keys/apex-kek type=aes256-gcm96 exportable=false allow_plaintext_backup=false > /dev/null
for pol in apex-api apex-tools apex-backup-snapshot; do
  echo -n | bao_con "$RAIZ_ORIG" policy write "$pol" "/policies/$pol.hcl" > /dev/null
done
token_de() { echo -n | bao_con "$RAIZ_ORIG" token create -policy="$1" -period=768h -orphan -no-default-policy -field=token; }
TOK_TOOLS="$(token_de apex-tools)"; TOK_API="$(token_de apex-api)"; TOK_BK="$(token_de apex-backup-snapshot)"
printf '%s' "$TOK_BK" | dk run --rm -i -v "$V_TOK:/t" --user 10001:10001 --entrypoint sh "$BACKUP_IMG" -c 'umask 077; cat > /t/token'
ok "políticas y tokens (tools, api, backup) emitidos; el de backup en su volumen"

# --- 2. cadena de prueba envuelta con apex-kek (S5-D95) ---------------------------------------
CLARO="$(head -c 24 /dev/urandom | base64 | tr -d '\n')"
CLARO_B64="$(printf '%s' "$CLARO" | base64 | tr -d '\n')"
CIFRADO="$(printf '%s' "$CLARO_B64" | bao_con "$TOK_TOOLS" write -field=ciphertext transit/encrypt/apex-kek plaintext=-)"
case "$CIFRADO" in vault:v1:*) ok "cadena de prueba envuelta con apex-kek" ;; *) muere "transit/encrypt no devolvió vault:v1" ;; esac

# --- 3. respaldo con instantánea --------------------------------------------------------------
dk run -d --name "$C_DB" --network "$NET" --network-alias db -e POSTGRES_HOST_AUTH_METHOD=trust postgres:16-alpine > /dev/null
# S5-D182: por TCP, no por socket: el servidor temporal del initdb solo escucha por socket y responde a
# pg_isready/psql mientras se está apagando ("the database system is shutting down").
n=0; until dk exec "$C_DB" pg_isready -h 127.0.0.1 -U postgres > /dev/null 2>&1; do n=$((n + 1)); [ "$n" -le 60 ] || muere "postgres no arrancó"; sleep 1; done
dk exec "$C_DB" psql -h 127.0.0.1 -U postgres -c "CREATE DATABASE apex_restore" > /dev/null
dk exec "$C_DB" psql -h 127.0.0.1 -U postgres -c "CREATE TABLE IF NOT EXISTS pareja (n int)" > /dev/null
run_backup() {
  dk run --rm --network "$NET" -e PGHOST=db -e PGUSER=postgres -e PGDATABASE=postgres -e "BACKUP_AGE_RECIPIENT=$AGE_PUB" \
    -v "$V_BK:/data/backups" -v "$V_UP:/data/uploads" -v "$(nativa "$WORK/k")/sign.key:/run/apex/backup/sign.key:ro" \
    -v "$(nativa "$WORK/k")/id.txt:/run/apex/backup/verify.key:ro" -v "$V_TOK:/run/apex/openbao-backup:ro" \
    --tmpfs /tmp --read-only --cap-drop ALL --entrypoint /opt/backup/run.sh "$BACKUP_IMG"
}
SALIDA_RUN="$(run_backup 2>&1)" || { echo "$SALIDA_RUN" | tail -5 >&2; falla "run.sh con token montado terminó con error"; }
MANIFIESTO="$(dk run --rm -v "$V_BK:/b:ro" --entrypoint sh "$BACKUP_IMG" -c 'cat /b/latest.json')"
case "$MANIFIESTO" in *'"openbao_snapshot"'*'"verified": true'*) ok "el manifiesto trae openbao_snapshot con verified=true" ;; *) falla "el manifiesto no trae openbao_snapshot verificado" ;; esac
dk run --rm -v "$V_BK:/b:ro" -v "$(nativa "$WORK/k"):/k:ro" --entrypoint sh "$BACKUP_IMG" -c 'minisign -V -m /b/latest.json -x /b/latest.json.minisig -p /k/sign.pub' > /dev/null 2>&1 \
  && ok "latest.json firmado: minisign -V verifica" || falla "la firma de latest.json no verifica"
dk run --rm -v "$V_BK:/b:ro" --entrypoint sh "$BACKUP_IMG" -c 'ls /b | grep -q -- "-openbao.snap.age$"' \
  && ok "existe <name>-openbao.snap.age" || falla "falta el archivo -openbao.snap.age"
dk run --rm -v "$V_BK:/b:ro" --entrypoint sh "$BACKUP_IMG" -c 'for f in /b/*-openbao.snap.age; do head -c 40 "$f" | grep -q "age-encryption.org" || exit 1; done' \
  && ok "la instantánea está cifrada con age" || falla "la instantánea no es un archivo age"

# --- 4. desastre ---------------------------------------------------------------------------------
docker rm -f "$C_OB" > /dev/null; docker volume rm -f "$V_DATA" > /dev/null
docker volume create "$V_DATA" > /dev/null
arrancar_openbao
[ "$(dk exec "$C_OB" wget -q -O - http://127.0.0.1:8200/v1/sys/seal-status 2> /dev/null | tr -d ' ' | sed -n 's/.*"initialized":\([a-z]*\).*/\1/p')" = "false" ] \
  && ok "desastre: OpenBao vuelve vacío y sin inicializar" || falla "OpenBao no quedó vacío"

# --- 5. restauración en pareja -------------------------------------------------------------------
inicializar; KEYS_NUEVAS="$KEYS"; RAIZ_NUEVA="$RAIZ"; KEYS=""; RAIZ=""
desellar "$KEYS_NUEVAS" && ok "clúster nuevo inicializado y desellado con llaves NUEVAS" || muere "no se pudo desellar el clúster nuevo"
# La raiz efimera del init nuevo va a un volumen propio, archivo 600 de uid 10001 (restore.sh exige 600; S5-D181).
printf '%s' "$RAIZ_NUEVA" | dk run --rm -i -v "$V_RT:/t" --user 10001:10001 --entrypoint sh "$BACKUP_IMG" -c 'umask 077; cat > /t/token; chmod 600 /t/token'
restore() { # <args extra de restore.sh...>
  dk run --rm --network "$NET" -e PGHOST=db -e PGUSER=postgres -e PGDATABASE=apex_restore \
    -v "$V_BK:/data/backups" -v "$V_UP:/data/uploads" -v "$(nativa "$WORK/k"):/k:ro" -v "$V_RT:/rt:ro" \
    -e "BACKUP_AGE_RECIPIENT=$AGE_PUB" -v "$(nativa "$WORK/k")/sign.key:/run/apex/backup/sign.key:ro" \
    --tmpfs /tmp --entrypoint /opt/backup/restore.sh "$BACKUP_IMG" /data/backups/latest.json \
    -i /k/id.txt -P /k/sign.pub --confirm-database apex_restore "$@"
}
RC=0; SALIDA_R="$(restore --with-openbao 2>&1)" || RC=$?
[ "$RC" = "2" ] && ok "sin --openbao-token-file, --with-openbao sale con 2 y no toca nada" || falla "--with-openbao sin token debía salir con 2 (salió $RC)"
RC=0; SALIDA_R="$(restore --with-openbao --openbao-token-file /rt/token 2>&1)" || RC=$?
if [ "$RC" = "0" ]; then ok "restore.sh --with-openbao restaura la base y la instantánea"; else echo "$SALIDA_R" | tail -6 >&2; falla "restore.sh --with-openbao salió con $RC"; fi
case "$SALIDA_R" in *"llaves originales"*) ok "restore.sh avisa que hay que desellar con las llaves originales" ;; *) falla "restore.sh no avisó de las llaves originales" ;; esac

# --- 6. desello con las originales y descifrado ---------------------------------------------------
n=0; until dk exec "$C_OB" wget -q -O /dev/null "http://127.0.0.1:8200/v1/sys/health?sealedcode=200&uninitcode=200" 2> /dev/null; do n=$((n + 1)); [ "$n" -le 20 ] || break; sleep 1; done
# Hallazgo del ensayo real: tras `snapshot-force` OpenBao sigue desellado con la llave en memoria del
# clúster nuevo; el estado restaurado solo manda al reiniciar. Hay que reiniciar (o sellar) y desellar
# con las llaves ORIGINALES (docs/operacion/openbao.md).
docker restart "$C_OB" > /dev/null
n=0; until dk exec "$C_OB" wget -q -O /dev/null "http://127.0.0.1:8200/v1/sys/health?sealedcode=200&uninitcode=200" 2> /dev/null; do n=$((n + 1)); [ "$n" -le 40 ] || break; sleep 1; done
SELLADO="$(dk exec "$C_OB" wget -q -O - http://127.0.0.1:8200/v1/sys/seal-status | tr -d ' ' | sed -n 's/.*"sealed":\([a-z]*\).*/\1/p')"
if [ "$SELLADO" = "true" ]; then ok "tras reiniciar OpenBao restaurado queda sellado"; else falla "OpenBao debía quedar sellado tras reiniciar (sealed=$SELLADO)"; fi
desellar "$KEYS_NUEVAS" && falla "las llaves NUEVAS no deberían desellar" || ok "las llaves del clúster nuevo no desellan"
desellar "$KEYS_ORIG" && ok "las llaves ORIGINALES desellan" || falla "las llaves originales no desellaron"
DESCIFRADO="$(printf '' | bao_con "$TOK_TOOLS" write -field=plaintext transit/decrypt/apex-kek "ciphertext=$CIFRADO" 2> /dev/null || true)"
[ -n "$DESCIFRADO" ] && [ "$(printf '%s' "$DESCIFRADO" | base64 -d 2> /dev/null)" = "$CLARO" ] \
  && ok "transit/decrypt devuelve exactamente la cadena original" || falla "transit/decrypt no devolvió la cadena original"

# --- 7. negativos de política ---------------------------------------------------------------------
printf '' | bao_con "$TOK_BK" write -field=plaintext transit/decrypt/apex-kek "ciphertext=$CIFRADO" > /dev/null 2>&1 \
  && falla "el token de backup pudo descifrar" || ok "el token de backup no descifra (403)"
printf '' | bao_con "$TOK_API" read sys/storage/raft/snapshot > /dev/null 2>&1 \
  && falla "el token de api pudo pedir la instantánea" || ok "el token de api no pide la instantánea (403)"

echo "openbao_restore_e2e: $fallas fallas"
[ "$fallas" -eq 0 ]
