#!/usr/bin/env bash
# test_env_isolation.sh
#
# Prueba VIVA de H-1 (S4B-D56, precisión de la revisión de seguridad de W0-3): lee el entorno del
# proceso 1 de cada contenedor (`/proc/1/environ`) y falla si trae un secreto que no le toca. Solo
# imprime NOMBRES de variable; jamás un valor. Corre contra un stack que arranca como producción
# (job `e2e-stack` de la CI, ensayo `apex-ensayo`, `prod-smoke.sh`), no contra el de desarrollo,
# donde `.env` es la suma de los dos ejemplos.
#
# Reglas por servicio (api, worker y web nunca ven nada de operación; backup solo lo suyo):
#   api         : ni POSTGRES_PASSWORD, ni *_DB_PASSWORD, ni RCLONE_*, BACKUP_SIGN_*, BACKUP_AGE_*,
#                 BACKUP_VERIFY_*; su DATABASE_URL no usa al propietario.
#   worker      : lo mismo salvo BACKUP_SIGN_PUBKEY (S5-B13, S5-D170: llave pública para verificar
#                 la firma del manifiesto; nunca la privada).
#   backup      : puede tener PGPASSWORD (de apex_backup), RCLONE_*, BACKUP_SIGN_PUBKEY y
#                 BACKUP_AGE_*; no POSTGRES_PASSWORD ni *_DB_PASSWORD ni DATABASE_URL.
# Además, ninguna contraseña de .env.ops (por valor) aparece donde no corresponde.
# Variables: DC (comando compose; por defecto el de producción con los dos --env-file) y
# OPS_ENV_FILE (para comparar por valor; opcional), SERVICIOS (por defecto "api worker backup").
set -uo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
if [ -z "${DC:-}" ]; then
  DC="docker compose --env-file .env --env-file .env.ops -f infra/compose.yml"
fi
OPS_ENV_FILE="${OPS_ENV_FILE:-.env.ops}"
SERVICIOS="${SERVICIOS:-api worker backup}"

fallas=0
ok() { echo "  ok   $1"; }
falla() { echo "  FALLA $1"; fallas=$((fallas + 1)); }

valor_de() { # clave -> valor de OPS_ENV_FILE
  [ -f "$OPS_ENV_FILE" ] || return 0
  grep -E "^$1=" "$OPS_ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '\r'
}

entorno_de() { # servicio -> NOMBRE=valor por línea (solo se filtra y compara aquí dentro)
  $DC exec -T "$1" sh -c "tr '\\0' '\\n' < /proc/1/environ" 2> /dev/null | tr -d '\r'
}

for svc in $SERVICIOS; do
  if ! entorno="$(entorno_de "$svc")" || [ -z "$entorno" ]; then
    falla "$svc: no se pudo leer /proc/1/environ"
    continue
  fi
  nombres="$(printf '%s\n' "$entorno" | cut -d= -f1)"
  case "$svc" in
    backup)
      prohibidos='^(POSTGRES_PASSWORD|APEX_[A-Z_]*_DB_PASSWORD|DATABASE_URL)$'
      ;;
    worker)
      prohibidos='^(POSTGRES_PASSWORD|APEX_[A-Z_]*_DB_PASSWORD|RCLONE_.*|BACKUP_SIGN_KEY[A-Z_]*|BACKUP_AGE_.*|BACKUP_VERIFY_.*)$'  # S5-B13: la PUBKEY es de worker
      ;;
    *)
      prohibidos='^(POSTGRES_PASSWORD|APEX_[A-Z_]*_DB_PASSWORD|RCLONE_.*|BACKUP_SIGN_.*|BACKUP_AGE_.*|BACKUP_VERIFY_.*)$'
      ;;
  esac
  encontrados="$(printf '%s\n' "$nombres" | grep -E "$prohibidos" || true)"
  if [ -n "$encontrados" ]; then
    falla "$svc recibe variables que no le tocan: $(printf '%s' "$encontrados" | tr '\n' ' ')"
  else
    ok "$svc: sin variables de operación ajenas (solo nombres comparados)"
  fi
  # Por valor: la contraseña del propietario no aparece en ningún servicio que no sea suyo.
  for clave in POSTGRES_PASSWORD APEX_API_DB_PASSWORD APEX_WORKER_DB_PASSWORD APEX_BACKUP_DB_PASSWORD APEX_OWNER_DB_PASSWORD; do
    secreto="$(valor_de "$clave")"
    [ -n "$secreto" ] || continue
    propio=0
    case "$svc:$clave" in
      api:APEX_API_DB_PASSWORD | worker:APEX_WORKER_DB_PASSWORD | backup:APEX_BACKUP_DB_PASSWORD) propio=1 ;;
    esac
    if [ "$propio" = "0" ] && printf '%s\n' "$entorno" | grep -qF -- "$secreto"; then
      falla "$svc contiene (por valor) la contraseña de $clave"
    fi
  done
  # api y worker: su DATABASE_URL usa su rol, no al propietario.
  if [ "$svc" = "api" ] || [ "$svc" = "worker" ]; then
    rol="apex_$svc"
    if printf '%s\n' "$entorno" | grep -q "^DATABASE_URL=postgresql+asyncpg://$rol:"; then
      ok "$svc: DATABASE_URL usa $rol"
    else
      falla "$svc: DATABASE_URL no usa $rol"
    fi
  fi
