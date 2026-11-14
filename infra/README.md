# infra

Compose (`compose.yml`, `compose.dev.yml`, `compose.openbao.yml`), Nginx, backup y OpenBao (v0.2). Se completa en US-005 y US-006.

## Orden de arranque y archivos de entorno (S4B-W0-3)

Dos archivos de entorno (S4B-D79): `.env` (lo que lee `Settings`, sin contraseñas) y `.env.ops` (propietario, contraseñas de rol, respaldo, firma, puertos y red). Los dos con modo 600 y fuera de git; se copian de `.env.example` y `.env.ops.example`. En producción:

```
docker compose --env-file .env --env-file .env.ops -f infra/compose.yml up -d --build
```

Cadena: `db` -> `migrate` (propietario, `alembic upgrade head`) -> `dbsetup` (`infra/db/apply.sh`: roles y permisos) -> `api` (rol `apex_api`, no migra) -> `worker` (`apex_worker`) y `web`; `backup` (`apex_backup`) tras `dbsetup`. En desarrollo (`compose.dev.yml`) `migrate` y `dbsetup` solo existen con `--profile prod-init` y api, worker, tools y backup usan al propietario. Detalle, rollback de roles (`infra/db/revoke.sql`) y ensayo en la misma máquina: `docs/RUNBOOK.md` §12.

## Redes (S5-D10, S5-D77)

Hay dos redes de Compose:

- `default` (`${APEX_SUBNET}`, 172.30.0.0/24): `web` (IP fija), `api`, `worker`, `tools`, `db` y `backup`. Es la red del tráfico normal.
- `custody` (`${APEX_CUSTODY_SUBNET}`, 172.30.1.0/24; `internal: true`): `openbao`, `openbao-bootstrap`, `api`, `worker` y `tools`. Sin salida a internet ni al anfitrión; nadie publica puertos desde ella. `web`, `db` y `backup` no están (el respaldo entra en B13, para el snapshot).

`api` y `worker` esperan a que `openbao` esté `healthy` (sellado cuenta como sano). El perfil `bootstrap` (`openbao-bootstrap`) y los archivos `infra/openbao/` instalan y operan OpenBao; `compose.openbao.yml` se apila cuando `CRYPTO_PROVIDER=openbao` y quita `keys` de `api` y `worker`. Operación: `docs/operacion/openbao.md`.

## Caddy y el perfil `tls` (S6-D64, D82)

`caddy` (Caddy 2.11.3 por digest) solo existe con `--profile tls` y vive en la red `default` con IP fija `${APEX_CADDY_IP:-172.30.0.11}` (fuera del `ip_range`, como `web`). `compose.yml` lo declara sin puertos; `compose.tls.yml` publica `${WEB_PORT:-80}:80` y `${TLS_PORT:-443}:443` y deja a `web` sin puertos (`ports: !override []`); `compose.dev.yml` lo publica en `127.0.0.1:8443` con `APEX_DOMAIN=apex.localhost:8443` y la CA interna. Corre `read_only`, con `cap_drop: [ALL]` y solo `NET_BIND_SERVICE`, sin puerto 2019, y recibe cinco variables (`APEX_DOMAIN`, `APEX_TLS_ISSUER`, `APEX_ACME_EMAIL`, `APEX_ACME_CA`, `APEX_HSTS_MAX_AGE`). `caddy_data` (certificados y cuenta ACME) y `caddy_config` son volúmenes con nombre. El `Caddyfile` y su prueba (`infra/caddy/tests/test_caddyfile.sh`) están en `infra/caddy/`.

`web` monta `${APEX_REAL_IP_CONF:-./nginx/snippets/real-ip.conf}` sobre `/etc/nginx/snippets/real-ip.conf` (solo lectura): por omisión el snippet versionado, que es `real-ip.conf.in` con la IP de fábrica; `deploy.sh` apunta la variable a un render fuera del árbol si `APEX_CADDY_IP` cambia. `cap_drop: [ALL]` rige para los once servicios (`db` con cinco capacidades de Postgres). Guía: `docs/operacion/tls.md`.

## Volumen `keys`: `custody/`, `sign/` y `jwt/` (S6-D58, S7-D4)

El volumen `keys` tiene tres subcarpetas: `custody/` (`kek.bin`), `sign/` (`sign-ed25519.key`) y `jwt/` (el par JWT). `api` monta solo `custody/` y `jwt/` (`volume.subpath`, solo lectura; nunca `sign/`, por eso no puede firmar ni ve la semilla); `worker` monta `custody/` y `sign/`; `tools` el volumen entero. Con `compose.openbao.yml` el api sigue con `custody/` y `jwt/` y el worker no monta nada. `compose.dev.yml` no redefine estos montajes (desarrollo muestra la misma regresión que producción). Esto exige Docker Engine 26 (API 1.45) y Compose 2.26 (S6-D78). Un volumen plano se migra con `tools init-keys --migrate-layout` (lo hace `deploy.sh` antes de `up -d`; `docs/RUNBOOK.md` §12). `web` limita su tmpfs `/var/cache/nginx` a 64 MB (Nginx guarda ahí los cuerpos de hasta 6 MB de la subida de adjuntos) y la subida tiene su propia zona `apex_upload` (30 por minuto por IP, `snippets/upload-zone.conf`).
