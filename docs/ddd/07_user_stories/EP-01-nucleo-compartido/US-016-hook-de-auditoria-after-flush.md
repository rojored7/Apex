# US-016 · Como equipo quiero que toda tabla marcada `__audited__ = True` escriba su auditoría automáticamente en el `after_flush` para que ningún módulo pueda olvidarse de auditar un cambio

- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context:** Audit (hook en `core/audit.py`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero un hook `after_flush` de SQLAlchemy que, para cada modelo con `__audited__ = True`, registre `insert`, `update` o `delete` con `before` y `after` y el usuario de la petición
para que socios, planes, membresías, pagos, usuarios y configuración queden auditados sin código repetido en cada service

## Contexto de dominio

- **Aggregate / entidades:** `AuditEntry`; tablas auditadas de v0.1: `members`, `plans`, `memberships`, `payments`, `users`, `settings_sections`.
- **Reglas que aplica:** RN-16; RN-13 (los campos cifrados se guardan como blob, nunca en claro); `03_context_map.md` (Audit ← todos, Published Language por hook; Audit no depende de nadie); regla de datos 3 (`created_by`).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `audit.diff_row(before, after) -> (before, after)` (solo columnas cambiadas en `update`)

## Alcance

- **Backend:** variable de contexto `current_actor` (`contextvars`) con el `user_id` de la petición (la fija la dependencia de autenticación de US-034; en CLI y worker se fija explícitamente con `SYSTEM_USER_ID` o con el usuario de `--as`); listener `after_flush` sobre la sesión que recorre `session.new`, `session.dirty` (con cambios reales según `inspect(obj).attrs[...].history`) y `session.deleted` de modelos con `__audited__ = True` y llama `record(...)` de US-015 en la misma transacción; serializa columnas en su forma persistida (los campos `Encrypted` se toman como el blob `apx1....`, nunca el valor descifrado); un borrado lógico (`deleted_at` de nulo a fecha) se registra como `update`; listener `before_flush` que llena `created_by` en inserciones con `current_actor`; acción `insert` en altas.
- **Front:** No aplica.

## Criterios de aceptación

1. Insertar una fila de un modelo de prueba auditado deja una fila en `audit.audit_log` con `action = insert`, `after` con sus columnas y `user_id` igual al actor de la petición.
2. Actualizar dos columnas deja `action = update` con `before` y `after` solo de esas dos columnas.
3. Una actualización sin cambios reales no genera fila de auditoría.
4. Un modelo sin `__audited__` no genera filas.
5. Para un campo cifrado, `before` y `after` contienen el blob con prefijo `apx1.` y nunca el texto en claro (prueba con un modelo que usa `Encrypted`, activa cuando exista US-028).
6. Si la transacción se revierte, tampoco queda la fila de auditoría.
7. En CLI y worker, sin actor explícito, el `flush` de un modelo auditado falla con error claro (no se audita con `user_id` vacío por accidente).
8. `created_by` se llena automáticamente con el actor en cada inserción de un modelo con `CommonColumnsMixin`.

## Escenarios BDD

```gherkin
# language: es
Característica: Auditoría automática por hook

  Escenario: Cambio auditado con antes y después
    Dado un modelo auditado con una fila existente
    Y un actor autenticado "admin-1"
    Cuando cambio su campo "notes" y confirmo la transacción
    Entonces existe una fila de auditoría "update" con "before" y "after" de "notes"
    Y el user_id es "admin-1"

  Escenario: Campo cifrado nunca en claro
    Dado un socio con documento "1020304" cifrado
    Cuando se audita la inserción
    Entonces el "after" contiene un valor que empieza por "apx1."
    Y no contiene "1020304"

  Escenario: Proceso sin actor
    Dado un comando de CLI que no fijó actor
    Cuando inserta una fila de un modelo auditado
    Entonces el flush falla indicando que falta el actor
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no (usa la tabla de US-015).
- **Trigger / restricciones:** ninguno nuevo.
- **Funciones puras a probar:** `diff_row` (sin cambios, un cambio, cambio a nulo), serialización de tipos (UUID, fecha, `Decimal` prohibido, enum).
- **Pruebas:** service con base real (insert, update, delete lógico, rollback, sin actor); prueba de rendimiento básica: 500 inserciones auditadas en menos de 5 s (insumo para la importación de US-112).
- **Archivos principales:** `api/src/app/core/audit.py`, `api/src/app/core/db.py` (registro del listener).

## Supuestos

- Supuesto: worker y CLI actúan con `SYSTEM_USER_ID` (`system@apex.local`, expuesto en `core/context.py`; N-15), o con el usuario de `--as <email>` cuando una persona ejecuta el comando.

## Dependencias

- US-015 · Tabla de auditoría y cadena de hashes.
- US-034 · current_user (suave: el actor por HTTP sale del usuario autenticado; sin ella el actor se fija a mano; agregado en consolidación)

## INVEST

- **Independiente:** solo requiere la tabla de auditoría; el caso cifrado se activa con US-028.
- **Negociable:** forma de propagar el actor.
- **Valiosa:** garantiza que ningún cambio quede sin rastro.
- **Estimable:** mecanismo de SQLAlchemy conocido.
- **Pequeña:** tres a cuatro días.
- **Testeable:** filas de auditoría verificables por caso.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas con PostgreSQL real en verde; cobertura de 80 % o más
- [ ] Revisión de PR aprobada
