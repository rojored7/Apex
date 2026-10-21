# EP-15 · Custodia de llaves con OpenBao — desglose técnico de épica

- **Épica:** `docs/ddd/06_epics/EP-15-custodia-de-llaves-openbao.md`
- **Versión:** v0.2
- **Historias:** US-133 a US-136 (4 historias, 21 puntos)

## Resumen

- Saca la KEK del servidor de aplicación. Las piezas son:
  - un servicio `openbao` con motor Transit en Compose, con desellado Shamir de 5 llaves y umbral 3 (US-133);
  - un `OpenBaoProvider` que implementa el puerto `KeyProvider` de `core/crypto` (US-134);
  - el comando idempotente y reanudable `cli migrate-provider`, que vuelve a envolver las DEK sin recifrar ningún dato (US-135);
  - un estado degradado explícito cuando OpenBao está sellado: `/health` responde 503 con `crypto` y las rutas que usan el bus responden 503 `crypto_unavailable` (US-136).
- Todo vive en `core/crypto`, `core/config.py`, `core/health.py`, `core/errors.py`, `main.py`, `cli.py`, `worker/` e `infra/`. Ningún módulo de negocio cambia.

## Correcciones aplicadas por DECISIONES.md

- US-133 supone un Shamir de 5 llaves con umbral 3. Se aplica tal cual: aceptado por DECISIONES N-50.
- Con OpenBao, la DEK se envuelve con lo que devuelve Transit (`vault:v<n>:...`) y no con AES-256-GCM local; `crypto_keys.wrapped_material` guarda ese texto: aceptado por DECISIONES N-03.
- US-135 pone `--as <email>` como parámetro propio. Todo CLI lo acepta y, sin `--as`, el actor es el usuario técnico `SYSTEM_USER_ID` (`00000000-0000-0000-0000-000000000001`), que aparece en `created_by`, en `crypto_ops.user_id` y en la auditoría. US-029 deja `user_id` nulo en CLI y worker; eso también se corrige: corregido por DECISIONES N-15.
- US-136 supone que `/health` responde 503 cuando el bus está sellado, que las rutas del bus responden 503 `crypto_unavailable` y que `/health` existe en la raíz y en `/api/v1/health`. Se aplica: aceptado por DECISIONES N-16.
- El job de US-135 es un `CryptoJob(kind = migrate_provider)`, con `count` en `crypto_ops` para los lotes. El valor `rewrap` de `kind` no se usa aquí: aplicado según DECISIONES N-05.
- Las alertas internas van a Telegram: "OpenBao sellado" está entre las alertas que van al chat del equipo. US-136 no lo tiene en su alcance (solo pide log y estado en `/health`), así que no se agrega. Cuando exista el puerto `core.alerts` que propone EP-14 (US-126), la transición a `sealed` llama a `core.alerts.alert("crypto_sealed", ...)` con 1 h de trabajo adicional: anotado según DECISIONES N-34.
- Q27 no aplica en v0.2. La llave de firma `apex-sign-audit` se crea en Transit como `ed25519`; si llega ML-DSA, la rota EP-17: anotado según DECISIONES Q27.

## Validación contra el dominio y la arquitectura

Dominio:
- `CryptoKey.provider` (`local` o `openbao`), `CryptoJob.kind = migrate_provider` y `CryptoOp` con los verbos `wrap` y `unwrap` coinciden con el dominio 2.13.
- La invariante "el material en claro nunca se persiste" se cumple: Transit devuelve el texto cifrado, y la DEK en claro solo vive en memoria del proceso, como en v0.1.
- Funciones puras:
  - `openbao_provider.key_name(purpose, data_class) -> str`: `apex-kek-<data_class>` para `encrypt` e `index`, y `apex-sign-<uso>` para `sign`;
  - `openbao_provider.map_error(status, body) -> CryptoError`: 403 → `CryptoForbidden`, 503 con `sealed` → `CryptoSealed`, timeout → `CryptoUnreachable`;
  - `crypto.plan_provider_migration(keys) -> list[KeyId]`;
  - `crypto.health_state(provider_status, deks_loaded) -> "ok" | "sealed" | "unreachable"`.

