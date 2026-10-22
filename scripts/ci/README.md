# scripts/ci

Scripts que corren la CI (`.github/workflows/ci.yml`), `run-gates.sh` y el cierre de sprint. Todos en Bash (`#!/usr/bin/env bash`, `set -euo pipefail`), revisados con `bash -n`, y calculan la raíz con `git rev-parse --show-toplevel`. Los que llevan Docker usan contenedores desechables y no tocan el stack levantado, salvo `compose-smoke.sh`.

## Scripts y archivos

1. `check-image-secrets.sh <imagen>`: exporta el sistema de archivos de la imagen del api y falla si hay un `.env` (salvo `.env.example`), una llave privada PEM o archivos `.pem`, `.key` o `.kek` bajo `app/`; incluye `gitleaks dir` (US-039). Job `images`.
2. `check-key-files.sh [archivos...]`: falla si un archivo versionado (o pasado por argumento, en pre-commit) es material de llave por su nombre, o un `.env*` distinto de `.env.example` y `.env.seed.example` (US-039, S2-W0-1). Job `secrets-scan` y pre-commit.
3. `check-licenses-api.sh [python]`: lista blanca estricta de licencias del runtime del api (`uv sync --frozen --no-dev` en `api/.venv-runtime`); una licencia desconocida también falla (US-004). Job `api`.
4. `compose-smoke.sh`: levanta db, db_test, api y web con build, espera `healthy`, corre `seed` con un `.env.seed` efímero, compara `TRUSTED_PROXIES` con la IP real de `web` y llama a `web-smoke.sh` y a `scripts/smoke/headers.sh`; baja el stack con sus volúmenes salvo `SMOKE_KEEP=1` (US-005, US-006). Job `images`.
5. `notice.sh`: regenera `NOTICE` con las dependencias directas del api y del front y las licencias fijas (fuentes OFL-1.1, herramientas MPL-2.0); la CI compara con `git diff --exit-code NOTICE` (US-004). Job `api`.
6. `test_api_image.sh [imagen]`: prueba la imagen del api: usuario no root (UID 10001), tzdata, `alembic heads`, sin `.env` ni llaves y sin herramientas de desarrollo (US-005). Job `images`.
7. `test_check_key_files.sh`: casos de `check-key-files.sh` (bloquea `.env`, `.env.seed` y cualquier `.env.*`; permite los dos ejemplos). Job `secrets-scan` y `run-gates.sh`.
8. `test_compose_config.sh`: contrato de `docker compose config` en producción, desarrollo y el perfil E2E (`infra/compose.e2e.yml`): db sin puertos en producción, llaves en solo lectura, misma imagen para api, worker y tools, red con subred fija y `web` en IP fija, `.env.seed` solo en `tools`, zona E2E del borde solo con `compose.e2e.yml`. Copia `.env.example` a `.env` si falta y lee el JSON con el Python del api (`uv`). Job `images` y `run-gates.sh`.
9. `test_licenses.sh`: pruebas de control de `check-licenses-api.sh` (un paquete LGPL y uno sin metadatos deben fallar; el runtime real debe pasar). Job `api`.
10. `test_nginx_conf.sh`: `nginx -t` en la imagen oficial con `default.conf` y `snippets/`, presencia de las directivas del contrato (cuerpo de 5 MB, cabeceras y CSP con nonce, `limit_req` de 60r/m en `/api/v1/auth/` y 429 en envelope, log sin query strings) y una prueba funcional con Nginx real (S2-W0-1, V4). Job `images` y `run-gates.sh`.
11. `web-smoke.sh`: smoke de Nginx con el stack levantado (SPA, fallback, `/api/v1/health` y cabeceras); lo invoca `compose-smoke.sh`.
12. `licenses-exceptions.txt`: dependencias MPL-2.0 aceptadas sin modificar, una por línea con su justificación; la leen `check-licenses-api.sh` y `notice.sh`.
13. `fixtures/`: paquetes de control de `test_licenses.sh` (`sin-licencia/`, sin metadatos de licencia).

Fuera de esta carpeta, `scripts/smoke/headers.sh` revisa las cabeceras y el log de Nginx contra el stack levantado. Su ráfaga agota el `limit_req` de la IP del host durante unos 60 segundos (ver `docs/RUNBOOK.md`, sección 1).

## Cómo correrlos en local

Desde cualquier carpeta del repositorio, con Docker y `uv` disponibles:

```
bash scripts/ci/test_check_key_files.sh
bash scripts/ci/test_nginx_conf.sh
bash scripts/ci/test_compose_config.sh
bash scripts/ci/compose-smoke.sh            # SMOKE_KEEP=1 deja el stack arriba
bash scripts/ci/test_api_image.sh           # sin argumento construye apex-api:ci
```
