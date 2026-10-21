# US-120 · Como administrador quiero mantener plantillas de aviso con variables para que cada recordatorio diga lo correcto sin escribirlo a mano

- **Épica:** EP-14 · Avisos de vencimiento
- **Bounded context:** Notifications (esquema `notifications`)
- **Versión:** v0.2
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Notif_Reglas` (`/avisos/reglas`, pestaña Plantillas)

## Historia

Como administrador
quiero crear, editar y listar plantillas de aviso con variables `{nombre}`, `{plan}`, `{vence}` y `{dias}`
para que los recordatorios de vencimiento salgan con un texto uniforme y correcto para cada socio

## Contexto de dominio

- **Aggregate / entidades:** `NotificationTemplate` (`name`, `subject`, `body`). Esta historia crea también el esquema `notifications` y las tablas base de `NotificationRule` y `Notification` que usan US-121 y US-124.
- **Reglas que aplica:** variables permitidas solo `{nombre}`, `{plan}`, `{vence}`, `{dias}` (`02_domain_model.md` 2.10); RN-14 no aplica (las plantillas no están en la lista de borrado lógico ni en la de prohibido); auditoría de cambios.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `notifications.render(template, context) -> str`

## Alcance

- **Backend:** módulo `notifications` (router, schemas, models, service), migración del esquema, CRUD de plantillas, validación de variables, vista previa con datos de ejemplo.
- **Front:** pestaña Plantillas de `Notif_Reglas`: lista, crear y editar en `SidePanel`, vista previa renderizada.

## Criterios de aceptación

1. `POST /api/v1/notification-templates` con `name`, `subject` y `body` crea la plantilla y responde 201; `name` es único y un duplicado responde 409.
2. Un `body` o `subject` que contiene una variable fuera de `{nombre}`, `{plan}`, `{vence}`, `{dias}` responde 422 con `field` igual a `body` o `subject`.
3. `notifications.render` reemplaza cada variable por su valor; `{vence}` se formatea como fecha civil de Bogotá (`20 oct 2026`) y `{dias}` como entero; una variable sin valor en el contexto lanza error (no deja la llave literal).
4. `GET /api/v1/notification-templates` pagina con `limit` (1 a 200, por defecto 25) y `offset`, acepta `q` sobre `name` y responde `{ items, total, limit, offset }`.
5. `PATCH /api/v1/notification-templates/{id}` actualiza y deja fila de auditoría con antes y después (`__audited__ = True`).
6. Una plantilla usada por una regla activa no se puede borrar: no existe endpoint `DELETE`; ver Supuestos.
7. `POST /api/v1/notification-templates/preview` devuelve el texto renderizado con un contexto de ejemplo, sin datos reales de socios.
8. Crear, editar y previsualizar exigen rol `admin`; el coach recibe 403 al escribir y 200 al listar.
9. `created_at` y `updated_at` se devuelven en ISO 8601 UTC.

## Escenarios BDD

```gherkin
# language: es
Característica: Plantillas de aviso

  Antecedentes:
    Dado que inicié sesión como administrador

  Escenario: Crear una plantilla válida y verla renderizada
    Cuando creo la plantilla "Vence pronto" con cuerpo "Hola {nombre}, tu {plan} vence el {vence} (faltan {dias} días)"
    Entonces la respuesta es 201
    Y la vista previa con nombre "Ana", plan "Mensual", vence "2026-10-20" y días 3 dice "Hola Ana, tu Mensual vence el 20 oct 2026 (faltan 3 días)"
    Y queda una fila de auditoría de tipo "insert" en "notification_templates"

  Escenario: Rechazar una variable desconocida
    Cuando creo una plantilla con cuerpo "Hola {apodo}"
    Entonces la respuesta es 422
    Y el error tiene "field" igual a "body"
```

## Endpoints

- `GET /api/v1/notification-templates` — rol(es): admin, coach — entrada: `q`, `limit`, `offset` — salida: página de plantillas — códigos: 200, 401, 403, 422
- `POST /api/v1/notification-templates` — rol(es): admin — entrada: `name`, `subject`, `body` — salida: plantilla — códigos: 201, 401, 403, 409, 422
- `GET /api/v1/notification-templates/{id}` — rol(es): admin, coach — códigos: 200, 401, 403, 404
- `PATCH /api/v1/notification-templates/{id}` — rol(es): admin — códigos: 200, 401, 403, 404, 409, 422
- `POST /api/v1/notification-templates/preview` — rol(es): admin — entrada: `subject`, `body` — salida: texto renderizado — códigos: 200, 422

## Pantalla

- `Notif_Reglas`, pestaña Plantillas, en `/avisos/reglas`: tabla de plantillas, `SidePanel` de edición con vista previa en vivo, estados de carga, vacío y error. El coach ve la lista sin botones de edición (`useCan`).

## Notas técnicas

- **Migración:** sí. Esquema `notifications`, tabla `notification_templates` (`id`, `name` único, `subject`, `body`, columnas comunes). Las tablas `notification_rules` y `notifications` se crean en US-121 y US-124 con su propia migración.
- **Trigger / restricciones:** índice único en `name`.
- **Funciones puras a probar:** `render` con las cuatro variables, con variable faltante en el contexto, con texto sin variables, con llaves escapadas.
- **Pruebas:** puras de `render` y del validador de variables; service con base real; router con rol y 422; Vitest de la vista previa.
- **Archivos principales:** `api/src/app/modules/notifications/{router,schemas,models,service}.py`, `web/src/features/notifications/`.

## Supuestos

- Supuesto: no hay borrado de plantillas en v0.2 (no está en el contrato ni en las reglas); una plantilla sin uso simplemente se deja de asignar.
- Supuesto: `subject` solo lo usa el canal correo; WhatsApp usa solo `body`.
- Supuesto: existe un endpoint de vista previa; el diseño lo sugiere pero ningún documento lo define.

## Dependencias

- US-016 · Hook de auditoría (auditar cambios)
- US-034 · require_role (roles por endpoint)
- US-061 · PanelLayout (pantalla)

## INVEST

- **Independiente:** solo depende del núcleo; no requiere reglas ni envío.
- **Negociable:** la vista previa y el formato de fecha pueden ajustarse.
- **Valiosa:** elimina mensajes improvisados y errores de redacción.
- **Estimable:** CRUD conocido más una función pura.
- **Pequeña:** cabe en un sprint (5).
- **Testeable:** `render` es pura y los 422 son verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para las tablas tocadas
- [ ] Revisión de PR aprobada