Arquitectura:
- `httpx` vive en `core/crypto/openbao_provider.py`; `core/crypto` es el único lugar con primitivas. El lint `banned-api` no cambia y ningún módulo de `modules/` se toca (criterio 3 de US-134).
- Contradicción de contrato con US-023 (EP-02). El `KeyProvider` de v0.1 es `wrap(dek) -> bytes` y `unwrap(wrapped) -> bytes`, sin referencia de llave y sin `async`. US-133 crea una llave de Transit por `data_class` y US-134 habla de `httpx.AsyncClient`.
- Resolución propuesta, que no es una brecha porque todo queda dentro de `core/crypto`:
  - el puerto pasa a `wrap(key_ref, dek)` y `unwrap(key_ref, wrapped)`; `LocalFileProvider` ignora `key_ref` y usa su única KEK;
  - el puerto sigue siendo síncrono y `OpenBaoProvider` usa `httpx.Client` síncrono con timeout. Las llamadas al proveedor ocurren al arrancar, al rotar, al migrar y al firmar, y el bus las ejecuta con `anyio.to_thread.run_sync` cuando está en contexto async.
  - Si US-023 ya se implementó sin `key_ref`, US-134 hace el ajuste y adapta `LocalFileProvider` y su suite de contrato. Ese costo está incluido en la estimación.
- Proveedor por fila. El bus desenvuelve cada DEK con el proveedor que nombra su `crypto_keys.provider`, y `CRYPTO_PROVIDER` decide solo dónde se crean las llaves nuevas. Así, una migración interrumpida (algunas llaves `local`, otras `openbao`) arranca bien mientras el archivo de la KEK local siga presente, y nada queda inutilizable (criterio 4 de US-135).
- Auditoría:
  - cada `wrap` y `unwrap` se registra en `crypto_ops` (append-only, trigger de 0003) con `key_id`, `key_version`, `batch_id` y el usuario de `--as` o `SYSTEM_USER_ID`;
  - el comando de migración deja una entrada en `audit.audit_log`, escrita por `core.audit.record(action = "update", table_name = "crypto_keys", record_id = job_id, after = {from, to, total, done})`.
- Sin borrado físico de llaves (RN-14): la migración actualiza `wrapped_material` y `provider` en la misma fila.
- Error 503: `CryptoUnavailable` se mapea en `core/errors.py` al envelope `{error: {code: "crypto_unavailable", message: "El custodio de llaves no está disponible. Avise al administrador para desellarlo."}}`.
- Roles: `/health` está en la lista blanca; el resto de rutas conserva su rol. No hay endpoints nuevos del api.

## Tablas y migraciones

- `0030_crypto_jobs_single_running` (US-135):
  - índice único parcial `crypto.crypto_jobs (kind) WHERE status IN ('pending', 'running')`, para que no corran dos `migrate_provider` (ni dos jobs del mismo tipo) a la vez;
  - el downgrade borra el índice;
  - si `0003_crypto` ya lo incluyó, esta migración no se crea.
- Sin otros cambios de esquema:
  - `crypto_keys.provider` ya tiene CHECK con `local` y `openbao` (0003, US-024);
  - `crypto_jobs.kind` ya incluye `migrate_provider`.
  
  Se verifica al empezar el sprint. Si faltara algún valor, se agrega `0031_crypto_provider_openbao` (CHECK ampliado) dentro del rango 0030-0034.
- La migración de llaves no es de Alembic. Es un comando de `cli.py`, idempotente y auditado (regla de datos 8), y nunca toca las columnas cifradas de las tablas de negocio.

## Services y eventos

