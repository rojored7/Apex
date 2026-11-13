# TLS

Alcance: el perfil `tls` de Compose con Caddy 2.11.3 (S6-D63, D64, D77, D82). Termina TLS 1.3 con el
intercambio híbrido poscuántico `x25519mlkem768` (con caída a `x25519`; TLS 1.2 sigue aceptado, 1.1 no),
redirige el puerto 80 con un `308`, envía HSTS escalonado y reenvía a Nginx por la red del stack. Sin el
perfil, APEX sirve por HTTP en la LAN como hasta ahora. Los pasos de instalación están en
`instalar-en-servidor.md`; actualizar con el perfil, en `actualizar.md`.

## Qué cambia con el perfil

- `caddy` (imagen por digest, `read_only`, `cap_drop: [ALL]` y solo `NET_BIND_SERVICE`, sin API de administración ni puerto 2019) publica el 80 (`WEB_PORT`) y el HTTPS (`TLS_PORT`). `web` deja de publicar puertos: solo Caddy lo alcanza (`infra/compose.tls.yml`).
- Nginx (snippet `real-ip.conf`, contexto `http`) confía en `X-Forwarded-For` y en `X-Forwarded-Proto` solo si el par TCP es la IP fija de Caddy (`172.30.0.11/32` por omisión): el limitador por IP cuenta al cliente y no a Caddy, y un cliente que llegue directo no puede fingir `https`.
- El HSTS lo envía solo Caddy, solo por HTTPS y solo para el host (sin `includeSubDomains` ni `preload`).
- `caddy` recibe cinco variables y ninguna más: `APEX_DOMAIN`, `APEX_TLS_ISSUER`, `APEX_ACME_EMAIL`, `APEX_ACME_CA` y `APEX_HSTS_MAX_AGE`. `web` recibe además `APEX_CADDY_IP` (documental).

## Variables

- `APEX_DOMAIN`: va en `.env`. Forma `host[:puerto]`, sin esquema. Vacío = sin dominio. Un puerto solo se admite con `ALLOW_DOMAIN_PORT=true` y un host `*.localhost` (ensayo y desarrollo: `apex.localhost:8443`).
- `ALLOW_DOMAIN_PORT`: `false` por defecto. Va en `.env`.
- En `.env.ops` (solo las leen Compose, `deploy.sh` y el servicio `caddy`; el api no las lee):
  - `APEX_CADDY_IP` (`172.30.0.11`): IP fija de Caddy, dentro de `APEX_SUBNET` y fuera de `APEX_IP_RANGE`.
  - `APEX_TLS_ISSUER` (`internal`): `internal` (CA interna de Caddy) solo con hosts `*.localhost`; con un dominio real, el correo del emisor ACME (por ejemplo `ops@tu-dominio`).
  - `APEX_ACME_EMAIL`: correo ACME (documental; el emisor lo lleva `APEX_TLS_ISSUER`).
  - `APEX_ACME_CA`: directorio ACME. Vacío = el de Let's Encrypt de producción. Para ensayar con un dominio real, el de staging: `https://acme-staging-v02.api.letsencrypt.org/directory`.
  - `APEX_HSTS_MAX_AGE` (`300`): segundos de HSTS, ver «HSTS escalonado».
  - `TLS_PORT` (`443`): puerto HTTPS de Caddy, el mismo dentro y fuera del contenedor (`TLS_PORT:TLS_PORT`, S6-D96). **Debe ser el puerto de `APEX_DOMAIN`** (8443 con `apex.localhost:8443`) o 443 si `APEX_DOMAIN` no lleva puerto; `deploy.sh` sale con 2 si no coinciden.
  - `APEX_REAL_IP_CONF` (vacío): ruta del snippet `real-ip.conf` que monta `web`; ver «IP de Caddy distinta».


## Los dos modos y la coherencia de origen (S6-E1, US-153)

El api decide su origen público de `APEX_DOMAIN` (S6-D65); no hay variables nuevas.

