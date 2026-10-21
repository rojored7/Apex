# US-024 · Como equipo quiero las tablas crypto_keys, crypto_ops y crypto_jobs para registrar qué llave protege cada clase de dato, cada uso del bus y el progreso de los trabajos masivos

- **Épica:** EP-02 · Bus de criptografía y cifrado de datos personales
- **Bounded context:** Crypto (esquema `crypto`, `core/crypto/models.py`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero las tablas `crypto.crypto_keys`, `crypto.crypto_ops` y `crypto.crypto_jobs` con sus invariantes en la base
para que el inventario de llaves, la bitácora inmutable y el progreso de rotaciones existan desde v0.1 y nunca contengan material en claro

## Contexto de dominio

- **Aggregate / entidades:** `CryptoKey`, `CryptoOp`, `CryptoJob` (`02_domain_model.md` 2.13).
- **Reglas que aplica:** RN-13; RN-14 (llaves nunca se borran); `CLAUDE.md` bus punto 7 (metadatos, nunca material en claro; bitácora inmutable); invariante "una sola llave `active` por (`purpose`, `data_class`)".
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** modelos SQLAlchemy y migración de Alembic en el esquema `crypto`. `crypto_keys`: `id`, `purpose` (`encrypt` | `index` | `sign`), `data_class`, `algorithm` (`A256GCM` | `HMAC-SHA256` | `Ed25519` | `ML-DSA-65`), `provider` (`local` | `openbao`), `version` int, `state` (`active` | `decrypt_only` | `retired`), `wrapped_material` (bytes envueltos o referencia del proveedor), `rotated_at`, `rotate_by`, columnas comunes. `crypto_ops`: `id`, `at`, `user_id`, `verb`, `data_class`, `key_id`, `key_version`, `record_id`, `result` (`ok` | `error`), `batch_id`, `count` (filas del lote). `crypto_jobs`: `id`, `kind` (`rotate` | `reencrypt` | `migrate_provider`), `data_class`, `status` (`pending` | `running` | `done` | `failed`), `total`, `done`, `started_at`, `finished_at`, `error`.
- **Front:** No aplica

## Criterios de aceptación

1. Una migración de Alembic crea el esquema `crypto` y las tres tablas; `alembic downgrade -1` las elimina en una base vacía.
2. Toda tabla lleva `id` UUID, `created_at`, `updated_at` (TIMESTAMPTZ en UTC) y `created_by`.
3. Índice único parcial en `crypto_keys(purpose, data_class) WHERE state = 'active'`: insertar una segunda llave `active` para el mismo par falla en la base.
4. `CHECK` sobre los enums `purpose`, `algorithm`, `provider`, `state`, `verb`, `result`, `kind` y `status`.
5. Trigger en `crypto_ops` que rechaza todo `UPDATE` y todo `DELETE` (append-only).
6. Trigger en `crypto_keys` que rechaza `DELETE` (las llaves nunca se borran, RN-14); `UPDATE` permitido solo sobre `state`, `rotated_at`, `rotate_by` y `updated_at`.
7. `crypto_jobs` permite `UPDATE` de progreso (`status`, `done`, `finished_at`, `error`) y rechaza `DELETE`.
8. Ninguna columna de `crypto_keys` almacena material en claro: `wrapped_material` solo acepta bytes envueltos (verificado en US-025 con prueba de que el valor no es igual a la DEK).
9. Las tablas no son `__audited__` (su propia bitácora es `crypto_ops`) y la prueba de arquitectura de tablas auditadas (US-107) las lista como excluidas a propósito.

## Escenarios BDD

```gherkin
# language: es
Característica: Tablas del contexto Crypto

  Escenario: Crear el esquema en una base limpia
    Dado una base PostgreSQL 16 vacía
    Cuando se ejecuta "alembic upgrade head"
    Entonces existen crypto.crypto_keys, crypto.crypto_ops y crypto.crypto_jobs

  Escenario: Solo una llave activa por clase de dato
    Dado una llave active de purpose "encrypt" para "member.document"
    Cuando se inserta otra llave active de purpose "encrypt" para "member.document"
    Entonces la base rechaza la inserción por la restricción única parcial

  Escenario: La bitácora es inmutable
    Dado una fila en crypto.crypto_ops
    Cuando se ejecuta un UPDATE sobre esa fila
    Entonces la base rechaza la operación
    Y cuando se ejecuta un DELETE sobre esa fila también la rechaza

  Escenario: Las llaves no se borran
    Dado una llave en estado retired
    Cuando se ejecuta DELETE sobre crypto.crypto_keys
    Entonces la base rechaza la operación

  Escenario: Valor fuera del enum
    Cuando se inserta una llave con algorithm "DES"
    Entonces la base rechaza la inserción por el CHECK
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** sí; esquema `crypto`, tres tablas, índice único parcial, CHECKs y triggers (funciones `plpgsql`).
- **Trigger / restricciones:** `crypto_ops_no_update_delete`, `crypto_keys_no_delete_limited_update`, `crypto_jobs_no_delete`.
- **Funciones puras a probar:** no hay.
- **Pruebas:** service con base real (`db_test`) para cada trigger y restricción; prueba de migración arriba y abajo.
- **Archivos principales:** `api/src/app/core/crypto/models.py`, `api/migrations/versions/<rev>_crypto_schema.py`, `api/tests/crypto/test_crypto_tables.py`.

## Supuestos

- Supuesto: `crypto_ops` agrega la columna `count` para registrar el número de registros de un lote (no está en el modelo; nace de la mitigación "registrar por lote" de EP-02).
- Supuesto: `crypto_jobs.status` usa los valores `pending`, `running`, `done`, `failed` (el modelo nombra `status` sin enumerarlo).

## Dependencias

- US-012 · Base de datos y Alembic multiesquema

## INVEST

- **Independiente:** solo depende de la base y Alembic.
- **Negociable:** nombres de estados de job y columna `count`.
- **Valiosa:** es el inventario y la evidencia del uso de llaves.
- **Estimable:** tres tablas y tres triggers.
- **Pequeña:** una migración.
- **Testeable:** cada restricción se prueba contra la base.

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
