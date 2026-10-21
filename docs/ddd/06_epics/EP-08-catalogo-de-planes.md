# EP-08 · Catálogo de planes

- **Versión del plan:** v0.1 (Tarea 5).
- **Bounded context:** Plans (negocio, esquema `plans`).
- **Estimación relativa:** S.

## Objetivo de negocio

Que el dueño defina qué vende y a qué precio (mensualidad, trimestre, tiquetera de clases) y pueda subir precios o retirar un plan sin afectar lo que ya se vendió.

## Actores

- Administrador: único que crea, edita, activa y desactiva planes.
- Coach: solo lista los planes activos para vender (`GET /plans?active=true`).
- Memberships: lee el plan al vender (Conformist).

## Capacidades incluidas

### Backend
- Aggregate `Plan`: `name`, `price_cop` (value object `Money`, entero mayor que 0, RN-01), `kind` (`days` | `classes`), `duration_days` (siempre presente, P2), `class_count` (obligatorio si `kind = classes`), `is_active`, `deleted_at`; auditado.
- Función pura `plans.validate_plan(kind, duration_days, class_count)`.
- RN-08: un plan con membresías activas no se borra, solo se desactiva; `deactivate_or_fail` consulta `memberships.service.count_active_by_plan(plan_id)`, la única llamada en sentido contrario documentada en el mapa de contextos.
- RN-04 desde el lado de Plans: cambiar el precio no toca membresías vendidas (lo garantiza la copia en EP-09).
- Eventos `PlanCreated`, `PlanUpdated`, `PlanDeactivated`.
- Endpoints solo admin: `GET/POST /plans`, `GET/PATCH /plans/{id}`, `POST /plans/{id}/activate`, `POST /plans/{id}/deactivate`.

### Front
- Pantalla de planes con lista, crear y editar en `SidePanel`, y activar o desactivar. El formulario pide duración en días y número de clases cuando el tipo es por clases.
- Oculta la entrada de menú para el coach.

## Fuera de alcance

- Promociones, descuentos o precios por socio.
- Planes por varias sedes.

## Criterios de éxito medibles

- No se puede dar de baja un plan con membresías activas; se desactiva (criterio de salida de la Tarea 5).
- Un plan `classes` sin `class_count` o un precio con decimales devuelve 422.
- Cambiar el precio de un plan no cambia `agreed_price_cop` de ninguna membresía existente (prueba conjunta con EP-09).
- Un coach recibe 403 en crear y editar y 200 en listar activos.

## Dependencias

- EP-04 Identidad y acceso.
- EP-06 Layout y componentes compartidos del front.
- EP-09 Membresías, para cerrar RN-08 (la consulta `count_active_by_plan`); hasta entonces la baja se prueba con un doble.

## Riesgos

- P2 sin confirmar: si los planes por clases no tienen vigencia máxima, cambia el formulario y la regla de fin.
- La única dependencia inversa (Plans → Memberships) puede crecer si no se vigila; queda documentada como excepción.

## Pantallas del diseño que habilita

- `Planes`.
