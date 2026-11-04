#!/usr/bin/env bash
# test_deploy_script.sh: pruebas de infra/deploy.sh con docker, git, curl, sleep y stat FALSOS
# (S4B-B4, US-117, paso 78; S4B-D41, D67, D78, D94). Bash puro. No toca ningun daemon ni repo.
#
# Contrato que fija este archivo (lo implementa el Verde, paso 80):
#   deploy.sh --ref <vX.Y.Z> --expect-sha <40 hex> [--kek-file <ruta>] [--i-know-no-backup]
#             [--i-know-unsigned-ref]
#   - salidas: 0 ok; 2 uso o preverificacion (sin tocar docker salvo `compose ... config -q`);
#     distinto de 0 si falla algo posterior (respaldo, build); la salud falla con 1;
#   - la raiz es el padre de infra/ (se calcula desde la ruta del script, no desde el cwd);
#   - --ref con forma vX.Y.Z (nunca main); --expect-sha de 40 hex; ambos obligatorios;
#   - orden: argumentos -> git (fetch --tags, rev-parse REF^{commit} == SHA, verify-tag solo si
#     existe .github/allowed_signers, checkout -q, status --porcelain vacio) -> archivos (.env y
#     .env.ops presentes, modo `stat -c %a` <= 600, propietario `stat -c %u` == `id -u`, no
#     rastreados con `git ls-files --error-unmatch`, sin `cambiar-esto`, .env sin ^POSTGRES_ ni
#     ^DATABASE_URL=, APEX_{API,WORKER,BACKUP}_DB_PASSWORD de >= 24 caracteres y distintas,
#     --kek-file legible, BACKUP_AGE_RECIPIENT y BACKUP_SIGN_PUBKEY no vacios salvo con
#     --i-know-no-backup) -> `docker compose --env-file .env --env-file .env.ops -f
#     infra/compose.yml config -q` -> db en marcha (`compose ... ps ... db` imprime algo; si no,
#     salida 2) -> respaldo `compose ... run --rm backup /opt/backup/run.sh --prefix pre-deploy`
#     (se toma el nombre de la linea `run.sh: listo pre-deploy-AAAAMMDD-HHMMSS`) y comprobacion
#     de los dos archivos, .minisig y cabecera age mediante otro `compose ... run|exec` (sin
#     nombrar run.sh) -> `docker tag` de las tres imagenes a `:prev-<fecha>` y
#     <DEPLOY_STATE_DIR>/deploy-<fecha>.state.json -> `compose ... build` (o, con
#     DEPLOY_SKIP_BUILD=1, `docker image inspect` de la etiqueta OCI revision == REF, si no 2)
#     -> `compose ... up -d` -> sondeo con curl de http://127.0.0.1:$WEB_PORT/api/v1/health cada
#     3 s (sleep) hasta DEPLOY_HEALTH_TIMEOUT, exito con "db":"ok" y "migrations":"ok" en el
#     cuerpo -> lectura de /proc/1/environ del api (S4B-D56) -> exito imprime la `version`;
#     fallo imprime 100 lineas del log del api (`logs --tail 100 api`) y escribe
#     <DEPLOY_STATE_DIR>/rollback-<fecha>.txt;
#   - variables: DEPLOY_NOW (AAAAMMDD-HHMMSS, solo pruebas), DEPLOY_STATE_DIR (por omision
#     FUERA del repo, para no ensuciar el arbol), DEPLOY_HEALTH_TIMEOUT (por omision 120),
#     DEPLOY_SKIP_BUILD, WEB_PORT (del .env.ops);
#   - deploy-<fecha>.state.json (sin jq) lleva las claves "ref", "sha", "prev_tag", "manifest" y
#     "images"; rollback-<fecha>.txt nombra las etiquetas prev-*, la ruta del manifiesto y la
#     frase "este script no restaura la base", y no contiene PASSWORD, SECRET ni AGE-SECRET.
# Fallo esperado en el Rojo: el stub sale con 99.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
SRC_DEPLOY="$ROOT/infra/deploy.sh"
FAKES_SRC="$ROOT/scripts/ci/fakes"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/apex-deploy-tests.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT
PASSES=0
FAILS=0
_ok() { PASSES=$((PASSES + 1)); echo "  ok   $1"; }
_fail() { FAILS=$((FAILS + 1)); echo "  FALLA $1"; }
assert_eq() { if [ "$2" = "$3" ]; then _ok "$1"; else _fail "$1 (esperado '$2', obtenido '$3')"; fi; }
assert_contains() { case "$2" in *"$3"*) _ok "$1" ;; *) _fail "$1 (no contiene '$3')" ;; esac; }
assert_lacks() { case "$2" in *"$3"*) _fail "$1 (contiene '$3')" ;; *) _ok "$1" ;; esac; }
assert_nonzero() { if [ "$2" -ne 0 ]; then _ok "$1"; else _fail "$1 (salio con 0)"; fi; }