done


# S5-W0-3 (L-9, S5-D44): reparto estático de los secretos de los canales y del token de OpenBao.
# Se lee del `config` renderizado de Compose (todos los perfiles), así que cubre también los
# servicios de un solo uso (`migrate`, `dbsetup`) y `tools`, que no se pueden inspeccionar en vivo.
#   SMTP_*, TELEGRAM_*  : solo `api` y `worker` (con SMTP_PASSWORD y TELEGRAM_BOT_TOKEN presentes);
#   OPENBAO_TOKEN_FILE  : solo `api`, `worker` y `tools`;
#   web, db, backup, migrate, dbsetup: ninguna de ellas. Solo se imprimen NOMBRES.
SERVICIOS_ESTATICOS="${SERVICIOS_ESTATICOS:-api worker tools web db backup migrate dbsetup}"

nombres_de_config() { # servicio -> NOMBRES de su bloque `environment` en `compose config`
  printf '%s\n' "$config_render" | awk -v svc="$1" '
    /^  [A-Za-z0-9_-]+:$/ { actual = $1; sub(":", "", actual); en_env = 0; next }
    actual == svc && /^    environment:/ { en_env = 1; next }
    actual == svc && en_env && /^      [A-Za-z0-9_]+:/ { k = $1; sub(":", "", k); print k; next }
    /^    [a-z_]+:/ { en_env = 0 }
  '
}

if config_render="$($DC --profile '*' config 2> /dev/null)" && [ -n "$config_render" ]; then
  for svc in $SERVICIOS_ESTATICOS; do
    nombres="$(nombres_de_config "$svc")"
    case "$svc" in
      api | worker)
        for requerida in SMTP_PASSWORD TELEGRAM_BOT_TOKEN; do
          if printf '%s\n' "$nombres" | grep -qx "$requerida"; then
            ok "$svc: recibe $requerida"
          else
            falla "$svc: no recibe $requerida (S5-D44)"
          fi
        done
        ;;
      *)
        # `tools` lee `.env` por env_file (SMTP_HOST, TELEGRAM_CHAT_ID... no son secretos, S5-D44):
        # solo se le prohíben los dos secretos, que viven en .env.ops (desviación 3 del Verde).
        patron_ajeno='^(SMTP_.*|TELEGRAM_.*)$'
        [ "$svc" = "tools" ] && patron_ajeno='^(SMTP_PASSWORD|TELEGRAM_BOT_TOKEN)$'
        ajenas="$(printf '%s\n' "$nombres" | grep -E "$patron_ajeno" || true)"
        if [ -n "$ajenas" ]; then
          falla "$svc recibe secretos de canales que no le tocan: $(printf '%s' "$ajenas" | tr '\n' ' ')"
        else
          ok "$svc: sin SMTP_* ni TELEGRAM_*"
        fi
        ;;
    esac
    case "$svc" in
      api | worker | tools)
        if printf '%s\n' "$nombres" | grep -qx 'OPENBAO_TOKEN_FILE'; then
          ok "$svc: recibe OPENBAO_TOKEN_FILE"
        else
          falla "$svc: no recibe OPENBAO_TOKEN_FILE (S5-D44)"
        fi
        ;;
      *)
        if printf '%s\n' "$nombres" | grep -qE '^OPENBAO_.*$'; then
          falla "$svc recibe variables de OpenBao que no le tocan"
        else
          ok "$svc: sin variables de OpenBao"
        fi
        ;;
    esac
  done
else
  falla "no se pudo renderizar 'compose config' para el reparto estático (L-9)"
fi

echo "test_env_isolation: $fallas fallas"
[ "$fallas" -eq 0 ]
