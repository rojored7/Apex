"""Variables del `.env` que no son del api (`NON_API_ENV_VARS`).

Extraído de `config.py` (S8-W0-3) para no pasar de 800 líneas; `config.py` lo reexporta. Solo
datos: nombres de variables que lee Compose, el CLI o pytest, nunca `Settings`.
"""

from __future__ import annotations

# Variables del .env que no son del api: las lee Compose (POSTGRES_*, puertos),
# pytest en el host (TEST_DATABASE_URL) o el CLI (admin inicial, US-041: vive en `.env.seed`
# y solo lo lee `SeedSettings` en el servicio tools; M-8).
NON_API_ENV_VARS: frozenset[str] = frozenset(
    {
        "ADMIN_EMAIL",
        "ADMIN_INITIAL_PASSWORD",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
        "TEST_DATABASE_URL",
        "WEB_PORT",
        "API_PORT",
        "DB_PORT",
        "DB_TEST_PORT",
        # S4B-W0-1 (S4B-D79): variables de operación de .env.ops.example; las lee Compose o el
        # servicio backup, nunca Settings. Los nombres son exactamente los de ese archivo.
        "BACKUP_KEEP_DAYS",
        "BACKUP_CRON",
        "BACKUP_AGE_RECIPIENT",
        "BACKUP_AGE_VERIFY_RECIPIENT",
        "BACKUP_RCLONE_REMOTE",
        "RCLONE_CONFIG_APEX_TYPE",
        "RCLONE_CONFIG_APEX_PROVIDER",
        "RCLONE_CONFIG_APEX_ENDPOINT",
        "RCLONE_CONFIG_APEX_ACCESS_KEY_ID",
        "RCLONE_CONFIG_APEX_SECRET_ACCESS_KEY",
        "BACKUP_SIGN_KEY_FILE",
        "BACKUP_VERIFY_IDENTITY_FILE",
        "DEPLOY_HEALTH_TIMEOUT",
        "APEX_API_DB_PASSWORD",
        "APEX_WORKER_DB_PASSWORD",
        "APEX_BACKUP_DB_PASSWORD",
        # S5-W0-4 (S5-D89, D141): contraseña de apex_owner y las de migrate/tools; solo Compose.
        "APEX_OWNER_DB_PASSWORD",
        "MIGRATE_DB_PASSWORD",
        "TOOLS_DB_PASSWORD",
        "APEX_SUBNET",
        "APEX_IP_RANGE",
        "APEX_WEB_IP",
        # S5-W0-2: red de custodia de OpenBao (S5-D77) y rol de migraciones (S5-D96); solo Compose.
        "APEX_CUSTODY_SUBNET",
        "MIGRATE_DB_USER",
        # S5-W0-3 (S5-D96): rol del servicio `tools`; solo Compose.
        "TOOLS_DB_USER",
        # S6-W0-5 (S6-D65, D77 final): variables de Caddy y del perfil `tls`; solo Compose y el
        # servicio `caddy`. El api no lee el emisor ACME (`APEX_TLS_ISSUER`).
        "APEX_CADDY_IP",
        "APEX_TLS_ISSUER",
        "APEX_ACME_EMAIL",
        "APEX_ACME_CA",
        "APEX_HSTS_MAX_AGE",
        "TLS_PORT",
        # S6-W0-4 (S6-D82): snippet real-ip.conf que monta web; solo Compose y deploy.sh.
        "APEX_REAL_IP_CONF",
    }
)
