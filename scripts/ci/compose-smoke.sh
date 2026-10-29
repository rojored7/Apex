#!/usr/bin/env bash
# compose-smoke.sh
#
# Smoke del stack (US-005, T14; US-006, T10). Levanta db, db_test y api con build,
# espera db y db_test en healthy, exige api en ejecución y, salvo que
# SMOKE_ALLOW_UNHEALTHY=1 (solo mientras no exista /health, US-020), api en healthy.
# Si existe web/Dockerfile levanta web y corre scripts/ci/web-smoke.sh. Al final
# baja el stack con sus volúmenes, salvo SMOKE_KEEP=1.
# S2-W0-1: con api healthy corre `tools seed` leyendo ADMIN_* de .env.seed (si no existe,
# crea uno efímero con una contraseña aleatoria y lo borra al salir; uno existente no se
# toca) y comprueba que web tiene la IP fija de TRUSTED_PROXIES.
# S4B-W0-1: tras el seed levanta backup y hace una corrida real con claves de prueba.
# S4B-W0-3: sin perfil no se listan migrate ni dbsetup; los dos --env-file (.env y .env.ops).
# S4A-W0-2: con api healthy levanta worker (sin perfil), exige healthy y 0 reinicios tras
# 30 s, corre `--run-once expirations` dos veces y compara el id de las dos `--status`.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
[ -f .env ] || cp .env.example .env
# S4B-W0-3 (S4B-D79, E7): las variables de operación (POSTGRES_*, puertos...) viven en .env.ops. En
# este equipo .env es la suma de los dos ejemplos y no hace falta; en un clon limpio .env.ops sale
# del ejemplo. Compose recibe los dos --env-file (el segundo manda si repite una clave).
if ! grep -q "^POSTGRES_PASSWORD=" .env && [ ! -f .env.ops ]; then cp .env.ops.example .env.ops; fi
ENVS=(--env-file .env)
if [ -f .env.ops ]; then ENVS+=(--env-file .env.ops); fi
DC=(docker compose "${ENVS[@]}" -f infra/compose.yml -f infra/compose.dev.yml)

SEED_EFIMERO=0
bajar() {
  if [ "$SEED_EFIMERO" = "1" ]; then rm -f "$ROOT/.env.seed"; fi
  if [ "${SMOKE_KEEP:-0}" = "1" ]; then
    echo "compose-smoke: SMOKE_KEEP=1, el stack queda arriba"
  else
    if [ "${CI:-}" != "" ]; then
      "${DC[@]}" down -v --remove-orphans > /dev/null 2>&1 || true
    else
      # Fuera de CI nunca se borran los volúmenes del proyecto apex (pgdata, uploads, keys).
      "${DC[@]}" down --remove-orphans > /dev/null 2>&1 || true
    fi
  fi
}
trap bajar EXIT

estado() { "${DC[@]}" ps --format json "$1" 2>/dev/null | tr -d '\r' | head -1; }
campo() { estado "$1" | sed -n "s/.*\"$2\":\"\([^\"]*\)\".*/\1/p"; }

esperar_healthy() {
  local svc="$1" limite="$2" t=0
  while [ "$t" -lt "$limite" ]; do
    [ "$(campo "$svc" Health)" = "healthy" ] && { echo "compose-smoke: $svc healthy a los ${t}s"; return 0; }
    sleep 3; t=$((t + 3))
  done
  echo "compose-smoke: $svc no llegó a healthy en ${limite}s (estado: $(campo "$svc" State)/$(campo "$svc" Health))" >&2
  "${DC[@]}" logs --tail 40 "$svc" >&2 || true
  return 1
}

inicio=$(date +%s)
# S4B-W0-3 (S4B-D99, S4B-D100): en desarrollo migrate y dbsetup llevan el perfil prod-init: sin él no
# se listan y nada depende de ellos (el api migra al arrancar con el propietario). test_db_roles.sh
# no corre aquí: este smoke no aplica roles.
servicios="$("${DC[@]}" config --services | tr -d '\r')"
for svc in migrate dbsetup; do
  if printf '%s\n' "$servicios" | grep -qx "$svc"; then
    echo "compose-smoke: $svc aparece sin el perfil prod-init" >&2; exit 1
  fi
