# EP-26 · Cierre criptográfico post-cuántico — desglose técnico de épica

- **Épica:** `docs/ddd/06_epics/EP-26-cierre-criptografico-post-cuantico.md`
- **Versión:** v1.0
- **Historias:** US-196 a US-199 (4 historias, 21 puntos)

## Resumen

La épica cierra la v1.0 con cuatro cambios, todos dentro de `core/crypto`, `cli.py`, el worker y la imagen del api:

- Firma de cada backup con la `data_class` `backup.signature` por el verbo `sign` del bus, y verificación antes de restaurar y en `backup_check` (US-196).
- Formato CycloneDX del CBOM que ya existe desde v0.3 (US-197, sujeto a la pregunta de Q26).
- Envoltura de las DEK con ML-KEM-768 detrás del mismo `KeyProvider`: por Transit si OpenBao lo implementa, o con un adaptador sobre `liboqs-python` (US-198).
- Re-envoltura reanudable de las DEK existentes como `CryptoJob(kind = rewrap)`, sin recifrar datos (US-199).

Ningún módulo de negocio cambia: el algoritmo va en el dato (`crypto_keys.algorithm`, `wrap_algorithm`) y el que llama nunca lo elige.

## Correcciones aplicadas por DECISIONES.md

- US-196: los backups anteriores a v1.0 no se firman retroactivamente y `backup_check` los lista como "sin firma" sin fallar: aceptado por DECISIONES N-48.
- US-196: si OpenBao no ofrece ML-DSA, la llave `backup.signature` se crea con Ed25519 y se rota a ML-DSA-65 después; las firmas viejas se verifican con su llave (`key_id` en el `.sig.json`): aplica DECISIONES Q27 (dicho para la auditoría, mismo patrón para backups).
- US-196: el SHA-256 del archivo no se calcula con `hashlib` fuera de `core/crypto`; se usa el bus (`digest`, N-06), ampliado con una variante por archivo en streaming dentro de `core/crypto`.
- US-197 trata el CBOM como entregable de v1.0 con formato CycloneDX → el CBOM se adelantó a v0.3 (US-146) y `docs/PLAN.md` v1.0 punto 3 quedó solo con la firma de backups: DECISIONES Q26. La historia queda pendiente de la pregunta de abajo.
- US-198: si OpenBao no implementa ML-KEM, la alternativa con `liboqs-python` deja la llave privada ML-KEM envuelta por Transit (clásico) y debilita la protección post-cuántica efectiva; se acepta documentada con esa debilidad: DECISIONES N-48.
- US-199 pide una migración para agregar `rewrap` a `CryptoJob.kind` → no hace falta: `0003_crypto` ya crea `crypto_jobs.kind` con `rewrap` en el CHECK: corregido por DECISIONES N-05.
- US-199 exige `--confirm` genérico → exige la confirmación literal `REENVOLVER` y un actor con rol admin: `cli rewrap-keys --to ML-KEM-768 --confirm REENVOLVER --as <email de un admin activo>`; sin `--as` el comando se niega (no corre como `SYSTEM_USER_ID`, que está inactivo, porque la acción exige una persona responsable): corregido por DECISIONES N-48 y N-15.

## Validación contra el dominio y la arquitectura

