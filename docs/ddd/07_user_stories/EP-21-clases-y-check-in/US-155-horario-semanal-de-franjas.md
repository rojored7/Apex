# US-155 · Como administrador quiero definir el horario semanal de franjas para que las clases se generen solas con su hora, cupo y coach

- **Épica:** EP-21 · Clases, horario y check-in
- **Bounded context:** Classes (esquema `classes`)
- **Versión:** v0.4
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica de la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Horario` (`/clases/horario`)

## Historia

Como administrador
quiero crear, editar y desactivar las franjas del horario semanal
para que el sistema sepa qué clases hay cada día, a qué hora, con qué cupo y qué coach

## Contexto de dominio

- **Aggregate / entidades:** `ClassSlot` (`weekday` 0 a 6, `start_time`, `duration_min`, `capacity`, `default_coach_id`, `is_active`).
- **Reglas que aplica:** Q23 (editar o desactivar una franja afecta solo a las sesiones aún no generadas); Q11 (`default_capacity` de `settings.classes` como valor inicial del cupo); RN-15 (solo admin); RN-14 (no se borran: se desactivan).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `classes.validate_slot(weekday, start_time, duration_min, capacity) -> None | ClassError`

## Alcance

- **Backend:** modelo y migración `classes.class_slots` con `__audited__ = True`; `GET/POST /api/v1/class-slots`, `PATCH /api/v1/class-slots/{id}`; `default_coach_id` validado con `auth.service` (usuario activo con rol coach o admin).
- **Front:** pantalla `Horario` con grilla semanal, crear y editar en `SidePanel`, activar y desactivar.

## Criterios de aceptación

1. `GET /class-slots` y las escrituras exigen rol `admin`; coach recibe 403 en `POST` y `PATCH`, y 403 en `GET` (la pantalla es solo admin).
2. `POST` valida: `weekday` de 0 (lunes) a 6 (domingo); `start_time` `HH:MM` en hora de Bogotá; `duration_min` de 15 a 240; `capacity` entero mayor o igual a 1; si no se envía `capacity` toma `settings.classes.default_capacity`; errores devuelven 422 con `field`.
3. Dos franjas activas con el mismo `weekday` y `start_time` devuelven 409.
4. `default_coach_id` debe ser un usuario activo con rol `coach` o `admin`; otro valor devuelve 422.
5. `PATCH` con `is_active=false` desactiva la franja; no existe `DELETE`.
6. Editar o desactivar una franja no modifica ninguna `ClassSession` ya generada (prueba con una sesión existente).
7. `GET /class-slots` pagina con `limit`/`offset` (máximo 200) y filtra por `is_active` y `weekday`.
8. Cada alta y cambio queda auditado con antes y después.

## Escenarios BDD

```gherkin
# language: es
Característica: Horario semanal

  Escenario: El administrador crea la franja de las 6:00 de los lunes
    Dado que inicié sesión como administrador
    Y el cupo por defecto es 15
    Cuando creo una franja el lunes a las 06:00 de 60 minutos con la coach "Sara"
    Entonces la franja queda activa con cupo 15
    Y aparece en la grilla del lunes

  Escenario: Franja duplicada
    Dado que existe una franja activa el lunes a las 06:00
    Cuando intento crear otra el lunes a las 06:00
    Entonces recibo 409
```

## Endpoints

- `GET /api/v1/class-slots` — rol(es): admin — entrada: `is_active?`, `weekday?`, `limit`, `offset` — salida: `{ items, total, limit, offset }` — códigos: 200, 401, 403, 422
- `POST /api/v1/class-slots` — rol(es): admin — entrada: `{ weekday, start_time, duration_min, capacity?, default_coach_id }` — códigos: 201, 401, 403, 409, 422
- `PATCH /api/v1/class-slots/{id}` — rol(es): admin — códigos: 200, 401, 403, 404, 409, 422

## Pantalla

- `Horario` en `/clases/horario`: grilla semanal, `SidePanel` de edición, estados de carga, vacío ("aún no hay franjas") y error.

## Notas técnicas

- **Migración:** sí; esquema `classes`, tabla `class_slots` con columnas comunes; índice único parcial `(weekday, start_time) WHERE is_active`.
- **Trigger / restricciones:** `CHECK weekday BETWEEN 0 AND 6`, `CHECK capacity >= 1`.
- **Funciones puras a probar:** `validate_slot` con límites.
- **Pruebas:** puras, service con base real (409, coach válido, no toca sesiones), router (rol), front.
- **Archivos principales:** `api/src/app/modules/classes/{models,schemas,service,router}.py`, `web/src/features/classes/pages/SchedulePage.tsx`.

## Supuestos

- Supuesto: `start_time` se guarda como hora local de Bogotá (tipo `TIME` sin zona) porque es una plantilla semanal; la conversión a `starts_at` UTC ocurre al generar la sesión (Colombia no tiene horario de verano).
- Supuesto: rango de `duration_min` de 15 a 240 minutos.

## Dependencias

- US-154 · Configurar horas y clases (cupo por defecto)
- US-016 · Hook de auditoría

## INVEST

- **Independiente:** CRUD de plantilla, sin sesiones.
- **Negociable:** forma de la grilla.
- **Valiosa:** base de toda la operación de clases.
- **Estimable:** modelo, tres endpoints y una pantalla.
- **Pequeña:** cabe en un sprint.
- **Testeable:** validaciones y 409 verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `class_slots`
- [ ] Revisión de PR aprobada
