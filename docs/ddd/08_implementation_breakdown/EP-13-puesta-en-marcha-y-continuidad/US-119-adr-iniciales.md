# US-119 · ADR iniciales — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-13-puesta-en-marcha-y-continuidad/US-119-adr-iniciales.md`
- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context / módulo:** ninguno; documentación (`docs/adr/`) y una prueba en `api/tests/core/`
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

Los tres ADR documentan decisiones ya tomadas en `04_architecture_decision.md`, `CLAUDE.md` y DECISIONES.md. Lo que la historia pone mal se corrige con DECISIONES N-02 (normalización), N-06 (SHA-256 por el bus) y N-04 (formato de firma). La única elección abierta, dónde documentar la serialización canónica, la deja la historia al equipo y no cambia contrato. Se elige ADR-004.

## Resumen

Se escriben en `docs/adr/` cuatro documentos con las seis secciones fijas (Estado, Contexto, Decisión, Alternativas descartadas, Consecuencias, Cómo se verifica):

- `ADR-001-monolito-modular.md` resume `04_architecture_decision.md`: monolito modular, esquema por contexto, bus de eventos en la misma transacción, worker en la misma imagen y reglas de importación.
- `ADR-002-bus-de-criptografia.md` fija:
  - la única puerta del bus;
  - el formato del blob `apx1.<key_id>.<alg>.<nonce_b64url>.<ciphertext_b64url>`;
  - el AAD igual al id del registro;
  - el envelope de KEK y DEK;
  - la normalización del índice ciego de N-02;
  - el formato de firma de N-04;
  - `digest` de N-06;
  - la lista `banned-api`.
- `ADR-003-pagos-inmutables.md` fija el trigger, las cuatro columnas de anulación una sola vez y la prohibición de `DELETE`.
- `ADR-004-serializacion-canonica-de-auditoria.md` fija la serialización de la cadena con un ejemplo de entrada y su hash esperado. Ese ejemplo se convierte en prueba unitaria de `chain_hash`.

Cada ADR dice que cambiar la decisión exige detenerse y preguntar. Una prueba revisa que las secciones existan y que los archivos de prueba citados en "Cómo se verifica" existan.

## Correcciones aplicadas por DECISIONES.md

- Criterio 2: "`normalize_for_index` (minúsculas, sin espacios ni puntos)" → ADR-002 documenta la normalización vigente: NFKD sin diacríticos, minúsculas, sin espacios, puntos ni guiones; teléfono solo dígitos sin `57`/`+57` inicial; correo en minúsculas y sin espacios: corregido por DECISIONES N-02.
- La cadena de auditoría usa SHA-256 → ADR-004 dice que el hash lo calcula `core.crypto.bus.digest` y que `core/audit.py` no importa `hashlib`: corregido por DECISIONES N-06.
- ADR-002 agrega el formato de firma `apx1.<key_id>.<alg>.<sig_b64url>` y el registro de `data_class` como constante en `core/crypto/registry.py`: aceptado por DECISIONES N-04.
- ADR-002 agrega la regla de enmascarado en memoria (ninguna columna `*_hint`): corregido por DECISIONES N-01.
- ADR-002 agrega la regla de licencias de librerías criptográficas (sin GPL, LGPL ni AGPL) y la ampliación de la lista con `0BSD`, `ISC` y `OFL-1.1`: aceptado por DECISIONES N-49 (solo se cita).
- Supuesto de la historia "la serialización canónica va en ADR-002 salvo que el equipo cree ADR-004" → se crea ADR-004, para que ADR-002 no mezcle cifrado con auditoría. Es la alternativa que la historia permite; no cambia alcance.

## Validación contra el dominio

- RN-02 (pago inmutable) → ADR-003: el trigger `payments.forbid_mutation()` de `0011_payments_immutability` deja pasar solo `voided`, `void_reason`, `voided_by` y `voided_at`, de `voided = false` a `true`, una sola vez; prohíbe `DELETE`; la regla se repite en código en `payments.service.can_void`.
- RN-13 (datos sensibles cifrados) → ADR-002.
- RN-16 (cadena de auditoría) → ADR-004: `hash = digest(prev_hash || canonical(row))`, con `prev_hash` inicial de 64 ceros. `canonical` es JSON con claves ordenadas, separadores `(",", ":")`, UTF-8, fechas ISO 8601 UTC con `Z`, UUID en minúsculas y `None` como `null` (US-015).
- Q27 y N-48 se citan en ADR-002 como evolución prevista: ML-DSA para firmas desde v0.3 y backups sin firma antes de v1.0.
- Confirmado: sin discrepancias con el dominio.

## Validación contra la arquitectura

- `04_architecture_decision.md` sección 1 ya anuncia que ADR-001 sale de sus secciones 1 a 8 (en la tarea 12 del plan).
- `CLAUDE.md` (bus, reglas 1 a 9) es la fuente de ADR-002. Las ampliaciones del bus propuestas en este lote (`digest_file` y `verify_age_archive` de US-115) se nombran en ADR-002 como "propuestas pendientes del gate" y no como decididas.
- "Cómo se verifica" de cada ADR apunta a pruebas reales:
  - ADR-001: `tests/architecture/test_no_cross_models.py` y `test_every_route_has_role.py`;
  - ADR-002: `tests/architecture/test_banned_imports.py`, la prueba de que no hay datos en claro de US-031 y las pruebas del índice ciego de US-026;
  - ADR-003: `tests/payments/test_immutability_trigger.py` de US-096;
  - ADR-004: `tests/core/test_chain_hash_vector.py`.
