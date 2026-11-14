#!/usr/bin/env bash
# test_compose_config.sh
#
# Verifica la configuración de Compose (US-005, T3) con `docker compose config`:
# db sin puertos en producción, keys en solo lectura en api, misma imagen
# para api, worker y tools, volúmenes declarados, db_test solo en desarrollo y sin
# volúmenes persistentes. Usa el Python del entorno del api para leer el JSON.
# `config` omite los servicios con perfil y los volúmenes sin uso: por eso se piden
# los perfiles y `backups` se busca en el archivo.
# S2-W0-1 (M-1, M-8): red por defecto con subred fija, `web` con IP fija fuera del rango
# dinámico, TRUSTED_PROXIES de .env.example igual a esa IP /32, `.env.seed` solo en el
# env_file de `tools` (required: false, Compose >= 2.24) y ADMIN_* fuera de api, worker y db.
# S3-W0-1 (S3-D62): postgres:16 por el mismo digest en compose.yml y compose.dev.yml.
# S4A-W0-1 (US-113; S4A-D8, S4A-D9, S4A-D49): keys en solo lectura solo en api; worker sin
# volúmenes, read_only, tmpfs /tmp, cap_drop ALL, no-new-privileges, healthcheck por latido y
# depends_on de db y api healthy; ningún servicio de producción monta código vivo; en desarrollo
# worker y tools montan api/src y api/migrations en solo lectura.
# Rojo S6-W0-4 (S6-D64, D82; M-7, L-6): servicio caddy con perfil tls, compose.tls.yml, perfil tls en desarrollo,
# cap_drop ALL en los once servicios y el bind de real-ip.conf (bloque al final).
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
[ -f .env ] || cp .env.example .env
# S4B-W0-3 (S4B-D56): produccion se renderiza con los dos ejemplos y contraseñas CENTINELA distintas
# por rol (la prueba busca fugas por nombre y por valor). El .env real solo lo lee `env_file`.
TMPD="$(mktemp -d)"
trap 'rm -rf "$TMPD"' EXIT
cat > "$TMPD/centinelas.env" <<'SENT'
POSTGRES_PASSWORD=centinela-propietario-0123456789
APEX_API_DB_PASSWORD=centinela-api-0123456789abcd
APEX_WORKER_DB_PASSWORD=centinela-worker-0123456789ab
APEX_BACKUP_DB_PASSWORD=centinela-backup-0123456789a
APEX_OWNER_DB_PASSWORD=centinela-owner-0123456789abc
RCLONE_CONFIG_APEX_SECRET_ACCESS_KEY=centinela-rclone-secreto
SENT
ENVS=(--env-file .env.example --env-file .env.ops.example --env-file "$TMPD/centinelas.env")
PROD="$(docker compose "${ENVS[@]}" --profile worker --profile tools -f infra/compose.yml config --format json)"
DEV="$(docker compose "${ENVS[@]}" -f infra/compose.yml -f infra/compose.dev.yml config --format json)"
# E3 / E9: migrate y dbsetup solo existen en desarrollo con el perfil prod-init.
DEV_INIT="$(docker compose "${ENVS[@]}" --profile prod-init -f infra/compose.yml -f infra/compose.dev.yml config --format json 2>/dev/null || echo "{}")"
if docker compose "${ENVS[@]}" -f infra/compose.yml -f infra/compose.dev.yml config --quiet > /dev/null 2>&1; then DEV_QUIET=0; else DEV_QUIET=1; fi
# S4B-D13: sin variables de red (solo .env.example) y con las del ensayo.
PROD_SIN_OPS="$(docker compose --env-file .env.example -f infra/compose.yml config --format json 2>/dev/null || echo "{}")"
PROD_RED="$(APEX_SUBNET=172.31.0.0/24 APEX_IP_RANGE=172.31.0.128/25 APEX_WEB_IP=172.31.0.10 docker compose "${ENVS[@]}" -f infra/compose.yml config --format json 2>/dev/null || echo "{}")"
RUNBOOK_NO_DEPS="$(grep -c 'run --rm --no-deps dbsetup' docs/RUNBOOK.md || true)"
# S4A-W0-1: worker y tools en desarrollo (binds de codigo en solo lectura); tools solo sale con su
# perfil. Desde S4A-W0-2 el worker no tiene perfil y `--profile worker` queda inofensivo.
DEV_PERFILES="$(docker compose "${ENVS[@]}" --profile worker --profile tools -f infra/compose.yml -f infra/compose.dev.yml config --format json)"
COMPOSE_YML="$(cat infra/compose.yml)"
# S5-W0-4 (M-12): POSTGRES_USER con un valor propio para ver en que servicios se interpola.
SU="$(POSTGRES_USER=centinela-super docker compose "${ENVS[@]}" --profile worker --profile tools -f infra/compose.yml config --format json 2>/dev/null || echo "{}")"
# V4 del Sprint 2: perfil E2E del borde (infra/compose.e2e.yml); vacio si el archivo falta.
E2E="$(docker compose "${ENVS[@]}" -f infra/compose.yml -f infra/compose.e2e.yml config --format json 2>/dev/null || echo "{}")"
# Sin resolver los env_file: conserva la lista de archivos y su `required`.
CRUDO="$(docker compose "${ENVS[@]}" --profile worker --profile tools -f infra/compose.yml config --no-env-resolution --format json)"
# S4B-W0-1: compose.verify.yml (identidad de verificacion solo en backup) con un archivo temporal.
VERIFY="$(BACKUP_VERIFY_IDENTITY_FILE="$ROOT/.env.example" docker compose "${ENVS[@]}" -f infra/compose.yml -f infra/compose.verify.yml config --format json 2>/dev/null || echo "{}")"
# S5-W0-2 (S5-D10, D11, D12, D74, D77): perfil bootstrap, overlay de OpenBao y perfil openbao en desarrollo.
BOOT="$(docker compose "${ENVS[@]}" --profile bootstrap -f infra/compose.yml config --format json 2>/dev/null || echo "{}")"
OVL="$(docker compose "${ENVS[@]}" --profile worker --profile tools -f infra/compose.yml -f infra/compose.openbao.yml config --format json 2>/dev/null || echo "{}")"
DEV_OB="$(docker compose "${ENVS[@]}" --profile openbao --profile worker --profile tools -f infra/compose.yml -f infra/compose.dev.yml config --format json 2>/dev/null || echo "{}")"
# S5-B4 (S5-D78): mailpit y telegram-fake solo en desarrollo y solo con el perfil avisos.
DEV_AV="$(docker compose "${ENVS[@]}" --profile avisos -f infra/compose.yml -f infra/compose.dev.yml config --format json 2>/dev/null || echo "{}")"
OVL_YML="$(cat infra/compose.openbao.yml 2>/dev/null || true)"
COMPOSE_VERSION="$(docker compose version --short 2>/dev/null | tr -d '\r' || true)"
IGNORA_SEED="$(git check-ignore -q .env.seed && echo si || echo no)"
IGNORA_SEED_EJEMPLO="$(git check-ignore -q .env.seed.example && echo si || echo no)"
IGNORA_OPS="$(git check-ignore -q .env.ops && echo si || echo no)"
IGNORA_OPS_EJEMPLO="$(git check-ignore -q .env.ops.example && echo si || echo no)"

# Rojo S6-W0-4 (S6-D64, D82, M-7, L-6; paso 27): caddy con perfil tls, compose.tls.yml, perfil tls en
# desarrollo, cap_drop en los once servicios y el bind de real-ip.conf. Los renders que dependen de
# archivos que aun no existen (compose.tls.yml) caen a "{}" y las aserciones fallan una por una.
TLS_PROF="$(docker compose "${ENVS[@]}" --profile tls -f infra/compose.yml config --format json 2>/dev/null || echo "{}")"
TLS_OVL="$(docker compose "${ENVS[@]}" --profile tls -f infra/compose.yml -f infra/compose.tls.yml config --format json 2>/dev/null || echo "{}")"
TLS_OVL_PUERTOS="$(WEB_PORT=8280 TLS_PORT=8443 docker compose "${ENVS[@]}" --profile tls -f infra/compose.yml -f infra/compose.tls.yml config --format json 2>/dev/null || echo "{}")"
TLS_DEV="$(WEB_PORT=8180 docker compose "${ENVS[@]}" --profile tls -f infra/compose.yml -f infra/compose.dev.yml config --format json 2>/dev/null || echo "{}")"
TODOS_PERFILES="$(docker compose "${ENVS[@]}" --profile '*' -f infra/compose.yml config --format json 2>/dev/null || echo "{}")"
REAL_IP_FUERA="$(APEX_REAL_IP_CONF=/tmp/apex-real-ip/real-ip.conf docker compose "${ENVS[@]}" -f infra/compose.yml config --format json 2>/dev/null || echo "{}")"
CADDY_IP_ENSAYO="$(APEX_SUBNET=172.31.2.0/24 APEX_IP_RANGE=172.31.2.128/25 APEX_WEB_IP=172.31.2.10 APEX_CADDY_IP=172.31.2.11 docker compose "${ENVS[@]}" --profile tls -f infra/compose.yml config --format json 2>/dev/null || echo "{}")"
OPS_EJEMPLO_TEXTO="$(cat .env.ops.example 2>/dev/null || true)"
export TLS_PROF TLS_OVL TLS_OVL_PUERTOS TLS_DEV TODOS_PERFILES REAL_IP_FUERA CADDY_IP_ENSAYO OPS_EJEMPLO_TEXTO