- Dominio: `CryptoKey` (2.13) gana el atributo `wrap_algorithm`; `CryptoJob.kind = rewrap` (N-05); `CryptoOp` registra `sign`, `verify`, `wrap`, `unwrap` con `batch_id`. Invariantes que se mantienen: una sola llave `active` por (`purpose`, `data_class`); el material en claro nunca se persiste; rotar o re-envolver nunca deja una DEK sin envoltura válida.
- Clases de dato: `backup.signature` (sign) ya está en el catálogo (`02_domain_model.md` sección 5); se registra en `core/crypto/registry.py` (N-04) y su llave se crea con `cli init-keys --data-class backup.signature --purpose sign` (idempotente).
- Bus: `sign("backup.signature", manifest_bytes)` y `verify(...)` con formato de firma `apx1.<key_id>.<alg>.<sig_b64url>` (N-04); `digest_file(path) -> str` nuevo en `core/crypto/bus.py` (SHA-256 por bloques; los backups pueden pesar gigabytes y `digest(data)` exige cargarlos en memoria).
- Lint banned-api: `oqs` y `cryptography` solo en `core/crypto`; el adaptador ML-KEM vive en `core/crypto/mlkem_provider.py` (o dentro de `openbao_provider.py`); `test_banned_imports.py` incluye `oqs` y sigue verde. `worker/jobs/backup_check.py`, `worker/jobs/backup_sign.py` y `cli.py` solo llaman al bus y a `core.crypto.service`.
- Contenedor `backup`: no habla con OpenBao ni tiene llaves (supuesto de US-196). Escribe el archivo cifrado con `age` en el volumen `backups`; la firma la pone el worker (misma imagen del api) con un job, y el procedimiento manual usa `cli sign-backup` y `cli verify-backup`. Así ningún contenedor necesita el socket de Docker para ejecutar comandos en otro.
- Roles: `GET /crypto/cbom` solo admin (router de `core/crypto`, US-146); `GET /crypto/jobs` solo admin (US-144). Los comandos de CLI atribuyen con `--as <email>` (N-15).
- Auditoría: exportaciones CBOM como `export`; cada firma, verificación, wrap y unwrap en `crypto_ops`.
- Irreversibilidad (`CLAUDE.md`): activar `CRYPTO_WRAP_ALG=ML-KEM-768` en producción y ejecutar `rewrap-keys` son decisiones irreversibles en la práctica; las historias entregan el código y el comando, y la ejecución en producción exige aprobación explícita del dueño, backup firmado y verificado, y respaldo de las llaves de desellado de OpenBao fuera del servidor.

## Tablas y migraciones

- `0095_crypto_keys_wrap_algorithm_nullable` (US-198): columna `crypto.crypto_keys.wrap_algorithm` text nula con CHECK en (`A256GCM-KW`, `transit-aes256-gcm96`, `ML-KEM-768`, `ML-KEM-768+transit`); paso 1 de 3.
- Paso 2 (no es migración, es comando de `cli.py`): `cli backfill-wrap-algorithm [--as <email>]` llena cada fila según su `provider` (local → `A256GCM-KW`, N-03; openbao → `transit-aes256-gcm96`), idempotente y auditado.
- `0096_crypto_keys_wrap_algorithm_not_null` (US-198): `wrap_algorithm` pasa a `NOT NULL`; paso 3 de 3. El upgrade falla con mensaje claro si queda alguna fila nula.
- `0097_crypto_keys_purpose_kem` (US-198, solo si se usa el adaptador con liboqs): amplía el CHECK de `crypto_keys.purpose` con `kem` y de `algorithm` con `ML-KEM-768`, para guardar el par ML-KEM de envoltura (pública en `public_material`, privada en `wrapped_material` envuelta por Transit). Incluye la columna `public_material` text nula.
- `0098_crypto_jobs_one_running_per_kind` (US-199, solo si US-145 no lo creó): índice único parcial `crypto.crypto_jobs(kind) WHERE status = 'running'`.
- Sin migración para `rewrap` (ya está en `0003_crypto`, N-05). El número 0099 queda libre.

## Services y eventos