`core/crypto/openbao_provider.py` (`OpenBaoProvider`):
- `wrap` y `unwrap` usan `POST /v1/transit/encrypt/<n>` y `POST /v1/transit/decrypt/<n>`, con la DEK en base64.
- `sign` y `verify` usan `/v1/transit/sign/<n>` y `/v1/transit/verify/<n>`.
- `rotate` usa `POST /v1/transit/keys/<n>/rotate`.
- `key_info` usa `GET /v1/transit/keys/<n>`.
- Lee el token de `OPENBAO_TOKEN_PATH` en cada arranque y lo renueva con `auth/token/renew-self` antes de que venza (token periódico).
- Timeout `OPENBAO_TIMEOUT_S` (5 s por defecto); TLS verificado si `OPENBAO_ADDR` es HTTPS.
- El token nunca se loguea y se redacta en las excepciones.

`core/crypto/provider.py`:
- Registro de proveedores `providers: dict[str, KeyProvider]`, que se arma al arrancar.
- `CRYPTO_PROVIDER` desconocido → `ConfigError` que nombra el valor, y el api no arranca (criterio 7 de US-134).

`core/crypto/bus.py`:
- Estado `CryptoState` (`ok`, `sealed` o `unreachable`).
- `load_deks()` al arrancar, por fila y con su proveedor.
- `ensure_available()` lanza `CryptoUnavailable` y la llaman `encrypt`, `decrypt`, `blind_index`, `sign`, `verify` y `digest`. Un blob nunca se devuelve como si fuera el valor (RN-13).

`core/crypto/service.py` (`migrate_provider(from_, to, by, dry_run) -> CryptoJob`):
1. Crea el `CryptoJob` con `total`.
2. Por cada llave que quede en `from_`, en su propia transacción: `unwrap` con el proveedor de origen, `wrap` con el de destino, `unwrap` del nuevo envoltorio y comparación en tiempo constante con la DEK. Después actualiza `wrapped_material` y `provider`, escribe `crypto_ops` con el mismo `batch_id` y suma `done`.
3. Al final, `status = done` y `finished_at`.
4. Ante un error: `status = failed` con `error` sin material de llave, y la siguiente ejecución sigue desde la siguiente llave.

`core/health.py`:
- `register_health_check("crypto", fn)` (registro de US-020).
- `/health` responde `{status, db, crypto, backup, version}`; `crypto` distinto de `ok` → 503 (N-16); `backup` sigue siendo informativo (US-115).

`main.py` (lifespan):
- Intenta `load_deks()`; si falla con `CryptoSealed` o `CryptoUnreachable`, arranca en modo degradado.
- Lanza una tarea asyncio que sondea cada `CRYPTO_RECOVERY_POLL_S` (30 s por defecto), vuelve a intentar `load_deks()` y loguea una vez por transición (`sealed` → `ok`).

`worker/main.py`:
- Tiene su propio `load_deks()` y su propio sondeo.
- Los jobs marcados `needs_crypto` (fase `send` de `notify`, y `sign_audit` en EP-17) se omiten y quedan en `worker.job_runs` con `result = skipped` y `details = {"reason": "crypto_sealed"}`.

Eventos de dominio: ninguno emitido ni consumido.

Llamadas service a service: ninguna. Es `core` puro.

## Endpoints

- `GET /health` — roles: público (lista blanca)
- `GET /api/v1/health` — roles: público (lista blanca)
- Las rutas que usan el bus (por ejemplo `GET /api/v1/members/{id}` y `POST /api/v1/members`) conservan sus roles y suman 503 `crypto_unavailable`.

## Componentes de front

- No aplica. El cliente de `web/src/core/api/client.ts` ya muestra el envelope de error genérico. El mensaje de `crypto_unavailable` va en español desde el api y no hace falta componente nuevo.

## Worker, CLI e infraestructura

`infra/openbao/config.hcl`:
- almacenamiento `file` en el volumen `openbao-data`;
- listener `0.0.0.0:8200` solo en la red interna de Compose;
- `ui = false` y `disable_mlock` según el host;
- sin TLS en la red interna en v0.2, porque TLS llega con EP-20.

