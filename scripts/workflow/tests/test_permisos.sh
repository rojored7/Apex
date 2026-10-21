#!/usr/bin/env bash
# Prueba de arquitectura de los scripts (US-008, T7): modo 100755 en git,
# sintaxis válida y ningún push desde los scripts.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

echo "test_permisos"
SCRIPTS=(slice-gate.sh checkpoint-commit.sh run-gates.sh validate-impact-analysis.sh)
cd "$REPO_ROOT"
for s in "${SCRIPTS[@]}"; do
  ruta="scripts/workflow/$s"
  assert_file_exists "$ruta"
  modo="$("$REAL_GIT" ls-files -s "$ruta" | cut -d' ' -f1)"
  if [ "$modo" = "100755" ]; then _ok "$s en modo 100755"; else _fail "$s en modo '${modo:-sin seguimiento}'"; fi
  assert_exit 0 "$s pasa bash -n" bash -n "$ruta"
  if grep -Eq 'git (push|.*--force|.*--no-verify|.*reset --hard)' "$ruta"; then _fail "$s contiene push, --force, --no-verify o reset --hard"; else _ok "$s sin push ni operaciones destructivas"; fi
  if head -1 "$ruta" | grep -q '^#!/usr/bin/env bash'; then _ok "$s con shebang"; else _fail "$s sin shebang"; fi
  if grep -q 'set -euo pipefail' "$ruta"; then _ok "$s con set -euo pipefail"; else _fail "$s sin set -euo pipefail"; fi
done

finish
