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

## Volumen `keys`: `custody/` y `jwt/` (S6-D58)

El volumen `keys` tiene dos subcarpetas: `custody/` (`kek.bin`, `sign-ed25519.key`) y `jwt/` (el par JWT). `api` y `tools` montan el volumen entero; `worker` monta solo `custody/` (`volume.subpath: custody`, en `/run/apex/keys/custody`) y con `compose.openbao.yml` no monta nada. Esto exige Docker Engine 26 (API 1.45) y Compose 2.26 (S6-D78). Un volumen plano se migra con `tools init-keys --migrate-layout` (lo hace `deploy.sh` antes de `up -d`; `docs/RUNBOOK.md` §12). `web` limita su tmpfs `/var/cache/nginx` a 64 MB (Nginx guarda ahí los cuerpos de hasta 6 MB de la subida de adjuntos) y la subida tiene su propia zona `apex_upload` (30 por minuto por IP, `snippets/upload-zone.conf`).
