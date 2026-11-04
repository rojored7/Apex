#!/usr/bin/env bash
# restore_e2e.sh: restauración de punta a punta (S4B-B3a, US-116; S4B-D42, D57, D58, D89, D97).
#
# Solo corre en contenedores y en la CI (job `images`, tras `SMOKE_KEEP=1 compose-smoke.sh`, con
# la imagen `apex-backup` recién construida); en el host de desarrollo se usa sobre `apex-ensayo`
# (E2E_DC apunta a ese proyecto). NUNCA contra la base de desarrollo `apex-db-1`: crea y borra su
# propia base `apex_restore` en el `db` del proyecto indicado.
#
# Qué comprueba (todo contra el stack real, con una frase generada al azar y claves efímeras):
#   1. un socio con documento cifrado -> `export-kek` y `verify-kek-backup` (con pty en `tools`)
#      -> `run.sh` -> base `apex_restore` vacía;
#   2. casos que salen con 2 SIN tocar la base: firma ausente, firma inválida, sin `-P`, `tar` con
#      enlace simbólico (juego firmado de verdad), --confirm-database distinto;
#   3. `restore.sh -P --confirm-database` restaura; el ancla impresa (through_seq/through_hash)
#      coincide con `audit.verifications` de origen; los triggers `A` de origen siguen en `A`;
#   4. `restore-kek` en tmpfs -> el api (create_app/crypto_runtime) arranca con esa KEK y `reveal`
#      devuelve el documento; con otra KEK falla con `unwrap_failed` y sin material.
# Variables: E2E_DC (comando compose completo; por omisión .env/.env.ops + compose.yml + dev),
# E2E_ENV_DIR (carpeta de .env/.env.ops/.env.seed; por omisión la raíz; en el ensayo
# docs/scratch/ensayo), E2E_ADMIN_EMAIL (por omisión el de .env.seed o admin@smoke.apex.local),
# BACKUP_IMG (por omisión apex-backup:local), API_IMG (por omisión apex-api:local), KEEP_WORK=1
# (no borra la carpeta de trabajo). Solo corre sobre los proyectos apex-smoke, apex-ensayo y
# apex-e2e (o, en la CI, sobre el que indique E2E_ALLOW_PROJECT); rechaza ENV=production salvo
# con E2E_DC explícito (el ensayo de producción usa ENV=production).
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
if [ -n "${E2E_DC:-}" ]; then
  read -r -a DC <<< "$E2E_DC"
else
  ENVS=(--env-file .env)
  [ -f .env.ops ] && ENVS+=(--env-file .env.ops)
  DC=(docker compose "${ENVS[@]}" -f infra/compose.yml -f infra/compose.dev.yml)
fi
BACKUP_IMG="${BACKUP_IMG:-apex-backup:local}"
API_IMG="${API_IMG:-apex-api:local}"
E2E_ENV_DIR="${E2E_ENV_DIR:-.}"
RESTORE_DB=apex_restore
fallas=0
ok() { echo "  ok   $1"; }
falla() { echo "  FALLA $1" >&2; fallas=$((fallas + 1)); }
muere() { echo "restore_e2e: $1" >&2; exit 1; }
verifica() { # <descripción> <comando...>
  local desc="$1"; shift
  if "$@" > /dev/null 2>&1; then ok "$desc"; else falla "$desc"; fi
}
nativa() { if command -v cygpath > /dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }
valor() { grep -hE "^$1=" "$E2E_ENV_DIR/.env" "$E2E_ENV_DIR/.env.ops" 2> /dev/null | tail -1 | cut -d= -f2- | tr -d '\r'; }

