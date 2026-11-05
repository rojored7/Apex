#!/bin/bash
# Funciones puras del servicio backup (S4B-W0-1; S4B-D15, D17, D68, D97). Se cargan con
# `source`; no ejecutan nada al cargarse. Probadas por infra/backup/tests/test_lib.sh.
# Requiere bash (presente en postgres:16-alpine) y las utilidades de BusyBox o GNU.

# backup_name <prefijo> <epoch> -> <prefijo>-AAAAMMDD-HHMMSS (UTC).
backup_name() {
  printf '%s-%s' "$1" "$(date -u -d "@$2" +%Y%m%d-%H%M%S)"
}

# valid_prefix <prefijo>: apex, pre-deploy o pre-restore (S4B-D97).
valid_prefix() {
  case "${1:-}" in
    apex | pre-deploy | pre-restore) return 0 ;;
    *) return 1 ;;
  esac
}

# retention_to_delete <dias> <ahora_epoch> <ultimo_exitoso>: lee `epoch nombre` por stdin e
# imprime los juegos `apex-*` que se pueden borrar. Nunca el último exitoso, nunca un pre-*
# (se conservan para borrado manual) y nada si quedarían menos de dos juegos (S4B-D68).
retention_to_delete() {
  local dias="$1" ahora="$2" ultimo="$3" limite epoch nombre total=0
  local candidatos=()
  limite=$((ahora - 10#$dias * 86400))
  while read -r epoch nombre; do
    [ -n "${nombre:-}" ] || continue
    case "$nombre" in apex-*) ;; *) continue ;; esac
    total=$((total + 1))
    [ "$nombre" = "$ultimo" ] && continue
    if [ "$epoch" -lt "$limite" ]; then candidatos+=("$nombre"); fi
  done
  if [ $((total - ${#candidatos[@]})) -lt 2 ]; then
    return 0
  fi
  [ "${#candidatos[@]}" -eq 0 ] || printf '%s\n' "${candidatos[@]}"
}

# sanitize_error: filtro stdin -> stdout. Quita URL, claves de acceso, firmas y secretos
# largos de un mensaje de error y lo recorta a 200 caracteres (S4B-D68).
sanitize_error() {
  tr '\r\n' '  ' \
    | sed -E \
      -e 's#https?://[^[:space:]]*#<url>#g' \
      -e 's#(AKIA|ASIA)[0-9A-Z]{12,}#<clave>#g' \
      -e 's#X-Amz-[A-Za-z-]+=[^&[:space:]]*#<firma>#g' \
      -e 's#([Ss]ecret[_A-Za-z]*|[Aa]ccess[_A-Za-z]*|[Tt]oken|[Pp]assword)([=: ]+)[^[:space:]]+#\1\2<oculto>#g' \
      -e 's#[A-Za-z0-9/+]{40,}#<oculto>#g' \
    | cut -c1-200
}

# valid_recipient <valor>: age1 + 58 caracteres bech32 en minúscula (rechaza age1<plugin>1...).
valid_recipient() {
  [[ "${1:-}" =~ ^age1[0-9a-z]{58}$ ]]
}

# valid_keep_days <valor>: entero de 3 a 365.
valid_keep_days() {
  [[ "${1:-}" =~ ^[0-9]{1,3}$ ]] || return 1
  [ "$((10#$1))" -ge 3 ] && [ "$((10#$1))" -le 365 ]
}

# valid_remote <valor>: apex:<ruta> de hasta 200 caracteres en total, sin `..` ni espacios.
valid_remote() {
  local v="${1:-}"
  [[ "$v" =~ ^apex:[A-Za-z0-9._/-]{1,200}$ ]] || return 1
  [ "${#v}" -le 205 ] || return 1
  case "$v" in *..*) return 1 ;; esac
  return 0
}

# json_escape <texto>: escapa \ " y caracteres de control para un valor JSON.
json_escape() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/ }"
  s="${s//$'\r'/ }"
  s="${s//$'\t'/ }"
  printf '%s' "$s"
}

# manifest_json <name> <created_at> <database> <verify> <verified_at> <upload> <upload_error> [snap]
# Los archivos llegan por stdin, uno por línea: kind|name|size_bytes|sha256|plain_sha256.
# `snap` (opcional, S5-B13, S5-D8) es `name|size_bytes|sha256|verified` (`true` o `false`) y agrega
# la entrada `openbao_snapshot`. Imprime el manifiesto (format_version 1, S4B-D80). Sin jq.
manifest_json() {
  local name="$1" created="$2" db="$3" verify="$4" verified_at="$5" upload="$6" upload_error="$7"
  local snap="${8:-}" kind fname size sha plain primero=1 sname ssize ssha sver
  printf '{\n'
  printf '  "format_version": 1,\n'
  printf '  "name": "%s",\n' "$(json_escape "$name")"
  printf '  "created_at": "%s",\n' "$(json_escape "$created")"
  printf '  "database": "%s",\n' "$(json_escape "$db")"
  printf '  "files": [\n'
  while IFS='|' read -r kind fname size sha plain; do
    [ -n "${fname:-}" ] || continue
    [ "$primero" -eq 1 ] || printf ',\n'
    primero=0
    printf '    {"kind": "%s", "name": "%s", "size_bytes": %s, "sha256": "%s", "plain_sha256": "%s"}' \
      "$(json_escape "$kind")" "$(json_escape "$fname")" "$size" "$(json_escape "$sha")" "$(json_escape "$plain")"
  done
  printf '\n  ],\n'
  printf '  "verify": "%s",\n' "$(json_escape "$verify")"
  if [ -n "$verified_at" ]; then
    printf '  "verified_at": "%s",\n' "$(json_escape "$verified_at")"
  else
    printf '  "verified_at": null,\n'
  fi
  printf '  "upload": "%s"' "$(json_escape "$upload")"
  if [ -n "$upload_error" ]; then
    printf ',\n  "upload_error": "%s"' "$(json_escape "$upload_error")"
  fi
  if [ -n "$snap" ]; then
    IFS='|' read -r sname ssize ssha sver <<< "$snap"
    [ "$sver" = true ] || sver=false
    printf ',\n  "openbao_snapshot": {"name": "%s", "size_bytes": %s, "sha256": "%s", "verified": %s}' \
      "$(json_escape "$sname")" "$ssize" "$(json_escape "$ssha")" "$sver"
  fi
  printf '\n}\n'
}

# snapshot_curl_config <archivo-token> <url>: imprime el archivo de configuración de `curl -K` que
# pide la instantánea raft de OpenBao (S5-B13, L-2). El token entra por ese archivo (en /tmp, modo
# 600) y NUNCA por el argv, donde `ps` lo vería. Rechaza (código 1, sin salida) un token vacío o con
# caracteres fuera de [A-Za-z0-9._~+/=-] (comillas, barras invertidas y saltos de línea cerrarían el
# valor y permitirían inyectar directivas) y toda URL que no sea
# http://<host>[:<puerto>]/v1/sys/storage/raft/snapshot[-force] (la restauración en un clúster NUEVO exige -force: S5-D172). El salto de línea final se recorta.
snapshot_curl_config() {
  local tokfile="${1:-}" url="${2:-}" token
  [ -f "$tokfile" ] && [ -r "$tokfile" ] || return 1
  [[ "$url" =~ ^http://[A-Za-z0-9.-]+(:[0-9]{1,5})?/v1/sys/storage/raft/snapshot(-force)?$ ]] || return 1
  token="$(cat "$tokfile")" || return 1
  [ "${#token}" -ge 1 ] && [ "${#token}" -le 512 ] || return 1
  [[ "$token" =~ ^[A-Za-z0-9._~+/=-]+$ ]] || return 1
  printf 'url = "%s"\n' "$url"
  printf 'header = "X-Vault-Token: %s"\n' "$token"
  printf 'proto = "=http"\nfail\nsilent\nshow-error\nmax-time = 900\nconnect-timeout = 15\n'
}

# revoke_curl_config <archivo-token> <url>: como snapshot_curl_config, pero para revocar el token
# con `POST /v1/auth/token/revoke-self` (S5-D181: la raiz efimera del `init` de un cluster nuevo no
# debe sobrevivir a `restore.sh --with-openbao`). Solo acepta esa ruta y las mismas fichas de token.
revoke_curl_config() {
  local tokfile="${1:-}" url="${2:-}" token
  [ -f "$tokfile" ] && [ -r "$tokfile" ] || return 1
  [[ "$url" =~ ^http://[A-Za-z0-9.-]+(:[0-9]{1,5})?/v1/auth/token/revoke-self$ ]] || return 1
  token="$(cat "$tokfile")" || return 1
  [ "${#token}" -ge 1 ] && [ "${#token}" -le 512 ] || return 1
  [[ "$token" =~ ^[A-Za-z0-9._~+/=-]+$ ]] || return 1
  printf 'url = "%s"\n' "$url"
  printf 'header = "X-Vault-Token: %s"\n' "$token"
  printf 'request = "POST"\nproto = "=http"\nfail\nsilent\nshow-error\nmax-time = 30\nconnect-timeout = 15\n'
}

# valid_tar_listing: lee por stdin el listado de `tar -tv` (GNU o BusyBox) y acepta solo si hay al
# menos una entrada y TODAS son archivos regulares o directorios (primer carácter `-` o `d`; fuera
# enlaces simbólicos, duros, dispositivos y FIFO) con nombre relativo bajo `uploads/`, sin `..`,
# sin ruta absoluta y sin barras dobles (S4B-D42, S4B-D97). BusyBox muestra un enlace duro como
# tipo `-` con ` -> destino` y GNU como ` link to destino`: se rechazan por el nombre. Tope de
# entradas (MAX_TAR_ENTRIES, 20000) y de bytes declarados (MAX_TAR_BYTES, 20 GiB). Una línea que no
# encaja se rechaza.
valid_tar_listing() {
  local linea nombre n=0 total=0
  local max_n="${MAX_TAR_ENTRIES:-20000}" max_b="${MAX_TAR_BYTES:-21474836480}"
  local re='^[-d][rwxsStT-]{9} [^ ]+ +([0-9]+) [0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}(:[0-9]{2})? (.+)$'
  while IFS= read -r linea || [ -n "$linea" ]; do
    [[ "$linea" =~ $re ]] || return 1
    nombre="${BASH_REMATCH[3]}"
    case "$nombre" in
      *" -> "* | *" link to "*) return 1 ;;
    esac
    nombre="${nombre%/}"
    case "$nombre" in
      uploads | uploads/*) ;;
      *) return 1 ;;
    esac
    case "/$nombre/" in
      */../* | *//* | */./*) return 1 ;;
    esac
    n=$((n + 1))
    total=$((total + 10#${BASH_REMATCH[1]}))
    [ "$n" -le "$max_n" ] && [ "$total" -le "$max_b" ] || return 1
  done
  [ "$n" -gt 0 ]
}
