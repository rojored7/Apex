# US-199 · Como administrador quiero re-envolver las DEK existentes con ML-KEM en un trabajo reanudable para proteger los datos ya guardados sin recifrarlos

- **Épica:** EP-26 · Cierre criptográfico post-cuántico
- **Bounded context:** Crypto (`core/crypto`, `CryptoJob`)
- **Versión:** v1.0
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** Ninguna (historia sin front; el progreso se ve en `Llaves`, sección de trabajos)

## Historia

Como administrador
quiero ejecutar un comando que re-envuelva todas las DEK con ML-KEM y que pueda retomarse si se interrumpe
para que ninguna llave quede inutilizable y los datos no se tengan que recifrar

## Contexto de dominio

- **Aggregate / entidades:** `CryptoJob(kind = rewrap)`, `CryptoKey`, `CryptoOp`.
- **Reglas que aplica:** una sola llave `active` por (`purpose`, `data_class`); material en claro nunca persistido; operación por lote con `batch_id`; la migración de proveedor (US-135) es el patrón.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `crypto.pending_rewrap(keys, target_alg) -> list[key_id]`

## Alcance

- **Backend:** `cli rewrap-keys --to ML-KEM-768 [--resume]`; crea un `CryptoJob(kind = rewrap)` con `total` igual al número de llaves pendientes; por cada llave: unwrap con el algoritmo actual, wrap con ML-KEM, verificación de unwrap de la nueva envoltura, y solo entonces actualización atómica de `wrapped_material` y `wrap_algorithm`. Ver progreso en `GET /crypto/jobs` (US-144).
- **Front:** No aplica.

## Criterios de aceptación

1. El comando re-envuelve cada DEK sin tocar ningún dato cifrado de las tablas de negocio (los blobs `apx1.*` no cambian, verificado por hash de las columnas antes y después).
2. Cada llave se actualiza en su propia transacción y solo después de comprobar que la nueva envoltura se desenvuelve a la misma DEK; si la comprobación falla, la llave queda con la envoltura anterior y el job registra el error.
3. Interrumpir el proceso a mitad y correr `--resume` continúa con las llaves pendientes; ninguna llave queda sin envoltura válida en ningún momento.
4. Correr el comando cuando ya no hay pendientes no cambia nada y termina con código 0 (idempotente).
5. Solo puede haber un job `rewrap` en curso; un segundo intento termina con código distinto de 0 y mensaje claro.
6. Cada operación deja filas en `crypto_ops` (`unwrap`, `wrap`) con el mismo `batch_id`; el `CryptoJob` registra `total`, `done`, `started_at`, `finished_at` y `error`.
7. Después del job, todos los datos se leen sin recifrar y `crypto_keys.wrap_algorithm = ML-KEM-768` en todas las llaves no `retired`.
8. El comando exige `--confirm` y se niega a correr si el último backup no tiene firma válida (US-196).

## Escenarios BDD

```gherkin
# language: es
Característica: Re-envoltura reanudable de llaves

  Escenario: Re-envoltura completa
    Dado que hay 8 llaves envueltas con el algoritmo anterior
    Y que el último backup tiene firma válida
    Cuando el administrador ejecuta la re-envoltura con confirmación
    Entonces las 8 llaves quedan envueltas con ML-KEM-768
    Y los datos cifrados de los socios no cambian y se siguen leyendo

  Escenario: Interrupción y reanudación
    Dado que la re-envoltura se interrumpió después de 3 llaves
    Cuando el administrador la ejecuta con reanudar
    Entonces el trabajo termina las 5 llaves restantes
    Y ninguna llave queda sin poder abrirse
```

## Endpoints

- Ninguno nuevo. Comando: `cli rewrap-keys --to ML-KEM-768 --confirm [--resume]`. Progreso visible en `GET /api/v1/crypto/jobs` (admin).

## Pantalla

- Ninguna propia; la sección de trabajos de `Llaves` muestra el job `rewrap` con su barra de progreso.

## Notas técnicas

- **Migración:** sí si `CryptoJob.kind` tiene CHECK: agregar el valor `rewrap`.
- **Trigger / restricciones:** índice único parcial de un job en curso por `kind` (si no existe desde US-145).
- **Funciones puras a probar:** `pending_rewrap` con llaves mezcladas y `retired`.
- **Pruebas:** integración con OpenBao real; prueba de interrupción simulada (excepción tras N llaves) y reanudación; hash de columnas cifradas antes y después; idempotencia.
- **Archivos principales:** `api/src/app/core/crypto/service.py`, `api/src/app/cli.py`.
- **Irreversibilidad:** re-envolver llaves es irreversible en la práctica (la envoltura anterior se sobrescribe). `CLAUDE.md` exige detenerse y preguntar antes de ejecutarlo: la ejecución en producción requiere aprobación explícita del dueño, backup firmado y verificado, y respaldo fuera del servidor de las llaves de desellado de OpenBao. La historia entrega el comando; no lo ejecuta en producción.

## Supuestos

- Supuesto: el valor `rewrap` de `CryptoJob.kind` no está en el modelo (`rotate`, `reencrypt`, `migrate_provider`); se agrega.
- Supuesto: las llaves `retired` también se re-envuelven solo si aún tienen datos que descifrar; si no, se omiten.

## Dependencias

- US-198 · Envoltura de llaves con ML-KEM
- US-135 · Migrar proveedor de llaves (patrón de re-envoltura reanudable)
- US-196 · firma de backups (no corre sin un backup firmado previo; agregado en consolidación)

## INVEST

- **Independiente:** un comando sobre el proveedor ya preparado.
- **Negociable:** tratamiento de llaves retiradas.
- **Valiosa:** protege los datos ya guardados.
- **Estimable:** sigue el patrón de `migrate-provider`.
- **Pequeña:** cabe en un sprint.
- **Testeable:** interrupción y reanudación verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de integración con OpenBao real en verde; cobertura de 80 % o más en lo tocado
- [ ] Migración aplicada con `alembic upgrade head` y reversible (si aplica)
- [ ] Procedimiento de ejecución documentado con el punto de aprobación
- [ ] Revisión de seguridad del PR aprobada