OWNER="$(valor POSTGRES_USER)"; OWNER_PW="$(valor POSTGRES_PASSWORD)"; MAIN_DB="$(valor POSTGRES_DB)"
[ -n "$OWNER" ] && [ -n "$OWNER_PW" ] && [ -n "$MAIN_DB" ] || muere "faltan POSTGRES_USER, POSTGRES_PASSWORD o POSTGRES_DB en .env/.env.ops"
ADMIN="${E2E_ADMIN_EMAIL:-}"
if [ -z "$ADMIN" ] && [ -f "$E2E_ENV_DIR/.env.seed" ]; then ADMIN="$(grep -hE '^ADMIN_EMAIL=' "$E2E_ENV_DIR/.env.seed" | cut -d= -f2- | tr -d '\r')"; fi
ADMIN="${ADMIN:-admin@smoke.apex.local}"

DBCID="$("${DC[@]}" ps -q db | tr -d '\r' | head -1)"
[ -n "$DBCID" ] || muere "el servicio db no está levantado"
PROJECT="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$DBCID" | tr -d '\r')"
NET="$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{end}}' "$DBCID" | tr -d '\r')"
case "$PROJECT" in
  apex-smoke | apex-ensayo | apex-e2e) ;;
  *)
    if [ -z "${CI:-}" ] || [ "${E2E_ALLOW_PROJECT:-}" != "$PROJECT" ]; then
      muere "el proyecto Compose '$PROJECT' no está en la lista permitida (apex-smoke, apex-ensayo, apex-e2e): este script crea y borra bases"
    fi ;;
esac
if [ "$(valor ENV)" = "production" ] && [ -z "${E2E_DC:-}" ]; then
  muere "ENV=production: use E2E_DC explícito (ensayo) para confirmar que no es la base viva"
fi
vol() { docker volume ls -q --filter "label=com.docker.compose.project=$PROJECT" --filter "label=com.docker.compose.volume=$1" | head -1 | tr -d '\r'; }
BACKUPS_VOL="$(vol backups)"; UPLOADS_VOL="$(vol uploads)"
[ -n "$BACKUPS_VOL" ] && [ -n "$UPLOADS_VOL" ] || muere "no se encontraron los volúmenes backups y uploads del proyecto $PROJECT"
echo "restore_e2e: proyecto $PROJECT, red $NET, admin $ADMIN, base de destino $RESTORE_DB"

