# US-006 · Como equipo quiero un Nginx que sirva el build del front y haga proxy de `/api/` al api, empaquetado en su imagen, para que el navegador use un solo origen y las subidas queden limitadas a 5 MB

- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context:** ninguno de negocio (`infra/nginx/`, `web/Dockerfile`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `infra/nginx/default.conf` que sirva `web/dist`, haga proxy de `/api/` a `api:8000` y limite el cuerpo a 5 MB, y una imagen `web` que contenga el build
para que el front y el API compartan origen (sin CORS en producción) y ninguna subida pase de 5 MB

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** "Seguridad" de `CLAUDE.md` (archivos de máximo 5 MB); `04_architecture_decision.md` sección 4 (nginx sirve `web/dist` y proxy `/api`); las cabeceras y la CSP las endurece US-038.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `default.conf` con `listen 80`, `root /usr/share/nginx/html`, `try_files $uri /index.html` para el enrutamiento del SPA, `location /api/ { proxy_pass http://api:8000; }` con `X-Forwarded-For` y `X-Forwarded-Proto` (necesarios para el rate limit por IP de US-036), `client_max_body_size 5m`, caché larga para `/assets/` con hash y `no-cache` para `index.html`, `server_tokens off`.
- **Front:** `web/Dockerfile` multi-stage (etapa `node` con `npm ci && npm run build`, etapa `nginx:stable-alpine` que copia `dist` y `default.conf`); servicio `web` en `infra/compose.yml` publicando el puerto 80 y con `depends_on` a `api`.

## Criterios de aceptación

1. `curl http://localhost/` devuelve el `index.html` del build con 200.
2. `curl http://localhost/socios/123` (ruta del SPA inexistente como archivo) devuelve `index.html` con 200.
3. `curl http://localhost/api/v1/health` llega al contenedor `api` y devuelve su respuesta.
4. Un `POST` a `/api/` con cuerpo de 5 MB más 1 byte recibe 413 de Nginx sin llegar al api.
5. La cabecera `Server` no revela la versión de Nginx.
6. El api recibe la IP real del cliente en `X-Forwarded-For`.
7. La imagen `web` se construye en el job `images` de CI.

## Escenarios BDD

```gherkin
# language: es
Característica: Un solo origen para front y API

  Escenario: Ruta del SPA servida por Nginx
    Dado el sistema levantado con Docker Compose
    Cuando el navegador pide "/socios/123"
    Entonces Nginx responde 200 con "index.html"

  Escenario: Proxy al API
    Dado el sistema levantado
    Cuando pido "/api/v1/health"
    Entonces la respuesta viene del servicio "api"

  Escenario: Subida demasiado grande
    Dado un archivo de 5 MB más un byte
    Cuando lo envío por POST a "/api/v1/members/1/attachments"
    Entonces Nginx responde 413
    Y el api no recibe la petición
```

## Endpoints

- Ninguno propio; proxy de `/api/` hacia el api.

## Pantalla

- Ninguna (sirve el build del front).

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** smoke con `curl` en CI tras `docker compose up` (las cuatro peticiones de los criterios 1 a 4).
- **Archivos principales:** `infra/nginx/default.conf`, `web/Dockerfile`, `web/.dockerignore`, `infra/compose.yml` (servicio `web`).

## Supuestos

- Supuesto: se elige build del front dentro de `web/Dockerfile` (multi-stage) en lugar de copiar un artefacto de CI, porque permite `docker compose build` sin CI; `05_service_design.md` sección 7 deja ambas opciones abiertas.

## Dependencias

- US-005 · Dockerfile del api y Compose (servicio `api` al que hace proxy).
- US-009 · Esqueleto del front (lo que se construye y sirve).

## INVEST

- **Independiente:** solo necesita que existan el api y el esqueleto del front.
- **Negociable:** estrategia de build y caché.
- **Valiosa:** un solo origen, límite de subida y base para las cabeceras de seguridad.
- **Estimable:** configuración conocida.
- **Pequeña:** dos días.
- **Testeable:** cuatro peticiones `curl`.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (supuesto declarado)

## Definición de terminado

- [ ] Smoke de `curl` en verde
- [ ] Imagen `web` construida en CI
- [ ] Revisión de PR aprobada