done
echo "compose-smoke: migrate y dbsetup solo existen con el perfil prod-init"
"${DC[@]}" build api
"${DC[@]}" up -d --build db db_test
esperar_healthy db 120
esperar_healthy db_test 120
# US-023: sin KEK, llave de firma y par JWT en el volumen keys, el api no arranca.
# init-keys es idempotente: en un volumen ya poblado no toca nada.
"${DC[@]}" --profile tools run --rm tools init-keys
"${DC[@]}" up -d api
[ "$(campo api State)" = "running" ] || { echo "compose-smoke: api no está en ejecución" >&2; "${DC[@]}" logs --tail 40 api >&2; exit 1; }
echo "compose-smoke: api en ejecución"

if [ "${SMOKE_ALLOW_UNHEALTHY:-0}" = "1" ]; then
  echo "compose-smoke: SMOKE_ALLOW_UNHEALTHY=1, no se exige api healthy (hasta US-020)"
else
  esperar_healthy api 90
fi

# S4A-W0-2 (US-113, S4A-D9): el worker es parte del stack por defecto (sin perfil), llega a
# healthy por el latido y no se reinicia; `--run-once expirations` dos veces el mismo día
# reutiliza la misma fila de worker.job_runs (mismo id en --status). Enmienda E6: la primera
# invocación acepta 0 o 3 (el serve del contenedor puede estar recuperando el ciclo del día).
if ! "${DC[@]}" config --services | tr -d '\r' | grep -qx worker; then
  echo "compose-smoke: worker no está en el stack por defecto (sigue tras un perfil)" >&2; exit 1
fi
"${DC[@]}" up -d worker
esperar_healthy worker 120
sleep 30
reinicios="$(docker inspect -f '{{.RestartCount}}' "$("${DC[@]}" ps -q worker | tr -d '\r')" | tr -d '\r')"
[ "$reinicios" = "0" ] || { echo "compose-smoke: worker con $reinicios reinicios" >&2; "${DC[@]}" logs --tail 40 worker >&2; exit 1; }
echo "compose-smoke: worker sin reinicios tras 30s"

worker_cli() { "${DC[@]}" run --rm -T worker python -m app.worker.main "$@"; }
estado_job() {
  local salida linea
  salida="$(worker_cli --status expirations | tr -d '\r')" || { echo "compose-smoke: --status expirations falló" >&2; return 1; }
  linea="$(printf '%s\n' "$salida" | grep '^{"details": ' | tail -1)"
  [ -n "$linea" ] || { echo "compose-smoke: --status expirations sin JSON" >&2; return 1; }
  printf '%s\n' "$linea"
}
id_de() { printf '%s\n' "$1" | sed -n 's/.*"id": "\([^"]*\)".*/\1/p'; }
resultado_de() { printf '%s\n' "$1" | sed -n 's/.*"result": "\([^"]*\)".*/\1/p'; }

set +e; worker_cli --run-once expirations > /dev/null; codigo=$?; set -e
case "$codigo" in
  0) echo "compose-smoke: --run-once expirations (1) salida 0" ;;
  3) echo "compose-smoke: --run-once expirations (1) salida 3 (corrida running vigente, E6); se espera a que cierre"
     for _ in $(seq 1 20); do
       [ "$(resultado_de "$(estado_job)")" = "running" ] || break
       sleep 3
     done ;;
  *) echo "compose-smoke: --run-once expirations (1) salida $codigo (se esperaba 0 o 3)" >&2; exit 1 ;;
esac
primero="$(estado_job)"
[ "$(resultado_de "$primero")" = "ok" ] || { echo "compose-smoke: --status tras la primera corrida: $primero" >&2; exit 1; }
set +e; worker_cli --run-once expirations > /dev/null; codigo=$?; set -e
[ "$codigo" = "0" ] || { echo "compose-smoke: --run-once expirations (2) salida $codigo (se esperaba 0)" >&2; exit 1; }
echo "compose-smoke: --run-once expirations (2) salida 0"
segundo="$(estado_job)"
[ "$(resultado_de "$segundo")" = "ok" ] || { echo "compose-smoke: --status tras la segunda corrida: $segundo" >&2; exit 1; }
[ -n "$(id_de "$primero")" ] && [ "$(id_de "$primero")" = "$(id_de "$segundo")" ] \
  || { echo "compose-smoke: las dos corridas del día no usan la misma fila ($(id_de "$primero") / $(id_de "$segundo"))" >&2; exit 1; }