psqlx() { docker exec -i "$DBCID" psql -X -At -v ON_ERROR_STOP=1 -U "$OWNER" "$@"; }
en_backup() { MSYS_NO_PATHCONV=1 docker run --rm -v "$BACKUPS_VOL:/data/backups" -v "$(nativa "$CLAVES"):/k:ro" --entrypoint bash "$BACKUP_IMG" -c "$1"; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/restore-e2e.XXXXXX")"
CLAVES="$WORK/claves"; SALIDA="$WORK/salida"; PY="$WORK/py"
mkdir -p "$CLAVES" "$SALIDA" "$PY"
chmod 777 "$SALIDA"
limpiar() {
  psqlx -d postgres -c "DROP DATABASE IF EXISTS $RESTORE_DB" > /dev/null 2>&1 || true
  en_backup 'rm -f /data/backups/e2e-* /data/backups/pre-restore-* /data/backups/latest.json /data/backups/latest.json.minisig /data/backups/apex-*' > /dev/null 2>&1 || true
  if [ "${KEEP_WORK:-0}" != "1" ]; then rm -rf "$WORK"; fi
}
trap limpiar EXIT

# --- claves efímeras: par age, par minisign y archivo de entorno del propietario (0600) -----------
MSYS_NO_PATHCONV=1 docker run --rm -v "$(nativa "$CLAVES"):/k" --entrypoint sh "$BACKUP_IMG" -c \
  'age-keygen -o /tmp/id.txt 2>/dev/null && cp /tmp/id.txt /k/id.txt && grep "^# public key:" /tmp/id.txt | sed "s/^# public key: //" > /k/age.pub && minisign -G -W -f -p /k/sign.pub -s /k/sign.key >/dev/null && chmod 644 /k/*'
AGE_PUB="$(tr -d '\r\n' < "$CLAVES/age.pub")"
if [ -n "${CI:-}" ]; then echo "::add-mask::$(grep '^AGE-SECRET-KEY-' "$CLAVES/id.txt" | tr -d '\r\n')"; fi
PTY_FRASE="$(head -c 24 /dev/urandom | base64 | tr -d '/+=\n')"
export PTY_FRASE
if [ -n "${CI:-}" ]; then echo "::add-mask::$PTY_FRASE"; fi
ENVFILE="$WORK/restore.env"
( umask 077
  printf 'PGHOST=db\nPGUSER=%s\nPGPASSWORD=%s\nPGDATABASE=%s\nBACKUP_AGE_RECIPIENT=%s\nBACKUP_KEEP_DAYS=14\n' \
    "$OWNER" "$OWNER_PW" "$RESTORE_DB" "$AGE_PUB" > "$ENVFILE" )

restore_sh() { # <args de restore.sh...>: deja RC y SALIDA_RESTORE (la credencial entra solo por --env-file)
  RC=0
  SALIDA_RESTORE="$(MSYS_NO_PATHCONV=1 docker run --rm --network "$NET" --env-file "$(nativa "$ENVFILE")" \
    -v "$BACKUPS_VOL:/data/backups" -v "$UPLOADS_VOL:/data/uploads" -v "$(nativa "$CLAVES"):/k:ro" \
    -v "$(nativa "$CLAVES")/sign.key:/run/apex/backup/sign.key:ro" --tmpfs /tmp \
    --entrypoint /opt/backup/restore.sh "$BACKUP_IMG" "$@" 2>&1)" || RC=$?
}
base_vacia() { [ "$(psqlx -d "$RESTORE_DB" -c "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")" = "0" ]; }
sin_pre_restore() { [ -z "$(en_backup 'ls /data/backups | grep "^pre-restore-" || true')" ]; }

# --- scripts de Python que corren dentro del contenedor `tools` (mismo código que el api) -------
cat > "$PY/ptyrun.py" << 'PYEOF'
"""Corre un comando bajo un pseudoterminal y teclea la frase cuando age la pide."""
import json, os, pty, re, select, sys, time

AVISO = re.compile(rb"(?i)passphrase[^\n:]*:\s*$")

def correr(args, frase, timeout=120.0):
    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.execvpe(args[0], list(args), dict(os.environ))
        finally:
            os._exit(127)
    salida, desde, limite = b"", 0, time.monotonic() + timeout
    while time.monotonic() < limite:
        listo, _, _ = select.select([fd], [], [], 0.2)
        if not listo:
            continue
        try:
            trozo = os.read(fd, 4096)
        except OSError:
            break
        if not trozo:
            break
        salida += trozo
        if AVISO.search(salida[desde:]):
            desde = len(salida)
            os.write(fd, frase.encode() + b"\n")
    else:
        os.kill(pid, 9)
        raise TimeoutError("el comando bajo pty no terminó a tiempo")
    _, estado = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(estado), salida.decode(errors="replace")

if __name__ == "__main__":
    codigo, texto = correr(json.loads(os.environ["PTY_ARGV"]), os.environ["PTY_FRASE"])
    sys.stdout.write(texto)
    sys.exit(codigo)
PYEOF
cat > "$PY/crear_socio.py" << 'PYEOF'
"""Alta de un socio con documento cifrado; imprime su id."""
import asyncio, os
from app import cli_base
from app.cli_base import crypto_runtime, resolve_admin_actor, unit_of_work
from app.modules.members import service as members
from app.modules.members.schemas import MemberCreate

async def main():
    async with crypto_runtime(cli_base.get_settings()) as session:
        async with session.begin():
            actor = await resolve_admin_actor(session, os.environ["E2E_ADMIN"], required=True)
        with unit_of_work(actor):
            async with session.begin():
                datos = MemberCreate(first_name="Restore", last_name="E2E", document=os.environ["E2E_DOC"], data_consent=True)
                creado = await members.create(session, datos)
    print("MEMBER_ID=" + str(creado.id))

asyncio.run(main())
PYEOF
cat > "$PY/revelar.py" << 'PYEOF'
"""Arranca el bus con la KEK de CRYPTO_LOCAL_KEK_PATH sobre DATABASE_URL y revela el documento."""
import asyncio, os
from uuid import UUID
from app import cli_base
from app.cli_base import crypto_runtime, resolve_admin_actor, unit_of_work
from app.modules.members import service as members

async def main():
    async with crypto_runtime(cli_base.get_settings()) as session:
        async with session.begin():
            actor = await resolve_admin_actor(session, os.environ["E2E_ADMIN"], required=True)
        with unit_of_work(actor):
            async with session.begin():
                visto = await members.reveal(session, UUID(os.environ["E2E_MEMBER"]), "document", ip="127.0.0.1")
    print("REVELADO=" + str(visto.value))

asyncio.run(main())
PYEOF
cat > "$PY/restaurar_kek.py" << 'PYEOF'
"""restore-kek (con pty) a tmpfs y comprobación de la KEK restaurada y de una KEK ajena."""
import os, subprocess, sys
sys.path.insert(0, "/py")
from ptyrun import correr

DB = os.environ["E2E_RESTORE_URL"]
codigo, texto = correr(["python", "-m", "app.cli", "restore-kek", "/salida/kek.age", "--out", "/dev/shm/restaurada-kek.bin", "--as", os.environ["E2E_ADMIN"]], os.environ["PTY_FRASE"])
print("restore-kek salida", codigo)
if codigo != 0:
    sys.stdout.write(texto.replace(os.environ["PTY_FRASE"], "<frase>"))
    sys.exit(1)

def revelar(kek):
    entorno = dict(os.environ, DATABASE_URL=DB, CRYPTO_LOCAL_KEK_PATH=kek)
    return subprocess.run(["python", "/py/revelar.py"], env=entorno, capture_output=True, text=True)

buena = revelar("/dev/shm/restaurada-kek.bin")
print("revelar con la KEK restaurada salida", buena.returncode)
print(buena.stdout.strip())
if buena.returncode != 0:
    sys.stdout.write(buena.stderr[-600:])
    sys.exit(1)
fd = os.open("/dev/shm/otra-kek.bin", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
os.write(fd, os.urandom(32)); os.close(fd)
mala = revelar("/dev/shm/otra-kek.bin")
for ruta in ("/dev/shm/restaurada-kek.bin", "/dev/shm/otra-kek.bin"):
    os.remove(ruta)
print("revelar con otra KEK salida", mala.returncode)
print("unwrap_failed" if "unwrap_failed" in mala.stderr else "SIN-unwrap_failed")
print("documento-visible" if os.environ["E2E_DOC"] in (mala.stdout + mala.stderr) else "sin-documento")
PYEOF
chmod 644 "$PY"/*.py

TOOLS() { "${DC[@]}" --profile tools run --rm -T --no-deps "$@"; }
TOOLS_PY() { MSYS_NO_PATHCONV=1 "${DC[@]}" --profile tools run --rm -T --no-deps -v "$(nativa "$PY"):/py:ro" -v "$(nativa "$SALIDA"):/salida" --entrypoint python "$@"; }

# --- 1. socio, ancla de auditoría, KEK exportada y respaldo ---------------------------------------
psqlx -d postgres -c "DROP DATABASE IF EXISTS $RESTORE_DB" -c "CREATE DATABASE $RESTORE_DB" > /dev/null
DOC="E2E-$(head -c 6 /dev/urandom | od -An -tx1 | tr -d ' \n')"
SALIDA_ALTA="$(TOOLS_PY -e E2E_ADMIN="$ADMIN" -e E2E_DOC="$DOC" tools /py/crear_socio.py | tr -d '\r')"
MEMBER_ID="$(printf '%s\n' "$SALIDA_ALTA" | sed -n 's/^MEMBER_ID=//p' | tail -1)"
[ -n "$MEMBER_ID" ] || muere "no se pudo crear el socio de prueba"
ok "socio con documento cifrado creado"
TOOLS tools verify-audit --as "$ADMIN" > /dev/null
ANCLA_ORIGEN="$(psqlx -d "$MAIN_DB" -F ' ' -c 'SELECT through_seq, through_hash FROM audit.verifications ORDER BY created_at DESC LIMIT 1')"
[ -n "$ANCLA_ORIGEN" ] || muere "la base de origen no tiene verificaciones"
TRIGGERS_ORIGEN="$(psqlx -d "$MAIN_DB" -c "SELECT tgname || ':' || tgenabled::text FROM pg_trigger WHERE NOT tgisinternal ORDER BY 1")"

MSYS_NO_PATHCONV=1 docker run --rm --user 0 -v "$UPLOADS_VOL:/data/uploads" --entrypoint sh "$BACKUP_IMG" -c \
  'echo adjunto-e2e > /data/uploads/e2e-adjunto.txt && chown 10001:10001 /data/uploads/e2e-adjunto.txt' || muere "no se pudo crear el adjunto de prueba"
PTY_ARGV='["python","-m","app.cli","export-kek","--out","/salida/kek.age","--as","'"$ADMIN"'"]'
TOOLS_PY -e PTY_ARGV="$PTY_ARGV" -e PTY_FRASE tools /py/ptyrun.py > /dev/null || muere "export-kek falló"
ok "export-kek con age -p (frase por la terminal)"
PTY_ARGV='["python","-m","app.cli","verify-kek-backup","/salida/kek.age","--as","'"$ADMIN"'"]'
VERIFICACION="$(TOOLS_PY -e PTY_ARGV="$PTY_ARGV" -e PTY_FRASE tools /py/ptyrun.py | tr -d '\r')" || muere "verify-kek-backup falló"
case "$VERIFICACION" in *"failed=0"*) ok "verify-kek-backup abre todas las DEK" ;; *) falla "verify-kek-backup: $VERIFICACION" ;; esac

CLAVE_FIRMA="$(nativa "$CLAVES")/sign.key"
MSYS_NO_PATHCONV=1 BACKUP_SIGN_KEY_FILE="$CLAVE_FIRMA" BACKUP_AGE_RECIPIENT="$AGE_PUB" \
  "${DC[@]}" run --rm -T --no-deps --entrypoint /opt/backup/run.sh backup > /dev/null || muere "run.sh falló"
ok "run.sh: juego de respaldo firmado"

# --- 2. negativas: salen con 2 y no tocan la base ----------------------------------------------------
ARGS=(/data/backups/latest.json -i /k/id.txt -P /k/sign.pub --confirm-database "$RESTORE_DB")
en_backup 'cp /data/backups/latest.json /data/backups/e2e-sin-firma.json'
restore_sh /data/backups/e2e-sin-firma.json -i /k/id.txt -P /k/sign.pub --confirm-database "$RESTORE_DB"
[ "$RC" = 2 ] && ok "manifiesto sin firma: sale 2" || falla "manifiesto sin firma: salió $RC"
en_backup 'sed "s/\"verify\": \"skipped\"/\"verify\": \"ok\"/" /data/backups/latest.json > /data/backups/e2e-alterado.json; cp /data/backups/latest.json.minisig /data/backups/e2e-alterado.json.minisig'
restore_sh /data/backups/e2e-alterado.json -i /k/id.txt -P /k/sign.pub --confirm-database "$RESTORE_DB"
[ "$RC" = 2 ] && ok "firma inválida: sale 2" || falla "firma inválida: salió $RC"
restore_sh /data/backups/latest.json -i /k/id.txt --confirm-database "$RESTORE_DB"
[ "$RC" = 2 ] && ok "sin -P: sale 2" || falla "sin -P: salió $RC"
restore_sh /data/backups/latest.json -i /k/id.txt -P /k/sign.pub --confirm-database otra_base
[ "$RC" = 2 ] && ok "--confirm-database distinto: sale 2" || falla "--confirm-database distinto: salió $RC"
# Juego firmado de verdad cuyo tar trae un enlace simbólico (el sha256 y la firma son válidos).
MSYS_NO_PATHCONV=1 docker run --rm -v "$BACKUPS_VOL:/data/backups" -v "$(nativa "$CLAVES"):/k:ro" -v "$CLAVE_FIRMA:/run/apex/backup/sign.key:ro" --entrypoint bash "$BACKUP_IMG" -c '
set -e; . /opt/backup/lib.sh; cd /tmp; mkdir -p w/uploads; ln -s /etc/passwd w/uploads/enlace
tar -C w -cf - uploads | age -r "$(cat /k/age.pub)" -o /data/backups/e2e-malo-uploads.tar.age
nombre="$(grep -F "\"kind\": \"db\"" /data/backups/latest.json | sed -E "s/.*\"name\": \"([^\"]*)\".*/\1/" | head -1)"
cp "/data/backups/$nombre" /data/backups/e2e-malo-db.dump.age
sd="$(sha256sum < /data/backups/e2e-malo-db.dump.age | cut -d" " -f1)"; su="$(sha256sum < /data/backups/e2e-malo-uploads.tar.age | cut -d" " -f1)"
{ printf "db|e2e-malo-db.dump.age|1|%s|%s\n" "$sd" "$sd"; printf "uploads|e2e-malo-uploads.tar.age|1|%s|%s\n" "$su" "$su"; } \
  | manifest_json e2e-malo 2026-01-01T00:00:00Z x skipped "" skipped "" > /data/backups/e2e-malo.json
minisign -S -s /run/apex/backup/sign.key -m /data/backups/e2e-malo.json -x /data/backups/e2e-malo.json.minisig > /dev/null' \
  || muere "no se pudo armar el juego con tar malicioso"
restore_sh /data/backups/e2e-malo.json -i /k/id.txt -P /k/sign.pub --confirm-database "$RESTORE_DB"
[ "$RC" = 2 ] && ok "tar con enlace simbólico (firmado): sale 2" || falla "tar con enlace simbólico: salió $RC"
verifica "las negativas no tocaron la base de destino" base_vacia
verifica "las negativas no tomaron respaldo pre-restore" sin_pre_restore

MSYS_NO_PATHCONV=1 docker run --rm --user 0 -v "$UPLOADS_VOL:/data/uploads" --entrypoint sh "$BACKUP_IMG" -c 'rm -f /data/uploads/e2e-adjunto.txt'
# --- 3. restauración real ----------------------------------------------------------------------------------
restore_sh "${ARGS[@]}"
[ "$RC" = 0 ] && ok "restore.sh restaura (salida 0)" || { falla "restore.sh salió $RC"; printf '%s\n' "$SALIDA_RESTORE" | sed 's/^/    /' >&2; }
IMPRESA="$(printf '%s\n' "$SALIDA_RESTORE" | sed -n 's/.*ancla de auditoría: through_seq=\([0-9]*\) through_hash=\([0-9a-f]*\).*/\1 \2/p' | tail -1)"
[ "$IMPRESA" = "$ANCLA_ORIGEN" ] && ok "el ancla impresa coincide con audit.verifications de origen" || falla "ancla impresa '$IMPRESA' distinta de la de origen '$ANCLA_ORIGEN'"
ANCLA_RESTAURADA="$(psqlx -d "$RESTORE_DB" -F ' ' -c 'SELECT through_seq, through_hash FROM audit.verifications ORDER BY created_at DESC LIMIT 1')"
[ "$ANCLA_RESTAURADA" = "$ANCLA_ORIGEN" ] && ok "audit.verifications restaurada coincide con la de origen" || falla "audit.verifications restaurada distinta"
TRIGGERS_RESTAURADOS="$(psqlx -d "$RESTORE_DB" -c "SELECT tgname || ':' || tgenabled::text FROM pg_trigger WHERE NOT tgisinternal ORDER BY 1")"
[ "$TRIGGERS_RESTAURADOS" = "$TRIGGERS_ORIGEN" ] && ok "los triggers (WORM incluidos) quedan igual que en origen ($(printf '%s\n' "$TRIGGERS_ORIGEN" | grep -c ':A$') en A)" || falla "triggers distintos tras pg_restore"
[ -n "$(en_backup 'ls /data/backups | grep "^pre-restore-.*\.json$" || true')" ] && ok "el respaldo pre-restore quedó en la carpeta" || falla "no hay respaldo pre-restore"

# dbsetup repone los permisos (el volcado va con --no-acl) y el api lee un adjunto restaurado (L5).
if "${DC[@]}" --profile prod-init run --rm -T --no-deps -e PGDATABASE="$RESTORE_DB" dbsetup > /dev/null 2>&1; then
  ok "dbsetup sobre la base restaurada"
  [ "$(psqlx -d "$RESTORE_DB" -c "SELECT has_table_privilege('apex_api', 'members.members', 'SELECT')")" = "t" ] \
    && ok "apex_api puede leer members.members tras dbsetup" || falla "apex_api sin permiso de lectura tras dbsetup"
else
  falla "dbsetup sobre la base restaurada falló"
fi
DUENO="$(MSYS_NO_PATHCONV=1 docker run --rm -v "$UPLOADS_VOL:/data/uploads:ro" --entrypoint stat "$BACKUP_IMG" -c '%u:%g %a' /data/uploads/e2e-adjunto.txt 2> /dev/null | tr -d '\r')"
case "$DUENO" in "10001:10001 6"*) ok "el adjunto restaurado es del uid 10001 y privado ($DUENO)" ;; *) falla "adjunto restaurado con dueño/modo '$DUENO'" ;; esac
LECTURA="$(MSYS_NO_PATHCONV=1 docker run --rm -v "$UPLOADS_VOL:/data/uploads:ro" --entrypoint cat "$API_IMG" /data/uploads/e2e-adjunto.txt 2> /dev/null | tr -d '\r')"
[ "$LECTURA" = "adjunto-e2e" ] && ok "la imagen del api lee el adjunto restaurado" || falla "el api no pudo leer el adjunto restaurado"

