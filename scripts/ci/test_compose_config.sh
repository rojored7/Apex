#!/usr/bin/env bash
# test_compose_config.sh
#
# Verifica la configuración de Compose (US-005, T3) con `docker compose config`:
# db sin puertos en producción, keys en solo lectura en api y worker, misma imagen
# para api, worker y tools, volúmenes declarados, db_test solo en desarrollo y sin
# volúmenes persistentes. Usa el Python del entorno del api para leer el JSON.
# `config` omite los servicios con perfil y los volúmenes sin uso: por eso se piden
# los perfiles y `backups` se busca en el archivo.
# S2-W0-1 (M-1, M-8): red por defecto con subred fija, `web` con IP fija fuera del rango
# dinámico, TRUSTED_PROXIES de .env.example igual a esa IP /32, `.env.seed` solo en el
# env_file de `tools` (required: false, Compose >= 2.24) y ADMIN_* fuera de api, worker y db.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
[ -f .env ] || cp .env.example .env
PROD="$(docker compose --env-file .env --profile worker --profile tools -f infra/compose.yml config --format json)"
DEV="$(docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml config --format json)"
COMPOSE_YML="$(cat infra/compose.yml)"
# Sin resolver los env_file: conserva la lista de archivos y su `required`.
CRUDO="$(docker compose --env-file .env --profile worker --profile tools -f infra/compose.yml config --no-env-resolution --format json)"
COMPOSE_VERSION="$(docker compose version --short 2>/dev/null | tr -d '\r' || true)"
IGNORA_SEED="$(git check-ignore -q .env.seed && echo si || echo no)"
IGNORA_SEED_EJEMPLO="$(git check-ignore -q .env.seed.example && echo si || echo no)"

PROD="$PROD" DEV="$DEV" COMPOSE_YML="$COMPOSE_YML" CRUDO="$CRUDO" COMPOSE_VERSION="$COMPOSE_VERSION" IGNORA_SEED="$IGNORA_SEED" IGNORA_SEED_EJEMPLO="$IGNORA_SEED_EJEMPLO" RAIZ="$ROOT" uv run --directory api --quiet python - <<'EOF'
import ipaddress
import json
import os
import sys
from pathlib import Path

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

# --- S2-W0-1 · M-1: subred fija e IP fija del proxy ---------------------------------
red = prod_doc.get("networks", {}).get("default", {})
ipam = (red.get("ipam") or {}).get("config") or [{}]
subred_txt = ipam[0].get("subnet", "")
rango_txt = ipam[0].get("ip_range", "")
check(subred_txt in ("172.30.0.0/24", "172.31.0.0/24"), f"red default con subred fija 172.30.0.0/24 o 172.31.0.0/24 ({subred_txt or 'sin subred'})")
web_redes = prod["web"].get("networks") or {}
web_ip_txt = ((web_redes.get("default") or {}).get("ipv4_address")) or ""
check(bool(web_ip_txt), f"web con ipv4_address fija ({web_ip_txt or 'sin IP'})")
if subred_txt and web_ip_txt and rango_txt:
    subred = ipaddress.ip_network(subred_txt)
    web_ip = ipaddress.ip_address(web_ip_txt)
    rango = ipaddress.ip_network(rango_txt)
    check(web_ip in subred, "la IP de web cae dentro de la subred")
    check(rango.subnet_of(subred) and web_ip not in rango, "ip_range dinámico dentro de la subred y sin la IP de web")
else:
    check(False, "subred, ip_range e IP de web definidos")

ejemplo = {}
for linea in (Path(os.environ["RAIZ"]) / ".env.example").read_text(encoding="utf-8").splitlines():
    linea = linea.strip()
    if linea and not linea.startswith("#") and "=" in linea:
        clave, valor = linea.split("=", 1)
        ejemplo[clave.strip()] = valor.strip()
confianza = [p.strip() for p in ejemplo.get("TRUSTED_PROXIES", "").split(",") if p.strip()]
check(
    bool(web_ip_txt) and confianza == [f"{web_ip_txt}/32"],
    f"TRUSTED_PROXIES de .env.example = IP de web /32 ({','.join(confianza) or 'vacio'})",
)

# --- S2-W0-1 · M-8: .env.seed solo para tools ----------------------------------------
crudo = json.loads(os.environ["CRUDO"])["services"]


def archivos(svc):
    return [(Path(e["path"]).name, e.get("required", True)) for e in crudo[svc].get("env_file", [])]


version = os.environ.get("COMPOSE_VERSION", "")
partes = [int(x) for x in version.split(".")[:2] if x.isdigit()]
check(len(partes) == 2 and tuple(partes) >= (2, 24), f"docker compose >= 2.24 para env_file required: false ({version})")
check(archivos("tools") == [(".env", True), (".env.seed", False)], f"tools: env_file [.env, .env.seed required: false] ({archivos('tools')})")
for svc in ("api", "worker", "db"):
    check(all(nombre != ".env.seed" for nombre, _ in archivos(svc)), f"{svc} no lee .env.seed")
    con_valor = [k for k, v in (prod[svc].get("environment") or {}).items() if k.startswith("ADMIN_") and v]
    check(not con_valor, f"{svc} no recibe ADMIN_* con valor ({con_valor or 'ninguna'})")
check(all(k not in ejemplo for k in ("ADMIN_EMAIL", "ADMIN_INITIAL_PASSWORD")), ".env.example no trae ADMIN_* (van en .env.seed; M-8)")
seed_ejemplo = Path(os.environ["RAIZ"]) / ".env.seed.example"
claves_seed = {}
if seed_ejemplo.is_file():
    for linea in seed_ejemplo.read_text(encoding="utf-8").splitlines():
        if linea.strip() and not linea.strip().startswith("#") and "=" in linea:
            k, v = linea.split("=", 1)
            claves_seed[k.strip()] = v.strip()
check(claves_seed == {"ADMIN_EMAIL": "", "ADMIN_INITIAL_PASSWORD": ""}, f".env.seed.example con ADMIN_EMAIL y ADMIN_INITIAL_PASSWORD vacias (L-9) ({sorted(claves_seed)})")
check(os.environ["IGNORA_SEED"] == "si", "git ignora .env.seed")
check(os.environ["IGNORA_SEED_EJEMPLO"] == "no", "git versiona .env.seed.example (!.env.seed.example)")
print(f"test_compose_config: {len(fallas)} fallas")
sys.exit(1 if fallas else 0)
EOF
