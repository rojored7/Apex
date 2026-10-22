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
permite .env.seed.example
permite docs/README.md

echo "test_check_key_files: $fallas fallas"
[ "$fallas" -eq 0 ]
