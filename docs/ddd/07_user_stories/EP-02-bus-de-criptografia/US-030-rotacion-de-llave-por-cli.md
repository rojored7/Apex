# US-030 · Como equipo quiero rotar la llave de una clase de dato por CLI con recifrado por lotes y progreso para responder a una sospecha de filtración sin dejar datos ilegibles

- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context:** Crypto (`core/crypto/service.py`, `cli.py`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 8
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front; la pantalla llega en US-145)

## Historia

Como equipo
quiero `cli rotate-key <data_class>` que cree una DEK nueva, pase la anterior a `decrypt_only`, recifre por lotes de 500 con progreso en `crypto_jobs` y retire la anterior al terminar
para que el administrador pueda rotar una llave sin detener el sistema y con evidencia del proceso

## Contexto de dominio

- **Aggregate / entidades:** `CryptoKey`, `CryptoJob` (`kind = rotate` y `reencrypt`), `CryptoOp`.
- **Reglas que aplica:** invariantes de 2.13: una sola `active` por (`purpose`, `data_class`); la anterior queda `decrypt_only` hasta que el job termine y la retire; material en claro nunca persistido. Regla de datos 8 (migraciones de datos son comandos de `cli.py`, idempotentes y auditados). RN-14 (llaves nunca se borran).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `crypto.next_key_state(current_state, job_status) -> state` (transiciones permitidas)

## Alcance

- **Backend:** servicio `crypto.service.rotate(data_class, reason, by)` y recifrado `reencrypt_batch(data_class, job_id, batch_size=500)`. Cada clase de dato declara qué tabla y columnas cifra (registro de US-025). Para clases con índice, se rota también la llave `index` si se pide (`--index`), recalculando `_idx`. El job es reanudable: procesa filas cuyo blob tenga `key_id` distinto de la llave activa. Al llegar `done = total`, la llave anterior pasa a `retired`. Una sola rotación en curso por `data_class`.
- **Front:** No aplica

## Criterios de aceptación

1. Tras `rotate-key member.document` existe una llave `active` nueva con `version` anterior + 1 y la anterior queda `decrypt_only` con `rotated_at` y `rotate_by`.
2. Durante el recifrado, todos los documentos se leen sin error (los viejos con la `decrypt_only`, los nuevos con la `active`).
3. El recifrado procesa lotes de 500 filas, cada lote en su propia transacción, y actualiza `crypto_jobs.done` después de cada lote.
4. Al terminar, ninguna fila de `members.members` tiene un blob con el `key_id` anterior, el job queda `done` y la llave anterior `retired`.
5. Interrumpir el comando a la mitad y volver a correrlo continúa el mismo job sin recifrar dos veces las filas ya migradas y sin crear otra llave.
6. Lanzar una segunda rotación de la misma clase con un job `running` termina con error "rotación en curso" y no crea llave.
7. Cada lote deja una fila en `crypto_ops` con `verb = encrypt`, `batch_id` y `count`; la rotación deja una fila `verb = rotate`.
8. Si un lote falla, el job queda `failed` con `error`, la llave anterior sigue `decrypt_only` (nunca `retired`) y los datos siguen legibles.
9. El comando exige `--reason` no vacío; sin él termina con código distinto de 0.
10. La rotación queda en la auditoría del sistema con el motivo (acción registrada en `audit_log` sobre `crypto_keys`).

## Escenarios BDD

```gherkin
# language: es
Característica: Rotación de llave por CLI

  Antecedentes:
    Dado 1.200 socios con documento cifrado con la llave versión 1

  Escenario: Rotación completa
    Cuando el operador ejecuta "cli rotate-key member.document --reason 'rotación anual'"
    Entonces existe la llave versión 2 en estado active
    Y el job avanza en lotes de 500 hasta done 1200
    Y la llave versión 1 queda retired
    Y todos los documentos se leen correctamente

  Escenario: Reanudar tras una interrupción
    Dado un job de rotación interrumpido con done 500
    Cuando el operador vuelve a ejecutar el comando
    Entonces el job continúa desde las filas pendientes
    Y no se crea una llave versión 3

  Escenario: Rotación concurrente
    Dado un job de rotación running para "member.document"
    Cuando el operador ejecuta otra rotación de "member.document"
    Entonces el comando termina con error "rotación en curso"

  Escenario: Sin motivo
    Cuando el operador ejecuta "cli rotate-key member.document" sin --reason
    Entonces el comando termina con código distinto de 0 y no cambia ninguna llave

  Escenario: Falla en un lote
    Dado que el lote 2 falla por un error de base
    Cuando termina el comando
    Entonces el job queda failed con el error
    Y la llave versión 1 sigue decrypt_only
```

## Endpoints

- Ninguno. Comando: `uv run python -m app.cli rotate-key <data_class> --reason "<motivo>" [--index]`.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** índice único parcial de llave activa (US-024); el cambio de active a decrypt_only y la creación de la nueva van en la misma transacción.
- **Funciones puras a probar:** `next_key_state` (active→decrypt_only→retired; prohibido retired→active).
- **Pruebas:** integración con 1.200 filas de prueba, interrupción simulada, concurrencia con dos sesiones, falla inyectada.
- **Archivos principales:** `api/src/app/core/crypto/service.py`, `api/src/app/cli.py`, `api/tests/crypto/test_rotate.py`.
- **Riesgo:** CPU en horario de atención; el comando informa el total de filas antes de empezar.

## Supuestos

- Supuesto: la llave `index` solo se rota con `--index` explícito, porque exige recalcular todos los `_idx` y es una operación más delicada (el documento no distingue).

## Dependencias

- US-028 · Tipos de columna Encrypted y BlindIndexed
- US-029 · Bitácora crypto_ops por lote
- US-016 · hook de auditoría (la rotación se registra en audit_log; agregado en consolidación)

## INVEST

- **Independiente:** opera sobre el bus y cualquier tabla con `Encrypted`; se prueba con tabla de prueba antes de que exista Members.
- **Negociable:** tamaño de lote y rotación de índice.
- **Valiosa:** capacidad de respuesta ante filtración.
- **Estimable:** flujo conocido con job reanudable.
- **Pequeña:** al límite (8); no se parte porque rotar sin recifrar deja el proceso incompleto.
- **Testeable:** estados de llave y job exactos.

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
- [ ] Front: pruebas de componente y página; sin colores literales (si aplica)
- [ ] Migración aplicada con `alembic upgrade head` y reversible (si aplica)
- [ ] `docs/openapi.json` regenerado (si cambia el contrato)
- [ ] Auditoría verificada para las tablas tocadas (si aplica)
- [ ] Revisión de PR aprobada
