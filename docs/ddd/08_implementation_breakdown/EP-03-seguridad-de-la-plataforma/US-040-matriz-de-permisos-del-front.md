# US-040 · Matriz de permisos única del front — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-03-seguridad-de-la-plataforma/US-040-matriz-de-permisos-del-front.md`
- **Épica:** EP-03 · Seguridad de la plataforma
- **Bounded context / módulo:** presentación (`web/src/core/auth/permissions.ts`, `web/src/core/auth/Can.tsx`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

La matriz sale de la sección "Permisos" de `ROUTES.md` más las decisiones de rol de DECISIONES.md (Q6, Q7, Q8 y N-20). Los nombres de acción los define esta historia, que es su dueña. Las rutas del API que respaldan cada acción ya tienen rol declarado en sus historias. No hay backend ni contrato HTTP nuevo.

## Resumen

`permissions.ts` exporta la lista cerrada `ACTIONS` (tupla `as const`), el tipo `Action`, el tipo `Role` y la matriz `MATRIX: Record<Action, readonly Role[]>`. `can(role, action)` niega por defecto: rol nulo, acción ausente o acción desconocida en tiempo de ejecución. `useCan(action)` lee el rol de la sesión (US-053) y, hasta que exista, de un contexto inyectable. `<Can action>` no renderiza sus hijos sin permiso. Una regla de ESLint prohíbe comparar el rol con literales fuera de `permissions.ts`. La tabla de verdad completa se prueba en Vitest.

## Correcciones aplicadas por DECISIONES.md

- La historia trae `members.update` como una sola acción → solo el admin cambia el documento (es identidad) y el coach edita el resto; existe la reactivación del socio, solo para admin, desde v0.1. Se agregan `members.document.update` (admin) y `members.reactivate` (admin). `members.update` queda para admin y coach: corregido por DECISIONES N-20.
- La historia no dice si el coach ve socios dados de baja → admin y coach los ven en la lista y en la ficha en solo lectura. `members.view` incluye los dados de baja y no hay acción aparte: corregido por DECISIONES N-20.
- Reveal, congelar y borrar asistencia para coach → `members.reveal`, `memberships.freeze` y `attendance.delete` en admin y coach: corregido por DECISIONES Q6, Q7 y Q8 (la historia ya los cita; se confirman).
- Grupo "Hoy" del menú → no es una pantalla ni una acción: son enlaces a pantallas que ya tienen su acción (`classes.view`, `wods.view`, `notifications.view`). No se crea `today.view`: corregido por DECISIONES Q25.
- Exportaciones de socios y pagos (v0.2) → solo admin: `members.export` y `payments.export` se dejan declaradas en admin para que EP-16 no toque la matriz: corregido por DECISIONES Q15 y N-29.

## Validación contra el dominio

- RN-15: coach no anula ni borra; socio solo lo suyo. Es la regla convertida en datos.
- Matriz propuesta (acción → roles):
  - Solo admin: `members.delete`, `members.reactivate`, `members.document.update`, `members.export`, `plans.view`, `plans.manage`, `memberships.cancel`, `payments.void`, `payments.export`, `audit.view`, `users.manage`, `settings.manage`, `crypto.manage`, `notifications.rules.edit`.
  - Admin y coach: `dashboard.view`, `members.view`, `members.create`, `members.update`, `members.reveal`, `members.history.view`, `memberships.view`, `memberships.sell`, `memberships.freeze`, `payments.view`, `payments.register`, `classes.view`, `attendance.delete`, `wods.view`, `movements.view`, `results.record`, `athletes.view`, `notifications.view`, `account.manage`.
  - Solo member: `me.home.view`, `me.payments.view`, `me.wods.view`, `me.results.submit`, `me.progress.view`, `me.profile.update`, `me.notifications.manage`.
- `plans.view` es la pantalla Planes, oculta para el coach según `ROUTES.md`. Vender usa `memberships.sell`, y el selector de planes de la venta no depende de `plans.view` (US-079 criterio 9).
- `members.history.view` respalda `GET /members/{id}/audit`, que es de admin y coach (US-106). `audit.view` es la pantalla de auditoría, solo admin (US-102).
- `account.manage` ("Mi cuenta" del panel, US-045 y US-061) es de admin y coach. El socio cambia su contraseña desde `/mi/datos` con `me.profile.update`. Así se cumple el criterio 4: el member solo tiene acciones `me.*`.
- Eventos: ninguno. Función pura: `can(role: Role | null, action: Action | string) -> boolean`.

## Validación contra la arquitectura

- Ubicación: `web/src/core/auth/` (estructura de `05_service_design.md` sección 5). La consumen `shared/ui` (`SideNav`, `MaskedValue`) y las features.
- Seguridad real en el API: cada acción tiene detrás un endpoint con `require_role` (US-034). El front solo oculta.
- Sin colores literales (no hay estilos).
- Front condicionado a D1.

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
- [ ] T1 · `web/src/core/auth/permissions.test.ts`: tabla de verdad generada desde una copia literal de la matriz esperada (3 roles por todas las acciones) con `it.each`; los casos explícitos de los criterios 1 a 4; `can(null, x)` es falso; `can("coach", "pagos.anular" as Action)` es falso en tiempo de ejecución; `// @ts-expect-error` sobre `can("coach", "no.existe")` demuestra que el tipo lo impide (criterio 5) — 2 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T2 · `web/eslint.config.js`: regla `no-restricted-syntax` con selectores para `BinaryExpression[operator=/^[!=]==?$/]` donde un lado es `Literal[value=/^(admin|coach|member)$/]` y el otro es un `MemberExpression` o `Identifier` llamado `role`, y para `SwitchCase` sobre `role`; desactivada solo en `src/core/auth/permissions.ts` y `src/core/auth/session.ts`. Más una prueba `web/tests/unit/no-role-literals.test.ts` que corre ESLint sobre un archivo fixture con `role === "admin"` y espera el error (criterio 7) — 2 h

### Front
- [ ] T3 · `web/src/core/auth/permissions.ts`: `ROLES`, `type Role`, `ACTIONS` (`as const`) con las acciones de la matriz, `type Action`, `MATRIX` con `satisfies Record<Action, readonly Role[]>` (si falta una acción, no compila) y `can()` con `Object.hasOwn` y negación por defecto — 2 h
- [ ] T4 · `web/src/core/auth/useCan.ts`: `RoleContext` (`React.createContext<Role | null>(null)`) y `useCan(action: Action): boolean`. Hasta US-053 el rol llega por `RoleProvider`; US-053 lo conecta a `session.ts` sin cambiar la firma — 1 h
- [ ] T5 · `web/src/core/auth/Can.tsx`: `<Can action fallback?>`, que renderiza `children` si `useCan(action)` y si no `fallback ?? null` — 0,5 h
- [ ] T6 · `web/src/core/auth/Can.test.tsx` (Testing Library): con `RoleProvider value="coach"`, `<Can action="payments.void"><button>Anular</button></Can>` no renderiza el botón y `<Can action="payments.register">` sí; con `admin` aparece "Anular" (escenarios BDD); sin proveedor (rol nulo) no renderiza nada — 2 h
- [ ] T7 · Alinear consumidores ya escritos: US-066 usa `useCan("member.reveal")` y US-072 usa `useCan("member.create")` (en singular). Los nombres canónicos son `members.reveal` y `members.create`, y el tipo `Action` impide compilar los otros. Se anota en esas historias — 0,5 h

### DevOps
- [ ] T8 · El job del front en `.github/workflows/ci.yml` ya corre `npm run lint` y `npm test` (US-003); verificar que `permissions.test.ts` y `no-role-literals.test.ts` entran en el patrón de Vitest — 0,5 h

### Seguridad
- [ ] T9 · Revisión: ningún componente decide visibilidad con el rol directo; denegar por defecto; la matriz no se usa para decidir nada en el API (el API tiene `require_role`); un cambio en la matriz debe acompañar al rol del endpoint correspondiente (lista de comprobación en la plantilla de PR) — 0,5 h

## Orden de ejecución
1. T1 (tabla de verdad en rojo)
2. T3
3. T4
4. T6 (en rojo)
5. T5
6. T2
7. T7
8. T8
9. T9

## Dependencias técnicas
- US-009 · Esqueleto del front: proyecto Vite, ESLint y Vitest.
- US-053 · Guardas de ruta por rol: conecta `useCan` con la sesión real y usa la matriz en `canAccessRoute`.
- US-061 · PanelLayout, TopBar y SideNav: oculta entradas del menú con `useCan`.
- US-066 · MaskedValue e historial y US-072 · Lista de socios en celular: deben usar los nombres canónicos (T7).
- US-034 · require_role: el API vuelve a verificar cada acción.

## Endpoints
- Ninguno.

## Riesgos
- Que la matriz y el rol del endpoint se desalineen (por ejemplo, el front muestra "Congelar" y el API responde 403) — mitigación: lista de comprobación en el PR y las pruebas E2E por rol de cada feature; a futuro se puede generar la matriz desde `docs/openapi.json` (fuera de alcance).
- Acciones de versiones futuras (clases, WODs, portal) declaradas antes de que existan sus pantallas — impacto nulo (solo ocultan); mitigación: las features nuevas agregan acciones en el mismo PR y la tabla de verdad obliga a declararlas.
- Front condicionado a D1: si el gate no aprueba el front en `web/`, esta historia sale completa.
- P6 (coach que también es socio, v1.1): la matriz por rol único no lo cubre — mitigación: supuesto aceptado de v1.1; `can` recibe un solo rol en v0.1.

## Estimación
- Backend: 0 h
- Front: 4 h
- Pruebas: 6 h
- DevOps / seguridad: 1 h
- **Total: 11 h**

## Definición de hecho
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/core/auth`
- [ ] `cd web && npm test -- tests/unit/no-role-literals.test.ts`
- [ ] `grep -rnE "role\s*[!=]==?\s*['\"](admin|coach|member)['\"]" web/src --include=*.ts --include=*.tsx | grep -v "core/auth/"` no devuelve nada
- [ ] Cobertura ≥ 80 % en lo tocado: `cd web && npx vitest run src/core/auth --coverage --coverage.thresholds.lines=80`
