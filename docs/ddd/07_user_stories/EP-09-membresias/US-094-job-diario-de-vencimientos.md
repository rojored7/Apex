# US-094 · Como administrador quiero que cada mañana el sistema actualice solo los estados de las membresías para ver al abrir quién vence y quién ya venció

- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context:** Memberships (esquema `memberships`), job del worker
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero que a las 7:00 de Bogotá el sistema recalcule el estado de todas las membresías
para que al abrir el gimnasio la lista de "por vencer" y "vencidos" esté correcta sin que nadie haga nada

## Contexto de dominio

- **Aggregate / entidades:** `Membership`.
- **Reglas que aplica:** RN-06 corregida por Q11 (`expiring_days` de `settings.memberships`, por defecto 7), RN-07 (entrar y salir de `frozen` por fecha), Q28 (`today` = `today_bogota()`), Q4 (antes de v0.4 solo cambia por fecha), `04_architecture_decision.md` 5 (el worker no recibe eventos: consulta tablas y emite eventos dentro de su propia transacción).
- **Eventos que emite:** `MembershipExpiring`, `MembershipExpired` (solo en la transición)
- **Eventos que consume:** ninguno
- **Funciones puras:** `compute_status`

## Alcance

- **Backend:** `memberships.service.recompute_statuses(today) -> list[events]`; job `api/src/app/worker/jobs/expirations.py` registrado en el scheduler de US-113 a las 07:00 `America/Bogota`; comando `cli recompute-memberships [--date AAAA-MM-DD]` para correrlo a demanda (supuesto). El estado también se recalcula al leer la membresía (US-084, US-089), así que el job corrige lo que quedó desactualizado de un día a otro.
- **Front:** No aplica.

## Criterios de aceptación

1. `recompute_statuses(today)` recorre en lotes (500 por lote) las membresías con estado `active`, `expiring` o `frozen`, calcula `compute_status(m, today, expiring_days)` y actualiza solo las que cambian.
2. Con `FrozenClock` y `end_date = 2026-10-31`, `expiring_days = 7`: el 2026-10-24 la membresía pasa de `active` a `expiring` y se emite `MembershipExpiring` una vez; el 2026-11-01 pasa a `expired` y se emite `MembershipExpired` una vez.
3. Correr el job dos veces el mismo día no emite eventos duplicados ni crea filas de auditoría nuevas (idempotente: solo emite en la transición).
4. Si el servidor estuvo apagado y el job corre el 2026-11-03 sobre una membresía `active` con fin el 2026-10-31, pasa directo a `expired` y emite solo `MembershipExpired`.
5. Una membresía con ventana de congelación que empieza hoy pasa a `frozen`; la que termina ayer vuelve a `active` o `expiring` según su nueva fecha de fin.
6. `pending_payment` y `cancelled` nunca cambian en este job.
7. `today` es `today_bogota()`: con `FrozenClock` en 2026-11-01 02:00 UTC (2026-10-31 21:00 en Bogotá), la membresía que termina el 2026-10-31 sigue `expiring`.
8. Cada cambio de estado deja auditoría `update` con `user_id` del usuario de sistema del worker (supuesto) y el estado antes y después.
9. Un fallo en un lote revierte solo ese lote, se registra en el log JSON (sin datos personales) y el job continúa con el siguiente; el job termina con un resumen `{ revisadas, cambiadas, por_vencer, vencidas, errores }` en el log.
10. Con 1.000 socios el job termina en menos de 60 segundos.

## Escenarios BDD

```gherkin
# language: es
Característica: Job diario de vencimientos

  Antecedentes:
    Dado que "expiring_days" es 7
    Y "Laura Gómez" tiene una membresía "active" del 2026-10-01 al 2026-10-31

  Escenario: Pasa a por vencer a 7 días
    Dado que hoy en Bogotá es 2026-10-24
    Cuando corre el job de vencimientos
    Entonces la membresía queda "expiring"
    Y se emite "MembershipExpiring" una vez

  Escenario: Pasa a vencida al día siguiente del fin
    Dado que la membresía está "expiring"
    Y que hoy en Bogotá es 2026-11-01
    Cuando corre el job de vencimientos
    Entonces la membresía queda "expired"
    Y se emite "MembershipExpired" una vez

  Escenario: Correr dos veces no duplica
    Dado que hoy en Bogotá es 2026-10-24
    Cuando corre el job de vencimientos dos veces
    Entonces se emite "MembershipExpiring" una sola vez
    Y hay una sola entrada de auditoría del cambio

  Escenario: La noche en UTC no adelanta el vencimiento
    Dado que la hora actual es 2026-11-01 02:00 UTC
    Cuando corre el job de vencimientos
    Entonces la membresía no queda "expired"

  Escenario: Pendiente de pago no se toca
    Dado que "Juan Rodríguez" tiene una membresía en "pending_payment" con fin el 2026-10-15
    Y que hoy en Bogotá es 2026-11-01
    Cuando corre el job de vencimientos
    Entonces la membresía sigue "pending_payment"

  Escenario: Un lote con error no detiene el job
    Dado que el segundo lote falla por un error interno
    Cuando corre el job de vencimientos
    Entonces los lotes primero y tercero quedan actualizados
    Y el resumen del job informa 1 error
```

## Endpoints

- Ninguno. Job `expirations` del worker (07:00 `America/Bogota`) y comando `uv run python -m app.cli recompute-memberships --date AAAA-MM-DD` (supuesto).

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no.
- **Funciones puras a probar:** `compute_status` en las fronteras de la fecha (ya cubierta en US-083).
- **Pruebas:** worker con `FrozenClock` y base real (transiciones, idempotencia, frontera UTC/Bogotá, reanudación tras días sin correr, error por lote); prueba de que los eventos se emiten dentro de la transacción del lote.
- **Archivos principales:** `api/src/app/modules/memberships/service.py`, `api/src/app/worker/jobs/expirations.py`, `api/src/app/cli.py`, `api/tests/worker/test_expirations.py`.

## Supuestos

- Supuesto: el worker actúa con un usuario técnico `system` (sin login, `is_active = false` para el panel) cuyo id va en `created_by` y en la auditoría; no está definido en el dominio.
- Supuesto: existe el comando `cli recompute-memberships` para correr el recálculo a demanda (no está en la lista de comandos de `05_service_design.md`).

## Dependencias

- US-083 · Reglas puras de fechas y estados
- US-084 · Vender membresía
- US-113 · Proceso worker programado

## INVEST

- **Independiente:** un job sobre la tabla existente; el worker lo provee US-113.
- **Negociable:** tamaño de lote y comando a demanda.
- **Valiosa:** cumple la frase guía: saber al abrir quién vence.
- **Estimable:** recorrido por lotes con reglas ya probadas.
- **Pequeña:** cuatro días.
- **Testeable:** fechas con `FrozenClock` y conteo de eventos.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y bordes (sin endpoint: no hay rol)
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de worker con `FrozenClock` y PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Auditoría verificada para `memberships`
- [ ] Log JSON del job sin datos personales
- [ ] Revisión de PR aprobada
