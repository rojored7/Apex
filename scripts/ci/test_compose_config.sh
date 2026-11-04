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
OVL_YML="$(cat infra/compose.openbao.yml 2>/dev/null || true)"
COMPOSE_VERSION="$(docker compose version --short 2>/dev/null | tr -d '\r' || true)"
IGNORA_SEED="$(git check-ignore -q .env.seed && echo si || echo no)"
IGNORA_SEED_EJEMPLO="$(git check-ignore -q .env.seed.example && echo si || echo no)"
IGNORA_OPS="$(git check-ignore -q .env.ops && echo si || echo no)"
IGNORA_OPS_EJEMPLO="$(git check-ignore -q .env.ops.example && echo si || echo no)"

SU="$SU" BOOT="$BOOT" OVL="$OVL" DEV_OB="$DEV_OB" OVL_YML="$OVL_YML" DEV_INIT="$DEV_INIT" DEV_QUIET="$DEV_QUIET" PROD_SIN_OPS="$PROD_SIN_OPS" PROD_RED="$PROD_RED" RUNBOOK_NO_DEPS="$RUNBOOK_NO_DEPS" VERIFY="$VERIFY" PROD="$PROD" DEV="$DEV" DEV_PERFILES="$DEV_PERFILES" E2E="$E2E" COMPOSE_YML="$COMPOSE_YML" CRUDO="$CRUDO" COMPOSE_VERSION="$COMPOSE_VERSION" IGNORA_SEED="$IGNORA_SEED" IGNORA_SEED_EJEMPLO="$IGNORA_SEED_EJEMPLO" IGNORA_OPS="$IGNORA_OPS" IGNORA_OPS_EJEMPLO="$IGNORA_OPS_EJEMPLO" RAIZ="$ROOT" uv run --directory api --quiet python - <<'EOF'
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
keys_api = [v for v in prod["api"].get("volumes", []) if v.get("target") == "/run/apex/keys"]
check(bool(keys_api) and keys_api[0].get("read_only") is True, "api monta keys en solo lectura")
# S4A-W0-1 (S4A-D49, M-5): en 4A el worker no cifra ni descifra; el Sprint 5 vuelve a montar keys:ro.
destinos_worker = {v.get("target") for v in prod["worker"].get("volumes", []) or []}
check(not ({"/run/apex/keys", "/data/uploads"} & destinos_worker), "worker no monta keys ni uploads hasta el Sprint 5")
tools = [v for v in prod["tools"].get("volumes", []) if v.get("target") == "/run/apex/keys"]
check(bool(tools) and not tools[0].get("read_only"), "tools monta keys con escritura")
check(prod["api"]["image"] == prod["worker"]["image"] == prod["tools"]["image"], "api, worker y tools usan la misma imagen")
check("profiles" not in prod["worker"], "worker sin perfil desde S4A-W0-2")
check("db_test" not in prod, "db_test no existe en compose.yml")
# S5-W0-2: se suman el volumen raft de OpenBao y un volumen de token por servicio (S5-D11).
VOLS_OB = ("openbao-data", "openbao-token-api", "openbao-token-worker", "openbao-token-tools")
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
    set(mont) == {"/data/backups", "/data/uploads", "/run/apex/backup/sign.key"},
    f"backup monta exactamente backups, uploads y la llave de firma ({sorted(mont)})",
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
check(mont_api.get("/run/apex/keys", {}).get("read_only") is True, "api: keys en solo lectura")
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
# S5-W0-2 (S5-D11): a backups:ro se suma SOLO su token de OpenBao, tambien :ro (la asercion original exigia un unico montaje).
check(
    sorted((m.get("source"), m.get("target"), m.get("read_only")) for m in mont_w)
    == [("backups", "/data/backups", True), ("openbao-token-worker", "/run/apex/openbao", True)],
    f"worker monta exactamente backups en /data/backups y su token en /run/apex/openbao, ambos de solo lectura ({[(m.get('source'), m.get('target')) for m in mont_w]})",
)

# web (S4B-D11, D75).
web = prod["web"]
check(depende(prod, "web") == {"api": "service_healthy"}, f"web depende de api healthy ({depende(prod, 'web')})")
check(web.get("read_only") is True and web.get("cap_drop") == ["ALL"] and "no-new-privileges:true" in (web.get("security_opt") or []), "web con read_only, cap_drop ALL y no-new-privileges")
check(set(web.get("tmpfs") or []) >= {"/var/cache/nginx", "/var/run", "/tmp"}, f"web con tmpfs /var/cache/nginx, /var/run y /tmp ({web.get('tmpfs')})")
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
    prohibidas = [k for k in env if k.endswith("_DB_PASSWORD") or k.startswith(("RCLONE_", "BACKUP_AGE_", "BACKUP_SIGN_"))]
    check(not prohibidas, f"{svc} sin *_DB_PASSWORD, RCLONE_*, BACKUP_AGE_* ni BACKUP_SIGN_* ({prohibidas or 'ninguna'})")
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
check({"openbao-token-api", "openbao-token-worker", "openbao-token-tools"} <= fuentes_boot, f"S5: openbao-bootstrap escribe los tres volumenes de token ({sorted(fuentes_boot)})")
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
for svc in ("web", "db", "backup"):
    check("custody" not in redes_de(prod, svc), f"S5: {svc} fuera de la red custody ({sorted(redes_de(prod, svc))})")
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

# compose.openbao.yml (S5-D74): api y worker sin keys; con su token; tools conserva keys.
ovl_doc = json.loads(os.environ["OVL"])
ovl = ovl_doc.get("services", {})
check(bool(ovl.get("api")) and bool(ovl.get("worker")), "S5: el overlay renderiza con api y worker")
for svc in ("api", "worker"):
    check("/run/apex/keys" not in {v.get("target") for v in montajes(ovl.get(svc, {}))} and bool(ovl.get(svc)), f"S5: con compose.openbao.yml {svc} no monta keys")
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

print(f"test_compose_config: {len(fallas)} fallas")
sys.exit(1 if fallas else 0)
EOF
