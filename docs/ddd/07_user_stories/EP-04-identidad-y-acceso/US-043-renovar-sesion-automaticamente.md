# US-043 · Como administrador o coach quiero que mi sesión se renueve sola mientras trabajo para no tener que volver a ingresar cada 15 minutos

- **Épica:** EP-04 · Identidad y acceso
- **Bounded context:** Auth (esquema `auth`, módulo `auth`) y `web/src/core/api`
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna propia (transversal a todas las pantallas del panel)

## Historia

Como administrador o coach
quiero que el sistema renueve mi acceso en segundo plano mientras mi sesión de 7 días siga vigente
para atender recepción sin interrupciones cada 15 minutos

## Contexto de dominio

- **Aggregate / entidades:** `User`, `RefreshToken`.
- **Reglas que aplica:** refresh rota el token y revoca el anterior (`05_service_design.md` 3, `auth.service.refresh`); "un refresh token ya usado no sirve una segunda vez" (EP-04); bloquear impide el uso de sesiones.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `auth.is_refresh_usable(token, now) -> bool` (no revocado, no vencido, usuario activo y no bloqueado).

## Alcance

- **Backend:** `auth.service.refresh(refresh_token)` y `POST /auth/refresh` (público en la lista blanca, autenticado por la cookie de refresh).
- **Front:** en `core/api/client.ts`, ante un 401 con código `token_expired`, un solo refresh compartido entre peticiones concurrentes y entre pestañas, reintento de la petición original y redirección a `/login` si el refresh falla.

## Criterios de aceptación

1. `POST /api/v1/auth/refresh` con una cookie de refresh vigente responde 200 con un access token nuevo de 15 minutos y una cookie de refresh nueva; en la misma transacción el token anterior queda con `revoked_at` en UTC.
2. Usar por segunda vez un refresh token ya rotado responde 401 `unauthorized`, no emite tokens y revoca todas las sesiones del usuario, porque es señal de robo (N-13).
3. Un refresh vencido (`expires_at` en el pasado), revocado, o de un usuario bloqueado, inactivo o con `deleted_at`, responde 401 `unauthorized`.
4. Sin cookie responde 401 `unauthorized`; el cuerpo de la petición se ignora.
5. Un access token vencido en cualquier endpoint protegido responde 401 con código `token_expired`, distinto de `invalid_token`.
6. El front, ante `token_expired`, hace como máximo un `POST /auth/refresh` aunque haya varias peticiones en vuelo, y reintenta cada una una sola vez.
7. Con dos pestañas abiertas, solo una pestaña ejecuta el refresh y la otra recibe el token nuevo por `BroadcastChannel`; ninguna queda deslogueada por usar el token rotado.
8. Si el refresh responde 401, el front borra el access token de memoria y navega a `/login` conservando la ruta de origen en `?next=`.
9. El valor del refresh token nunca se escribe en logs del API ni en la consola del navegador.

## Escenarios BDD

```gherkin
# language: es
Característica: Renovar la sesión automáticamente

  Antecedentes:
    Dado un coach con sesión iniciada hace 16 minutos y refresh vigente

  Escenario: Renovación transparente
    Cuando abre la lista de socios y el access token ya venció
    Entonces el front pide un refresh una sola vez
    Y la lista de socios se muestra sin volver a ingresar
    Y el refresh anterior queda revocado

  Escenario: Refresh reutilizado
    Dado un refresh token que ya fue rotado
    Cuando se envía otra vez a "/auth/refresh"
    Entonces recibe 401 con código "unauthorized"

  Escenario: Usuario bloqueado mientras trabajaba
    Dado que el admin bloqueó al coach
    Cuando el front intenta renovar la sesión
    Entonces recibe 401 con código "unauthorized"
    Y el front lo lleva a "/login?next=/socios"

  Escenario: Dos pestañas abiertas
    Dado el coach tiene "/socios" y "/pagos" abiertos en dos pestañas
    Cuando ambas detectan el token vencido al mismo tiempo
    Entonces solo se hace un refresh
    Y las dos pestañas siguen con sesión
```

## Endpoints

- `POST /api/v1/auth/refresh` — rol(es): público (lista blanca; autentica la cookie) — entrada: cookie de refresh — salida: `{ access_token, token_type, expires_in }` y cookie nueva — códigos: 200, 401.

## Pantalla

- Ninguna. Afecta a todas las pantallas del panel a través de `client.ts`.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** la rotación se hace con `SELECT ... FOR UPDATE` sobre la fila del refresh para que dos peticiones simultáneas no roten el mismo token dos veces.
- **Funciones puras a probar:** `is_refresh_usable` con vencido, revocado, usuario bloqueado y vigente.
- **Pruebas:** service con base real (rotación atómica, reutilización), router (401 por causa), front (Vitest de `client.ts` con peticiones concurrentes simuladas y `BroadcastChannel`).
- **Archivos principales:** `api/src/app/modules/auth/service.py`, `router.py`; `web/src/core/api/client.ts`, `web/src/core/auth/session.ts`.

## Supuestos

- Decidido (N-13): reutilizar un refresh ya rotado revoca todas las sesiones del usuario, no solo responde 401.
- Supuesto: la coordinación entre pestañas usa `BroadcastChannel` y un candado en memoria.

## Dependencias

- US-042 · Iniciar sesión (emite el primer refresh)

## INVEST

- **Independiente:** solo depende del login.
- **Negociable:** el mecanismo de coordinación entre pestañas se puede cambiar.
- **Valiosa:** evita que recepción pierda el trabajo cada 15 minutos.
- **Estimable:** un endpoint y un interceptor.
- **Pequeña:** dos o tres días.
- **Testeable:** concurrencia y reutilización son escenarios binarios.

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
- [ ] Front: pruebas de `client.ts`; sin colores literales
- [ ] Migración aplicada con `alembic upgrade head` y reversible (no aplica)
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para las tablas tocadas (no aplica)
- [ ] Revisión de PR aprobada