- `core/crypto/bus.py`: `digest_file(path) -> str` (nuevo); `sign` y `verify` existentes con `data_class = backup.signature`.
- `core/crypto/backup.py` (nuevo, dentro de `core/crypto` porque firma): función pura `manifest(name, size_bytes, sha256, created_at) -> bytes` canónica; `sign_backup(path, by) -> SigFile` (escribe `<archivo>.sig.json` con `sha256`, `size_bytes`, `created_at` UTC, `key_id`, `algorithm`, `signature`); `verify_backup(path) -> VerifyResult` (recalcula el SHA-256 y verifica con la llave de `key_id`).
- `core/crypto/service.py`: `to_cyclonedx(keys) -> dict` (pura, CycloneDX 1.6 con un `cryptographic-asset` por llave, sin `wrapped_material`); `cbom(format)` extiende `build_cbom` de US-146; `pending_rewrap(keys, target_alg) -> list[key_id]` (pura; excluye `retired`, que por invariante ya no tienen datos); `rewrap_keys(target_alg, by, resume)` (crea o reanuda el `CryptoJob(rewrap)`; por llave y en su propia transacción: `unwrap` actual, `wrap` con ML-KEM, `unwrap` de la nueva envoltura y comparación con la DEK, y solo entonces `UPDATE` de `wrapped_material` y `wrap_algorithm`; si falla, la llave conserva la envoltura anterior y el job registra el error); `backfill_wrap_algorithm(by)`.
- `KeyProvider`: `wrap(dek, alg)` y `unwrap(wrapped, alg)` eligen el algoritmo por `wrap_algorithm` del registro; `OpenBaoProvider` usa ML-KEM de Transit si existe; si no, `MlKemHybridProvider` encapsula con `oqs` una llave efímera que envuelve la DEK, y la llave privada ML-KEM vive envuelta por Transit. Selección por `CRYPTO_WRAP_ALG` solo para llaves nuevas.
- Worker: `worker/jobs/backup_sign.py` (nuevo, 02:30 America/Bogota, después del backup de las 02:00 de N-50) firma los backups de v1.0 que no tienen `.sig.json`; si OpenBao está sellado, deja el estado en `worker.job_runs` y `backup_check` reintenta. `worker/jobs/backup_check.py` (US-115) llama a `verify_backup` y falla con el nombre del archivo si la firma no verifica o falta en un backup de v1.0 en adelante.
- Eventos de dominio: ninguno.

## Endpoints

- `GET /api/v1/crypto/cbom` — roles: admin
- `GET /api/v1/crypto/jobs` — roles: admin

## Componentes de front

- `web/src/features/system/components/CbomExportMenu.tsx` en `Llaves`: menú del botón "Exportar CBOM" con "JSON interno" y "CycloneDX" (sujeto a la pregunta de US-197).
- `Llaves` (US-143, US-144) muestra la columna `wrap_algorithm` y el job `rewrap` en la pestaña Trabajos sin cambios de componente (lee los campos nuevos del API).
- Pruebas Vitest del menú y de la columna nueva.

## Worker, CLI e infraestructura

- CLI nuevos: `cli sign-backup <archivo> [--as <email>]`, `cli verify-backup <archivo>` (código 0 solo si coincide el SHA-256 y la firma verifica), `cli cbom --format json|cyclonedx [--out archivo]`, `cli backfill-wrap-algorithm [--as <email>]`, `cli rewrap-keys --to ML-KEM-768 --confirm REENVOLVER --as <email> [--resume]` (se niega si hay otro `rewrap` en curso o si el último backup no tiene firma válida).
- Compose: el volumen `backups` se monta de solo lectura en `api` (para que `rewrap-keys` y `verify-backup` lean el último backup) y de lectura y escritura en `worker` (el job solo escribe archivos `.sig.json`); el contenedor `backup` no recibe `BAO_TOKEN`.
- `api/Dockerfile`: compilación de `liboqs` desde fuente con versión fijada y suma verificada en una etapa del multi-stage, `OQS_INSTALL_PATH` fijado para que `liboqs-python` no descargue nada en tiempo de ejecución; tamaño de imagen documentado.
- Licencias: `liboqs-python` (MIT) y `liboqs` (MIT) pasan `pip-licenses`; los componentes de terceros que `liboqs` incluye se revisan y se listan en `NOTICE`; la librería de validación de esquema JSON para la prueba de CycloneDX (por ejemplo `jsonschema`, MIT) solo como dependencia de desarrollo; esquema de CycloneDX 1.6 versionado en `api/tests/fixtures/`.
- Documentación: procedimiento de restauración en `docs/runbooks/restore.md` que exige `cli verify-backup` en verde antes de `pg_restore`; `docs/adr/ADR-00x-ml-kem.md` con la decisión de Transit o liboqs y su debilidad (N-48).
- OpenBao de `compose.dev.yml` para las pruebas de integración de firma, wrap y unwrap.

