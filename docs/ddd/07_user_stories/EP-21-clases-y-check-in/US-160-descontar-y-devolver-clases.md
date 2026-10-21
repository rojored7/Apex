# US-160 · Como administrador quiero que cada asistencia descuente una clase de los planes por clases y que borrarla la devuelva para que la tiquetera del socio cuadre sin contar a mano

- **Épica:** EP-21 · Clases, horario y check-in
- **Bounded context:** Memberships (esquema `memberships`) reaccionando a eventos de Classes
- **Versión:** v0.4
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica de la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (el efecto se ve en `Membresias` y en la pestaña Membresías de `Socio_Ficha`)

## Historia

Como administrador
quiero que al registrar una asistencia se descuente una clase de la membresía por clases del socio, y que al borrar la asistencia se devuelva
para que el saldo de clases sea exacto y la membresía venza cuando se agoten

## Contexto de dominio

- **Aggregate / entidades:** `Membership` (`classes_total`, `classes_remaining`, `status`).
- **Reglas que aplica:** RN-05 (plan por clases: fin por fecha y además se descuentan clases por asistencia); RN-06 (`compute_status`: `classes_remaining = 0` implica `expired`); Q4 (hasta v0.4 los planes por clases vencían solo por fecha: desde aquí se activa el descuento); los handlers corren en la misma transacción del emisor.
- **Eventos que emite:** `ClassConsumed(membership_id, classes_remaining)`; `MembershipExpired` cuando llega a 0.
- **Eventos que consume:** `MemberCheckedIn`, `AttendanceRemoved`
- **Funciones puras:** `memberships.consume_class(membership) -> Membership`, `memberships.return_class(membership) -> Membership`

## Alcance

- **Backend:** handlers `on_member_checked_in` y `on_attendance_removed` en `memberships/service.py` suscritos con `core/events.subscribe`; la membresía afectada es la vigente del socio (`active`, `expiring`) de plan `classes`; se recalcula el estado con `compute_status`.
- **Front:** No aplica (el saldo ya se muestra en las listas).

## Criterios de aceptación

1. Un check-in de un socio con membresía por clases vigente y 12 clases restantes deja `classes_remaining = 11` en la misma transacción y emite `ClassConsumed`.
2. Un check-in con `classes_remaining = 1` deja 0, la membresía pasa a `expired` y se emite `MembershipExpired`.
3. Borrar esa asistencia (`AttendanceRemoved`) devuelve la clase: `classes_remaining` sube en 1 sin superar `classes_total`, y el estado se recalcula con `compute_status` (si vuelve a tener clases y la fecha no ha pasado, deja de estar `expired`).
4. Un check-in de un socio con membresía por días, vencida, congelada, sin membresía o con `pending_payment` no cambia ninguna membresía.
5. Si el handler falla, el check-in completo se revierte (no queda asistencia sin descuento).
6. Los cambios de `classes_remaining` quedan auditados en `memberships`.
7. `consume_class` nunca deja `classes_remaining` negativo (prueba pura).

## Escenarios BDD

```gherkin
# language: es
Característica: Descuento de clases por asistencia

  Escenario: Asistencia en una tiquetera de 12 clases
    Dado que "Laura Gómez" tiene una membresía de 12 clases con 12 restantes
    Cuando el coach le hace check-in en la clase de hoy
    Entonces su membresía queda con 11 clases restantes

  Escenario: Última clase de la tiquetera
    Dado que "Laura Gómez" tiene 1 clase restante
    Cuando hace check-in
    Entonces su membresía queda con 0 clases y en estado vencida

  Escenario: Se borra una asistencia por error
    Dado que a "Laura Gómez" se le descontó una clase por un check-in equivocado
    Cuando el coach borra esa asistencia
    Entonces recupera la clase descontada
```

## Endpoints

- Ninguno nuevo (reacciona a `POST /attendance` y `DELETE /attendance/{id}`).

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no (`classes_total` y `classes_remaining` existen desde v0.1).
- **Trigger / restricciones:** `CHECK classes_remaining >= 0` si no existe (una migración).
- **Funciones puras a probar:** `consume_class`, `return_class` (tope en `classes_total`), `compute_status` con 0 clases.
- **Pruebas:** puras, service con base real (evento en la misma transacción, reversión ante fallo).
- **Archivos principales:** `api/src/app/modules/memberships/service.py`.

## Supuestos

- Supuesto: la membresía que se descuenta es la vigente en el momento del check-in, no una futura (Q1); si el socio tiene una vigente por días y una futura por clases, no se descuenta nada.
- Supuesto: devolver una clase a una membresía `expired` por clases la reactiva si su fecha de fin no ha pasado; no hay regla explícita sobre reactivar.

## Dependencias

- US-159 · Check-in en tablet (evento `MemberCheckedIn`)
- US-086 · Activar por cobertura de pagos (patrón de handlers en memberships)

## INVEST

- **Independiente:** solo handlers en memberships.
- **Negociable:** reactivación al devolver.
- **Valiosa:** la tiquetera cuadra sola.
- **Estimable:** dos handlers y dos funciones puras.
- **Pequeña:** sí.
- **Testeable:** conteos exactos.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Auditoría verificada para `memberships`
- [ ] Revisión de PR aprobada
