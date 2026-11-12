# Análisis de impacto previo · Sprint 6 (v0.3: auditoría firmada, administración de llaves, adjuntos y autorización de datos, TLS híbrido)

Fecha: 5 de noviembre de 2026 (línea base tomada entre las 23:40 y las 23:59 hora local).
Alcance: `update` sobre un repositorio con código (`flow-update`, Fase 0).
Anclaje: rama `feat/sprint-06-auditoria-firmada-llaves-adjuntos-tls`, HEAD `47ec673` ("docs(adr): ADR-005
punto 2 con la política real de tools, sin rewrap (S5-D271); S5-D272 llaves y contraseñas
provisionales"), que es `3cd752a` ("chore(release): cierre del Sprint 5, v0.2.0", etiqueta local
`v0.2.0`) más dos commits de documentos (`caa4f77`, `47ec673`). `main` sigue en `a1ad4cb` (cierre del
Sprint 4B): **el Sprint 5 no está fusionado ni empujado**; el PR, el merge, `git push origin v0.2.0` y
el Release siguen siendo pasos humanos ("Dueños asignados al cierre del Sprint 5"). `git status` limpio
salvo un archivo sin seguimiento ajeno a esta fase (`docs/ddd/blueprints/sprint-06-exploracion.md`, la
exploración de la Fase 1 de otro agente; no se tocó). Un solo worktree.
Plan de referencia: `docs/ddd/09_sprint_plan/SPRINT-06.md` (14 historias: US-140 a US-142 de EP-17,
US-143 a US-146 de EP-18, US-147 a US-151 de EP-19, US-152 y US-153 de EP-20; 53 puntos y 217 h;
"bloques en orden de ejecución, sin slices: se refina al llegar"; Wave 0 con Caddy, la excepción de
6 MB en Nginx y `uploads` en el backup; Waves 3a y 3b con los bloques A (firma), B (llaves, primera
parte), C (adjuntos) y D (rotación desde pantalla); bloque E (TLS) en Wave 0 y validación; Waves 5a y
5b de front; migraciones "en los rangos reservados" `0040` a `0051`; 9 endpoints nuevos y 4 cambiados).

## Veredicto: AMARILLO

Se puede avanzar a la Fase 1 con `--allow-amber`. Nada es ROJO: todo lo que el sprint consume del
Sprint 5 y anteriores existe y está en verde (`KeyProvider` `async` con `sign`/`verify`,
`OpenBaoProvider.sign`/`verify` contra `transit/sign|verify/<key_ref>`, `bus.sign`/`bus.verify` con
el formato `apx1.<key_id>.<alg>.<sig>`, `SIGNATURE_ALGS = {Ed25519, ML-DSA-65}`, `ALGORITHMS` y el
CHECK de `crypto_keys` con `ML-DSA-65`, `keyring._load_rows` que conserva las filas `sign` en todos
los estados sin `unwrap`, `core/audit_verify.py` con `audit.verifications` append-only y
`run_verification`, `core/alerts.py` con `alert(code, **context)`, el worker con `JobSpec`/`run_job`
y `with_crypto`, `core/crypto/service.py` con `start_rotation`/`reencrypt_batch`/`finish_rotation`/
`next_key_state`/`validate_reason`, los índices `ix_crypto_ops_at`, `ix_crypto_ops_batch_id` y
`uq_crypto_jobs_in_progress`, `AUDIT_ACTIONS` con `download`, `export` y `verify`,
`members.service.count_without_consent`, `DashboardOut.members_without_consent`,
`settings.service.current_privacy_version`, `PrivacySettings.consent_required_from`, el volumen
`uploads` montado en `api` y `tools` y dentro del respaldo cifrado (`infra/backup/run.sh:104`) y de
`restore.sh`, `core/http.csv_download` con `nosniff` y `no-store`, `api.blob` en el front, las rutas
`/sistema/llaves` y `/sistema/auditoria` en `routeTable.ts`, el permiso `crypto.manage`, la pestaña
`adjuntos` reservada en la ficha y `Tabs` en `shared/ui`), `apex-db-1` está en
`0020_notifications_indexes (head)`, el stack de desarrollo (seis contenedores) está sano, las
imágenes `apex-api:local` y `apex-web:local` llevan la revisión `3cd752a` (el código de HEAD: los dos
commits posteriores son solo documentos) y `ruff`, `ruff format --check` (739 archivos), `mypy
--strict` (192 archivos) y `tsc --noEmit` pasan en HEAD. El amarillo viene de nueve cosas que el plan
debe fijar antes de tocar código.

Primera, **el OpenBao fijado (2.7.2, el único digest de `compose.yml` y de la CI) no tiene ML-DSA en
Transit**: en un contenedor desechable `-dev` de esa imagen exacta, `bao write -f transit/keys/x
type=ml-dsa parameter_set=65` responde `400 unknown key type ml-dsa` (también `ml-dsa-65`, `mldsa65`,
`ml-dsa-44` y `slh-dsa`; `ed25519`, `ecdsa-p256` y `rsa-2048` sí existen). Q27 deja de ser un riesgo
MEDIUM y pasa a ser el camino único del sprint: la llave `audit.signature` nace Ed25519 y "rotar a
ML-DSA-65 después" no tiene backend en v0.3. Además `bus.SIGN_ALG_V01 = "Ed25519"` (`bus.py:42,144`)
y `bootstrap._ALGORITHM["sign"] = "Ed25519"` están fijos en código (el algoritmo no sale de la fila),
`liboqs-python`/`oqs` no está en `pyproject.toml` ni en `uv.lock` (el stack de `CLAUDE.md` lo lista;
`ruff banned-api` lo confina a `core/crypto`), y firmar ML-DSA en el proceso del api contradiría el
criterio 6 de US-141 ("la llave privada nunca se lee en el proceso"). Segunda, **ninguna pieza de la
firma existe todavía y las que hay apuntan al proveedor local**: `registry.signing_specs()` está vacío
(no hay clase `audit.signature`), `bootstrap._create_missing` escribe `local:sign-ed25519` en toda fila
`sign` sea cual sea el proveedor (`bootstrap.py:54-56`; `openbao_wire.ruta` rechaza ese `key_ref` por
los dos puntos), `OpenBaoProvider.SIGN_KEY = "apex-sign-audit"` existe pero nadie lo usa, `cli
init-keys --data-class` es un stub que sale con error (`cli.py:130-147`), las políticas
`apex-api.hcl`, `apex-worker.hcl` y `apex-tools.hcl` solo tienen `encrypt|decrypt/apex-kek` y
`renew-self` (S5-D113: "`apex-sign-audit` no tiene política hasta v0.3"), el worker abre solo
`member.phone` y `member.email` (`runtime.WORKER_CRYPTO_CLASSES`, duplicado en `notify.CRYPTO_CLASSES`),
y `core/audit.py` solo puede importar `core/crypto/digest` (`test_core_import_direction.py:60-73`): el
`sign_latest` del desglose no cabe en `core/audit.py`. Tercera, **`core/crypto/router.py` no puede
importar `core/audit`**: la misma prueba recorre todo `core/crypto/` y falla con cualquier
`app.core.audit`; el desglose de EP-18 hace que el router y `service.py` llamen `core.audit.record`.
La auditoría de la rotación y del CBOM necesita otro camino (puerto registrado desde `main.py`, como
`set_membership_gate`, o una excepción anotada a la prueba). Cuarta, **la rotación desde pantalla
(US-145) choca con los permisos de base del api y con dos decisiones del 4B**: `apex_api` tiene solo
`SELECT` en `crypto.crypto_jobs` y `SELECT, INSERT` + `UPDATE (updated_at)` en `crypto.crypto_keys`
(`grants.sql:95-97`, S4B-D61), pero `start_rotation` inserta y actualiza `crypto_jobs` y `_swap_key`
cambia `state`, `rotated_at`, `rotated_by`; hoy solo `tools` (propietario) rota. Y el criterio 7 de
US-145 ("al terminar la anterior pasa a `retired`") contradice S4B-D63 (`finish_rotation` cierra el
job sin tocar la llave) y S4B-D140 (`retired` solo por `retire-key`, irreversible y con
`--confirm-audit-blobs`). Quinta, **la numeración y la lista de migraciones del plan están
desactualizadas**: la cadena real es lineal `0001 → 0020` y la siguiente es `0021` (el Sprint 5 ya
abandonó los rangos reservados: `0015` en vez de `0030`, S5-D4, RUNBOOK §6); `0042_crypto_keys_mldsa_check`,
`0045_crypto_ops_indexes` y `0046_crypto_jobs_one_running` **no hacen falta** (`models.py:51,124-128,156`
y `0003`); quedan tres reales (firmas, columnas de `verifications`, adjuntos) y una opcional (índice de
consentimiento). Sexta, **el puerto `Reencryptor` que `CLAUDE.md` atribuye a `registry.py` no existe**
(cero resultados de `Reencryptor` y `rotation_not_supported` en `src/`); `cli rotate-key` ya sale 2
para `attachment.sensitive` (`rotate_key.py:53`, G-09), pero `start_rotation` sobre una clase sin
columnas daría `total = 0` y `finish_rotation` cerraría el job sin recifrar un solo archivo (pérdida
silenciosa de cobertura, no de datos). Séptima, **adjuntos arrastra dependencias y contratos sin
decidir**: `UploadFile` de FastAPI exige `python-multipart` (no está en `uv.lock`; Apache-2.0),
`boto3` tampoco (Apache-2.0, pesado) y `S3CompatibleStorage` no tiene historia que lo use en v0.3;
`POST /members` recibe hoy `data_consent: bool` y el servidor fija `data_consent_at = now`
(`schemas.py:93`, `service.py:233`), `data_consent_version` siempre es `None` (`service.py:234,259`) y
`members` no tiene arista hacia `settings` en `ALLOWED_EDGES`; el evento `SensitiveFieldRevealed` que
US-150 "sigue emitiendo" nunca existió; `test_reveal_single_door` prohíbe `bus.decrypt` fuera de las
dos puertas de `members`; `MemberListQuery` no tiene `consent`. Octava, **TLS no existe en ninguna
capa y el modo dual choca con la configuración actual**: no hay `infra/caddy/`, servicio `caddy`,
perfil `tls` ni `compose.tls.yml`; `caddy:2-alpine` del host es la 2.11.3 (sirve: `x25519mlkem768`
en `curves` desde la 2.10) pero sin digest; `proxy-api.conf` sobrescribe `X-Forwarded-For` con
`$remote_addr` y `X-Forwarded-Proto` con `$scheme` (detrás de Caddy el api vería a todos con la IP de
Caddy: el riesgo 4 del plan es real hoy); `COOKIE_SECURE`/`ALLOW_INSECURE_COOKIE` ya existen con su
validador de producción (`config.py:215-216,416-424`) y el `cookie_secure(settings)` derivado del
desglose los duplica; `LAN_ORIGIN` duplica `FRONT_BASE_URL` (N-11); `openssl s_client -groups
X25519MLKEM768` exige OpenSSL ≥ 3.5 (Ubuntu 24.04 de CI trae 3.0); `deploy.sh` y `prod-smoke.sh`
sondean `http://127.0.0.1:${WEB_PORT}`, que con el perfil `tls` deja de existir; y el residual
"TLS en `custody`" (S5-D63, dueño EP-20) no lo cubre US-152 ni US-153. Novena, **listas cerradas y
pruebas por igualdad exacta que el sprint cambia**: `test_adr_docs` ("exactamente los cinco archivos":
un ADR nuevo para `signature_payload` lo rompe, y cambiar uno existente exige preguntar, S4B-D47),
`PRIVATE_HELPERS["members"]` y su igualdad (`test_no_cross_models.py:171-173`), `ALLOWED_EDGES`,
`IMPORTADORES_REALES` del bus, las puertas de `test_reveal_single_door`, el conjunto de archivos del
worker (`<=`), `len(PUBLIC_ROUTES) == 8` (ninguna ruta nueva es pública: bien), `ENABLED_FEATURES.size
== 10` (`crypto` pasa a 11), `ALERT_CONTEXT_KEYS`, `DETAIL_KEYS`, `MODULES`, la matriz `PRIVILEGIOS`
y el `ARRAY clasificadas` fail-closed, `APP_SCHEMAS` y las cuatro sentencias de esquemas de
`grants.sql`, `test_sql_literals_constant` (candados `4_270_001..003`), `test_env_example` (toda
variable nueva de `Settings` en `.env.example`; el conteo "16 cubetas" citado por comentario).
Todo se absorbe con las condiciones de la sección 9; ninguna exige cambiar el alcance de las catorce
historias, pero C1 (T-DOC) y C2 (firma y políticas) deben cerrarse antes de la Wave 0, y Q27 debe
reescribirse con el dato empírico de OpenBao 2.7.2.

## Cómo se verificó