`infra/compose.yml`:
- servicio `openbao` con la imagen fijada a una versión exacta (sin `latest`);
- sin `ports:` publicados; healthcheck con `bao status`;
- solo lo alcanzan `api` y `worker`, por la red `backend`;
- volúmenes `openbao-data` y `openbao-token`, montado en `api` y `worker` como solo lectura en `/run/secrets/openbao`.

`infra/compose.dev.yml`:
- `openbao` en modo dev, con una llave de desellado conocida, para las pruebas;
- un paso de CI que sella y desella el servidor de dev para los escenarios de US-136.

`infra/openbao/bootstrap.sh`, idempotente:
- inicializa con `-key-shares=5 -key-threshold=3` solo si no está inicializado, y muestra las llaves de desellado y el token raíz una sola vez, por la terminal y nunca en archivo;
- habilita `transit` si no está;
- crea las llaves `apex-kek-member.document`, `apex-kek-member.phone`, `apex-kek-member.email`, `apex-kek-member.birth_date` y `apex-kek-member.emergency_contact` (tipo `aes256-gcm96`, `exportable=false`, `allow_plaintext_backup=false`), más `apex-sign-audit` (tipo `ed25519`), solo si no existen;
- escribe la política `apex-api`:
  - `update` sobre `transit/encrypt/apex-*`, `transit/decrypt/apex-*`, `transit/sign/apex-*`, `transit/verify/apex-*` y `transit/keys/apex-*/rotate`;
  - `read` sobre `transit/keys/apex-*`, que `key_info` necesita y que la lista de permisos de US-133 no nombra;
  - `update` sobre `auth/token/renew-self`;
  - nada de `sys/*`;
- crea un token periódico con esa política y lo escribe con permisos 600 en el volumen `openbao-token`.

Decisión de autenticación:
- US-133 dejaba abierto token o AppRole. Se usa token periódico porque US-134 fija `OPENBAO_TOKEN_PATH`. AppRole queda como mejora sin cambio de contrato.

Documentación y licencias:
- `docs/operacion/openbao.md`: desellado tras un reinicio (3 de 5 llaves, en orden, con el comando exacto), dónde guardar las llaves (al menos dos lugares fuera del servidor), recuperación ante la pérdida de una llave (rekey con 3 de las restantes), verificación con `/health` y qué ve el usuario mientras tanto.
- `NOTICE`: OpenBao, MPL-2.0 sin modificar.

`cli.py`:
- `migrate-provider --from local --to openbao [--as <email>] [--dry-run]`;
- antes de empezar pide la confirmación escrita `MIGRAR` y recuerda tener un backup reciente y la KEK local respaldada (US-116);
- termina con código 0 y "nada que migrar" si no queda ninguna llave en `local`.

`.env.example`: `CRYPTO_PROVIDER=local`, `OPENBAO_ADDR=http://openbao:8200`, `OPENBAO_TOKEN_PATH=/run/secrets/openbao/token`, `OPENBAO_TIMEOUT_S=5` y `CRYPTO_RECOVERY_POLL_S=30`.

Pruebas:
- `api/tests/crypto/test_provider_contract.py`, parametrizada por proveedor: `local` y `openbao` real;
- `api/tests/crypto/test_openbao_provider.py`: mapeo de errores y token ausente en los logs;
- `api/tests/crypto/test_migrate_provider.py`: interrupción simulada, idempotencia y blobs de `members.members` iguales byte a byte;
- `api/tests/core/test_health_crypto.py` y `api/tests/members/test_router_crypto_unavailable.py`;
- `api/tests/worker/test_skip_when_sealed.py`;
- tests de arquitectura que siguen en verde: `test_banned_imports.py` y `test_no_cross_models.py`.

## Dependencias

