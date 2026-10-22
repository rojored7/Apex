#!/usr/bin/env bash
# check-image-secrets.sh <imagen>
#
# Inspección de secretos en la imagen del api (US-039, T7). Exporta el sistema de archivos
# de la imagen (`docker create` + `docker export`) a un directorio temporal y falla si:
#   1. existe algún `.env` (salvo `.env.example`);
#   2. algún archivo contiene `-----BEGIN ... PRIVATE KEY-----`;
#   3. hay `.pem`, `.key` o `.kek` bajo `app/`.
# Excluye de forma explícita el parser PEM de cryptography (contiene la cabecera como constante)
# y los certificados públicos de CA (`etc/ssl/certs`,
# `usr/share/ca-certificates`, `**/certifi/cacert.pem`): no son secretos.
# Termina con `gitleaks dir` sobre el mismo directorio (imagen oficial, MIT); con
# SKIP_GITLEAKS=1 se omite (por ejemplo sin acceso a Docker Hub).
set -euo pipefail

IMG="${1:?uso: check-image-secrets.sh <imagen>}"
ROOT="$(git rev-parse --show-toplevel)"
fallas=0
ok() { echo "  ok   $1"; }
falla() { echo "  FALLA $1"; fallas=$((fallas + 1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
contenedor="$(docker create "$IMG")"
docker export "$contenedor" | tar -x -C "$TMP" 2>/dev/null || true
docker rm -f "$contenedor" > /dev/null

envs="$(find "$TMP" -xdev \( -name ".env" -o -name ".env.*" \) ! -name ".env.example" 2>/dev/null | sed "s|$TMP||" || true)"
if [ -z "$envs" ]; then ok "sin archivos .env en la imagen"; else falla "archivos .env en la imagen:$envs"; fi

privadas="$(grep -rlsE --exclude-dir=lib -e "-----BEGIN (RSA |EC |OPENSSH |ENCRYPTED |DSA |)PRIVATE KEY-----" "$TMP" 2>/dev/null | grep -vE "etc/ssl/certs|usr/share/ca-certificates|certifi/cacert\.pem|site-packages/cryptography/hazmat/primitives/serialization/" | sed "s|$TMP||" || true)"
if [ -z "$privadas" ]; then ok "ninguna llave privada por contenido"; else falla "llaves privadas por contenido:$privadas"; fi

bajo_app="$(find "$TMP/app" -xdev -path "*/site-packages" -prune -o \( -name "*.pem" -o -name "*.key" -o -name "*.kek" \) -print 2>/dev/null | sed "s|$TMP||" || true)"
if [ -z "$bajo_app" ]; then ok "sin .pem, .key ni .kek bajo /app"; else falla "material de llave bajo /app:$bajo_app"; fi

if [ "${SKIP_GITLEAKS:-0}" = "1" ]; then
  echo "  (gitleaks omitido: SKIP_GITLEAKS=1)"
elif MSYS_NO_PATHCONV=1 docker run --rm -v "$TMP:/scan:ro" -v "$ROOT/.gitleaks.toml:/gitleaks.toml:ro" zricethezav/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f dir /scan --config /gitleaks.toml --no-banner --redact > "$TMP/.gitleaks.log" 2>&1; then
  ok "gitleaks dir sin hallazgos"
else
  falla "gitleaks dir encontró secretos (ver salida)"
  tail -20 "$TMP/.gitleaks.log" || true
fi

echo "check-image-secrets: $fallas fallas"
[ "$fallas" -eq 0 ]