## Dependencias

- EP-13 · US-114 (backup nocturno con `age`), US-115 (`backup_check` y campo `backup` en `/health`), US-116 (respaldo de la KEK).
- EP-15 · US-133 y US-134 (OpenBao con Transit y `OpenBaoProvider`), US-135 (patrón de migración reanudable de proveedor), US-136 (estado degradado con OpenBao sellado).
- EP-17 · US-140 y US-141 (llave de firma por `data_class` y patrón de firma; `init-keys --data-class`).
- EP-18 · US-143 (inventario), US-144 (bitácora y jobs), US-145 (un job en curso por tipo), US-146 (CBOM interno y router admin).
- EP-02 · US-024 (`crypto_jobs` con `rewrap`, N-05), US-027 (firma en el bus), N-06 (`digest`).
- EP-01 · US-113 / N-50 (`worker.job_runs`).

## Riesgos

- Front condicionado a D1: solo afecta el menú de exportación de US-197 (unas 2 h).
- OpenBao sin ML-KEM ni ML-DSA en Transit: la protección post-cuántica efectiva depende de una llave clásica de Transit — mitigación: alternativa documentada (N-48, Q27) y rotación cuando Transit lo implemente; el algoritmo va en el dato, así que el cambio posterior no toca módulos.
- `liboqs` declara que no recomienda su uso en producción y agrega una librería nativa a la imagen — mitigación: versión fijada y compilada en CI, pruebas de ida y vuelta con reinicio de proceso, y decisión explícita en el ADR.
- `liboqs-python` intenta descargar y compilar `liboqs` en tiempo de ejecución si no la encuentra: riesgo de cadena de suministro — mitigación: `OQS_INSTALL_PATH` fijo en la imagen y prueba de arranque sin red.
- Re-envoltura irreversible: un fallo a mitad podría dejar una DEK inutilizable — mitigación: verificación de la nueva envoltura antes del `UPDATE`, una transacción por llave, reanudación, backup firmado previo exigido por el comando y aprobación del dueño.
- Firma de backups dependiente de OpenBao abierto: un backup de la noche con OpenBao sellado queda sin firma hasta la siguiente corrida — mitigación: reintento en `backup_check` y estado en `/health`.
- Backups grandes: calcular el SHA-256 en memoria tumbaría el worker — mitigación: `digest_file` por bloques.
- Ambigüedad Q26 sobre el CBOM en v1.0 (pregunta de US-197).

## Estado y estimación por historia

- US-196 · Firma de backups — **READY** — 24 h — Firma por el bus con `backup.signature` desde un job del worker y verificación en `backup_check` y restauración; anteriores a v1.0 sin firma (N-48), Ed25519 si falta ML-DSA (Q27).
- US-197 · CBOM CycloneDX — **NEEDS_REFINEMENT** — 12 h — Q26 adelantó el CBOM a v0.3 y dejó v1.0 solo con la firma de backups: ¿el formato CycloneDX se mantiene en v1.0 como formato adicional de `GET /crypto/cbom` y `cli cbom`, sin cambiar el JSON de US-146? Propuesta por defecto: sí, se mantiene como extensión en v1.0.
- US-198 · Envoltura de llaves con ML-KEM — **READY** — 40 h — `wrap_algorithm` en tres pasos, ML-KEM por Transit o adaptador liboqs con su debilidad documentada (N-48), todo dentro de `core/crypto`.
- US-199 · Re-envoltura reanudable de DEKs — **READY** — 24 h — `CryptoJob(rewrap)` sin migración (corregido por N-05), confirmación literal `REENVOLVER` y actor admin (corregido por N-48), una transacción por llave.

## Total de la épica

- **Total: 100 h**
