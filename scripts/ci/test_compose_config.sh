#!/usr/bin/env bash
# test_compose_config.sh
#
# Verifica la configuración de Compose (US-005, T3) con `docker compose config`:
# db sin puertos en producción, keys en solo lectura en api y worker, misma imagen
# para api, worker y tools, volúmenes declarados, db_test solo en desarrollo y sin
# volúmenes persistentes. Usa el Python del entorno del api para leer el JSON.
# `config` omite los servicios con perfil y los volúmenes sin uso: por eso se piden
# los perfiles y `backups` se busca en el archivo.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
[ -f .env ] || cp .env.example .env
PROD="$(docker compose --env-file .env --profile worker --profile tools -f infra/compose.yml config --format json)"
DEV="$(docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml config --format json)"
COMPOSE_YML="$(cat infra/compose.yml)"

PROD="$PROD" DEV="$DEV" COMPOSE_YML="$COMPOSE_YML" uv run --directory api --quiet python - <<'EOF'
import json
import os
import sys

prod_doc = json.loads(os.environ["PROD"])
prod = prod_doc["services"]
dev = json.loads(os.environ["DEV"])["services"]
texto = os.environ["COMPOSE_YML"]
fallas = []


def check(cond, msg):
    print(("  ok   " if cond else "  FALLA ") + msg)
    if not cond:
        fallas.append(msg)


check("ports" not in prod["db"], "db no publica puertos en produccion")
for svc in ("api", "worker"):
    keys = [v for v in prod[svc].get("volumes", []) if v.get("target") == "/run/apex/keys"]
    check(bool(keys) and keys[0].get("read_only") is True, f"{svc} monta keys en solo lectura")
tools = [v for v in prod["tools"].get("volumes", []) if v.get("target") == "/run/apex/keys"]
check(bool(tools) and not tools[0].get("read_only"), "tools monta keys con escritura")
check(prod["api"]["image"] == prod["worker"]["image"] == prod["tools"]["image"], "api, worker y tools usan la misma imagen")
check("worker" in prod["worker"].get("profiles", []), "worker queda tras un perfil hasta US-113")
check("db_test" not in prod, "db_test no existe en compose.yml")
check({"pgdata", "uploads", "keys"} <= set(prod_doc.get("volumes", {})), "volumenes pgdata, uploads y keys en uso")
check(all(f"\n  {v}:" in texto for v in ("pgdata", "uploads", "keys", "backups")), "volumenes pgdata, uploads, keys y backups declarados")
check("db_test" in dev, "db_test existe en desarrollo")
check(not [v for v in dev["db_test"].get("volumes", []) if v.get("type") == "volume"], "db_test sin volumenes persistentes")
check(any(str(p.get("target")) == "5432" for p in dev["db_test"].get("ports", [])), "db_test publica su puerto en desarrollo")
check(any(v.get("target") == "/app/migrations" for v in dev["api"].get("volumes", [])), "api en desarrollo monta migrations/ (B-3)")
check("POSTGRES_PASSWORD" not in texto, "compose.yml no lleva secretos en linea")
print(f"test_compose_config: {len(fallas)} fallas")
sys.exit(1 if fallas else 0)
EOF