echo "test_deploy_script"
if [ ! -f "$SRC_DEPLOY" ]; then
  _fail "existe infra/deploy.sh"
  echo "test_deploy_script: $FAILS fallas"
  exit 1
fi

# --- falsos ejecutables en una carpeta propia (Windows no guarda el bit +x) -------------------
FAKEBIN="$TMP_ROOT/bin"
mkdir -p "$FAKEBIN"
for f in docker git curl sleep stat; do
  cp "$FAKES_SRC/$f" "$FAKEBIN/$f"
  chmod +x "$FAKEBIN/$f"
done

SHA=0123456789abcdef0123456789abcdef01234567
OTRO_SHA=fedcba9876543210fedcba9876543210fedcba98
REF=v0.1.0
NOW=20261103-120000
N=0
R=""; LOGD=""; LOGG=""; STATE=""

# mk_repo: crea un repositorio de prueba con .env y .env.ops validos e inventados (no reales).
mk_repo() {
  N=$((N + 1))
  R="$TMP_ROOT/repo$N"
  mkdir -p "$R/infra" "$R/state"
  cp "$SRC_DEPLOY" "$R/infra/deploy.sh"
  : > "$R/infra/compose.yml"
  printf 'ENV=production\nCORS_ORIGINS=https://apex.ejemplo.local\nLOG_LEVEL=INFO\n' > "$R/.env"
  cat > "$R/.env.ops" << 'OPS'
POSTGRES_USER=apex
POSTGRES_PASSWORD=prueba-propietario-0000000000000000
POSTGRES_DB=apex
DATABASE_URL=postgresql+asyncpg://apex:prueba-propietario-0000000000000000@db:5432/apex
APEX_API_DB_PASSWORD=prueba-rol-api-1111111111111111
APEX_WORKER_DB_PASSWORD=prueba-rol-worker-22222222222222
APEX_BACKUP_DB_PASSWORD=prueba-rol-backup-33333333333333
BACKUP_AGE_RECIPIENT=age1-destinatario-de-prueba
BACKUP_SIGN_PUBKEY=RWQ-clave-publica-de-prueba
WEB_PORT=8480
OPS
  printf 'age-encryption.org/v1\nmaterial-de-prueba\n' > "$R/kek.bin"
  LOGD="$R/docker.log"; LOGG="$R/git.log"; : > "$LOGD"; : > "$LOGG"
  STATE="$R/state"
}

# set_var <archivo> <CLAVE> <valor>: reemplaza (o anade) CLAVE=valor en el repo actual.
set_var() {
  local f="$R/$1" k="$2" v="$3"
  { grep -v "^$k=" "$f" || true; printf '%s=%s\n' "$k" "$v"; } > "$f.tmp"
  mv "$f.tmp" "$f"
}
drop_var() { { grep -v "^$2=" "$R/$1" || true; } > "$R/$1.tmp"; mv "$R/$1.tmp" "$R/$1"; }

# d [VAR=valor ...] -- <argumentos de deploy.sh>: corre deploy.sh con los falsos; deja RC y OUT.
RC=0; OUT=""
d() {
  local extra=()
  while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do extra+=("$1"); shift; done
  [ "$#" -gt 0 ] && shift
  RC=0
  OUT="$(cd "$R" && env \
      PATH="$FAKEBIN:$PATH" HOME="$R" \
      FAKE_DOCKER_LOG="$LOGD" FAKE_GIT_LOG="$LOGG" FAKE_CURL_LOG="$R/curl.log" FAKE_SLEEP_LOG="$R/sleep.log" \
      FAKE_GIT_REV="$SHA" DEPLOY_NOW="$NOW" DEPLOY_STATE_DIR="$STATE" DEPLOY_HEALTH_TIMEOUT=3 \
      ${extra[@]+"${extra[@]}"} \
      bash infra/deploy.sh "$@" 2>&1)" || RC=$?
}
# Argumentos validos (una palabra por argumento; las rutas de prueba no llevan espacios).
# (S4B-D179: sin .github/allowed_signers la etiqueta no tiene firma verificable y se exige la bandera.)
buenos() { echo --ref "$REF" --expect-sha "$SHA" --kek-file "$R/kek.bin" --i-know-unsigned-ref; }
sin_firma_ok() { echo --ref "$REF" --expect-sha "$SHA" --kek-file "$R/kek.bin"; }
# docker_ajeno: lineas del registro de docker que NO son `config -q` (debe quedar vacio en los 2).
docker_ajeno() { grep -v ' config -q' "$LOGD" || true; }

