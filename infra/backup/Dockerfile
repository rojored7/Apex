# Imagen del servicio backup de APEX (S4B-W0-1, S4B-D14, D57, D73, D75). pg_dump 16, age,
# minisign, rclone y supercronic sobre Alpine; usuario apex (UID 10001); inerte sin
# destinatario age. Nunca contiene identidades, llaves de firma ni rclone.conf: llegan por
# archivos montados (compose.yml, compose.verify.yml) y por variables de entorno.

# postgres:16-alpine por digest (2026-10-29, S3-D62); renovar (docs/RUNBOOK.md §7):
# docker buildx imagetools inspect postgres:16-alpine --format '{{json .Manifest.Digest}}'
FROM postgres:16-alpine@sha256:0cefaabd882e42bcb2a2f3dc56d3ce4770560ba62fd7f197f1a2e008fd5731ab
# Versiones verificadas en Alpine 3.24.3 el 2026-10-29: apk policy age minisign rclone supercronic
RUN apk add --no-cache age=1.3.2-r1 rclone=1.74.1-r3 supercronic=0.2.49-r1 minisign=0.12-r2 tzdata \
    && addgroup -g 10001 apex \
    && adduser -D -u 10001 -G apex apex \
    && mkdir -p /data/backups /opt/backup /run/apex/backup \
    && chown -R apex:apex /data /run/apex
# restore.sh llega en S4B-B3a: hasta entonces el COPY lista solo lo que existe.
COPY --chown=apex:apex --chmod=0555 run.sh lib.sh entrypoint.sh healthcheck.sh /opt/backup/
COPY --chown=apex:apex --chmod=0444 manifest.schema.json /opt/backup/
ENV TZ=America/Bogota
USER apex
WORKDIR /opt/backup
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s CMD ["/opt/backup/healthcheck.sh"]
ENTRYPOINT ["/opt/backup/entrypoint.sh"]
