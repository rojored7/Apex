# EP-18 · Administración de llaves de cifrado — desglose técnico de épica

- **Épica:** `docs/ddd/06_epics/EP-18-administracion-de-llaves.md`
- **Versión:** v0.3
- **Historias:** US-143 a US-146 (4 historias, 14 puntos)

## Resumen

La épica pone delante del administrador lo que en v0.1 y v0.2 solo existía por CLI: el inventario de llaves (US-143), la bitácora `crypto_ops` y el progreso de `crypto_jobs` (US-144), la rotación de una llave `encrypt` con confirmación "ROTAR" y motivo (US-145) y la exportación del inventario criptográfico CBOM en JSON propio (US-146).

Todo vive en `core/crypto/`: `router.py` (rutas `/crypto/*`, solo admin) y `service.py` (lectura, rotación en segundo plano y CBOM). La rotación reutiliza el flujo de recifrado por lotes de 500 de `cli rotate-key` (US-030). Ningún endpoint devuelve `wrapped_material` ni otro material de llave.

Hay una brecha en US-145: el recifrado de US-030 recorre columnas de tablas, pero desde v0.3 la clase `attachment.sensitive` cifra archivos en el `StorageProvider` del módulo `attachments`, al que `core/crypto` no puede llegar sin depender de un módulo.

## Correcciones aplicadas por DECISIONES.md

- La épica deja el CBOM "si el gate decide adelantarlo" o con el botón deshabilitado → el CBOM entra en v0.3 dentro de esta épica como JSON propio; CycloneDX queda para EP-26: corregido por DECISIONES Q26.
- US-145 rota cualquier llave `active` → la pantalla solo rota llaves de `purpose = encrypt`; las llaves `index` se rotan solo por CLI con `--index` y las `sign` (por ejemplo `audit.signature`, Q27) por CLI. Pedir la rotación de una llave `index` o `sign` por el API devuelve 409 `purpose_not_rotatable`: corregido por DECISIONES N-07.
- US-146 audita la descarga del CBOM como `export` → se mantiene `export`, porque el CBOM es un listado (inventario), no un archivo de un registro; `download` queda para recibos y adjuntos: precisado por DECISIONES N-08.
- La rotación desde la pantalla atribuye la acción al administrador que la pide; la rotación reanudada por CLI usa `--as <email>` o `SYSTEM_USER_ID`: corregido por DECISIONES N-15.
- `crypto_ops` lleva `count` por lote y `CryptoJob.kind` admite `rewrap`; los filtros de `GET /crypto/jobs` aceptan esos valores: aceptado por DECISIONES N-05.

## Validación contra el dominio y la arquitectura

- **Dominio:** `CryptoKey`, `CryptoOp` (append-only) y `CryptoJob` (`02_domain_model.md` 2.13). Invariantes: una sola `active` por (`purpose`, `data_class`) por índice único parcial (US-024); rotar deja la anterior `decrypt_only` hasta que el job termine y la retire; una sola rotación en curso por `data_class`; el material en claro nunca se persiste ni se exporta. La función pura `next_key_state` de US-030 sigue siendo la única que decide transiciones (`active` → `decrypt_only` → `retired`; prohibido volver a `active`).
- **Ubicación del router:** `core/crypto/router.py` está previsto en `05_service_design.md` sección 2 y en `03_context_map.md` (Crypto "0.3 router admin"). Verificado contra las reglas:
  - Lint `banned-api`: la lista blanca de `pyproject.toml` es `app.core.crypto` y `app.core.security` completos, así que `router.py` y `service.py` quedan dentro y no rompen el lint; aun así no deben importar `cryptography` ni `oqs` (solo `bus.py`, `provider.py` y los proveedores lo hacen). Se agrega una aserción a `tests/architecture/test_banned_imports.py` que exige que `core/crypto/router.py` y `core/crypto/service.py` no importen primitivas directamente.
  - Regla "core no depende de módulos": el router solo importa `core.security.require_role`, `core.crypto.service`, `core.audit` y `core.errors`; ningún `app.modules.*`. Test nuevo `tests/architecture/test_core_independent.py` que falla si un archivo de `core/` importa `app.modules`.
  - Registro en `main.py` con prefijo `/api/v1/crypto`; `test_every_route_has_role.py` cubre las cuatro rutas.