# caso_2 <descripcion> [VAR=valor ...] -- <args>: sale con 2 y sin docker salvo config -q.
caso_2() {
  local desc="$1"; shift
  d "$@"
  assert_eq "$desc: sale con 2" 2 "$RC"
  assert_eq "$desc: ningun docker salvo config -q" "" "$(docker_ajeno)"
}

echo "-- argumentos"
mk_repo; d --
assert_eq "sin argumentos: sale con 2" 2 "$RC"
mk_repo; d -- --expect-sha "$SHA"
assert_eq "sin --ref: sale con 2" 2 "$RC"
mk_repo; d -- --ref "$REF"
assert_eq "--ref sin --expect-sha: sale con 2" 2 "$RC"
assert_eq "--ref sin --expect-sha: sin docker" "" "$(cat "$LOGD")"
mk_repo; d -- --ref main --expect-sha "$SHA" --kek-file "$R/kek.bin"
assert_eq "--ref main (no es una etiqueta vX.Y.Z): sale con 2" 2 "$RC"
mk_repo; d -- --ref "$REF" --expect-sha abc123 --kek-file "$R/kek.bin"
assert_eq "--expect-sha corto: sale con 2" 2 "$RC"
mk_repo; d -- --ref "$REF" --expect-sha "$SHA" --opcion-rara
assert_eq "opcion desconocida: sale con 2" 2 "$RC"
assert_eq "argumentos invalidos: sin docker" "" "$(cat "$LOGD")"

echo "-- git: SHA, arbol limpio y firma"
mk_repo; d FAKE_GIT_REV="$OTRO_SHA" -- $(buenos)
assert_eq "SHA distinto: sale con 2" 2 "$RC"
assert_eq "SHA distinto: no llama a docker" "" "$(cat "$LOGD")"
assert_contains "SHA distinto: lo dice" "$OUT" "SHA"
mk_repo; d FAKE_GIT_REV="" -- $(buenos)
assert_eq "la etiqueta no existe (rev-parse falla): sale con 2" 2 "$RC"
mk_repo; d FAKE_GIT_FETCH_RC=1 -- $(buenos)
assert_eq "git fetch --tags falla: sale con 2" 2 "$RC"
assert_eq "git fetch falla: no llama a docker" "" "$(cat "$LOGD")"
mk_repo; d FAKE_GIT_PORCELAIN=" M api/src/app/main.py" -- $(buenos)
assert_eq "arbol sucio: sale con 2" 2 "$RC"
assert_eq "arbol sucio: no llama a docker" "" "$(cat "$LOGD")"
mk_repo; d -- $(buenos)
assert_lacks "con --i-know-unsigned-ref y sin allowed_signers no llama a verify-tag" "$(cat "$LOGG")" "verify-tag"
assert_contains "usa git fetch --tags" "$(cat "$LOGG")" "fetch --tags"
assert_contains "verifica la etiqueta con rev-parse" "$(cat "$LOGG")" "rev-parse"
assert_contains "pasa al SHA desprendido con checkout -q --detach" "$(cat "$LOGG")" "checkout -q --detach $SHA"
assert_lacks "nunca hace push" "$(cat "$LOGG")" "push"
assert_lacks "nunca hace pull" "$(cat "$LOGG")" "pull"
# M2 (S4B-D179): fail-closed. Sin allowed_signers y sin la bandera: 2, sin checkout ni docker.
mk_repo; d -- $(sin_firma_ok)
assert_eq "sin allowed_signers ni --i-know-unsigned-ref: sale con 2" 2 "$RC"
assert_contains "sin firma: el mensaje pide --i-know-unsigned-ref" "$OUT" "etiqueta sin firma verificable: use --i-know-unsigned-ref"
assert_lacks "sin firma: no hay checkout" "$(cat "$LOGG")" "checkout"
assert_eq "sin firma: no llama a docker" "" "$(cat "$LOGD")"
mk_repo; mkdir -p "$R/.github"; printf 'rojored7 ssh-ed25519 AAAA-de-prueba\n' > "$R/.github/allowed_signers"
d FAKE_GIT_VERIFY_RC=1 -- $(sin_firma_ok)
assert_eq "allowed_signers presente y firma invalida: sale con 2" 2 "$RC"
assert_contains "con allowed_signers llama a verify-tag" "$(cat "$LOGG")" "verify-tag"
assert_lacks "firma invalida: no hay checkout" "$(cat "$LOGG")" "checkout"
mk_repo; mkdir -p "$R/.github"; printf 'rojored7 ssh-ed25519 AAAA-de-prueba\n' > "$R/.github/allowed_signers"
d -- $(sin_firma_ok)
assert_eq "allowed_signers presente y firma valida, sin bandera: sale con 0" 0 "$RC"
mk_repo; mkdir -p "$R/.github"; printf 'rojored7 ssh-ed25519 AAAA-de-prueba\n' > "$R/.github/allowed_signers"
d FAKE_GIT_VERIFY_RC=1 -- $(buenos)
assert_eq "firma invalida con --i-know-unsigned-ref: sigue (0)" 0 "$RC"

