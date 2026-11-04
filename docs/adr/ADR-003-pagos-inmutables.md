# ADR-003 · Pagos inmutables

## Estado

Aceptado. Vigente desde el Sprint 3 (migración `0011_payments_immutability`). Cambiarlo exige detenerse y preguntar: toca el registro contable del gimnasio y la cadena de auditoría.

## Contexto

`payments.payments` es el libro de lo que el gimnasio cobró. Un `UPDATE` o un `DELETE` sobre un pago esconde un error o un fraude y deja los totales del mes sin explicación. Las reglas de código no bastan: un script de mantenimiento, una consola de base o un bug en otro módulo se saltan el `service.py`. La corrección legítima (un pago mal registrado) existe y debe dejar rastro.

## Decisión

Un pago nunca se edita ni se borra. Un error se corrige anulándolo y registrando un pago nuevo.

- Columnas de anulación en la propia fila: `voided` (booleano), `void_reason` (texto, hasta 500 caracteres), `voided_by` y `voided_at`. La restricción `void_coherent` exige que las cuatro estén vacías o que las cuatro estén llenas (motivo no en blanco).
- La función `payments.forbid_mutation()` y dos triggers `ENABLE ALWAYS` (por fila `BEFORE UPDATE OR DELETE` y por sentencia `BEFORE TRUNCATE`) dejan pasar una sola transición: la anulación completa de un pago vigente. Todo lo demás se rechaza con `ERRCODE = integrity_constraint_violation` y `CONSTRAINT = payments_immutable`: borrar, vaciar la tabla, tocar un anulado, cambiar cualquiera de las diez columnas protegidas o dejar una anulación incompleta.
- `ENABLE ALWAYS` hace que ni `session_replication_role = replica` salte los triggers.
- No existe ruta `DELETE` ni `PUT`/`PATCH` sobre pagos; solo `POST /payments/{id}/void` con motivo, que exige el rol `admin`.
- El rol de base `apex_api` no recibe `DELETE` sobre la tabla (`infra/db/grants.sql`); el trigger es la segunda barrera, no la única.
- Una columna nueva en `payments.payments` obliga a decidir si el trigger la protege.

## Alternativas descartadas

- **Solo la regla en `service.py`:** no frena a quien entra por otra puerta; el rastro de auditoría llega tarde.
- **Tabla de reversos aparte (asiento contrario):** más fiel a la contabilidad de doble entrada, pero APEX no lleva libro mayor; duplica consultas y totales sin dar más garantía que la anulación en la fila.
- **Borrado lógico (`deleted_at`) como en socios y planes:** permitiría "desaparecer" un pago; un pago anulado sigue visible, con quién y por qué.
- **Solo `REVOKE UPDATE, DELETE`:** el propietario de la tabla y el migrador se lo saltan; el trigger vale también para ellos.

## Consecuencias

- Los totales del mes cuentan los pagos no anulados; una anulación cambia el total y deja la auditoría (`audit.audit_log`) con el antes y el después.
- Cualquier corrección de datos exige un pago nuevo; no hay "arreglo rápido" por SQL, y es deliberado.
- Las migraciones que tocan esta tabla deben convivir con los triggers: una migración de datos sobre pagos se diseña como anulación más pago nuevo, no como `UPDATE`.
- Una anulación no se deshace: reactivar un pago anulado se hace con un pago nuevo.

## Cómo se verifica

- `api/tests/payments/test_immutability.py` prueba en la base cada rechazo (`delete`, `truncate`, `already_voided`, `column`, `incomplete_void`) y que bajo `session_replication_role = replica` siguen.
- `api/tests/migrations/test_0011_payments_immutability.py` prueba la migración (función, triggers y ciclo de bajada y subida).
- `api/tests/payments/test_void.py` y `api/tests/payments/test_router_void.py` prueban la anulación por el service y por el endpoint.
- `api/tests/architecture/test_no_physical_delete.py` impide el borrado físico en el código.
- Cambiar esta decisión (permitir editar o borrar pagos, relajar el trigger) exige detenerse y preguntar.
