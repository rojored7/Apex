#!/usr/bin/env bash
# Revisión estática de los scripts de infra/backup (S4B-W0-1; S4B-D19, D57, D68, D73, D78).
# Sin shellcheck (GPL, no disponible): `bash -n` y reglas por patrón.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/harness.sh"

echo "test_scripts_static"
SCRIPTS=()
for f in "$BACKUP_DIR_SRC"/*.sh "$TESTS_DIR"/*.sh; do
  [ -f "$f" ] && SCRIPTS+=("$f")
done
# S4B-B4 (paso 78): con el repo completo (no dentro de apex-backup:local, que solo monta
# infra/backup) se revisan tambien deploy.sh, prod-smoke.sh y infra/tests/*.sh.
REPO_ROOT="$(cd "$BACKUP_DIR_SRC/../.." && pwd)"
REPO_MODE=0
[ -f "$REPO_ROOT/infra/compose.yml" ] && REPO_MODE=1
DEPLOY="$REPO_ROOT/infra/deploy.sh"
SMOKE="$REPO_ROOT/scripts/ci/prod-smoke.sh"
EXTRA=()
if [ "$REPO_MODE" -eq 1 ]; then
  for f in "$DEPLOY" "$SMOKE" "$REPO_ROOT"/infra/tests/*.sh; do
    if [ -f "$f" ]; then SCRIPTS+=("$f"); EXTRA+=("$f"); else _fail "existe ${f#"$REPO_ROOT"/}"; fi
  done
fi
RUN="$BACKUP_DIR_SRC/run.sh"
ENTRY="$BACKUP_DIR_SRC/entrypoint.sh"
for esperado in run.sh lib.sh entrypoint.sh healthcheck.sh; do
  [ -f "$BACKUP_DIR_SRC/$esperado" ] && _ok "existe $esperado" || _fail "existe $esperado"
done
[ -f "$RUN" ] || { finish; exit; }

for f in "${SCRIPTS[@]}"; do
  assert_ok "bash -n $(basename "$f")" bash -n "$f"
done

# Patrones prohibidos en cualquier script de producción (no en las pruebas).
PROD=()
for f in "$BACKUP_DIR_SRC"/*.sh; do PROD+=("$f"); done
if [ "$REPO_MODE" -eq 1 ] && [ -f "$DEPLOY" ]; then PROD+=("$DEPLOY"); fi
prohibido() { # <descripcion> <regex>
  local desc="$1" re="$2" hallado=""
  for f in "${PROD[@]}"; do
    if grep -nE -- "$re" "$f" | grep -vE '^[0-9]+:[[:space:]]*#' > /dev/null; then hallado="$hallado $(basename "$f")"; fi
  done
  [ -z "$hallado" ] && _ok "sin $desc" || _fail "$desc en:$hallado"
}
prohibido "set -x" '(^|[[:space:];])set -[a-z]*x'
prohibido "down -v" 'down[[:space:]]+(-v|--volumes)'
prohibido "volume rm" 'volume[[:space:]]+rm'
prohibido "push" '(^|[[:space:];|&])git[[:space:]]+push|docker[[:space:]]+push'
prohibido "--force" '(^|[[:space:]])--force([[:space:]=]|$)'
prohibido "rclone sync" 'rclone[[:space:]]+sync'
prohibido "rclone delete" 'rclone[[:space:]]+delete'
prohibido "rclone purge" 'rclone[[:space:]]+purge'
prohibido "rclone deletefile" 'rclone[[:space:]]+deletefile'
prohibido "-vv" '(^|[[:space:]])-vv([[:space:]]|$)'
prohibido "--dump" '(^|[[:space:]])--dump([[:space:]=]|$)'
prohibido "echo de PGPASSWORD" '(echo|printf)[^#|]*(PGPASSWORD|RCLONE_CONFIG_APEX_SECRET_ACCESS_KEY|AGE-SECRET-KEY)'
prohibido "rclone con -v" 'rclone[^#|]*[[:space:]]-v([[:space:]]|$)'

# prod-smoke.sh e infra/tests/*.sh (humo y E2E): pueden usar down -v sobre apex-smoke, pero nunca
# set -x ni imprimir secretos (deploy.sh ya pasó por la lista completa de PROD).
for f in ${EXTRA[@]+"${EXTRA[@]}"}; do
  [ "$f" = "$DEPLOY" ] && continue
  n="${f#"$REPO_ROOT"/}"
  if grep -nE -- '(^|[[:space:];])set -[a-z]*x' "$f" | grep -vE '^[0-9]+:[[:space:]]*#' > /dev/null; then _fail "set -x en $n"; else _ok "sin set -x en $n"; fi
  if grep -nE -- '(echo|printf)[^#|>]*(RCLONE_CONFIG_APEX_SECRET_ACCESS_KEY|AGE-SECRET-KEY)' "$f" | grep -vE '^[0-9]+:[[:space:]]*#|::add-mask::' > /dev/null; then _fail "echo de secretos en $n"; else _ok "sin echo de secretos en $n"; fi
done

# deploy.sh (S4B-D41, D67): contenido minimo del contrato; en el Rojo el stub no lo cumple.
if [ "$REPO_MODE" -eq 1 ] && [ -f "$DEPLOY" ]; then
  dep="$(cat "$DEPLOY")"
  assert_contains "deploy.sh con set -euo pipefail" "$dep" "set -euo pipefail"
  assert_contains "deploy.sh sale con 2 en la preverificacion" "$dep" "exit 2"
  assert_contains "deploy.sh exige --expect-sha" "$dep" "--expect-sha"
  assert_contains "deploy.sh hace git fetch --tags" "$dep" "git fetch --tags"
  assert_contains "deploy.sh resuelve la etiqueta con ^{commit}" "$dep" "^{commit}"
  assert_contains "deploy.sh valida compose con config -q" "$dep" "config -q"
  assert_contains "deploy.sh respalda con --prefix pre-deploy" "$dep" "--prefix pre-deploy"
  assert_contains "deploy.sh etiqueta prev-" "$dep" "prev-"
  assert_contains "deploy.sh escribe rollback-" "$dep" "rollback-"
  assert_contains "deploy.sh dice que no restaura la base" "$dep" "este script no restaura la base"
  assert_contains "deploy.sh respeta DEPLOY_SKIP_BUILD" "$dep" "DEPLOY_SKIP_BUILD"
  assert_contains "deploy.sh compara la etiqueta OCI revision" "$dep" "org.opencontainers.image.revision"
  assert_contains "deploy.sh lee /proc/1/environ del api" "$dep" "/proc/1/environ"
  assert_contains "deploy.sh pasa al SHA desprendido" "$dep" 'checkout -q --detach "$REAL_SHA"'
  assert_contains "deploy.sh apaga los comodines para DEPLOY_COMPOSE_EXTRA" "$dep" "set -f"
  assert_contains "deploy.sh filtra el log del api" "$dep" "input_value|PASSWORD|SECRET|KEY|TOKEN"
fi
# B4 (pendientes del Verde): la copia de la KEK del humo es un archivo de age REAL y deploy_e2e pasa la bandera.
if [ "$REPO_MODE" -eq 1 ] && [ -f "$SMOKE" ]; then
  smk2="$(cat "$SMOKE")"
  assert_contains "prod-smoke.sh fabrica la copia de la KEK con age -p" "$smk2" "age -p"
  if grep -nE '(echo|printf)[^#]*age-encryption.org' "$SMOKE" > /dev/null; then _fail "prod-smoke.sh escribe la cabecera de age a mano"; else _ok "prod-smoke.sh no fabrica la cabecera de age a mano"; fi
fi
E2E_SH="$REPO_ROOT/infra/tests/deploy_e2e.sh"
if [ "$REPO_MODE" -eq 1 ] && [ -f "$E2E_SH" ]; then
  assert_contains "deploy_e2e.sh pasa --i-know-unsigned-ref a deploy.sh" "$(cat "$E2E_SH")" "--i-know-unsigned-ref"
fi
# Defectos del humo real en Linux (S4B-D190 a D196).
if [ "$REPO_MODE" -eq 1 ] && [ -f "$SMOKE" ]; then
  smk3="$(cat "$SMOKE")"
  assert_lacks "prod-smoke.sh no monta el ayudante pty como pty.py (taparia el modulo pty)" "$smk3" ":/pty.py"
  assert_contains "prod-smoke.sh monta el ayudante con otro nombre" "$smk3" "/t/ptyrun.py"
  assert_contains "prod-smoke.sh ignora comentarios al buscar cambiar-esto" "$smk3" "grep -v '^[[:space:]]*#'"
fi
# S5-B13 (S5-D95): el e2e de la restauración de OpenBao sigue el contrato y no es un stub.
OB_E2E="$REPO_ROOT/infra/tests/openbao_restore_e2e.sh"
if [ "$REPO_MODE" -eq 1 ]; then
  if [ -f "$OB_E2E" ]; then
    obe="$(cat "$OB_E2E")"
    assert_lacks "openbao_restore_e2e.sh ya no es un stub (exit 99)" "$(grep -vE '^[[:space:]]*#' "$OB_E2E")" "exit 99"
    assert_contains "openbao_restore_e2e.sh envuelve una cadena con transit/encrypt/apex-kek" "$obe" "transit/encrypt/apex-kek"
    assert_contains "openbao_restore_e2e.sh descifra con transit/decrypt/apex-kek" "$obe" "transit/decrypt/apex-kek"
    # S5-D172: el ensayo real mostro que la raiz sale del `init` del clúster nuevo y que restore.sh usa snapshot-force.
    assert_contains "openbao_restore_e2e.sh inicializa un clúster nuevo para la restauración" "$obe" "operator init"
    assert_contains "openbao_restore_e2e.sh restaura la instantánea raft con restore.sh --with-openbao" "$obe" "--with-openbao"
    assert_contains "openbao_restore_e2e.sh desella con las llaves originales" "$obe" "llaves originales"
    assert_contains "openbao_restore_e2e.sh solo toca recursos desechables apex-obe2e-" "$obe" "apex-obe2e-"
    # S5-D182: el entrypoint de postgres levanta un servidor temporal SOLO por socket durante el initdb;
    # pg_isready/psql por socket ya responden ahí y el CREATE DATABASE cae en "the database system is
    # shutting down". Por TCP (127.0.0.1) solo responde el servidor definitivo.
    assert_contains "openbao_restore_e2e.sh espera a postgres por TCP, no por el socket del initdb" "$obe" "pg_isready -h 127.0.0.1"
    assert_lacks "openbao_restore_e2e.sh no usa psql por socket" "$(grep -vE '^[[:space:]]*#' "$OB_E2E")" "psql -U postgres -c"
  else
    _fail "existe infra/tests/openbao_restore_e2e.sh"
  fi
fi
RESTORE_SH="$REPO_ROOT/infra/tests/restore_e2e.sh"
if [ "$REPO_MODE" -eq 1 ] && [ -f "$RESTORE_SH" ]; then
  rst="$(cat "$RESTORE_SH")"
  assert_contains "restore_e2e.sh abre el directorio de trabajo a 755" "$rst" 'chmod 755 "$WORK" "$PY"'
  assert_contains "restore_e2e.sh deja las claves escribibles por el contenedor" "$rst" 'chmod 777 "$SALIDA" "$CLAVES"'
  assert_contains "restore_e2e.sh comprueba con minisign que el manifiesto alterado no verifica" "$rst" "minisign -V -p /k/sign.pub -m /data/backups/e2e-alterado.json"
  assert_lacks "restore_e2e.sh ya no altera solo skipped por ok" "$rst" 's/\"verify\": \"skipped\"/'
fi
if [ "$REPO_MODE" -eq 1 ] && [ -f "$REPO_ROOT/infra/tests/deploy_e2e.sh" ]; then
  de="$(cat "$REPO_ROOT/infra/tests/deploy_e2e.sh")"
  assert_lacks "deploy_e2e.sh no usa tar --null (GNU)" "$de" "--null"
  assert_contains "deploy_e2e.sh fija umask 022 para el clon" "$de" "umask 022"
  assert_contains "deploy_e2e.sh abre el directorio de trabajo a 755" "$de" 'chmod 755 "$WORK"'
fi
# prod-smoke.sh (S4B-D46, D78): solo apex-smoke, mascaras y down -v acotado.
if [ "$REPO_MODE" -eq 1 ] && [ -f "$SMOKE" ]; then
  smk="$(cat "$SMOKE")"
  assert_contains "prod-smoke.sh usa el proyecto apex-smoke" "$smk" "apex-smoke"
  assert_contains "prod-smoke.sh enmascara con ::add-mask::" "$smk" "::add-mask::"
  assert_contains "prod-smoke.sh baja el stack solo con SMOKE_DOWN o CI" "$smk" "SMOKE_DOWN"
  assert_contains "prod-smoke.sh usa la subred 172.31.1.0/24" "$smk" "172.31.1.0/24"
  assert_contains "prod-smoke.sh usa el puerto 8380" "$smk" "8380"
fi

# run.sh: modo estricto, umask y copyto sin borrado.
cuerpo="$(cat "$RUN")"
assert_contains "run.sh con set -euo pipefail" "$cuerpo" "set -euo pipefail"
assert_contains "run.sh con umask 077" "$cuerpo" "umask 077"
assert_contains "run.sh sube con rclone copyto" "$cuerpo" "rclone copyto"
assert_contains "run.sh con --log-level ERROR" "$cuerpo" "--log-level ERROR"
assert_contains "run.sh firma con minisign -S" "$cuerpo" "minisign -S"
assert_contains "run.sh limpia con trap" "$cuerpo" "trap "
assert_contains "run.sh acepta --prefix" "$cuerpo" "--prefix"
assert_contains "run.sh exige firma (salida 2)" "$cuerpo" "exit 2"
assert_contains "run.sh no toca latest.json con pre-*" "$cuerpo" "latest.json"
assert_contains "run.sh pasa PGPASSWORD solo a pg_dump (asignación prefijo)" "$cuerpo" 'PGPASSWORD="$_PGPW" pg_dump'
assert_lacks "run.sh no usa env PGPASSWORD (argv visible)" "$cuerpo" 'env PGPASSWORD='
assert_contains "run.sh usa --immutable" "$cuerpo" "--immutable"

# entrypoint.sh: inerte pero visible sin destinatario.
if [ -f "$ENTRY" ]; then
  assert_contains "entrypoint avisa 'backup deshabilitado'" "$(cat "$ENTRY")" "backup deshabilitado: falta BACKUP_AGE_RECIPIENT"
  assert_contains "entrypoint arranca supercronic" "$(cat "$ENTRY")" "supercronic"
fi

finish
