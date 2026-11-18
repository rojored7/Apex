# Pantalla de TV: operación del día a día

Guía para quien instala y cuida la pantalla de la pared del box. El contrato exacto está en
`docs/openapi.json` (`GET /api/v1/tv/today`).

## Cómo funciona

- La TV no tiene usuario: abre `/tv#token=<token>` y pide `GET /api/v1/tv/today` con la cabecera
  `X-Device-Token`. Solo la cabecera cuenta: un `?token=` en la consulta, `Authorization` y las
  cookies se ignoran, y el api responde 401 `unauthorized` igual para token ausente, inventado,
  rotado o revocado.
- El token vive en el fragmento de la URL (después de `#`): el navegador nunca lo manda al
  servidor ni lo deja en el registro de Nginx. La pantalla lo lee una vez, lo guarda en el navegador de la TV
  (`localStorage`, clave `apex.tv.token`; decisión S8-D32) y deja la URL en `/tv` antes de la primera petición.
  Se guarda para que un reinicio de la TV o un corte de luz no la dejen sin pantalla (no tiene teclado). Si lo
  prefieres solo en memoria, borra ese dato del navegador de la TV y vuelve a abrir el enlace tras cada reinicio.
  La pantalla llama `POST /auth/logout` al abrir: no deja una sesión de panel abierta en ese navegador (si la
  abres en el mismo equipo donde usas el panel, te cierra la sesión en TODAS las pestañas): por eso Configuración ya no tiene «Abrir la TV»; solo copia el enlace. Un `?token=` en la URL de la TV no se acepta: se descarta, se limpia la URL y la pantalla dice «Falta el enlace».
- El tablero trae el WOD de hoy (hora de Bogotá), sus movimientos con las cargas Rx en gramos y,
  si la sección lo permite, el ranking «Todos» con un máximo de 50 filas.

## Generar, rotar y revocar el enlace

1. Entra al panel como admin: Configuración, sección «Pantalla de TV».
2. «Generar enlace nuevo» (`POST /api/v1/settings/tv/regenerate-token`) muestra el enlace UNA
   sola vez. Cópialo en el equipo de la TV; no queda guardado en el api (solo su SHA-256).
3. Cada vez que generas uno nuevo, el anterior deja de valer al instante (la TV vieja muestra
   «Token inválido» y reintenta cada 5 minutos).
4. «Revocar» (`POST /api/v1/settings/tv/revoke-token`) deja la TV sin acceso hasta que generes otro.
5. Si el enlace se filtró (foto de la pantalla, chat), rota el token de inmediato.

Recomendaciones: copia el enlace de Configuración y ábrelo solo en la TV (escríbelo o pégalo allí); cierra la sesión del
panel en la TV; usa el perfil `tls` (HTTPS) para que el token no viaje en claro por la red del box.

## Privacidad (Ley 1581 de 2012)

- La TV muestra solo `Nombre I.` (primera palabra del nombre e inicial del apellido), el nivel y
  la marca. Nunca documento, teléfono, correo, sexo, fecha de nacimiento, notas ni ids.
- Un solo ranking «Todos» (Rx y Rx+ por marca y después escalados), sin grupos por sexo.
- No aparecen los socios dados de baja ni los que no tienen autorización de datos vigente. Las
  posiciones se calculan después de excluirlos: no queda un hueco que delate a nadie.
- Nombra la pantalla de TV en el texto de la política de privacidad (Configuración, sección
  «Privacidad», con una `policy_version` nueva) para que la autorización la cubra. Esto es un dato
  del gimnasio: el sistema no lo cambia por código.

## Límites contra sondeos

- Con token válido cuenta solo la cubeta `tv`, por token: 30 peticiones por minuto
  (`TV_TOKEN_LIMIT`), suficiente para refrescar cada 15 segundos.
- Con token inválido cuenta `tv-fail`, por IP: 12 por minuto (`TV_IP_LIMIT`); la petición 13 responde
  429 con `Retry-After`. Los fallos de un equipo no bloquean a la TV válida que sale por la misma IP.
- Ambas variables aceptan de 1 a 120.
- Además, Nginx limita `/api/v1/tv/` a 120 peticiones por minuto por IP (ráfaga de 60; zona `apex_tv` en
  `infra/nginx/snippets/tv-zone.conf`): corta los sondeos antes de que lleguen a la base. Es holgado para una
  o varias pantallas por IP; el 429 sale en el mismo envelope del api.

## Reparar la sección de la TV

Si la fila guardada de la sección `tv` ya no valida (por ejemplo, tras una edición manual en la base),
el panel la lee con los valores por defecto y «Generar enlace nuevo» o «Revocar» la reparan. Al
repararla, `refresh_seconds` y `show_leaderboard` vuelven a sus valores por defecto (30 segundos y
ranking visible) y se pierde el token vigente: revisa esos dos ajustes y vuelve a generar el enlace.

## Si el ranking es demasiado grande

Un WOD con más de 1.000 resultados vigentes no arma ranking (422 `leaderboard_too_large` en el panel).
La TV no cae: muestra el WOD con el ranking vacío y el api deja un aviso `tv: ranking omitido` en el log.

## Comprobaciones

```
curl -s -o /dev/null -w '%{http_code}\n' -H "X-Device-Token: $(cat token.txt)" http://127.0.0.1:8181/api/v1/tv/today   # 200
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8181/api/v1/tv/today                                          # 401
docker compose logs web api | grep -c -F -f token.txt                                                                    # 0
```

`token.txt` debe tener permisos 600 y se borra al terminar. `scripts/ci/prod-smoke.sh` hace estas
tres comprobaciones sobre el stack de producción desechable.

## Qué ve la pantalla cuando algo falla