- **Modo LAN (sin `APEX_DOMAIN`).** El origen público es `FRONT_BASE_URL` (puede ser `http:`). CORS acepta solo `CORS_ORIGINS` (vacío = sin CORS). `COOKIE_SECURE` puede ser `false`; con `ENV=production` el api exige `COOKIE_SECURE=true` salvo `ALLOW_INSECURE_COOKIE=true` (riesgo aceptado P7, S4B-D154).
- **Modo dominio (con `APEX_DOMAIN`).** El origen público es `https://<APEX_DOMAIN>` (con el puerto si lo lleva, por ejemplo `https://apex.localhost:8443`). CORS acepta ese origen además de `CORS_ORIGINS`. La cookie del refresh lleva `Secure` y `SameSite=Strict` (en LAN solo `SameSite=Strict`).
- **Qué valida el arranque con dominio.** El api no arranca si: `CORS_ORIGINS` contiene un origen `http:` (otros orígenes `https:` siguen válidos); `FRONT_BASE_URL` no es exactamente el origen público; `COOKIE_SECURE=false`; o `ALLOW_INSECURE_COOKIE=true` (con dominio no hay excepción P7); o `AUTH_ALLOWED_ORIGINS` lleva un origen `http:` o, si no está vacía, no contiene el origen público. Vale en `ENV=dev` y en `production`.
- **Mensajes de arranque.** `Configuración inválida (inválidas o desconocidas: ALLOW_INSECURE_COOKIE, AUTH_ALLOWED_ORIGINS, COOKIE_SECURE, CORS_ORIGINS, FRONT_BASE_URL). Revisa .env y .env.example.` Lista solo los nombres de las variables incoherentes, nunca sus valores; corrige esas variables en `.env` y reinicia.
- **IP real del cliente.** `TRUSTED_PROXIES` sigue siendo solo la IP de Nginx (S6-D82): Caddy no entra. Nginx restaura la IP real con `real_ip` y el api salta una sola vez, así el limitador no cuenta a Caddy.
- **Volver a LAN: `APEX_DOMAIN` vacío también en `.env.ops`.** Compose interpola `APEX_DOMAIN` al api desde `.env.ops` (`infra/compose.yml`); si ahí queda el valor del modo dominio, el api sigue en modo dominio con `FRONT_BASE_URL` y cookie de LAN y no arranca: el error nombra `ALLOW_INSECURE_COOKIE, COOKIE_SECURE, FRONT_BASE_URL`. Vacíalo en `.env` y en `.env.ops`.
- **Variables del humo `tls-smoke.sh`** (las lee solo el script, no el api): `TLS_SMOKE_ADMIN_EMAIL` y `TLS_SMOKE_ADMIN_PASSWORD_FILE` (archivo de una línea, modo 600; nunca se imprime) activan el login real y exigen 200, `Access-Control-Allow-Origin` igual al origen público, y la cookie `apex_refresh` con `HttpOnly`, `SameSite=strict` y `Secure` (con `--lan`, sin `Secure`); con `Origin: http://<dominio>` exigen 403 sin `Access-Control-Allow-Origin`. Sin ellas el humo escribe «omitida: cookie y CORS (sin TLS_SMOKE_ADMIN_*)». `TLS_SMOKE_ALLOW_SEALED=1` acepta `/api/v1/health` con 503 y `"crypto":"sealed"` como «aviso: custodio sellado» (por omisión exige 200). `prod-smoke.sh --tls` las pasa solo, con un archivo temporal 600 que borra al terminar.

## De LAN a dominio, paso a paso

Requisitos: un nombre DNS que apunte a la IP pública del servidor y los puertos 80 y 443 de esa IP reenviados al servidor (el 80 lo exige el desafío HTTP-01 de ACME).