echo "-- M1: el checkout va despues de las comprobaciones que no dependen del codigo nuevo"
# S4B-D191: un .env copiado del ejemplo conserva el comentario de cabecera que nombra cambiar-esto.
mk_repo; { printf '# ejemplo: cambiar todos los "cambiar-esto"\n'; cat "$R/.env"; } > "$R/.env.n"; mv "$R/.env.n" "$R/.env"
{ printf '  # tambien indentado: cambiar-esto\n'; cat "$R/.env.ops"; } > "$R/.env.ops.n"; mv "$R/.env.ops.n" "$R/.env.ops"
d -- $(buenos)
assert_eq "cambiar-esto solo en comentarios: sale con 0" 0 "$RC"
mk_repo; set_var .env OTRA_CLAVE cambiar-esto; d -- $(buenos)
assert_eq "fallo de .env: sale con 2" 2 "$RC"
assert_lacks "fallo de .env: no hubo checkout (HEAD intacto)" "$(cat "$LOGG")" "checkout"
mk_repo; d FAKE_STAT_MODE=644 -- $(buenos)
assert_lacks "modo 644: no hubo checkout" "$(cat "$LOGG")" "checkout"
mk_repo; set_var .env.ops BACKUP_SIGN_PUBKEY ""; d -- $(buenos)
assert_lacks "sin llave publica de firma: no hubo checkout" "$(cat "$LOGG")" "checkout"
mk_repo; d -- --ref "$REF" --expect-sha "$SHA" --kek-file "$R/no-existe.bin" --i-know-unsigned-ref
assert_lacks "KEK ausente: no hubo checkout" "$(cat "$LOGG")" "checkout"
mk_repo; d DEPLOY_SKIP_BUILD=1 FAKE_DOCKER_REVISION=otra -- $(buenos)
assert_lacks "SKIP_BUILD con etiqueta distinta: no hubo checkout" "$(cat "$LOGG")" "checkout"
mk_repo; d FAKE_DOCKER_CONFIG_RC=1 -- $(buenos)
assert_eq "config -q falla tras el checkout: sale con 2" 2 "$RC"
assert_eq "config -q falla: checkout al SHA y vuelta al codigo anterior (2 checkouts)" 2 "$(grep -c '^checkout' "$LOGG")"
mk_repo; d FAKE_DOCKER_DB_RUNNING=0 -- $(buenos)
assert_eq "db detenida: tambien restaura el codigo (2 checkouts)" 2 "$(grep -c '^checkout' "$LOGG")"
mk_repo; d -- $(buenos)
assert_eq "camino feliz: un solo checkout (no se restaura)" 1 "$(grep -c '^checkout' "$LOGG")"

