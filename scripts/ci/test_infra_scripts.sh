#!/usr/bin/env bash
# test_infra_scripts.sh
#
# Envoltorio de las pruebas de shell de infra/backup (S4B-W0-1, S4B-D19) y, desde S4B-B4, de
# scripts/ci/test_deploy_script.sh y scripts/ci/test_check_release_version.sh. Bash puro: sin
# bats ni shellcheck.
# S4B-B3a: infra/backup/tests/run.sh recorre test_*.sh, así que incluye test_restore_guard.sh
# (psql, pg_restore, age y minisign falsos en el host; los reales en la CI). Esta comprobación
# explícita evita que un renombrado lo saque del envoltorio sin que nadie lo note.
# S4B-B4: test_deploy_script.sh usa los falsos de scripts/ci/fakes (docker, git, curl, sleep, stat);
# infra/tests/deploy_e2e.sh y scripts/ci/prod-smoke.sh NO corren aquí (solo apex-smoke y la CI).
# Rojo S6-W0-4: bash -n y --dry-run de scripts/ci/tls-smoke.sh (bloque al final).
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
fallas=0
if [ ! -f infra/backup/tests/test_restore_guard.sh ]; then
  echo "test_infra_scripts: falta infra/backup/tests/test_restore_guard.sh" >&2
  fallas=$((fallas + 1))
fi
# S5-B13: test_snapshot.sh (instantánea raft de OpenBao en el respaldo) también debe seguir aquí.
if [ ! -f infra/backup/tests/test_snapshot.sh ]; then
  echo "test_infra_scripts: falta infra/backup/tests/test_snapshot.sh" >&2
  fallas=$((fallas + 1))
fi
bash infra/backup/tests/run.sh || fallas=$((fallas + 1))
for prueba in test_deploy_script test_check_release_version; do
  if [ -f "scripts/ci/$prueba.sh" ]; then
    bash "scripts/ci/$prueba.sh" || fallas=$((fallas + 1))
  else
    echo "test_infra_scripts: falta scripts/ci/$prueba.sh" >&2
    fallas=$((fallas + 1))
  fi
done

