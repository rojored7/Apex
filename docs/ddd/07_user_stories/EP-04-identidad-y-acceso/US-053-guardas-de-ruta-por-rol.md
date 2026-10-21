# US-053 · Como administrador o coach quiero que el front solo me deje entrar a las pantallas de mi rol para no ver opciones que no puedo usar

- **Épica:** EP-04 · Identidad y acceso
- **Bounded context:** Auth (front `web/src/core/auth/`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Todas las rutas de `ROUTES.md` (guardas sobre `routes.tsx`)

## Historia

Como administrador o coach
quiero que el front me lleve a mi inicio según mi rol y me impida abrir pantallas que no me corresponden
para no encontrarme con opciones que el sistema después me va a negar

## Contexto de dominio

- **Aggregate / entidades:** `User` (rol del token).
- **Reglas que aplica:** RN-15; sección "Permisos" de `ROUTES.md` (coach no ve Sistema ni Planes; socio solo `/mi/*`); el front oculta y el API vuelve a verificar.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `canAccessRoute(role, path) -> boolean` y `homeFor(role) -> "/" | "/mi"` en `web/src/core/auth/`.

## Alcance

- **Backend:** No aplica (el API ya responde 401 y 403 por US-034).
- **Front:** `core/auth/session.ts` (estado de sesión), componente `RequireAuth` y `RequireRole` sobre `routes.tsx`, redirección a `/login?next=` sin sesión, a `homeFor(role)` tras login, y página "Sin permiso" para rutas de otro rol.

## Criterios de aceptación

1. Sin sesión, cualquier ruta distinta de `/login`, `/recuperar`, `/restablecer/:token` y `/tv` redirige a `/login?next=<ruta>`.
2. Tras iniciar sesión, si hay `next` permitido para el rol se navega ahí; si no, a `/` para `admin` y `coach` y a `/mi` para `member`.
3. Un coach que abre `/planes` o cualquier `/sistema/*` ve la página "Sin permiso" con un enlace a `/`, y el `SideNav` no muestra esas entradas.
4. Un usuario `member` que abre cualquier ruta del panel es redirigido a `/mi`; un `admin` o `coach` que abre `/mi/*` es redirigido a `/`.
5. `canAccessRoute` usa la misma matriz de permisos de US-040; agregar una ruta a `routes.tsx` sin declarar sus roles hace fallar una prueba.
6. Un 403 del API en una pantalla permitida muestra el mensaje del envelope sin cerrar la sesión; un 401 que no se puede renovar lleva a `/login`.
7. Las guardas no hacen peticiones extra: el rol sale de la respuesta de login o de `GET /auth/me` al recargar la página.

## Escenarios BDD

```gherkin
# language: es
Característica: Guardas de ruta por rol

  Escenario: El admin entra a su inicio
    Dado un admin que acaba de iniciar sesión
    Entonces el front lo lleva a "/"
    Y el menú muestra "Planes" y "Sistema"

  Escenario: El coach no abre planes
    Dado un coach con sesión
    Cuando escribe "/planes" en la barra de direcciones
    Entonces ve la página "Sin permiso"
    Y el menú no muestra "Planes" ni "Sistema"

  Escenario: Sin sesión se pide ingresar
    Dado que no hay sesión
    Cuando abre "/socios"
    Entonces el front lo lleva a "/login?next=/socios"

  Escenario: Ruta sin roles declarados
    Dado una ruta nueva en "routes.tsx" sin roles
    Cuando corre la prueba de rutas
    Entonces la prueba falla
```

## Endpoints

- Ninguno nuevo. Usa `GET /api/v1/auth/me` (US-045) al recargar.

## Pantalla

- Todas las rutas del panel y del portal; página "Sin permiso". `// DESIGN-GAP:` la página "Sin permiso" no está en el diseño.

## Notas técnicas

- **Migración:** no.
- **Funciones puras a probar:** `canAccessRoute` y `homeFor` para los tres roles con cada ruta de `ROUTES.md`.
- **Pruebas:** Vitest de guardas y funciones puras, prueba que recorre `routes.tsx` y exige roles, E2E Playwright "coach no ve Planes".
- **Archivos principales:** `web/src/core/auth/session.ts`, `RequireAuth.tsx`, `RequireRole.tsx`, `web/src/routes.tsx`.

## Supuestos

- Ninguno.

## Dependencias

- US-042 · Iniciar sesión
- US-040 · Matriz de permisos del front
- US-067 · Mapa de rutas
- US-045 · GET /auth/me (se usa al recargar la página para restaurar la sesión; agregado en consolidación)

## INVEST

- **Independiente:** solo front; el API ya protege.
- **Negociable:** el diseño de "Sin permiso" es libre.
- **Valiosa:** cada rol ve solo lo suyo.
- **Estimable:** dos componentes y dos funciones puras.
- **Pequeña:** dos o tres días.
- **Testeable:** cada combinación rol y ruta es binaria.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] Lint y `tsc` estricto del front en verde
- [ ] Pruebas de funciones puras y componentes en verde; cobertura de 80 % o más en `core/auth`
- [ ] E2E de rol denegado en verde
- [ ] Sin colores literales
- [ ] Revisión de PR aprobada