SU="$SU" BOOT="$BOOT" OVL="$OVL" DEV_OB="$DEV_OB" DEV_AV="$DEV_AV" OVL_YML="$OVL_YML" DEV_INIT="$DEV_INIT" DEV_QUIET="$DEV_QUIET" PROD_SIN_OPS="$PROD_SIN_OPS" PROD_RED="$PROD_RED" RUNBOOK_NO_DEPS="$RUNBOOK_NO_DEPS" VERIFY="$VERIFY" PROD="$PROD" DEV="$DEV" DEV_PERFILES="$DEV_PERFILES" E2E="$E2E" COMPOSE_YML="$COMPOSE_YML" CRUDO="$CRUDO" COMPOSE_VERSION="$COMPOSE_VERSION" IGNORA_SEED="$IGNORA_SEED" IGNORA_SEED_EJEMPLO="$IGNORA_SEED_EJEMPLO" IGNORA_OPS="$IGNORA_OPS" IGNORA_OPS_EJEMPLO="$IGNORA_OPS_EJEMPLO" RAIZ="$ROOT" uv run --directory api --quiet python - <<'EOF'
import ipaddress
import json
import os
import re
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
# S7-D4: el api monta solo las subrutas custody y jwt del volumen keys (nunca sign/ ni el volumen entero).
def keys_de(doc, svc):
    return sorted(
        ((v.get("target"), (v.get("volume") or {}).get("subpath"), v.get("read_only")) for v in doc[svc].get("volumes", []) or [] if v.get("source") == "keys"),
        key=str,
    )
check(
    keys_de(prod, "api") == [("/run/apex/keys/custody", "custody", True), ("/run/apex/keys/jwt", "jwt", True)],
    f"S7-D4: api monta keys con subpath custody y jwt, solo lectura, y sin volumen entero ({keys_de(prod, 'api')})",
)
# S5-B3 (S5-D20, H-2): el worker descifra avisos; con CRYPTO_PROVIDER=local monta keys en solo lectura
# (compose.openbao.yml lo quita). Uploads sigue sin montarse.
destinos_worker = {v.get("target") for v in prod["worker"].get("volumes", []) or []}
# S6-W0-2, S7-D4: el worker monta SOLO las subrutas custody y sign del volumen keys (nunca jwt/).
check(
    keys_de(prod, "worker") == [("/run/apex/keys/custody", "custody", True), ("/run/apex/keys/sign", "sign", True)],
    f"S7-D4: worker monta keys con subpath custody y sign, solo lectura ({keys_de(prod, 'worker')})",
)
check("/data/uploads" not in destinos_worker, "worker no monta uploads")
tools = [v for v in prod["tools"].get("volumes", []) if v.get("target") == "/run/apex/keys"]
check(bool(tools) and not tools[0].get("read_only"), "tools monta keys con escritura")
check(prod["api"]["image"] == prod["worker"]["image"] == prod["tools"]["image"], "api, worker y tools usan la misma imagen")
check("profiles" not in prod["worker"], "worker sin perfil desde S4A-W0-2")
check("db_test" not in prod, "db_test no existe en compose.yml")
# S5-W0-2: se suman el volumen raft de OpenBao y un volumen de token por servicio (S5-D11).
VOLS_OB = ("openbao-data", "openbao-token-api", "openbao-token-worker", "openbao-token-tools", "openbao-token-backup")
check({"pgdata", "uploads", "keys", *VOLS_OB} <= set(prod_doc.get("volumes", {})), "volumenes pgdata, uploads, keys, openbao-data y openbao-token-{api,worker,tools} en uso")
check(all(f"\n  {v}:" in texto for v in ("pgdata", "uploads", "keys", "backups", *VOLS_OB)), "volumenes pgdata, uploads, keys, backups, openbao-data y openbao-token-* declarados")
check("db_test" in dev, "db_test existe en desarrollo")
check(not [v for v in dev["db_test"].get("volumes", []) if v.get("type") == "volume"], "db_test sin volumenes persistentes")
check(any(str(p.get("target")) == "5432" for p in dev["db_test"].get("ports", [])), "db_test publica su puerto en desarrollo")
check(any(v.get("target") == "/app/migrations" for v in dev["api"].get("volumes", [])), "api en desarrollo monta migrations/ (B-3)")
check(re.search(r"POSTGRES_PASSWORD\s*[:=]\s*[^$\s]", texto) is None, "compose.yml no lleva secretos en linea (solo interpolaciones)")

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
# V4 del Sprint 2 (perfil E2E del borde): solo compose.e2e.yml monta la zona de limit_req
# alternativa sobre la de la imagen, en solo lectura; producción y desarrollo no la montan.
ZONA_E2E = "/etc/nginx/snippets/auth-zone.conf"
def montajes(servicio):
    return [v for v in (servicio.get("volumes") or []) if isinstance(v, dict)]
e2e = (json.loads(os.environ["E2E"]).get("services") or {})
for nombre, doc in (("producción", prod), ("desarrollo", dev)):
    check(not any(v.get("target") == ZONA_E2E for v in montajes(doc.get("web", {}))), f"web en {nombre} no monta la zona E2E del borde")
zona = [v for v in montajes(e2e.get("web", {})) if v.get("target") == ZONA_E2E]
check(
    len(zona) == 1 and zona[0].get("read_only") is True and str(zona[0].get("source", "")).replace("\\", "/").endswith("infra/nginx/e2e/auth-zone.conf"),
    "compose.e2e.yml monta infra/nginx/e2e/auth-zone.conf en solo lectura sobre la zona de la imagen",
)
check({"api", "web", "db"} <= set(e2e), "compose.e2e.yml se apila sobre compose.yml (api, web y db)")
# S3-W0-1 (S3-D62): postgres:16 fijado por el mismo digest en los dos compose.
img_db = str(prod.get("db", {}).get("image", ""))
img_db_test = str(dev.get("db_test", {}).get("image", ""))
check(
    re.fullmatch(r"postgres:16@sha256:[0-9a-f]{64}", img_db) is not None
    and re.fullmatch(r"postgres:16@sha256:[0-9a-f]{64}", img_db_test) is not None
    and img_db == img_db_test,
    f"postgres fijado por digest en los dos compose ({img_db or 'sin db'} / {img_db_test or 'sin db_test'})",
)
# --- S4A-W0-1 (US-113; S4A-D8, S4A-D9, S4A-D49, S4A-D56): worker endurecido y con latido ---
worker = prod["worker"]
check(worker.get("command") == ["python", "-m", "app.worker.main"], f"worker.command = python -m app.worker.main ({worker.get('command')})")
hc = worker.get("healthcheck") or {}
hc_test = hc.get("test") or []
check(len(hc_test) >= 2 and hc_test[0] == "CMD" and hc_test[1] == "python", f"worker con healthcheck CMD python ({hc_test[:2]})")
check(
    (hc.get("interval"), hc.get("timeout"), hc.get("retries"), hc.get("start_period")) == ("30s", "5s", 3, "1m30s"),
    f"healthcheck del worker 30s/5s/3/90s ({hc.get('interval')}/{hc.get('timeout')}/{hc.get('retries')}/{hc.get('start_period')})",
)
dep = worker.get("depends_on") or {}
check((dep.get("db") or {}).get("condition") == "service_healthy", "worker depende de db healthy")
check((dep.get("api") or {}).get("condition") == "service_healthy", "worker depende de api healthy")
check("ports" not in worker, "worker no publica puertos")
# S4B-W0-3: el worker monta solo backups:ro (aserción exacta mas abajo; antes era 'sin volumenes').
check(worker.get("read_only") is True, "worker con read_only")
check("/tmp" in (worker.get("tmpfs") or []), f"worker con tmpfs /tmp ({worker.get('tmpfs')})")
check(worker.get("cap_drop") == ["ALL"], f"worker con cap_drop ALL ({worker.get('cap_drop')})")
check("no-new-privileges:true" in (worker.get("security_opt") or []), f"worker con no-new-privileges ({worker.get('security_opt')})")


def fuente(v):
    return str(v.get("source", "")).replace("\\", "/").rstrip("/")


codigo_vivo = [
    f"{svc}:{fuente(v)}"
    for svc, doc in prod.items()
    for v in montajes(doc)
    if fuente(v).endswith("api/src") or fuente(v).endswith("api/migrations")
]
check(not codigo_vivo, f"ningun servicio de compose.yml monta api/src ni api/migrations ({codigo_vivo or 'ninguno'})")
dev_perfiles = json.loads(os.environ["DEV_PERFILES"])["services"]
for svc in ("worker", "tools"):
    for origen, destino in (("api/src", "/app/src"), ("api/migrations", "/app/migrations")):
        m = [v for v in montajes(dev_perfiles.get(svc, {})) if v.get("target") == destino and fuente(v).endswith(origen)]
        check(len(m) == 1 and m[0].get("read_only") is True, f"{svc} en desarrollo monta ../{origen} en {destino} en solo lectura")
