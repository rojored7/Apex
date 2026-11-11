#!/usr/bin/env bash
# test_check_key_files.sh
#
# Casos de scripts/ci/check-key-files.sh (US-039; S2-W0-1, E2): bloquea .env, .env.seed y
# cualquier .env.*; permite .env.example y .env.seed.example. Pasa los nombres como
# argumentos (el modo pre-commit), así que no toca el índice de git.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
SCRIPT="$ROOT/scripts/ci/check-key-files.sh"
fallas=0
ok() { echo "  ok   $1"; }
falla() { echo "  FALLA $1"; fallas=$((fallas + 1)); }

bloquea() { if bash "$SCRIPT" "$1" > /dev/null 2>&1; then falla "deja pasar $1"; else ok "bloquea $1"; fi; }
permite() { if bash "$SCRIPT" "$1" > /dev/null 2>&1; then ok "permite $1"; else falla "bloquea $1 (debe permitirlo)"; fi; }

bloquea .env
bloquea .env.seed
bloquea infra/.env.seed
bloquea .env.local
bloquea kek.bin
bloquea jwt_ed25519.pem
permite .env.example
permite .env.ops.example
bloquea .env.ops
bloquea infra/.env.ops
bloquea backup-sign.key
bloquea backup-verify-identity.txt
bloquea age-identity.txt
bloquea rclone.conf
bloquea apex-20261021-070005-db.dump.age
permite infra/backup/manifest.schema.json
permite .env.seed.example
permite docs/README.md

# --- Rojo S6-W0-2 (S6-D58, S5-D201): modo `--layout <dir> [--provider local|openbao] [--only custody|all]`
# Comprueba el contenido de un volumen `keys`: custody/kek.bin, custody/sign-ed25519.key y
# jwt/jwt_ed25519.{pem,pub}, todos con modo 600 y dueño 10001 (stat -c %a / %u). Un layout plano
# o mixto es error con «corra init-keys --migrate-layout». `--only custody` es la vista del worker
# (solo custody; si ve jwt/ es un error: nada del JWT visible al worker). Con `--provider openbao`
# no se exige custody. Los modos y el dueño salen del `stat` falso de scripts/ci/fakes (Git Bash
# en Windows no guarda modos POSIX).
FAKEBIN="$(mktemp -d)"
LAYOUT_TMP="$(mktemp -d)"
trap 'rm -rf "$FAKEBIN" "$LAYOUT_TMP"' EXIT
cp "$ROOT/scripts/ci/fakes/stat" "$FAKEBIN/stat"
chmod +x "$FAKEBIN/stat"
n_layout=0
nuevo_layout() { # <custody|jwt|ambos|plano|mixto>: arma un volumen de prueba y deja su ruta en $V
  n_layout=$((n_layout + 1))
  V="$LAYOUT_TMP/v$n_layout"
  mkdir -p "$V"
  case "$1" in
    ambos | custody) mkdir -p "$V/custody"; : > "$V/custody/kek.bin"; : > "$V/custody/sign-ed25519.key" ;;
  esac
  case "$1" in
    ambos | jwt) mkdir -p "$V/jwt"; : > "$V/jwt/jwt_ed25519.pem"; : > "$V/jwt/jwt_ed25519.pub" ;;
  esac
  case "$1" in
    plano | mixto) : > "$V/kek.bin"; : > "$V/sign-ed25519.key"; : > "$V/jwt_ed25519.pem"; : > "$V/jwt_ed25519.pub" ;;
  esac
  [ "$1" != "mixto" ] || { mkdir -p "$V/custody"; : > "$V/custody/kek.bin"; }
}
layout() { # <descripcion> <rc esperado> <texto esperado o ""> <VAR=valor...> -- <argumentos>
  local desc="$1" esperado="$2" texto="$3"; shift 3
  local extra=()
  while [ "$#" -gt 0 ] && [ "$1" != "--" ]; do extra+=("$1"); shift; done
  [ "$#" -gt 0 ] && shift
  local rc=0 salida
  salida="$(env PATH="$FAKEBIN:$PATH" FAKE_STAT_MODE=600 FAKE_STAT_UID=10001 ${extra[@]+"${extra[@]}"} bash "$SCRIPT" "$@" 2>&1)" || rc=$?
  if [ "$rc" != "$esperado" ]; then falla "layout: $desc (salida $rc, se esperaba $esperado)"; return; fi
  if [ -n "$texto" ] && ! grep -Fq -- "$texto" <<< "$salida"; then falla "layout: $desc (la salida no dice '$texto')"; return; fi
  ok "layout: $desc"
}
nuevo_layout ambos;   layout "layout nuevo con modo 600 y dueño 10001 pasa" 0 "" -- --layout "$V"
nuevo_layout plano;   layout "layout plano es error y pide migrar" 1 "init-keys --migrate-layout" -- --layout "$V"
nuevo_layout mixto;   layout "layout mixto es error y pide migrar" 1 "init-keys --migrate-layout" -- --layout "$V"
nuevo_layout custody; layout "sin el par JWT es error y nombra jwt_ed25519.pub" 1 "jwt_ed25519.pub" -- --layout "$V"
nuevo_layout jwt;     layout "sin custody es error y nombra kek.bin" 1 "kek.bin" -- --layout "$V"
nuevo_layout ambos;   layout "modo 644 es error" 1 "644" FAKE_STAT_MODE=644 -- --layout "$V"
nuevo_layout ambos;   layout "dueño distinto de 10001 es error" 1 "10001" FAKE_STAT_UID=1000 -- --layout "$V"
nuevo_layout jwt;     layout "con --provider openbao no se exige custody" 0 "" -- --layout "$V" --provider openbao
nuevo_layout plano;   layout "con --provider openbao el plano sigue siendo error" 1 "init-keys --migrate-layout" -- --layout "$V" --provider openbao
nuevo_layout custody; layout "vista del worker (--only custody) pasa con solo custody/" 0 "" -- --layout "$V" --only custody
nuevo_layout ambos;   layout "vista del worker con jwt/ visible es error" 1 "jwt" -- --layout "$V" --only custody
nuevo_layout jwt;     layout "vista del worker sin custody es error" 1 "kek.bin" -- --layout "$V" --only custody
nuevo_layout ambos;   layout "--only desconocido sale con 2" 2 "" -- --layout "$V" --only otra
layout "--layout de una carpeta inexistente es error y lo dice" 1 "no existe" -- --layout "$LAYOUT_TMP/no-existe"
# El modo por nombre sigue vivo: material de llave versionado se bloquea también en las subcarpetas.
bloquea keys/custody/kek.bin
bloquea keys/custody/sign-ed25519.key
bloquea keys/jwt/jwt_ed25519.pem
bloquea keys/jwt/jwt_ed25519.pub

echo "test_check_key_files: $fallas fallas"
[ "$fallas" -eq 0 ]