echo "-- L5, L6, L7: DEPLOY_NOW, DEPLOY_COMPOSE_EXTRA y cabecera de la KEK"
mk_repo; d DEPLOY_NOW="../../etc/x" -- $(buenos)
assert_eq "DEPLOY_NOW con forma invalida: sale con 2" 2 "$RC"
mk_repo; d DEPLOY_COMPOSE_EXTRA="infra/compose.otro.yml" -- $(buenos)
assert_eq "DEPLOY_COMPOSE_EXTRA fuera de la lista blanca: 2" 2 "$RC"
mk_repo; d "DEPLOY_COMPOSE_EXTRA=infra/*" -- $(buenos)
assert_eq "DEPLOY_COMPOSE_EXTRA con comodin: 2" 2 "$RC"
mk_repo; d DEPLOY_COMPOSE_EXTRA="infra/compose.verify.yml" -- $(buenos)
assert_eq "DEPLOY_COMPOSE_EXTRA=infra/compose.verify.yml: 0" 0 "$RC"
assert_contains "pasa -f infra/compose.verify.yml a compose" "$(cat "$LOGD")" "-f infra/compose.verify.yml"
mk_repo; printf 'no-es-age\nmaterial\n' > "$R/kek.bin"
caso_2 "KEK sin cabecera age" -- $(buenos)
mk_repo; : > "$R/kek.bin"
caso_2 "KEK vacia" -- $(buenos)

echo "-- L4: el log del api se filtra antes de imprimirlo"
mk_repo
d FAKE_CURL_BODY='{"status":"degraded","db":"ok","migrations":"mismatch"}' FAKE_DOCKER_LOG_EXTRA="error input_value=secreto-123 TOKEN=abc" -- $(buenos)
assert_eq "salud en mismatch (log con valores): sale con 1" 1 "$RC"
assert_contains "se imprime el log normal" "$OUT" "linea de log falsa 1"
assert_lacks "no se imprime input_value" "$OUT" "input_value"
assert_lacks "no se imprime TOKEN" "$OUT" "TOKEN"

echo "-- el api debe traer DATABASE_URL con su rol"
mk_repo; d FAKE_DOCKER_DATABASE_URL="" -- $(buenos)
assert_eq "DATABASE_URL ausente en el api: sale con 1" 1 "$RC"
mk_repo; d FAKE_DOCKER_DATABASE_URL="postgresql+asyncpg://apex:x@db:5432/apex" -- $(buenos)
assert_eq "DATABASE_URL con el propietario: sale con 1" 1 "$RC"

echo "-- .env y .env.ops"
mk_repo; rm "$R/.env"
caso_2 "sin .env" -- $(buenos)
mk_repo; rm "$R/.env.ops"
caso_2 "sin .env.ops" -- $(buenos)
mk_repo; set_var .env POSTGRES_PASSWORD ""
caso_2 ".env con POSTGRES_PASSWORD=" -- $(buenos)
mk_repo; set_var .env DATABASE_URL ""
caso_2 ".env con DATABASE_URL=" -- $(buenos)
mk_repo; set_var .env OTRA_CLAVE cambiar-esto
caso_2 ".env con cambiar-esto" -- $(buenos)
mk_repo; set_var .env.ops POSTGRES_PASSWORD cambiar-esto
caso_2 ".env.ops con cambiar-esto" -- $(buenos)
mk_repo; set_var .env.ops APEX_API_DB_PASSWORD cambiar-esto
caso_2 "contrasena de rol con cambiar-esto" -- $(buenos)
mk_repo; set_var .env.ops APEX_API_DB_PASSWORD corta12345
caso_2 "contrasena de rol de 10 caracteres" -- $(buenos)
mk_repo; set_var .env.ops APEX_WORKER_DB_PASSWORD "$(grep '^APEX_API_DB_PASSWORD=' "$R/.env.ops" | cut -d= -f2-)"
caso_2 "dos contrasenas de rol iguales" -- $(buenos)
mk_repo
caso_2 ".env.ops con modo 644" FAKE_STAT_MODE=644 -- $(buenos)
mk_repo
caso_2 ".env.ops de otro propietario" FAKE_STAT_UID=424242 -- $(buenos)
mk_repo
caso_2 ".env.ops rastreado por git" FAKE_GIT_TRACKED=".env.ops" -- $(buenos)
mk_repo
caso_2 ".env rastreado por git" FAKE_GIT_TRACKED=".env" -- $(buenos)
mk_repo
caso_2 "sin --kek-file" -- --ref "$REF" --expect-sha "$SHA"
mk_repo
caso_2 "KEK que no existe" -- --ref "$REF" --expect-sha "$SHA" --kek-file "$R/no-existe.bin"
mk_repo; set_var .env.ops BACKUP_AGE_RECIPIENT ""
caso_2 "sin BACKUP_AGE_RECIPIENT" -- $(buenos)
mk_repo; drop_var .env.ops BACKUP_AGE_RECIPIENT
caso_2 "BACKUP_AGE_RECIPIENT ausente" -- $(buenos)
mk_repo; set_var .env.ops BACKUP_SIGN_PUBKEY ""
caso_2 "sin BACKUP_SIGN_PUBKEY" -- $(buenos)
mk_repo; d FAKE_DOCKER_CONFIG_RC=1 -- $(buenos)
assert_eq "compose config -q falla: sale con 2" 2 "$RC"
assert_eq "compose config -q falla: nada mas de docker" "" "$(docker_ajeno)"
mk_repo; d -- $(buenos)
assert_contains "valida con compose config -q y los dos --env-file" "$(cat "$LOGD")" "--env-file .env --env-file .env.ops -f infra/compose.yml config -q"

