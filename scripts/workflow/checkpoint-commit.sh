#!/usr/bin/env bash
# checkpoint-commit.sh "<mensaje>"
#
# Confirma el slice como `chore(checkpoint): <mensaje>` solo si slice-gate.sh pasó
# sobre el estado actual del árbol (sello .git/apex/slice-gate.ok con la misma
# huella). Nunca sobre main. Nunca empuja al remoto: eso lo hace una persona (A-02).
set -euo pipefail

usage() {
  cat <<'EOF'
Uso: checkpoint-commit.sh "<mensaje>"

Crea el commit `chore(checkpoint): <mensaje>` con `git add -A` si:
  - la rama actual no es main;
  - existe .git/apex/slice-gate.ok, escrito por slice-gate.sh;
  - la huella del árbol de trabajo coincide con la del sello (nada cambió después del gate).
Borra el sello al terminar. No hace push.
Si CHECKPOINT_TRAILER está definida, su texto va como segundo párrafo del mensaje
(por ejemplo, una línea Co-Authored-By).
EOF
}

case "${1:-}" in
  -h|--help) usage; exit 0 ;;
  "") usage >&2; exit 2 ;;
esac
MENSAJE="$1"

ROOT="$(git rev-parse --show-toplevel)"
GIT_DIR="$(git rev-parse --absolute-git-dir)"
SELLO="$GIT_DIR/apex/slice-gate.ok"

fallo() { echo "checkpoint-commit: $*" >&2; exit 1; }

RAMA="$(git rev-parse --abbrev-ref HEAD)"
[ "$RAMA" != "main" ] || fallo "no se hacen checkpoints sobre main; crea una rama feat/, fix/ o chore/"
[ -f "$SELLO" ] || fallo "no hay sello: corre scripts/workflow/slice-gate.sh primero"

huella() {
  (
    cd "$ROOT"
    {
      git diff HEAD --
      git ls-files --others --exclude-standard | sort | while IFS= read -r f; do
        printf '%s %s\n' "$f" "$(git hash-object -- "$f")"
      done
    } | git hash-object --stdin
  )
}

SELLADA="$(grep '^huella=' "$SELLO" | cut -d= -f2)"
MODULO="$(grep '^modulo=' "$SELLO" | cut -d= -f2)"
ACTUAL="$(huella)"
[ "$SELLADA" = "$ACTUAL" ] || fallo "el árbol cambió después del gate de '$MODULO'; vuelve a correr slice-gate.sh"

cd "$ROOT"
git add -A
if [ -n "${CHECKPOINT_TRAILER:-}" ]; then
  git commit -q -m "chore(checkpoint): $MENSAJE" -m "$CHECKPOINT_TRAILER"
else
  git commit -q -m "chore(checkpoint): $MENSAJE"
fi
rm -f "$SELLO"
echo "checkpoint-commit: $(git rev-parse --short HEAD) chore(checkpoint): $MENSAJE"