- **«Token inválido. Pide un enlace nuevo en Configuración»**: el token se rotó o se revocó. La TV reintenta cada
  5 minutos; abre el enlace nuevo (`/tv#token=...`) para que el token nuevo reemplace al guardado.
- **«Sin conexión»** (pastilla junto a la fecha): falló la red, el api respondió 429 o 5xx. Conserva el último tablero
  y se recupera sola en la siguiente lectura.
- **«Sin WOD publicado»**: hoy no hay WOD. Publícalo desde el panel (`/wods/nuevo`).
- **«Falta el enlace de la pantalla»**: no hay token en la URL ni guardado.

## Prueba de resistencia de la pantalla (US-177)

La TV se prueba con dos corridas automáticas en GitHub Actions (`.github/workflows/nightly.yml`), sin que nadie mire una pared:

- **12 h aceleradas (`tv-soak`)**: la spec `web/tests/soak/tv.soak.spec.ts` con `page.clock` simula 12 horas, mide el heap por CDP al final de cada cuarto y exige que el último no pase del primero en más de 20 %. Corre a diario y a mano.
- **5 h reales (`tv-soak-real`)**: la misma spec sin `page.clock` (`SOAK_REAL_HOURS`), con temporizadores, recolección de memoria y repintado reales. Toma una muestra del heap cada 10 minutos, aplica el mismo criterio del 20 % entre el primer y el último cuarto y exige cero errores de consola. El heap queda en el resumen del job (`$GITHUB_STEP_SUMMARY`). Solo corre por `workflow_dispatch` con `real_hours` distinto de 0 (por defecto 0: un disparo manual sin entrada no la corre, y se dispara con `real_hours=5`; tope 5,5; un runner alojado corta a las 6 h); nunca con `schedule`.

Ambas son automáticas. Una corrida de 12 h reales seguidas no se prueba así: se descartó por el corte del runner y por no dejar procesos de fondo en el equipo local.
El resultado de cada disparo de las 5 h reales (éxito o fallo, enlace a la corrida y el heap del resumen) se anota en el cuaderno del sprint (`docs/scratch/sprint-NN.md`) y en el CHANGELOG de la versión; la corrida no se da por hecha sin esa nota.

### Correr la prueba a mano (local)

```
cd web
SOAK_REAL_HOURS=0.03 SOAK_SAMPLE_MINUTES=0.4 npm run soak   # unos 2 minutos reales, 4 muestras
```

`SOAK_REAL_HOURS` debe ser un número mayor que 0 y como máximo 5,5. `SOAK_SAMPLE_MINUTES` (por defecto 10) acorta el intervalo entre muestras en corridas cortas: debe dar al menos 4 muestras (`horas * 60 / minutos >= 4`) o la spec falla con ese mensaje. `SOAK_SUMMARY_FILE` cambia dónde se escribe el resumen (por defecto `web/test-results/soak-real-heap.md`).

### Dispararla por la API REST (sin `gh`)

El token de GitHub va en un archivo `curlrc` temporal (`mktemp`, nombre único) que un subshell crea con `umask 077` y borra al salir aunque `curl` falle (`trap`); el subshell no deja la `umask` cambiada. El token nunca se imprime ni va en la línea de comandos. `mktemp` resuelve la carpeta aunque `TMPDIR` no esté definida.

```
# <dueño>/<repo> salen de `git remote get-url origin`
(
  umask 077; F="$(mktemp)"; trap 'rm -f "$F"' EXIT
  printf 'protocol=https\nhost=github.com\n\n' | GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never git credential fill \
    | sed -n 's/^password=//p' | { read -r T; [ -n "$T" ] && printf 'header = "Authorization: Bearer %s"\n' "$T" > "$F"; }
  [ -s "$F" ] || { echo "sin credencial guardada" >&2; exit 1; }
  curl -sS -K "$F" -X POST -H "Accept: application/vnd.github+json" \
    https://api.github.com/repos/<dueño>/<repo>/actions/workflows/nightly.yml/dispatches \
    -d '{"ref":"<rama>","inputs":{"real_hours":"5"}}'
  # seguimiento
  curl -sS -K "$F" "https://api.github.com/repos/<dueño>/<repo>/actions/workflows/nightly.yml/runs?event=workflow_dispatch&per_page=1"
)
```

Notas:
- En NTFS (Windows) `umask` no cambia los permisos del archivo: ahí el archivo queda legible por tu usuario según las ACL de la carpeta temporal; lo que protege es que se borra al salir. Prefiere correrlo en Linux o WSL.
- Si el token es tuyo y no el de git, usa uno de alcance fino (fine-grained) limitado a este repositorio con solo el permiso «Actions: write» (y «Metadata: read»).
- `real_hours` vale `0` por defecto: un disparo sin entrada corre solo `tv-soak`; con `real_hours=5` corre los dos jobs (`tv-soak` y `tv-soak-real`). `tv-soak-real` tiene su propio grupo de concurrencia: no deja en espera al `tv-soak` nocturno.
- **`real_hours` solo es seguro con un número mayor que 0 (hasta 5,5).** El `if` del job `tv-soak-real` compara con la cadena `'0'`: `0.0`, `00` o un valor vacío no son `'0'`, así que el job arranca y falla de inmediato en el paso «validar real_hours» (no deja la prueba a medias, pero gasta un runner). Para no correrla deja el valor en `0` o no escribas nada. Desde la API REST, pasa siempre `"real_hours":"5"` o `"0"`.

### Observación en la TV del gimnasio

Mirar la pantalla instalada en la pared durante una jornada es una comprobación de operación (que el enlace sigue vigente, que el tablero rota y que no queda congelado), no una deuda de código: la evidencia de memoria y de errores de consola ya la dan las dos corridas automáticas.