1. `.env`: `APEX_DOMAIN=apex.tu-dominio`, `FRONT_BASE_URL=https://apex.tu-dominio`, `COOKIE_SECURE=true` y `ALLOW_INSECURE_COOKIE=false`. Sin puerto en `APEX_DOMAIN` y con `ALLOW_DOMAIN_PORT=false`.
2. `.env.ops`: `APEX_TLS_ISSUER=ops@tu-dominio` (el correo, no `internal`), `APEX_HSTS_MAX_AGE=300`, `TLS_PORT=443` y `WEB_PORT=80`.
3. Antes de tocar producción, ensaya con staging: `APEX_ACME_CA=https://acme-staging-v02.api.letsencrypt.org/directory`. El navegador no confiará en ese certificado: sirve para comprobar que el desafío funciona. Cuando emita, vuelve a dejar `APEX_ACME_CA` vacío.
4. Despliega con el perfil (`actualizar.md`): `DEPLOY_COMPOSE_EXTRA="-f infra/compose.tls.yml --profile tls" bash infra/deploy.sh ...`. Si usas también la identidad de verificación del respaldo, añade `infra/compose.verify.yml` a esa variable.
5. Comprueba (sin credenciales): `docker compose ... ps caddy` en `healthy`; `curl -sI http://apex.tu-dominio/login` responde `308` a `https://apex.tu-dominio/login`; `curl -sI https://apex.tu-dominio/api/v1/health` responde `200` con `strict-transport-security: max-age=300`.
6. **Paso humano explícito: el ACME HTTP-01 real.** La emisión con el dominio real y la renovación (Caddy renueva solo, unos 30 días antes del vencimiento) solo se prueban en el servidor con el dominio y los puertos reenviados. Ningún humo de la CI las cubre (usan la CA interna).

Vuelta atrás a LAN: quita `-f infra/compose.tls.yml --profile tls` de `DEPLOY_COMPOSE_EXTRA`, vuelve a poner `FRONT_BASE_URL=http://<ip>`, `ALLOW_INSECURE_COOKIE=true` (riesgo aceptado P7) y despliega o recrea `web`: `docker compose --env-file .env --env-file .env.ops -f infra/compose.yml up -d web` y `... stop caddy`. Mientras el HSTS siga vigente en los navegadores que ya visitaron el dominio, esos navegadores seguirán exigiendo HTTPS hasta que venza.

## HSTS escalonado

Un HSTS largo con un certificado roto deja el panel inaccesible para esos navegadores durante todo el `max-age`, sin botón de «continuar de todos modos». Por eso se sube por escalones, cada uno solo cuando el anterior corrió sin incidentes:

1. `300` (5 minutos): la primera semana, mientras compruebas emisión, redirección y renovación.
2. `604800` (7 días): tras al menos una renovación correcta del certificado.
3. `31536000` (1 año): cuando el servicio lleva semanas estable. No hay `includeSubDomains` ni `preload`: no se añaden sin una decisión aparte.

Cambiar el escalón: edita `APEX_HSTS_MAX_AGE` en `.env.ops` y recrea Caddy (`docker compose --env-file .env --env-file .env.ops -f infra/compose.yml -f infra/compose.tls.yml --profile tls up -d caddy`). Bajar el valor no acorta el que los navegadores ya guardaron.

Un monitor externo (UptimeRobot u otro) ve el `308` del puerto 80, no un `200`: apúntalo al HTTPS, o acepta el `308`.

## IP de Caddy distinta de la de fábrica

`infra/nginx/snippets/real-ip.conf` (versionado y horneado en la imagen de `web`) confía en `172.30.0.11/32`. Si cambias `APEX_CADDY_IP` (por ejemplo porque cambiaste `APEX_SUBNET`):

1. `deploy.sh` renderiza `infra/nginx/snippets/real-ip.conf.in` a `${DEPLOY_STATE_DIR}/real-ip.conf` (por omisión `~/.local/state/apex-deploy/real-ip.conf`, modo 644, fuera del árbol) y exporta `APEX_REAL_IP_CONF` apuntando a él. Compose lo monta sobre el snippet horneado. El árbol de git no se ensucia. `deploy.sh` sale con 2 si `APEX_CADDY_IP` no es una IPv4.
2. Si recreas `web` a mano, exporta antes la misma variable (`APEX_REAL_IP_CONF=<ruta> docker compose ... up -d web`) o ponla en `.env.ops`; sin ella Compose usa el snippet versionado y Nginx dejaría de confiar en Caddy (todos los clientes contarían como la IP de Caddy en el limitador).
3. El snippet incluye también los `map` de `$apex_proto` (S6-D97), así que con otra IP de Caddy el api sigue recibiendo `X-Forwarded-Proto: https` solo desde Caddy.