echo "-- db detenida y respaldo pre-deploy"
mk_repo; d FAKE_DOCKER_DB_RUNNING=0 -- $(buenos)
assert_eq "db detenida: sale con 2" 2 "$RC"
assert_lacks "db detenida: no hay respaldo" "$(cat "$LOGD")" "run.sh"
assert_lacks "db detenida: no construye" "$(cat "$LOGD")" " build"
mk_repo; d FAKE_DOCKER_BACKUP_RC=1 -- $(buenos)
assert_nonzero "respaldo falla: sale distinto de 0" "$RC"
assert_lacks "respaldo falla: no construye" "$(cat "$LOGD")" " build"
assert_lacks "respaldo falla: no levanta" "$(cat "$LOGD")" " up "
mk_repo; d FAKE_DOCKER_BACKUP_CHECK_RC=1 -- $(buenos)
assert_nonzero "archivos del respaldo incompletos: sale distinto de 0" "$RC"
assert_lacks "archivos incompletos: no construye" "$(cat "$LOGD")" " build"
mk_repo; d -- $(buenos) --i-know-no-backup
assert_eq "--i-know-no-backup: sale con 0" 0 "$RC"
assert_lacks "--i-know-no-backup: no corre run.sh" "$(cat "$LOGD")" "run.sh"
mk_repo; set_var .env.ops BACKUP_AGE_RECIPIENT ""
d -- $(buenos) --i-know-no-backup
assert_eq "--i-know-no-backup no exige BACKUP_AGE_RECIPIENT" 0 "$RC"

echo "-- camino feliz"
mk_repo; d -- $(buenos)
assert_eq "camino feliz: sale con 0" 0 "$RC"
dlog="$(cat "$LOGD")"
assert_contains "respaldo con --prefix pre-deploy" "$dlog" "run --rm backup /opt/backup/run.sh --prefix pre-deploy"
assert_contains "etiqueta prev-<fecha> de apex-api" "$dlog" "apex-api:prev-$NOW"
assert_contains "etiqueta prev-<fecha> de apex-web" "$dlog" "apex-web:prev-$NOW"
assert_contains "etiqueta prev-<fecha> de apex-backup" "$dlog" "apex-backup:prev-$NOW"
assert_contains "construye" "$dlog" " build"
assert_contains "levanta con up -d" "$dlog" " up -d"
assert_contains "imprime la version" "$OUT" "$REF"
estado="$STATE/deploy-$NOW.state.json"
if [ -f "$estado" ]; then _ok "escribe deploy-<fecha>.state.json"; else _fail "escribe deploy-<fecha>.state.json"; fi
cuerpo_estado="$(cat "$estado" 2> /dev/null || true)"
for clave in '"ref"' '"sha"' '"prev_tag"' '"manifest"' '"images"'; do
  assert_contains "state.json lleva $clave" "$cuerpo_estado" "$clave"
done
assert_contains "state.json nombra el manifiesto pre-deploy" "$cuerpo_estado" "pre-deploy-20261103-120000"
assert_contains "state.json nombra prev-<fecha>" "$cuerpo_estado" "prev-$NOW"
assert_eq "state.json sin secretos" 0 "$(printf '%s' "$cuerpo_estado" | grep -cE 'PASSWORD|SECRET|AGE-SECRET' || true)"
assert_contains "sondea el /health del puerto de .env.ops" "$(cat "$R/curl.log" 2> /dev/null || true)" "127.0.0.1:8480/api/v1/health"
assert_lacks "nunca down -v" "$dlog" "down -v"
assert_lacks "nunca volume rm" "$dlog" "volume rm"
assert_lacks "nunca pull" "$dlog" " pull"
assert_lacks "nunca push" "$dlog" "push"