- **Auditoría:** la rotación y el CBOM llaman `core.audit.record(...)` en la misma transacción. Dirección `core/crypto/service.py` → `core/audit.py` → `core/crypto/bus.py`: no es ciclo a nivel de módulo si `core/crypto/__init__.py` queda vacío y `bus.py` no importa `service.py`. Si `crypto_keys` es `__audited__` (US-030), el hook debe excluir `wrapped_material` del `before`/`after`, o la auditoría (`GET /audit/{seq}`) expondría material envuelto (ver riesgos).
- **Paginación:** `limit` 1 a 200, por defecto 25, `{items, total, limit, offset}` en keys, ops y jobs.
- **Rol:** `require_role("admin")` en las cuatro rutas; coach y socio 403; sin token 401.
- **Brecha (US-145):** `crypto.service.reencrypt_batch` de US-030 procesa filas cuyo blob tiene `key_id` distinto de la llave activa, según el registro de `data_class` → (tabla, columna) de `core/crypto/registry.py` (N-04). Para `attachment.sensitive` el blob no está en una columna sino en un objeto del `StorageProvider` (`modules/attachments/storage/`). Recifrarlo desde `core/crypto` obligaría a importar un módulo desde `core`, prohibido. Sin solución, la rotación de `attachment.sensitive` nunca termina y la llave anterior nunca se retira. Propuesta en "Estado y estimación".

## Tablas y migraciones

- `0045_crypto_ops_indexes` (US-144): `CREATE INDEX IF NOT EXISTS` sobre `crypto.crypto_ops (at DESC)` y `crypto.crypto_ops (batch_id)`; solo si `0003_crypto` no los creó (verificar al implementar). Downgrade: borra los índices creados por esta migración.
- `0046_crypto_jobs_one_running` (US-145): índice único parcial `crypto.crypto_jobs (data_class) WHERE status = 'running'`, solo si `0003_crypto` no lo creó. Downgrade: borra el índice.
- Si se aprueba la propuesta de la brecha: ninguna tabla nueva en `crypto`; la columna `key_id` de los adjuntos sensibles va en `0050_attachments` (EP-19).
- Sin cambios en `crypto_keys`.

## Services y eventos

- `core/crypto/service.py`:
  - `list_keys(purpose, state, provider, data_class, limit, offset) -> Page[CryptoKeyOut]` — nunca selecciona `wrapped_material`; incluye `records_count` por `data_class` calculado con el registro (supuesto de US-143); no escribe en `crypto_ops`.
  - `list_ops(from_, to, verb, data_class, key_id, user_id, result, batch_id, limit, offset) -> Page[CryptoOpOut]` ordenado por `at` descendente.
  - `list_jobs(status, kind, data_class, limit, offset) -> Page[CryptoJobOut]`.
  - `job_percent(total: int, done: int) -> int` (pura): `done * 100 // total`, 0 si `total = 0`.
  - `validate_rotation_request(reason: str, confirm: str) -> None | CryptoError` (pura): `confirm == "ROTAR"` exacto y `reason.strip()` no vacío.
  - `start_rotation(key_id, reason, by) -> RotationStarted` — exige `state = active` (409 `key_not_active`), `purpose = encrypt` (409 `purpose_not_rotatable`, N-07) y ningún job `running` para la `data_class` (409 `rotation_running`, además del índice único); en una transacción crea la DEK nueva (versión + 1), pasa la anterior a `decrypt_only` con `rotated_at`/`rotate_by`, crea el `CryptoJob(kind=rotate)`, escribe `crypto_ops(verb=rotate)` y `audit.record` con usuario y motivo; después del commit lanza la tarea asíncrona `run_rotation_job(job_id)` con su propia sesión.
  - `run_rotation_job(job_id)` — reutiliza `reencrypt_batch(data_class, job_id, batch_size=500)` de US-030 (lote por transacción, `batch_id` por lote, `done` actualizado); al llegar `done = total` retira la anterior; ante error deja `failed` con `error` y la anterior en `decrypt_only`.
  - `build_cbom(keys, fixed_algorithms, app_version, generated_at) -> dict` (pura): orden estable por `data_class`, `purpose`, `version`; agrega los algoritmos fijos (JWT `Ed25519`, contraseñas `argon2id`, índice `HMAC-SHA256`); nunca incluye `wrapped_material`.
  - `export_cbom(by) -> tuple[bytes, str]` — arma el JSON, nombre `apex-cbom-AAAA-MM-DD.json` con `today_bogota()`, `audit.record(action="export", after={count})`.
- Eventos: ninguno emitido ni consumido.
- Llamadas a otros services: ninguna (`core/crypto` no llama a módulos).

## Endpoints

- `GET /api/v1/crypto/keys` — roles: admin
- `GET /api/v1/crypto/ops` — roles: admin
- `GET /api/v1/crypto/jobs` — roles: admin
- `POST /api/v1/crypto/keys/{id}/rotate` — roles: admin
- `GET /api/v1/crypto/cbom` — roles: admin

## Componentes de front

