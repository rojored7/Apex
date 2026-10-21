# US-053 · Guardas de ruta por rol — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-04-identidad-y-acceso/US-053-guardas-de-ruta-por-rol.md`
- **Épica:** EP-04 · Identidad y acceso
- **Bounded context / módulo:** Auth, solo front (`web/src/core/auth/`, `web/src/routes.tsx`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

Es una historia solo de front y no toca contratos del API. Usa `GET /auth/me` (US-045) y `POST /auth/refresh` (US-043) para restaurar la sesión al recargar, porque el access token vive solo en memoria (N-13). La matriz de permisos se reutiliza de US-040, y la forma de enlazar rutas y acciones queda definida aquí.

## Resumen

Cada ruta de `routes.tsx` declara `access`. El valor es `"public"` o una acción de `permissions.ts` (US-040), por ejemplo `plans.view`, `users.manage` o `me.view`. `canAccessRoute(role, path)` busca la ruta y delega en `can(role, action)`. `homeFor(role)` devuelve `/` para `admin` y `coach` y `/mi` para `member`. Hay dos componentes de guarda:

- `RequireAuth`: sin sesión, intenta restaurarla con una sola secuencia, refresh y después `GET /auth/me`. Si no lo logra, lleva a `/login?next=<ruta>`.
- `RequireRole`: muestra "Sin permiso" o redirige (`member` a `/mi`, y el panel lejos de `/mi/*`).

Un 403 del API muestra el mensaje del envelope sin cerrar la sesión. Una prueba recorre `routes.tsx` y falla si alguna ruta no declara `access`.

## Correcciones aplicadas por DECISIONES.md

- Restaurar la sesión al recargar requiere un `POST /auth/refresh` antes de `GET /auth/me`, porque el access token vive solo en memoria y la cookie de refresh es `HttpOnly`. El criterio 7 dice que "el rol sale de login o de `GET /auth/me` al recargar". Se cumple con esa secuencia, que corre una sola vez por carga de página y no en cada navegación. Coherente con DECISIONES N-13.
- La ruta pública `/tv` recibe el token de dispositivo una sola vez por la query y después lo manda en `X-Device-Token`. La guarda la trata como pública sin sesión: coherente con DECISIONES N-44 (la TV llega en v0.5; aquí solo queda en la lista de rutas públicas).

## Validación contra el dominio

- Entidad: `User`, del que solo interesa el rol del principal.
- RN-15: el front oculta y el API vuelve a verificar. El coach no ve Sistema ni Planes; el socio solo ve `/mi/*`.
- Funciones puras: `canAccessRoute(role: Role, path: string): boolean` y `homeFor(role: Role): "/" | "/mi"` en `web/src/core/auth/routeAccess.ts`. Además `safeNext(next: string | null, role): string | null`, que solo acepta rutas relativas internas (empiezan por `/`, no por `//` ni por un esquema) y permitidas para el rol.
- No emite ni consume eventos.

## Validación contra la arquitectura

- Front en `web/src/core/auth/`. No se crean endpoints, y el backend sigue protegiendo cada ruta (US-034 y US-035).
- No hay comparaciones de rol con cadenas literales fuera de `permissions.ts` (criterio 7 de US-040). `canAccessRoute` y `homeFor` usan `can` y constantes.
- Sin colores literales: la página "Sin permiso" usa los tokens y los componentes del kit.
- Peticiones: las guardas no consultan el API en cada navegación. La restauración se hace una vez, con una promesa compartida en `session.ts`.

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
- [ ] T1 · Vitest `web/src/core/auth/routeAccess.test.ts`:
  - `canAccessRoute` para los tres roles con cada ruta de `ROUTES.md`; por ejemplo, el coach no entra a `/planes` ni a `/sistema/*` y `member` solo entra a `/mi/*`;
  - `homeFor` para los tres roles;
  - `safeNext` rechaza `//evil.com`, `https://x` y una ruta de otro rol. — 1.5 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T2 · Vitest `web/src/routes.test.ts`: recorre el árbol exportado por `routes.tsx` y falla si una ruta no declara `access`, o si declara una acción que no existe en `permissions.ts` (además del chequeo de tipos). — 0.5 h

### Front
- [ ] T3 · `web/src/core/auth/routeAccess.ts`:
  - funciones `canAccessRoute`, `homeFor` y `safeNext`;
  - tipo `RouteAccess = "public" | Action`;
  - los metadatos `access` en cada ruta de `web/src/routes.tsx`. Las públicas son `/login`, `/recuperar`, `/restablecer/:token` y `/tv`; `/planes` lleva `plans.view` y `/sistema/*` lleva `users.manage` o `settings.manage`. — 2 h
- [ ] T4 · En `web/src/core/auth/session.ts`, `restoreSession()`: promesa compartida que hace `POST /auth/refresh` y luego `GET /auth/me` (US-045) y llena `user`. Se llama una vez al montar la app.

  `web/src/core/auth/RequireAuth.tsx`:
  - mientras se restaura, muestra un estado de carga;
  - sin sesión, navega a `/login?next=<ruta actual>`.

  En `LoginPage` (US-042), usar `safeNext` y `homeFor` para redirigir. — 2.5 h
- [ ] T5 · `web/src/core/auth/RequireRole.tsx`:
  - un `member` en una ruta del panel va a `/mi`;
  - un `admin` o `coach` en `/mi/*` va a `/`;
  - si no, cuando `!canAccessRoute`, se muestra `web/src/core/auth/NoPermissionPage.tsx`: "Sin permiso", con un enlace a `homeFor(role)` y la marca `// DESIGN-GAP: la página "Sin permiso" no está en el diseño`.

  El `SideNav` filtra sus entradas con `canAccessRoute`. — 1.5 h
- [ ] T6 · En `web/src/core/api/client.ts`, un 403 publica el mensaje del envelope en el sistema de avisos del kit (US-065 o el toast existente) y no limpia la sesión. Un 401 sin renovación posible ya lleva a `/login` (US-043). — 0.5 h
- [ ] T7 · Vitest `web/src/core/auth/RequireAuth.test.tsx` y `RequireRole.test.tsx`:
  - sin sesión en `/socios` lleva a `/login?next=/socios`;
  - un coach en `/planes` ve "Sin permiso" y el menú no muestra Planes ni Sistema;
  - un `member` en `/socios` va a `/mi`;
  - un admin en `/mi` va a `/`;
  - al recargar, se restaura con un refresh y un `me` (se cuentan las llamadas);
  - un 403 muestra el mensaje y la sesión sigue. — 1.5 h
- [ ] T8 · Playwright `web/tests/e2e/role-guards.spec.ts`: "coach no ve Planes". El coach escribe `/planes` en la barra y ve "Sin permiso", y el menú no muestra Planes ni Sistema. El admin ve los dos. — 1.5 h

### DevOps
- No aplica.

### Seguridad
- [ ] T9 · Revisión:
  - `next` no permite redirecciones abiertas (`safeNext`);
  - las guardas no reemplazan al API (prueba de US-035 vigente);
  - ningún token en `localStorage`;
  - el rol no se deduce del JWT en el cliente, sino de la respuesta de login o de `me`. — 0.5 h

## Orden de ejecución
1. T1 y T2 (en rojo)
2. T3
3. T7 (en rojo)
4. T4
5. T5
6. T6
7. T8
8. T9

## Dependencias técnicas
- US-040 · Matriz de permisos del front: `can`, `Action` y `permissions.ts`.
- US-042 · Iniciar sesión: `session.ts`, `homeFor` y `LoginPage`.
- US-043 · Renovar sesión: refresh y `client.ts`.
- US-045 · `GET /auth/me`.
- US-067 · Mapa de rutas (`routes.tsx`).
- US-061 · `SideNav`.

## Endpoints
- Ninguno.

## Riesgos
- Si `ROUTES.md` cambia de rutas y no se actualiza `routes.tsx`, la matriz queda desfasada. Mitigación: T2 exige `access` en cada ruta, y la prueba del API (US-035) sigue protegiendo.
- Mientras se restaura la sesión al recargar, se muestra una pantalla de carga. Si el refresh tarda (por ejemplo, con la LAN lenta), la experiencia empeora. Mitigación: es una sola petición en serie con `me`, y hay timeout en `client.ts`.
- Front condicionado a D1.

## Estimación
- Backend: 0 h
- Front: 6.5 h
- Pruebas: 5 h
- DevOps / seguridad: 0.5 h
- **Total: 12 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .` (sin cambios en el API; debe seguir verde)
- [ ] `cd api && uv run mypy src` (sin cambios en el API; debe seguir verde)
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/core/auth src/routes.test.ts`
- [ ] `cd web && npx playwright test tests/e2e/role-guards.spec.ts`
- [ ] `cd api && uv run pytest tests/architecture -q` (debe seguir verde; esta historia no toca el API)
- [ ] Abrir `http://localhost/socios` sin sesión lleva a `/login?next=/socios`; abrir `http://localhost/login?next=//evil.com` y entrar como admin lleva a `/`.
- [ ] Recargar `/socios` con sesión hace exactamente un `POST /api/v1/auth/refresh` y un `GET /api/v1/auth/me` (pestaña Red del navegador o traza de Playwright).
- [ ] Cobertura ≥ 80 % en `web/src/core/auth`: `cd web && npm test -- --coverage src/core/auth`