## Comprobaciones

- `bash scripts/ci/tls-smoke.sh --dc "<comando de docker compose del stack>"` (CA interna, host `*.localhost`): `Negotiated TLS1.3 group: X25519MLKEM768` y la caída a `X25519`, TLS 1.1 rechazado y 1.2 aceptado, `308` de `/login`, `/_caddy_health` `200` por HTTP, `acme-challenge` sin `308`, HSTS solo por HTTPS, `/api/v1/health` por Caddy y el limitador por IP real con dos clientes. Con `--lan` comprueba el stack sin perfil. `--dry-run` lista las comprobaciones sin levantar nada.
- `bash scripts/ci/prod-smoke.sh --no-build --provider openbao --tls`: el stack de producción desechable (`apex-smoke`) con el perfil y el `tls-smoke.sh` al final. Necesita Linux (CI o contenedor auxiliar).
- **SSL Labs es evidencia humana.** `https://www.ssllabs.com/ssltest/` contra el dominio real tras el paso 6; guarda la calificación en el cuaderno del sprint. No corre en la CI.

## Residual: la red `custody`

Caddy no cifra el tráfico de la red interna `custody` (api, worker y tools hacia OpenBao). Esa red es `internal: true` (sin salida a internet ni al anfitrión). El TLS interno de OpenBao queda como residual de v0.4 a cargo del operador.

## Si algo falla

- `caddy` no llega a `healthy`: `docker compose ... logs --tail 80 caddy`. Causas habituales: `APEX_DOMAIN` o `APEX_TLS_ISSUER` vacíos (el Caddyfile no valida) y el puerto 80 ocupado en el anfitrión.
- El certificado no se emite: el 80 no llega desde fuera (reenvío), el DNS no apunta al servidor o se agotó el cupo de Let's Encrypt (usa staging para ensayar). `caddy_data` guarda los certificados y la cuenta ACME: no lo borres.
- Con `APEX_DOMAIN=apex.localhost:8443` (ensayo y desarrollo) Caddy escucha el 8443 dentro del contenedor, porque el puerto del nombre manda; por eso se publica `8443:8443` (S6-D96). `tls-smoke.sh` lee el puerto del propio contenedor y entra por la red del stack.
- El sitio HTTP (puerto 80) solo sirve `/_caddy_health` y el reto ACME; todo lo demás recibe un 308 a `https://<APEX_DOMAIN><ruta>` (con el puerto de `APEX_DOMAIN`). En LAN con puerto (ensayo) el 80 de la máquina no suele estar publicado, así que el 308 solo es útil en producción con 80/443.
- La IP de Caddy, `real_ip` y los dos `map` del protocolo viven todos en `real-ip.conf` (incluido en el contexto `http` de Nginx, S6-D97): al cambiar `APEX_CADDY_IP` el render los actualiza juntos.

## Notas de la revisión de seguridad de W0-4

- `compose.dev.yml` y `compose.tls.yml` no se combinan: cada uno publica los puertos de Caddy a su manera (desarrollo `127.0.0.1:8443:8443`; producción `${TLS_PORT}:${TLS_PORT}` y `${WEB_PORT}:80`) y Compose concatenaría las listas. En desarrollo se usa `-f infra/compose.yml -f infra/compose.dev.yml --profile tls`; en producción y en el ensayo, `-f infra/compose.yml [-f infra/compose.openbao.yml] -f infra/compose.tls.yml --profile tls`.
- `deploy.sh` con el perfil `tls` sale con 2, sin construir nada, si `APEX_TLS_ISSUER=internal` acompaña a un dominio que no termina en `.localhost`, si `APEX_DOMAIN` lleva puerto y `TLS_PORT` no coincide, si `APEX_DOMAIN` no lleva puerto y `TLS_PORT` no es 443, o si `APEX_CADDY_IP` no es una IPv4 limpia (sin máscara ni ceros a la izquierda).
- `tls-smoke.sh` solo confía en la CA interna para el host exacto `apex.localhost`.