- `web/src/features/system/pages/KeysPage.tsx` en `/sistema/llaves` (menú solo admin) con `Tabs`: Inventario, Bitácora, Trabajos; botón "Exportar CBOM" en el `PageHeader`.
- `web/src/features/system/components/KeysInventory.tsx`: `DataTable` con filtros `purpose`, `state`, `provider`; `StatusTag` con texto; fechas en hora de Bogotá; botón "Rotar" solo en filas `active` de `purpose = encrypt`.
- `web/src/features/system/components/CryptoOpsLog.tsx`: tabla filtrable y paginada.
- `web/src/features/system/components/CryptoJobs.tsx`: lista con barra de progreso y texto del porcentaje; `refetchInterval` de 5 s solo mientras haya un job `running`.
- `web/src/features/system/components/RotateKeyModal.tsx`: `ConfirmModal` con clase de dato, `records_count`, motivo y campo "ROTAR"; confirmar deshabilitado hasta escribirlo exacto; al confirmar salta a Trabajos.
- `web/src/features/system/api.ts` y `schemas.ts` (Zod del cuerpo de rotación); pruebas Vitest de tabla, filtros, refresco condicionado con temporizador falso, modal y botón CBOM.

## Worker, CLI e infraestructura

- La rotación corre como tarea asíncrona en el proceso del API (supuesto de US-145); si el API se reinicia, el job queda `running` sin avance y se reanuda con `cli rotate-key <data_class> --reason ... --as <email>`, que continúa el mismo job (US-030, criterio 5). El runbook de llaves lo documenta.
- Sin cambios de Compose ni de Nginx.

## Dependencias

- EP-02: US-024 (tablas e índice de llave activa), US-029 (bitácora por lote), US-030 (rotación por CLI y `reencrypt_batch`), US-031 (pruebas de arquitectura criptográfica).
- EP-15: US-134 (proveedor OpenBao; la DEK nueva se envuelve con Transit), US-136 (503 `crypto_unavailable`).
- EP-03: US-034 (`require_role`), US-036 / test de rutas con rol.
- EP-06: US-061 (`PanelLayout`), US-063 (`DataTable` y paginación), `ConfirmModal`, `Tabs`, `StatusTag`.
- EP-19: US-147 (registro de `attachment.sensitive`; necesario para cerrar la brecha de US-145).
- EP-26: US-197 extiende el CBOM con CycloneDX sin cambiar este endpoint.

## Riesgos

- Material envuelto en la auditoría: si `crypto_keys` está marcada `__audited__` sin exclusión, `before`/`after` de la rotación guardan `wrapped_material` y `GET /audit/{seq}` lo devuelve — mitigación: exclusión de columnas en el hook (`__audit_exclude__ = {"wrapped_material"}`) o auditoría explícita con `audit.record` y `after` saneado; prueba de contrato sobre la auditoría de una rotación.
- Rotación lanzada en horario de atención sobre muchas filas consume CPU — mitigación: el modal muestra `records_count` antes de confirmar.
- Job huérfano tras reinicio del API: deja la clase con un job `running` que bloquea nuevas rotaciones (409) — mitigación: reanudación por CLI documentada; considerar un latido (`updated_at`) para detectar jobs huérfanos en una versión posterior.
- `records_count` por `data_class` hace `count(*)` sobre tablas de otros esquemas mediante el registro de US-030: es el mismo mecanismo genérico del recifrado, no un import de `models`, pero debe quedar cubierto por `test_core_independent.py`.
- Ciclo de import `core/crypto/service.py` ↔ `core/audit.py` si `core/crypto/__init__.py` reexporta el service — mitigación: `__init__.py` vacío y prueba de importación aislada.
- Front condicionado a D1.

## Estado y estimación por historia

- US-143 · Inventario de llaves — **READY** — 12 h — Lectura paginada de `crypto_keys` sin material de llave y con `records_count` por clase de dato; router en `core/crypto/router.py` validado contra el lint y la regla de independencia de `core`.
- US-144 · Bitácora y trabajos criptográficos — **READY** — 13 h — Dos lecturas paginadas, `job_percent` pura e índices de `crypto_ops` en `0045` si faltan.
- US-145 · Rotar llave desde la pantalla — **ARCHITECTURAL_GAP_DETECTED** — 24 h — Brecha: el recifrado de US-030 solo recorre columnas y no puede recifrar los archivos de `attachment.sensitive` sin que `core/crypto` importe el módulo `attachments`. Propuesta: agregar en `core/crypto/registry.py` un puerto `Reencryptor` (`count_pending(old_key_id)`, `reencrypt_batch(old_key_id, batch_size, batch_id)`) que los módulos registran al importarse (igual que `core.events.subscribe`); `reencrypt_batch` de columnas queda como implementación por defecto, `attachments.service` registra la suya para `attachment.sensitive` y guarda `key_id` del blob en `attachments.attachments.key_id` (migración `0050`) para contar pendientes sin leer archivos. Mientras no se apruebe, el API devuelve 409 `rotation_not_supported` para `attachment.sensitive`. Incluye además N-07 (solo `encrypt`).
- US-146 · Exportar CBOM — **READY** — 10 h — JSON propio adelantado a v0.3 por Q26, `build_cbom` pura y auditoría `export`.

## Total de la épica

- **Total: 59 h**
