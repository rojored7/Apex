# US-195 · Como socio quiero recibir un push cuando logro un récord personal para celebrar mi progreso en el momento

- **Épica:** EP-25 · Portal del socio
- **Bounded context:** Notifications (esquema `notifications`), consume eventos de Athletes
- **Versión:** v1.0
- **Actor:** socio
- **Tamaño:** 3
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (historia sin front; el aviso aparece en `Portal_Avisos`)

## Historia

Como socio
quiero que cuando el sistema registre un récord mío me llegue una notificación push
para enterarme y sentir que mi esfuerzo cuenta

## Contexto de dominio

- **Aggregate / entidades:** `Notification`, `NotificationRule` con trigger nuevo `personal_record_set`, `NotificationTemplate`.
- **Reglas que aplica:** Q13 (los avisos de récord llegan en v1.0 con push al socio), RN-17 (idempotencia), preferencias de canal del socio.
- **Eventos que emite:** `NotificationQueued`, `NotificationSent`, `NotificationFailed`
- **Eventos que consume:** `PersonalRecordSet`
- **Funciones puras:** `notifications.render(template, context)` con variables nuevas `{movimiento}` y `{marca}`

## Alcance

- **Backend:** valor nuevo `personal_record_set` en `NotificationRule.trigger`; handler `on_personal_record_set` que crea un `Notification(pending)` por regla activa con canal `push`; el envío lo hace el job o un envío inmediato posterior al commit (ver Supuesto).
- **Front:** No aplica (las reglas se configuran en `Notif_Reglas`, que admite el nuevo disparador).

## Criterios de aceptación

1. Las reglas aceptan `trigger = personal_record_set` solo con `channel = push` y `offset_days = 0`; otra combinación devuelve 422.
2. Un `PersonalRecordSet` con regla activa crea un `Notification` `pending` con `target_date` = fecha de Bogotá del récord y `rendered_body` con el movimiento o benchmark y la marca.
3. La unicidad de RN-17 se mantiene: para este disparador la clave es (`rule_id`, `record_id`); un mismo récord no genera dos avisos.
4. Si el socio no tiene suscripción push activa o desactivó el canal, el aviso queda `skipped` con `skip_reason = sin canal` y no se envía.
5. El envío usa `WebPushChannel` (US-194); un fallo deja `failed` con `last_error`.
6. Si el handler falla al crear el aviso, el récord no se revierte por esta causa (ver Supuesto) y el error queda en el log sin datos personales.

## Escenarios BDD

```gherkin
# language: es
Característica: Aviso de récord nuevo

  Escenario: Récord con push activo
    Dado que existe una regla activa de récord personal por push
    Y que "Juan" tiene push activo
    Cuando el coach valida un resultado de "Juan" que crea un RM de 100 kg en "Deadlift"
    Entonces "Juan" recibe un push con "Deadlift" y "100 kg"

  Escenario: Socio sin suscripción push
    Dado que "Marta" no tiene push activo
    Cuando se registra un récord de "Marta"
    Entonces el aviso queda omitido con el motivo "sin canal"
```

## Endpoints

- Ninguno nuevo (amplía `POST/PATCH /api/v1/notification-rules` con el disparador nuevo; rol admin).

## Pantalla

- Ninguna propia; `Notif_Reglas` muestra el disparador "Récord personal".

## Notas técnicas

- **Migración:** sí; columna `record_id` nullable en `notifications.notifications` y restricción única parcial (`rule_id`, `record_id`) `WHERE record_id IS NOT NULL`; ampliar el CHECK de `trigger`. La restricción de RN-17 existente sobre (`rule_id`, `membership_id`, `target_date`) pasa a parcial `WHERE membership_id IS NOT NULL` (cambio en dos pasos, sin editar migraciones aplicadas).
- **Trigger / restricciones:** las anteriores.
- **Funciones puras a probar:** `render` con las variables nuevas.
- **Pruebas:** service con el evento; idempotencia; canal simulado.
- **Archivos principales:** `api/src/app/modules/notifications/service.py`, `models.py`, `schemas.py`.

## Supuestos

- Supuesto: el aviso de récord se crea en un handler posterior al commit (o lo recoge el job en su siguiente corrida) para que un fallo del aviso no revierta la validación del resultado; esto se aparta de la regla general de handlers en la misma transacción (`02_domain_model.md` sección 3) y debe confirmarse en el gate.
- Supuesto: el envío del push de récord es inmediato (no espera al job de las 07:00); si no se acepta, sale al día siguiente.
- Supuesto: `Notification.membership_id` pasa a ser opcional para este disparador (un récord no depende de una membresía); el modelo actual lo trata como obligatorio.

## Dependencias

- US-194 · Suscripción web push
- US-181 · Récord derivado por carga (emite `PersonalRecordSet`)

## INVEST

- **Independiente:** un disparador nuevo sobre el canal existente.
- **Negociable:** inmediato o en la corrida diaria.
- **Valiosa:** motivación del socio.
- **Estimable:** un handler, una migración y una plantilla.
- **Pequeña:** pocos días.
- **Testeable:** unicidad por récord y omisión sin canal.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] Auditoría verificada para avisos
- [ ] Revisión de PR aprobada
