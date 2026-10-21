# US-083 · Como administrador quiero que el sistema calcule la fecha de fin, el estado y la cobertura de cada membresía con reglas fijas para no sacar fechas a mano ni equivocarme

- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context:** Memberships (módulo `memberships`, funciones puras de `service.py`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero que la fecha de fin, el estado (al día, por vencer, vencido, congelado) y la cobertura de pagos se calculen siempre con las mismas reglas
para confiar en lo que dice el sistema sobre quién está al día

## Contexto de dominio

- **Aggregate / entidades:** `Membership` con value objects `DateRange` y `FreezeWindow`.
- **Reglas que aplica:** RN-03 (activa si la suma de pagos no anulados es mayor o igual al precio pactado), RN-05 (fin = inicio + `duration_days`, también en planes por clases), RN-06 corregida por Q11 (por vencer si faltan `expiring_days` días o menos, por defecto 7), Q28 ("hoy" es la fecha civil de `America/Bogota` vía `today_bogota()`), Q1 (renovar arranca el día siguiente al fin de la vigente), Q4 (antes de v0.4 un plan por clases solo vence por fecha).
- **Eventos que emite:** ninguno (son funciones puras)
- **Eventos que consume:** ninguno
- **Funciones puras:** `compute_end_date(start_date, plan) -> date`, `compute_status(membership, today, expiring_days) -> MembershipStatus`, `next_start_for_renewal(current, today) -> date`, `is_covered(agreed_price_cop, payments) -> bool`

## Alcance

- **Backend:** las cuatro funciones en `api/src/app/modules/memberships/service.py`, tipos `MembershipStatus` (enum `pending_payment`, `active`, `expiring`, `expired`, `frozen`, `cancelled`) y estructuras mínimas de entrada (dataclasses congeladas) para probarlas sin base. `apply_freeze` va en US-089.
- **Front:** No aplica.

## Criterios de aceptación

1. `compute_end_date(2026-10-01, plan days 30)` devuelve `2026-10-31`; con plan `classes` de 60 días devuelve `2026-11-30`. La fórmula es `start_date + duration_days` días para ambos tipos.
2. `compute_status` aplica este orden y es determinista: `cancelled` es terminal y se devuelve siempre; `pending_payment` no cambia por fecha; si hay ventana de congelación que contiene `today` devuelve `frozen`; si `today > end_date` o `classes_remaining = 0` devuelve `expired`; si `end_date - today <= expiring_days` devuelve `expiring`; si no, `active`.
3. Con `end_date = 2026-10-31` y `expiring_days = 7`: el 2026-10-23 es `active`, el 2026-10-24 es `expiring`, el 2026-10-31 es `expiring` y el 2026-11-01 es `expired`.
4. `expiring_days` es parámetro (sale de `settings.memberships`, US-058); con `expiring_days = 3` el 2026-10-28 es `expiring` y el 2026-10-27 es `active`.
5. Una membresía `active` con `start_date` posterior a `today` (membresía futura de Q1) devuelve `active` (no `expiring`) mientras `end_date - today > expiring_days`.
6. Mientras no exista check-in (Q4), `classes_remaining` nunca baja; un plan por clases se comporta por fecha. La regla `classes_remaining = 0 → expired` queda implementada y probada para v0.4.
7. `next_start_for_renewal(current, today)`: si `current` no ha vencido (`today <= current.end_date`) devuelve `current.end_date + 1 día`; si ya venció o es `None`, devuelve `today`.
8. `is_covered(agreed_price_cop, payments)` suma solo los pagos con `voided = false` y devuelve `true` si la suma es mayor o igual a `agreed_price_cop`; todos los montos son enteros en COP.
9. Ninguna función lee la base, el reloj del sistema ni la configuración: todo entra por parámetro (`today` lo calcula el llamador con `core.clock.today_bogota()`).
10. Cobertura de pruebas de estas funciones: 100 % de ramas.

## Escenarios BDD

```gherkin
# language: es
Característica: Reglas puras de fechas, estados y cobertura

  Escenario: Fecha de fin de un plan por días
    Dado un plan por días de 30 días
    Cuando calculo la fecha de fin para un inicio el 2026-10-01
    Entonces la fecha de fin es 2026-10-31

  Escenario: Estados al cruzar las fechas
    Dada una membresía activa con fin el 2026-10-31 y "expiring_days" igual a 7
    Cuando calculo el estado para hoy 2026-10-23
    Entonces el estado es "active"
    Cuando calculo el estado para hoy 2026-10-24
    Entonces el estado es "expiring"
    Cuando calculo el estado para hoy 2026-11-01
    Entonces el estado es "expired"

  Escenario: Pendiente de pago no cambia por fecha
    Dada una membresía en "pending_payment" con fin el 2026-10-31
    Cuando calculo el estado para hoy 2026-11-15
    Entonces el estado es "pending_payment"

  Escenario: Cancelada es terminal
    Dada una membresía cancelada con fin el 2026-12-31
    Cuando calculo el estado para hoy 2026-10-10
    Entonces el estado es "cancelled"

  Escenario: Cobertura ignora pagos anulados
    Dada una membresía con precio pactado 120000
    Y pagos de 80000 no anulado y 40000 anulado
    Cuando evalúo la cobertura
    Entonces no está cubierta

  Escenario: Inicio de renovación con la vigente sin vencer
    Dada una membresía vigente con fin el 2026-10-31
    Cuando calculo el inicio de la renovación para hoy 2026-10-28
    Entonces el inicio es 2026-11-01

  Escenario: Inicio de renovación con la membresía ya vencida
    Dada una membresía con fin el 2026-10-31
    Cuando calculo el inicio de la renovación para hoy 2026-11-05
    Entonces el inicio es 2026-11-05
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** las cuatro, con `pytest.mark.parametrize`: fronteras de `expiring_days` (0, 3, 7), fin en último día del mes y año bisiesto (inicio 2028-02-01 + 30 = 2028-03-02), `classes_remaining = 0`, ventana de congelación que contiene y que no contiene `today`, pagos todos anulados, pago que supera el precio.
- **Pruebas:** solo puras, sin base ni reloj.
- **Archivos principales:** `api/src/app/modules/memberships/service.py`, `api/tests/memberships/test_rules.py`.

## Supuestos

- Supuesto: `end_date` es inclusiva (el socio está al día también el día de `end_date`), coherente con RN-06 "al día si hoy ≤ fin".

## Dependencias

- US-013 · Reloj y fecha de Bogotá (`today_bogota()` usado por los llamadores)

## INVEST

- **Independiente:** no necesita tablas ni endpoints.
- **Negociable:** nombres internos y tipos de entrada.
- **Valiosa:** es el corazón de "quién está al día".
- **Estimable:** cuatro funciones con casos enumerados.
- **Pequeña:** dos días.
- **Testeable:** cada regla tiene casos con fecha concreta.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y bordes (no hay rol: no hay endpoint)
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras en verde con 100 % de ramas
- [ ] Revisión de PR aprobada
