# US-153 · Como administrador quiero que toda petición HTTP se redirija a HTTPS con HSTS y que el modo LAN siga funcionando sin dominio para no exponer tokens por error y no romper el gimnasio si no hay internet

- **Épica:** EP-20 · Acceso cifrado con TLS híbrido
- **Bounded context:** ninguno de negocio (borde: `caddy`, `nginx`, `core/config`)
- **Versión:** v0.3
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero que con dominio todo vaya por HTTPS (redirección, HSTS, CORS y CSP al dominio) y que sin dominio el sistema siga funcionando por HTTP en la LAN
para que nadie use por descuido una conexión sin cifrar y el gimnasio no dependa de internet para operar

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** P7 (modo LAN por HTTP en el puerto 80 sin Caddy); CORS solo para el dominio del front (`CORS_ORIGINS`); CSP y cabeceras de US-038; restricción no funcional "funciona con internet intermitente en el local".
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `config.public_origin(settings) -> str` (deriva `https://<dominio>` o el origen LAN)

## Alcance

- **Backend:** Caddy redirige `http://` a `https://` con 308; agrega `Strict-Transport-Security`; `CORS_ORIGINS` y la CSP (`connect-src`) se derivan del dominio HTTPS cuando `APEX_DOMAIN` existe; en modo LAN (sin `APEX_DOMAIN`) no se envía HSTS y Nginx sigue en el puerto 80.
- **Front:** No aplica (el front usa rutas relativas `/api/v1`).

## Criterios de aceptación

1. Con dominio, `curl -I http://<dominio>/login` responde 308 a `https://<dominio>/login`.
2. Con dominio, toda respuesta HTTPS lleva `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
3. En modo LAN no se envía `Strict-Transport-Security` (evita bloquear el acceso por IP en la red local).
4. Con dominio, una petición CORS desde `http://<dominio>` (sin TLS) o desde otro origen es rechazada; desde `https://<dominio>` es aceptada.
5. La CSP servida con dominio no contiene orígenes `http:`.
6. Sin `APEX_DOMAIN` y sin el perfil `tls`, `docker compose up` deja el sistema usable en `http://<ip-del-servidor>` como en v0.1.
7. El arranque del API falla con un mensaje claro si `APEX_DOMAIN` está definido y `CORS_ORIGINS` contiene un origen `http:` distinto del de LAN.
8. El runbook explica cómo pasar de LAN a dominio y cómo volver atrás.

## Escenarios BDD

```gherkin
# language: es
Característica: Redirección a HTTPS y modo LAN

  Escenario: Petición por HTTP con dominio configurado
    Dado que el sistema corre con el dominio "box.apex.co"
    Cuando un navegador pide "http://box.apex.co/login"
    Entonces recibe una redirección 308 a "https://box.apex.co/login"
    Y la respuesta HTTPS trae la cabecera Strict-Transport-Security

  Escenario: Gimnasio sin dominio
    Dado que el sistema corre sin dominio configurado
    Cuando recepción abre "http://192.168.1.10/login"
    Entonces ve la pantalla de acceso sin redirección
    Y la respuesta no trae Strict-Transport-Security
```

## Endpoints

- Ninguno nuevo.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** `public_origin` con y sin dominio.
- **Pruebas:** smoke con `curl -I` en ambos modos; prueba de configuración del API (validación al arrancar).
- **Archivos principales:** `infra/caddy/Caddyfile`, `infra/nginx/default.conf`, `api/src/app/core/config.py`, `docs/runbooks/tls.md`.

## Supuestos

- Supuesto: `max-age` de HSTS de un año con `includeSubDomains` y sin `preload` (no está fijado en ningún documento; `preload` es difícil de revertir).

## Dependencias

- US-152 · TLS automático con Caddy híbrido

## INVEST

- **Independiente:** solo configuración del borde.
- **Negociable:** valores de HSTS.
- **Valiosa:** evita fugas por HTTP y mantiene la operación en LAN.
- **Estimable:** configuración y smoke.
- **Pequeña:** sí.
- **Testeable:** cabeceras y códigos verificables con `curl`.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde (cambio en `config.py`)
- [ ] Smoke de ambos modos en verde
- [ ] Runbook actualizado
- [ ] Revisión de PR aprobada
