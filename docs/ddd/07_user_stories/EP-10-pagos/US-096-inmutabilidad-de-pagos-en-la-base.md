# US-096 · Como administrador quiero que la base de datos impida editar o borrar un pago para que la caja no se pueda alterar ni por error de programación ni a mano

- **Épica:** EP-10 · Registro inmutable de pagos
- **Bounded context:** Payments (esquema `payments`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero que ningún pago pueda modificarse ni borrarse en la base, salvo marcarlo una sola vez como anulado
para tener la certeza de que el registro de caja es el que realmente ocurrió

## Contexto de dominio

- **Aggregate / entidades:** `Payment`.
- **Reglas que aplica:** RN-02 (pago inmutable: ninguna columna cambia después de crear salvo las cuatro de anulación, y solo una vez; todo `DELETE` se rechaza), RN-14 (prohibido el borrado físico de pagos), `04_architecture_decision.md` sección 7 (triggers de inmutabilidad), regla de datos 5 de `CLAUDE.md`.
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** `payments.can_void(payment) -> bool` (verdadero solo si `voided = false`).

## Alcance

- **Backend:** trigger de PostgreSQL `payments.forbid_payment_mutation` (BEFORE UPDATE OR DELETE) en una migración de Alembic; función pura `can_void`; el service nunca emite `UPDATE` de otras columnas ni `DELETE`.
- **Front:** No aplica.

## Criterios de aceptación

1. Un `DELETE FROM payments.payments` de cualquier fila falla con un error de la base (SQLSTATE de excepción levantada por el trigger), también ejecutado con el usuario de la aplicación.
2. Un `UPDATE` que cambia `amount_cop`, `method`, `reference`, `paid_at`, `membership_id`, `registered_by`, `created_at` o `created_by` falla, aunque cambie también las columnas de anulación.
3. Un `UPDATE` que pasa `voided` de `false` a `true` y llena `void_reason` (no vacío), `voided_by` y `voided_at` es aceptado; también se acepta el cambio de `updated_at` en esa misma sentencia.
4. Un `UPDATE` sobre una fila con `voided = true` falla siempre (la anulación ocurre una sola vez).
5. Un `UPDATE` que pone `voided = true` sin `void_reason`, sin `voided_by` o sin `voided_at`, o con `void_reason` vacío tras recortar, falla.
6. Un `UPDATE` que intenta volver `voided` de `true` a `false` falla.
7. `payments.can_void` devuelve `true` para un pago con `voided = false` y `false` para uno anulado.
8. La migración es reversible (`downgrade` elimina trigger y función) y no toca datos.
9. La prueba de arquitectura confirma que `payments/service.py` no contiene `delete(` sobre el modelo `Payment`.

## Escenarios BDD

```gherkin
# language: es
Característica: Inmutabilidad de los pagos en la base

  Antecedentes:
    Dado un pago de 120000 por "cash" no anulado

  Escenario: La anulación completa es la única modificación permitida
    Cuando actualizo en la base "voided" a verdadero con motivo "Monto mal digitado", "voided_by" y "voided_at"
    Entonces la actualización es aceptada
    Y el monto sigue siendo 120000

  Escenario: Editar el monto es rechazado por la base
    Cuando actualizo en la base "amount_cop" a 100000
    Entonces la base rechaza la sentencia
    Y el monto sigue siendo 120000

  Escenario: Borrar un pago es rechazado por la base
    Cuando ejecuto un DELETE sobre ese pago
    Entonces la base rechaza la sentencia
    Y el pago sigue existiendo

  Escenario: Anular sin motivo es rechazado
    Cuando actualizo "voided" a verdadero con motivo vacío
    Entonces la base rechaza la sentencia

  Escenario: Un pago anulado no se puede volver a tocar
    Dado que el pago ya está anulado
    Cuando actualizo "void_reason" a "otro motivo"
    Entonces la base rechaza la sentencia
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** sí; crea la función PL/pgSQL y el trigger `BEFORE UPDATE OR DELETE ON payments.payments FOR EACH ROW`. Lógica: en `DELETE` levantar excepción; en `UPDATE`, si `OLD.voided` es verdadero levantar; si alguna columna distinta de `voided`, `void_reason`, `voided_by`, `voided_at`, `updated_at` difiere (`IS DISTINCT FROM`) levantar; exigir `NEW.voided = true`, `btrim(NEW.void_reason) <> ''`, `NEW.voided_by IS NOT NULL`, `NEW.voided_at IS NOT NULL`.
- **Trigger / restricciones:** el de arriba. El mixin común actualiza `updated_at`; por eso se permite en la transición.
- **Funciones puras a probar:** `can_void` con pago vigente y anulado.
- **Pruebas:** service con base real (cada criterio con SQL directo vía la sesión de prueba); pura de `can_void`; arquitectura.
- **Archivos principales:** `api/migrations/versions/*_payments_immutable_trigger.py`, `api/src/app/modules/payments/service.py`, `api/tests/payments/test_immutability.py`.

## Supuestos

- Ninguno.

## Dependencias

- US-095 · Registrar pago (la tabla debe existir).

## INVEST

- **Independiente:** solo depende de la tabla; no requiere front ni la anulación por API.
- **Negociable:** la forma de levantar el error (mensaje, SQLSTATE) es ajustable; la regla no.
- **Valiosa:** convierte RN-02 en garantía de la base y no solo del código.
- **Estimable:** una función y un trigger con pruebas.
- **Pequeña:** menos de dos días.
- **Testeable:** cada transición tiene prueba SQL directa.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol (rol no aplica: regla de base)
- [x] Endpoints y roles definidos (no hay)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] Revisión de PR aprobada