# --- 4. KEK restaurada: el api arranca y revela; con otra KEK, unwrap_failed -------------------------------------
E2E_RESTORE_URL="postgresql+asyncpg://$OWNER:$OWNER_PW@db:5432/$RESTORE_DB"
export E2E_RESTORE_URL
SALIDA_KEK="$(TOOLS_PY -e PTY_FRASE -e E2E_ADMIN="$ADMIN" -e E2E_DOC="$DOC" -e E2E_MEMBER="$MEMBER_ID" \
  -e E2E_RESTORE_URL tools /py/restaurar_kek.py | tr -d '\r')" || { falla "restaurar_kek.py falló"; printf '%s\n' "${SALIDA_KEK//"$OWNER_PW"/<oculto>}" >&2; }
case "$SALIDA_KEK" in *"REVELADO=$DOC"*) ok "con la KEK restaurada, reveal devuelve el documento" ;; *) falla "reveal no devolvió el documento" ;; esac
case "$SALIDA_KEK" in *"unwrap_failed"*) ok "con otra KEK el arranque falla con unwrap_failed" ;; *) falla "con otra KEK no apareció unwrap_failed" ;; esac
case "$SALIDA_KEK" in *"sin-documento"*) ok "con otra KEK no se ve el documento ni material" ;; *) falla "con otra KEK apareció el documento" ;; esac

echo "restore_e2e: $fallas fallas"
[ "$fallas" -eq 0 ]
