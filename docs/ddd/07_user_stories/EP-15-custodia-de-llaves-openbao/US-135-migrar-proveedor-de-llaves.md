# US-135 · Como administrador quiero migrar las llaves del proveedor local a OpenBao sin recifrar datos para pasar a la custodia segura en minutos y sin riesgo para la información

- **Épica:** EP-15 · Custodia de llaves con OpenBao
- **Bounded context:** Crypto (`core/crypto/service.py`, `cli.py`)
- **Versión:** v0.2
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero ejecutar `cli migrate-provider local→openbao`
para re-envolver cada DEK con la KEK de OpenBao, dejar `provider = openbao` en `crypto_keys` y poder retirar el archivo de la KEK local

## Contexto de dominio

- **Aggregate / entidades:** CryptoKey, CryptoJob (`kind = migrate_provider`), CryptoOp.
- **Reglas que aplica:** RN-13; regla de datos 8 (migraciones de datos como comandos de `cli.py`, idempotentes y auditados); invariante "el material en claro nunca se persiste"; `CLAUDE.md` (detenerse antes de decisiones irreversibles).
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** `crypto.plan_provider_migration(keys) -> list[KeyId]` (solo las que aún tienen `provider = local`).

## Alcance

- **Backend:** comando `migrate-provider --from local --to openbao --as <email> [--dry-run]` que crea un `CryptoJob(kind=migrate_provider)`, por cada `CryptoKey` con `provider = local`: desenvuelve con `LocalFileProvider`, envuelve con `OpenBaoProvider`, verifica que el nuevo envoltorio desenvuelve a la misma DEK y actualiza `wrapped_material` y `provider` en una transacción por llave; registra `unwrap` y `wrap` en `crypto_ops` con el mismo `batch_id`; avanza `done/total`; al terminar marca el job `done`. Reanudable: si se interrumpe, la siguiente ejecución continúa con las llaves que siguen en `local`. Nunca toca las columnas cifradas de las tablas de negocio.
- **Front:** No aplica.

## Criterios de aceptación

1. Después de la migración, todas las filas de `crypto_keys` tienen `provider = openbao` y los datos cifrados de v0.1 se leen sin recifrar (los blobs de `members.members` no cambian byte a byte).
2. Borrar el archivo de la KEK local después de migrar y reiniciar con `CRYPTO_PROVIDER=openbao` no afecta la lectura de datos.
3. Ejecutar el comando una segunda vez no cambia nada y termina con código 0 con el mensaje "nada que migrar".
4. Si el proceso se interrumpe a mitad, ninguna llave queda inutilizable (cada llave cambia en su propia transacción y solo después de verificar el nuevo envoltorio) y la siguiente ejecución completa el resto.
5. El `CryptoJob` registra `total`, `done`, `started_at`, `finished_at` y `error` si lo hubo.
6. Cada llave migrada deja `unwrap` (local) y `wrap` (openbao) en `crypto_ops` con el mismo `batch_id`, `key_id` y `key_version`, y el comando deja una entrada en auditoría con el usuario de `--as`.
7. `--dry-run` lista las llaves que se migrarían sin escribir nada.
8. Antes de empezar, el comando exige confirmación escrita (`MIGRAR`) y recuerda tener un backup reciente y la KEK local respaldada.

## Escenarios BDD

```gherkin
# language: es
Característica: Migrar proveedor de llaves

  Escenario: Migración completa sin recifrar
    Dado cinco DEK con provider "local" y socios cifrados
    Y OpenBao desellado
    Cuando ejecuto "cli migrate-provider --from local --to openbao" y confirmo "MIGRAR"
    Entonces las cinco llaves quedan con provider "openbao"
    Y los blobs de los socios no cambian
    Y el job "migrate_provider" queda "done" con 5 de 5

  Escenario: Reanudar una migración interrumpida
    Dado una migración interrumpida con 2 de 5 llaves migradas
    Cuando ejecuto el comando otra vez
    Entonces se migran las 3 restantes
    Y las 2 ya migradas no cambian
```

## Endpoints

- Ninguno. Comando `uv run python -m app.cli migrate-provider --from local --to openbao --as <email> [--dry-run]`.

## Pantalla

- Ninguna (el job se verá en `Llaves`, US-144).

## Notas técnicas

- **Migración:** no de esquema.
- **Trigger / restricciones:** `crypto_ops` append-only; una sola `CryptoJob` de tipo `migrate_provider` en curso (índice parcial).
- **Funciones puras a probar:** `plan_provider_migration` con llaves mixtas.
- **Pruebas:** integración con OpenBao real; interrupción simulada a mitad; idempotencia; comparación byte a byte de blobs.
- **Archivos principales:** `api/src/app/core/crypto/service.py`, `api/src/app/cli.py`, `api/tests/crypto/test_migrate_provider.py`.

## Supuestos

- Supuesto: la confirmación escrita `MIGRAR` y el parámetro `--as` no están en los documentos; se agregan por la regla de detenerse ante decisiones irreversibles y para atribuir la auditoría.

## Dependencias

- US-134 · Proveedor OpenBao.
- US-029 · Bitácora `crypto_ops` por lote.

## INVEST

- **Independiente:** solo toca `crypto_keys` y `crypto_jobs`.
- **Negociable:** forma de confirmación.
- **Valiosa:** completa el paso a custodia real.
- **Estimable:** cinco llaves en v0.1.
- **Pequeña:** un comando con job.
- **Testeable:** byte a byte, idempotencia y reanudación.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de integración y de reanudación en verde; cobertura de 80 % o más
- [ ] Auditoría verificada del comando
- [ ] Revisión de PR aprobada
