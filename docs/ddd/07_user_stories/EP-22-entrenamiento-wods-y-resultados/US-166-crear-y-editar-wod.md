# US-166 · Como coach quiero crear y editar el WOD con sus movimientos, reps y cargas RX para publicar el entrenamiento del día

- **Épica:** EP-22 · Entrenamiento: movimientos, WODs y resultados
- **Bounded context:** Training (esquema `wods`, módulo `wods`)
- **Versión:** v0.5
- **Actor:** administrador, coach
- **Tamaño:** 8
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `WOD_Form` (`/wods/nuevo`, `/wods/:id/editar`)

## Historia

Como coach
quiero crear y editar un WOD con fecha, tipo de marca, time cap y sus movimientos con reps y cargas RX por sexo
para publicar el entrenamiento del día y que los resultados se registren contra él

## Contexto de dominio

- **Aggregate / entidades:** `Wod` (raíz): `date`, `title`, `score_type` (`time` | `rounds_reps` | `reps` | `load`), `time_cap_s`, `is_benchmark`, `description`. Entidad interna `WodMovement`: `movement_id`, `order`, `reps`, `load_rx_m_kg`, `load_rx_f_kg`, `notes`, `is_primary`.
- **Reglas que aplica:** copia de valores (cambiar el catálogo después no cambia WODs pasados); un WOD principal por fecha; Q19: `wod_movements.is_primary`, a lo sumo uno por WOD (índice único parcial); `score_type` decide los campos obligatorios del resultado.
- **Eventos que emite:** `WodPublished(wod_id, date)`
- **Eventos que consume:** ninguno
- **Funciones puras:** `wods.validate_wod(score_type, time_cap_s, movements)`

## Alcance

- **Backend:** modelos `Wod` y `WodMovement`, auditados; `wods.service.create`, `update`, `get`; el `create` reemplaza la lista completa de movimientos en una transacción; lee el catálogo por el propio módulo.
- **Front:** `WOD_Form` con fecha, título, tipo de marca, time cap, benchmark, descripción y lista ordenable de movimientos (selector de movimientos activos, reps, carga RX hombre, carga RX mujer, notas, marca de principal).

## Criterios de aceptación

1. `POST /api/v1/wods` con datos válidos y al menos un movimiento crea el WOD, responde 201 y emite `WodPublished`.
2. `score_type` fuera del enum, `time_cap_s` negativo o una lista de movimientos vacía devuelven 422 con `field`.
3. Cada `WodMovement` copia el `movement_id` y guarda reps y cargas como valores propios; editar o desactivar el movimiento en el catálogo no cambia el WOD (prueba con un WOD pasado).
4. Marcar dos movimientos como `is_primary` en el mismo WOD devuelve 422; el índice único parcial lo impide también en la base.
5. Ya existe un WOD principal para la fecha: crear otro con la misma fecha devuelve 409 con `existing_id`.
6. Las cargas son enteros o decimales de kg mayores o iguales a 0; un valor negativo devuelve 422.
7. `PATCH /api/v1/wods/{id}` actualiza los campos y reemplaza los movimientos; si el WOD ya tiene resultados registrados, no se permite cambiar `score_type` (422 `score_type_locked`).
8. Solo admin y coach (`require_role("admin", "coach")`); un `member` recibe 403.
9. `date` es una fecha civil (sin hora); `created_at` y `updated_at` en UTC.
10. Crear y editar quedan en auditoría con antes y después (`__audited__ = True` en `wods.wods` y `wods.wod_movements`).

## Escenarios BDD

```gherkin
# language: es
Característica: Crear y editar WOD

  Escenario: El coach publica el WOD de mañana
    Dado que inicié sesión como coach
    Y el catálogo tiene "Thruster" y "Pull-up" activos
    Cuando creo el WOD "Fran" para el 22 oct 2026 con tipo de marca "time", time cap de 600 segundos
    Y agrego "Thruster" con 21-15-9 reps, 43 kg hombre, 30 kg mujer, marcado como principal
    Y agrego "Pull-up" con 21-15-9 reps
    Entonces el WOD queda publicado para el 22 oct 2026
    Y se emite el evento WodPublished

  Escenario: Dos movimientos principales
    Dado que estoy creando un WOD
    Cuando marco "Thruster" y "Pull-up" como principales
    Entonces el sistema rechaza el WOD indicando que solo puede haber un movimiento principal
```

## Endpoints

- `POST /api/v1/wods` — rol(es): admin, coach — entrada: `{ date, title, score_type, time_cap_s?, is_benchmark, description?, movements: [{ movement_id, order, reps, load_rx_m_kg?, load_rx_f_kg?, notes?, is_primary }] }` — salida: WOD con movimientos — códigos: 201, 401, 403, 409, 422
- `PATCH /api/v1/wods/{id}` — rol(es): admin, coach — entrada: campos parciales y `movements` completo — salida: WOD — códigos: 200, 401, 403, 404, 409, 422
- `GET /api/v1/wods/{id}` — rol(es): admin, coach — salida: WOD con movimientos — códigos: 200, 401, 403, 404

## Pantalla

- `WOD_Form` en `/wods/nuevo` y `/wods/:id/editar`: formulario con React Hook Form + Zod y lista de movimientos ordenable. Estados de guardado y error por campo.

## Notas técnicas

- **Migración:** sí; `wods.wods` (índice único sobre `date`) y `wods.wod_movements` (FK a `wods.wods`, FK a `wods.movements`, índice único parcial `(wod_id) WHERE is_primary`).
- **Trigger / restricciones:** CHECK de `score_type`; cargas `>= 0`.
- **Funciones puras a probar:** `validate_wod` con lista vacía, dos principales, time cap negativo.
- **Pruebas:** service con base real (copia de valores tras editar el catálogo, unicidad por fecha, bloqueo de `score_type` con resultados), router, front.
- **Archivos principales:** `api/src/app/modules/wods/*`, `web/src/features/wods/pages/WodFormPage.tsx`.

## Supuestos

- Supuesto: "un WOD principal por fecha" se implementa como unicidad de `wods.wods.date`. Con esa unicidad, el WOD distinto que se asigna a una sesión concreta (US-168) tiene que ser un WOD existente de otra fecha (por ejemplo, un benchmark). Si el box necesita dos WODs nuevos el mismo día, hay que relajar la unicidad con un campo `is_main` (pregunta abierta).
- Supuesto: no se permite cambiar `score_type` de un WOD con resultados, porque invalidaría el `Score` ya validado.

## Dependencias

- US-165 · Catálogo de movimientos (selector)

## INVEST

- **Independiente:** solo depende del catálogo.
- **Negociable:** formato de reps (texto como "21-15-9") ajustable.
- **Valiosa:** sin WOD no hay resultados ni leaderboard.
- **Estimable:** dos tablas y un formulario conocido.
- **Pequeña:** cabe en un sprint con el formulario como mayor esfuerzo.
- **Testeable:** unicidades y copia de valores verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `wods.wods` y `wods.wod_movements`
- [ ] Revisión de PR aprobada
