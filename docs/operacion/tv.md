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
  abres en el mismo equipo donde usas el panel, te cierra la sesión).
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

Recomendaciones: genera el enlace desde otro equipo y pégalo en la TV; cierra la sesión del
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
