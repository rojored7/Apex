#!/usr/bin/env bash
# deploy.sh --ref <vX.Y.Z> --expect-sha <40 hex> --kek-file <ruta>
#           [--i-know-no-backup] [--i-know-unsigned-ref]
#
# Despliegue de una versión etiquetada en el servidor (S4B-B4, US-117; S4B-D41, D56, D67, D81).
# Se corre desde cualquier carpeta: calcula la raíz del repositorio desde su propia ruta.
#
# Salidas: 0 desplegado; 2 uso o preverificación (no se tocó nada: ni el código ni docker; el
# único cambio posible es el checkout del SHA, que se deshace antes de salir); 1 fallo posterior
# al inicio (respaldo, construcción, arranque o salud); el detalle de lo que sigue en pie va a
# <DEPLOY_STATE_DIR>/rollback-<fecha>.txt.
#
# Orden: argumentos -> git (fetch de etiquetas, la etiqueta resuelve al SHA esperado, firma:
# sin .github/allowed_signers o con firma inválida exige --i-know-unsigned-ref, árbol limpio) ->
# .env y .env.ops (modo, propietario, sin seguimiento de git, sin valores de ejemplo, contraseñas)
# -> KEK (cabecera age) y destinatarios -> SKIP_BUILD -> checkout del SHA (desprendido; si algo
# falla después se restaura el código anterior) -> `compose config -q` -> db en marcha ->
# respaldo pre-deploy y su comprobación -> etiquetas prev-<fecha> y deploy-<fecha>.state.json ->
# construcción (o DEPLOY_SKIP_BUILD) -> `up -d` -> sondeo de /api/v1/health -> entorno del api ->
# versión.
#
# Sprint 5 (S5-D15, D74, D96): MIGRATE_DB_USER se exige en .env.ops y su rol debe existir en la base
# (si no, sale 2 antes de construir o levantar); con CRYPTO_PROVIDER=openbao en .env se apila
# infra/compose.openbao.yml (sale 2 si falta) y se avisa si kek.bin sigue en el volumen keys; el sondeo
# acepta el 503 de un api SELLADO (db y migrations en ok) y lo explica, porque un OpenBao sellado tras
# un reinicio es un estado esperado: se desella a mano (docs/operacion/openbao.md).
#
# Variables: DEPLOY_STATE_DIR (por omisión ${XDG_STATE_HOME:-$HOME/.local/state}/apex-deploy,
# FUERA del repositorio para no ensuciar el árbol), DEPLOY_HEALTH_TIMEOUT (segundos; por omisión
# el de .env.ops o 120), DEPLOY_SKIP_BUILD=1 (usa las imágenes ya construidas si su etiqueta
# org.opencontainers.image.revision coincide con la etiqueta pedida), DEPLOY_NOW (AAAAMMDD-HHMMSS,
# solo pruebas). Nunca baja el stack, nunca toca volúmenes, nunca sube nada a ningún sitio.
#
# Todo el cuerpo vive en main(): bash lee la función completa antes de ejecutarla, así el
# `git checkout` de la etiqueta puede reemplazar este mismo archivo sin corromper la corrida.
set -euo pipefail