echo "-- fallo de salud"
mk_repo
d FAKE_CURL_BODY='{"status":"degraded","db":"ok","migrations":"mismatch"}' -- $(buenos)
assert_eq "salud en mismatch: sale con 1" 1 "$RC"
rb="$STATE/rollback-$NOW.txt"
if [ -f "$rb" ]; then _ok "escribe rollback-<fecha>.txt"; else _fail "escribe rollback-<fecha>.txt"; fi
cuerpo_rb="$(cat "$rb" 2> /dev/null || true)"
assert_contains "rollback nombra apex-api:prev-<fecha>" "$cuerpo_rb" "apex-api:prev-$NOW"
assert_contains "rollback nombra apex-web:prev-<fecha>" "$cuerpo_rb" "apex-web:prev-$NOW"
assert_contains "rollback nombra apex-backup:prev-<fecha>" "$cuerpo_rb" "apex-backup:prev-$NOW"
assert_contains "rollback nombra el manifiesto pre-deploy" "$cuerpo_rb" "pre-deploy-20261103-120000.json"
assert_contains "rollback dice que no restaura la base" "$cuerpo_rb" "este script no restaura la base"
assert_eq "rollback sin PASSWORD/SECRET/AGE-SECRET" 0 "$(printf '%s' "$cuerpo_rb" | grep -cE 'PASSWORD|SECRET|AGE-SECRET' || true)"
assert_contains "imprime el log del api al fallar" "$OUT" "linea de log falsa"
assert_contains "pide 100 lineas del log" "$(cat "$LOGD")" "--tail 100"
mk_repo
d FAKE_CURL_RC=7 FAKE_CURL_BODY="" -- $(buenos)
assert_eq "api que no responde: sale con 1" 1 "$RC"
if [ -f "$STATE/rollback-$NOW.txt" ]; then _ok "api que no responde: escribe rollback"; else _fail "api que no responde: escribe rollback"; fi
mk_repo
d FAKE_CURL_BODY='{"status":"degraded","db":"unknown","migrations":"ok"}' -- $(buenos)
assert_eq "db no ok: sale con 1" 1 "$RC"
mk_repo
d FAKE_DOCKER_UP_RC=1 -- $(buenos)
assert_nonzero "up -d falla: sale distinto de 0" "$RC"

echo "-- DEPLOY_SKIP_BUILD"
mk_repo; d DEPLOY_SKIP_BUILD=1 FAKE_DOCKER_REVISION=otra-etiqueta -- $(buenos)
assert_eq "SKIP_BUILD con etiqueta OCI distinta: sale con 2" 2 "$RC"
assert_lacks "SKIP_BUILD distinta: no levanta" "$(cat "$LOGD")" " up "
mk_repo; d DEPLOY_SKIP_BUILD=1 FAKE_DOCKER_REVISION="$REF" -- $(buenos)
assert_eq "SKIP_BUILD con etiqueta OCI igual: sale con 0" 0 "$RC"
assert_lacks "SKIP_BUILD igual: no construye" "$(cat "$LOGD")" " build"
assert_contains "SKIP_BUILD lee org.opencontainers.image.revision" "$(cat "$LOGD")" "org.opencontainers.image.revision"

echo "-- estatico de infra/deploy.sh"
fuente="$(cat "$SRC_DEPLOY")"
assert_contains "set -euo pipefail" "$fuente" "set -euo pipefail"
no_contiene() { # <descripcion> <regex ERE>; revisa TODO el archivo, comentarios incluidos
  if grep -nE -- "$2" "$SRC_DEPLOY" > /dev/null; then _fail "deploy.sh contiene $1"; else _ok "deploy.sh sin $1"; fi
}
no_contiene "down -v" 'down[[:space:]]+(-v|--volumes)'
no_contiene "volume rm" 'volume[[:space:]]+rm'
no_contiene "set -x" '(^|[[:space:];])set -[a-z]*x'
no_contiene "push" '(^|[^[:alnum:]_])push([^[:alnum:]_]|$)'
no_contiene "--force" '--force([[:space:]=]|$)'
no_contiene "pull" '(^|[^[:alnum:]_])pull([^[:alnum:]_]|$)'
no_contiene "IMAGE_TAG" 'IMAGE_TAG'
no_contiene "jq" '(^|[^[:alnum:]_])jq([^[:alnum:]_]|$)'

