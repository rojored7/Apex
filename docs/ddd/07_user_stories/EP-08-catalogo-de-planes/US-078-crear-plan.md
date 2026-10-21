# US-078 · Como administrador quiero crear un plan con precio en pesos y tipo por días o por clases para definir qué vende el gimnasio

- **Épica:** EP-08 · Catálogo de planes
- **Bounded context:** Plans (esquema `plans`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Planes` (`/planes`, panel lateral "Nuevo plan")

## Historia

Como administrador
quiero crear un plan con nombre, precio en COP, tipo (por días o por clases), duración en días y número de clases
para tener un catálogo de lo que vendo y poder venderlo a los socios sin calcular nada a mano

## Contexto de dominio

- **Aggregate / entidades:** `Plan` (raíz) con value object `Money` (`price_cop`).
- **Reglas que aplica:** RN-01 (dinero entero en COP, mayor que 0), P2 (todo plan tiene `duration_days`, también los de clases), invariante "`kind = classes` exige `class_count`; `kind = days` lo deja nulo", RN-14 (el plan admite baja lógica con `deleted_at`, ver US-082), RN-15 (solo admin).
- **Eventos que emite:** `PlanCreated`
- **Eventos que consume:** ninguno
- **Funciones puras:** `plans.validate_plan(kind, duration_days, class_count) -> None | PlanError`

## Alcance

- **Backend:** modelo `plans.plans` con `CommonColumnsMixin` y `__audited__ = True`, migración de Alembic del esquema `plans`, `schemas.py` (`PlanCreate`, `PlanOut`), `plans.service.create(data, by)`, función pura `validate_plan`, endpoint `POST /plans`.
- **Front:** `web/src/features/plans/`: botón "Nuevo plan" en `Planes`, `SidePanel` con formulario React Hook Form + Zod; el campo "Número de clases" aparece y es obligatorio solo cuando el tipo es "Por clases"; el precio se escribe y muestra con `format.ts` (`$ 120.000`).

## Criterios de aceptación

1. `POST /api/v1/plans` con `name`, `price_cop`, `kind`, `duration_days` y, si `kind = classes`, `class_count` crea el plan con `is_active = true` y responde 201 con el `PlanOut` completo (incluye `id`, `created_at` en UTC ISO 8601).
2. `price_cop` es entero mayor que 0; un valor con decimales (`120000.5`), negativo, cero o en texto devuelve 422 con `field = "price_cop"`.
3. `duration_days` es entero mayor que 0 y obligatorio para ambos tipos; ausente o menor o igual a 0 devuelve 422 con `field = "duration_days"`.
4. `kind = classes` sin `class_count`, o con `class_count` menor o igual a 0, devuelve 422 con `field = "class_count"`.
5. `kind = days` con `class_count` distinto de nulo devuelve 422 con `field = "class_count"`.
6. `name` vacío o solo espacios devuelve 422 con `field = "name"`; se guarda recortado.
7. `validate_plan` es una función pura sin acceso a base y tiene pruebas unitarias para las cuatro combinaciones de tipo y clase.
8. El endpoint declara `require_role("admin")`; un coach recibe 403 y una petición sin token 401, ambos con el envelope `{ "error": { "code", "message" } }`.
9. La creación deja una fila en `audit.audit_log` con `action = insert`, `table_name = plans`, el usuario y el `after` del plan.
10. Se emite `PlanCreated` dentro de la misma transacción; si un handler falla, el plan no queda creado.
11. `created_by` queda con el id del administrador autenticado.
12. En el front, el panel no permite enviar si el formulario es inválido y muestra el mensaje del campo devuelto por `field` cuando el API responde 422.

## Escenarios BDD

```gherkin
# language: es
Característica: Crear un plan

  Antecedentes:
    Dado que estoy autenticado como administrador

  Escenario: Crear un plan mensual por días
    Cuando creo el plan "Mensual" con precio 120000, tipo "days" y duración 30 días
    Entonces la respuesta es 201
    Y el plan "Mensual" queda activo con precio 120000 y sin número de clases
    Y queda una entrada de auditoría "insert" sobre "plans" con mi usuario

  Escenario: Crear una tiquetera por clases con vigencia máxima
    Cuando creo el plan "Tiquetera 12" con precio 150000, tipo "classes", duración 60 días y 12 clases
    Entonces la respuesta es 201
    Y el plan queda con 12 clases y 60 días de vigencia

  Escenario: Precio con decimales
    Cuando creo el plan "Mensual" con precio 120000.5, tipo "days" y duración 30 días
    Entonces la respuesta es 422
    Y el error señala el campo "price_cop"

  Escenario: Plan por clases sin número de clases
    Cuando creo el plan "Tiquetera" con precio 150000, tipo "classes" y duración 60 días sin número de clases
    Entonces la respuesta es 422
    Y el error señala el campo "class_count"

  Escenario: Plan por días con número de clases
    Cuando creo el plan "Mensual" con precio 120000, tipo "days", duración 30 días y 8 clases
    Entonces la respuesta es 422
    Y el error señala el campo "class_count"

  Escenario: Coach intenta crear un plan
    Dado que estoy autenticado como coach
    Cuando creo el plan "Mensual" con precio 120000, tipo "days" y duración 30 días
    Entonces la respuesta es 403
    Y no se crea ningún plan
```

## Endpoints

- `POST /api/v1/plans` — rol(es): admin — entrada: `{ name: str, price_cop: int, kind: "days"|"classes", duration_days: int, class_count: int|null }` — salida: `PlanOut { id, name, price_cop, kind, duration_days, class_count, is_active, created_at, updated_at }` — códigos: 201, 401, 403, 422.

## Pantalla

- `Planes` en `/planes`: botón "Nuevo plan" y `SidePanel` de creación. Estados: enviando (botón deshabilitado), error de campo, éxito (cierra el panel y refresca la lista). La entrada del menú está oculta para el coach (`useCan`).

## Notas técnicas

- **Migración:** sí. Crea el esquema `plans` y la tabla `plans.plans` (`id` UUID, `name` text, `price_cop` integer, `kind` text, `duration_days` integer, `class_count` integer null, `is_active` boolean default true, `deleted_at` timestamptz null, `created_at`, `updated_at`, `created_by`).
- **Trigger / restricciones:** `CHECK (price_cop > 0)`, `CHECK (duration_days > 0)`, `CHECK ((kind = 'classes' AND class_count > 0) OR (kind = 'days' AND class_count IS NULL))`, `CHECK (kind IN ('days','classes'))`.
- **Funciones puras a probar:** `validate_plan("days", 30, None)` ok; `validate_plan("classes", 60, 12)` ok; `validate_plan("classes", 60, None)` error `class_count`; `validate_plan("days", 30, 8)` error `class_count`; `validate_plan("days", 0, None)` error `duration_days`.
- **Pruebas:** pura; service con base real (auditoría y evento); router (rol, 422, envelope); front (formulario condicional y error de campo).
- **Archivos principales:** `api/src/app/modules/plans/{models,schemas,service,router,exceptions}.py`, `api/migrations/versions/<rev>_plans.py`, `web/src/features/plans/{api.ts,schemas.ts,components/PlanForm.tsx,pages/PlansPage.tsx}`.

## Supuestos

- Supuesto: el nombre del plan no tiene regla de unicidad (no está en el dominio); se admiten dos planes con el mismo nombre.

## Dependencias

- US-034 · Dependencias `current_user` y `require_role` (rol admin)
- US-016 · Hook de auditoría `after_flush`
- US-061 · PanelLayout con TopBar y SideNav
- US-065 · SidePanel y ConfirmModal

## INVEST

- **Independiente:** solo depende del núcleo y del kit del front; no necesita membresías.
- **Negociable:** el diseño del panel y los textos de ayuda se pueden ajustar; las validaciones son fijas.
- **Valiosa:** sin planes no se puede vender ninguna membresía.
- **Estimable:** una tabla, una función pura, un endpoint y un formulario.
- **Pequeña:** cabe en 3 a 4 días.
- **Testeable:** cada validación tiene un 422 con `field` concreto.

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
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `plans`
- [ ] Revisión de PR aprobada
