# US-089 · Como administrador o coach quiero congelar una membresía entre dos fechas para que el socio no pierda los días que no puede entrenar

- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context:** Memberships (esquema `memberships`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Membresias` (`/membresias`, modal "Congelar") y pestaña Membresías de `Socio_Ficha`

## Historia

Como administrador o coach
quiero congelar la membresía de un socio indicando desde y hasta qué fecha
para que su fecha de fin se corra exactamente esos días y el sistema respete los límites que fijó el dueño

## Contexto de dominio

- **Aggregate / entidades:** `Membership` con value object `FreezeWindow` (`frozen_from ≤ frozen_to`, dentro de la vigencia, una sola congelación vigente a la vez).
- **Reglas que aplica:** RN-07 (congelar N días corre el fin N días; N = `(frozen_to - frozen_from) + 1`), RN-06 (estado `frozen` entre `frozen_from` y `frozen_to`), Q7 (congelan admin y coach), Q9 (límites en `settings.memberships`: `max_freeze_days_per_membership` 30, `max_freezes_per_membership` 2, `max_retroactive_days` 7), Q1 (no solape con la futura), Q28.
- **Eventos que emite:** `MembershipFrozen`
- **Eventos que consume:** ninguno
- **Funciones puras:** `apply_freeze(membership, frozen_from, frozen_to, limits, today) -> Membership | FreezeError`

## Alcance

- **Backend:** función pura `apply_freeze` (devuelve una copia nueva, no muta), `memberships.service.freeze(id, frozen_from, frozen_to, by)` que lee los límites con `settings.service.get_section("memberships")`, endpoint `POST /memberships/{id}/freeze`.
- **Front:** modal "Congelar" con dos fechas, cálculo en vivo de días y de la nueva fecha de fin, y mensajes de los límites.

## Criterios de aceptación

1. `POST /api/v1/memberships/{id}/freeze` con `{ frozen_from, frozen_to }` sobre una membresía `active` o `expiring` responde 200 con la membresía: `end_date` aumentada en `(frozen_to - frozen_from) + 1` días, `frozen_from`/`frozen_to` guardados, `freeze_count + 1` y `frozen_days_total + N`.
2. El estado resultante lo da `compute_status`: `frozen` si `today_bogota()` está en la ventana; si la ventana es futura, sigue `active` (o `active` si la extensión la saca de `expiring`).
3. Solo sobre `active` o `expiring`; sobre `pending_payment`, `frozen`, `expired` o `cancelled` devuelve 422 `code = "membership_not_freezable"`.
4. `frozen_from > frozen_to` devuelve 422 `field = "frozen_to"`.
5. `frozen_from` anterior a `today - max_retroactive_days` devuelve 422 `code = "freeze_too_retroactive"`.
6. `frozen_from` fuera de `[start_date, end_date]` de la membresía devuelve 422 `code = "freeze_outside_validity"`.
7. Si `freeze_count` ya es igual a `max_freezes_per_membership`, devuelve 422 `code = "freeze_limit_reached"`.
8. Si `frozen_days_total + N > max_freeze_days_per_membership`, devuelve 422 `code = "freeze_days_exceeded"` con los días disponibles en `message`.
9. Si ya existe una ventana con `frozen_to >= today` (congelación vigente o programada), devuelve 409 `code = "freeze_already_scheduled"`.
10. Si la nueva `end_date` se solaparía con una membresía futura del socio, devuelve 409 `code = "membership_overlap"` (supuesto) y no cambia nada.
11. Los límites salen de `settings.memberships` (US-058); si la sección no existe, se usan los valores por defecto 30, 2 y 7.
12. `apply_freeze` es pura, no muta su entrada y tiene pruebas de cada límite.
13. Roles: admin y coach (Q7); `member` 403; sin token 401.
14. Queda auditoría `update` con `end_date`, `frozen_from`, `frozen_to` antes y después; se emite `MembershipFrozen`.

## Escenarios BDD

```gherkin
# language: es
Característica: Congelar una membresía

  Antecedentes:
    Dado que hoy en Bogotá es 2026-10-10
    Y la configuración de membresías tiene máximo 30 días, 2 congelaciones y 7 días retroactivos
    Y "Laura Gómez" tiene una membresía "active" del 2026-10-01 al 2026-10-31 sin congelaciones
    Y que estoy autenticado como coach

  Escenario: Congelar 10 días desde hoy
    Cuando congelo la membresía de "Laura Gómez" del 2026-10-10 al 2026-10-19
    Entonces la respuesta es 200
    Y la fecha de fin pasa a 2026-11-10
    Y la membresía queda "frozen"
    Y se emite "MembershipFrozen"

  Escenario: Congelación programada a futuro
    Cuando congelo la membresía de "Laura Gómez" del 2026-10-20 al 2026-10-24
    Entonces la fecha de fin pasa a 2026-11-05
    Y la membresía sigue "active"

  Escenario: Supera los días permitidos
    Cuando congelo la membresía de "Laura Gómez" del 2026-10-10 al 2026-11-15
    Entonces la respuesta es 422
    Y el error tiene el código "freeze_days_exceeded"
    Y la fecha de fin sigue en 2026-10-31

  Escenario: Demasiado retroactiva
    Cuando congelo la membresía de "Laura Gómez" del 2026-10-01 al 2026-10-05
    Entonces la respuesta es 422
    Y el error tiene el código "freeze_too_retroactive"

  Escenario: Fechas invertidas
    Cuando congelo la membresía de "Laura Gómez" del 2026-10-19 al 2026-10-10
    Entonces la respuesta es 422
    Y el error señala el campo "frozen_to"

  Escenario: Tercera congelación
    Dado que la membresía ya tuvo 2 congelaciones terminadas
    Cuando congelo la membresía de "Laura Gómez" del 2026-10-12 al 2026-10-13
    Entonces la respuesta es 422
    Y el error tiene el código "freeze_limit_reached"

  Escenario: Membresía pendiente de pago
    Dado que "Juan Rodríguez" tiene una membresía en "pending_payment"
    Cuando congelo la membresía de "Juan Rodríguez" del 2026-10-10 al 2026-10-12
    Entonces la respuesta es 422
    Y el error tiene el código "membership_not_freezable"

  Escenario: Socio del portal denegado
    Dado que estoy autenticado con rol "member"
    Cuando congelo la membresía de "Laura Gómez" del 2026-10-10 al 2026-10-19
    Entonces la respuesta es 403
```

## Endpoints

- `POST /api/v1/memberships/{id}/freeze` — rol(es): admin, coach — entrada: `{ frozen_from: date, frozen_to: date }` — salida: `MembershipOut` (incluye `frozen_from`, `frozen_to`, `freeze_count`, `frozen_days_total`) — códigos: 200, 401, 403, 404, 409, 422.

## Pantalla

- `Membresias` (modal "Congelar") y pestaña Membresías de `Socio_Ficha`: dos `Field` de fecha, texto "Son N días; la membresía terminará el 10 nov 2026", errores por código con texto en español. Botón visible para admin y coach.

## Notas técnicas

- **Migración:** no (columnas `frozen_from`, `frozen_to`, `freeze_count`, `frozen_days_total` creadas en US-084).
- **Trigger / restricciones:** `CHECK (frozen_from IS NULL OR frozen_from <= frozen_to)`.
- **Funciones puras a probar:** `apply_freeze` con: 10 días (fin +10), ventana de un solo día (+1), cada límite de Q9, estado no congelable, ventana fuera de vigencia, retroactividad en la frontera exacta (hoy − 7 permitido, hoy − 8 rechazado).
- **Pruebas:** puras; service con base real (lectura de límites desde settings, solape con futura, auditoría); router; front (cálculo en vivo).
- **Archivos principales:** `api/src/app/modules/memberships/{service,router,schemas,exceptions}.py`, `web/src/features/memberships/components/FreezeModal.tsx`.

## Supuestos

- Supuesto: el modelo guarda solo la última ventana (`frozen_from`, `frozen_to`); las anteriores quedan en la auditoría y en `freeze_count`/`frozen_days_total`.
- Supuesto: "dentro de la vigencia" significa que `frozen_from` está entre `start_date` y el `end_date` vigente; `frozen_to` puede pasar del fin original porque el fin se corre.
- Supuesto: si la extensión del fin se solapa con una membresía futura, se rechaza con 409 en lugar de correr también la futura; queda como pregunta abierta (alternativa: correr la futura N días en la misma transacción).

## Dependencias

- US-084 · Vender membresía
- US-058 · Parámetros de membresías (límites de Q9)

## INVEST

- **Independiente:** opera sobre una membresía existente y la configuración.
- **Negociable:** textos y forma del modal; el tratamiento del solape con la futura.
- **Valiosa:** el socio no pierde días por viajes o lesiones; el dueño controla los abusos con límites.
- **Estimable:** reglas enumeradas.
- **Pequeña:** cuatro días.
- **Testeable:** cada límite tiene un código de error.

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
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `memberships`
- [ ] Revisión de PR aprobada
