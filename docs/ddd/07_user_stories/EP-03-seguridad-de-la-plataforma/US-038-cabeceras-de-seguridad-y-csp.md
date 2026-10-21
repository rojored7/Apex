# US-038 · Como equipo quiero que Nginx envíe las cabeceras de seguridad y una CSP con nonce para que el front no pueda ser incrustado ni ejecutar scripts inyectados

- **Épica:** EP-03 · Seguridad de la plataforma
- **Bounded context:** infraestructura (`infra/nginx/default.conf`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (afecta a todas)

## Historia

Como equipo
quiero `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy` y una `Content-Security-Policy` con nonce por petición en Nginx, verificadas por un smoke en CI
para que un XSS o un clickjacking no comprometan la sesión del administrador

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** `04_architecture_decision.md` sección 6 (cabeceras y CSP con nonce, `client_max_body_size 5m`); reglas web de seguridad del usuario.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `default.conf` agrega: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`, CSP `default-src 'self'; script-src 'self' 'nonce-$request_id'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'`. El nonce se inyecta en `index.html` con `sub_filter` sobre un marcador del build de Vite. Las cabeceras aplican también a `/api/`. Smoke `scripts/smoke/headers.sh` con `curl -I`.
- **Front:** el build de Vite no genera scripts en línea; `index.html` lleva el marcador de nonce.

## Criterios de aceptación

1. `curl -I http://localhost/` devuelve las cuatro cabeceras y la CSP con un nonce.
2. Dos peticiones seguidas reciben nonces distintos.
3. `curl -I http://localhost/api/v1/health` (vía Nginx) devuelve también `X-Content-Type-Options` y `X-Frame-Options`.
4. El front carga sin violaciones de CSP en la consola del navegador (prueba Playwright que escucha `securitypolicyviolation`).
5. Un script en línea agregado a mano en `index.html` sin nonce es bloqueado por el navegador.
6. El smoke corre en CI contra la imagen construida y falla si falta alguna cabecera.
7. `client_max_body_size 5m` sigue vigente: un cuerpo de 6 MB recibe 413.

## Escenarios BDD

```gherkin
# language: es
Característica: Cabeceras de seguridad del front

  Escenario: Cabeceras presentes
    Dado el stack levantado con Docker Compose
    Cuando se pide la página principal
    Entonces la respuesta trae X-Content-Type-Options, X-Frame-Options, Referrer-Policy y Permissions-Policy
    Y trae una Content-Security-Policy con nonce

  Escenario: Script inyectado bloqueado
    Dado un script en línea sin nonce en la página
    Cuando el navegador carga la página
    Entonces el script no se ejecuta y se registra una violación de CSP

  Escenario: Falta una cabecera
    Dado una configuración de Nginx sin X-Frame-Options
    Cuando corre el smoke de cabeceras en CI
    Entonces el job falla indicando la cabecera faltante
```

## Endpoints

- Ninguno propio.

## Pantalla

- Ninguna propia; condiciona todas.

## Notas técnicas

- **Migración:** no.
- **Pruebas:** smoke con `curl -I`, Playwright para violaciones de CSP.
- **Archivos principales:** `infra/nginx/default.conf`, `web/index.html`, `scripts/smoke/headers.sh`, `.github/workflows/ci.yml`.
- **Riesgo:** librerías del front que inyecten estilos o scripts en línea chocan con la CSP; se detecta con la prueba de violaciones. HSTS llega con TLS en US-153.

## Supuestos

- Supuesto: el nonce de CSP se deriva de `$request_id` de Nginx y se inyecta con `sub_filter` (el documento pide nonce sin fijar el mecanismo).
- Supuesto: `style-src 'self'` sin `'unsafe-inline'`; si una dependencia lo exige se discute antes de abrirlo.

## Dependencias

- US-006 · Nginx e imagen del front

## INVEST

- **Independiente:** solo Nginx y el build.
- **Negociable:** directivas finas de la CSP.
- **Valiosa:** mitiga XSS y clickjacking.
- **Estimable:** configuración y smoke.
- **Pequeña:** dos días.
- **Testeable:** `curl -I` y violaciones medibles.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales (si aplica)
- [ ] Migración aplicada con `alembic upgrade head` y reversible (si aplica)
- [ ] `docs/openapi.json` regenerado (si cambia el contrato)
- [ ] Auditoría verificada para las tablas tocadas (si aplica)
- [ ] Revisión de PR aprobada