# --- S4B-W0-1 (US-114; S4B-D14, D57, D59, D75, D79): servicio backup -------------------------
backup = prod.get("backup") or {}
check(bool(backup), "backup existe en produccion")
check(backup.get("image") == "apex-backup:local", f"backup.image = apex-backup:local ({backup.get('image')})")
ctx = str(((backup.get("build") or {}).get("context")) or "").replace("\\", "/")
check(ctx.endswith("infra/backup"), f"backup.build.context termina en infra/backup ({ctx})")
check("ports" not in backup, "backup no publica puertos")
check("env_file" not in backup, "backup sin env_file (solo su bloque environment)")
entorno = backup.get("environment") or {}
check(entorno.get("PGHOST") == "db", f"backup con PGHOST=db ({entorno.get('PGHOST')})")
check("DATABASE_URL" not in entorno, "backup sin DATABASE_URL")
mont = {v.get("target"): v for v in montajes(backup)}
check(
    set(mont) == {"/data/backups", "/data/uploads", "/run/apex/backup/sign.key", "/run/apex/openbao-backup"},
    f"backup monta backups, uploads, la llave de firma y el token de OpenBao (S5-B13) ({sorted(mont)})",
)
check(not (mont.get("/data/backups") or {}).get("read_only"), "backup escribe en backups")
check((mont.get("/data/uploads") or {}).get("read_only") is True, "backup monta uploads en solo lectura")
check((mont.get("/run/apex/backup/sign.key") or {}).get("read_only") is True, "la llave de firma va en solo lectura")
check(all("keys" not in str(v.get("source", "")) or v.get("type") != "volume" for v in montajes(backup)) and not any(v.get("source") == "keys" for v in montajes(backup)), "backup no monta el volumen keys")
check(backup.get("read_only") is True, "backup con read_only")
check("/tmp" in (backup.get("tmpfs") or []), f"backup con tmpfs /tmp ({backup.get('tmpfs')})")
check(backup.get("cap_drop") == ["ALL"], "backup con cap_drop ALL")
check("no-new-privileges:true" in (backup.get("security_opt") or []), "backup con no-new-privileges")
check(((backup.get("depends_on") or {}).get("db") or {}).get("condition") == "service_healthy", "backup depende de db healthy")
bhc = backup.get("healthcheck") or {}
check(bhc.get("test") == ["CMD", "pgrep", "-x", "supercronic"], f"backup healthcheck pgrep supercronic ({bhc.get('test')})")
check(
    (bhc.get("interval"), bhc.get("timeout"), bhc.get("retries"), bhc.get("start_period")) == ("30s", "5s", 3, "20s"),
    "healthcheck de backup 30s/5s/3/20s",
)
check(backup.get("restart") == "unless-stopped", "backup con restart unless-stopped")
check("backups" in prod_doc.get("volumes", {}), "volumen backups en uso")
dev_backup = dev.get("backup") or {}
check(not [v for v in montajes(dev_backup) if fuente(v).endswith("api/src")], "backup en desarrollo no monta codigo")
# compose.verify.yml: la identidad de verificacion solo en backup (S4B-D59).
vsvc = (json.loads(os.environ["VERIFY"]).get("services") or {})
vmont = [v for v in montajes(vsvc.get("backup", {})) if v.get("target") == "/run/apex/backup/verify.key"]
check(len(vmont) == 1 and vmont[0].get("read_only") is True, "compose.verify.yml monta verify.key en backup en solo lectura")
for svc in ("worker", "api", "tools"):
    check(not [v for v in montajes(vsvc.get(svc, {})) if v.get("target") == "/run/apex/backup/verify.key"], f"{svc} no recibe la identidad de verificacion")
# .env.ops.example (S4B-D79, E7/E8): existe, versionado y sin claves repetidas con .env.example.
ops_ejemplo = Path(os.environ["RAIZ"]) / ".env.ops.example"
check(ops_ejemplo.is_file(), ".env.ops.example existe")
claves_ops = set()
if ops_ejemplo.is_file():
    for linea in ops_ejemplo.read_text(encoding="utf-8").splitlines():
        if linea.strip() and not linea.strip().startswith("#") and "=" in linea:
            claves_ops.add(linea.split("=", 1)[0].strip())
check(not (claves_ops & set(ejemplo)), f"ninguna clave de .env.ops.example esta tambien en .env.example ({sorted(claves_ops & set(ejemplo))})")
check(os.environ["IGNORA_OPS_EJEMPLO"] == "no", "git versiona .env.ops.example (!.env.ops.example)")
check(os.environ["IGNORA_OPS"] == "si", "git ignora .env.ops")
# --- S4B-W0-3 (H-1, M-3, L-4, L-7; S4B-D7..D13, D56, D75, D79, D99; E3, E7, E9) -----------------
# Las contraseñas del render son CENTINELAS distintas por rol (centinelas.env): así "no contiene"
# se comprueba por valor y por nombre. `crudo` no resuelve los env_file: solo ve `environment`.
crudo_doc = json.loads(os.environ["CRUDO"])
CENT = {
    "owner": "centinela-propietario-0123456789",
    "api": "centinela-api-0123456789abcd",
    "worker": "centinela-worker-0123456789ab",
    "backup": "centinela-backup-0123456789a",
    "rclone": "centinela-rclone-secreto",
    "ownerdb": "centinela-owner-0123456789abc",
}


def entorno_de(doc, svc):
    return {k: ("" if v is None else str(v)) for k, v in (doc.get(svc, {}).get("environment") or {}).items()}


def ent(svc):
    """`environment` de produccion SIN resolver los env_file (el .env real de esta maquina no cuenta)."""
    return entorno_de(crudo_doc["services"], svc)


def depende(doc, svc):
    return {k: (v or {}).get("condition") for k, v in (doc.get(svc, {}).get("depends_on") or {}).items()}


def seguridad(doc, svc):
    s = doc.get(svc, {})
    return (
        s.get("read_only") is True
        and s.get("cap_drop") == ["ALL"]
        and "no-new-privileges:true" in (s.get("security_opt") or [])
    )


cr = crudo_doc["services"]
SERVICIOS_PROD = {"db", "migrate", "dbsetup", "api", "worker", "web", "backup", "tools"}
check(SERVICIOS_PROD <= set(prod), f"produccion define {sorted(SERVICIOS_PROD)} ({sorted(prod)})")
db_url_dueno = f"postgresql+asyncpg://apex:{CENT['owner']}@db:5432/apex"

# migrate (S4B-D8): unidad de arranque aparte, credencial del propietario, sin env_file.
mig = prod.get("migrate", {})
check(mig.get("image") == "apex-api:local", f"migrate usa apex-api:local ({mig.get('image')})")
check(mig.get("command") == ["alembic", "upgrade", "head"], f"migrate.command = alembic upgrade head ({mig.get('command')})")
check(mig.get("restart") == "no", f"migrate con restart no ({mig.get('restart')})")
check("env_file" not in cr.get("migrate", {}), "migrate sin env_file")
check(ent("migrate").get("DATABASE_URL", "").startswith("postgresql+asyncpg://apex_owner:"), f"migrate.DATABASE_URL usa apex_owner (S5-D89) ({ent('migrate').get('DATABASE_URL', '')[:40]})")
check(depende(prod, "migrate") == {"db": "service_healthy"}, f"migrate depende solo de db healthy ({depende(prod, 'migrate')})")
check("ports" not in mig and not mig.get("volumes"), "migrate sin ports ni volumenes")
check(str(mig.get("user")) == "10001:10001", f"migrate con user 10001:10001 ({mig.get('user')})")
check(seguridad(prod, "migrate"), "migrate con read_only, cap_drop ALL y no-new-privileges (L-7)")

# dbsetup (S4B-D9, D72): postgres:16 por el digest de db, apply.sh, tres contraseñas de rol.
dbs = prod.get("dbsetup", {})
check(dbs.get("image") == prod["db"]["image"], f"dbsetup usa la imagen de db ({dbs.get('image')})")
check(dbs.get("entrypoint") == ["/bin/sh", "/opt/db/apply.sh"], f"dbsetup.entrypoint ({dbs.get('entrypoint')})")
dbs_mont = {v.get("target"): v for v in montajes(dbs)}
check(
    set(dbs_mont) == {"/opt/db"} and dbs_mont["/opt/db"].get("read_only") is True and fuente(dbs_mont["/opt/db"]).endswith("infra/db"),
    f"dbsetup monta solo infra/db en /opt/db de solo lectura ({sorted(dbs_mont)})",
)
env_dbs = ent("dbsetup")
check(
    {"PGHOST", "PGUSER", "PGPASSWORD", "PGDATABASE", "APEX_API_DB_PASSWORD", "APEX_WORKER_DB_PASSWORD", "APEX_BACKUP_DB_PASSWORD"} <= set(env_dbs),
    f"dbsetup con las credenciales del propietario y las tres contraseñas de rol ({sorted(env_dbs)})",
)
check(env_dbs.get("PGPASSWORD") == CENT["owner"] and env_dbs.get("APEX_API_DB_PASSWORD") == CENT["api"], "dbsetup recibe cada contraseña de su variable")
check("env_file" not in cr.get("dbsetup", {}), "dbsetup sin env_file")
check(depende(prod, "dbsetup").get("migrate") == "service_completed_successfully", f"dbsetup depende de migrate completado en produccion ({depende(prod, 'dbsetup')})")
check(str(dbs.get("user")) == "999:999", f"dbsetup con user 999:999 ({dbs.get('user')})")
check(seguridad(prod, "dbsetup") and dbs.get("restart") == "no", "dbsetup endurecido y con restart no")
check("ports" not in dbs, "dbsetup sin ports")

