# US-059 · Cliente API y tipos generados — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-06-layout-y-componentes-front/US-059-cliente-api-y-tipos-generados.md`
- **Épica:** EP-06 · Layout y componentes compartidos del front
- **Bounded context / módulo:** presentación (`web/src/core/api/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

El contrato que consume ya está fijado: base `/api/v1`, envelope de error, `Page<T>` y `limit` máximo de 200. La estrategia de sesión que la historia deja abierta ("`credentials` según la estrategia de sesión") la cierra DECISIONES N-13: el access token va en memoria y el refresh en una cookie HttpOnly. El refresh con una sola petición compartida es de US-043; esta historia solo deja el gancho.

## Resumen

Construye la única puerta del front hacia el API. Incluye `client.ts` (fetch con base `/api/v1`, cabecera `Authorization: Bearer` tomada de memoria, `credentials: "same-origin"` para la cookie de refresh, timeout, parseo del envelope a `ApiError` y gancho `onUnauthorized`), `errors.ts` (`ApiError`, `parseApiError`), `query.ts` (`toQueryString`, `listParams`) y `types.ts`, generado desde `docs/openapi.json` con `openapi-typescript`. También agrega el script `npm run gen:api`, el job de CI que falla si los tipos versionados están desactualizados y la regla de ESLint que prohíbe `fetch` fuera de `core/api/`.

## Correcciones aplicadas por DECISIONES.md

- "`credentials` según la estrategia de sesión" (indefinido en la historia) → el access token solo vive en memoria (nunca en `localStorage` ni `sessionStorage`) y el refresh viaja en cookie HttpOnly, por eso el cliente usa `credentials: "same-origin"`: corregido por DECISIONES N-13.
- Consecuencia de N-13 (reusar un refresh ya rotado revoca todas las sesiones del usuario) → el gancho `onUnauthorized` debe permitir a US-043 hacer un solo refresh compartido. El cliente nunca llama a `/auth/refresh` por su cuenta, y el criterio 4 (una sola invocación por petición) se prueba con peticiones concurrentes: corregido por DECISIONES N-13.
- Envelope con 503 `crypto_unavailable` (OpenBao sellado) → el cliente lo trata como un `ApiError` con su `code` y no como `network_error`: aceptado por DECISIONES N-16.
- Fuente de los tipos → `types.ts` se genera desde el archivo versionado `docs/openapi.json` y no desde el servidor, porque `/openapi.json` está apagado en producción: aceptado por DECISIONES N-14.

## Validación contra el dominio

- No hay aggregates: consume el contrato HTTP de todos los módulos.
- RN-01: el dinero viaja como `number` entero. El cliente no lo transforma; lo formatea `format.ts` (US-060).
- Fechas en ISO 8601 UTC, sin conversión en el cliente (criterio 8, regla de datos 2).
- Contrato de listas `{ items, total, limit, offset }` (regla de datos 6, D2). `listParams` nunca envía `limit` mayor que 200.
- Funciones puras: `parseApiError(status, body) -> ApiError`, `toQueryString(params) -> string` y `listParams(params) -> Record<string, string>`.

## Validación contra la arquitectura

- Capas de backend: no aplica (la historia no toca `api/`; consume `docs/openapi.json` de US-021).
- Estructura del front de `05_service_design.md` 5: `web/src/core/api/client.ts`, `errors.ts`, `query.ts` y `types.ts`. Las features usan el cliente desde su `api.ts` con TanStack Query.
- Seguridad de la arquitectura (sección 6): el cliente no registra en consola cuerpos ni tokens (criterio 9), y el token solo existe en memoria (N-13).
- Licencias: `openapi-typescript` (MIT) y `msw` (MIT) están permitidas.

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
- [ ] T1 · `web/src/core/api/errors.test.ts` y `query.test.ts` (Vitest): `parseApiError` con envelope completo, sin `field`, con `existing_id`, con cuerpo no JSON, con cuerpo vacío (los dos últimos dan `code: "network_error"` y un mensaje en español) y con 503 `crypto_unavailable`; `toQueryString` omite `undefined` y `null` y repite arreglos (`status=a&status=b`); `listParams` convierte 500 en 200, 0 en 25 y `undefined` en 25 — 1 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T2 · `web/tests/lint/no-direct-fetch.test.ts`: ESLint programático sobre dos fixtures; `fetch(` en `src/features/x/api.ts` falla, y en `src/core/api/client.ts` pasa; `console.log` en `core/api/` falla — 0.5 h
- [ ] T3 · `web/src/core/api/types.contract.test-d.ts` (`expectTypeOf` de Vitest): `Page<MemberRow>` tiene `items`, `total`, `limit` y `offset`, y una lectura de `member.cedula` lleva `// @ts-expect-error`, así que `tsc` falla si alguien quita el comentario (criterio 6) — 0.5 h

### Front
- [ ] T4 · `web/src/core/api/errors.ts`: `class ApiError extends Error { status; code; message; field?; existingId? }` y `parseApiError(status, body)`, con mensajes genéricos en español ("No pudimos conectar con el servidor. Intenta de nuevo.") — 1 h
- [ ] T5 · `web/src/core/api/query.ts`: `toQueryString(params)`, `listParams({ limit, offset, ...filtros })` con `MAX_LIMIT = 200` y `DEFAULT_LIMIT = 25` como constantes — 1 h
- [ ] T6 · `web/src/core/api/client.ts`: `api.get/post/patch/delete<T>(path, { query, body, signal })` con `BASE = "/api/v1"`; `setAccessTokenGetter(fn)` (el token lo entrega la sesión en memoria, US-042 y US-043); `credentials: "same-origin"`; timeout de 15 s con `AbortController` (`code: "timeout"`); 204 devuelve `undefined`; `registerOnUnauthorized(handler)` invocado como máximo una vez por petición ante 401 (si el handler resuelve `retry`, se reintenta una vez; si no hay handler, se propaga el `ApiError`); sin `console.*` — 2.5 h
- [ ] T7 · `web/src/core/api/types.ts` generado y versionado; `web/package.json` con `"gen:api": "openapi-typescript ../docs/openapi.json -o src/core/api/types.ts"` y `openapi-typescript` en versión exacta; `web/src/core/api/page.ts` con `type Page<T> = { items: T[]; total: number; limit: number; offset: number }`, comprobado contra el esquema de lista del contrato — 1.5 h
- [ ] T8 · `web/eslint.config.js`: `no-restricted-globals` (`fetch`) y `no-console` con override solo para `src/core/api/**` (`fetch` permitido) — 0.5 h
- [ ] T9 · `web/src/core/api/client.test.ts` (Vitest + MSW): 200 tipado; 409 con `existing_id`; 422 con `field`; 502 sin cuerpo da `network_error`; timeout; tres peticiones concurrentes con 401 invocan `onUnauthorized` una vez cada una y el handler compartido es uno solo (contrato para US-043); `Authorization` presente cuando hay token; espía de `console` sin llamadas — 2 h

### DevOps
- [ ] T10 · `.github/workflows/ci.yml`: job `web-contract` que corre `npm ci && npm run gen:api && git diff --exit-code src/core/api/types.ts` y `npx tsc --noEmit` (criterio 5) — 1 h

### Seguridad
- [ ] T11 · Revisión: el token nunca va a `localStorage`, `sessionStorage` ni la URL; `credentials` nunca es `"include"` (no hay orígenes cruzados en v0.1, P7); no se registran cuerpos — 0.5 h

## Orden de ejecución
1. T1 (en rojo)
2. T4
3. T5
4. T7
5. T3
6. T9 (en rojo)
7. T6
8. T2 (en rojo)
9. T8
10. T10
11. T11

## Dependencias técnicas
- US-009 · Esqueleto del front: proyecto Vite, ESLint y Vitest.
- US-021 · Exportación de OpenAPI: `docs/openapi.json` versionado.
- US-017 / US-019 · Envelope de error y contrato de listas del API: la forma que parsea el cliente.
- US-043 · Renovación de sesión: conecta `registerOnUnauthorized` con el refresh compartido entre pestañas; no bloquea esta historia.

## Endpoints
- Ninguno.

## Riesgos
- Front condicionado a D1: si el gate no aprueba S1, la historia sale del repositorio.
- Un `openapi.json` incompleto mientras no existan los módulos genera tipos vacíos y oculta errores — mitigación: T3 fija un tipo de prueba; cada historia de backend regenera el contrato en su definición de hecho.
- Que el reintento automático tras el refresh duplique una escritura no idempotente (por ejemplo, un pago) — mitigación: el reintento solo ocurre cuando el 401 llegó antes de procesar (código `token_expired`, US-043); se prueba en T9 y en US-043.
- Que un cambio de `openapi-typescript` cambie la forma de `types.ts` — mitigación: versión exacta en `package.json` y diff en CI.

## Estimación
- Backend: 0 h
- Front: 6.5 h
- Pruebas: 4 h
- DevOps / seguridad: 1.5 h
- **Total: 12 h**

## Definición de hecho
- [ ] Backend: no aplica (la historia no toca `api/`); `cd api && uv run pytest tests/architecture -q` sigue verde en CI
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/core/api tests/lint`
- [ ] `cd web && npm run gen:api && git diff --exit-code src/core/api/types.ts`
- [ ] `grep -rn "fetch(" web/src --include=*.ts --include=*.tsx | grep -v src/core/api` no devuelve nada
- [ ] Quitar el `@ts-expect-error` de `types.contract.test-d.ts` hace fallar `npx tsc --noEmit` (verificación manual en el PR)
- [ ] Cobertura ≥ 80 % en lo tocado: `cd web && npx vitest run --coverage src/core/api` con umbral 80 en `core/api/`