echo "compose-smoke: --status expirations ok, misma fila en las dos corridas"

# M-8: ADMIN_* solo llegan a tools por .env.seed. Seed idempotente: con un admin activo
# responde "omitido".
if [ ! -f .env.seed ]; then
  SEED_EFIMERO=1
  ( umask 077
    printf 'ADMIN_EMAIL=admin@smoke.apex.local\nADMIN_INITIAL_PASSWORD=%s\n' "$(head -c 24 /dev/urandom | base64 | tr -d '/+=\n')" > .env.seed )
  echo "compose-smoke: .env.seed efímero creado (se borra al salir)"
fi
"${DC[@]}" --profile tools run --rm tools seed
if "${DC[@]}" exec -T api sh -c 'env | grep -q "^ADMIN_[A-Z_]*=."'; then
  echo "compose-smoke: el api recibe ADMIN_* con valor (deben ir solo en .env.seed)" >&2; exit 1
fi
echo "compose-smoke: api sin ADMIN_*"

# S4B-W0-1 (US-114; S4B-D14, D57, D59, D96): servicio backup. Sin destinatario queda inerte pero
# visible (healthy y el log lo dice). Luego un par age y una llave minisign DE PRUEBA (solo en este
# smoke, en una carpeta ignorada, borradas al salir) para una corrida real contra la base de
# desarrollo: manifiesto válido y firmado, dos archivos age, verify skipped, upload skipped, y los
# dos descifran con la identidad de prueba (pg_restore --list lista members.members; tar lista uploads/).
if [ -f infra/backup/Dockerfile ]; then
  "${DC[@]}" up -d --build backup
  esperar_healthy backup 60
  "${DC[@]}" logs backup 2>&1 | tr -d '\r' | grep -q 'backup deshabilitado: falta BACKUP_AGE_RECIPIENT' \
    || { echo "compose-smoke: backup sin destinatario no avisa que está deshabilitado" >&2; exit 1; }
  echo "compose-smoke: backup inerte y visible sin destinatario"

  CLAVES="$ROOT/scripts/ci/tmp.backup-smoke"
  rm -rf "$CLAVES"; mkdir -p "$CLAVES"
  trap 'rm -rf "$CLAVES"; bajar' EXIT
  BACKUP_IMG=apex-backup:local
  # Archivos de prueba efímeros: 644 para que el UID 10001 del contenedor los lea en Linux.
  MSYS_NO_PATHCONV=1 docker run --rm -v "$CLAVES:/k" --entrypoint sh "$BACKUP_IMG" -c \
    'age-keygen -o /tmp/id.txt 2>/dev/null && cp /tmp/id.txt /k/id.txt && grep "^# public key:" /tmp/id.txt | sed "s/^# public key: //" > /k/age.pub && minisign -G -W -f -p /k/sign.pub -s /k/sign.key >/dev/null && chmod 644 /k/*'
  AGE_PUB="$(tr -d '\r\n' < "$CLAVES/age.pub")"
  SIGN_PUB="$(sed -n '2p' "$CLAVES/sign.pub" | tr -d '\r\n')"
  if [ -n "${CI:-}" ]; then
    echo "::add-mask::$(grep '^AGE-SECRET-KEY-' "$CLAVES/id.txt" | tr -d '\r\n')"
  fi
  # En Windows (Git Bash) la ruta del bind va en formato nativo y sin conversión del resto de argumentos.
  CLAVE_FIRMA="$CLAVES/sign.key"
  if command -v cygpath > /dev/null 2>&1; then CLAVE_FIRMA="$(cygpath -m "$CLAVE_FIRMA")"; fi
  MSYS_NO_PATHCONV=1 BACKUP_SIGN_KEY_FILE="$CLAVE_FIRMA" BACKUP_AGE_RECIPIENT="$AGE_PUB" BACKUP_SIGN_PUBKEY="$SIGN_PUB" \
    "${DC[@]}" run --rm -T --no-deps --entrypoint /opt/backup/run.sh backup
  VOL="$(docker volume ls -q --filter label=com.docker.compose.project=apex --filter label=com.docker.compose.volume=backups | head -1 | tr -d '\r')"
  [ -n "$VOL" ] || { echo "compose-smoke: no se encontró el volumen backups" >&2; exit 1; }
  en_backup() { MSYS_NO_PATHCONV=1 docker run --rm -v "$VOL:/data/backups:ro" -v "$CLAVES:/k:ro" --entrypoint sh "$BACKUP_IMG" -c "$1"; }
  MANIFIESTO="$(en_backup 'cat /data/backups/latest.json' | tr -d '\r')"
  NOMBRE="$(printf '%s\n' "$MANIFIESTO" | sed -n 's/.*"name": "\([^"]*\)".*/\1/p' | head -1)"
  printf '%s\n' "$MANIFIESTO" > "$CLAVES/latest.json"
  uv run --directory api --quiet python ../infra/backup/tests/validate_manifest.py ../infra/backup/manifest.schema.json "$CLAVES/latest.json" \
    || { echo "compose-smoke: latest.json no cumple manifest.schema.json" >&2; exit 1; }
  printf '%s\n' "$MANIFIESTO" | grep -q '"verify": "skipped"' || { echo "compose-smoke: se esperaba verify skipped" >&2; exit 1; }
  printf '%s\n' "$MANIFIESTO" | grep -q '"upload": "skipped"' || { echo "compose-smoke: se esperaba upload skipped" >&2; exit 1; }
  en_backup "minisign -V -P '$SIGN_PUB' -m /data/backups/latest.json -x /data/backups/latest.json.minisig >/dev/null" \
    || { echo "compose-smoke: la firma de latest.json no verifica" >&2; exit 1; }
  en_backup "for f in /data/backups/$NOMBRE-db.dump.age /data/backups/$NOMBRE-uploads.tar.age; do [ \"\$(head -c 21 \$f)\" = 'age-encryption.org/v1' ] || exit 1; done" \
    || { echo "compose-smoke: los archivos no tienen cabecera age" >&2; exit 1; }
  en_backup "age -d -i /k/id.txt /data/backups/$NOMBRE-db.dump.age | pg_restore --list | grep -q members" \
    || { echo "compose-smoke: el volcado descifrado no lista members" >&2; exit 1; }
  en_backup "age -d -i /k/id.txt /data/backups/$NOMBRE-uploads.tar.age | tar -t | grep -q '^uploads/'" \
    || { echo "compose-smoke: el tar de uploads descifrado no lista uploads/" >&2; exit 1; }
  # Limpieza: solo el juego de esta corrida y el manifiesto (el volumen es del proyecto).
  MSYS_NO_PATHCONV=1 docker run --rm -v "$VOL:/data/backups" --entrypoint sh "$BACKUP_IMG" -c \
    "rm -f /data/backups/$NOMBRE-db.dump.age /data/backups/$NOMBRE-uploads.tar.age /data/backups/latest.json /data/backups/latest.json.minisig"
  echo "compose-smoke: backup: manifiesto firmado, dos archivos age que descifran, verify y upload skipped"
fi

if [ -f web/Dockerfile ] && [ -f scripts/ci/web-smoke.sh ]; then
  "${DC[@]}" up -d --build web
  esperar_healthy web 60
  # M-1: la IP de web es la única de TRUSTED_PROXIES.
  ip_web="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$("${DC[@]}" ps -q web)" | tr -d '\r')"
  confianza="$(grep -E '^TRUSTED_PROXIES=' .env | cut -d= -f2 | tr -d '\r')"
  if [ "$confianza" != "$ip_web/32" ]; then
    echo "compose-smoke: web está en $ip_web y TRUSTED_PROXIES=$confianza (deben coincidir)" >&2; exit 1
  fi
  echo "compose-smoke: web en $ip_web = TRUSTED_PROXIES"
  bash scripts/ci/web-smoke.sh
  # US-038: cabeceras de seguridad y CSP con nonce contra el stack construido.
  [ -f scripts/smoke/headers.sh ] && bash scripts/smoke/headers.sh
fi
echo "compose-smoke: verde en $(( $(date +%s) - inicio ))s"