# Rojo S6-W0-4 (S6-D63, D82, D83; P-TLS): scripts/ci/tls-smoke.sh. Aquí solo se prueba lo que no necesita
# levantar nada: sintaxis, uso, `--dry-run` (renderiza `docker compose config` con y sin el perfil tls y
# lista las comprobaciones) y lo estático. La ejecución real corre en el ensayo ($DCET), en prod-smoke
# --tls y en el job `images` de la CI. Nota (paso 26): la línea que prueba el intercambio es
# `Negotiated TLS1.3 group: X25519MLKEM768`; el `grep -cE '^ *-groups '` = 1 (D83) comprueba que la ayuda
# de `openssl s_client` en alpine:3.22 lista la opción `-groups` (coincide también -srp_moregroups).
TLS_SMOKE=scripts/ci/tls-smoke.sh
tls_falla() { echo "test_infra_scripts: $1" >&2; fallas=$((fallas + 1)); }
tls_ok() { echo "  ok   $1"; }
if [ -f "$TLS_SMOKE" ]; then
  if bash -n "$TLS_SMOKE"; then tls_ok "tls-smoke.sh pasa bash -n"; else tls_falla "tls-smoke.sh no pasa bash -n"; fi
  rc=0; bash "$TLS_SMOKE" --help > /dev/null 2>&1 || rc=$?
  [ "$rc" = "0" ] && tls_ok "tls-smoke.sh --help sale con 0" || tls_falla "tls-smoke.sh --help sale con $rc (se esperaba 0)"
  rc=0; bash "$TLS_SMOKE" --opcion-rara > /dev/null 2>&1 || rc=$?
  [ "$rc" = "2" ] && tls_ok "tls-smoke.sh con una opción desconocida sale con 2" || tls_falla "tls-smoke.sh con una opción desconocida sale con $rc (se esperaba 2)"
  rc=0; bash "$TLS_SMOKE" --dc > /dev/null 2>&1 || rc=$?
  [ "$rc" = "2" ] && tls_ok "tls-smoke.sh --dc sin valor sale con 2" || tls_falla "tls-smoke.sh --dc sin valor sale con $rc (se esperaba 2)"
  rc=0; dry="$(bash "$TLS_SMOKE" --dry-run 2>&1 | tr -d '\r')" || rc=$?
  [ "$rc" = "0" ] && tls_ok "tls-smoke.sh --dry-run sale con 0" || tls_falla "tls-smoke.sh --dry-run sale con $rc (se esperaba 0)"
  dry_tiene() { # descripcion regex ERE
    if grep -Eq -- "$2" <<< "$dry"; then tls_ok "--dry-run lista: $1"; else tls_falla "--dry-run no lista: $1 (patrón $2)"; fi
  }
  dry_tiene "el intercambio híbrido (Negotiated TLS1.3 group: X25519MLKEM768)" 'Negotiated TLS1\.3 group: X25519MLKEM768'
  dry_tiene "la caída a X25519" 'Negotiated TLS1\.3 group: X25519( |$|[^M])'
  dry_tiene "la comprobación de -groups (grep -cE '^ *-groups ' = 1, D83)" "grep -cE '\\^ \\*-groups '"
  dry_tiene "TLS 1.1 rechazado" 'tls1_1'
  dry_tiene "TLS 1.2 aceptado" 'tls1_2'
  dry_tiene "el 308 de /login con Location https://apex.localhost" '308.*apex\.localhost'
  dry_tiene "que /.well-known/acme-challenge/x no responde 308 (M1)" 'acme-challenge'
  dry_tiene "/_caddy_health por HTTP (E8)" '_caddy_health'
  dry_tiene "HSTS max-age=300 y su ausencia con --lan" 'Strict-Transport-Security.*max-age=300'
  dry_tiene "la cookie con Secure" 'Secure'
  dry_tiene "el limitador por IP real con dos clientes (S6-D29)" '[Ll]imitador.*(IP real|dos clientes)'
  dry_tiene "el render sin perfil tls (caddy ausente)" 'render sin perfil tls:.*caddy ausente'
  dry_tiene "el render con perfil tls (caddy presente, web sin puertos)" 'render con perfil tls:.*caddy presente.*web sin puertos'
  rc=0; dry_lan="$(bash "$TLS_SMOKE" --lan --dry-run 2>&1 | tr -d '\r')" || rc=$?
  [ "$rc" = "0" ] && tls_ok "tls-smoke.sh --lan --dry-run sale con 0" || tls_falla "tls-smoke.sh --lan --dry-run sale con $rc (se esperaba 0)"
  if grep -qi 'lan' <<< "$dry_lan"; then tls_ok "--lan --dry-run nombra el modo LAN"; else tls_falla "--lan --dry-run no nombra el modo LAN"; fi
  rc=0; bash "$TLS_SMOKE" --dc "docker compose -p apex-prueba-tls" --dry-run > /dev/null 2>&1 || rc=$?
  [ "$rc" = "0" ] && tls_ok "tls-smoke.sh acepta --dc con --dry-run" || tls_falla "tls-smoke.sh --dc ... --dry-run sale con $rc (se esperaba 0)"
  # Estático: la línea de negociación y la ayuda de -groups están en el script; nadie escribe dentro de infra/;
  # ningún proyecto fijo (apex, apex-ensayo) y los temporales propios con mktemp -d (S6-D82).
  est() { # descripcion regex-que-debe-estar
    if grep -Eq -- "$2" "$TLS_SMOKE"; then tls_ok "tls-smoke.sh: $1"; else tls_falla "tls-smoke.sh no tiene: $1 (patrón $2)"; fi
  }
  est "cuenta Negotiated TLS1.3 group: X25519MLKEM768" 'Negotiated TLS1\.3 group: X25519MLKEM768'
  est "cuenta la ayuda con grep -cE '^ *-groups '" "grep -cE '\\^ \\*-groups '"
  est "usa mktemp -d para sus temporales" 'mktemp -d'
  est "renderiza el overlay compose.tls.yml" 'compose\.tls\.yml'
  est "usa la CA interna del volumen de Caddy (root.crt)" 'root\.crt'
  if grep -nE '(>|tee)[[:space:]]+"?(\$ROOT/|\./)?infra/' "$TLS_SMOKE" > /dev/null; then tls_falla "tls-smoke.sh escribe dentro de infra/ (S6-D82)"; else tls_ok "tls-smoke.sh no escribe dentro de infra/"; fi
  if grep -nE '(-p|--project-name)[ =]"?apex(-ensayo)?"?([[:space:]]|$)' "$TLS_SMOKE" > /dev/null; then tls_falla "tls-smoke.sh fija los proyectos apex o apex-ensayo"; else tls_ok "tls-smoke.sh no fija los proyectos apex ni apex-ensayo"; fi
else
  tls_falla "falta scripts/ci/tls-smoke.sh"
fi
echo "test_infra_scripts: $fallas fallas"
[ "$fallas" -eq 0 ]
