# US-124 · Como administrador quiero que cada mañana se genere la lista de avisos del día sin duplicados para no olvidar a nadie ni repetir mensajes

- **Épica:** EP-14 · Avisos de vencimiento
- **Bounded context:** Notifications (esquema `notifications`)
- **Versión:** v0.2
- **Actor:** administrador (ejecuta el worker)
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (historia sin front; el resultado se ve en US-127 y US-129)

## Historia

Como administrador
quiero que el worker cree a las 7:00 hora de Bogotá los avisos que corresponden según las reglas activas
para que cada socio que vence o venció reciba su recordatorio exactamente una vez por regla y fecha

## Contexto de dominio

- **Aggregate / entidades:** `Notification` (`rule_id`, `member_id`, `membership_id`, `target_date`, `channel`, `status`, `rendered_body`, `attempts`, `last_error`, `sent_at`, `sent_by`, `skip_reason`).
- **Reglas que aplica:** RN-17 (único por `rule_id`, `membership_id`, `target_date`); preferencias de canal (US-123); Q28 (`today_bogota()`); Q13 (solo disparadores de vencimiento); RN-06 (estados).
- **Eventos que emite:** `NotificationQueued`
- **Eventos que consume:** `MembershipExpiring`, `MembershipExpired` (para marcar membresías candidatas; ver notas)
- **Funciones puras:** `notifications.target_dates(rule, membership) -> list[date]`, `notifications.render(template, context)`

## Alcance

- **Backend:** tabla `notifications.notifications`; `notifications.service.generate_for(today)`; fase 1 del job `worker/jobs/notify.py` (generar); fase 2 (enviar) en US-125.
- **Front:** No aplica.

## Criterios de aceptación

1. `target_dates(rule, membership)` devuelve `[membership.end_date + rule.offset_days]`; para una membresía con `end_date = 2026-10-20` y las cinco reglas por defecto las fechas son 17, 20, 21 y 27 de octubre y 4 de noviembre de 2026.
2. El job, con `today = today_bogota()`, crea un `Notification` por cada regla activa y membresía no cancelada cuya fecha objetivo es hoy, con `status = pending`, `channel` de la regla y `rendered_body` ya renderizado.
3. Una regla `membership_expiring` solo genera si la membresía está en `active` o `expiring` ese día; una `membership_expired` solo si está en `expired` y el socio no tiene una membresía vigente o futura (renovó).
4. Si el canal de la regla no está activo en las preferencias del socio, el aviso se crea con `status = skipped` y `skip_reason = "canal desactivado por el socio"`.
5. Si el canal está deshabilitado en `settings.channels`, el aviso se crea `skipped` con `skip_reason = "canal deshabilitado"`.
6. Existe restricción única en base sobre (`rule_id`, `membership_id`, `target_date`); correr el job dos veces el mismo día no crea filas nuevas ni emite `NotificationQueued` dos veces (inserción con `ON CONFLICT DO NOTHING`).
7. Una membresía congelada (`frozen`) no genera avisos mientras lo esté; como congelar corre `end_date` (RN-07), las fechas objetivo se recalculan solas.
8. El job no descifra contacto en esta fase; solo usa `first_name` en claro para `{nombre}`.
9. `target_date` es una fecha civil (`DATE`); `created_at` en UTC.
10. Cada aviso creado queda auditado y emite `NotificationQueued`.
11. Si el worker no corrió un día, la siguiente corrida genera también los avisos con `target_date` de los días faltantes hasta 15 días atrás.

## Escenarios BDD

```gherkin
# language: es
Característica: Generación diaria de avisos

  Antecedentes:
    Dado que las cinco reglas por defecto están activas
    Y Juan Ríos tiene una membresía que termina el 2026-10-20

  Escenario: Generar el aviso de tres días antes una sola vez
    Dado que hoy en Bogotá es 2026-10-17
    Cuando el worker corre el job de avisos dos veces
    Entonces existe exactamente un aviso pendiente para Juan con fecha objetivo 2026-10-17
    Y se emitió un solo evento NotificationQueued

  Escenario: No avisar a quien ya renovó
    Dado que hoy en Bogotá es 2026-10-21
    Y Juan tiene una membresía futura que empieza el 2026-10-21
    Cuando el worker corre el job de avisos
    Entonces no se crea ningún aviso de la regla "1 día después" para Juan
```

## Endpoints

- Ninguno. Job `worker/jobs/notify.py` (fase generar) registrado en el worker de US-113; comando `cli notify --generate-only` para correrlo a mano.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** sí, `notifications.notifications` con FK a `notification_rules`, índice único (`rule_id`, `membership_id`, `target_date`), índice (`status`, `target_date`).
- **Trigger / restricciones:** ninguno adicional; no se borran filas.
- **Funciones puras a probar:** `target_dates` con las cinco reglas, con membresía congelada (fin corrido), con fin a fin de mes y año.
- **Pruebas:** puras; job con `FrozenClock` y base real (idempotencia, recuperación de días faltantes, preferencias, renovación).
- **Archivos principales:** `api/src/app/modules/notifications/service.py`, `api/src/app/worker/jobs/notify.py`.
- La consulta de membresías candidatas pasa por `memberships.service` (no se leen tablas ajenas). Los eventos `MembershipExpiring/Expired` del job de vencimientos (US-094) corren antes en la misma mañana; el generador no depende de ellos para ser correcto, usa el estado recalculado.

## Supuestos

- Supuesto: recuperación de hasta 15 días faltantes (el mayor `offset_days` por defecto); no está definido en ningún documento.
- Supuesto: los avisos `membership_expired` se suprimen si el socio ya renovó; la regla de negocio no lo dice, pero avisar a quien ya pagó contradice el objetivo de la épica.
- Supuesto: un aviso suprimido por preferencia o canal deshabilitado se guarda como `skipped` (rastro) en lugar de no crearse.

## Dependencias

- US-121 · Reglas de aviso
- US-094 · Job diario de vencimientos (estados del día)
- US-113 · Proceso worker programado
- US-122 · canales de aviso y US-123 · preferencias del socio (suaves: canal deshabilitado y preferencias se filtran al generar; agregado en consolidación)

## INVEST

- **Independiente:** entrega la cola sin depender de un canal real.
- **Negociable:** supresión por renovación y ventana de recuperación.
- **Valiosa:** es el corazón de la épica.
- **Estimable:** función pura más un job.
- **Pequeña:** 5.
- **Testeable:** fechas exactas e idempotencia con `FrozenClock`.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Prueba de idempotencia del job (dos corridas)
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] Auditoría verificada para las tablas tocadas
- [ ] Revisión de PR aprobada
