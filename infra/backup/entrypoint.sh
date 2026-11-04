#!/bin/bash
# Entrypoint del servicio backup (S4B-W0-1, S4B-D14). Sin BACKUP_AGE_RECIPIENT queda inerte
# pero visible: avisa en el log y arranca supercronic con una crontab vacía (el healthcheck
# sigue en verde y no hay respaldos sin cifrar).
set -euo pipefail

# Con argumentos (docker compose run --rm backup /opt/backup/run.sh --prefix pre-deploy, S4B-B4) ejecuta
# ese script en lugar del cron. Solo los dos scripts de la imagen; cualquier otra cosa se rechaza.
if [ "$#" -gt 0 ]; then
  case "$1" in
    /opt/backup/run.sh | /opt/backup/restore.sh) exec "$@" ;;
    *) echo "entrypoint: ERROR solo se admite /opt/backup/run.sh o /opt/backup/restore.sh" >&2; exit 2 ;;
  esac
fi

CRON="${BACKUP_CRON:-0 2 * * *}"
if ! [[ "$CRON" =~ ^[0-9*/,-]+\ [0-9*/,-]+\ [0-9*/,-]+\ [0-9*/,-]+\ [0-9*/,-]+$ ]]; then
  echo "entrypoint: ERROR BACKUP_CRON inválido (cinco campos cron)" >&2
  exit 2
fi
if [ -z "${BACKUP_AGE_RECIPIENT:-}" ]; then
  echo "ERROR backup deshabilitado: falta BACKUP_AGE_RECIPIENT"
  : > /tmp/crontab
else
  printf '%s /opt/backup/run.sh\n' "$CRON" > /tmp/crontab
  echo "entrypoint: respaldo programado ($CRON)"
fi
exec supercronic -quiet /tmp/crontab