# db: solo POSTGRES_*, sin env_file (H-1).
check("env_file" not in cr["db"], "db sin env_file")
check(set(ent("db")) == {"POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "APEX_OWNER_DB_PASSWORD"}, f"db: environment POSTGRES_* y APEX_OWNER_DB_PASSWORD ({sorted(ent('db'))})")

# api (S4B-D56, D75).
check(archivos("api") == [(".env", True)], f"api: env_file exactamente [.env] ({archivos('api')})")
env_api = ent("api")
check(env_api.get("DATABASE_URL", "").startswith("postgresql+asyncpg://apex_api:"), "api.DATABASE_URL usa apex_api")
check(env_api.get("MIGRATE_ON_STARTUP") == "false", f"api con MIGRATE_ON_STARTUP=false ({env_api.get('MIGRATE_ON_STARTUP')})")
check(env_api.get("APP_VERSION") == "dev", f"api con APP_VERSION=${{GIT_SHA:-dev}} ({env_api.get('APP_VERSION')})")
dep_api = depende(prod, "api")
check(dep_api.get("dbsetup") == "service_completed_successfully" and dep_api.get("db") == "service_healthy", f"api depende de dbsetup completado y db healthy ({dep_api})")
check(((prod["api"].get("healthcheck") or {}).get("start_period")) in ("1m0s", "60s"), f"api con start_period 60s ({(prod['api'].get('healthcheck') or {}).get('start_period')})")
check(seguridad(prod, "api") and "/tmp" in (prod["api"].get("tmpfs") or []), "api con read_only, tmpfs /tmp, cap_drop ALL y no-new-privileges")
mont_api = {v.get("target"): v for v in montajes(prod["api"])}
check(mont_api.get("/run/apex/keys/custody", {}).get("read_only") is True and mont_api.get("/run/apex/keys/jwt", {}).get("read_only") is True, "api: keys (custody y jwt) en solo lectura")
check("/data/uploads" in mont_api and not mont_api["/data/uploads"].get("read_only"), "api: uploads con escritura")
for svc in ("api", "web"):
    arg = (prod[svc].get("build") or {}).get("args") or {}
    check(arg.get("GIT_SHA") == "dev", f"{svc}: build.args.GIT_SHA = ${{GIT_SHA:-dev}} ({arg.get('GIT_SHA')})")

# worker (S4B-D10, D11).
check(archivos("worker") == [(".env", True)], f"worker: env_file exactamente [.env] ({archivos('worker')})")
env_w = ent("worker")
check(env_w.get("DATABASE_URL", "").startswith("postgresql+asyncpg://apex_worker:"), "worker.DATABASE_URL usa apex_worker")
check(env_w.get("BACKUP_DIR") == "/data/backups", f"worker con BACKUP_DIR=/data/backups ({env_w.get('BACKUP_DIR')})")
mont_w = montajes(prod["worker"])
# S5-W0-2 (S5-D11): a backups:ro se suma su token de OpenBao, tambien :ro. S5-B3 (S5-D197): con el
# proveedor local suma keys:ro (descifra avisos); compose.openbao.yml lo quita (S5-D193).
check(
    sorted((m.get("source"), m.get("target"), m.get("read_only")) for m in mont_w)
    == [("backups", "/data/backups", True), ("keys", "/run/apex/keys/custody", True), ("keys", "/run/apex/keys/sign", True), ("openbao-token-worker", "/run/apex/openbao", True)],
    f"worker monta exactamente backups en /data/backups, keys (subpaths custody y sign) y su token en /run/apex/openbao, todos de solo lectura ({[(m.get('source'), m.get('target')) for m in mont_w]})",
)

# web (S4B-D11, D75).
web = prod["web"]
check(depende(prod, "web") == {"api": "service_healthy"}, f"web depende de api healthy ({depende(prod, 'web')})")
check(web.get("read_only") is True and web.get("cap_drop") == ["ALL"] and "no-new-privileges:true" in (web.get("security_opt") or []), "web con read_only, cap_drop ALL y no-new-privileges")
check({str(t).split(":")[0] for t in (web.get("tmpfs") or [])} >= {"/var/cache/nginx", "/var/run", "/tmp"}, f"web con tmpfs /var/cache/nginx, /var/run y /tmp ({web.get('tmpfs')})")
check(sorted(web.get("cap_add") or []) == ["CHOWN", "NET_BIND_SERVICE", "SETGID", "SETUID"], f"web con cap_add exactamente CHOWN, SETGID, SETUID, NET_BIND_SERVICE ({web.get('cap_add')})")

# backup (S4B-D7: rol apex_backup en producción).
env_b = ent("backup")
check(env_b.get("PGUSER") == "apex_backup" and env_b.get("PGPASSWORD") == CENT["backup"], f"backup usa apex_backup con su contraseña ({env_b.get('PGUSER')})")
dep_b = depende(prod, "backup")
check(dep_b.get("dbsetup") == "service_completed_successfully" and dep_b.get("db") == "service_healthy", f"backup depende de dbsetup completado y db healthy ({dep_b})")

# tools: propietario por environment, backups de solo lectura (S4B-D86).
check(archivos("tools") == [(".env", True), (".env.seed", False)], f"tools: env_file [.env, .env.seed opcional] ({archivos('tools')})")
check(ent("tools").get("DATABASE_URL", "").startswith("postgresql+asyncpg://apex_owner:"), f"tools.DATABASE_URL usa apex_owner por environment (S5-D89) ({ent('tools').get('DATABASE_URL', '')[:40]})")
mont_t = {v.get("target"): v for v in montajes(prod["tools"])}
check(mont_t.get("/data/backups", {}).get("read_only") is True, "tools monta backups en solo lectura")
check(mont_t.get("/run/apex/keys") is not None and not mont_t["/run/apex/keys"].get("read_only"), "tools: keys con escritura")
check("/data/uploads" in mont_t, "tools monta uploads")

# S5-W0-4 (M-12, S5-D6, D62, D89): apex_owner NOSUPERUSER es el dueno de los esquemas en pilas nuevas.
mont_db = {v.get("target"): v for v in montajes(prod["db"])}
init_owner = mont_db.get("/docker-entrypoint-initdb.d/10-apex-owner.sh", {})
check(bool(init_owner) and init_owner.get("read_only") is True and fuente(init_owner).endswith("infra/db/initdb/10-apex-owner.sh"), f"S5: db monta infra/db/initdb/10-apex-owner.sh en /docker-entrypoint-initdb.d de solo lectura ({sorted(mont_db)})")
check(ent("db").get("APEX_OWNER_DB_PASSWORD") == CENT["ownerdb"], "S5: db recibe APEX_OWNER_DB_PASSWORD por environment")
for svc in ("api", "worker", "web", "backup", "dbsetup"):
    check("APEX_OWNER_DB_PASSWORD" not in ent(svc), f"S5: {svc} no recibe APEX_OWNER_DB_PASSWORD")
check(ent("migrate").get("DATABASE_URL", "").startswith("postgresql+asyncpg://apex_owner:" + CENT["ownerdb"] + "@"), "S5: migrate entra con apex_owner y su contraseña")
check(ent("tools").get("DATABASE_URL", "").startswith("postgresql+asyncpg://apex_owner:" + CENT["ownerdb"] + "@"), "S5: tools entra con apex_owner y su contraseña")
raw_mig = (os.environ["COMPOSE_YML"])
check("postgresql+asyncpg://${MIGRATE_DB_USER:-apex_owner}:" in raw_mig, "S5: compose.yml: migrate usa ${MIGRATE_DB_USER:-apex_owner} (S5-D89)")
check("postgresql+asyncpg://${TOOLS_DB_USER:-apex_owner}:" in raw_mig, "S5: compose.yml: tools usa ${TOOLS_DB_USER:-apex_owner} (S5-D89)")
su = json.loads(os.environ["SU"]).get("services", {})
con_su = sorted(
    svc for svc, doc in su.items()
    if svc not in ("db", "dbsetup") and "centinela-super" in json.dumps({k: doc.get(k) for k in ("environment", "command", "entrypoint", "healthcheck")})
)
check(not con_su, f"S5: POSTGRES_USER solo llega a db y dbsetup ({con_su or 'ninguno'})")
check("centinela-super" in json.dumps(su.get("db", {}).get("environment")) and "centinela-super" in json.dumps(su.get("dbsetup", {}).get("environment")), "S5: db y dbsetup siguen recibiendo POSTGRES_USER")

# Secretos por servicio (H-1): por nombre y por valor.
DUENOS = {"db", "migrate", "dbsetup", "tools"}  # S5-W0-4: migrate y tools ya no llevan la del propietario
for svc in sorted(set(prod) - DUENOS):
    env = ent(svc)
    check("POSTGRES_PASSWORD" not in env, f"{svc} no recibe POSTGRES_PASSWORD")
    check(CENT["owner"] not in env.values(), f"{svc} no recibe la contraseña del propietario por valor")
for svc in ("api", "worker", "web"):
    env = ent(svc)
    # S5-B13 (S5-D170): worker y tools reciben BACKUP_SIGN_PUBKEY (publica); las demas BACKUP_SIGN_* siguen prohibidas.
    prohibidas = [k for k in env if k.endswith("_DB_PASSWORD") or k.startswith(("RCLONE_", "BACKUP_AGE_", "BACKUP_SIGN_")) and not (k == "BACKUP_SIGN_PUBKEY" and svc == "worker")]
    check(not prohibidas, f"{svc} sin *_DB_PASSWORD, RCLONE_*, BACKUP_AGE_* ni BACKUP_SIGN_* salvo la publica ({prohibidas or 'ninguna'})")
    propios = {"api": ("api",), "worker": ("worker",), "web": ()}[svc]
    ajenos = [n for n, c in CENT.items() if n not in propios and any(c in v for v in env.values())]
    check(not ajenos, f"{svc} no contiene contraseñas de otros roles por valor")
    check(not str(env.get("DATABASE_URL", "")).startswith("postgresql+asyncpg://apex:"), f"{svc}.DATABASE_URL no usa al propietario")
check(CENT["api"] in ent("api").get("DATABASE_URL", "") and CENT["worker"] not in ent("api").get("DATABASE_URL", ""), "api usa solo su contraseña de rol")
check(CENT["worker"] in ent("worker").get("DATABASE_URL", ""), "worker usa su contraseña de rol")

# E7: el recorte de .env.example y lo que pasa a .env.ops.example.
def claves_de(ruta):
    salida = {}
    if ruta.is_file():
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if linea.strip() and not linea.strip().startswith("#") and "=" in linea:
                k, v = linea.split("=", 1)
                salida[k.strip()] = v.strip()
    return salida


ej = claves_de(Path(os.environ["RAIZ"]) / ".env.example")
ops = claves_de(Path(os.environ["RAIZ"]) / ".env.ops.example")
check(web_ip_txt == ops.get("APEX_WEB_IP"), f"web.ipv4_address = APEX_WEB_IP ({web_ip_txt})")
ajenas_en_ej = [k for k in ej if k.startswith(("POSTGRES_", "RCLONE_", "BACKUP_")) or k.endswith("_DB_PASSWORD") or k in ("DATABASE_URL", "TEST_DATABASE_URL")]
check(not ajenas_en_ej, f".env.example sin POSTGRES_, _DB_PASSWORD, RCLONE_, BACKUP_ ni DATABASE_URL ({ajenas_en_ej or 'limpio'})")
faltan_ops = [k for k in ("POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_DB", "DATABASE_URL", "TEST_DATABASE_URL", "WEB_PORT", "API_PORT", "DB_PORT", "DB_TEST_PORT") if k not in ops]
check(not faltan_ops, f".env.ops.example trae POSTGRES_*, DATABASE_URL, TEST_DATABASE_URL y los cuatro puertos (faltan {faltan_ops or 'ninguna'})")
check(ej.get("TRUSTED_PROXIES") == "172.30.0.10/32", "TRUSTED_PROXIES de .env.example sigue siendo 172.30.0.10/32")

# Red parametrizada (S4B-D13): con y sin APEX_SUBNET, APEX_IP_RANGE y APEX_WEB_IP.
def red_de(doc):
    cfg = ((doc.get("networks", {}).get("default", {}).get("ipam") or {}).get("config") or [{}])[0]
    ip = (((doc["services"]["web"].get("networks") or {}).get("default") or {}).get("ipv4_address"))
    return cfg.get("subnet"), cfg.get("ip_range"), ip


check(red_de(json.loads(os.environ["PROD_SIN_OPS"])) == ("172.30.0.0/24", "172.30.0.128/25", "172.30.0.10"), f"sin variables de red valen los de hoy ({red_de(json.loads(os.environ['PROD_SIN_OPS']))})")
check(red_de(json.loads(os.environ["PROD_RED"])) == ("172.31.0.0/24", "172.31.0.128/25", "172.31.0.10"), f"con APEX_SUBNET, APEX_IP_RANGE y APEX_WEB_IP cambian ({red_de(json.loads(os.environ['PROD_RED']))})")

# E3 (S4B-D99): en desarrollo migrate y dbsetup llevan perfil y el RUNBOOK documenta --no-deps.
init = json.loads(os.environ["DEV_INIT"])["services"]
check("migrate" not in dev and "dbsetup" not in dev, "en desarrollo sin perfil no existen migrate ni dbsetup")
check(init.get("migrate", {}).get("profiles") == ["prod-init"] and init.get("dbsetup", {}).get("profiles") == ["prod-init"], "en desarrollo migrate y dbsetup llevan profiles [prod-init]")
check(int(os.environ.get("RUNBOOK_NO_DEPS", "0")) >= 1, "docs/RUNBOOK.md documenta `run --rm --no-deps dbsetup`")

# Desarrollo (S4B-D11, E9): el propietario, MIGRATE_ON_STARTUP=true y depends_on solo db.
for svc in ("api", "worker"):
    env = entorno_de(dev, svc)
    check(env.get("DATABASE_URL") == db_url_dueno, f"desarrollo: {svc}.DATABASE_URL usa ${{POSTGRES_USER}} (propietario)")
    check(env.get("MIGRATE_ON_STARTUP") == "true", f"desarrollo: {svc} con MIGRATE_ON_STARTUP=true")
    check(set(depende(dev, svc)) == {"db"}, f"desarrollo: {svc} depende solo de db (!override) ({depende(dev, svc)})")
db_b = entorno_de(dev, "backup")
check(set(depende(dev, "backup")) == {"db"} and depende(dev, "backup")["db"] == "service_healthy", f"E9: backup en desarrollo depende solo de db healthy ({depende(dev, 'backup')})")
check("dbsetup" not in depende(dev, "backup"), "E9: backup en desarrollo no depende de dbsetup")
check(db_b.get("PGUSER") == "apex" and db_b.get("PGPASSWORD") == CENT["owner"], f"E9: backup en desarrollo usa ${{POSTGRES_USER}} y su contraseña ({db_b.get('PGUSER')})")
check(os.environ.get("DEV_QUIET") == "0", "E9: el render de desarrollo valida con config --quiet")

# E2E (compose.yml + compose.e2e.yml) contiene la cadena completa.
check({"migrate", "dbsetup", "api", "web", "db", "worker", "backup"} <= set(e2e), f"compose.e2e.yml contiene migrate, dbsetup, api, web, db, worker y backup ({sorted(e2e)})")

# --- S5-W0-2 (US-133, US-136; S5-D10, D11, D12, D15, D74, D77, D104; M-1, M-2, M-3, L-3) -----------
# OpenBao (custodia de llaves): servicio, red `custody`, tokens por servicio, bootstrap, overlay.
def redes_de(doc, svc):
    return set(((doc.get(svc) or {}).get("networks") or {"default": None}).keys())


def hay(doc, svc):
    return svc in doc


ob = prod.get("openbao") or {}
check(hay(prod, "openbao"), "S5: produccion define el servicio openbao (sin perfil)")
check(re.fullmatch(r"openbao/openbao:2\.7\.2@sha256:[0-9a-f]{64}", str(ob.get("image", ""))) is not None, f"S5: openbao con imagen openbao/openbao:2.7.2 por digest ({ob.get('image')})")
check(hay(prod, "openbao") and "ports" not in ob, "S5: openbao no publica puertos")
check(ob.get("read_only") is True, "S5: openbao con read_only")
check("/tmp" in (ob.get("tmpfs") or []), f"S5: openbao con tmpfs /tmp ({ob.get('tmpfs')})")
check(ob.get("cap_drop") == ["ALL"], f"S5: openbao con cap_drop ALL ({ob.get('cap_drop')})")
check("no-new-privileges:true" in (ob.get("security_opt") or []), f"S5: openbao con no-new-privileges ({ob.get('security_opt')})")
usuario_ob = str(ob.get("user", "")).split(":")[0]
check(usuario_ob not in ("", "0", "root"), f"S5: openbao corre con usuario no raiz fijo ({ob.get('user')})")
check(hay(prod, "openbao") and redes_de(prod, "openbao") == {"custody"}, f"S5: openbao solo en la red custody ({sorted(redes_de(prod, 'openbao'))})")
custody = prod_doc.get("networks", {}).get("custody", {})
check(custody.get("internal") is True, f"S5: la red custody es internal: true ({custody.get('internal')})")
sub_custody = (((custody.get("ipam") or {}).get("config") or [{}])[0]).get("subnet", "")
try:
    c_red = ipaddress.ip_network(sub_custody)
    d_red = ipaddress.ip_network(subred_txt)
    custody_bien = c_red.prefixlen == 24 and not c_red.overlaps(d_red)
except ValueError:
    custody_bien = False
check(custody_bien, f"S5: custody con subred /24 fija que no solapa la red default ({sub_custody or 'sin subred'}; S5-D77)")
mont_ob = {v.get("target"): v for v in montajes(ob)}
check(
    set(mont_ob) == {"/openbao/file", "/openbao/config/config.hcl"},
    f"S5: openbao monta exactamente /openbao/file y /openbao/config/config.hcl ({sorted(mont_ob)})",
)
check((mont_ob.get("/openbao/file") or {}).get("source") == "openbao-data", "S5: el raft va en el volumen openbao-data (no bind mount)")
cfg_ob = mont_ob.get("/openbao/config/config.hcl") or {}
check(cfg_ob.get("read_only") is True and fuente(cfg_ob).endswith("infra/openbao/config.hcl"), "S5: openbao monta infra/openbao/config.hcl en solo lectura (el archivo, nunca la carpeta)")
check(not [v for v in montajes(ob) if fuente(v).endswith("infra/openbao") or v.get("target") in ("/openbao/config", "/openbao")], "S5: openbao no monta la carpeta infra/openbao ni /openbao/config")
check(any("-config=/openbao/config/config.hcl" in str(c) for c in (ob.get("command") or [])), f"S5: openbao arranca con server -config=/openbao/config/config.hcl ({ob.get('command')})")
hc_ob = ob.get("healthcheck") or {}
hc_txt = " ".join(str(x) for x in (hc_ob.get("test") or []))
check("wget" in hc_txt and "/v1/sys/health?sealedcode=200&uninitcode=200" in hc_txt and "curl" not in hc_txt, f"S5: healthcheck de openbao con wget a sys/health?sealedcode=200&uninitcode=200 ({hc_txt[:90]})")
check(all(hc_ob.get(k) for k in ("interval", "timeout", "retries", "start_period")), f"S5: healthcheck de openbao con interval, timeout, retries y start_period ({sorted(hc_ob)})")

# openbao-bootstrap (perfil bootstrap): solo existe con el perfil; sin logs; CHOWN y nada mas.
check("openbao-bootstrap" not in prod, "S5: openbao-bootstrap no existe sin el perfil bootstrap")
boot_doc = json.loads(os.environ["BOOT"])
boot_s = boot_doc.get("services", {})
bs = boot_s.get("openbao-bootstrap") or {}
check(bs.get("profiles") == ["bootstrap"], f"S5: openbao-bootstrap con profiles [bootstrap] ({bs.get('profiles')})")
check((bs.get("logging") or {}).get("driver") == "none", f"S5: openbao-bootstrap con logging.driver none (M-1) ({bs.get('logging')})")
check(bs.get("cap_drop") == ["ALL"] and bs.get("cap_add") == ["CHOWN"], f"S5: openbao-bootstrap con cap_drop ALL y cap_add solo CHOWN ({bs.get('cap_drop')} / {bs.get('cap_add')})")
check(bs.get("restart") == "no", f"S5: openbao-bootstrap con restart no ({bs.get('restart')})")
check(bool(bs) and "ports" not in bs and bs.get("network_mode") == "service:openbao" and not bs.get("networks"), f"S5 S5-D107: openbao-bootstrap sin puertos, con network_mode service:openbao y sin red propia ({bs.get('network_mode')} / {bs.get('networks')})")
check(bool(bs) and (bs.get("environment") or {}).get("BAO_ADDR") == "http://127.0.0.1:8210", f"S5 S5-D107: openbao-bootstrap habla con el listener local 127.0.0.1:8210 ({(bs.get('environment') or {}).get('BAO_ADDR')})")
check(bool(bs) and "env_file" not in bs, "S5: openbao-bootstrap sin env_file")
fuentes_boot = {v.get("source") for v in montajes(bs) if v.get("type") == "volume"}
check({"openbao-token-api", "openbao-token-worker", "openbao-token-tools", "openbao-token-backup"} <= fuentes_boot, f"S5: openbao-bootstrap escribe los cuatro volumenes de token, backup incluido (S5-B13) ({sorted(fuentes_boot)})")
check(bool(bs) and all(v.get("read_only") is True for v in montajes(bs) if v.get("type") == "bind"), "S5: los bind mounts de openbao-bootstrap van en solo lectura")
check(bool(bs) and not [v for v in montajes(bs) if v.get("source") in ("keys", "pgdata", "uploads", "backups")], "S5: openbao-bootstrap no monta keys, pgdata, uploads ni backups")

# Tokens (S5-D11): un volumen por servicio, :ro y solo en su servicio.
for quien in ("api", "worker", "tools"):
    vol = f"openbao-token-{quien}"
    duenos = {s for s, d in prod.items() for v in montajes(d) if v.get("source") == vol}
    check(duenos == {quien}, f"S5: {vol} montado solo en {quien} ({sorted(duenos) or 'ninguno'})")
    check(bool(duenos) and all(v.get("read_only") is True for v in montajes(prod.get(quien, {})) if v.get("source") == vol), f"S5: {vol} en solo lectura en {quien}")

# Redes (S5-D10): api, worker y tools en default y custody; web, db y backup fuera de custody.
for svc in ("api", "worker", "tools"):
    check(redes_de(prod, svc) == {"default", "custody"}, f"S5: {svc} en las redes default y custody ({sorted(redes_de(prod, svc))})")
for svc in ("web", "db"):
    check("custody" not in redes_de(prod, svc), f"S5: {svc} fuera de la red custody ({sorted(redes_de(prod, svc))})")

# S5-B13 (S5-D8, S5-D11, L-2): backup se une a custody para pedir la instantanea raft; su token
# (apex-backup-snapshot) vive en un volumen propio, montado :ro SOLO en backup.
check(redes_de(prod, "backup") == {"default", "custody"}, f"S5-B13: backup en las redes default y custody ({sorted(redes_de(prod, 'backup'))})")
duenos_bk = {s for s, d in prod.items() for v in montajes(d) if v.get("source") == "openbao-token-backup"}
check(duenos_bk == {"backup"}, f"S5-B13: openbao-token-backup montado solo en backup ({sorted(duenos_bk) or 'ninguno'})")
mont_bk = [v for v in montajes(prod.get("backup", {})) if v.get("source") == "openbao-token-backup"]
check(len(mont_bk) == 1 and mont_bk[0].get("read_only") is True and mont_bk[0].get("target") == "/run/apex/openbao-backup", f"S5-B13: backup monta openbao-token-backup en /run/apex/openbao-backup:ro ({[(v.get('target'), v.get('read_only')) for v in mont_bk]})")
check(not [s for s in ("api", "worker", "tools", "web", "db") if any("openbao-backup" in str(v.get("target")) for v in montajes(prod.get(s, {})))], "S5-B13: nadie mas monta /run/apex/openbao-backup")
check(prod["backup"].get("cap_drop") == ["ALL"] and prod["backup"].get("read_only") is True, "S5-B13: backup conserva cap_drop ALL y read_only")
# H-1: worker y tools reciben la llave publica para verificar la firma del manifiesto (S5-D72, no es secreta).
for svc in ("worker", "tools"):
    check("BACKUP_SIGN_PUBKEY" in ent(svc), f"S5-B13: {svc} recibe BACKUP_SIGN_PUBKEY por environment (S5-D72)")
for svc in ("api", "web", "db"):
    check("BACKUP_SIGN_PUBKEY" not in ent(svc), f"S5-B13: {svc} no recibe BACKUP_SIGN_PUBKEY")
check("BACKUP_SIGN_KEY_FILE" not in "".join(ent("worker")) + "".join(ent("tools")), "S5-B13: la llave privada de firma nunca llega a worker ni tools")
for svc in ("api", "worker"):
    check(depende(prod, svc).get("openbao") == "service_healthy", f"S5: {svc} depende de openbao healthy ({depende(prod, svc)})")
check(prod["tools"].get("cap_drop") == ["ALL"], f"S5: tools con cap_drop ALL (L-3) ({prod['tools'].get('cap_drop')})")

# Healthcheck del api tolerante al sellado (S5-D15): 200, o 503 con db == ok y migrations == ok.
hc_api = (prod["api"].get("healthcheck") or {}).get("test") or []
guion = str(hc_api[3]) if len(hc_api) >= 4 else ""
check(hc_api[:3] == ["CMD", "python", "-c"], f"S5: healthcheck del api sigue siendo CMD python -c ({hc_api[:3]})")
check(all(s in guion for s in ("503", "HTTPError", "db", "migrations", "ok", "127.0.0.1:8000/health")) and "curl" not in guion, "S5: el guion del api acepta 200, o 503 con db == ok y migrations == ok (lee el cuerpo del HTTPError; sin curl)")
check(guion.count("ok") >= 2 and "sys.exit" in guion, "S5: el guion del api compara db y migrations contra ok y sale con sys.exit")

# M-3: nada de desarrollo en el compose de produccion ni en el overlay.
for nombre, contenido in (("compose.yml", texto), ("compose.openbao.yml", os.environ.get("OVL_YML", ""))):
    for prohibida in ("dev-entrypoint", "BOOTSTRAP_NONINTERACTIVE", "openbao-seal"):
        check(prohibida not in contenido, f"S5 M-3: {nombre} no contiene {prohibida}")
check("openbao-dev-data" not in texto, "S5 M-3: compose.yml no declara el volumen openbao-dev-data")

# compose.openbao.yml (S5-D74, S5-D193): worker sin keys; api con keys SOLO LECTURA (la llave JWT vive ahí;
# kek.bin lo borra retire-local-kek); ambos con su token; tools conserva keys.
ovl_doc = json.loads(os.environ["OVL"])
ovl = ovl_doc.get("services", {})
check(bool(ovl.get("api")) and bool(ovl.get("worker")), "S5: el overlay renderiza con api y worker")
check(not [v for v in montajes(ovl.get("worker", {})) if v.get("source") == "keys" or str(v.get("target", "")).startswith("/run/apex/keys")] and bool(ovl.get("worker")), "S5: con compose.openbao.yml worker no monta keys (ni la subruta custody, S6-D58)")
check(keys_de(ovl, "api") == [("/run/apex/keys/custody", "custody", True), ("/run/apex/keys/jwt", "jwt", True)], f"S5-D193, S7-D4: con compose.openbao.yml api monta keys con subpath custody y jwt en solo lectura ({keys_de(ovl, 'api')})")
for svc in ("api", "worker"):
    check(any(v.get("source") == f"openbao-token-{svc}" and v.get("read_only") is True for v in montajes(ovl.get(svc, {}))), f"S5: con compose.openbao.yml {svc} monta su token en solo lectura")
check(any(v.get("target") == "/run/apex/keys" for v in montajes(ovl.get("tools", {}))), "S5: con compose.openbao.yml tools conserva keys (migrate-provider)")
check("ports" not in (ovl.get("openbao") or {}) and bool(ovl.get("openbao")), "S5: el overlay conserva openbao sin puertos")

# Desarrollo (S5-D12): openbao con perfil y volumen propio; api, worker y tools no dependen de el.
dob = json.loads(os.environ["DEV_OB"]).get("services", {})
dev_ob = dob.get("openbao") or {}
check("openbao" not in dev, "S5: en desarrollo sin perfil openbao no existe")
check(dev_ob.get("profiles") == ["openbao"], f"S5: en desarrollo openbao con profiles [openbao] ({dev_ob.get('profiles')})")
check(any(v.get("source") == "openbao-dev-data" for v in montajes(dev_ob)) and not any(v.get("source") == "openbao-data" for v in montajes(dev_ob)), "S5: en desarrollo openbao usa el volumen openbao-dev-data (no openbao-data)")
check(any("dev-entrypoint" in str(c) for c in list(dev_ob.get("entrypoint") or []) + list(dev_ob.get("command") or [])), "S5: en desarrollo openbao arranca con dev-entrypoint.sh")
check((dev_ob.get("environment") or {}).get("APEX_ENV") == "dev", f"S5 M-3: en desarrollo openbao lleva APEX_ENV=dev ({(dev_ob.get('environment') or {}).get('APEX_ENV')})")
check("openbao-dev-data" in json.loads(os.environ["DEV_OB"]).get("volumes", {}), "S5: openbao-dev-data declarado en la vista de desarrollo")
for svc in ("api", "worker"):
    check(set(depende(dev, svc)) == {"db"} and set(depende(dob, svc)) == {"db"}, f"S5: desarrollo: {svc} depende solo de db, con y sin el perfil openbao ({depende(dob, svc)})")
check("openbao" not in depende(dob, "tools"), f"S5: desarrollo: tools no depende de openbao ({depende(dob, 'tools')})")

# S5-B4 (S5-D78): Mailpit y el Telegram falso, solo en desarrollo, con el perfil `avisos`, por digest.
dav = json.loads(os.environ["DEV_AV"]).get("services", {})
mailpit, tfake = dav.get("mailpit") or {}, dav.get("telegram-fake") or {}
check("mailpit" not in dev and "telegram-fake" not in dev, "S5-B4: en desarrollo sin el perfil avisos no existen mailpit ni telegram-fake")
check(mailpit.get("profiles") == ["avisos"], f"S5-B4: mailpit con profiles [avisos] ({mailpit.get('profiles')})")
check(tfake.get("profiles") == ["avisos"], f"S5-B4: telegram-fake con profiles [avisos] ({tfake.get('profiles')})")
check(re.fullmatch(r"axllent/mailpit:v?[0-9][^@]*@sha256:[0-9a-f]{64}", str(mailpit.get("image", ""))) is not None, f"S5-B4: mailpit por digest ({mailpit.get('image')})")
check(re.fullmatch(r"python:3\.12-alpine@sha256:[0-9a-f]{64}", str(tfake.get("image", ""))) is not None, f"S5-B4: telegram-fake usa python:3.12-alpine por digest ({tfake.get('image')})")
puertos_mp = [(p.get("host_ip"), str(p.get("published")), p.get("target")) for p in mailpit.get("ports", [])]
check(puertos_mp == [("127.0.0.1", "8125", 8025)], f"S5-B4: mailpit solo publica 127.0.0.1:8125 (interfaz web); el SMTP 1025 no ({puertos_mp})")
check(bool(tfake) and "ports" not in tfake, "S5-B4: telegram-fake no publica puertos")
check(any(str(v.get("source", "")).replace("\\", "/").endswith("scripts/dev/telegram_fake.py") and v.get("read_only") is True for v in montajes(tfake)), "S5-B4: telegram-fake monta scripts/dev/telegram_fake.py en solo lectura")
for svc in ("api", "worker", "tools"):
    check(not ({"mailpit", "telegram-fake"} & set(depende(dav, svc))), f"S5-B4: {svc} no depende de mailpit ni de telegram-fake ({depende(dav, svc)})")
check(not ({"mailpit", "telegram-fake"} & set(prod)) and "mailpit" not in texto and "telegram-fake" not in texto, "S5-B4: compose.yml (produccion) no nombra mailpit ni telegram-fake")
for svc in ("mailpit", "telegram-fake"):
    check(str((dav.get(svc) or {}).get("restart", "no")) in ("no", "", "None"), f"S5-B4: {svc} no se reinicia solo (herramienta de desarrollo)")


# Rojo S6-W0-5 (S6-D79, O4): un solo proceso del api. Ningun servicio (en produccion, desarrollo y
# con todos los perfiles) declara --workers en su comando ni recibe UVICORN_WORKERS o WEB_CONCURRENCY.
for etiqueta, doc in (("produccion", prod), ("desarrollo", dev), ("desarrollo con perfiles", dev_perfiles)):
    for nombre, servicio in doc.items():
        orden = [str(x) for x in (servicio.get("command") or []) + (servicio.get("entrypoint") or [])]
        check(not any(x == "--workers" or x.startswith("--workers=") for x in orden), f"S6-D79: {etiqueta}: {nombre} sin --workers en command/entrypoint")
        entorno = servicio.get("environment") or {}
        check(not ({"UVICORN_WORKERS", "WEB_CONCURRENCY"} & set(entorno)), f"S6-D79: {etiqueta}: {nombre} no recibe UVICORN_WORKERS ni WEB_CONCURRENCY")

# Rojo S6-W0-5 (S6-D57, D65, D77): el bloque environment del api recibe el almacen y el dominio;
# worker y tools no reciben APEX_DOMAIN (validate_origins solo corre en el api).
entorno_api = prod["api"].get("environment") or {}
for variable in ("STORAGE_PROVIDER", "S3_ENDPOINT_URL", "S3_BUCKET", "S3_REGION", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY", "S3_ENABLE_PRODUCTION", "APEX_DOMAIN"):
    check(variable in entorno_api, f"S6-W0-5: api recibe {variable} en su bloque environment")
# Verde: `prod` resuelve el env_file (`.env` trae APEX_DOMAIN, no secreta, y por env_file le llega
# también a worker y tools; Compose no permite quitar una clave del env_file). Lo que se afirma es
# que ningún servicio salvo el api la declara explícitamente en su bloque environment.
for svc in ("worker", "tools"):
    check("APEX_DOMAIN" not in (crudo_doc["services"][svc].get("environment") or {}), f"S6-W0-5: {svc} no declara APEX_DOMAIN en su bloque environment (por env_file sí la hereda; solo el api la valida)")
    check("S3_SECRET_ACCESS_KEY" not in (prod[svc].get("environment") or {}), f"S6-W0-5: {svc} no recibe S3_SECRET_ACCESS_KEY")

# Rojo S6-W0-2 (S6-D54, D58, D59, E13): subruta custody del worker, volumen entero en api y tools,
# tmpfs de web con tope (Nginx guarda ahi los cuerpos de hasta 6m con proxy_request_buffering on) y
# api sin tmpfs de spool (la subida es cuerpo crudo sin archivos temporales).
def sin_subruta(doc, svc):
    m = [v for v in montajes(doc[svc]) if v.get("source") == "keys"]
    return len(m) == 1 and m[0].get("target") == "/run/apex/keys" and not (m[0].get("volume") or {}).get("subpath")

check(not sin_subruta(prod, "api"), "S7-D4: api no monta el volumen keys entero")
check(sin_subruta(prod, "tools"), "S6-D58: tools monta el volumen keys entero (sin subpath) en /run/apex/keys")
check(not sin_subruta(ovl, "api"), "S7-D4: con compose.openbao.yml api no monta keys entero")
check(sin_subruta(ovl, "tools"), "S6-D58: con compose.openbao.yml tools sigue montando keys entero")
# M-4, hallazgo 12: compose.dev.yml no redefine los montajes de keys del api ni del worker, asi
# desarrollo muestra la misma regresion que produccion.
check(keys_de(dev, "api") == keys_de(prod, "api"), f"S7-D4: en desarrollo api monta las mismas subrutas que produccion ({keys_de(dev, 'api')})")
check(keys_de(dev, "worker") == keys_de(prod, "worker"), "S7-D4: en desarrollo worker monta las mismas subrutas que produccion")
check("/run/apex/keys" not in open(os.path.join(os.environ["RAIZ"], "infra", "compose.dev.yml"), encoding="utf-8").read(), "M-4: compose.dev.yml no redefine montajes de keys")
cache_web = [t for t in (web.get("tmpfs") or []) if str(t).split(":")[0] == "/var/cache/nginx"]
check(len(cache_web) == 1 and "size=64m" in str(cache_web[0]).split(":", 1)[-1].split(","), f"E13: tmpfs /var/cache/nginx de web lleva size=64m ({cache_web})")
check(list(prod["api"].get("tmpfs") or []) == ["/tmp"], f"S6-D59: tmpfs del api sin cambios, solo /tmp y sin spool de subida ({prod['api'].get('tmpfs')})")
check(not [v for v in montajes(prod["worker"]) if v.get("source") == "keys" and (v.get("volume") or {}).get("subpath") not in ("custody", "sign")], "S7-D4: ningun montaje de keys del worker fuera de custody y sign (nada del JWT visible al worker)")
check("subpath: custody" in texto and "subpath: sign" in texto and "subpath: jwt" in texto, "S7-D4: compose.yml declara las subrutas custody, sign y jwt")


# --- Rojo S6-W0-4 (S6-D63, D64, D77, D82; M-7 a..e, L-6, E9, E13, M2) -------------------------------
tls_prof_doc = json.loads(os.environ["TLS_PROF"])
tls_prof = tls_prof_doc.get("services", {})
tls_ovl = json.loads(os.environ["TLS_OVL"]).get("services", {})
tls_ovl_puertos = json.loads(os.environ["TLS_OVL_PUERTOS"]).get("services", {})
tls_dev = json.loads(os.environ["TLS_DEV"]).get("services", {})
todos = json.loads(os.environ["TODOS_PERFILES"]).get("services", {})
real_ip_fuera = json.loads(os.environ["REAL_IP_FUERA"]).get("services", {})
caddy_ip_ensayo = json.loads(os.environ["CADDY_IP_ENSAYO"]).get("services", {})
CADDY_REF = "caddy:2.11.3@sha256:ec18ee54aab3315c22e25f3b2babda73ff8007d39b13b3bd1bfffa2f0444c7d9"
CINCO_CADDY = {"APEX_DOMAIN", "APEX_TLS_ISSUER", "APEX_ACME_EMAIL", "APEX_ACME_CA", "APEX_HSTS_MAX_AGE"}


def publicados(svc):
    return sorted((str(p.get("host_ip") or ""), str(p.get("published")), str(p.get("target"))) for p in (svc.get("ports") or []))


# Sin el perfil tls, caddy no existe en ninguna vista (produccion ni desarrollo).
check("caddy" not in prod and "caddy" not in dev, "S6-D64: sin el perfil tls no existe el servicio caddy (produccion ni desarrollo)")
caddy = tls_prof.get("caddy", {})
check(bool(caddy), "S6-D64: con --profile tls compose.yml define el servicio caddy")
check(caddy.get("profiles") == ["tls"], f"S6-D64: caddy con profiles [tls] ({caddy.get('profiles')})")
check(caddy.get("image") == CADDY_REF, f"S6-D64: caddy por digest {CADDY_REF} ({caddy.get('image')})")
check(caddy.get("read_only") is True, "S6-D64: caddy con read_only")
check(caddy.get("cap_drop") == ["ALL"], f"S6-D64: caddy con cap_drop ALL ({caddy.get('cap_drop')})")
check(caddy.get("cap_add") == ["NET_BIND_SERVICE"], f"S6-D64: caddy con cap_add solo NET_BIND_SERVICE ({caddy.get('cap_add')})")
check("no-new-privileges:true" in (caddy.get("security_opt") or []), f"S6-D64: caddy con no-new-privileges ({caddy.get('security_opt')})")
caddy_ip_txt = (((caddy.get("networks") or {}).get("default") or {}).get("ipv4_address")) or ""
check(caddy_ip_txt == "172.30.0.11", f"S6-D64: caddy con ipv4_address 172.30.0.11 por omision ({caddy_ip_txt or 'sin IP'})")
if caddy_ip_txt and subred_txt and rango_txt:
    cip = ipaddress.ip_address(caddy_ip_txt)
    check(cip in ipaddress.ip_network(subred_txt) and cip not in ipaddress.ip_network(rango_txt) and caddy_ip_txt != web_ip_txt, "S6-D64: la IP de caddy cae en la subred, fuera del ip_range dinamico y distinta de web")
else:
    check(False, "S6-D64: IP de caddy, subred y ip_range definidos")
ip_ensayo = (((caddy_ip_ensayo.get("caddy") or {}).get("networks") or {}).get("default") or {}).get("ipv4_address")
check(ip_ensayo == "172.31.2.11", f"S6-D64: APEX_CADDY_IP=172.31.2.11 la sigue caddy ({ip_ensayo})")
cmont = {v.get("target"): v for v in montajes(caddy)}
check((cmont.get("/data") or {}).get("source") == "caddy_data" and (cmont.get("/config") or {}).get("source") == "caddy_config", f"S6-D64: caddy monta caddy_data en /data y caddy_config en /config ({sorted(cmont)})")
cf_mont = cmont.get("/etc/caddy/Caddyfile") or {}
check(cf_mont.get("read_only") is True and fuente(cf_mont).endswith("infra/caddy/Caddyfile"), f"S6-D64: caddy monta infra/caddy/Caddyfile en solo lectura ({fuente(cf_mont)})")
check({"caddy_data", "caddy_config"} <= set(tls_prof_doc.get("volumes", {})), "S6-D64: volumenes caddy_data y caddy_config en uso con el perfil tls")
check(all(f"\n  {v}:" in texto for v in ("caddy_data", "caddy_config")), "S6-D64: compose.yml declara los volumenes caddy_data y caddy_config (lista literal)")
check((depende(tls_prof, "caddy").get("web")) == "service_healthy", f"S6-D64: caddy depende de web healthy ({depende(tls_prof, 'caddy')})")
env_caddy = entorno_de(tls_prof, "caddy")
check(set(env_caddy) == CINCO_CADDY, f"S6-D64: environment de caddy = exactamente las cinco variables ({sorted(env_caddy)})")
check("env_file" not in tls_prof.get("caddy", {}), "S6-D64: caddy sin env_file")
check(not (caddy.get("ports") or []), f"S6-D64: sin el overlay compose.tls.yml caddy no publica puertos ({publicados(caddy)})")
hc_caddy = " ".join(str(x) for x in ((caddy.get("healthcheck") or {}).get("test") or []))
check("wget" in hc_caddy and "http://127.0.0.1/_caddy_health" in hc_caddy, f"S6-D64/E8: healthcheck de caddy con wget a http://127.0.0.1/_caddy_health ({hc_caddy})")
check("2019" not in json.dumps(tls_prof.get("caddy", {})), "S6-D64: caddy sin puerto 2019 (admin off)")
check(not any(k in env_otro for svc, doc in tls_prof.items() if svc not in ("caddy",) for env_otro in [entorno_de(tls_prof, svc)] for k in ("APEX_TLS_ISSUER", "APEX_ACME_EMAIL", "APEX_ACME_CA", "APEX_HSTS_MAX_AGE", "TLS_PORT")), "S6-D65: las variables de Caddy solo en caddy (ningun otro servicio)")
check("APEX_CADDY_IP" in ent("web") or "APEX_CADDY_IP" in entorno_de(tls_prof, "web"), "S6-D64: web recibe APEX_CADDY_IP en su environment (paso 28)")
check(not any("APEX_CADDY_IP" in entorno_de(tls_prof, s) for s in tls_prof if s not in ("web", "caddy")), "S6-D65: APEX_CADDY_IP solo en web (y caddy)")

# compose.tls.yml: caddy publica 80 y 443; web ya no publica nada. Sin el overlay, web publica ${WEB_PORT:-80}:80.
check(publicados(prod["web"]) == [("", "80", "80")], f"S6-D64: sin overlay web publica WEB_PORT:80 ({publicados(prod['web'])})")
check(bool(tls_ovl.get("caddy")), "S6-D64: compose.tls.yml existe y apila el servicio caddy")
check(publicados(tls_ovl.get("caddy", {})) == [("", "443", "443"), ("", "80", "80")], f"S6-D64: con compose.tls.yml caddy publica 80 y 443 y nada mas ({publicados(tls_ovl.get('caddy', {}))})")
check("ports" not in tls_ovl.get("web", {"ports": 1}), "S6-D64: con compose.tls.yml web queda sin puertos (ports: !override [])")
check(publicados(tls_ovl_puertos.get("caddy", {})) == [("", "8280", "80"), ("", "8443", "8443")], f"S6-D64: WEB_PORT y TLS_PORT mueven los puertos de caddy ({publicados(tls_ovl_puertos.get('caddy', {}))})")
check(bool(tls_ovl_puertos) and "ports" not in tls_ovl_puertos.get("web", {"ports": 1}), "S6-D64: con otros puertos web sigue sin publicar")

# compose.dev.yml: perfil tls con el dominio y el emisor de desarrollo; web conserva su puerto.
dcaddy = tls_dev.get("caddy", {})
check(bool(dcaddy) and dcaddy.get("profiles") == ["tls"], f"S6-D48: compose.dev.yml deja caddy bajo el perfil tls ({dcaddy.get('profiles')})")
env_dcaddy = entorno_de(tls_dev, "caddy")
check(env_dcaddy.get("APEX_DOMAIN") == "apex.localhost:8443" and env_dcaddy.get("APEX_TLS_ISSUER") == "internal", f"S6-D48/D77: desarrollo con APEX_DOMAIN=apex.localhost:8443 y APEX_TLS_ISSUER=internal ({env_dcaddy.get('APEX_DOMAIN')} / {env_dcaddy.get('APEX_TLS_ISSUER')})")
check(publicados(dcaddy) == [("127.0.0.1", "8443", "8443")], f"S6-D48: desarrollo publica solo 127.0.0.1:8443:8443 ({publicados(dcaddy)})")
check(publicados(tls_dev.get("web", {})) == [("", "8180", "80")], f"S6-D48: en desarrollo web conserva su puerto ({publicados(tls_dev.get('web', {}))})")

# cap_drop: [ALL] en los once servicios (E9, M2, L-6), db con las cinco capacidades de Postgres, nunca NET_RAW.
ONCE = {"db", "migrate", "dbsetup", "api", "worker", "tools", "backup", "openbao", "openbao-bootstrap", "web", "caddy"}
check(set(todos) == ONCE, f"M-7c: compose.yml (todos los perfiles) define exactamente los once servicios ({sorted(todos)})")
sin_drop = sorted(s for s in ONCE if (todos.get(s) or {}).get("cap_drop") != ["ALL"])
check(not sin_drop, f"M-7c/L-6: cap_drop [ALL] en los once servicios (sin el: {sin_drop or 'ninguno'})")
check(sorted((todos.get("db") or {}).get("cap_add") or []) == ["CHOWN", "DAC_OVERRIDE", "FOWNER", "SETGID", "SETUID"], f"E9: db con cap_drop ALL y cap_add CHOWN, DAC_OVERRIDE, FOWNER, SETGID, SETUID ({(todos.get('db') or {}).get('cap_add')})")
check(not [s for s, d in todos.items() if "NET_RAW" in (d.get("cap_add") or [])], "M-7c: ningun servicio con NET_RAW")
check((todos.get("web") or {}).get("cap_add") is not None and sorted((todos.get("web") or {}).get("cap_add") or []) == ["CHOWN", "NET_BIND_SERVICE", "SETGID", "SETUID"], "M-7c: web conserva sus cuatro capacidades")

# real-ip.conf: bind de un solo archivo que gana al horneado (D82); la variable lo saca del arbol.
def real_ip(svcs):
    return [v for v in montajes(svcs.get("web", {})) if v.get("target") == "/etc/nginx/snippets/real-ip.conf"]


m_ri = real_ip(prod)
check(len(m_ri) == 1 and m_ri[0].get("read_only") is True and m_ri[0].get("type") == "bind" and fuente(m_ri[0]).endswith("infra/nginx/snippets/real-ip.conf"), f"S6-D82: web monta infra/nginx/snippets/real-ip.conf en /etc/nginx/snippets/real-ip.conf:ro ({[(fuente(v), v.get('read_only')) for v in m_ri]})")
m_ri2 = real_ip(real_ip_fuera)
check(len(m_ri2) == 1 and fuente(m_ri2[0]).endswith("apex-real-ip/real-ip.conf") and m_ri2[0].get("read_only") is True, f"S6-D82: APEX_REAL_IP_CONF mueve el origen del bind fuera del arbol ({[fuente(v) for v in m_ri2]})")
check("${APEX_REAL_IP_CONF:-./nginx/snippets/real-ip.conf}:/etc/nginx/snippets/real-ip.conf:ro" in texto, "S6-D82: compose.yml monta ${APEX_REAL_IP_CONF:-./nginx/snippets/real-ip.conf}:/etc/nginx/snippets/real-ip.conf:ro")
check(re.search(r"(?m)^#?\s*APEX_REAL_IP_CONF=\s*$", os.environ["OPS_EJEMPLO_TEXTO"]) is not None, ".env.ops.example documenta APEX_REAL_IP_CONF vacia por omision (S6-D82)")
check("APEX_REAL_IP_CONF" not in ejemplo, "S6-D82: APEX_REAL_IP_CONF no esta en .env.example (la lee solo Compose)")

# D79 (ya desde W0-5): el api no lleva --workers ni UVICORN_WORKERS.
cmd_api = " ".join(str(x) for x in (prod["api"].get("command") or []))
check("--workers" not in cmd_api and "UVICORN_WORKERS" not in texto and "UVICORN_WORKERS" not in json.dumps(prod["api"]), f"S6-D79: api sin command con --workers y sin UVICORN_WORKERS ({cmd_api or 'sin command'})")
check(not any(t == "2019" for _, _, t in publicados(tls_ovl.get("caddy", {}))), "S6-D64: nunca se publica el 2019 de caddy")

print(f"test_compose_config: {len(fallas)} fallas")
sys.exit(1 if fallas else 0)
EOF
