# US-015 · Como equipo quiero la tabla de auditoría append-only con su cadena de hashes y serialización canónica para que cualquier fila alterada rompa la cadena y se pueda demostrar

- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context:** Audit (escritura en `core/audit.py`, esquema `audit`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `audit.audit_log` con `seq`, `prev_hash` y `hash = SHA-256(prev_hash || canonical(row))`, una función pura `chain_hash` y un trigger que rechace `UPDATE` y `DELETE`
para que la auditoría sea evidencia confiable de quién hizo qué y nadie la pueda editar sin que se note

## Contexto de dominio

- **Aggregate / entidades:** `AuditEntry` (`seq` bigserial, `at`, `user_id`, `action` en `insert | update | delete | reveal | export | login | verify`, `table_name`, `record_id`, `before` JSON, `after` JSON, `prev_hash`, `hash`).
- **Reglas que aplica:** RN-16 (cada fila lleva el hash de la anterior; una fila alterada rompe la cadena); RN-14 (la auditoría nunca se borra); `04_architecture_decision.md` sección 7 (triggers de inmutabilidad).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `audit.chain_hash(prev_hash, row) -> str`, `audit.canonical(row) -> bytes`

## Alcance

- **Backend:** modelo `AuditEntry` en `core/audit.py` (la tabla no lleva `updated_at` ni `deleted_at`; `seq` es la clave de orden); migración de `audit.audit_log` con índices por (`table_name`, `record_id`), `at` y `user_id`; trigger `BEFORE UPDATE OR DELETE` que lanza excepción; `canonical(row)`: JSON con claves ordenadas, separadores `(",", ":")`, UTF-8, fechas ISO 8601 en UTC con `Z`, UUID en minúscula, `None` como `null`; hash inicial `prev_hash` = 64 ceros; `record(session, action, table, record_id, before, after, user_id)` que bloquea la última fila (`SELECT ... FOR UPDATE` sobre la cola o `pg_advisory_xact_lock`) para que dos transacciones concurrentes no tomen el mismo `prev_hash`; función `verify_chain(rows) -> VerifyResult(ok, broken_at_seq)` pura sobre una secuencia de filas.
- **Front:** No aplica.

## Criterios de aceptación

1. Tres llamadas a `record` producen tres filas con `seq` consecutivos donde el `prev_hash` de cada una es el `hash` de la anterior y la primera usa 64 ceros.
2. `chain_hash` es determinista: la misma fila con claves en distinto orden produce el mismo hash.
3. Un `UPDATE` o `DELETE` sobre `audit.audit_log`, incluso como dueño de la tabla, es rechazado por la base.
4. Alterar a mano el `after` de la fila 2 (deshabilitando el trigger en la prueba) hace que `verify_chain` devuelva `ok = false` y `broken_at_seq = 2`.
5. Dos transacciones concurrentes que auditan a la vez producen una cadena válida (sin dos filas con el mismo `prev_hash`).
6. La especificación de `canonical` queda documentada en `docs/adr/` como decisión irreversible (lo redacta US-119; aquí se deja el texto en el docstring).
7. Las fechas de `at` son `TIMESTAMPTZ` en UTC.

## Escenarios BDD

```gherkin
# language: es
Característica: Cadena de auditoría

  Escenario: Tres filas encadenadas
    Dado una tabla de auditoría vacía
    Cuando registro tres acciones auditadas
    Entonces cada fila guarda el hash de la anterior
    Y la verificación de la cadena es correcta

  Escenario: Fila alterada rompe la cadena
    Dado una cadena de cinco filas válida
    Cuando altero a mano el campo "after" de la fila con seq 2
    Y verifico la cadena
    Entonces el resultado es "rota en seq 2"

  Escenario: Edición prohibida por la base
    Dado una fila de auditoría existente
    Cuando ejecuto un UPDATE sobre ella
    Entonces PostgreSQL rechaza la operación
```

## Endpoints

- Ninguno (la consulta y la verificación HTTP están en EP-11).

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** sí, `audit.audit_log` y la función y trigger `audit.forbid_mutation()`.
- **Trigger / restricciones:** `BEFORE UPDATE OR DELETE ... FOR EACH ROW EXECUTE FUNCTION audit.forbid_mutation()`; `CHECK (action IN (...))`.
- **Funciones puras a probar:** `canonical` (orden de claves, fechas, UUID, None, acentos), `chain_hash`, `verify_chain` (cadena vacía, una fila, rota al inicio, al medio y al final).
- **Pruebas:** puras, service con base real (trigger, concurrencia con dos sesiones).
- **Archivos principales:** `api/src/app/core/audit.py`, `api/migrations/versions/*_audit_log.py`.

## Supuestos

- Supuesto: `hashlib` se usa dentro de `core/audit.py` para SHA-256; como `banned-api` lo prohíbe fuera de `core/crypto` y `core/security`, el cálculo se delega a una función de `core/crypto` (`crypto.sha256(data)`) o se agrega `core/audit.py` a la excepción de ruff. Se elige delegar en `core/crypto` para no ampliar la excepción.

## Dependencias

- US-012 · Base de datos y Alembic multiesquema.

## INVEST

- **Independiente:** solo requiere la base.
- **Negociable:** mecanismo de bloqueo para la concurrencia.
- **Valiosa:** es la evidencia de RN-16 y el soporte ante la Ley 1581.
- **Estimable:** acotada.
- **Pequeña:** dos o tres días.
- **Testeable:** cadena rota detectada en seq exacto.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas puras y con PostgreSQL real en verde
- [ ] Migración aplicada y reversible
- [ ] Revisión de PR aprobada
