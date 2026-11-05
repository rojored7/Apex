# Imagen del servicio backup de APEX (S4B-W0-1, S4B-D14, D57, D73, D75). pg_dump 16, age,
# minisign, rclone y supercronic sobre Alpine; usuario apex (UID 10001); inerte sin
# destinatario age. curl (S5-B13) pide la instantanea raft de OpenBao con `-K` (token fuera del
# argv). Nunca contiene identidades, llaves de firma ni rclone.conf: llegan por
# archivos montados (compose.yml, compose.verify.yml) y por variables de entorno.

# postgres:16-alpine por digest (2026-10-29, S3-D62); renovar (docs/RUNBOOK.md §7):
# docker buildx imagetools inspect postgres:16-alpine --format '{{json .Manifest.Digest}}'
FROM postgres:16-alpine@sha256:0cefaabd882e42bcb2a2f3dc56d3ce4770560ba62fd7f197f1a2e008fd5731ab
# Versiones verificadas en Alpine 3.24.3 el 2026-11-04 (rclone renovado; test_backup_apk_pins.sh lo vigila): apk policy age minisign rclone supercronic curl
RUN apk add --no-cache age=1.3.2-r1 rclone=1.75.2-r0 supercronic=0.2.49-r1 minisign=0.12-r2 curl=8.23.0-r0 tzdata \
    && addgroup -g 10001 apex \
    && adduser -D -u 10001 -G apex apex \
    && mkdir -p /data/backups /opt/backup /run/apex/backup \
    && chown -R apex:apex /data /run/apex
# restore.sh (S4B-B3a) se corre a mano con `run --rm --entrypoint`, nunca por cron.
COPY --chown=apex:apex --chmod=0555 run.sh restore.sh lib.sh entrypoint.sh healthcheck.sh /opt/backup/
COPY --chown=apex:apex --chmod=0444 manifest.schema.json /opt/backup/
ENV TZ=America/Bogota
# Revision OCI de la imagen (V12): GIT_SHA lo pasa el build, igual que api y web.
ARG GIT_SHA=dev
LABEL org.opencontainers.image.revision=$GIT_SHA
USER apex
WORKDIR /opt/backup
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s CMD ["/opt/backup/healthcheck.sh"]
ENTRYPOINT ["/opt/backup/entrypoint.sh"]
