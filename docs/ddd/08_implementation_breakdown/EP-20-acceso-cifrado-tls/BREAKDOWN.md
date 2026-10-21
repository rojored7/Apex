# EP-20 · Acceso cifrado con TLS híbrido — desglose técnico de épica

- **Épica:** `docs/ddd/06_epics/EP-20-acceso-cifrado-tls.md`
- **Versión:** v0.3
- **Historias:** US-152 a US-153 (2 historias, 8 puntos)

## Resumen

La épica pone Caddy delante de Nginx, como un perfil opcional `tls` de Compose, para servir el sistema por HTTPS con certificado automático (ACME) y negociar el grupo híbrido `X25519MLKEM768`. Si el cliente no lo soporta, cae a `X25519` (US-152).

Con dominio configurado, toda petición HTTP se redirige con 308, se envía HSTS y CORS y la CSP se derivan del origen HTTPS. Sin dominio, el sistema sigue igual que en v0.1: HTTP en el puerto 80 de la LAN, sin HSTS (US-153).

No hay módulos de negocio ni tablas. El único código Python es la derivación y la validación del origen público en `core/config.py`.

## Correcciones aplicadas por DECISIONES.md

- La épica y las historias tratan P7 como pregunta abierta → se toma el supuesto del gate: solo LAN en v0.1 y TLS con Caddy en v0.3, cuando haya dominio; Caddy es opcional. No cambia el contrato y se anota como riesgo. Es supuesto aceptado de DECISIONES P7 (sección A).
- US-153 deriva el origen público solo para CORS y CSP → también se usa como origen de los enlaces de activación y recuperación (`FRONT_BASE_URL`). Si `FRONT_BASE_URL` no coincide con `public_origin` cuando hay dominio, el arranque falla con mensaje claro: coherente con DECISIONES N-11.
- Detrás de Caddy, el API ve como cliente a Nginx, y Nginx ve a Caddy → `TRUSTED_PROXIES` debe incluir la red interna de Compose de Caddy y Nginx, para que el rate limit de login y de `forgot` siga contando la IP real del cliente: coherente con DECISIONES N-14.
- La cookie HttpOnly del refresh token (N-13) debe llevar `Secure` cuando hay dominio y no puede llevarlo en modo LAN por HTTP → la bandera se deriva de `public_origin` (esquema `https`): coherente con DECISIONES N-13. Es una consecuencia del modo dual y no agrega alcance.
- La CSP con nonce por `$request_id` (N-14) se mantiene en Nginx. Caddy no reescribe cabeceras de la aplicación: solo agrega HSTS y hace la redirección.

## Validación contra el dominio y la arquitectura

- **Dominio:** sin aggregates ni eventos. Se cumplen las restricciones no funcionales: TLS con Caddy desde v0.3 (`01_product_discovery.md` sección 6), funcionamiento con internet intermitente (el modo LAN no depende de ACME) y licencias permitidas (Caddy Apache 2.0, imagen oficial sin módulos).
- **Arquitectura:** coincide con la vista de despliegue de `04_architecture_decision.md` sección 4 (caddy → nginx → api). Las cabeceras de seguridad y la CSP siguen en Nginx (US-038). `core/config.py` es configuración compartida; el cambio lo hace la épica de infraestructura, no un módulo de dominio, así que respeta la regla 4 de módulos.
- **Funciones puras:** `core.config.public_origin(settings) -> str` (`https://<APEX_DOMAIN>` o el origen LAN `LAN_ORIGIN`, por ejemplo `http://192.168.1.10`), `core.config.validate_origins(settings) -> None | ConfigError` (con dominio: ningún origen `http:` en `CORS_ORIGINS` distinto del de LAN, y `FRONT_BASE_URL` igual a `public_origin`), `core.config.cookie_secure(settings) -> bool`.
- **Seguridad:**
  - solo TLS 1.2 y 1.3;
  - HSTS `max-age=31536000; includeSubDomains`, sin `preload` (supuesto de US-153);
  - sin HSTS en LAN;
  - Nginx deja de publicar el puerto 80 al host cuando el perfil `tls` está activo;
  - los certificados persisten en el volumen `caddy_data`;
  - ningún secreto en la imagen (`ACME_EMAIL` y `APEX_DOMAIN` por `.env`).
- **Rol y endpoints:** no hay endpoints nuevos. `test_every_route_has_role.py` no cambia.

## Tablas y migraciones

- No aplica: la épica no crea ni cambia tablas. El rango reservado 0055-0059 queda sin uso.

## Services y eventos

- `core/config.py`: campos `APEX_DOMAIN: str | None`, `ACME_EMAIL: str | None` y `LAN_ORIGIN: str`; las funciones puras `public_origin`, `validate_origins` y `cookie_secure`; validación en el arranque (falla rápido con un mensaje que nombra la variable).
- `core/security.py`: la cookie de refresh usa `cookie_secure(settings)` en lugar de un valor fijo.
- CORS en `create_app()`: la lista sale de `CORS_ORIGINS` validada y, con dominio, se limita al origen HTTPS.
- Eventos: ninguno.

## Endpoints

- Ninguno.

## Componentes de front