- La historia no toca código de producción; solo agrega una prueba.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `docs/adr/ADR-001-monolito-modular.md`: Estado (Aceptado, fecha y versión v0.1), Contexto (un gimnasio, menos de 10 usuarios, consistencia de S5 y RN-03), Decisión (monolito modular, esquema por contexto, eventos en la misma transacción, worker en la misma imagen, reglas de importación entre módulos), Alternativas descartadas (microservicios, monolito sin módulos, BaaS, cola externa), Consecuencias (trade-offs de la sección 8), Cómo se verifica, y la regla de detenerse y preguntar — 1,5 h
- [ ] T2 · `docs/adr/ADR-002-bus-de-criptografia.md`: la única puerta (`encrypt`, `decrypt`, `blind_index`, `sign`, `verify`, `digest`), `data_class` como registro en `core/crypto/registry.py`, envelope KEK/DEK con AES-256-GCM para envolver (N-03), formato exacto del blob y de la firma con un ejemplo, AAD igual al id del registro asignado en Python antes del flush, índice ciego HMAC-SHA-256 con la normalización de N-02 y ejemplos (`1.020-304` → `1020304`; `+57 300 123 4567` → `3001234567`), enmascarado en memoria (N-01), lista `banned-api`, evolución prevista (OpenBao v0.2, ML-DSA v0.3, ML-KEM v1.0) y ampliaciones pendientes del gate — 2 h
- [ ] T3 · `docs/adr/ADR-003-pagos-inmutables.md`: RN-02, trigger `BEFORE UPDATE OR DELETE`, las cuatro columnas de anulación una sola vez, corrección con pago nuevo, regla espejo en `payments.service.can_void`, el evento `PaymentVoided` y su efecto en la cobertura (US-087), y alternativas descartadas (borrado lógico de pagos, edición con historial) — 1 h
- [ ] T4 · `docs/adr/ADR-004-serializacion-canonica-de-auditoria.md`: reglas de `canonical(row)`, fórmula del hash con `bus.digest`, `prev_hash` inicial, un salto de `seq` cuenta como ruptura (N-30), ejemplo de entrada completo (una fila `insert` de `plans` con valores fijos) y su hash esperado en hexadecimal, y la advertencia de que cambiar la serialización con datos invalida toda la cadena — 1 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T5 · `api/tests/core/test_chain_hash_vector.py`: `chain_hash("0"*64, fila_del_ejemplo)` es igual al hash escrito en ADR-004 (el test lee el valor esperado del ADR con una expresión regular sobre un bloque marcado, para que documento y código no diverjan) — 1 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T6 · `api/tests/architecture/test_adr_docs.py`: cada `docs/adr/ADR-00[1-4]-*.md` tiene los encabezados de las seis secciones y la frase de detenerse y preguntar; toda ruta `tests/...py` citada en "Cómo se verifica" existe en `api/tests/` — 1 h

### Front
- No aplica.

### DevOps
- [ ] T7 · `docs/adr/README.md` con el índice de los cuatro ADR y la plantilla de las seis secciones para los siguientes; enlace desde el README del repositorio — 0,5 h

### Seguridad
- [ ] T8 · Revisión: ADR-002 no contiene material de llave ni ejemplos con llaves reales (los ejemplos usan llaves de prueba marcadas como tales); el ejemplo de ADR-004 no usa datos personales reales — 0,5 h

## Orden de ejecución

1. T4, luego T5 (el vector de prueba sale del ADR y debe pasar contra `chain_hash` de US-015).
2. T1, T2 y T3.
3. T6.
4. T7 y T8.

## Dependencias técnicas

- US-015 · Tabla de auditoría y cadena de hashes: `chain_hash` y `canonical`.
- US-016 · Hook de auditoría after_flush.
- US-025 · Cifrado AES-GCM y formato de blob.
- US-026 · Índice ciego HMAC con N-02.
- US-027 · Firma en el bus (formato de N-04).
- US-031 · Pruebas de arquitectura criptográfica (`test_banned_imports.py`).
- US-022 y US-035 · Pruebas de arquitectura de models cruzados y de rutas con rol.
- US-096 · Inmutabilidad de pagos en la base (prueba del trigger).

## Endpoints

- Ninguno.

## Riesgos

- ADR desactualizado frente al código (por ejemplo, la normalización cambia y el ADR no): se documenta algo falso — mitigación: T5 ata el vector de ADR-004 al código y T6 ata las rutas de prueba; el ejemplo de normalización de ADR-002 también se agrega a las pruebas de US-026.
- Que el gate no apruebe las ampliaciones del bus de US-115 — mitigación: ADR-002 las nombra como pendientes y se actualiza al cerrar el gate.
- Las pruebas citadas no existen todavía si esta historia se adelanta — mitigación: el orden de v0.1 la deja al final (README, punto 9) y T6 falla si falta alguna.

## Estimación

- Backend: 6 h
- Front: 0 h
- Pruebas: 2 h
- DevOps / seguridad: 1 h
- **Total: 9 h**

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_chain_hash_vector.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `ls docs/adr/ADR-001-monolito-modular.md docs/adr/ADR-002-bus-de-criptografia.md docs/adr/ADR-003-pagos-inmutables.md docs/adr/ADR-004-serializacion-canonica-de-auditoria.md` encuentra los cuatro
- [ ] `grep -c "^## " docs/adr/ADR-00*.md` muestra al menos 6 por archivo
- [ ] Revisión del PR por alguien distinto del autor, con la lista de las seis secciones marcada