echo "-- prod-smoke.sh y release.yml: sin llaves age fuera de ::add-mask::"
for f in scripts/ci/prod-smoke.sh .github/workflows/release.yml; do
  if [ ! -f "$ROOT/$f" ]; then _fail "existe $f"; continue; fi
  malas="$(grep -n 'AGE-SECRET-KEY-' "$ROOT/$f" | grep -v '::add-mask::' || true)"
  if [ -z "$malas" ]; then _ok "$f sin AGE-SECRET-KEY- fuera de ::add-mask::"; else _fail "$f: $malas"; fi
done

echo "-- release.yml: permisos y forma (S4B-D44, D67, D81)"
RY="$ROOT/.github/workflows/release.yml"
ry="$(cat "$RY")"
assert_contains "release.yml: dispara con etiquetas v*.*.*" "$ry" 'tags: ["v*.*.*"]'
assert_contains "release.yml: permissions contents: read global" "$ry" "contents: read"
n_write="$(grep -c 'contents: write' "$RY" || true)"
assert_eq "release.yml: contents: write exactamente una vez" 1 "$n_write"
dentro_draft="$(awk '/^  draft:/{d=1} d && /contents: write/{print "si"; exit}' "$RY")"
assert_eq "release.yml: contents: write solo dentro del job draft" si "$dentro_draft"
assert_contains "release.yml: job verify" "$ry" "  verify:"
assert_contains "release.yml: job draft necesita verify" "$ry" "needs: verify"
assert_contains "release.yml: corre check-release-version.sh" "$ry" "check-release-version.sh"
assert_contains "release.yml: corre prod-smoke.sh" "$ry" "prod-smoke.sh"
# L8: la etiqueta entra por `env: TAG:` y se usa como "$TAG"; ninguna linea de `run:` interpola ${{ }}.
assert_contains "release.yml: GIT_SHA es la etiqueta (via \$TAG)" "$ry" 'GIT_SHA="$TAG"'
interpoladas="$(grep -n 'github.ref_name' "$RY" | grep -vE '^[0-9]+:[[:space:]]*(TAG: \$\{\{ github.ref_name \}\}|group:|#)' || true)"
assert_eq "release.yml: github.ref_name solo aparece en env TAG, group o comentarios" "" "$interpoladas"
assert_contains "release.yml: mascara de secretos" "$ry" "::add-mask::"
assert_lacks "release.yml: no publica imagenes (docker push)" "$ry" "docker push"
assert_lacks "release.yml: sin packages: write" "$ry" "packages: write"
assert_lacks "release.yml: no crea la etiqueta (git tag)" "$ry" "git tag"
assert_lacks "release.yml: sin git push" "$ry" "git push"

echo "-- L3: SMOKE_DIR y E2E_ENV_DIR solo bajo docs/scratch/, sin .. (salen con 2 antes de usar docker)"
SMOKE="$ROOT/scripts/ci/prod-smoke.sh"
E2E="$ROOT/infra/tests/deploy_e2e.sh"
for malo in "$ROOT/../fuera" "$ROOT/docs/scratch/../../fuera" "$ROOT/docs" "$ROOT"; do
  rc=0; salida="$(SMOKE_DIR="$malo" bash "$SMOKE" 2>&1)" || rc=$?
  assert_eq "prod-smoke con SMOKE_DIR=$malo: sale con 2" 2 "$rc"
  assert_contains "prod-smoke con SMOKE_DIR=$malo: dice por que" "$salida" "SMOKE_DIR"
  rc=0; salida="$(E2E_ENV_DIR="$malo" E2E_KEK_FILE="$ROOT/LICENSE" bash "$E2E" 2>&1)" || rc=$?
  assert_eq "deploy_e2e con E2E_ENV_DIR=$malo: sale con 2" 2 "$rc"
  assert_contains "deploy_e2e con E2E_ENV_DIR=$malo: dice por que" "$salida" "E2E_ENV_DIR"
done

echo "-- L9: deploy.sh escribe el estado y el rollback con umask 077"
n_umask="$(grep -c 'umask 077' "$SRC_DEPLOY" || true)"
if [ "$n_umask" -ge 3 ]; then _ok "deploy.sh usa umask 077 al crear carpeta, estado y rollback ($n_umask)"; else _fail "deploy.sh: umask 077 aparece $n_umask veces (se esperaban >= 3)"; fi

echo "  resumen: $PASSES ok, $FAILS fallas"
echo "test_deploy_script: $FAILS fallas"
[ "$FAILS" -eq 0 ]
