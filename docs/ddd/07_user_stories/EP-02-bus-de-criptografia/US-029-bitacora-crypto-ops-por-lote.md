# US-029 · Como equipo quiero que cada operación del bus quede en la bitácora crypto_ops, agrupada por lote cuando es masiva, para demostrar quién usó qué llave sin multiplicar escrituras

- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context:** Crypto (`core/crypto/bus.py`, tabla `crypto.crypto_ops`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero que `encrypt`, `decrypt`, `index`, `sign`, `verify`, `wrap`, `unwrap` y `rotate` escriban en `crypto_ops` quién, verbo, `data_class`, `key_id`, versión, `record_id` y resultado, con `batch_id` en operaciones por lote
para tener evidencia de cada uso de llave frente a la Ley 1581 sin que una lista de 1.000 socios produzca 1.000 escrituras

## Contexto de dominio

- **Aggregate / entidades:** `CryptoOp` (append-only).
- **Reglas que aplica:** RN-13; `CLAUDE.md` bus punto 7; `05_service_design.md` 3 core.crypto.bus ("en lotes, un `batch_id` por lote"); riesgo de EP-02 sobre el costo por operación.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** el bus recibe el contexto de operación (`user_id` del request o del CLI/worker, `record_id`) por un `contextvar` o parámetro. Operación individual: una fila con `count = 1`. Contexto de lote (`with bus.batch(verb, data_class) as b:`): una fila por (verbo, `data_class`, `key_id`) al cerrar el lote con `batch_id` y `count`. Un fallo registra `result = error` con el `record_id` afectado. La escritura va en la misma transacción que la operación de negocio.
- **Front:** No aplica

## Criterios de aceptación

1. Cifrar un campo de un socio deja exactamente una fila en `crypto_ops` con `verb = encrypt`, la `data_class`, `key_id`, `key_version`, `record_id` y `result = ok`.
2. Un lote que descifra 500 documentos deja una sola fila con `batch_id` no nulo y `count = 500`.
3. Un descifrado que falla (AAD incorrecto) deja una fila `result = error` con el `record_id`, aunque la operación de negocio se revierta (se registra en una transacción aparte o se reintenta el registro tras el rollback).
4. `user_id` es el usuario del request; en CLI y worker es `SYSTEM_USER_ID` o el de `--as` (N-15), con el `batch_id` del comando.
5. Ninguna fila contiene material de llave, texto en claro ni blob.
6. `crypto_ops` es append-only (trigger de US-024): un intento de `UPDATE` falla.

## Escenarios BDD

```gherkin
# language: es
Característica: Bitácora de operaciones criptográficas

  Escenario: Operación individual
    Dado un administrador autenticado
    Cuando el módulo de socios cifra el teléfono de un socio
    Entonces existe una fila en crypto_ops con verb "encrypt", data_class "member.phone" y result "ok"
    Y la fila tiene el user_id del administrador y el record_id del socio

  Escenario: Lote de descifrado
    Dado 500 socios con documento cifrado
    Cuando un comando descifra los 500 dentro de un lote
    Entonces existe una sola fila con count 500 y un batch_id

  Escenario: Falla de descifrado
    Dado un blob copiado de otro socio
    Cuando el bus intenta descifrarlo
    Entonces queda una fila con result "error" y el record_id del registro
    Y la fila no contiene el blob ni texto en claro
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna. La bitácora se consulta en `Llaves` desde v0.3 (US-144).

## Notas técnicas

- **Migración:** no (columnas en US-024).
- **Trigger / restricciones:** append-only de US-024.
- **Funciones puras a probar:** agregación del lote por (verbo, data_class, key_id).
- **Pruebas:** integración con base real; conteo de filas por operación y por lote; registro del error tras rollback.
- **Archivos principales:** `api/src/app/core/crypto/bus.py`, `api/src/app/core/crypto/oplog.py`, `api/tests/crypto/test_oplog.py`.

## Supuestos

- Supuesto: los errores de operación se registran en una transacción independiente para que el rollback del negocio no borre la evidencia (el documento no lo fija).
- Supuesto: el cálculo de índice en una búsqueda (`q` en la lista de socios) cuenta como operación individual con `record_id` nulo.

## Dependencias

- US-024 · Tablas crypto_keys, crypto_ops, crypto_jobs
- US-025 · Cifrado AES-GCM y formato de blob

## INVEST

- **Independiente:** solo el bus y la tabla.
- **Negociable:** granularidad de agregación por lote.
- **Valiosa:** evidencia de uso de llaves.
- **Estimable:** un registro y un contexto de lote.
- **Pequeña:** dos o tres días.
- **Testeable:** conteo exacto de filas.

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