- No aplica. El front usa rutas relativas `/api/v1`, así que funciona igual por HTTP en LAN y por HTTPS con dominio.

## Worker, CLI e infraestructura

- `infra/compose.yml`: servicio `caddy` con `profiles: ["tls"]` y la imagen oficial `caddy:2.10` o superior, fijada por digest. Publica 80 y 443 y monta los volúmenes `caddy_data` y `caddy_config` y `infra/caddy/Caddyfile` en solo lectura. Depende de `nginx` sano. Cuando el perfil está activo, `nginx` no publica puertos al host; se usa un archivo `infra/compose.tls.yml` que anula `ports` de `nginx`, porque Compose no permite condicionar `ports` por perfil.
- `infra/caddy/Caddyfile`, global y sitio:
  - `email {$ACME_EMAIL}`;
  - sitio `{$APEX_DOMAIN}` con `tls { curves x25519mlkem768 x25519; protocols tls1.2 tls1.3 }`;
  - `header Strict-Transport-Security "max-age=31536000; includeSubDomains"`;
  - `reverse_proxy nginx:80` con `X-Forwarded-Proto`;
  - redirección HTTP→HTTPS automática de Caddy con código 308 explícito.
  
  Variante de staging con `acme_ca https://acme-staging-v02.api.letsencrypt.org/directory` activada por variable.
- `infra/nginx/default.conf`: confía en `X-Forwarded-For` y `X-Forwarded-Proto` solo desde la red interna (`set_real_ip_from`). `connect-src` de la CSP se arma con el origen público; con dominio no incluye orígenes `http:`.
- `infra/compose.dev.yml`: perfil `tls` con un dominio local (`apex.localhost`) y la CA interna de Caddy (`tls internal`) para el smoke.
- `.env.example`: `APEX_DOMAIN`, `ACME_EMAIL`, `ACME_STAGING`, `LAN_ORIGIN` y el ajuste de `TRUSTED_PROXIES`.
- `scripts/workflow/tls-smoke.sh`:
  - `openssl s_client -groups X25519MLKEM768` (grupo negociado);
  - `-groups X25519` (caída);
  - `-tls1_1` (rechazo);
  - `curl -I http://...` (308 y `Location`);
  - cabecera HSTS presente con dominio y ausente en LAN;
  - `docker compose config` con y sin perfil.
- `docs/runbooks/tls.md`: cómo pasar de LAN a dominio y cómo volver atrás, reenvío de puertos del router, prueba de renovación con staging, SSL Labs (evidencia de calificación A).
- `NOTICE`: licencia de Caddy (Apache 2.0).
- CI: el smoke corre con `tls internal`; la prueba con ACME real queda en el runbook porque necesita dominio público.

## Dependencias

- EP-00: US-005 (Compose y healthchecks), US-006 (Nginx e imagen del front), US-004 (licencias y `NOTICE`), US-008 (scripts de gate).
- EP-03: US-038 (cabeceras de seguridad y CSP con nonce), US-035 o la historia que fija `TRUSTED_PROXIES` y CORS (N-14), US-036 (rate limit por IP).
- EP-04: US-042 y US-043 (cookie HttpOnly del refresh, N-13), US-047 y US-048 (`FRONT_BASE_URL`, N-11).
- EP-25 depende de esta épica para usar el portal desde fuera del gimnasio.

## Riesgos

- P7 sin confirmar: si hay dominio desde el inicio, esta épica se adelanta a v0.1. Mitigación: el perfil `tls` es independiente y se puede activar en cualquier versión sin cambios de código.
- Versión de Caddy sin `x25519mlkem768` en `curves`: la historia se bloquea. Mitigación: fijar Caddy 2.10 o superior por digest y verificarlo en el smoke.
- Rate limit y logs con la IP de Caddy en vez de la del cliente, si `TRUSTED_PROXIES` no se ajusta: el limitador bloquearía a todos a la vez. Mitigación: prueba del limitador detrás de los dos proxies.
- Cookie `Secure` en modo LAN por HTTP: el navegador no la guarda y se rompe el refresh. Mitigación: `cookie_secure` derivado y prueba en ambos modos.
- HSTS mal configurado en LAN bloquearía el acceso por IP. Mitigación: HSTS solo en el bloque de sitio con dominio y prueba explícita de su ausencia en LAN.
- Clientes viejos sin el grupo híbrido. Mitigación: `x25519` como segundo grupo y prueba de caída.
- Dependencia de internet para emitir y renovar el certificado. Mitigación: Caddy renueva con 30 días de margen y el modo LAN sigue disponible si falla.

## Estado y estimación por historia

- US-152 · TLS automático con Caddy híbrido — **READY** — 18 h — Perfil `tls` con Caddy oficial, `curves x25519mlkem768 x25519`, TLS 1.2 y 1.3, volúmenes persistentes, smoke con CA interna y runbook; P7 como supuesto aceptado.
- US-153 · Redirección HTTPS, HSTS y modo LAN — **READY** — 11 h — Redirección 308, HSTS solo con dominio, `public_origin` y `validate_origins` puras en `core/config.py`, con cookie `Secure` y `TRUSTED_PROXIES` derivados (N-13, N-14).

## Total de la épica

- **Total: 29 h**