main() {
  local ROOT
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  cd "$ROOT"

  local REF="" EXPECT_SHA="" KEK_FILE="" NO_BACKUP=0 UNSIGNED_OK=0
  local ENV_FILE=.env OPS_FILE=.env.ops
  local DC=(docker compose --env-file "$ENV_FILE" --env-file "$OPS_FILE" -f infra/compose.yml)
  # DEPLOY_COMPOSE_EXTRA: archivos compose adicionales, p. ej. infra/compose.verify.yml (identidad de verificacion).
  local extra
  # Sin expansión de comodines y con lista blanca: hoy solo infra/compose.verify.yml.
  set -f
  for extra in ${DEPLOY_COMPOSE_EXTRA:-}; do
    [ "$extra" = "infra/compose.verify.yml" ] || { printf 'deploy: ERROR DEPLOY_COMPOSE_EXTRA solo admite infra/compose.verify.yml\n' >&2; exit 2; }
    DC+=(-f "$extra")
  done
  set +f

  local RESTORE_TO=""
  log() { printf 'deploy: %s\n' "$*"; }
  # Si el código ya pasó a la etiqueta, una preverificación fallida lo devuelve a donde estaba.
  restaurar_codigo() {
    if [ -n "$RESTORE_TO" ]; then
      git checkout -q "$RESTORE_TO" > /dev/null 2>&1 || printf 'deploy: aviso: no se pudo volver a %s; hágalo a mano\n' "$RESTORE_TO" >&2
      RESTORE_TO=""
    fi
  }
  die2() { printf 'deploy: ERROR %s\n' "$*" >&2; restaurar_codigo; exit 2; }
  aviso() { printf 'deploy: aviso: %s\n' "$*" >&2; }

  # --- argumentos -----------------------------------------------------------------------------
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --ref) [ "$#" -ge 2 ] || die2 "--ref necesita un valor"; REF="$2"; shift 2 ;;
      --expect-sha) [ "$#" -ge 2 ] || die2 "--expect-sha necesita un valor"; EXPECT_SHA="$2"; shift 2 ;;
      --kek-file) [ "$#" -ge 2 ] || die2 "--kek-file necesita un valor"; KEK_FILE="$2"; shift 2 ;;
      --i-know-no-backup) NO_BACKUP=1; shift ;;
      --i-know-unsigned-ref) UNSIGNED_OK=1; shift ;;
      *) die2 "argumento desconocido: $1 (uso: deploy.sh --ref vX.Y.Z --expect-sha <40 hex> --kek-file <ruta>)" ;;
    esac
  done
  [ -n "$REF" ] || die2 "falta --ref (una etiqueta vX.Y.Z)"
  [ -n "$EXPECT_SHA" ] || die2 "falta --expect-sha (el SHA de 40 caracteres de la etiqueta; sale del CHANGELOG.md o del Release)"
  [[ "$REF" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] || die2 "--ref debe ser una etiqueta vX.Y.Z, nunca una rama"
  [[ "$EXPECT_SHA" =~ ^[0-9a-f]{40}$ ]] || die2 "--expect-sha debe tener 40 caracteres hexadecimales en minúsculas"

  # --- git: la etiqueta es el SHA esperado, firma si hay con qué verificarla, árbol limpio -------
  git fetch --tags --quiet || die2 "git fetch --tags falló (¿sin red al repositorio?)"
  local REAL_SHA
  REAL_SHA="$(git rev-parse "$REF^{commit}" 2> /dev/null)" || die2 "la etiqueta $REF no existe en este repositorio"
  [ "$REAL_SHA" = "$EXPECT_SHA" ] || die2 "el SHA de $REF no coincide con --expect-sha (SHA real $REAL_SHA): no se despliega"
  # Firma (falla cerrado, S4B-D81 ampliada): sin firma verificable solo se sigue con --i-know-unsigned-ref.
  # Con firma o sin ella, la garantía real es --expect-sha, que debe salir del Release, no de este clon.
  if [ -f .github/allowed_signers ] \
    && GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=gpg.format GIT_CONFIG_VALUE_0=ssh \
      GIT_CONFIG_KEY_1=gpg.ssh.allowedSignersFile GIT_CONFIG_VALUE_1=.github/allowed_signers \
      git verify-tag "$REF" > /dev/null 2>&1; then
    log "firma de la etiqueta $REF verificada"
  elif [ "$UNSIGNED_OK" -eq 1 ]; then
    aviso "la etiqueta $REF no tiene firma verificable; sigue por --i-know-unsigned-ref (deuda S4B-D81, v0.2)"
  else
    die2 "etiqueta sin firma verificable: use --i-know-unsigned-ref (y tome --expect-sha del Release, no de este clon)"
  fi
  [ -z "$(git status --porcelain)" ] || die2 "el árbol de trabajo tiene cambios sin confirmar: límpielo antes de desplegar"
  # El checkout va más abajo, después de todo lo que no depende del código nuevo (S4B-D179).

  # --- .env y .env.ops ------------------------------------------------------------------------
  local f
  for f in "$ENV_FILE" "$OPS_FILE"; do
    [ -f "$f" ] || die2 "falta $f (cópielo de ${f}.example o .env.example/.env.ops.example y complételo)"
    local modo
    modo="$(stat -c %a "$f")"
    [[ "$modo" =~ ^[0-7]+$ ]] || die2 "no se pudo leer el modo de $f"
    [ $((8#$modo & 8#177)) -eq 0 ] || die2 "$f tiene modo $modo: debe ser 600 o más estricto (chmod 600 $f)"
    [ "$(stat -c %u "$f")" = "$(id -u)" ] || die2 "$f no pertenece a quien despliega"
    if git ls-files --error-unmatch -- "$f" > /dev/null 2>&1; then
      die2 "$f está bajo seguimiento de git: nunca se versiona"
    fi
    if grep -v '^[[:space:]]*#' "$f" | grep -q 'cambiar-esto'; then
      die2 "$f conserva valores de ejemplo (cambiar-esto)"
    fi
  done
  if grep -qE '^(POSTGRES_|DATABASE_URL=)' "$ENV_FILE"; then
    die2 "$ENV_FILE contiene POSTGRES_* o DATABASE_URL=: esas variables van solo en $OPS_FILE (S4B-D56)"
  fi
  # S5-W0-3 (revisión de seguridad, M1): los dos secretos de canal solo van en .env.ops; `tools`
  # lee .env por env_file y Compose no puede quitarle una clave. Solo se imprime el NOMBRE.
  local secreto_de_canal
  for secreto_de_canal in SMTP_PASSWORD TELEGRAM_BOT_TOKEN; do
    if grep -qE "^${secreto_de_canal}=[^[:space:]]" "$ENV_FILE"; then
      die2 "$ENV_FILE contiene $secreto_de_canal con valor: va solo en $OPS_FILE (S5-D44)"
    fi
  done
  grep -qE '^ENV=production[[:space:]]*$' "$ENV_FILE" || die2 "$ENV_FILE debe tener ENV=production"

  valor() { # <archivo> <clave>: último valor de la clave, sin CR
    { grep -E "^$2=" "$1" || true; } | tail -1 | cut -d= -f2- | tr -d '\r'
  }
  local k
  local -a pw_names=(POSTGRES_PASSWORD APEX_API_DB_PASSWORD APEX_WORKER_DB_PASSWORD APEX_BACKUP_DB_PASSWORD)
  # S5-W0-4 (S5-D89, D142): con MIGRATE_DB_USER=apex_owner (pila nueva) su contraseña también se exige,
  # de 24 o más y distinta de las demás; con otro usuario (servidor existente) no hace falta.
  if [ "$(valor "$OPS_FILE" MIGRATE_DB_USER)" = "apex_owner" ]; then
    pw_names+=(APEX_OWNER_DB_PASSWORD)
  fi
  local -a pw_vals=()
  local v
  for k in "${pw_names[@]}"; do
    v="$(valor "$OPS_FILE" "$k")"
    [ "${#v}" -ge 24 ] || die2 "$k en $OPS_FILE debe tener 24 caracteres o más (openssl rand -hex 24)"
    [[ "$v" =~ ^[A-Za-z0-9._~-]+$ ]] || die2 "$k en $OPS_FILE solo admite [A-Za-z0-9._~-]"
    pw_vals+=("$v")
  done
  local i j
  for i in "${!pw_vals[@]}"; do
    for j in "${!pw_vals[@]}"; do
      if [ "$i" -lt "$j" ] && [ "${pw_vals[$i]}" = "${pw_vals[$j]}" ]; then
        die2 "${pw_names[$i]} y ${pw_names[$j]} son iguales: cada rol lleva su propia contraseña"
      fi
    done
  done

  # --- S5-D96 y S5-D74: rol de las migraciones y proveedor de llaves ----------------------------
  local MIGRATE_ROLE PROVIDER
  MIGRATE_ROLE="$(valor "$OPS_FILE" MIGRATE_DB_USER)"
  [ -n "$MIGRATE_ROLE" ] || die2 "falta MIGRATE_DB_USER en $OPS_FILE (sin valor por defecto: apex_owner en una pila nueva, el propietario actual en un servidor existente)"
  [[ "$MIGRATE_ROLE" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || die2 "MIGRATE_DB_USER en $OPS_FILE solo admite [A-Za-z0-9_] y no puede empezar por un dígito"
  PROVIDER="$(valor "$ENV_FILE" CRYPTO_PROVIDER)"; PROVIDER="${PROVIDER:-local}"
  # S5-W0-4 (S5-D141): contraseñas opcionales de migrate y tools. Sin ellas Compose usa
  # APEX_OWNER_DB_PASSWORD (pila nueva). Si están, deben ser fuertes; con un usuario distinto de
  # apex_owner (servidor existente) son OBLIGATORIAS: la contraseña de ese rol (falla cerrado).
  local var_pw usr_pw
  for var_pw in MIGRATE_DB_PASSWORD TOOLS_DB_PASSWORD; do
    v="$(valor "$OPS_FILE" "$var_pw")"
    if [ -n "$v" ]; then
      [ "${#v}" -ge 24 ] || die2 "$var_pw en $OPS_FILE debe tener 24 caracteres o más (la contraseña del rol correspondiente)"
      [[ "$v" =~ ^[A-Za-z0-9._~-]+$ ]] || die2 "$var_pw en $OPS_FILE solo admite [A-Za-z0-9._~-]"
    else
      usr_pw="$(valor "$OPS_FILE" "${var_pw%_PASSWORD}_USER")"
      if [ -n "$usr_pw" ] && [ "$usr_pw" != "apex_owner" ]; then
        die2 "${var_pw%_PASSWORD}_USER=$usr_pw en $OPS_FILE exige $var_pw (la contraseña de ese rol; Compose no usa APEX_OWNER_DB_PASSWORD con otro usuario, S5-D141)"
      fi
    fi
  done
  case "$PROVIDER" in local|openbao) ;; *) die2 "CRYPTO_PROVIDER en $ENV_FILE debe ser local u openbao" ;; esac

  local WEB_PORT TIMEOUT
  WEB_PORT="$(valor "$OPS_FILE" WEB_PORT)"; WEB_PORT="${WEB_PORT:-80}"
  [[ "$WEB_PORT" =~ ^[0-9]{1,5}$ ]] || die2 "WEB_PORT en $OPS_FILE no es un número"
  TIMEOUT="${DEPLOY_HEALTH_TIMEOUT:-$(valor "$OPS_FILE" DEPLOY_HEALTH_TIMEOUT)}"; TIMEOUT="${TIMEOUT:-120}"
  [[ "$TIMEOUT" =~ ^[0-9]{1,4}$ ]] || die2 "DEPLOY_HEALTH_TIMEOUT debe ser un número de segundos"
  [[ -z "${DEPLOY_NOW:-}" || "${DEPLOY_NOW:-}" =~ ^[0-9]{8}-[0-9]{6}$ ]] || die2 "DEPLOY_NOW debe tener la forma AAAAMMDD-HHMMSS"

  # --- KEK y respaldo --------------------------------------------------------------------------
  [ -n "$KEK_FILE" ] || die2 "falta --kek-file: la copia de la KEK (export-kek) debe existir antes de tocar nada"
  [ -f "$KEK_FILE" ] && [ -r "$KEK_FILE" ] && [ -s "$KEK_FILE" ] || die2 "--kek-file no es un archivo legible y no vacío"
  head -n 1 "$KEK_FILE" 2> /dev/null | tr -d '\r' | grep -aqx 'age-encryption.org/v1' \
    || die2 "--kek-file no es un respaldo de la KEK hecho con export-kek (falta la cabecera de age)"
  if [ "$NO_BACKUP" -eq 0 ]; then
    [ -n "$(valor "$OPS_FILE" BACKUP_AGE_RECIPIENT)" ] || die2 "falta BACKUP_AGE_RECIPIENT en $OPS_FILE (o use --i-know-no-backup)"
    [ -n "$(valor "$OPS_FILE" BACKUP_SIGN_PUBKEY)" ] || die2 "falta BACKUP_SIGN_PUBKEY en $OPS_FILE (o use --i-know-no-backup)"
  else
    aviso "--i-know-no-backup: no habrá respaldo pre-deploy; el despliegue no tendrá vuelta atrás para la base"
  fi

  if [ "${DEPLOY_SKIP_BUILD:-0}" = "1" ]; then
    local img rev
    for img in apex-api:local apex-web:local; do
      rev="$(docker image inspect --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$img" 2> /dev/null | tr -d '\r' || true)"
      [ "$rev" = "$REF" ] || die2 "DEPLOY_SKIP_BUILD=1 pero $img tiene org.opencontainers.image.revision='${rev:-<ninguna>}' y se pidió $REF"
    done
    log "DEPLOY_SKIP_BUILD=1: las imágenes locales ya son de $REF"
  fi

  # --- el código pasa al SHA de la etiqueta (desprendido: sin ambigüedad rama/etiqueta) ----------
  local PREV_HEAD PREV_BRANCH
  PREV_HEAD="$(git rev-parse HEAD 2> /dev/null || true)"
  PREV_BRANCH="$(git symbolic-ref -q --short HEAD 2> /dev/null || true)"
  git checkout -q --detach "$REAL_SHA" || die2 "git checkout de $REAL_SHA falló"
  RESTORE_TO="${PREV_BRANCH:-$PREV_HEAD}"
  [ -z "$(git status --porcelain)" ] || die2 "el árbol quedó sucio tras el checkout de $REF"
  log "código en $REF ($REAL_SHA)"

  # El overlay llega con el código de la etiqueta; con openbao es obligatorio (api y worker sin keys).
  if [ "$PROVIDER" = "openbao" ]; then
    [ -f infra/compose.openbao.yml ] || die2 "CRYPTO_PROVIDER=openbao pero $REF no trae infra/compose.openbao.yml"
    DC+=(-f infra/compose.openbao.yml)
    log "CRYPTO_PROVIDER=openbao: se apila infra/compose.openbao.yml"
  fi

  "${DC[@]}" config -q || die2 "docker compose config -q rechaza la configuración"

  [ -n "$("${DC[@]}" ps --status running -q db 2> /dev/null | tr -d '\r')" ]     || die2 "el servicio db no está en marcha: este script actualiza un servidor ya instalado (instalar-en-servidor.md)"
  # S5-D96: migrate corre con MIGRATE_DB_USER; si el rol no existe fallaría a mitad del despliegue.
  # Se consulta con psql como propietario (exec db) antes de respaldar, construir, levantar o etiquetar.
  # El nombre ya se validó contra [A-Za-z0-9_]: es seguro interpolarlo.
  local fila
  fila="$("${DC[@]}" exec -T db sh -c "psql -U \"\$POSTGRES_USER\" -d postgres -Atc \"SELECT 1 FROM pg_roles WHERE rolname = '$MIGRATE_ROLE'\"" 2> /dev/null | tr -d '\r' || true)"
  [ "$fila" = "1" ] || die2 "el rol $MIGRATE_ROLE no existe: corra \`dbsetup\` o fije MIGRATE_DB_USER"
  RESTORE_TO=""

  # --- a partir de aquí un fallo es 1 y deja constancia -----------------------------------------
  local NOW STATE_DIR
  NOW="${DEPLOY_NOW:-$(date +%Y%m%d-%H%M%S)}"
  STATE_DIR="${DEPLOY_STATE_DIR:-${XDG_STATE_HOME:-$HOME/.local/state}/apex-deploy}"
  ( umask 077; mkdir -p "$STATE_DIR" )

  local MANIFEST_NAME="(ninguno: se usó --i-know-no-backup)"
  if [ "$NO_BACKUP" -eq 0 ]; then
    local salida
    log "respaldo pre-deploy"
    if ! salida="$("${DC[@]}" run --rm backup /opt/backup/run.sh --prefix pre-deploy < /dev/null 2>&1)"; then
      printf '%s\n' "$salida" | tr -d '\r' | tail -20 >&2
      printf 'deploy: ERROR el respaldo pre-deploy falló; no se construyó ni se levantó nada\n' >&2
      exit 1
    fi
    MANIFEST_NAME="$(printf '%s\n' "$salida" | tr -d '\r' | sed -n 's/^run\.sh: listo \(pre-deploy-[0-9]\{8\}-[0-9]\{6\}\)$/\1/p' | tail -1)"
    if [ -z "$MANIFEST_NAME" ]; then
      printf 'deploy: ERROR no se pudo leer el nombre del respaldo pre-deploy\n' >&2
      exit 1
    fi
    # Comprobación: los dos archivos cifrados (cabecera de age), el manifiesto y su firma válida.
    if ! "${DC[@]}" run --rm --no-deps --entrypoint sh backup -c '
        n="$1"; d=/data/backups
        for f in "$d/$n-db.dump.age" "$d/$n-uploads.tar.age"; do
          [ -s "$f" ] || { echo "falta $f" >&2; exit 1; }
          head -n 1 "$f" | grep -aqx "age-encryption.org/v1" || { echo "cabecera inválida en $f" >&2; exit 1; }
        done
        [ -s "$d/$n.json" ] && [ -s "$d/$n.json.minisig" ] || { echo "falta el manifiesto firmado" >&2; exit 1; }
        minisign -V -P "$BACKUP_SIGN_PUBKEY" -m "$d/$n.json" -x "$d/$n.json.minisig" > /dev/null
      ' sh "$MANIFEST_NAME" < /dev/null > /dev/null; then
      printf 'deploy: ERROR el respaldo %s está incompleto o su firma no verifica; no se continúa\n' "$MANIFEST_NAME" >&2
      exit 1
    fi
    log "respaldo $MANIFEST_NAME comprobado (dos archivos age y manifiesto firmado)"
  fi

  # Etiquetas prev-<fecha> de lo que corre AHORA (no de lo que diga :local, que con SKIP_BUILD ya
  # puede ser lo nuevo).
  local svc cid src
  local -a PREV_IMAGES=()
  for svc in api web backup; do
    cid="$("${DC[@]}" ps -q "$svc" 2> /dev/null | head -1 | tr -d '\r' || true)"
    src=""
    if [ -n "$cid" ]; then src="$(docker inspect -f '{{.Image}}' "$cid" 2> /dev/null | tr -d '\r' || true)"; fi
    [ -n "$src" ] || src="apex-$svc:local"
    docker tag "$src" "apex-$svc:prev-$NOW" || { printf 'deploy: ERROR no se pudo etiquetar apex-%s:prev-%s\n' "$svc" "$NOW" >&2; exit 1; }
    PREV_IMAGES+=("apex-$svc:prev-$NOW")
  done
  local STATE_FILE="$STATE_DIR/deploy-$NOW.state.json"
  (
    umask 077
    {
      printf '{\n'
      printf '  "ref": "%s",\n' "$REF"
      printf '  "sha": "%s",\n' "$REAL_SHA"
      printf '  "prev_head": "%s",\n' "$PREV_HEAD"
      printf '  "prev_tag": "prev-%s",\n' "$NOW"
      printf '  "manifest": "%s",\n' "$MANIFEST_NAME"
      printf '  "images": ["%s", "%s", "%s"]\n' "${PREV_IMAGES[0]}" "${PREV_IMAGES[1]}" "${PREV_IMAGES[2]}"
      printf '}\n'
    } > "$STATE_FILE"
  )
  log "estado guardado en $STATE_FILE"

  # --- construcción y arranque -----------------------------------------------------------------
  if [ "${DEPLOY_SKIP_BUILD:-0}" != "1" ]; then
    log "construcción de las imágenes de $REF"
    GIT_SHA="$REF" "${DC[@]}" build || { printf 'deploy: ERROR la construcción falló; lo que corre no se tocó\n' >&2; exit 1; }
  fi

  local ROLLBACK="$STATE_DIR/rollback-$NOW.txt"
  escribir_rollback() ( # <motivo>; subshell: el umask no escapa
    umask 077
    {
      printf 'APEX · despliegue de %s fallido (%s)\n\n' "$REF" "$NOW"
      printf 'Motivo: %s\n\n' "$1"
      printf 'Imágenes anteriores (etiquetadas antes de construir):\n'
      printf '  %s\n' "${PREV_IMAGES[@]}"
      printf 'Respaldo previo: %s (manifiesto %s.json y %s.json.minisig en el volumen backups)\n' "$MANIFEST_NAME" "$MANIFEST_NAME" "$MANIFEST_NAME"
      printf 'Código anterior: %s\n\n' "${PREV_HEAD:-desconocido}"
      printf 'Para volver al código y a las imágenes anteriores:\n'
      printf '  git checkout %s\n' "${PREV_HEAD:-<código anterior>}"
      printf '  docker tag apex-api:prev-%s apex-api:local\n' "$NOW"
      printf '  docker tag apex-web:prev-%s apex-web:local\n' "$NOW"
      printf '  docker tag apex-backup:prev-%s apex-backup:local\n' "$NOW"
      printf '  docker compose --env-file .env --env-file .env.ops -f infra/compose.yml up -d\n\n'
      printf 'Importante: este script no restaura la base. Si la migración nueva ya corrió, bajar\n'
      printf 'las imágenes NO deshace el esquema: siga docs/RUNBOOK.md sección 12 (rollback por\n'
      printf 'migración o restauración del respaldo previo con restore.sh).\n'
    } > "$ROLLBACK"
  )
  fallo_despliegue() { # <motivo>
    printf 'deploy: ERROR %s\n' "$1" >&2
    printf 'deploy: últimas 100 líneas del log del api (filtradas):\n' >&2
    "${DC[@]}" logs --tail 100 api 2>&1 | tr -d '\r' | { grep -viE 'input_value|PASSWORD|SECRET|KEY|TOKEN' || true; } >&2 || true
    escribir_rollback "$1"
    printf 'deploy: instrucciones de vuelta atrás en %s\n' "$ROLLBACK" >&2
    exit 1
  }

  log "arranque (openbao, migrate y dbsetup corren solos antes del api)"
  if ! GIT_SHA="$REF" "${DC[@]}" up -d; then
    fallo_despliegue "docker compose up -d terminó con error"
  fi

  # --- salud: db y migrations en ok ------------------------------------------------------------
  # S5-D15: curl SIN -f y con el código HTTP aparte, para leer el cuerpo de un 503. Solo 200 y 503
  # cuentan; un 503 es sano únicamente si trae db y migrations en ok (api sellado, no caído).
  local url="http://127.0.0.1:${WEB_PORT}/api/v1/health" body="" waited=0 healthy=0 code=""
  # L2: el archivo temporal del sondeo se borra aunque el script salga por cualquier camino (trap en EXIT).
  PROBE_TMP="$(mktemp)"
  trap 'rm -f "${PROBE_TMP:-}"' EXIT
  local probe="$PROBE_TMP"
  log "sondeo de $url (hasta ${TIMEOUT} s)"
  while :; do
    # Si curl falla (sin respuesta) la vuelta cuenta como no sana, diga lo que diga el cuerpo.
    if code="$(curl -sS -o "$probe" -w '%{http_code}' --max-time 5 "$url" 2> /dev/null)"; then
      body="$(tr -d '\r' < "$probe")"
    else
      code=""; body=""
    fi
    case "$code" in 200|503) ;; *) body="" ;; esac
    if printf '%s' "$body" | grep -Eq '"db": ?"ok"' && printf '%s' "$body" | grep -Eq '"migrations": ?"ok"'; then
      healthy=1; break
    fi
    [ "$waited" -lt "$TIMEOUT" ] || break
    sleep 3
    waited=$((waited + 3))
  done
  rm -f "$probe"
  [ "$healthy" -eq 1 ] || fallo_despliegue "/health no llegó a db ok y migrations ok en ${TIMEOUT} s"
  if printf '%s' "$body" | grep -Eq '"crypto": ?"sealed"'; then
    log "api en estado sellado: desellar OpenBao (docs/operacion/openbao.md)"
  fi

  # --- entorno del api (S4B-D56): sin secretos de operación y con la versión pedida -------------
  local envapi
  envapi="$("${DC[@]}" exec -T api sh -c 'tr "\0" "\n" < /proc/1/environ' 2> /dev/null | tr -d '\r' || true)"
  [ -n "$envapi" ] || fallo_despliegue "no se pudo leer /proc/1/environ del api"
  local prohibidas
  prohibidas="$(printf '%s\n' "$envapi" | cut -d= -f1 | grep -E '^(POSTGRES_[A-Z_]*|APEX_[A-Z_]*_DB_PASSWORD|RCLONE_[A-Z_]*|BACKUP_SIGN_[A-Z_]*|BACKUP_AGE_[A-Z_]*|BACKUP_VERIFY_[A-Z_]*)$' || true)"
  [ -z "$prohibidas" ] || fallo_despliegue "el api tiene variables de operación que no le tocan: $(printf '%s' "$prohibidas" | tr '\n' ' ')"
  # S5-W0-3 (L-9): web no recibe ningún dato de correo ni de Telegram. Solo NOMBRES, nunca valores.
  local envweb ajenas_web
  envweb="$("${DC[@]}" exec -T web sh -c 'tr "\0" "\n" < /proc/1/environ' 2> /dev/null | tr -d '\r' || true)"
  [ -n "$envweb" ] || fallo_despliegue "no se pudo leer /proc/1/environ de web"
  ajenas_web="$(printf '%s\n' "$envweb" | cut -d= -f1 | grep -E '^(SMTP_[A-Z_]*|TELEGRAM_[A-Z_]*)$' || true)"
  [ -z "$ajenas_web" ] || fallo_despliegue "web tiene variables de canales que no le tocan: $(printf '%s' "$ajenas_web" | tr '\n' ' ')"
  # DATABASE_URL debe existir en el api y usar su rol: su ausencia también es un fallo.
  if ! printf '%s\n' "$envapi" | grep -q '^DATABASE_URL=postgresql+asyncpg://apex_api:'; then
    fallo_despliegue "el api no usa su rol apex_api en DATABASE_URL"
  fi
  local appver
  appver="$(printf '%s\n' "$envapi" | sed -n 's/^APP_VERSION=//p' | tail -1)"
  [ "$appver" = "$REF" ] || fallo_despliegue "APP_VERSION del api es '${appver:-<vacía>}' y se esperaba $REF"

  # S5-D74: con OpenBao la KEK ya no debe estar en un archivo a mano del api; tools conserva el
  # volumen keys solo para migrate-provider. Un kek.bin que sigue ahí es un aviso, nunca un fallo.
  if [ "$PROVIDER" = "openbao" ]; then
    if "${DC[@]}" run --rm -T --no-deps --entrypoint test tools -f /run/apex/keys/kek.bin > /dev/null 2>&1; then
      aviso "kek.bin sigue en el volumen keys: con OpenBao verificado, retírela (docs/operacion/openbao.md)"
    fi
  fi

  local version
  version="$(printf '%s' "$body" | sed -n 's/.*"version": *"\([^"]*\)".*/\1/p')"
  log "despliegue listo: versión ${version:-$REF} (etiqueta $REF, respaldo previo $MANIFEST_NAME, proveedor de llaves $PROVIDER)"
}

main "$@"
exit 0
