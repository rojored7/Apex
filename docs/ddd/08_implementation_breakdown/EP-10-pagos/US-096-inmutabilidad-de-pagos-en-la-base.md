# US-096 · Inmutabilidad de pagos en la base — desglose técnico

> **Corregido en S3-W0-1** (`docs/ddd/blueprints/sprint-03-plan.md`, sección 1; registro en `docs/ddd/DECISIONES.md`, "Sprint 3"). Donde el texto de abajo choque con estas notas, mandan las notas:
> - Sin `CHECK voided_at >= created_at` (S3-D68): en pruebas `created_at` sale del servidor y `voided_at` del `FrozenClock`. Sí entran `SECURITY INVOKER` y `SET search_path = pg_catalog` en las funciones de trigger.
> - Los triggers van con `ALTER TABLE ... ENABLE ALWAYS TRIGGER` (S3-D49); el error lleva `CONSTRAINT = payments_immutable` y se traduce a 409 `payment_already_voided` (D13). La limpieza de pruebas cierra con `ENABLE ALWAYS TRIGGER` por nombre (E1).

- **Historia:** `docs/ddd/07_user_stories/EP-10-pagos/US-096-inmutabilidad-de-pagos-en-la-base.md`
- **Épica:** EP-10 · Registro inmutable de pagos
- **Bounded context / módulo:** Payments (`api/src/app/modules/payments/`, migración en `api/migrations/versions/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

La regla RN-02 está cerrada por el dominio, por `04_architecture_decision.md` sección 7 y por los criterios de la historia: una única transición permitida (anulación), una sola vez, con las cuatro columnas de anulación y `updated_at`. No hay supuestos abiertos. El trigger se prueba con SQL directo que intenta saltarse el ORM.

## Resumen

Agrega la migración `0011_payments_immutability` con la función PL/pgSQL `payments.forbid_mutation()` y el trigger `BEFORE UPDATE OR DELETE ... FOR EACH ROW`, más un trigger de sentencia que rechaza `TRUNCATE`. Agrega la función pura `payments.can_void(payment) -> bool` que usa US-097. Las pruebas ejecutan `UPDATE`, `DELETE` y `TRUNCATE` crudos con `text()` sobre la sesión de prueba para demostrar que la base rechaza todo lo que no sea la anulación completa.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md.
- Nombre de la función: la historia dice `payments.forbid_payment_mutation`; se usa el nombre canónico `payments.forbid_mutation()` y la migración `0011_payments_immutability` de la especificación de desglose (simétrico con `audit.forbid_mutation()` de US-015).
- La columna `member_id` que agrega US-095 a `0010_payments` también queda protegida (es una columna de negocio más).

## Validación contra el dominio

- Aggregate `Payment`; invariante RN-02 de `02_domain_model.md` 2.4: ninguna columna cambia después de crear salvo `voided`, `void_reason`, `voided_by`, `voided_at`, y solo una vez; todo `DELETE` se rechaza. RN-14: prohibido el borrado físico de pagos.
- La transición permitida es exactamente `voided: false → true` con `btrim(void_reason) <> ''`, `voided_by IS NOT NULL`, `voided_at IS NOT NULL`, y `updated_at` libre (lo toca el mixin común).
- Función pura: `can_void(payment) -> bool` devuelve `not payment.voided`. Coincide con `02_domain_model.md` sección 4.
- Eventos: ninguno emitido ni consumido.

## Validación contra la arquitectura

- Módulo dueño: `payments`. La migración vive en `api/migrations/versions/` y es la única con DDL de triggers del esquema `payments`.
- Doble barrera exigida por la restricción dura: trigger en PostgreSQL más regla en código (`can_void` y un service que nunca emite `UPDATE` de otras columnas ni `DELETE`).
- Sin llamadas a otros services, sin eventos, sin bus de criptografía, sin rol (no hay endpoint).
- Lint y arquitectura: prueba que `payments/service.py` no contiene `delete(` ni `session.delete` sobre `Payment` ni `update(Payment)` fuera de `void`.
- Auditoría: no cambia; el `UPDATE` de anulación lo audita el hook de US-016 (lo verifica US-097).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- [ ] T1 · `0011_payments_immutability`: función `payments.forbid_mutation() RETURNS trigger LANGUAGE plpgsql` con esta lógica: si `TG_OP = 'DELETE'` → `RAISE EXCEPTION 'payments_immutable: delete' USING ERRCODE = 'P0001'`; si `TG_OP = 'UPDATE'`: si `OLD.voided` → levantar `payments_immutable: already_voided`; si alguna de `id`, `membership_id`, `member_id`, `amount_cop`, `method`, `reference`, `paid_at`, `registered_by`, `created_at`, `created_by` es `IS DISTINCT FROM` su valor anterior → levantar `payments_immutable: column`; exigir `NEW.voided = true AND btrim(coalesce(NEW.void_reason, '')) <> '' AND NEW.voided_by IS NOT NULL AND NEW.voided_at IS NOT NULL`, si no → levantar `payments_immutable: incomplete_void`; devolver `NEW`. Trigger `payments_forbid_mutation BEFORE UPDATE OR DELETE ON payments.payments FOR EACH ROW EXECUTE FUNCTION payments.forbid_mutation()`. Trigger `payments_forbid_truncate BEFORE TRUNCATE ON payments.payments FOR EACH STATEMENT` con función `payments.forbid_truncate()`. `downgrade` elimina los dos triggers y las dos funciones, sin tocar datos — 3 h

### Models
- No aplica.

### Service
- [ ] T2 · Función pura `can_void(payment: Payment) -> bool` en `payments/service.py`; constante `IMMUTABLE_ERROR_PREFIX = "payments_immutable"` que el service usa para traducir el error de la base a 409 en US-097 — 1 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T3 · `api/tests/payments/test_can_void.py`: pago vigente devuelve `true`; pago anulado devuelve `false` (objetos `Payment` en memoria, sin base) — 0,5 h

### Tests de service con PostgreSQL
- [ ] T4 · `api/tests/payments/test_immutability.py`, cada caso con `await session.execute(text(...))` crudo y verificación posterior de la fila con una segunda consulta: `DELETE` rechazado; `TRUNCATE` rechazado; `UPDATE` de `amount_cop`, `method`, `reference`, `paid_at`, `membership_id`, `member_id`, `registered_by`, `created_at`, `created_by` rechazado (parametrizado), también cuando la misma sentencia llena las columnas de anulación; anulación completa aceptada con `updated_at` cambiado y monto intacto; anulación sin motivo, con motivo de espacios, sin `voided_by` o sin `voided_at` rechazada; segunda anulación rechazada; `voided` de `true` a `false` rechazado; `UPDATE` sin cambios sobre un pago anulado rechazado. Cada caso usa `SAVEPOINT` para seguir en la misma transacción de prueba — 4 h
- [ ] T5 · Mismo archivo: el rechazo ocurre ejecutando con el rol de la aplicación (`SET ROLE apex_app` si existe en `compose.dev.yml`; si no, se documenta que la prueba corre con el usuario de la app) y la excepción trae el prefijo `payments_immutable` — 1 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T6 · `api/tests/architecture/test_payments_immutability_code.py`: analiza con `ast` `payments/service.py` y falla si encuentra `delete(Payment)`, `session.delete(`, o `update(Payment)` fuera de la función `void` — 1 h

### Front
- No aplica.

### DevOps
- [ ] T7 · Verificar en `infra/compose.dev.yml` y en la documentación de despliegue que el usuario de la aplicación no es dueño de las tablas del esquema `payments` (el dueño puede `ALTER TABLE ... DISABLE TRIGGER`); si EP-13 no separa roles, anotarlo como riesgo en `docs/adr/` — 1 h

### Seguridad
- [ ] T8 · Revisión del trigger por una segunda persona (o agente `database-reviewer`): lista completa de columnas protegidas contra `\d payments.payments`, `SECURITY INVOKER`, sin `EXCEPTION WHEN OTHERS` que trague errores — 0,5 h

## Orden de ejecución
1. T3 (pura en rojo)
2. T2
3. T4, T5 (pruebas SQL en rojo)
4. T1
5. T6
6. T7
7. T8

## Dependencias técnicas
- US-095 · Registrar pago: la tabla `payments.payments` (`0010_payments`) debe existir, incluida la columna `member_id`.
- US-097 · Anular pago: usa `can_void` y traduce el error del trigger a 409.

## Endpoints
- Ninguno.

## Riesgos
- Una columna nueva agregada a `payments` en el futuro quedaría editable si no se agrega a la lista del trigger — mitigación: la prueba T4 compara la lista de columnas protegidas con `information_schema.columns` y falla si aparece una columna no clasificada.
- El dueño de la tabla o un superusuario pueden deshabilitar triggers (`ALTER TABLE ... DISABLE TRIGGER`, `session_replication_role = replica`) — mitigación: T7, rol de aplicación sin propiedad de tablas.
- Un trigger mal escrito bloquea anulaciones legítimas — mitigación: el caso feliz de anulación es la primera prueba de T4 y US-097 la repite por la API.

## Estimación
- Backend: 4 h (T1, T2)
- Front: 0 h
- Pruebas: 6,5 h (T3 a T6)
- DevOps / seguridad: 1,5 h (T7, T8)
- **Total: 12 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/payments/test_can_void.py -q`
- [ ] `cd api && uv run pytest tests/payments/test_immutability.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
- [ ] `psql -c "UPDATE payments.payments SET amount_cop = 1"` falla con `payments_immutable: column`; `psql -c "DELETE FROM payments.payments"` falla con `payments_immutable: delete`; `psql -c "TRUNCATE payments.payments"` falla
- [ ] `psql -c "\dS+ payments.payments"` muestra los triggers `payments_forbid_mutation` y `payments_forbid_truncate`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.payments --cov-fail-under=80`
