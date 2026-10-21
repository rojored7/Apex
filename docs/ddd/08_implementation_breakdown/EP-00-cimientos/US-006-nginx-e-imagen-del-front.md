# US-006 · Nginx con proxy al api e imagen del front — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-00-cimientos/US-006-nginx-e-imagen-del-front.md`
- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context / módulo:** ninguno de negocio, terreno (`infra/nginx/default.conf`, `web/Dockerfile`, servicio `web` de `infra/compose.yml`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

El papel de Nginx (servir `web/dist`, proxy de `/api/` a `api:8000`, 5 MB de cuerpo) está fijado en `04_architecture_decision.md` sección 4 y en "Seguridad" de `CLAUDE.md`. El supuesto de construir el front dentro de `web/Dockerfile` cabe en lo que `05_service_design.md` sección 7 deja abierto. Las cabeceras de seguridad, la CSP con nonce y el registro sin query strings de la TV quedan para US-038 y EP-23 (DECISIONES N-14 y N-44), sin cambiar esta historia.

## Resumen

`infra/nginx/default.conf` con `listen 80`, `server_tokens off`, `client_max_body_size 5m`, fallback del SPA a `index.html`, proxy de `/api/` a `http://api:8000` conservando la ruta, cabeceras `X-Forwarded-For` (con la IP real del cliente, sobrescrita y no concatenada), `X-Forwarded-Proto`, `Host` y `X-Request-ID`, caché larga e inmutable para `/assets/` y `no-cache` para `index.html`. `web/Dockerfile` en dos etapas (Node para `npm ci && npm run build`, `nginx:stable-alpine` con `dist` y `default.conf`). El servicio `web` de Compose publica el puerto 80. Un smoke con `curl` en CI cubre los criterios 1 a 4.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md.
- Notas de coordinación (no cambian esta historia): el nonce de la CSP con `$request_id` y `sub_filter` es de US-038 (N-14); por eso aquí ya se propaga `X-Request-ID $request_id`. No registrar query strings de `/api/v1/tv/` es de EP-23 (N-44); el `log_format` se define aquí con nombre propio (`apex`) para que EP-23 solo agregue una `location`.

## Validación contra el dominio

- No hay aggregates, entidades, value objects, invariantes RN-xx ni eventos.
- El límite de 5 MB protege la regla de adjuntos de `CLAUDE.md` ("tamaño máximo 5 MB") en el borde, antes de que el api lea un byte.

## Validación contra la arquitectura

- Un solo origen para front y API: en producción no hace falta CORS (US-037 lo deja cerrado para los orígenes de `CORS_ORIGINS`).
- `X-Forwarded-For` lo necesita el rate limit por IP de US-036 junto con `TRUSTED_PROXIES` (N-14). Como Nginx es el borde en v0.1 (P7: solo LAN), se sobrescribe con `$remote_addr`; cuando Caddy entre delante (EP-20), Nginx pasa a `real_ip` desde Caddy.
- `/api/v1/health` llega al api porque `proxy_pass http://api:8000;` sin URI conserva la ruta completa; el api debe montar `/api/v1/health` además de `/health` (N-16, US-020).
- `/health` en la raíz no se publica por Nginx (cae en el SPA); el healthcheck del contenedor `api` lo usa directo (US-005).
- Sin módulos, sin bus, sin roles, sin paginación ni auditoría: no aplica.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- No aplica.

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- No aplica.

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T1 · `scripts/ci/tests/test_nginx_conf.sh`: corre `docker run --rm -v "$PWD/infra/nginx/default.conf:/etc/nginx/conf.d/default.conf:ro" --add-host api:127.0.0.1 nginx:stable-alpine nginx -t` y con `grep` verifica `client_max_body_size 5m`, `server_tokens off` y `proxy_set_header X-Forwarded-For $remote_addr` — 1 h
- [ ] T2 · `scripts/ci/web-smoke.sh` (lo invoca `scripts/ci/compose-smoke.sh` de US-005 después de levantar `web`): `curl -fsS http://localhost/` contiene `<div id="root">` (criterio 1); `curl -fsS http://localhost/socios/123` devuelve 200 con el mismo `index.html` (criterio 2); `curl -sS -o /dev/null -w '%{http_code}' http://localhost/api/v1/health` distinto de 404 de Nginx y con cabecera de respuesta del api (criterio 3; 200 cuando exista US-020); `head -c 5242881 /dev/zero | curl -s -o /dev/null -w '%{http_code}' -X POST --data-binary @- http://localhost/api/v1/members/1/attachments` devuelve 413 y `docker compose logs api` no registra esa petición (criterio 4); `curl -sI http://localhost/` con `Server: nginx` sin versión (criterio 5) — 2 h
- [ ] T3 · Prueba de la IP real (criterio 6): con el marcador de `app.main` no hay ruta que la devuelva, así que se verifica en el log de acceso de Nginx (`$remote_addr`) y con una ruta temporal de eco solo en `compose.dev.yml`; la prueba definitiva por el api la hace US-036 al leer `X-Forwarded-For` con `TRUSTED_PROXIES` — 0,5 h

### Front
- [ ] T4 · `web/Dockerfile` etapa `build`: `FROM node:22-alpine AS build`, `WORKDIR /web`, `COPY web/package.json web/package-lock.json ./`, `npm ci`, `COPY web/ ./`, `npm run build`; contexto de build la raíz del repositorio (necesita `infra/nginx/default.conf`) — 1 h
- [ ] T5 · `web/Dockerfile` etapa final: `FROM nginx:stable-alpine`, `COPY --from=build /web/dist /usr/share/nginx/html`, `COPY infra/nginx/default.conf /etc/nginx/conf.d/default.conf`, `EXPOSE 80`; `web/Dockerfile.dockerignore` (BuildKit lo aplica al contexto raíz cuando el Dockerfile está en `web/`) que excluye `**/node_modules`, `web/dist`, `api/`, `.git`, `.env*`, `keys/`, `_entregas/` — 1 h

### DevOps
- [ ] T6 · `infra/nginx/default.conf` bloque `server`: `listen 80;`, `server_name _;`, `server_tokens off;`, `client_max_body_size 5m;`, `root /usr/share/nginx/html;`, `log_format apex` en JSON con `$remote_addr`, `$request_method`, `$uri` (sin `$args`), `$status`, `$request_time`, `$request_id`; `access_log /dev/stdout apex;` — 1 h
- [ ] T7 · `location /api/`: `proxy_pass http://api:8000;` (sin URI, conserva `/api/v1/...`), `proxy_http_version 1.1`, `proxy_set_header Host $host`, `proxy_set_header X-Forwarded-For $remote_addr` (sobrescribe, impide que un cliente falsifique su IP para el rate limit), `proxy_set_header X-Forwarded-Proto $scheme`, `proxy_set_header X-Request-ID $request_id`, `proxy_read_timeout 60s`; con `proxy_request_buffering on` (por defecto) el 413 sale antes de abrir la conexión al api — 1,5 h
- [ ] T8 · Locations del SPA: `location = /index.html { add_header Cache-Control "no-cache"; }`, `location /assets/ { expires 1y; add_header Cache-Control "public, max-age=31536000, immutable"; try_files $uri =404; }`, `location /fonts/` y `location /brand/` con caché de 30 días, `location / { try_files $uri $uri/ /index.html; }` — 0,5 h
- [ ] T9 · Servicio `web` en `infra/compose.yml` (sobre el esqueleto de US-005): `build: { context: .., dockerfile: web/Dockerfile }`, `image: apex-web:local`, `ports: ["80:80"]`, `depends_on: api: condition: service_started`, `healthcheck: wget -q -O /dev/null http://127.0.0.1/index.html` cada 10 s, `restart: unless-stopped` — 1,5 h
- [ ] T10 · Job `images` de CI (US-003 T6): confirmar el build de `web/Dockerfile` con `context: .` y agregar a `scripts/ci/compose-smoke.sh` el `up -d web` y la llamada a `scripts/ci/web-smoke.sh` (criterio 7) — 1 h

### Seguridad
- [ ] T11 · Revisión: `X-Forwarded-For` sobrescrito y no concatenado; `server_tokens off`; el log de acceso no incluye `$args` ni cabeceras con tokens (`Authorization`, `Cookie`); la imagen final no contiene `node_modules` ni fuentes del api (`docker run --rm apex-web:local ls /usr/share/nginx/html`); anotar que cabeceras de seguridad y CSP son de US-038 — 1 h

## Orden de ejecución
1. T1 (prueba de sintaxis y directivas, en rojo)
2. T6, T7, T8 (configuración de Nginx)
3. T4, T5 (imagen del front)
4. T9 (servicio en Compose)
5. T2, T3 (smoke con `curl`)
6. T10 (enganche en CI)
7. T11 (revisión)

## Dependencias técnicas
- US-005 · Dockerfile del api y Compose: servicio `api` destino del proxy, esqueleto del servicio `web` y `scripts/ci/compose-smoke.sh`.
- US-009 · Esqueleto del front: `web/package.json`, `package-lock.json` y el build que se sirve.
- US-003 · Pipeline CI: job `images`.
- US-020 · `create_app()` y `/health`: `/api/v1/health` con 200 para cerrar el criterio 3 con respuesta real del api.
- US-036 · Rate limit: consumidor de `X-Forwarded-For`; US-038 · Cabeceras y CSP: endurece este mismo archivo.

## Endpoints
- Ninguno.

## Riesgos
- `X-Forwarded-For` con `$proxy_add_x_forwarded_for` concatenaría el valor que manda el cliente y permitiría saltar el rate limit de login — mitigación: `$remote_addr` en T7; cuando entre Caddy (EP-20) se cambia a `set_real_ip_from` con la IP de Caddy.
- `.dockerignore` con contexto en la raíz: un `web/.dockerignore` no se aplica si el contexto es la raíz, y el build copiaría `api/`, `.git` o un `.env` local — mitigación: `web/Dockerfile.dockerignore` (T5) y revisión del contenido de la imagen en T11.
- El 413 con cuerpo `chunked` sin `Content-Length`: Nginx lo detecta al leer el cuerpo con `proxy_request_buffering on`; si alguien lo apaga para subidas grandes, el api recibiría parte del cuerpo — mitigación: dejar el valor por defecto y la prueba de T2 con `--data-binary`.
- Sin `/api/v1/health` hasta US-020, el criterio 3 se verifica con la respuesta 404 del api (cuerpo JSON de FastAPI), no con el 404 HTML de Nginx — mitigación: T2 distingue ambos por la cabecera `content-type`.
- Front condicionado a D1: si el gate no aprueba el front en este repositorio, `web/Dockerfile` copia un artefacto entregado por el otro flujo de trabajo y T4 se reemplaza por `COPY dist/`.

## Estimación
- Backend: 0 h
- Front: 2 h
- Pruebas: 3,5 h
- DevOps / seguridad: 6,5 h
- **Total: 12 h**

## Definición de hecho
- [ ] `docker run --rm -v "$PWD/infra/nginx/default.conf:/etc/nginx/conf.d/default.conf:ro" --add-host api:127.0.0.1 nginx:stable-alpine nginx -t` termina con código 0
- [ ] `docker build -f web/Dockerfile -t apex-web:ci .` termina con código 0
- [ ] `docker compose -f infra/compose.yml -f infra/compose.dev.yml config` termina con código 0
- [ ] `docker compose -f infra/compose.yml -f infra/compose.dev.yml up -d --build db api web && bash scripts/ci/web-smoke.sh` termina con código 0
- [ ] `curl -sI http://localhost/ | grep -i '^server:'` devuelve `Server: nginx` sin número de versión
- [ ] `head -c 5242881 /dev/zero | curl -s -o /dev/null -w '%{http_code}' -X POST --data-binary @- http://localhost/api/v1/members/1/attachments` imprime `413`
- [ ] `bash scripts/ci/tests/test_nginx_conf.sh` termina con código 0
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm run build` (si hay front)
- [ ] El job `images` de CI construye `apex-web` y corre el smoke en verde (enlace en el PR)
