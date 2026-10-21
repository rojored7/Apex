# EP-03 · Seguridad de la plataforma

- **Versión del plan:** v0.1 (Tarea 1 punto 3, `security.py`; Tarea 3 punto 3, rate limit; Tarea 10 punto 4, cabeceras de Nginx; sección 6 de `04_architecture_decision.md`).
- **Bounded context:** `core/security` y `core/ratelimit` (transversal, shared kernel restringido) más la configuración de seguridad de `infra/nginx`.
- **Estimación relativa:** M.

## Objetivo de negocio

Que solo entre quien debe y que cada quien vea solo lo que su rol permite: el coach no anula pagos, el socio solo ve lo suyo y nadie entra sin rol salvo las rutas públicas. Esto protege la plata del gimnasio y los datos personales de los socios, y deja al dueño tranquilo de que un error de programación no abre una puerta.

## Actores

- Administrador, coach y socio, como sujetos de los controles.
- Atacante externo o curioso en la LAN, contra quien se diseñan los controles.
- Pipeline de CI, que hace cumplir las pruebas de arquitectura de seguridad.

## Capacidades incluidas

- Hash y verificación de contraseñas con argon2id.
- JWT firmado con Ed25519, vida de 15 minutos; creación de refresh tokens de 7 días (la tabla y la revocación las pone EP-04). Llave privada por archivo o volumen, nunca en la imagen.
- Dependencias de FastAPI `current_user` y `require_role("admin" | "coach" | "member")`; cada endpoint declara su rol (RN-15).
- Prueba de arquitectura `test_every_route_has_role.py`: recorre las rutas registradas y falla si alguna no tiene dependencia de rol y no está en la lista blanca (`/health`, `/auth/login`, `/auth/refresh`, `/auth/forgot`, `/auth/reset`, `/tv/today`).
- Rate limit de 5 intentos por minuto por IP en `login` y `forgot` (`slowapi` MIT o contador en memoria).
- CORS solo para el dominio del front, desde `CORS_ORIGINS`.
- Nginx: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Permissions-Policy`, CSP con nonce para el front, `client_max_body_size 5m`.
- Logs sin datos personales: prueba de que ni un token ni un campo cifrado aparecen en la salida de log.
- Gestión de secretos: ningún secreto en código ni en imágenes; todo por `.env`, con `.env.example` versionado y validación de presencia al arrancar.
- Reglas de rol explícitas que `BRECHAS.md` sección 5 pide declarar: `DELETE /members/{id}`, `POST /memberships/{id}/cancel` y `POST /payments/{id}/void` son solo admin. Se verifican en las épicas de cada módulo con esta dependencia.
- En el front (dentro del kit de EP-06 y de EP-04): ocultar acciones según rol, sabiendo que el API vuelve a verificar.

## Fuera de alcance

- Usuarios, sesiones, activación y recuperación (EP-04).
- TLS y Caddy (EP-20).
- Cifrado de datos en reposo (EP-02).

## Criterios de éxito medibles

- La prueba de arquitectura de rutas falla si se agrega un endpoint sin rol.
- El sexto intento de login en un minuto desde la misma IP recibe 429.
- Un JWT vencido, firmado con otra llave o con el algoritmo cambiado es rechazado (prueba de "alg confusion").
- Un coach recibe 403 en anular pago, anular membresía, dar de baja socio, planes y sistema; un socio recibe 403 en todo lo que no es `/me/*`.
- La respuesta del front servida por Nginx trae las cinco cabeceras de seguridad y la CSP (prueba con `curl -I` en CI o smoke).
- Una petición CORS desde un origen no listado es rechazada.

## Dependencias

- EP-01 Núcleo compartido (config, errores, logging).
- EP-00 Cimientos (Nginx y lint `banned-api`).

## Riesgos

- Un rate limit en memoria se reinicia con el proceso y no se comparte entre réplicas; aceptable con un solo proceso.
- CSP con nonce exige que el build de Vite no inyecte scripts en línea; puede chocar con librerías del front.
- En v0.1 el sistema corre por HTTP en la LAN (supuesto de P7): los tokens viajan sin TLS hasta EP-20.

## Pantallas del diseño que habilita

- Ninguna propia. Condiciona qué ve cada rol en todas (sección "Permisos" de `ROUTES.md`).
