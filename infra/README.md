# infra

Compose (`compose.yml`, `compose.dev.yml`), Nginx, backup y OpenBao (v0.2). Se completa en US-005 y US-006.

## Orden de arranque y archivos de entorno (S4B-W0-3)

Dos archivos de entorno (S4B-D79): `.env` (lo que lee `Settings`, sin contraseñas) y `.env.ops` (propietario, contraseñas de rol, respaldo, firma, puertos y red). Los dos con modo 600 y fuera de git; se copian de `.env.example` y `.env.ops.example`. En producción:

```
docker compose --env-file .env --env-file .env.ops -f infra/compose.yml up -d --build
```

Cadena: `db` -> `migrate` (propietario, `alembic upgrade head`) -> `dbsetup` (`infra/db/apply.sh`: roles y permisos) -> `api` (rol `apex_api`, no migra) -> `worker` (`apex_worker`) y `web`; `backup` (`apex_backup`) tras `dbsetup`. En desarrollo (`compose.dev.yml`) `migrate` y `dbsetup` solo existen con `--profile prod-init` y api, worker, tools y backup usan al propietario. Detalle, rollback de roles (`infra/db/revoke.sql`) y ensayo en la misma máquina: `docs/RUNBOOK.md` §12.
