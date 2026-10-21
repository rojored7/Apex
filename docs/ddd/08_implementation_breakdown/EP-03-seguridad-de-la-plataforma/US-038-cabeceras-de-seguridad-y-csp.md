# US-038 · Cabeceras de seguridad y CSP con nonce en Nginx — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-03-seguridad-de-la-plataforma/US-038-cabeceras-de-seguridad-y-csp.md`
- **Épica:** EP-03 · Seguridad de la plataforma
- **Bounded context / módulo:** infraestructura de borde (`infra/nginx/default.conf`, `web/index.html`, `web/vite.config.ts`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

Las cabeceras, el texto exacto de la CSP y el mecanismo del nonce están definidos. DECISIONES N-14 acepta el nonce con `$request_id` y `sub_filter`. El supuesto de `style-src 'self'` sin `'unsafe-inline'` no cambia ningún contrato: si una librería lo rompe, la prueba de violaciones lo detecta antes de abrirlo. No hay backend ni tablas.

## Resumen

Un fragmento `infra/nginx/snippets/security-headers.conf` con `add_header ... always` se incluye en cada `location`, porque `add_header` dentro de un `location` anula las del `server`. La CSP del HTML lleva `'nonce-$request_id'`. `index.html` se sirve sin caché y pasa por `sub_filter`, que reemplaza el marcador `__CSP_NONCE__` que Vite escribe en los `<script>` y `<link>` generados (opción `html.cspNonce`). Las respuestas de `/api/` llevan `nosniff`, `X-Frame-Options`, `Referrer-Policy` y una CSP mínima `default-src 'none'; frame-ancestors 'none'`. Un smoke `scripts/smoke/headers.sh` con `curl -I` corre en CI contra el stack construido, y una prueba de Playwright escucha `securitypolicyviolation`.

## Correcciones aplicadas por DECISIONES.md

- Supuesto: nonce derivado de `$request_id` de Nginx e inyectado con `sub_filter` → aceptado: corregido por DECISIONES N-14 (aceptado).
- La historia no habla de la TV ni de los logs → Nginx no debe registrar query strings de `/api/v1/tv/`; el `default.conf` que se toca aquí deja preparado el `location` con `access_log` sin `$args`. La regla la verifica US-175 en v0.5: corregido por DECISIONES N-44.

## Validación contra el dominio

- Sin aggregates, eventos ni reglas RN-xx de negocio. Mitiga XSS y clickjacking sobre la sesión del administrador (RN-15 y RN-13 de forma indirecta: un XSS podría leer datos revelados).
- Funciones puras: ninguna.

## Validación contra la arquitectura

- Coincide con `04_architecture_decision.md` sección 4 (Nginx sirve `web/dist` y hace proxy a `api:8000`) y sección 6 (cabeceras, CSP con nonce y `client_max_body_size 5m`).
- `$request_id` son 32 caracteres hexadecimales (128 bits), aleatorios por petición: sirven como nonce.
- `sub_filter` solo funciona sobre respuestas sin comprimir: `index.html` no se precomprime (`gzip_static off` en ese `location`) y la compresión dinámica corre después del filtro.
- `index.html` cambia en cada petición, así que va con `Cache-Control: no-store`. US-006 lo tenía en `no-cache`; se endurece porque el nonce no puede reutilizarse.
- React aplica los `style={...}` por CSSOM, y eso no lo bloquea `style-src 'self'`. Lo que sí bloquea son los `<style>` en línea y los atributos `style` en HTML estático.
- `Permissions-Policy: camera=()`: la foto del socio de v0.3 (EP-19) usa `<input type="file" capture>`, que abre la app de cámara del sistema y no `getUserMedia`, así que no entra en conflicto.
- HSTS llega con TLS en US-153 (EP-20); aquí no se envía.
- Front condicionado a D1 (el front vive en `web/`).

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
- [ ] T1 · `web/tests/unit/index-html.test.ts` (Vitest): el `dist/index.html` construido no contiene `<script>` sin atributo `src` ni `<style>` en línea, y cada `<script>` y `<link rel="stylesheet">` lleva `nonce="__CSP_NONCE__"` — 1 h

### Front
- [ ] T2 · `web/vite.config.ts`: `html: { cspNonce: "__CSP_NONCE__" }`; `build.modulePreload.polyfill = false` (el polyfill inyecta un script en línea) — 1 h
- [ ] T3 · `web/index.html`: sin scripts ni estilos en línea; el script del tema inicial (claro u oscuro), si existe, pasa a archivo en `web/public/theme-init.js` cargado con `nonce` — 1 h
- [ ] T4 · `web/tests/e2e/csp.spec.ts` (Playwright): registra `securitypolicyviolation` con `page.addInitScript` antes de navegar; recorre `/login` y `/` con sesión de prueba y exige cero violaciones (criterio 4); segunda prueba con un `index.html` de control que trae un script en línea sin nonce y exige una violación y que el script no se ejecutó (criterio 5) — 2 h

### DevOps
- [ ] T5 · `infra/nginx/snippets/security-headers.conf` con `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin` y `Permissions-Policy: camera=(), microphone=(), geolocation=()`, todos con `always` — 0,5 h
- [ ] T6 · `infra/nginx/default.conf`: `location = /index.html` y el `try_files` del SPA con `include snippets/security-headers.conf`; la CSP exacta de la historia `default-src 'self'; script-src 'self' 'nonce-$request_id'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'`; `sub_filter '__CSP_NONCE__' '$request_id'; sub_filter_once off; sub_filter_types text/html;`; `add_header Cache-Control "no-store" always`; `location /assets/` con caché larga e include de cabeceras; `location /api/` con include, más `Content-Security-Policy "default-src 'none'; frame-ancestors 'none'" always`; `client_max_body_size 5m` sin cambios; `location /api/v1/tv/` con `access_log` en formato sin `$args` (N-44) — 2 h
- [ ] T7 · `scripts/smoke/headers.sh`: `curl -sI` a `/` y a `/api/v1/health` vía Nginx; verifica las cuatro cabeceras, la CSP con `nonce-[0-9a-f]{32}`, nonces distintos en dos peticiones seguidas (criterio 2), y que un `POST` de 6 MB a `/api/v1/health` devuelve 413 (criterio 7); termina con código distinto de 0 nombrando la cabecera faltante — 1,5 h
- [ ] T8 · `.github/workflows/ci.yml`: job `smoke-headers` que construye las imágenes, levanta `infra/compose.yml` con un `.env` de CI, espera `/health` y corre `scripts/smoke/headers.sh`; el job de Playwright incluye `csp.spec.ts` — 1,5 h

### Seguridad
- [ ] T9 · Revisión: ningún `location` queda sin el include (hay que buscar `location` en `default.conf` y comparar); `server_tokens off` sigue (US-006); no existen `'unsafe-inline'` ni `'unsafe-eval'`; `connect-src 'self'` alcanza porque el API está en el mismo origen — 0,5 h

## Orden de ejecución
1. T1 (prueba del HTML construido en rojo)
2. T2
3. T3
4. T5
5. T6
6. T7 (en local con Compose)
7. T4
8. T8
9. T9

## Dependencias técnicas
- US-006 · Nginx e imagen del front: `default.conf` base, `try_files`, proxy y `client_max_body_size`.
- US-009 · Esqueleto del front: proyecto Vite y `index.html`.
- US-003 · Pipeline de CI: jobs donde corren el smoke y Playwright.
- US-153 · Redirección HTTPS y HSTS (v0.3): agrega HSTS y ajusta `connect-src` al dominio.
- US-175 · Token de la TV (v0.5): verifica que no se registran query strings de `/api/v1/tv/`.

## Endpoints
- Ninguno.

## Riesgos
- Una librería del front inyecta `<style>` en línea (por ejemplo, algunas de gráficas o de toasts) y rompe la UI en producción — mitigación: la prueba de violaciones de T4 corre en CI; si aparece, se discute antes de abrir `style-src` (supuesto de la historia).
- `sub_filter` no se aplica si `index.html` llega comprimido o desde caché — mitigación: `no-store` y `gzip_static off` en ese `location`; T7 verifica nonces distintos.
- Front condicionado a D1: si el gate no aprueba el front en `web/`, T1 a T4 salen y la CSP se valida contra el front que llegue de otro flujo.
- Cabeceras perdidas por herencia de `add_header` en un `location` nuevo — mitigación: include obligatorio y T9.

## Estimación
- Backend: 0 h
- Front: 2 h
- Pruebas: 3 h
- DevOps / seguridad: 6 h
- **Total: 11 h**

## Definición de hecho
- [ ] `cd api && uv run pytest tests/architecture -q` (debe seguir verde; esta historia no toca el api)
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- tests/unit/index-html.test.ts`
- [ ] `cd web && npx playwright test tests/e2e/csp.spec.ts`
- [ ] `docker compose -f infra/compose.yml up -d --build && bash scripts/smoke/headers.sh` termina con código 0
- [ ] `curl -sI http://localhost/ | grep -i content-security-policy` muestra `nonce-` seguido de 32 caracteres hexadecimales, distinto en dos llamadas
- [ ] `curl -sI http://localhost/api/v1/health` trae `X-Content-Type-Options: nosniff` y `X-Frame-Options: DENY`
- [ ] El job `smoke-headers` falla en un PR de control que quita `X-Frame-Options` del fragmento
- [ ] Cobertura ≥ 80 % en lo tocado: no aplica cobertura de Python (historia sin código del api); la prueba del HTML construido y el smoke cubren el 100 % de las cabeceras
