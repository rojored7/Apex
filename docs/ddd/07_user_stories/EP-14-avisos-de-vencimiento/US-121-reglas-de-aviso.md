# US-121 · Como administrador quiero definir reglas de aviso relativas al vencimiento para que el sistema sepa cuándo y por qué canal recordar a cada socio

- **Épica:** EP-14 · Avisos de vencimiento
- **Bounded context:** Notifications (esquema `notifications`)
- **Versión:** v0.2
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Notif_Reglas` (`/avisos/reglas`)

## Historia

Como administrador
quiero crear, editar, activar y desactivar reglas de aviso con disparador, días de desfase, canal y plantilla
para que los recordatorios salgan 3 días antes, el día del vencimiento y 1, 7 y 15 días después sin que nadie tenga que acordarse

## Contexto de dominio

- **Aggregate / entidades:** `NotificationRule` (`name`, `trigger`, `offset_days`, `channel`, `template_id`, `is_active`).
- **Reglas que aplica:** `trigger` solo `membership_expiring` o `membership_expired` (Q13); `offset_days` negativo antes del fin, positivo después; canales de v0.2 solo `email` y `whatsapp_link` (N-34; Q14: `push` llega en v1.0, US-194).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** validación de coherencia `trigger`/`offset_days` (ver criterio 3)

## Alcance

- **Backend:** tabla `notification_rules`, CRUD, activar/desactivar, semilla de las cinco reglas por defecto.
- **Front:** `Notif_Reglas`: lista de reglas con estado, `SidePanel` para crear y editar, interruptor de activa; coach solo lectura.

## Criterios de aceptación

1. `POST /api/v1/notification-rules` crea una regla con `name`, `trigger`, `offset_days` (entero), `channel`, `template_id` y `is_active`; responde 201.
2. `trigger` fuera de `membership_expiring` / `membership_expired` responde 422 con `field = trigger`; `channel` fuera de `email` y `whatsapp_link` responde 422 con `field = channel` (incluido `push` en v0.2).
3. `membership_expiring` exige `offset_days <= 0`; `membership_expired` exige `offset_days >= 1`; lo contrario responde 422 con `field = offset_days`.
4. `template_id` inexistente responde 422 con `field = template_id`.
5. No puede haber dos reglas activas con el mismo (`trigger`, `offset_days`, `channel`): la segunda responde 409.
6. `GET /api/v1/notification-rules` pagina con `limit`/`offset` (máx. 200) y filtra por `is_active`, `channel` y `trigger`.
7. `PATCH /api/v1/notification-rules/{id}` permite cambiar todos los campos y `is_active`; desactivar una regla no borra ni cancela los avisos ya generados.
8. No existe borrado de reglas; se desactivan.
9. `cli seed` (o la migración de datos de esta historia como comando idempotente) crea las cinco reglas por defecto: -3, 0 (`membership_expiring`), 1, 7, 15 (`membership_expired`), canal `whatsapp_link`, si no existen.
10. Escritura solo `admin`; el coach recibe 403 al crear o editar y 200 al listar.
11. Cada cambio queda auditado (`__audited__ = True`).

## Escenarios BDD

```gherkin
# language: es
Característica: Reglas de aviso

  Antecedentes:
    Dado que inicié sesión como administrador
    Y existe la plantilla "Vence pronto"

  Escenario: Crear la regla de tres días antes
    Cuando creo la regla "3 días antes" con disparador "membership_expiring", desfase -3, canal "email" y plantilla "Vence pronto"
    Entonces la respuesta es 201
    Y la regla aparece activa en la lista de reglas

  Escenario: Rechazar un desfase incoherente con el disparador
    Cuando creo una regla con disparador "membership_expired" y desfase -3
    Entonces la respuesta es 422
    Y el error tiene "field" igual a "offset_days"

  Escenario: Rechazar el canal push en v0.2
    Cuando creo una regla con canal "push"
    Entonces la respuesta es 422
```

## Endpoints

- `GET /api/v1/notification-rules` — rol(es): admin, coach — entrada: `is_active`, `channel`, `trigger`, `limit`, `offset` — códigos: 200, 401, 403, 422
- `POST /api/v1/notification-rules` — rol(es): admin — códigos: 201, 401, 403, 409, 422
- `GET /api/v1/notification-rules/{id}` — rol(es): admin, coach — códigos: 200, 404
- `PATCH /api/v1/notification-rules/{id}` — rol(es): admin — códigos: 200, 401, 403, 404, 409, 422

## Pantalla

- `Notif_Reglas` en `/avisos/reglas`: tabla de reglas (nombre, cuándo en lenguaje natural "3 días antes del vencimiento", canal, plantilla, activa), `SidePanel` de edición, estados de carga, vacío y error.

## Notas técnicas

- **Migración:** sí, tabla `notifications.notification_rules` con FK a `notification_templates`, índice único parcial (`trigger`, `offset_days`, `channel`) `WHERE is_active`.
- **Trigger / restricciones:** CHECK de `channel` y `trigger` como enum de PostgreSQL o CHECK; el valor `push` se agrega con migración en US-194.
- **Funciones puras a probar:** validación de signo de `offset_days` por disparador.
- **Pruebas:** puras; service con base real (409 por duplicado activo); router con rol; Vitest de la descripción en lenguaje natural.
- **Archivos principales:** `api/src/app/modules/notifications/`, `web/src/features/notifications/pages/RulesPage.tsx`.

## Supuestos

- Supuesto: el día del vencimiento (`offset_days = 0`) pertenece a `membership_expiring`, porque la membresía sigue vigente ese día (RN-06: vencido si hoy > fin).
- Supuesto: no se permiten dos reglas activas iguales en disparador, desfase y canal; ningún documento lo exige, evita avisos dobles.
- Supuesto: las cinco reglas por defecto usan `whatsapp_link`, el único canal que no depende de credenciales externas.

## Dependencias

- US-120 · Plantillas de aviso (la regla referencia una plantilla y comparte el esquema)

## INVEST

- **Independiente:** no necesita el job para entregarse.
- **Negociable:** reglas por defecto y su canal se pueden ajustar.
- **Valiosa:** formaliza cuándo se avisa.
- **Estimable:** CRUD con validaciones claras.
- **Pequeña:** 5.
- **Testeable:** cada 422 y 409 es binario.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para las tablas tocadas
- [ ] Revisión de PR aprobada