- Lectura completa de `SPRINT-06.md`, el `README.md` del plan (fila del Sprint 6, dependencias "el 6
  necesita el 5"), los cuatro `BREAKDOWN.md` de EP-17 a EP-20, las catorce historias completas (US-140
  a US-153), `docs/ddd/impacto/sprint-05.md` y `sprint-04b.md` (referencia de formato), los bloques
  "Estado al cierre del Sprint 5", "Dueños asignados al cierre del Sprint 5" y "Tras el cierre" de
  `DECISIONES.md` (S5-D271, S5-D272) y las decisiones S5 que nombran v0.3, EP-17 a EP-20, Q27, Q16,
  G-09 o Caddy (S5-D4, D6, D9, D10, D19, D52, D63, D65, D113, D131, D183, D201, D207, D226, Q8;
  S4B-D45, D61, D63, D66, D140, D154), `docs/BRECHAS.md` §2 ("API de llaves", resuelto hacia
  `core/crypto/router.py` en v0.3) y §13 (filas 13.6, 13.10, 13.11, 13.17, 13.26), `docs/design/
  ROUTES.md` (Inicio, `/socios/nuevo`, `/socios/:id`, `/sistema/auditoria`, `/sistema/llaves`) y los
  textos de `Llaves.html` ("Rotar", "Exportar CBOM", "Bitácora", "Trabajos", "Proveedor activo:
  OpenBao Transit · conectado · sellado: no"), `Auditoria.html` ("última firma nocturna: hoy 02:00
  (ML-DSA)"), `Socio_Form.html` ("Autorización de datos (Ley 1581)"; `grep Foto` sin resultados),
  `Inicio.html` y `Socio_Ficha.html` (sin "consent"), `CLAUDE.md` (árbol, reglas de módulos, bus,
  licencias, seguridad, "Caddy opcional"), `docs/RUNBOOK.md` (índice, §6, §9, §12, §13), `docs/adr/`
  (cinco archivos) y `docs/operacion/` (ocho guías; sin TLS ni llaves por pantalla).
- Lectura del código que el sprint toca o consume (secciones 1 y 2): `main.py`, `cli.py`, `cli_base.py`,
  `cli_ops/{keys,rotate_key,verify_audit}.py`, `core/{audit,audit_verify,alerts,config,errors,
  health,http,jobs,ratelimit,security,db}.py`, `core/crypto/{__init__,registry,provider,bus,
  signature,keyring,bootstrap,service,rotation,discovery,models,openbao_provider,openbao_wire,
  local_provider,recovery}.py`, `worker/{registry,runner,runtime}.py`, `worker/jobs/{__init__,
  notify}.py`, `modules/audit/{service,router,schemas,verify,queries}.py`, `modules/members/{models,
  schemas,service,router,rules,changes,detail}.py`, `modules/settings/{schemas,service}.py`,
  `modules/dashboard/{service,schemas}.py`, `modules/auth/cookies.py`, `migrations/env.py`, `0002`,
  `0003`, `0013`, `0015`, `infra/compose.yml`, `compose.dev.yml`, `compose.openbao.yml`,
  `compose.e2e.yml`, `infra/nginx/default.conf` y `snippets/*`, `infra/openbao/bootstrap.sh` y
  `policies/*.hcl`, `infra/backup/run.sh` y `restore.sh`, `infra/db/{grants,roles}.sql`,
  `infra/deploy.sh`, `api/Dockerfile`, `api/pyproject.toml`, `uv.lock` (grep), `.env.example`,
  `scripts/ci/{test_compose_config,test_nginx_conf,test_images_pinned,prod-smoke,compose-smoke,
  check-licenses-api}.sh`, `licenses-exceptions.txt`, `.github/workflows/ci.yml`, las 59 pruebas de
  `api/tests/architecture` (en especial `test_core_import_direction`, `test_audited_tables`,
  `test_no_plaintext_at_rest`, `test_crypto_bus_importers`, `test_reveal_single_door`,
  `test_banned_imports`, `test_third_party_confinement`, `test_service_import_graph`,
  `test_no_cross_models`, `_imports.PRIVATE_HELPERS`, `test_worker_boundaries`,
  `test_every_route_has_role`, `test_writes_have_user_limit`, `test_user_limits_catalog`,
  `test_health_check_registrars`, `test_kek_path_single_door`, `test_sql_literals_constant`,
  `test_adr_docs`, `test_error_codes_per_route`, `test_file_and_function_size`, `test_read_modules`,
  `test_audit_module`, `test_app_layer_importers`), `tests/migrations/test_db_grants.py`,
  `tests/conftest.py` (limpieza), `tests/core/{test_migrations,test_env_example}.py`,
  `tests/worker/test_*.py` (uso de `JOBS`), `docs/openapi.json` (63 rutas, 83 operaciones),
  `web/src/config/{features,features.test,routeTable,routes.reference}.ts`,
  `web/src/core/auth/permissions.ts`, `web/src/layouts/nav.ts`, `web/src/core/api/client.ts`,
  `web/src/features/{members,dashboard,system}/` y `web/src/shared/{ui,lib}/`.
- Estado del stack con `docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml
  ps`, `exec api alembic current`, `docker image ls`, `docker image inspect` (etiqueta
  `org.opencontainers.image.revision`), `docker run --rm caddy:2-alpine caddy version`. **Sondeo
  empírico de Transit:** un contenedor desechable `apex-impacto-ob` con la imagen exacta
  `openbao/openbao:2.7.2@sha256:5046…561f` en modo `-dev` (sin red del stack, sin volúmenes; borrado al
  terminar): `bao secrets enable transit` y `bao write -f transit/keys/<n> type=<tipo>` con `ml-dsa`
  (`parameter_set=65`), `ml-dsa-65`, `mldsa65`, `ml-dsa-44`, `slh-dsa`, `ed25519`, `ecdsa-p256` y
  `rsa-2048`. **No se reconstruyó ninguna imagen ni se tocó el stack.**
- Gates baratos corridos en HEAD (sección 6): `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy src` en `api/`, `npx tsc --noEmit` en `web/`, y `pytest --co -q -p no:cacheprovider`
  (solo recolección, con y sin `-m "not perf"`, y sobre `tests/architecture`). No se corrió la suite
  (instrucción de la Fase 0): los totales vienen del cuaderno `docs/scratch/sprint-05.md`, sección
  "V9 · Gates completos". No se modificó ningún archivo fuera de este.

## 1. Inventario de contratos que el sprint consume

Cada uno marcado como: **existe** (con la firma esperada), **existe con otra firma o nombre**, o
**no existe** (lo crea el sprint o falta decidirlo).

### Firma de la cadena (`core/audit*`, `core/crypto/`, EP-17)

- `KeyProvider.sign(key_ref, data) -> bytes` y `verify(key_ref, data, signature) -> bool`
  (`provider.py:30-42`): **existen**, `async`. `OpenBaoProvider.sign` hace `POST
  /v1/transit/sign/<key_ref>` con `{"input": b64}` y devuelve el texto `vault:v<n>:<b64>` en ASCII;
  `verify` hace `POST /v1/transit/verify/<key_ref>` y responde `valid` (`openbao_provider.py:184-198`,
  S5-D9). `LocalFileProvider.sign`/`verify` firman con la semilla Ed25519 de
  `CRYPTO_LOCAL_SIGNING_KEY_PATH` y solo aceptan `SIGNING_KEY_REF = "local:sign-ed25519"`
  (`local_provider.py:35,102-116`). `openbao_wire.ruta` valida el `key_ref` con la expresión `_KEY_REF`
  antes de armar la ruta (`openbao_wire.py:59-62`): `local:sign-ed25519` no pasa.
- `bus.sign(data_class, data) -> str` y `bus.verify(data_class, data, signature) -> bool`
  (`bus.py:137-160`): **existen con un algoritmo fijo**: `format_signature(llave.key_id, SIGN_ALG_V01,
  firma)` con `SIGN_ALG_V01 = "Ed25519"` (`bus.py:42`); `verify` busca la llave por el `key_id` del
  blob, exige `purpose == "sign"` y la misma `data_class`, y resuelve el proveedor por la fila
  (`_provider(llave)`), con `crypto_ops` `sign`/`verify` (`result` `ok|error`). Q27 ("cada firma se
  verifica con la llave y el algoritmo con que se hizo") ya se cumple para la llave; el `alg` debe
  salir de `llave.algorithm` cuando exista más de uno.
- `signature.py`: `SIGNATURE_PREFIX = "apx1"`, `SIGNATURE_ALGS = {Ed25519, ML-DSA-65}`,
  `format_signature`, `parse_signature` (N-04, ADR-002): **existen**; la firma de OpenBao (texto
  `vault:v1:...`) entra como bytes y sale base64url dentro del blob (doble envoltura, reversible).
- `registry.DataClassSpec(name, encrypt, index_kind, sign, value_type, columns)` y `signing_specs()`
  (`registry.py:21-69`): **existen, pero no hay ninguna clase con `sign=True`**; `audit.signature`
  **no existe**. `kek.backup` (sin llave, `columns=()`) es el precedente de una clase sin columnas.
- `bootstrap._create_missing` (`bootstrap.py:41-85`): para `purpose == "sign"` escribe
  `wrapped_material = SIGNING_KEY_REF` y `provider = provider.name` **sin mirar el proveedor**: con
  `CRYPTO_PROVIDER=openbao` dejaría una fila `openbao` con referencia `local:…` que `ruta()` rechaza.
  `OpenBaoProvider.SIGN_KEY = "apex-sign-audit"` (`openbao_provider.py:43`, exportado en `__all__`)
  **existe sin usos**. `ensure_keys` (api, `create_missing=True`) crearía la fila `sign` al arrancar
  en cuanto el registro tenga la clase; el worker nunca inserta (`recovery.try_load`, `create_missing
  =False` con `classes`). `init-keys --data-class` (`cli.py:130-147`): **stub** que imprime "no
  implementado todavía (US-140)" y sale con error; `cli_ops/keys.py` solo escribe archivos.
- `keyring._load_rows` (`keyring.py:90-112`): una fila `sign` se carga **en todos los estados** con
  `material = wrapped_material` sin `unwrap` (Q27); `classes` filtra por `data_class`: el worker
  necesita `audit.signature` en `WORKER_CRYPTO_CLASSES` (`runtime.py:69`; `notify.CRYPTO_CLASSES`
  repite la lista, `notify.py:29`).
- Transit en OpenBao 2.7.2 (sondeo de esta fase): `type=ed25519|ecdsa-p256|rsa-2048` **existen**;
  `ml-dsa`, `ml-dsa-65`, `mldsa65`, `ml-dsa-44`, `slh-dsa` → `400 unknown key type`. **No hay forma de
  "consultar capacidades"** (el desglose de EP-17 lo supone): la detección es intentar crear y mapear el
  400. `infra/openbao/bootstrap.sh:171-173` ya crea `apex-sign-audit` `ed25519` no exportable y
  `ci.yml:117` igual con el token raíz `apex-ci`. Políticas: `apex-api.hcl` (`encrypt|decrypt/apex-kek`,
  `renew-self`), `apex-worker.hcl` (`decrypt/apex-kek`, `renew-self`), `apex-tools.hcl` (`encrypt`,
  `decrypt`, `keys/apex-kek` read, `rotate`, `config`, `renew-self`): **ninguna tiene
  `transit/sign/apex-sign-audit`, `transit/verify/apex-sign-audit` ni `transit/keys/apex-sign-audit`**
  (S5-D52 fija las políticas como exactas; `test_openbao_infra.sh` las parsea y rechaza `sys/`,
  `delete`, `sudo` y comodines fuera de `apex-*`: rutas `apex-sign-audit` pasan). Sin esto la demo 1 da
  `forbidden` en `_llamar`.
- `core/audit.py` (531 líneas): `AuditEntry`, `AUDIT_ACTIONS` (`insert, update, delete, reveal,
  export, download, login, verify`), `VerifyResult(ok, rows_checked, broken_at_seq, last_seq,
  last_hash)`, `canonical`, `chain_hash`, `verify_chain`, `append_entry`, `record(session, *, action,
  table_name, record_id, before, after, user_id=None, subject_member_id=None)`, `AUDIT_CHAIN_LOCK_KEY
  = 4_270_002`: **existen**. Regla de importación: `core/audit.py` solo puede importar
  `app.core.crypto.digest` de `core/crypto` y **nada de `core/crypto/` puede importar `app.core.audit`**
  (`test_core_import_direction.py:60-73`); `core/jobs.py` y `core/alerts.py` no importan `core/audit`
  (`:115`). Consecuencia: `signature_payload` y `needs_signature` (puras) caben en `core/audit.py`, pero
  `sign_latest` (que llama `bus.sign`) **no**: va en un archivo hermano (`core/audit_sign.py`, como
  `audit_verify.py`, que importa `core/audit` y puede importar `core/crypto/bus`). La verificación de
  firmas (`bus.verify`) cabe en `core/audit_verify.py` (309 líneas) o en un hermano.
- `core/audit_verify.py`: `AuditVerification(started_at, finished_at, through_seq, through_hash,
  rows_checked, ok, broken_at_seq, triggered_by, source)` (`:68-82`), `VerificationView`, `view_of`,
  `run_verification(session, *, by, source)`, `_persist`, `AUDIT_VERIFY_LOCK_KEY = 4_270_003`
  (candado de sesión): **existen**. Las columnas nulas de US-142 (`signatures_checked`,
  `signatures_valid`, `first_invalid_signature_seq`, `last_valid_signature_seq`,
  `last_valid_signature_at`, `last_valid_signature_algorithm`) **no existen**: migración; los triggers
  `verifications_forbid_mutation|truncate` de `0013` (`ENABLE ALWAYS` desde `0014`) se conservan.
  `VerifyResultOut` (`audit/schemas.py:40-48`) y `VerifyStartedOut` ganan los campos (nulos para las
  verificaciones viejas); `cli_ops/verify_audit.py` y `format_verify_message` cambian.
- Candado de la firma: `pg_advisory_xact_lock` con llave propia **no existe**; `4_270_004` es la
  siguiente libre (`MIGRATION_LOCK_KEY` `…001`, cadena `…002`, verificación `…003`;
  `test_sql_literals_constant.py:102-104` fija las tres por igualdad y gana la cuarta).
- `modules/audit/service.py` (182 líneas, fachada con `__all__`), `router.py` (`AdminDep`,
  `no_store` a nivel de router, cubetas `audit-verify`/`audit-verify-hour`/`staff-read`), privados
  `verify.py` (`verify(session, *, by) -> Finished | Started`, `last_verification`), `queries.py`
  (`AUDITABLE_TABLES`: solo afecta a `GET /audit?table=`), `diff.py`: **existen**.
  `GET /audit/signatures/latest` **no existe**; va en `audit/router.py` antes de `/audit/{seq}` (el
  router ya registra `/audit/verify/last` antes). `audit.signatures` **no debe ser `__audited__`**
  (auditar la auditoría; `test_audited_tables.EXCLUIDAS` gana la entrada con motivo).
- Worker: `JobSpec(name, run, hour, minute, timeout_s=900)` (`registry.py:21-28`), `JOBS =
  (expirations, notify, backup_check)` (`jobs/__init__.py`), `JobContext`, `JobResult(ok, details,
  status)`, `run_job`, `run_cycle`, `alert("job_failed", job=, result=, error_type=)` ante fallo
  (`runner.py:224`), `worker_runtime(with_crypto=True)` que carga `phone` y `email` y sondea si arranca
  sellado (`runtime.py:98-137`): **existen**. `needs_crypto` **no existe** (el worker ya corre siempre
  con el keyring: no hace falta). `DETAIL_KEYS` (`core/jobs.py:58-72`, solo enteros) gana las claves de
  `sign_audit` (`firmadas`, `sin_cambios`, `intentos`, por ejemplo); `RESULTS` sin `skipped` (criterio
  3 de US-141 termina en `error`: no hace falta `skipped`). `tests/worker/*` usan `JOBS[0]`
  (`expirations`) y `next(s for s in JOBS if s.name == ...)`: sumar `sign_audit` **al final o después
  de `notify`** no rompe índices; `test_worker_boundaries.py:111-116` fija los archivos con `<=`: sumar
  `jobs/sign_audit.py`. Reintentos 2, 4 y 8 s: `asyncio.sleep` (sin `now()` directo:
  `test_no_direct_now`). La "firma atrasada" con `is_signature_late(last_signed_at, now, 48)` usa
  `current_clock()`.
- `core/alerts.py`: `ALERT_CONTEXT_KEYS = {job, result, error_type, attempts, run_date, sqlstate,
  generados, enviados, fallidos, omitidos, pendientes}`, `COUNT_KEYS` enteros, `alert(code, **context)`
  con `code` libre (`:23-108`): **existe**. `alert("audit_sign_failed", job="sign_audit",
  result="error", error_type=…, attempts=3)` y `alert("audit_signature_late", job="sign_audit",
  result="late")` caben sin tocar la lista; `through_seq` o `age_h` exigirían claves nuevas.
  `TelegramAlertSink` compone el texto por `code` (S5-B4): dos códigos nuevos en su tabla de textos.
- `cli sign-audit [--as]` y `cli verify-audit` con firmas: **no existen** (`cli_ops/sign_audit.py`
  nuevo, un archivo por familia, S4B-D76; `cli.py` mide 350 líneas, tope 700; `--db-timeouts off` ya
  documenta `sign-audit`, RUNBOOK §9). `tools` necesita la política de firma en OpenBao.
- ADR: el desglose pide "`docs/adr/ADR-00x-auditoria.md`" para `signature_payload`; `test_adr_docs.py`
  exige **exactamente cinco archivos** con nombre fijo, y S4B-D47 exige detenerse y preguntar para
  cambiar un ADR. Un ADR-006 nuevo cambia la prueba (anotado) y ampliar ADR-004 exige la pregunta: paso
  humano en T-DOC.

### Llaves por pantalla (`core/crypto/`, EP-18)

- `core/crypto/__init__.py`: **docstring de 6 líneas, sin imports** (equivale a "vacío" para el ciclo
  que teme el desglose; US-143 dice "vacío": dejarlo sin imports basta, anotado).
- `core/crypto/router.py` **no existe**. `main.include_module_routers` solo carga
  `app.modules.<m>.router` (`main.py:106-110`); `health.router` se incluye aparte (`:386-388`): el
  router de `crypto` se registra explícitamente bajo el `APIRouter` de `/api/v1` desde `main.py`.
  `test_every_route_has_role`, `test_no_store_routes`, `test_routes_under_api_v1`,
  `test_writes_have_user_limit`, `test_list_routes_use_page_params` (toda `Page[...]` con
  `PageParams` **y `q`**, o exclusión con motivo) y `test_error_codes_per_route` (`responses_for` solo
  admite códigos de `_DESCRIPCIONES`) lo cubren sin cambios. **Bloqueo real:** el router no puede
  importar `app.core.audit` (`test_core_import_direction.py:60-66` recorre todo `core/crypto/`), y
  `core/crypto/service.py` y `discovery.py` tampoco (`:210-218`, "la auditoría de `rotate-key` la
  escribe el CLI"). Opciones: (a) puerto `set_audit_writer(fn)` en `core/crypto/` que `main.py` cablea a
  `core.audit.record` (patrón de `payments.set_membership_gate`, G-03); (b) excepción anotada a la
  prueba solo para `router.py`. Recomendación: (a).
- `core/crypto/service.py` (556 líneas; tope 800): `start_rotation(session, data_class, reason,
  actor) -> CryptoJob` (reanuda el job abierto o rota; `validate_reason`; `get_spec(data_class).encrypt`;
  `_no_custody_job`; candado `apex:rotate:<clase>` de **sesión** en conexión dedicada,
  `:217-237`), `reencrypt_batch(session, job, batch_size=500)` (exige que `current_keyring()` tenga la
  llave activa vigente: `crypto_key_changed` si no), `finish_rotation` (cierra `done` sin tocar la llave,
  S4B-D63), `fail_job`, `rotate_index`, `retire_key(session, key_id, *, confirmed_audit_blobs, actor)`
  (irreversible, S4B-D140), `count_rows_by_key`, `next_key_state` (única función de transición),
  `validate_reason`: **existen**. `start_rotation` recibe `data_class`, no `key_id`: el endpoint
  `POST /crypto/keys/{id}/rotate` traduce `id → (purpose, data_class)` y responde 409
  `purpose_not_rotatable` si `purpose != encrypt` (N-07), 409 `key_not_active`, 409 `rotation_running`
  (el índice `uq_crypto_jobs_in_progress` lo garantiza además), 409 `rotation_not_supported` para
  `attachment.sensitive` hasta el bloque D (hoy `rotate_key.py:53` sale 2 por G-09). `list_keys`,
  `list_ops`, `list_jobs`, `job_percent`, `validate_rotation_request`, `build_cbom`, `export_cbom`
  **no existen**: sumarlos a `service.py` lo acerca a 800; mejor `core/crypto/admin.py` (lecturas, CBOM,
  puras) y `router.py`, dejando `service.py` con la rotación.
- `records_count` por `data_class`: `discovery.encrypted_columns(Base.metadata, data_class)` y
  `_count_where`/`_pending_total` (`service.py:198-215`) ya cuentan por el registro sin importar
  `models` (US-030, S4B-D39): **existen**. Para `attachment.sensitive` (sin columnas) el conteo sale
  de `attachments.key_id` por el puerto del bloque D.
- Permisos de base para rotar desde el api: `apex_api` tiene `SELECT` en `crypto.crypto_jobs`,
  `SELECT, INSERT` y `UPDATE (updated_at)` en `crypto.crypto_keys` (`grants.sql:95-97`; S4B-D61
  "residuales aceptados"; `test_db_grants.PRIVILEGIOS`): **insuficiente**. `start_rotation` → `INSERT
  crypto_jobs`, `UPDATE crypto_jobs (status, done, error, finished_at)`, `_swap_key` → `UPDATE
  crypto_keys (state, rotated_at, rotated_by)` (el trigger `guard_keys_update` de `0003`/`0015` sigue
  vigilando la transición), `UPDATE members.members` (el api ya lo tiene), `INSERT crypto_ops` (ya).
  Dos salidas: (a) ampliar los grants del api por columna (`UPDATE (state, rotated_at, rotated_by,
  updated_at)` en `crypto_keys`; `INSERT` y `UPDATE (status, done, error, finished_at, updated_at)` en
  `crypto_jobs`), reabriendo S4B-D61 con decisión; (b) el api solo encola (`CryptoJob(status=pending)`)
  y otro proceso (worker o `tools`) ejecuta: el worker tiene menos privilegios aún (`SELECT` en ambas) y
  no monta `uploads` (`test_compose_config.sh:99`). Recomendación: (a) con `security-reviewer`, porque
  US-145 fija "tarea asíncrona en el proceso del api" y el recifrado de archivos (bloque D) exige
  `uploads`. El candado de sesión sostiene una conexión del pool durante todo el recifrado y un
  reinicio deja el job `running` (`start_rotation` ya lo reanuda; RUNBOOK lo documenta).
- Criterio 7 de US-145 ("al terminar, la anterior pasa a `retired`"): **contradice S4B-D63 y D140**;
  en el código la llave queda `decrypt_only` y `retired` solo llega con `retire-key --confirm-audit-blobs`
  (los blobs de `audit_log` y, desde v0.3, los adjuntos, siguen cifrados con la llave vieja). T-DOC.
- `crypto_keys`, `crypto_ops`, `crypto_jobs` **no son `__audited__`** (`models.py:12`;
  `test_audited_tables.EXCLUIDAS` con motivo y `test_las_excluidas_no_declaran_audited`): el punto
  "`test_audited_tables.py`: `crypto_keys.wrapped_material` excluido del diff" de `SPRINT-06.md` no
  aplica; la auditoría de la rotación y del CBOM es explícita con `audit.record(action="update"|
  "export", table_name="crypto.crypto_keys", record_id=job_id|None, after=saneado)` sin
  `wrapped_material` (el riesgo "material envuelto en la auditoría" del desglose queda cubierto por
  construcción; prueba de contrato igual).
- Índices y CHECK: `ix_crypto_ops_at (at DESC)`, `ix_crypto_ops_data_class_at`, `ix_crypto_ops_key_id`,
  `ix_crypto_ops_batch_id` (parcial) (`models.py:124-128`, `0003`) → **`0045` no hace falta**;
  `uq_crypto_jobs_in_progress` sobre `coalesce(data_class, '*') WHERE status IN (pending, running)`
  (`models.py:156`, `0003`) → **`0046` no hace falta**; `ALGORITHMS` con `ML-DSA-65` (`models.py:51`,
  CHECK de `0003`) → **`0042` no hace falta**. `JOB_KINDS` ya trae `rewrap` (N-05 cumplido).
- CBOM: `build_cbom(keys, fixed_algorithms, app_version, generated_at)` pura; `APP_VERSION` de
  `Settings`; `today_bogota()` para el nombre; descarga con `Content-Disposition` y `no-store` por
  `core/http` (generalizar `csv_download` a `file_download(body, filename, media_type)` o un hermano).
  Auditoría `export` (N-08) con `record_id=None` (admitido, `audit.py:133`). Cubeta: `GET` sin
  obligación; por seguridad `staff-read` o `export` (2/min). Front: `api.blob` ya existe (S5-F4).
- Pantalla `Llaves.html` muestra "Proveedor activo: OpenBao Transit · conectado · sellado: no": el
  front no consulta `/health.crypto` (BRECHAS 13.26) y `GET /crypto/keys` no lo trae: o la respuesta de
  llaves incluye `provider_status` (de `core/crypto/state.py`) o `// DESIGN-GAP:`. Decidir en T-DOC.
- Front: `routeTable.ts:163` tiene `/sistema/llaves` ("Llaves de cifrado", feature `crypto`, acceso
  `crypto.manage`, layout `panel`) **sin `load`** (hoy no se renderiza); `permissions.ts:36`
  `crypto.manage: ADMIN`; `nav.ts:84` "Llaves de cifrado"; `features.ts:16` `crypto` en `FEATURES`
  y **no** en `ENABLED_FEATURES` (`features.test.ts:11-12` fija diez por igualdad: pasa a once);
  `shared/ui` tiene `Tabs`, `DataTable`, `ConfirmModal`, `StatusTag`, `KpiCard`, `MaskedValue`:
  **existen**. `features/system/pages/KeysPage.tsx` y sus componentes **no existen**.

### Adjuntos y autorización (`modules/attachments` nuevo, `modules/members`, EP-19)

- `modules/attachments/` **no existe**. `main.MODULES` (`main.py:63-73`) gana `attachments`
  **antes de `members`** (members → attachments es la dirección del mapa; `attachments` nunca importa
  `members`); `cli_base._load_module_services` y `worker/runtime.py` reutilizan la lista;
  `migrations/env.py:35-41` importa los `models` de cada módulo: sumar `attachments`; `APP_SCHEMAS`
  (`core/db.py:50`) y las cuatro sentencias de esquemas de `grants.sql` (`:71-81`, enumeradas
  literalmente) ganan `attachments`. `ALLOWED_EDGES` (`test_service_import_graph.py:55-82`) gana
  `("members", "attachments")` y `("members", "settings")` (ver abajo); sin ciclo.
- `bus.encrypt(data_class, plaintext: bytes, aad: bytes, *, record_id) -> str` y `bus.decrypt`
  (`bus.py:59-108`), `aad_for(record_id)`: **existen**, síncronos; devuelven el blob textual `apx1.…`
  que se escribe tal cual en el objeto (5 MB → unos 7 MB de texto en memoria; aceptable, riesgo del
  desglose). La clase `attachment.sensitive` entra en `registry._V01` con `encrypt=True, columns=()`
  (`value_type` es `Literal["str","date","json"]`: sumar `"bytes"` o dejar `"str"` con comentario).
  `test_no_plaintext_at_rest.test_registry_columns_are_encrypted` recorre `spec.columns`: con `()` no
  exige columnas; la prueba nueva "los bytes originales no están en el archivo" es de `tests/attachments`.
- Puertas del descifrado: `test_reveal_single_door.py` (`PUERTA = members/detail.py:_decrypt_fields`,
  `PUERTA_EXPORTACION = members/exports.py:_decrypt_batch`, `test_nadie_fuera_de_core_llama_a_bus_decrypt`)
  y `test_crypto_bus_importers.IMPORTADORES_REALES` (cinco archivos de `members`; la lista blanca de
  rutas ya anticipa `attachments` "cuando exista, v0.3", `:14`): `attachments/service.py` (o un
  privado `crypto.py`) llamando `bus.encrypt`/`bus.decrypt` **rompe las dos pruebas** hasta que ganen
  una tercera puerta con nombre fijo (`modules/attachments/<archivo>.py:_decrypt_file`). Anotar.
- `core/http.py`: `no_store`, `NO_STORE`, `csv_download(body, filename)` con `nosniff`, `no-store`
  y `Content-Disposition: attachment` (`:21-58`): **existe para CSV**; la descarga de un adjunto
  necesita el `media_type` del `mime` guardado: `file_download(...)` nuevo (sin `StreamingResponse`
  obligatorio: el archivo cabe en memoria). CSP de las respuestas del api (`proxy-api.conf`:
  `default-src 'none'`) y `X-Content-Type-Options` ya salen de Nginx y del api.
- Subida: `fastapi.UploadFile`/`File(...)` exigen **`python-multipart`** (no está en `uv.lock`;
  Apache-2.0, aceptada; entra en `NOTICE` y `check-licenses-api.sh`). Alternativa sin dependencia:
  cuerpo crudo (`Request.stream()`, `Content-Type` del cliente ignorado) con `kind` y `sensitive` en la
  ruta o la query; entonces el borde de Nginx es exacto (`client_max_body_size 5m` = 5.242.880 bytes,
  sin sobrecarga multipart) y la "excepción de 6 MB" deja de hacer falta. `UPLOADS_DIR: Path`
  (`config.py:202`, `.env.example:33`) **existe**; `STORAGE_PROVIDER`, `S3_*` **no existen** (cada una
  entra en `Settings` + `.env.example`, `test_env_example`); `boto3` **no está** (Apache-2.0 con
  `botocore`, `s3transfer`, `jmespath`, `python-dateutil`, `urllib3`, `six`: pesa y nadie lo usa en
  v0.3). Nombre aleatorio: `uuid4().hex` o `secrets.token_hex(16)` (`secrets` no está prohibido por
  `banned-api`). Detección de tipo propia (JPEG, PNG, PDF): sin librería.
- Escritura atómica en `/data/uploads`: el api corre `read_only: true` con `tmpfs /tmp`
  (`compose.yml:123-127`) y `uploads` RW (`:118`); `os.replace` solo es atómico dentro del mismo
  sistema de archivos: el temporal va en `UPLOADS_DIR`, no en `/tmp`. `tools` monta `uploads` RW
  (`:237`), `backup` RO (`:283`), el worker **no** (`test_compose_config.sh:99` lo exige). El directorio
  nace en la imagen (`Dockerfile:37`, dueño `apex` 10001). `backup/run.sh:92-124` ya empaqueta
  `uploads` en `<name>-uploads.tar.age` y `restore.sh` lo repone con `API_UID 10001`: US-114 cumplida;
  falta la prueba de restauración **con un adjunto** (riesgo 5 del plan): `infra/tests/restore_e2e.sh`.
- `members`: `Member.data_consent_at: datetime | None`, `data_consent_version: str | None`
  (`models.py:86-87`), `MemberCreate.data_consent: bool` (el servidor fija `now`, M-4; `service.py:233`),
  `MemberPatch.data_consent: StrictBool | None` (solo `true`, `changes.py:190-207`),
  `compute_warnings` → `["data_consent_missing"]` (N-19), `count_without_consent(session)`
  (`service.py:334-343`, S5-D80/D240), `names_for`, `ensure_exists(session, id, *, include_deleted)`,
  `get` (`detail.py`) con `warnings`: **existen**. **Contrato a decidir (US-149):** la historia pide
  `data_consent_at` del cliente (fecha-hora con zona, ≤ ahora) y 422 `field="data_consent_at"` cuando
  `consent_required(today, consent_required_from)`; hoy el campo es `data_consent: bool` y la fecha la
  pone el servidor. Cambiarlo toca `MemberCreate`/`MemberPatch` (`extra="forbid"`), `seed/dataset.py`
  y `imports/parse.py` (el `xlsx` de `import-members` trae `data_consent`), el front
  (`MemberFormFields`, `schemas.ts`) y las pruebas; mantener `data_consent: bool` y sumar
  `data_consent_at` opcional (≤ ahora; por defecto ahora) es compatible. `data_consent_version` hoy
  **siempre `None`**: `settings.service.current_privacy_version()` **existe** (`service.py:16`, S2-D45)
  pero `members` no lo llama: arista nueva `members → settings` en `ALLOWED_EDGES` (sin ciclo:
  `settings` no importa `members`); 409 `privacy_version_missing` nuevo en el catálogo.
  `PrivacySettings.consent_required_from: date | None = None` (`settings/schemas.py:115,138`, N-18):
  el desglose lee el nulo como "obligatoria desde el despliegue de v0.3"; el código actual lo trata
  como "sin corte" (solo aviso). Confirmar en T-DOC (riesgo 1 del desglose).
- `GET /members?consent=missing`: `MemberListQuery(q, status, sort, membership_status, plan_id,
  limit, offset)` (`schemas.py:145-156`; `openapi.json` lo confirma) **no tiene `consent`**;
  `_filtro_de_estado`/`_consulta` ganan la rama; `MemberExportQuery` decide si también. El front
  `MembersListPage` lee la URL (`?membership_status=`): sumar `consent`.
- `GET /members/{id}` con `photo_attachment_id`: `MemberDetailOut` (`extra="forbid"`) gana el campo;
  `openapi.json`, `types.ts` y las fixtures del front (`memberDetailBody`) cambian.
- Rutas: `POST|GET /members/{id}/attachments` en `members/router.py` (292 líneas; `no_store` a nivel
  de router; `/members/export` ya va antes de `/{member_id}`), cubeta `members-write` (60/min) para
  subir y `members-detail` o `staff-read` para listar; `GET /attachments/{id}` en
  `attachments/router.py` (`StaffDep`; `GET` sin obligación de cubeta: por seguridad `members-detail`
  o una `attachments-read` nueva con `USER_*`, `.env.example` y el conteo de cubetas). 404 para socio
  inexistente o dado de baja al subir (N-20); descarga de un dado de baja permitida.
- Auditoría: `attachments.attachments` `__audited__ = True` (`insert` con `uploaded_by`) y
  `__audit_subject__ = "owner_id"` (`test_audit_subject` exige sujeto en modelos con socio); descarga con
  `audit.record(action="download", table_name="attachments.attachments", record_id=id,
  subject_member_id=owner_id)` (N-08, patrón de `payments/receipt.py`). El evento
  `SensitiveFieldRevealed` **no existe en el código** (grep sin resultados): US-150 lo da por existente;
  sin suscriptor es YAGNI → T-DOC decide no emitirlo (o crearlo en `attachments/service.py` con
  `test_events_without_pii`: `field="attachment:<id>"` es texto; revisar que la prueba lo admita).
- `PRIVATE_HELPERS["members"] = {rules, detail, changes, contact, channels, exports}`
  (`_imports.py:48`) y `test_no_cross_models.py:171-173` por igualdad: un privado nuevo
  (`attachments.py` o `consent.py`) entra en los dos sitios; `members/service.py` mide 588 líneas.
- Dashboard: `DashboardOut.members_without_consent: int` y `summary` que lo llena con
  `members_service.count_without_consent` (`dashboard/service.py:259`, S5-B10, US-132): **existe**; el
  punto "`GET /dashboard` llena `members_without_consent`" de `SPRINT-06.md` ya está hecho. Front:
  `NotificationKpis.tsx` muestra "Sin consentimiento" con el conteo (S5-F3) sin enlace a
  `/socios?consent=missing`; `Inicio.html` no dibuja la tarjeta (`// DESIGN-GAP:` ya anotado en
  BRECHAS 13.24). `MemberDetailPage.tsx:56` tiene la pestaña `adjuntos` con `disabledUntil: "v0.3"`
  y el aviso "Sin autorización de datos registrada" (Q16): **existen**. `Socio_Form.html` tiene la
  sección "Autorización de datos (Ley 1581)"; **no tiene campo de foto** (`grep Foto` vacío): el
  `PhotoField` de US-148 nace con `// DESIGN-GAP:`. `web/src/core/api/client.ts` tiene `api.blob`
  (descarga) pero **no `api.upload`** (FormData o binario con `timeout` propio). La miniatura por blob
  exige `img-src 'self' data: blob:` en la CSP de `= /index.html` (`default.conf:104`;
  `test_nginx_conf.sh` revisa la CSP: cambiar con prueba).
- Nginx: `client_max_body_size 5m` en el `server` (`default.conf:30`, "para los adjuntos de v0.3")
  pero `location /api/` lo baja a `64k` (`:73`) y `test_nginx_conf.sh:122-127` fija `64k` en `/api/`,
  `128k` solo en `settings/privacy` y `5m` en el server: un `location ~ ^/api/v1/members/[^/]+/attachments$`
  **antes** de `/api/` con `client_max_body_size 6m` (o `5m` exacto si el cuerpo es crudo),
  `include snippets/proxy-api.conf` y la prueba de borde 5.242.880 / 5.242.881 a través de Nginx (DoD).
  `proxy_read_timeout 60s` basta. Nginx no sirve `/data/uploads` (no hay `location` ni volumen en
  `web`): bien.

### TLS híbrido (`infra/`, `core/config.py`, EP-20)

- `infra/caddy/`, `Caddyfile`, servicio `caddy`, perfil `tls`, `compose.tls.yml`, volúmenes
  `caddy_data`/`caddy_config`: **no existen**. Perfiles hoy: `tools`, `bootstrap` (prod), `prod-init`,
  `openbao`, `avisos` (dev). `caddy:2-alpine` en el host = **2.11.3** (`x25519mlkem768` en `curves`
  y ML-KEM por omisión desde la 2.10, Go 1.24): sirve, **fijada por digest con fecha y comando**
  (`test_images_pinned.sh` revisa cada `image:` de los dos compose) y en el bloque fijo de `NOTICE`
  (Apache-2.0). `web` publica `${WEB_PORT:-80}:80` con IP fija `172.30.0.10` y `TRUSTED_PROXIES=
  172.30.0.10/32` (`.env.example:45`): con el perfil `tls`, `web` no debe publicar puertos (overlay
  `compose.tls.yml` con `ports: !override []`, porque Compose no condiciona `ports` por perfil) y
  Caddy recibe IP fija propia en la red `default` (por ejemplo `.11`).
- Proxies encadenados: `snippets/proxy-api.conf:6-7` pone `X-Forwarded-For $remote_addr` (sobrescribe
  la cadena) y `X-Forwarded-Proto $scheme` (`http` siempre); `core/ratelimit.py:6-8,88` recorre
  `X-Forwarded-For` de derecha a izquierda saltando `TRUSTED_PROXIES`. Detrás de Caddy el api vería
  **una sola IP (la de Caddy)** para todos los clientes: `limit_req` de Nginx y el limitador del api
  bloquearían a todos a la vez (riesgo 4 del plan, confirmado). Salida: en Nginx `set_real_ip_from
  <ip de caddy>; real_ip_header X-Forwarded-For; real_ip_recursive on;` (el comentario de
  `default.conf:2-3` lo anticipa) y `X-Forwarded-Proto $http_x_forwarded_proto` cuando viene de Caddy,
  o `proxy_add_x_forwarded_for` + `TRUSTED_PROXIES` con las dos IPs. Prueba del limitador detrás de los
  dos proxies (mitigación del plan) en el smoke.
- Cookie: `COOKIE_SECURE: bool = False`, `ALLOW_INSECURE_COOKIE: bool = False` con
  `validate_cookie_security(ENV, COOKIE_SECURE, ALLOW_INSECURE_COOKIE)` (`config.py:215-216,416-424`;
  producción exige `Secure` salvo `ALLOW_INSECURE_COOKIE=true`, P7, S4B-D154: el `.env` de instalación
  LAN lo pone en `true`) y `set_refresh_cookie(..., secure=settings.COOKIE_SECURE, samesite="strict")`
  (`auth/cookies.py:33-43`): **existe con otra forma** que el `cookie_secure(settings)` derivado de
  `public_origin`. Decidir: conservar `COOKIE_SECURE` explícito y endurecer el validador ("con
  `APEX_DOMAIN`, `COOKIE_SECURE=true` y `ALLOW_INSECURE_COOKIE=false` obligatorios") en vez de derivar.
- Origen público: `FRONT_BASE_URL` (`http://` o `https://`, validado, `:217,457-461`; N-11: enlaces de
  activación y recuperación), `CORS_ORIGINS` (vacío = sin CORS, nunca `*`), `AUTH_ALLOWED_ORIGINS`
  (vacío = el origen de `FRONT_BASE_URL`): **existen**. `public_origin`, `validate_origins`,
  `APEX_DOMAIN`, `ACME_EMAIL`, `ACME_STAGING`, `LAN_ORIGIN` **no existen**; `LAN_ORIGIN` duplica
  `FRONT_BASE_URL`. `Settings` es `extra="forbid"`: `APEX_DOMAIN` la leen el api (validación) y Caddy
  (interpolación de Compose) → campo de `Settings` en `.env.example`; `ACME_EMAIL`/`ACME_STAGING` solo
  Caddy → `.env.ops.example` + `NON_API_ENV_VARS` (S4B-D79) y las listas de variables prohibidas por
  servicio de `deploy.sh`/`prod-smoke.sh` (L-9, S5-D63) y `test_env_isolation.sh`.
- CSP y HSTS: `connect-src 'self'` relativo (`default.conf:104`) y el front con rutas relativas: "la
  CSP con dominio no contiene `http:`" se cumple por construcción; HSTS **no está** en ningún snippet
  (`security-headers.conf:3` lo reserva para US-153) y debe salir **solo de Caddy** (así el modo LAN
  no lo envía). `openbao/config.hcl` con `tls_disable = true` ("TLS llega con Caddy/EP-20",
  `test_openbao_infra.sh:213`): Caddy delante de Nginx **no cifra la red `custody`**; el residual
  S5-D63 (TLS en `custody`, dueño EP-20 v0.3, titular) queda fuera de US-152/US-153: decisión explícita.
- Sondas: `deploy.sh:345-370` sondea `http://127.0.0.1:${WEB_PORT}/api/v1/health` (acepta 503 con
  `crypto: sealed`); `prod-smoke.sh` igual; con el perfil `tls` el puerto 80 del host es de Caddy
  (redirección 308) y 443 TLS: la sonda debe aceptar `--profile tls` (`DEPLOY_COMPOSE_EXTRA`) y sondear
  por `docker compose exec web wget` o por `https://` con la CA interna. `openssl s_client -groups
  X25519MLKEM768` exige OpenSSL **≥ 3.5** (el runner `ubuntu-24.04` trae 3.0.13): el `tls-smoke.sh`
  corre `openssl` dentro de un contenedor (por ejemplo `alpine:3.22`, por digest) o usa `curl` de Caddy.
- `.github/workflows/ci.yml`: `images` corre `test_compose_config.sh` y `test_nginx_conf.sh` (`:337`),
  el smoke de Compose (`:344`) y la restauración (`:350`): el smoke TLS con `tls internal` y el modo
  LAN entran ahí; `e2e-stack` no cambia.

### Front (Waves 5a y 5b)

- `ENABLED_FEATURES` (diez) gana `crypto` (`features.test.ts:11-12` a once); `/sistema/llaves` gana
  `load` con `KeysPage`; `features/system/{components/{SignatureStatus,KeysInventory,CryptoOpsLog,
  CryptoJobs,RotateKeyModal},api.ts,schemas.ts}` nuevos; `VerifyChainButton.tsx:8` cierra su
  `DESIGN-GAP` ("última firma nocturna… ML-DSA": el texto real dirá `Ed25519`).
- `features/members`: `PhotoField` (sin diseño: `DESIGN-GAP`), `ConsentSection` (fecha, versión en
  solo lectura, archivo), `AttachmentsTab` (pestaña `adjuntos` habilitada), miniatura en el encabezado;
  `api.ts`/`schemas.ts` con `data_consent_at` y `photo_attachment_id`; `MembersListPage` con
  `consent=missing`. `shared/lib/download.ts` (`downloadBlob`) **existe**; `api.upload` **no**.
- `features/dashboard`: `NotificationKpis` enlaza "Sin consentimiento" a `/socios?consent=missing`
  (`ConsentKpi` del desglose ya existe como tarjeta; solo falta el enlace).
- `web/src/core/api/types.ts` se regenera con `npm run gen:api` (CI "tipos del api al día"). E2E
  (`web/tests/e2e/stack/`): estado de la firma, rotación desde pantalla, subida 5.242.880/5.242.881 y
  descarga de la autorización (DoD).

## 2. Blast radius por bloque

Dependientes inversos (grep de `from app.… import` en `src/`) de cada pieza que el sprint toca:
`core.audit` → 24 archivos (`cli_base`, seis `cli_ops`, `core/audit_verify`, `core/export_db`,
`imports/persist`, `main`, los siete de `modules/audit`, `dashboard/service`, `members/{contact,
detail,exports}`, `payments/{exports,service}`, `worker/runtime`); `core.audit_verify` → 3 (`cli`,
`cli_ops/verify_audit`, `audit/verify`); `core.crypto.service` → 4 (`cli_manifest`,
`cli_ops/{retire_key,rotate_key}`, `crypto/rotation`); `core.crypto.registry` → 6 (todos de
`core/crypto` salvo `cli_ops/rotate_key`); `core.crypto.bus` → 8 (`cli_manifest`, `crypto/{minisign,
service,types}`, `members/{changes,exports,service}`, `worker/jobs/backup_check`);
`core.crypto.keyring` → 10 (incluido `core/security.py` y `main.py`); `core.crypto.provider` → 17;
`modules.audit` → 10 (`cli_ops/verify_audit`, `main`, los de `audit`, `dashboard/service`,
`members/{router,service}`); `modules.members.service` → 16 (`imports/*`, `dashboard`, `memberships/
{lifecycle,queries,sell,service,summary}`, `notifications/{generate,queries,sending,service}`,
`payments/{exports,queries}`, `seed/apply`); `modules.dashboard` → solo su router y service;
`core.security` → 30 archivos; `core.config` → 44; `auth/cookies.py` → `auth/{router,rules}.py`.
Lo que cambia de firma en esos contratos es poco (secciones 1 y 5): `VerifyResultOut`,
`MemberCreate`/`MemberDetailOut`, `MemberListQuery`, y nada en `core.audit.record`.

### Wave 0 · T-DOC, Caddy con perfil `tls`, Nginx y respaldo

- Archivos nuevos: `infra/caddy/Caddyfile` (global `email {$ACME_EMAIL}`; sitio `{$APEX_DOMAIN}` con
  `tls { curves x25519mlkem768 x25519; protocols tls1.2 tls1.3 }`, `header Strict-Transport-Security
  "max-age=31536000; includeSubDomains"`, `reverse_proxy web:80` con `X-Forwarded-Proto`, redirección
  308 explícita; variante `acme_ca` de staging por variable; `tls internal` para `apex.localhost` en
  desarrollo), `infra/compose.tls.yml` (anula `ports` de `web`; publica 80 y 443 en `caddy`),
  `infra/caddy/tests/*` (Bash puro), `scripts/workflow/tls-smoke.sh` (grupo negociado, caída a
  `X25519`, rechazo de TLS 1.1, 308 con `Location`, HSTS presente con dominio y ausente en LAN, `docker
  compose config` con y sin perfil), `docs/operacion/tls.md` (el desglose dice `docs/runbooks/tls.md`:
  la carpeta real es `docs/operacion/`). Tocados: `infra/compose.yml` (servicio `caddy` con
  `profiles: ["tls"]`, imagen `caddy:2.11.3@sha256:…` con fecha y comando, IP fija en `default`,
  volúmenes `caddy_data` y `caddy_config`, `read_only`, `cap_drop`, `depends_on web healthy`),
  `infra/compose.dev.yml` (perfil `tls` con `apex.localhost` y CA interna), `infra/nginx/default.conf`
  (`set_real_ip_from`/`real_ip_header` desde la IP de Caddy; `location` de subida con `6m` o `5m`;
  `blob:` en `img-src`), `infra/nginx/snippets/proxy-api.conf` (`X-Forwarded-Proto` y `-For` cuando
  llegan de Caddy), `.env.example` (`APEX_DOMAIN`), `.env.ops.example` (`ACME_EMAIL`, `ACME_STAGING`),
  `core/config.py` (`APEX_DOMAIN: str | None`, `public_origin`, `validate_origins`, validador de la
  cookie con dominio; `NON_API_ENV_VARS`), `scripts/ci/{test_compose_config,test_nginx_conf,
  test_images_pinned,prod-smoke,compose-smoke}.sh`, `infra/deploy.sh` (sonda con perfil `tls`),
  `test_deploy_script.sh`, `test_env_isolation.sh`, `.github/workflows/ci.yml` (smoke TLS en `images`),
  `NOTICE` (bloque fijo: editar `notice.sh`), `CLAUDE.md`, `RUNBOOK.md` §14, `docs/operacion/
  instalar-en-servidor.md` ("TLS: todavía no" → perfil `tls`), `infra/tests/restore_e2e.sh` (un
  adjunto en el juego de respaldo; `uploads` ya viaja).
- Lo rompe fuera del gate: `test_env_example.py:34,40` en cuanto `Settings` gane un campo sin línea en
  `.env.example` o `.env` gane una clave ajena sin `NON_API_ENV_VARS` (**api, worker y `tools` dejan
  de arrancar**, `extra="forbid"`); `test_images_pinned.sh` con `caddy` sin digest;
  `test_compose_config.sh` (volúmenes declarados por cadena literal, `web` con y sin `ports` según el
  archivo); `test_nginx_conf.sh:122-127` (`64k` en `/api/`, `128k` una sola vez, CSP exacta);
  `test_deploy_script.sh` (282 casos) si cambia la sonda; `test_openbao_infra.sh:213` no cambia.
- Quirk de buildx (RUNBOOK §7): Caddy es imagen pública (`up -d --no-build caddy`); la imagen del api
  no cambia en W0 salvo por `core/config.py` (en desarrollo va por bind; en producción se reconstruye con
  el bloque A).

### Bloque A · Auditoría firmada (US-140 a US-142)

- Archivos nuevos: `core/audit_sign.py` (`AuditSignature` modelo de `audit.signatures`, `sign_latest`,
  `AUDIT_SIGN_LOCK_KEY = 4_270_004`, `latest_signature`), `cli_ops/sign_audit.py`,
  `worker/jobs/sign_audit.py`, `migrations/versions/0021_audit_signatures.py`,
  `0022_verify_signatures.py`, `tests/audit/test_sign_*.py`, `tests/worker/
  test_sign_audit.py`, `tests/cli/test_sign_audit.py`, `tests/migrations/test_002[12]_*.py`,
  `tests/crypto/test_sign_openbao.py` (marcador `openbao`, dos modos: con la llave Ed25519 real y con
  el 400 de `ml-dsa` simulado por `httpx.MockTransport`). Tocados: `core/audit.py`
  (`signature_payload`, `needs_signature`, `is_signature_late`: puras), `core/audit_verify.py`
  (columnas nuevas, verificación de firmas por `bus.verify`, `VerificationView`), `core/crypto/
  registry.py` (`audit.signature`, `sign=True`), `core/crypto/bootstrap.py` (`key_ref` y `algorithm`
  reales por proveedor: `apex-sign-audit` con `openbao`), `core/crypto/bus.py` (`alg` desde
  `llave.algorithm` en vez de `SIGN_ALG_V01`), `cli.py` (`init-keys --data-class` real o delegado a
  `cli_ops/keys.py`), `cli_ops/verify_audit.py`, `modules/audit/{router,schemas,service,verify}.py`
  (`GET /audit/signatures/latest`, `VerifyResultOut` ampliado), `worker/jobs/__init__.py` (`JOBS`),
  `worker/runtime.py` y `worker/jobs/notify.py` (`audit.signature` en las clases del worker),
  `core/jobs.py` (`DETAIL_KEYS`), `core/alerts_telegram.py` (textos de los dos códigos nuevos),
  `infra/openbao/policies/{apex-api,apex-worker,apex-tools}.hcl` (`sign`, `verify`, `keys` read de
  `apex-sign-audit`), `scripts/ci/test_openbao_infra.sh` (políticas exactas), `infra/db/grants.sql`
  (`audit.signatures`: api `SELECT`, worker `SELECT, INSERT`; `-- clasificada:`, `ARRAY`),
  `tests/migrations/test_db_grants.py`, `tests/conftest.py` (limpieza de `audit.signatures` con los
  triggers deshabilitados como `verifications`, antes de `audit_log`), `tests/architecture/
  {test_sql_literals_constant,test_audited_tables,test_worker_boundaries}.py`, `docs/openapi.json`,
  `types.ts`, `docs/adr/` (ADR nuevo o ampliación de ADR-004: paso humano), `RUNBOOK.md` §14,
  `docs/operacion/openbao.md` (política de firma y `init-keys --data-class`).
- Pruebas que fallan en silencio fuera del gate: `test_crypto_no_importa_audit_y_audit_solo_toma_digest`
  (si `core/audit.py` importa `bus`); `test_jobs_y_alerts_no_importan_modulos_ni_audit`;
  `test_sql_literals_constant` (candado nuevo sin anotar); `test_audited_tables` (`audit.signatures`
  sin exclusión → "toda tabla no excluida está auditada"); `test_db_grants`/`grants.sql` (**`dbsetup`
  falla cerrado** con la tabla sin clasificar; en desarrollo no corre, en CI y producción sí);
  `tests/core/test_migrations.py` (ciclo `0001 → head → base → head`: `0021`/`0022` con `downgrade`
  exacto); `test_worker_boundaries` (el job no escribe SQL ni importa `models`/`router`: llama
  `core.audit_sign`); `test_kek_path_single_door` (no aplica); `test_openbao_infra.sh` (políticas);
  `tests/core/test_env_example` (sin variables nuevas aquí); `test_error_codes_per_route` (sin códigos
  nuevos; el 503 ya cubre `crypto_unavailable`).
- Contratos: `signature_payload(through_seq, hash) -> bytes` con prefijo `apex-audit-sig-v1`
  (irreversible con datos: riesgo 2); `sign_latest(session, *, by=SYSTEM_USER_ID) -> signed |
  nothing_new` bajo `pg_advisory_xact_lock(4_270_004)` e índice único en `through_seq`; `bus.sign(
  "audit.signature", payload)`; fila con `key_id`, `algorithm` (de la llave), `signed_at` UTC; `crypto_ops`
  `sign`; el job reintenta 3 veces (2, 4, 8 s) ante `CryptoUnavailable`/`sealed`/`unreachable`, termina
  `error` con `alert("audit_sign_failed", …)` y, si `is_signature_late`, `alert("audit_signature_late",
  …)`; `cli sign-audit` sale 0 al firmar o sin novedad; `POST /audit/verify` recorre la cadena y las
  firmas (una llamada a Transit por firma; con el custodio sellado la parte de firmas no puede
  comprobarse: decidir `signatures_checked = 0` con bandera o 503, Q4); `GET /audit/signatures/latest`
  → `{latest: {through_seq, signed_at, algorithm, key_id}, last_valid: {...} | null, is_late}` solo
  admin. Con `CRYPTO_PROVIDER=local` (desarrollo, `apex-db-1`) la llave es `local:sign-ed25519` y firma
  el archivo `sign-ed25519.key` (el worker monta `keys:ro`); con `openbao`, `apex-sign-audit`.
- La demo "con OpenBao sellado debe reintentar y alertar" necesita el perfil `openbao` de
  `compose.dev.yml` y `scripts/dev/openbao-seal.sh`.

### Bloque B · Llaves, primera parte (US-143, US-144, US-146)

- Archivos nuevos: `core/crypto/router.py`, `core/crypto/admin.py` (`list_keys`, `list_ops`,
  `list_jobs`, `job_percent`, `build_cbom`, `export_cbom`, `set_audit_writer`), `core/crypto/
  schemas.py` (`CryptoKeyOut`, `CryptoOpOut`, `CryptoJobOut`, `RotateIn`, `RotationStartedOut`;
  nunca `wrapped_material`), `tests/crypto/test_admin_*.py`, `tests/crypto/test_router_*.py`,
  `tests/architecture/test_core_crypto_router.py` (no importa `app.modules`; `records_count` por el
  registro; `__init__` sin imports; consolidable en `test_core_import_direction`),
  `web/src/features/system/{pages/KeysPage.tsx,components/{KeysInventory,CryptoOpsLog,CryptoJobs,
  RotateKeyModal}.tsx}`. Tocados: `main.py` (registro explícito del router), `core/http.py`
  (`file_download`), `tests/architecture/test_core_import_direction.py` (si se elige la excepción),
  `web/src/config/{features,features.test,routeTable}.ts`, `features/system/{api,schemas}.ts`,
  `docs/openapi.json`, `types.ts`, `CLAUDE.md` (`core/crypto/{router,admin,schemas}.py`),
  `docs/operacion/rotar-llave.md` (pantalla), `BRECHAS.md` §14.
- Pruebas que fallan en silencio fuera del gate: `test_core_import_direction` (router o `admin` con
  `app.core.audit` o `app.modules`); `test_banned_imports` (`router.py`/`admin.py` dentro de
  `core/crypto` pasan el lint pero el desglose pide una aserción extra: que no importen
  `cryptography`/`oqs`); `test_list_routes_use_page_params` (`GET /crypto/keys|ops|jobs` con
  `Page[...]` sin `q`: exclusión con motivo o `q` sobre `data_class`); `test_every_route_has_role`
  (`AdminDep`); `test_no_store_routes`; `test_error_codes_per_route` (422 con parámetros; sin 429 si
  no hay cubeta); `test_file_and_function_size` (`service.py` 556 + lecturas → `admin.py` aparte);
  `test_health_check_registrars` no aplica; `features.test.ts` (`size == 10`).
- Contratos: `GET /crypto/keys?purpose&state&provider&data_class&limit&offset` (sin `wrapped_material`;
  `records_count` por `data_class`; no escribe `crypto_ops`), `GET /crypto/ops?from&to&verb&data_class&
  key_id&user_id&result&batch_id` (`at DESC`; `from`/`to` con `check_instant_range`), `GET /crypto/jobs?
  status&kind&data_class` con `percent`, `GET /crypto/cbom` (JSON, `apex-cbom-AAAA-MM-DD.json`, auditoría
  `export` con `{count}`); todo admin; `provider_status` opcional para la línea de `Llaves.html`.

### Bloque C · Adjuntos (US-147 a US-151)

- Archivos nuevos: `modules/attachments/{__init__,router,schemas,models,service,exceptions}.py`,
  `modules/attachments/storage/{__init__,base,local}.py` (`s3.py` solo si T-DOC lo mantiene),
  `modules/attachments/files.py` (privado: `detect_mime`, `validate_upload`, puerta `_decrypt_file`),
  `migrations/versions/0023_attachments.py` (`CREATE SCHEMA attachments`; tabla con CHECKs de
  `owner_table`, `kind`, `mime`, `size_bytes`, `kind <> 'consent' OR sensitive`; `key_id` nulo;
  `storage_provider`; índice `(owner_table, owner_id, kind, created_at DESC)`),
  `0024_members_consent_missing_idx.py` (opcional, solo si la medición lo pide), `tests/attachments/*`,
  `tests/migrations/test_0023_*.py`, `web/src/features/members/components/{PhotoField,ConsentSection,
  AttachmentsTab}.tsx`, `web/src/core/api/client.ts` (`api.upload`). Tocados: `main.MODULES`,
  `migrations/env.py`, `core/db.py` (`APP_SCHEMAS`), `core/crypto/registry.py`
  (`attachment.sensitive`), `core/config.py` + `.env.example` (`STORAGE_PROVIDER`; `S3_*` solo si
  entra S3), `core/http.py`, `members/{schemas,service,router,changes,rules}.py` (`attach`,
  `list_attachments`, `consent_required`, `validate_consent`, `data_consent_version` real, filtro
  `consent`, `photo_attachment_id`), `members/exceptions.py` (409 `privacy_version_missing`), `modules/
  attachments/service.py` ↔ `bus`, `seed/dataset.py` e `imports/parse.py` (si el contrato de
  consentimiento cambia), `infra/db/grants.sql` (`attachments.attachments`: api `SELECT, INSERT` y,
  si rota el api, `UPDATE (key_id, updated_at)`; esquema en las cuatro sentencias; `ARRAY`),
  `tests/migrations/test_db_grants.py`, `tests/conftest.py` (limpieza de `attachments.attachments`
  antes de `members`), `tests/architecture/{_imports,test_no_cross_models,test_service_import_graph,
  test_crypto_bus_importers,test_reveal_single_door,test_no_plaintext_at_rest,test_audited_tables,
  test_audit_subject,test_user_limits_catalog}.py`, `pyproject.toml`/`uv.lock` (`python-multipart`
  si multipart), `NOTICE`, `scripts/ci/check-licenses-api.sh`, `infra/nginx/default.conf`
  (`location` de subida, `blob:`), `scripts/ci/test_nginx_conf.sh`, `infra/tests/restore_e2e.sh`,
  `docs/openapi.json`, `types.ts`, `web/src/features/{members,dashboard}/*`, `CLAUDE.md`
  (`attachments/`), `docs/operacion/` (guía de adjuntos y autorización), `BRECHAS.md` §14.
- Pruebas que fallan en silencio fuera del gate: `test_reveal_single_door::test_nadie_fuera_de_core_llama_a_bus_decrypt`
  y `test_crypto_bus_importers` (tercera puerta sin anotar); `test_service_import_graph` (aristas
  `members → attachments`, `members → settings`; `attachments` nunca importa `members` ni `auth`);
  `test_no_cross_models` (privado nuevo de `members`; `attachments` no importa `members.models`);
  `test_audited_tables` (tabla nueva sin `__audited__`); `test_audit_subject` (modelo con socio sin
  sujeto); `test_writes_have_user_limit` (`POST /members/{id}/attachments` sin cubeta);
  `test_db_grants`/`grants.sql` (**`dbsetup` falla cerrado** con la tabla y el esquema nuevos);
  `test_env_example` (`STORAGE_PROVIDER`); `test_third_party_confinement` (patrón opcional: `boto3`
  solo bajo `attachments/storage/s3.py`); `test_error_codes_per_route` (422 `file_too_large`,
  `unsupported_type` con `field="file"`; 409 `privacy_version_missing`; 413 de Nginx no lo declara el
  api); `tests/members/*` que fijan `data_consent_version is None` y el alta sin consentimiento con
  solo `warnings`; `tests/imports` y `tests/cli/test_seed*` si el contrato cambia; `test_nginx_conf.sh`.
- Contratos: `attachments.service.store(session, *, owner_table, owner_id, kind, data: bytes,
  sensitive, by) -> AttachmentOut` (lee hasta 5.242.881 bytes y corta; `detect_mime`;
  `validate_upload`; `sensitive=True` forzado para `consent`; id en Python; cifra con `aad =
  aad_for(id)`; `put` atómico; borrado compensatorio si el flush falla), `open(session, id, by) ->
  (AttachmentOut, bytes)` (descifra, `audit.record("download")`, `crypto_ops` `decrypt`),
  `current_photo_ids(session, owner_table, owner_ids)`, `list_for_owner(...) -> Page[AttachmentOut]`
  (sin `filename_random`); `members.service.attach`/`list_attachments` (404 por `ensure_exists`),
  `create` con `consent_required` + `validate_consent` + `current_privacy_version` (409
  `privacy_version_missing`), `update` con autorización tardía, filtro `consent=missing`,
  `photo_attachment_id` en `get`. Descarga con `Content-Type` del `mime`, `Content-Disposition:
  attachment`, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`.

### Bloque D · Rotación desde pantalla (US-145, puerto `Reencryptor`)

- Archivos nuevos: `tests/crypto/test_rotation_api.py`, `tests/attachments/test_reencrypt.py`,
  `web/src/features/system/components/RotateKeyModal.tsx` (si no entró en B). Tocados:
  `core/crypto/registry.py` (puerto `Reencryptor(count_pending(session, old_key_id) -> int,
  reencrypt_batch(session, old_key_id, batch_size, batch_id) -> int)` con registro por `data_class`,
  como `core.events.subscribe`; implementación por omisión = columnas por `discovery`), `core/crypto/
  service.py` (`_pending_total`, `reencrypt_batch` y `finish_rotation` consultan el puerto; sin él,
  `start_rotation` responde `unsupported` para una clase sin columnas y sin reencryptor: **cierra el
  hueco de "job que termina sin recifrar"**), `core/crypto/router.py` (`POST /crypto/keys/{id}/rotate`
  → 202 `{job_id, new_key_id, previous_key_id}`; tarea `asyncio` con sesión propia que recarga el
  keyring, itera `reencrypt_batch`/`finish_rotation` y `fail_job` ante error), `modules/attachments/
  service.py` (registra su `Reencryptor` al importarse: lee cada objeto, descifra con la vieja, cifra
  con la activa, `put` atómico, actualiza `key_id`), `infra/db/grants.sql` y `test_db_grants.py`
  (grants del api sobre `crypto_jobs`/`crypto_keys` por columna; `UPDATE (key_id, updated_at)` en
  `attachments.attachments`), `cli_ops/rotate_key.py` (quita la salida 2 de `ATTACHMENT_CLASS`),
  `docs/operacion/rotar-llave.md`, `CLAUDE.md` (`registry.py`: ahora sí el puerto),
  `tests/architecture/test_file_and_function_size.py:106` ("las cuatro funciones de rotación miden
  menos de 50").
- Pruebas que fallan en silencio fuera del gate: `test_file_and_function_size` (funciones de rotación
  ≥ 50 líneas); `test_crypto_bus_importers`/`test_reveal_single_door` (el reencryptor de adjuntos
  descifra: misma puerta que la descarga); `test_db_grants`; `test_writes_have_user_limit`
  (`admin-write`); `test_error_codes_per_route` (409 `key_not_active`, `purpose_not_rotatable`,
  `rotation_running`, `rotation_not_supported`, `custody_job_running`; 422 `field="confirm"|"reason"`);
  `test_no_direct_now` en la tarea.
- Decisión de seguridad previa (sección 9, C6): grants del api o ejecución fuera del api; y el
  criterio 7 de US-145 contra S4B-D63/D140.

### Bloque E · TLS (US-152, US-153)

- Casi todo en Wave 0 (arriba). Lo que queda para la validación: `tls-smoke.sh` con la CA interna en
  CI y el modo LAN; evidencia `openssl s_client` (en contenedor con OpenSSL ≥ 3.5) del grupo
  `X25519MLKEM768`, de la caída a `X25519` y del rechazo de TLS 1.1; `curl -I http://…` → 308; HSTS
  presente con dominio y ausente en LAN; prueba del limitador detrás de los dos proxies (dos IPs de
  cliente distintas reciben cubetas distintas); SSL Labs con dominio real = paso humano (runbook).
- `core/config.py` (698 líneas): `public_origin(settings)`, `validate_origins(settings)` puras y el
  validador de la cookie con dominio; `tests/core/test_config*.py`; `main.py` (CORS desde
  `validate_origins`; hoy `CORS_ORIGINS` exacto, `main.py:242-252`).

### Deuda con dueño "v0.3" del cierre del Sprint 5: qué entra y qué queda con condición

- **Entra con slice natural:** subruta del volumen `keys` para la llave JWT del worker (S5-D201, "EP-17
  separa `custody/` y `jwt/` con `volume.subpath`"; exige migrar volúmenes e `init-keys`: cabe en la
  Wave 0 o en el bloque A con decisión explícita; si no cabe, nuevo dueño con versión); TLS en
  `custody` (S5-D63, titular, EP-20: **no** lo cubre US-152/US-153; decidir si Caddy o el listener de
  OpenBao con TLS interno entran, o queda con dueño v0.4); llavero `age -p` de llaves y contraseñas
  (S5-D272, "propuesta para v0.3, EP-18": no es código del sistema; procedimiento en
  `docs/operacion/openbao.md` o dueño titular); `rotation_not_supported` de `attachment.sensitive`
  (G-09) → bloque D.
- **Entra solo si el plan lo decide (hoy sin slice):** índice `memberships(end_date)` y CHECK `sent ⇒
  sent_at` (S5-D226, V8: una migración `0025` de dos índices y un CHECK; barato si va junto a las
  otras); `SMTP_TLS_MODE=ssl` para el 465 (S5-D207); `useBlobDownload` por instancia (LOW V10);
  índices de reglas e historial (V8 LOW 5); `display_name` (Q8, S5-D83, titular; BRECHAS 13.11);
  recibo PDF sin logo (BRECHAS 13.6, titular); "Exportar rango" de Auditoría (BRECHAS 13.10, v0.3);
  `unwrap` que devuelva `bytearray` (S5-B2 LOW, "cerrar en v0.3"); AppRole y rotación automática de
  tokens periódicos (S5-D52, operador); trazabilidad por socio de las exportaciones con `audit.append`
  (S5-D63, titular); retención de `rendered_body` (L-4, titular). Cada una recibe en T-DOC un slice
  del Sprint 6 o un dueño nuevo con versión (C1).
- **Pasos humanos pendientes del Sprint 5 que condicionan este sprint:** PR y merge de
  `feat/sprint-05-openbao-avisos-recibos` en `main` (la rama del Sprint 6 nace de ella: el PR del 6
  llegará con los commits del 5 si no se fusiona antes), `git push origin v0.2.0`, custodia 2/2/1 de
  las llaves de desello, `allowed_signers`, N-6/N-7 en el servidor.

### Archivos que el sprint no debe tocar

`core/audit.py` salvo las tres puras y la exclusión de `audit.signatures` (`AUDIT_ACTIONS` ya trae
`download`, `export` y `verify`; `record` no cambia), `core/db.py` salvo `APP_SCHEMAS`,
`core/context.py`, `core/locks.py`, `core/pagination.py`, `core/search.py`, `core/backup_status.py`,
`core/migrations_status.py`, `core/export.py`, `core/export_db.py`, `core/pdf.py`, `core/mail.py`,
`core/crypto/{archive,file_digest,digest,aead,blob,mac,normalize,secret,minisign,kek_backup,
migration,rotation,state,recovery,openbao_wire,local_provider}.py` (`openbao_provider.py` solo si
`SIGN_KEY` pasa a usarse desde `bootstrap`), migraciones `0001` a `0020`, `modules/{plans,
memberships,payments,notifications,auth}/*` (solo se consumen; `auth/cookies.py` no cambia si
`COOKIE_SECURE` sigue explícito), `infra/backup/*` (el respaldo ya incluye `uploads`), `infra/db/
roles.sql`, `infra/compose.e2e.yml`, `infra/compose.verify.yml`, `infra/compose.openbao.yml`,
`infra/openbao/{config.hcl,bootstrap.sh,dev-entrypoint.sh}` (solo `policies/*.hcl`),
`web/src/features/{plans,memberships,payments,notifications,auth}/**`, `web/src/core/api/types.ts`
solo por regeneración, `web/src/config/routes.reference.ts` (la ruta de llaves ya está).

## 3. Capa de datos

### Lo que existe (aplicado en `apex-db-1`; `db_test` se migra desde cero en cada sesión)

- `exec api alembic current` = `0020_notifications_indexes (head)`. Cadena lineal `0001 → … → 0020`
  (`0005b` entre `0005` y `0006`); una sola cabeza. **Convención fijada en el Sprint 5:** numeración
  secuencial real en vez de los rangos reservados del plan (`0015_crypto_provider_migration` en lugar
  de `0030`, S5-D4 y condición C1 de `impacto/sprint-05.md`; RUNBOOK §6 y la DoD "ciclo `0001` a
  `00NN`"). **La siguiente libre es `0021`.**
- Esquemas (`APP_SCHEMAS`, diez): `audit`, `auth`, `crypto`, `members`, `memberships`,
  `notifications`, `payments`, `plans`, `settings`, `worker`; `attachments` **no existe**.
- `audit.audit_log` con triggers `ENABLE ALWAYS` (`0014`); `audit.verifications` (`0013`) append-only
  con `through_seq`, `through_hash`, `rows_checked`, `ok`, `broken_at_seq`, `triggered_by`, `source`;
  función `audit.forbid_mutation()` de `0002` reutilizable para `audit.signatures`.
- `crypto.crypto_keys`: CHECK `purpose IN (encrypt, index, sign)`, `algorithm IN (A256GCM,
  HMAC-SHA256, Ed25519, ML-DSA-65)`, `provider IN (local, openbao)`, `state IN (active, decrypt_only,
  retired)`, índice único parcial de la activa por `(purpose, data_class)`, trigger
  `crypto_keys_guard` (`0003` + `0015`: `provider`/`wrapped_material` solo `local → openbao` o rewrap,
  nunca junto con `state`, y `OLD.purpose <> 'sign'` para ese cambio, S5-D4/D131/D183); ocho llaves en
  desarrollo (5 `encrypt`, 3 `index`, ninguna `sign`), proveedor `local`. `crypto.crypto_ops` con sus
  cuatro índices; `crypto.crypto_jobs` con `uq_crypto_jobs_in_progress`. Ninguna es `__audited__`.
- `members.members` con `data_consent_at` y `data_consent_version` nulos admitidos (Q16);
  `settings.settings_sections` con `privacy` (`policy_version`, `policy_text`, `retention_years`,
  `consent_required_from`). `worker.job_runs` con CHECK de ocho resultados (sin `skipped`).
- Roles: `apex_owner` NOSUPERUSER en pilas nuevas (S5-D6; en `apex-db-1` el propietario sigue siendo
  `apex`, S4B-D3), `apex_api`, `apex_worker`, `apex_backup` con la matriz de `grants.sql` (grants por
  columna, S5-D256) y el bloque fail-closed `clasificadas`.

### Lo que agrega el sprint

- Según `SPRINT-06.md`: `0040`, `0041`, `0042`, `0045`, `0046`, `0050`, `0051`. Según el código: tres
  reales y una opcional, en secuencia y en orden de bloques: `0021_audit_signatures` (US-140: tabla
  `audit.signatures` con `id`, `through_seq` bigint NOT NULL único, `hash` CHAR(64), `signature` text,
  `key_id` UUID (FK lógica), `algorithm` text con CHECK (`Ed25519`, `ML-DSA-65`), `signed_at`
  TIMESTAMPTZ, columnas comunes; índice `signed_at DESC`; triggers `signatures_forbid_mutation` y
  `signatures_forbid_truncate` sobre `audit.forbid_mutation()` con `ENABLE ALWAYS`, patrón de `0013`;
  `downgrade` borra triggers y tabla), `0022_verify_signatures` (US-142: seis columnas
  nulas en `audit.verifications`; sin llenado; los triggers de `0013` se conservan; `downgrade` las
  quita), `0023_attachments` (US-147: `CREATE SCHEMA attachments`; tabla con CHECKs y `key_id` nulo,
  G-09; `downgrade` borra tabla y esquema: solo en desarrollo), `0024_members_consent_missing_idx`
  (US-151, solo si una medición con 1.000 socios lo pide; con `(id) WHERE data_consent_at IS NULL AND
  deleted_at IS NULL`). `0042`, `0045` y `0046` **no se crean**. Opcional del plan (C1):
  `0025_memberships_end_date_idx_and_sent_check` para la deuda S5-D226.
- `test_db_grants.PRIVILEGIOS`, `grants.sql` (matriz, `-- clasificada:`, `ARRAY`, las cuatro
  sentencias de esquemas) clasifican `audit.signatures` (api `SELECT`; worker `SELECT, INSERT`;
  `tools` como propietario) y `attachments.attachments` (api `SELECT, INSERT` [+ `UPDATE (key_id,
  updated_at)` si rota el api]; worker nada); `apex_backup` lee por `pg_read_all_data`. Si el bloque D
  elige "rota el api": `crypto.crypto_jobs` api `INSERT` + `UPDATE (status, done, error, finished_at,
  updated_at)` y `crypto.crypto_keys` api `UPDATE (state, rotated_at, rotated_by, updated_at)` (el
  trigger sigue decidiendo las transiciones).
- Migraciones de datos: `init-keys --data-class audit.signature` (llave) e `init-keys --data-class
  attachment.sensitive` son comandos del CLI, idempotentes y auditados (regla de datos 8; `ensure_keys`
  del api también crearía las filas al arrancar: decidir si se confía en eso o se exige el comando);
  ninguna va en Alembic.

### Riesgos de orden y de la suite

- `0021` y `0022` en el bloque A antes del primer `sign_latest`; `0023` en el bloque C antes de
  `MODULES` con `attachments` (el api de desarrollo migra al reiniciar con `--reload`: escribir y probar
  contra `db_test` o parar `api`; mitigación de 4A). `pg_dump -Fc` de `apex-db-1` antes de `0021`
  (P-MIG; `*.dump` ignorado).
- `tests/conftest.py` `LIMPIEZA_DE_SESION` y `dos_sesiones`: `audit.signatures` se limpia como
  `audit.verifications` (triggers `ENABLE ALWAYS`: `ALTER TABLE … DISABLE TRIGGER USER` dentro de un
  `DO $$ … IF to_regclass(...) IS NOT NULL` para que el Rojo con la tabla aún inexistente no falle) y
  **antes** de `audit_log`; `attachments.attachments` antes de `members`. Los archivos de prueba van a
  un `tmp_path` por sesión (`UPLOADS_DIR`), nunca a `/data/uploads`.
- Rollback: `downgrade 0021`/`0022` borra firmas y columnas (sin datos de producción todavía);
  `downgrade 0023` borra adjuntos y esquema (los archivos quedan huérfanos en `uploads`: RUNBOOK §6
  gana la entrada). Tras el bloque D, una rotación de `attachment.sensitive` a medias deja objetos con
  dos `key_id`: la llave vieja no se retira hasta `count_pending == 0` (por eso `key_id` en la fila).
- Con OpenBao sellado: `migrate`/`dbsetup` corren igual; `sign_audit` reintenta y falla con alerta;
  `GET /attachments/{id}` sensible responde 503 `crypto_unavailable`; la foto (no sensible) sigue.

## 4. Servicios Docker y estrategia de rebuild

- Estado (`docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml ps`): seis
  contenedores `healthy` (`apex-api-1` en `127.0.0.1:8181` con bind de `src` y `migrations` y
  `--reload`, `apex-backup-1`, `apex-db-1` en `127.0.0.1:5442`, `apex-db_test-1` en `127.0.0.1:5443`,
  `apex-web-1` en `0.0.0.0:8180`, `apex-worker-1`), 7 h arriba; sin `openbao` (perfil `openbao` de
  desarrollo apagado: el proveedor de desarrollo es `local`). Imágenes `apex-api:local` (`b44a5dbd4692`)
  y `apex-web:local` (`bd9143cb2cf8`) con revisión `3cd752a`; `apex-backup:local` (`d69bfd76b26c`); las
  `prev-20261105-*` son copias de `deploy.sh`. `caddy:2-alpine` en el host = 2.11.3 (sin digest); la
  imagen de OpenBao 2.7.2 por digest está (se usó para el sondeo). **Las imágenes corresponden al código
  de HEAD** (los dos commits posteriores a `3cd752a` son documentos).
- Cómo corre cada servicio: `api` con bind de `src/` y `migrations/` (cambios sin rebuild); `worker` y
  `tools` con los mismos binds en solo lectura (`compose.dev.yml:54-65`): `sign-audit`, `init-keys
  --data-class`, `rotate-key` corren con `run --rm tools ...` sin reconstruir; el `worker` residente
  exige `restart worker` tras tocar `app/worker/`, `core/audit*` o `core/crypto` (RUNBOOK §7). La imagen
  de producción `apex-api:local` **cambia en cada bloque** (A: `core/audit_sign.py`, `0021`, `0022`;
  B: `core/crypto/{router,admin,schemas}.py`; C: `attachments/`, `0023`, `python-multipart` en
  `uv.lock`; D: registry; E: `core/config.py`) y al cierre; `web` cambia en 5a/5b. `migrate` y
  `dbsetup` (perfil `prod-init`) usan `apex-api:local` y `postgres:16`: tras `0021`-`0023` y los grants
  nuevos, el stack de producción exige reconstruir el api antes de `migrate` (S4B-D98).
- Volúmenes: `pgdata`, `uploads` (api RW, tools RW, backup RO, worker no), `keys` (api RO, worker RO
  con proveedor local, tools RW), `backups`, `openbao-data`, `openbao-token-{api,worker,tools,backup}`;
  nuevos `caddy_data` y `caddy_config` (`test_compose_config.sh:106-108` fija la lista por cadena
  literal: sumarlos). El bloque D no cambia montajes si rota el api; si rotara el worker habría que
  darle `uploads` contra `test_compose_config.sh:99` (S4A-D49).
- Servicio nuevo `caddy` (`infra/compose.yml`, `profiles: ["tls"]`): imagen `caddy:2.11.3@sha256:…`
  con fecha y comando (`test_images_pinned.sh`), `ports: 80:80, 443:443`, IP fija en `default`,
  `depends_on web: service_healthy`, `read_only: true`, `cap_drop ALL` + `cap_add NET_BIND_SERVICE`
  (o puertos altos con `user:`), volúmenes `caddy_data`, `caddy_config` y `./caddy/Caddyfile:ro`,
  `environment: APEX_DOMAIN, ACME_EMAIL, ACME_STAGING`, healthcheck con `caddy` o `wget` a
  `http://127.0.0.1/` (308 cuenta como vivo). `compose.tls.yml` anula `ports` de `web`. En
  `compose.dev.yml`: `tls internal` con `apex.localhost` y `127.0.0.1:8443`. Nginx no publica al host
  con el perfil: `deploy.sh`, `prod-smoke.sh` y `compose-smoke.sh` sondean por `exec web` o por `https`.
- Healthchecks: el de `api` sigue (`/health` con `db ok` y `migrations ok`, acepta 503 `sealed`,
  S5-D15); `worker` por latido; `caddy` nuevo. `backup` no cambia (ya incluye `uploads` y el snapshot).
- OpenBao: políticas nuevas exigen `openbao-bootstrap` (`--first-install` escribe políticas; en una
  instalación existente hay que aplicarlas: `bao policy write` desde el contenedor con un token con
  permiso, paso de `docs/operacion/openbao.md`) y **renovar los tres tokens** si las políticas cambian
  de nombre (si solo cambian de contenido, los tokens existentes heredan). `CRYPTO_PROVIDER=local` en
  desarrollo: la firma usa `sign-ed25519.key`; la demo con OpenBao va sobre el perfil `openbao` o el
  ensayo.
- Quirk del equipo (RUNBOOK §7): `docker compose build`/`up --build` fallan con Compose 5.6.1 + buildx
  0.38.1: se construye con `docker buildx build --load --network host …` y se levanta con `up -d
  --no-build`. **No se reconstruyó nada en esta fase.**

## 5. Contratos API y front

### Estado de `docs/openapi.json` en HEAD

63 rutas y 83 operaciones. `VerifyResultOut` publica `ok, rows_checked, through_seq, broken_at_seq,
started_at, finished_at, triggered_by, source`; `DashboardOut` ya trae `members_without_consent` y
`notifications_today` como enteros; `GET /api/v1/members` acepta `q, status, sort, membership_status,
plan_id, limit, offset`; `MemberDetailOut` sin `photo_attachment_id`; `MemberCreate` con `data_consent:
bool`; ninguna ruta `/crypto/*`, `/attachments/*` ni `/audit/signatures/*`. `web/src/core/api/types.ts`
coincide (CI "tipos del api al día").

### Lo que cambia

- Endpoints nuevos (9 rutas, 9 operaciones, todas con rol, bajo `/api/v1`, con `no_store`): `GET
  /audit/signatures/latest` (admin); `GET /crypto/keys`, `GET /crypto/ops`, `GET /crypto/jobs`, `POST
  /crypto/keys/{id}/rotate` (202), `GET /crypto/cbom` (admin, descarga); `POST /members/{id}/attachments`
  (201, multipart o cuerpo crudo), `GET /members/{id}/attachments` (`Page[AttachmentOut]`), `GET
  /attachments/{id}` (bytes). Total previsto: 72 rutas, 92 operaciones. Códigos nuevos del catálogo:
  409 `key_not_active`, `purpose_not_rotatable`, `rotation_running`, `rotation_not_supported`,
  `custody_job_running`, `privacy_version_missing`; 422 `file_too_large`, `unsupported_type`
  (`field="file"`), `field="confirm"|"reason"|"data_consent_at"`; 404 `attachment_not_found`.
  `PUBLIC_ROUTES` **no cambia** (ocho; `test_every_route_has_role.py:64-76`).
- Endpoints cambiados: `POST /audit/verify` y `GET /audit/verify/last` (`VerifyResultOut` con
  `signatures_checked`, `signatures_valid`, `first_invalid_signature_seq`, `last_valid_signature`
  nulos para verificaciones viejas); `POST /members` (consentimiento obligatorio por corte; 409
  `privacy_version_missing`; `data_consent_version` real); `PATCH /members/{id}` (autorización tardía:
  ya existe con `data_consent: true`; si entra `data_consent_at` explícito, cambia el esquema);
  `GET /members` (`consent=missing`); `GET /members/{id}` (`photo_attachment_id`); `GET /dashboard`
  **no cambia** (ya trae `members_without_consent`); `GET /health` **no cambia**.
- Cubetas: `POST /crypto/keys/{id}/rotate` → `admin-write`; `GET /crypto/cbom` → `export` (2/min) o
  `staff-read`; `POST /members/{id}/attachments` → `members-write`; `GET /attachments/{id}` →
  `members-detail` o `attachments-read` nueva (si nace: `USER_ATTACHMENTS_READ_LIMIT_PER_MIN` en
  `Settings`, `.env.example` con el comentario "Catálogo: 17 cubetas" y `test_user_limits_catalog`).
- CLI (contrato de operación): `init-keys --data-class audit.signature|attachment.sensitive [--as]`,
  `sign-audit [--as]`, `verify-audit` con firmas (salida distinta de 0 si una firma no es válida),
  `rotate-key attachment.sensitive` (tras D), `worker --run-once sign_audit`.
- Front: `ENABLED_FEATURES` gana `crypto` (11); `KeysPage` con tres pestañas y el modal; bloque de
  firma en `AuditPage`; `PhotoField`, `ConsentSection`, `AttachmentsTab` en `members`; enlace del KPI
  "Sin consentimiento"; `api.upload`; sin cambios en `nav.ts`, `permissions.ts`, `routeTable.ts` salvo el
  `load` de `/sistema/llaves`.

### Contradicciones entre desgloses y código que el plan cierra en T-DOC (Wave 0)

- Q27 "ML-DSA-65 si Transit lo ofrece; si no, Ed25519 y se rota después" → **OpenBao 2.7.2 no ofrece
  ML-DSA** (sondeo): la llave nace Ed25519 y la rotación a ML-DSA queda con dueño (EP-26 o una
  versión de OpenBao que lo traiga, verificada con el mismo sondeo en W0 de ese sprint).
- "Consultar capacidades de Transit" (US-140, desglose) → no existe esa API: se intenta crear y se mapea
  el 400 `unknown key type`.
- `0040`…`0051` → `0021`…`0024`; `0042`, `0045`, `0046` **no hacen falta**.
- "`sign_latest` en `core/audit.py`" → `core/audit_sign.py` (regla `audit.py` solo importa
  `crypto/digest`).
- "El router de `core/crypto` importa `core.audit`" → prohibido por `test_core_import_direction`:
  puerto `set_audit_writer` desde `main.py` o excepción anotada.
- "`core/crypto/__init__.py` vacío" → hoy docstring sin imports (equivalente; dejarlo).
- US-145 criterio 7 (`retired` al terminar) → S4B-D63/D140: queda `decrypt_only`; `retired` por
  `retire-key`.
- "`cli rotate-key --resume <job_id>`" (supuesto de US-145) → `start_rotation` reanuda por
  `data_class` el job abierto; no hay `--resume`.
- "`records_count` usa el registro, no `models`" → ya es así por `discovery.encrypted_columns`;
  para adjuntos sale de `attachments.key_id` por el puerto.
- "Puerto `Reencryptor` en `registry.py`" (`CLAUDE.md`, `SPRINT-06.md`) → **no existe**: lo crea el
  bloque D; `CLAUDE.md` se corrige en el mismo cambio.
- "`test_audited_tables.py`: `wrapped_material` excluido del diff" → `crypto_keys` no es auditada
  (excluida con motivo): auditoría explícita saneada.
- "`JOB_KINDS` admite `rewrap` (N-05)" → ya lo admite.
- "`test_core_independent.py` nuevo" → consolidar en `test_core_import_direction.py` (ya lo dice
  `SPRINT-06.md`).
- US-147 criterio 5 (`reveal`/`export` por lectura) y supuesto "no hay `download`" → `download`
  existe desde `0002`; una fila por descarga (N-08).
- US-150 "además emite `SensitiveFieldRevealed`" → el evento no existe; sin suscriptor no se crea.
- US-149 `data_consent_at` del cliente → hoy `data_consent: bool` con fecha del servidor (M-4):
  decidir el contrato; `consent_required_from = None` → significado (desglose: obligatoria desde v0.3;
  código: sin corte).
- `GET /dashboard` "llena `members_without_consent`" → ya lo llena (US-132, S5-B10).
- "`ROUTES.md` solo nombra la pestaña `/attachments`" → `ROUTES.md:25` ya nombra `POST
  /members/:id/attachments` para foto y autorización; `GET /attachments/:id` se agrega.
- `S3CompatibleStorage` con `boto3` → sin historia que lo use en v0.3: decidir (YAGNI) o justificar.
- Multipart (`python-multipart`) frente a cuerpo crudo → decidir; cambia la excepción de Nginx (6m o
  5m exacto).
- `docs/runbooks/tls.md` → `docs/operacion/tls.md`.
- `LAN_ORIGIN` → `FRONT_BASE_URL` (N-11); `cookie_secure(settings)` derivado → `COOKIE_SECURE`
  explícito con validador por dominio (S4B-D154, P7).
- "Caddy 2.10 o superior" → 2.11.3 en el host; fijar por digest.
- "`openssl s_client -groups X25519MLKEM768`" en CI → OpenSSL ≥ 3.5 solo en contenedor.
- "Nginx deja de publicar el 80 con el perfil `tls`" → overlay `compose.tls.yml` (Compose no condiciona
  `ports` por perfil; el desglose ya lo dice; `SPRINT-06.md` no lo nombra).
- "TLS en `custody`" (S5-D63, dueño EP-20) → no está en US-152/US-153: decisión explícita.
- "ADR de auditoría con `signature_payload`" → `test_adr_docs` fija cinco archivos; cambiar o sumar un
  ADR es paso humano (S4B-D47).
- `CLAUDE.md`: `registry.py` "puerto Reencryptor" (aún no), `attachments/ # v0.3` (nace), `sign_audit.py
  (v0.3, EP-17)` (nace), "Caddy opcional" (nace), `cli.py` "sign-audit llega en v0.3 (EP-17)" (nace);
  el stack lista `liboqs-python` que no está en `pyproject.toml`: corregir o justificar.

## 6. Línea base en HEAD `47ec673`

- `git log --oneline -3`: `47ec673 docs(adr): ADR-005 punto 2 …`, `caa4f77 docs(sprint-05): imágenes de
  cierre con GIT_SHA 3cd752a y notify en vivo (V12)`, `3cd752a chore(release): cierre del Sprint 5,
  v0.2.0`. `main` = `a1ad4cb`. `git status`: limpio salvo `docs/ddd/blueprints/sprint-06-exploracion.md`
  (sin seguimiento, ajeno). `git worktree list`: solo el principal.
- Suites (no corridas aquí; cita de `docs/scratch/sprint-05.md`, "V9 · Gates completos", HEAD
  `051751a`, mismo código de `api/` y `web/` que HEAD): api `pytest -m "not perf"` en tres partes
  **7.987 passed, 0 fallidas, 87 skipped (solo Windows: `age`, `pty`, OpenBao real, NTFS, enlaces,
  `mkfifo`), cobertura global 95 %** (umbral 80 %; archivos exigidos entre 85 y 100 %); en Linux con
  OpenBao real 434 passed / 8 skipped de los 15 archivos con saltos; 7 scripts de infraestructura
  "0 fallas" (`test_openbao_infra` 101 ok, `test_deploy_script` 282 ok); web **3.542 pruebas en 194
  archivos, cobertura 97,26 % sentencias / 93,55 % ramas**, lint 0, `tsc` 0, build; `pre-commit
  --all-files` 7/7 tras alinear ruff 0.17.1; `pip-audit` 0; licencias api y web; `NOTICE`; gitleaks;
  `check-image-secrets` ×3; `test_api_image`.
- Corrido en esta fase (HEAD, árbol limpio):
  - `cd api && uv run ruff check .` → `All checks passed!`.
  - `cd api && uv run ruff format --check .` → `739 files already formatted`.
  - `cd api && uv run mypy src` → `Success: no issues found in 192 source files`.
  - `cd web && npx tsc --noEmit` → sin salida, código 0.
  - `cd api && TEST_DATABASE_URL=… uv run pytest --co -q -p no:cacheprovider -m "not perf"` →
    **8.074 recolectadas de 8.105 (31 `perf` deseleccionadas)**; `tests/architecture` → **677**.
- Stack: seis contenedores `healthy` (sección 4); `exec api alembic current` =
  `0020_notifications_indexes (head)`; imágenes con revisión `3cd752a`.
- `.env` local (solo nombres): `WEB_PORT=8180`, `API_PORT=8181`, `DB_PORT=5442`, `DB_TEST_PORT=5443`,
  `TEST_DATABASE_URL=postgresql+asyncpg://apex:apex-test@127.0.0.1:5443/apex_test`,
  `CRYPTO_PROVIDER=local`. `caddy:2-alpine` = 2.11.3 en el host; `bao`, `age`, `gh`, `jq` no están en el
  host; Compose v5.6.1.
- Sondeo de Transit (OpenBao 2.7.2 por digest, `-dev`, contenedor desechable): `ed25519`, `ecdsa-p256`,
  `rsa-2048` → creadas; `ml-dsa` (`parameter_set=65`), `ml-dsa-65`, `mldsa65`, `ml-dsa-44`, `slh-dsa` →
  `400 unknown key type`.

## 7. Bugs, desajustes de configuración y contradicciones documentales

1. OpenBao 2.7.2 sin ML-DSA en Transit; `SIGN_ALG_V01` y `_ALGORITHM["sign"]` fijos en Ed25519;
   `liboqs` ausente del proyecto aunque `CLAUDE.md` lo liste.
2. `signing_specs()` vacío; `bootstrap._create_missing` escribe `local:sign-ed25519` con cualquier
   proveedor; `SIGN_KEY` sin usos; `init-keys --data-class` es un stub; políticas de OpenBao sin
   `sign`/`verify`; `WORKER_CRYPTO_CLASSES` sin `audit.signature` (duplicada en `notify.py`).
3. `core/audit.py` solo puede importar `core/crypto/digest`; nada de `core/crypto/` puede importar
   `core/audit` (`test_core_import_direction`): `sign_latest` y el router de llaves necesitan otra
   ubicación o un puerto.
4. `apex_api` sin privilegios para rotar (`crypto_jobs` solo `SELECT`; `crypto_keys` solo `updated_at`);
   US-145 criterio 7 contra S4B-D63/D140; candado de rotación de sesión en conexión dedicada.
5. Numeración de migraciones del plan (`0040`+) frente a la secuencia real (`0021`+); `0042`, `0045` y
   `0046` innecesarias.
6. Puerto `Reencryptor` inexistente pese a `CLAUDE.md`; una clase sin columnas haría que
   `finish_rotation` cerrara sin recifrar.
7. `python-multipart` y `boto3` ausentes; `S3CompatibleStorage` sin historia; `value_type` del registro
   sin `bytes`; `test_reveal_single_door` e `IMPORTADORES_REALES` cerrados a `members`.
8. `POST /members` con `data_consent: bool` y fecha del servidor; `data_consent_version` siempre `None`;
   `members` sin arista a `settings`; `MemberListQuery` sin `consent`; `SensitiveFieldRevealed`
   inexistente; `MemberDetailOut` sin `photo_attachment_id`.
9. Nginx: `64k` en `/api/` cubre la ruta de subida; `img-src` sin `blob:`; `proxy-api.conf` sobrescribe
   `X-Forwarded-For`/`-Proto` (rate limit roto detrás de Caddy); HSTS en ningún sitio (correcto hasta
   TLS).
10. Sin `infra/caddy/`, perfil `tls`, `compose.tls.yml`; `caddy:2-alpine` sin digest; `deploy.sh`/
    `prod-smoke.sh` sondean el puerto de Nginx; OpenSSL de CI sin ML-KEM.
11. `COOKIE_SECURE`/`ALLOW_INSECURE_COOKIE` ya existen con validador; `LAN_ORIGIN` duplica
    `FRONT_BASE_URL`; `Settings` `extra="forbid"` para `APEX_DOMAIN`/`ACME_*`.
12. `test_adr_docs` fija cinco ADR; el desglose pide uno nuevo; S4B-D47 exige preguntar.
13. Listas cerradas que cambian en el Rojo: `PRIVATE_HELPERS["members"]`, `ALLOWED_EDGES`, `MODULES`,
    `APP_SCHEMAS`, `ENABLED_FEATURES` (10), `DETAIL_KEYS`, `ALERT_CONTEXT_KEYS` (si hacen falta claves),
    `PRIVILEGIOS`/`clasificadas`, `test_sql_literals_constant`, `test_worker_boundaries`,
    `test_audited_tables.EXCLUIDAS`, `test_compose_config` (volúmenes), `test_nginx_conf` (CSP y topes).
14. `DashboardOut.members_without_consent` ya existe: `SPRINT-06.md` lo lista como cambio.
15. `Socio_Form.html` sin campo de foto; `Llaves.html` con "Proveedor activo … sellado: no" sin
    endpoint; `Auditoria.html` promete ML-DSA.
16. `Sprint 5` sin fusionar en `main` (`a1ad4cb`): el PR del Sprint 6 arrastrará ambos si el paso humano
    no ocurre antes.
17. Textos desactualizados: `CLAUDE.md` (`registry.py` con `Reencryptor`, `liboqs-python`), `openbao/
    config.hcl` ("TLS llega con Caddy/EP-20": Caddy no cifra `custody`), `instalar-en-servidor.md`
    ("Caddy en v0.2"), desgloses con `docs/runbooks/`, `cli rotate-key --resume`, "consultar
    capacidades de Transit", `0040`+.

## 8. Riesgos del plan ampliados con lo visto en el código

1. [HIGH] ML-DSA inalcanzable en v0.3 con OpenBao 2.7.2 (riesgo 1 del plan, de MEDIUM a HIGH): la
   promesa "ML-DSA si OpenBao la ofrece" se cumple solo como Ed25519. Mitigación: Q27 reescrita con el
   dato; `algorithm` desde la fila y `SIGNATURE_ALGS` con `ML-DSA-65` listos para cuando exista; la
   verificación con llaves rotadas se prueba con dos llaves Ed25519 (una `decrypt_only`).
2. [HIGH] Permisos del api para rotar (US-145): ampliar grants reabre S4B-D61; no ampliarlos deja la
   rotación fuera del api. Mitigación: C6 con `security-reviewer`; grants por columna y el trigger de
   transiciones; prueba de `test_db_grants`.
3. [HIGH] Rotación de `attachment.sensitive` sin `Reencryptor`: job que cierra sin recifrar.
   Mitigación: 409 `rotation_not_supported` hasta D; `start_rotation` rechaza clases sin columnas ni
   reencryptor; `key_id` en la fila.
4. [HIGH] Rate limit roto detrás de Caddy (riesgo 4 del plan, confirmado en `proxy-api.conf`).
   Mitigación: `real_ip` en Nginx + prueba de dos clientes con cubetas distintas en el smoke.
5. [MEDIUM] `signature_payload` irreversible (riesgo 2): prefijo `apex-audit-sig-v1`, ADR (paso humano)
   y prueba de bytes fijos.
6. [MEDIUM] `POST /audit/verify` pasa a depender del custodio (una llamada por firma): con OpenBao
   sellado la verificación hoy funciona y mañana no (o parcialmente). Mitigación: decisión Q4 (firmas
   "no comprobadas" con bandera o 503), y verificación local con la pública si el proveedor es `local`.
7. [MEDIUM] Variables nuevas y `extra="forbid"` (`APEX_DOMAIN`, `ACME_*`, `STORAGE_PROVIDER`, `S3_*`,
   `USER_*` nuevas): todas en `Settings` + `.env.example` o `NON_API_ENV_VARS` + `.env.ops.example` en
   el mismo slice; smoke de arranque.
8. [MEDIUM] Memoria: cifrar 5 MB en memoria (+33 % base64) por petición con `read_only` y `tmpfs`;
   un recifrado de adjuntos por lotes de 500 **archivos** de hasta 5 MB es mucho más pesado que 500
   filas. Mitigación: lote de adjuntos más pequeño (50) decidido en D.
9. [MEDIUM] `grants.sql` fail-closed: dos tablas y un esquema nuevos detienen `dbsetup` en CI y
   producción si no se clasifican. Mitigación: `test_db_grants` en el Rojo de cada migración.
10. [MEDIUM] `test_adr_docs` y S4B-D47: el ADR de la firma es paso humano; si no llega, el bloque A no
    cierra su DoD ("ADR de auditoría actualizado").
11. [MEDIUM] Licencias: `python-multipart` (Apache-2.0) y `boto3`+`botocore`+`s3transfer`+`jmespath`
    (Apache-2.0/MIT) pasan `check-licenses-api.sh`; `NOTICE` por `notice.sh`; peso de la imagen con
    `boto3` (~70 MB) sin uso en v0.3.
12. [MEDIUM] Objetos huérfanos en `uploads` (riesgo 5): borrado compensatorio y restauración con un
    adjunto; sin job de limpieza en v0.3 (anotar dueño).
13. [LOW] `deploy.sh`/`prod-smoke.sh` con perfil `tls`: sonda nueva con prueba en
    `test_deploy_script.sh`.
14. [LOW] El Sprint 5 sin fusionar: el PR del 6 será grande; mitigación: paso humano antes de la Wave 0.
15. [LOW] `caddy:2-alpine` suelto en el host: se fija por digest; `apex-*:prev-*` sin uso.

## 9. Condiciones para VERDE

Se incorporan al plan de la Fase 1; el plan-critic las verifica.

1. **T-DOC (Wave 0, antes de tocar código):** `SPRINT-06.md`, los cuatro `BREAKDOWN.md` y
   `DECISIONES.md` cierran: (a) la numeración real (`0021_audit_signatures`, `0022_audit_verifications_
   signatures`, `0023_attachments`, `0024` opcional, `0025` opcional de S5-D226; sin `0042`/`0045`/
   `0046`) y la DoD "ciclo `0001` a `00NN`"; (b) Q27 reescrita con el sondeo: Ed25519 en v0.3,
   `algorithm` desde la fila, ML-DSA con dueño (EP-26 o versión de OpenBao verificada); (c) la
   ubicación `core/audit_sign.py` y el puerto `set_audit_writer` (o la excepción a
   `test_core_import_direction`) para el router de llaves; (d) el contrato de US-149 (`data_consent:
   bool` + `data_consent_at` opcional, o `data_consent_at` obligatorio) y el significado de
   `consent_required_from = None`; (e) `retired` solo por `retire-key` (US-145 criterio 7 corregido),
   sin `--resume`; (f) multipart o cuerpo crudo, y `S3CompatibleStorage` fuera de v0.3 o con historia;
   (g) `COOKIE_SECURE` explícito con validador por dominio, `FRONT_BASE_URL` como origen LAN,
   `APEX_DOMAIN` en `Settings`, `ACME_*` en `.env.ops`; (h) el destino de cada deuda v0.3 de la
   sección 2 (subruta JWT S5-D201, TLS en `custody` S5-D63, llavero S5-D272, S5-D226, D207,
   `display_name`, logo, "Exportar rango", `bytearray`, AppRole, `audit.append`, L-4): slice o dueño
   con versión; (i) `CLAUDE.md` (`core/audit_sign.py`, `core/crypto/{router,admin,schemas}.py`,
   `attachments/`, `worker/jobs/sign_audit.py`, `cli_ops/sign_audit.py`, `infra/caddy/`, `Reencryptor`
   solo cuando exista, `liboqs-python` fuera o justificado), `openbao/config.hcl`,
   `instalar-en-servidor.md`, desgloses (`docs/operacion/tls.md`, "capacidades", `SensitiveFieldRevealed`,
   `ROUTES.md`) corregidos; (j) la pregunta humana del ADR (S4B-D47) planteada; (k) US-145 pasa de
   `ARCHITECTURAL_GAP_DETECTED` a READY con el puerto del bloque D y la decisión de grants.
2. **Bloque A (Rojo, firma y políticas):** `registry` con `audit.signature` (`sign=True`);
   `bootstrap._create_missing` escribe `key_ref` y `algorithm` reales por proveedor
   (`local:sign-ed25519` / `apex-sign-audit`); `bus.sign` etiqueta con `llave.algorithm`; `init-keys
   --data-class` real (idempotente; con `openbao` intenta `ml-dsa` y cae a `ed25519` mapeando el 400;
   `crypto_ops` y auditoría; `--as`); políticas `apex-api` (`verify`, `keys` read), `apex-worker`
   (`sign`, `verify`, `keys` read), `apex-tools` (`sign`, `verify`, `keys` read de `apex-sign-audit`)
   con `test_openbao_infra.sh` en verde y el procedimiento de reaplicación en `openbao.md`;
   `WORKER_CRYPTO_CLASSES` y `notify.CRYPTO_CLASSES` con `audit.signature` (o una sola constante);
   `core/audit_sign.py` con `AuditSignature`, `sign_latest` bajo `pg_advisory_xact_lock(4_270_004)` y
   `latest_signature`; `0021`/`0022` con `downgrade` exacto y triggers `ENABLE ALWAYS`;
   `signature_payload`, `needs_signature`, `is_signature_late` puras en `core/audit.py`;
   `worker/jobs/sign_audit.py` con 3 reintentos y las dos alertas; `cli sign-audit`; `verify` con firmas
   (decisión Q4 aplicada) y `VerifyResultOut` ampliado; `GET /audit/signatures/latest`; grants y
   `test_db_grants`; limpieza de `conftest`; `test_sql_literals_constant` con la cuarta llave;
   `test_audited_tables.EXCLUIDAS` con `audit.signatures`; `openapi.json` y `types.ts`; evidencia de
   `--run-once sign_audit` con OpenBao abierto y sellado en el cuaderno.
3. **Bloque B (Rojo, llaves):** `core/crypto/{router,admin,schemas}.py` sin `app.modules` ni
   `app.core.audit` (puerto cableado en `main.py`), registro explícito del router; `Page[...]` con
   `PageParams` y `q` o exclusión anotada; respuestas sin `wrapped_material` (prueba de contrato sobre
   JSON y OpenAPI); `records_count` por `discovery`; `build_cbom` pura con orden estable y algoritmos
   fijos; `export_cbom` auditado `export`; `file_download` en `core/http.py`; `provider_status` o
   `DESIGN-GAP` para la línea de `Llaves.html`; `service.py` bajo 800; `features.test.ts` a once;
   `KeysPage` con `Tabs`, `DataTable`, `StatusTag`, refresco de 5 s solo con `running`.
4. **Bloque C (Rojo, adjuntos):** `MODULES` con `attachments` antes de `members`; `APP_SCHEMAS`,
   `env.py`, `grants.sql` (esquema y tabla) y `test_db_grants`; `attachment.sensitive` en el registro
   (`columns=()`); tercera puerta de descifrado anotada en `test_reveal_single_door` e
   `IMPORTADORES_REALES`; `ALLOWED_EDGES` con `members → attachments` y `members → settings`;
   `PRIVATE_HELPERS["members"]` y la igualdad; `store`/`open`/`list_for_owner`/`current_photo_ids`
   con `detect_mime` y `validate_upload` puras (JPEG, PNG, PDF, ELF, PE), lectura acotada a
   5.242.881 bytes antes de escribir, temporal en `UPLOADS_DIR`, `aad = aad_for(id)`, borrado
   compensatorio; auditoría `download` (N-08) y `__audit_subject__ = "owner_id"`; `members.service`
   con `attach`, `list_attachments`, `consent_required`, `validate_consent`,
   `current_privacy_version` (409 `privacy_version_missing`), filtro `consent=missing`,
   `photo_attachment_id`; cubetas en todas las escrituras; `python-multipart` (si multipart) con
   `check-licenses-api.sh` y `NOTICE`; `STORAGE_PROVIDER` en `Settings` + `.env.example`; Nginx con el
   `location` de subida y `blob:`, `test_nginx_conf.sh` actualizado, prueba de borde 5.242.880 /
   5.242.881 a través de Nginx; `restore_e2e.sh` con un adjunto; `tests/attachments` con "no claro en
   disco"; `openapi.json` y `types.ts`.
5. **Bloque D (Rojo, rotación):** puerto `Reencryptor` en `registry.py` con implementación por
   omisión de columnas y registro desde `attachments.service`; `start_rotation`/`reencrypt_batch`/
   `finish_rotation` por el puerto (funciones < 50 líneas); `POST /crypto/keys/{id}/rotate` 202 con
   tarea `asyncio` que recarga el keyring, sesión propia, `fail_job` ante error y los cinco 409;
   grants del api por columna (o la alternativa decidida) con `test_db_grants`; `rotate_key.py` sin la
   salida 2; `CLAUDE.md` con el puerto; prueba de lectura durante el recifrado (fila vieja y nueva) y
   de reinicio (job `running` reanudado por CLI); lote de adjuntos acotado.
6. **Decisión de seguridad (antes de D):** `security-reviewer` sobre "el api rota llaves" (grants,
   candado de sesión, tarea en proceso) y sobre la descarga de adjuntos (rol, `no-store`, `nosniff`,
   sin URL pública, sin `filename_random` en respuestas), HSTS solo con dominio, ningún material de
   llave en auditoría ni CBOM (los cuatro puntos de la DoD).
7. **Wave 0 (infra TLS y Nginx):** `infra/caddy/Caddyfile` (curvas, protocolos, HSTS, 308,
   `reverse_proxy web:80`, staging por variable, `tls internal` en dev), servicio `caddy` con perfil
   `tls` por digest con fecha y comando, IP fija, volúmenes `caddy_data`/`caddy_config` en la lista
   literal de `test_compose_config.sh`, `compose.tls.yml` que anula `ports` de `web`; Nginx con
   `set_real_ip_from`/`real_ip_header` desde Caddy y `X-Forwarded-Proto` propagado;
   `core/config.py` con `APEX_DOMAIN`, `public_origin`, `validate_origins` y el validador de la cookie
   por dominio (`test_env_example` en verde; `ACME_*` en `NON_API_ENV_VARS` y `.env.ops.example`);
   `tls-smoke.sh` (OpenSSL ≥ 3.5 en contenedor por digest) en `images` de CI con `tls internal` y el
   modo LAN, incluida la prueba del limitador con dos clientes; `deploy.sh`/`prod-smoke.sh` con sonda
   compatible con el perfil y `test_deploy_script.sh`; `NOTICE` (Caddy, Apache-2.0) por `notice.sh`;
   `docs/operacion/tls.md` (LAN → dominio y vuelta, reenvío de puertos, staging, SSL Labs como
   evidencia humana); decisión escrita sobre TLS en `custody`.
8. **Waves 5a y 5b (front):** `SignatureStatus` y `VerifyChainButton` ampliado (cierra su
   `DESIGN-GAP`); `KeysPage` con tres pestañas, `RotateKeyModal` (confirmar deshabilitado hasta
   "ROTAR" exacto, salto a Trabajos) y "Exportar CBOM" por `api.blob`; `PhotoField` (`DESIGN-GAP`:
   sin diseño), `ConsentSection`, `AttachmentsTab` (pestaña habilitada), miniatura con `api.upload`/
   blob y `img-src blob:`; enlace del KPI "Sin consentimiento" a `/socios?consent=missing` y el filtro
   en la lista; `api.upload` en `client.ts` con tiempo propio; tokens sin colores literales; Vitest por
   página; E2E en `tests/e2e/stack/` (firma, rotación, 5.242.880/5.242.881, descarga); `BRECHAS.md`
   §14; `npm run lint && npx tsc --noEmit && npm test && npm run build`.
9. **Validación y cierre:** `--run-once sign_audit` con OpenBao abierto y sellado (reintenta y
   alerta), `verify-audit` con una cadena reescrita (firma inválida señalada) y con una llave `sign`
   `decrypt_only`, rotación desde pantalla sobre `member.phone` con lectura durante el proceso,
   subida y descarga a través de Nginx, smoke `tls internal` + modo LAN, restauración con un adjunto,
   `run-gates.sh` final con cobertura ≥ 80 % incluidos `core/audit_sign.py`, `core/crypto/{router,
   admin}.py`, `modules/attachments/*`, `worker/jobs/sign_audit.py`, `cli_ops/sign_audit.py`;
   `security-reviewer` sobre la DoD; `verify-delivery` con los dos pilares; y el paso humano: PR con
   CI en verde (y el del Sprint 5 antes), merge, `git tag -a v0.3.0`.

## 10. Preguntas abiertas

1. **Q27 con OpenBao 2.7.2:** ¿se acepta Ed25519 como único algoritmo de firma en v0.3 y la rotación a
   ML-DSA queda con dueño (EP-26 o una versión de OpenBao que lo traiga), o se bloquea el bloque A
   hasta subir OpenBao? (Recomendación: aceptar; el sondeo es reproducible en W0.)
2. **Auditoría desde `core/crypto`:** ¿puerto `set_audit_writer` cableado en `main.py` o excepción a
   `test_core_import_direction` para `router.py`? (Recomendación: puerto.)
3. **Rotación desde el api:** ¿grants por columna a `apex_api` sobre `crypto_jobs` y `crypto_keys`
   (reabre S4B-D61) o el api solo encola y rota otro proceso? (Recomendación: grants por columna con
   revisión de seguridad; el worker no monta `uploads`.)
4. **Verificación de firmas con el custodio sellado:** ¿`signatures_checked = 0` con bandera
   `custody_unavailable` y resultado "no comprobado", o 503? (Recomendación: bandera; la cadena se
   sigue verificando sin red.)
5. **Contrato de consentimiento (US-149):** ¿`data_consent_at` obligatorio del cliente o
   `data_consent: bool` + `data_consent_at` opcional ≤ ahora? ¿`consent_required_from = None` significa
   "obligatoria desde v0.3" (desglose) o "sin corte" (código)?
6. **Subida:** ¿multipart con `python-multipart` (6 MB en Nginx) o cuerpo crudo (5 MB exacto, sin
   dependencia)?
7. **S3:** ¿`S3CompatibleStorage` con `boto3` en v0.3 sin historia que lo use, o `STORAGE_PROVIDER`
   solo `local` y S3 con dueño?
8. **Cookie y origen:** ¿se deriva `cookie_secure` de `APEX_DOMAIN` (desglose) o se conserva
   `COOKIE_SECURE` explícito con validador por dominio (código, P7)? ¿`LAN_ORIGIN` o `FRONT_BASE_URL`?
9. **TLS en `custody` (S5-D63, dueño EP-20):** ¿entra (listener TLS de OpenBao con CA interna) o queda
   con dueño v0.4 explícito?
10. **ADR de la firma:** ¿ADR-006 nuevo (cambia `test_adr_docs`) o ampliación de ADR-004? Paso humano
    (S4B-D47).
11. **`init-keys --data-class`:** ¿comando obligatorio antes de firmar o basta `ensure_keys` del api
    (que crearía la fila al arrancar sin auditoría explícita)?
12. **Subruta `keys` para la llave JWT del worker (S5-D201, "EP-17"):** ¿entra en el sprint (migrar
    volúmenes e `init-keys`) o nuevo dueño?
13. **Línea "Proveedor activo … sellado: no" de `Llaves.html`:** ¿`provider_status` en
    `GET /crypto/keys` o `DESIGN-GAP`?
14. **`SensitiveFieldRevealed`:** ¿se crea el evento (sin suscriptor) o se deja solo la fila `download`?
15. **Fusión del Sprint 5:** ¿se abre y fusiona su PR antes de la Wave 0 del 6?

## Riesgos residuales (no bloquean)

- Las 87 pruebas saltadas en Windows (`age`, `pty`, OpenBao real, NTFS, enlaces, `mkfifo`) siguen
  corriendo en el contenedor Linux y en CI; las nuevas de firma contra OpenBao se suman al marcador
  `openbao` (CI exige 0 saltos en esos archivos, S5-D264).
- `bao` no existe en el host: toda operación de OpenBao (políticas nuevas, `init-keys` con Transit)
  es `docker compose exec openbao bao ...` o `run --rm tools`.
- `--reload` con polling reinicia el api a mitad de un E2E del proyecto `stack`; no editar `src/`
  durante la corrida.
- Con el perfil `tls`, cualquier monitor externo que sondee `http://` verá 308; el runbook lo dice.
- `GET /health` sigue respondiendo 503 con OpenBao sellado; `sign_audit` a las 07:00 fallará con
  alerta tras cada reinicio del servidor hasta desellar (RUNBOOK §13).
- Los triggers `crypto_*` de `0003` siguen en `'O'` (residual desde 4B); `0021` a `0023` no los tocan.
- `apex-api:prev-*` y `caddy:2-alpine` sueltos en el host no interfieren.