- De v0.1:
  - US-023: puerto `KeyProvider`, `LocalFileProvider` y suite de contrato (ver la contradicción de `key_ref` y `async`);
  - US-024: esquema `crypto` y CHECKs;
  - US-025: apertura de DEKs al arrancar;
  - US-029: `crypto_ops` por lote;
  - US-016 y US-015: auditoría;
  - US-017: envelope de error;
  - US-020: `create_app` y el registro de comprobaciones de `/health`;
  - US-005: Dockerfile y Compose;
  - US-113: worker y `job_runs`;
  - US-115: el campo `backup` de `/health`;
  - US-116: respaldo de la KEK, que se exige antes de migrar.
- Entre historias de la épica: US-134 → US-133; US-135 → US-134 y US-029; US-136 → US-134 y US-020.
- La consumen otras épicas:
  - EP-17 (firma de auditoría con Transit);
  - EP-18 (inventario por proveedor y job visible en `Llaves`);
  - EP-26 (ML-KEM);
  - EP-14 (fase `send` omitida si está sellado).

## Riesgos

- Un reinicio del servidor deja OpenBao sellado y los datos personales ilegibles hasta que alguien lo deselle: impacto operativo alto con un operador no técnico — mitigación: estado degradado explícito (US-136), un procedimiento paso a paso en `docs/operacion/openbao.md` y, cuando exista `core.alerts` (EP-14), un aviso al chat del equipo.
- Perder 3 de las 5 llaves de desellado equivale a perder todos los datos cifrados — mitigación: guardarlas en dos lugares fuera del servidor, un ensayo de desellado documentado y el backup de la KEK local conservado hasta verificar la migración.
- Migración interrumpida con llaves en dos proveedores — mitigación: una transacción por llave, verificación del nuevo envoltorio antes de escribir, desenvoltura por fila según `provider`, índice de un solo job en curso y reanudación.
- `/health` en 503 mientras OpenBao está sellado: `deploy.sh` o un `depends_on: service_healthy` pueden quedarse esperando — mitigación: Nginx no depende de la salud del api, y `deploy.sh` muestra "api en estado sellado: desellar OpenBao" en vez de fallar en silencio.
- El cambio de firma de `KeyProvider` (`key_ref`), si US-023 ya está implementado: se toca la suite de contrato de v0.1 — mitigación: se hace en US-134 con la suite parametrizada y sin cambiar el formato del blob (`apx1.<key_id>.<alg>...`), que es irreversible.
- Token de OpenBao expuesto — mitigación: archivo de permisos 600 en un volumen de solo lectura, política mínima, redacción en logs y prueba de que no aparece en `crypto_ops` ni en los logs.
- Latencia de OpenBao en la firma o la rotación — mitigación: las DEK se desenvuelven una sola vez al arrancar, así que las operaciones de campo no llaman a OpenBao.

## Estado y estimación por historia

- US-133 · Servicio OpenBao con Transit — **READY** — 20 h — Compose sin puertos publicados, `config.hcl`, `bootstrap.sh` idempotente con Shamir 5/3 (N-50), llaves por `data_class` no exportables, política mínima con `read` de llaves para `key_info`, token periódico en volumen y procedimiento de desellado.
- US-134 · Proveedor OpenBao — **READY** — 30 h — `OpenBaoProvider` síncrono con `httpx` y timeout, proveedor por fila y suite de contrato común. Incluye ajustar el puerto de US-023 a `wrap(key_ref, dek)` y `unwrap(key_ref, wrapped)`, que hace falta para tener una llave de Transit por `data_class`.
- US-135 · Migrar proveedor de llaves — **READY** — 20 h — `cli migrate-provider` reanudable e idempotente: una transacción por llave con verificación del nuevo envoltorio, `crypto_ops` con el mismo `batch_id`, auditoría con `--as` o `SYSTEM_USER_ID` (N-15) y migración `0030_crypto_jobs_single_running`.
- US-136 · Estado degradado con OpenBao sellado — **READY** — 13 h — `health_state` puro, `CryptoUnavailable` → 503 `crypto_unavailable` (N-16), campo `crypto` en `/health`, sondeo de 30 s y jobs del worker que usan el bus omitidos y registrados; la alerta por Telegram (N-34) queda fuera de su alcance.

## Total de la épica

- **Total: 83 h**
