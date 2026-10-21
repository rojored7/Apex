# US-040 · Como equipo quiero una matriz de permisos única en el front para que cada pantalla oculte las acciones que el rol no puede usar, sabiendo que el API vuelve a verificar

- **Épica:** EP-03 · Seguridad de la plataforma
- **Bounded context:** presentación (`web/src/core/auth/permissions.ts`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna propia (la usan todas)

## Historia

Como equipo
quiero `can(role, action)` y el hook `useCan(action)` con la matriz de la sección "Permisos" de `ROUTES.md`
para que el coach no vea botones de anular, dar de baja, planes ni sistema y el socio solo vea `/mi/*`, sin repetir reglas en cada pantalla

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** RN-15; `ROUTES.md` Permisos; Q6 (coach puede `reveal`), Q7 (coach congela), Q8 (coach borra asistencia).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `can(role, action) -> boolean`

## Alcance

- **Backend:** No aplica.
- **Front:** archivo `permissions.ts` con acciones nombradas (`members.create`, `members.update`, `members.delete`, `members.reveal`, `plans.view`, `plans.manage`, `memberships.sell`, `memberships.freeze`, `memberships.cancel`, `payments.register`, `payments.void`, `audit.view`, `users.manage`, `settings.manage`, `crypto.manage`, `notifications.rules.edit`, `attendance.delete`, y las de portal `me.*`). Hook `useCan` que lee el rol de la sesión (US-053). Componente `<Can action="...">` que no renderiza su contenido si no hay permiso.
- **Front (prueba):** tabla de verdad completa en Vitest.

## Criterios de aceptación

1. `can("coach", "payments.void")`, `can("coach", "memberships.cancel")`, `can("coach", "members.delete")`, `can("coach", "plans.manage")` y `can("coach", "settings.manage")` son `false`.
2. `can("coach", "members.reveal")`, `can("coach", "memberships.freeze")`, `can("coach", "memberships.sell")` y `can("coach", "payments.register")` son `true`.
3. `can("admin", x)` es `true` para toda acción de panel y `false` para las de portal `me.*`.
4. `can("member", x)` es `true` solo para acciones `me.*`.
5. Una acción desconocida devuelve `false` (denegar por defecto) y el tipo TypeScript impide escribir una acción que no existe.
6. `<Can action="payments.void">` no renderiza nada para un coach (prueba de componente).
7. Ningún componente compara el rol con cadenas literales: una regla de ESLint o una prueba de búsqueda falla si aparece `role === "admin"` fuera de `permissions.ts`.

## Escenarios BDD

```gherkin
# language: es
Característica: Matriz de permisos del front

  Escenario: Coach no ve anular pago
    Dado una sesión de coach
    Cuando se renderiza el detalle de un pago
    Entonces no aparece el botón "Anular"
    Y sí aparece el botón "Registrar pago"

  Escenario: Administrador ve todo el panel
    Dado una sesión de administrador
    Cuando se renderiza el detalle de un pago
    Entonces aparece el botón "Anular"

  Escenario: Acción desconocida
    Cuando se consulta un permiso que no está en la matriz
    Entonces la respuesta es negar
```

## Endpoints

- Ninguno. El API vuelve a verificar con `require_role` (US-034).

## Pantalla

- Ninguna propia.

## Notas técnicas

- **Migración:** no.
- **Funciones puras a probar:** `can` con tabla de verdad por rol y acción.
- **Pruebas:** Vitest y Testing Library.
- **Archivos principales:** `web/src/core/auth/permissions.ts`, `web/src/core/auth/Can.tsx`, `web/src/core/auth/permissions.test.ts`.

## Supuestos

- Supuesto: los nombres de acción se definen aquí (no existen en los documentos); se alinean con los endpoints del contrato.

## Dependencias

- US-009 · Esqueleto del front

## INVEST

- **Independiente:** solo el esqueleto; la sesión real llega en US-053 y aquí se usa un rol inyectado.
- **Negociable:** granularidad de acciones.
- **Valiosa:** una sola fuente de verdad para lo que ve cada rol.
- **Estimable:** una tabla y un hook.
- **Pequeña:** dos días.
- **Testeable:** tabla de verdad.

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
