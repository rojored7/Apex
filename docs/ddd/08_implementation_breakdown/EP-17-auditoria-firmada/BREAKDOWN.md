# EP-17 · Auditoría firmada post-cuántica — desglose técnico de épica

- **Épica:** `docs/ddd/06_epics/EP-17-auditoria-firmada.md`
- **Versión:** v0.3
- **Historias:** US-140 a US-142 (3 historias, 13 puntos)

## Resumen

La épica sella la cadena de auditoría de v0.1 con una firma diaria hecha fuera del proceso del API (OpenBao Transit) y amplía la verificación para que detecte una reescritura completa de la cadena. Son tres piezas, en este orden:

- US-140 deja la tabla append-only `audit.signatures`, la función pura `signature_payload` y la llave `sign` de la clase `audit.signature` registrada con `cli init-keys --data-class audit.signature`.
- US-141 agrega el job `sign_audit` al worker (07:00 Bogotá, con reintentos) y el comando `cli sign-audit`.
- US-142 amplía `audit.service.verify()` y `cli verify-audit` para comprobar cada firma contra el hash de la cadena, persiste el resultado de firmas en `audit.verifications` y expone `GET /audit/signatures/latest` con el bloque de estado en la pantalla `Auditoria`.

Ningún código fuera de `core/crypto` toca primitivas: la firma y la verificación pasan siempre por `core.crypto.bus.sign` y `core.crypto.bus.verify`, y el algoritmo lo decide la llave registrada (Q27).

## Correcciones aplicadas por DECISIONES.md

- La épica dice "firma con ML-DSA desde OpenBao 2.7" y su riesgo deja abierto si se bloquea → se firma con el verbo `sign` del bus y la `data_class` `audit.signature`; si Transit no ofrece ML-DSA al crear la llave, la llave nace `Ed25519` y se rota a `ML-DSA-65` después; las firmas viejas se verifican con su `key_id`. No bloquea: corregido por DECISIONES Q27.
- La épica dice "cada noche" → la firma corre a las 07:00 America/Bogota con el resto del worker, con 3 reintentos de espera creciente, y la pantalla marca "Firma atrasada" a las 48 h: corregido por DECISIONES N-32 (acepta los supuestos de US-141 y US-142).
- US-141 dice que "avisar" es solo log y pantalla → además del log, la bitácora y la pantalla, el fallo definitivo del job y la firma atrasada (más de 48 h) se envían como alerta interna del equipo por `core/alerts.py` (canal Telegram del gimnasio), degradable si el canal no está configurado: corregido por DECISIONES N-34.
- US-104 (v0.1) suponía que la última verificación se lee de la entrada `verify` de la auditoría → la última verificación vive en la tabla append-only `audit.verifications` (migración `0013`), y US-142 le agrega las columnas de firmas: corregido por DECISIONES N-30.
- El SHA-256 de la cadena y cualquier hash de apoyo se piden a `core.crypto.bus.digest`, nunca con `hashlib` en `core/audit.py`: corregido por DECISIONES N-06.
- El job y el CLI escriben `created_by` y `user_id` con `SYSTEM_USER_ID`; `cli sign-audit` y `cli init-keys` aceptan `--as <email>`: corregido por DECISIONES N-15.
- La firma del bus tiene el formato `apx1.<key_id>.<alg>.<sig_b64url>`; la tabla guarda además `key_id` y `algorithm` desnormalizados para la pantalla y el CBOM: aceptado por DECISIONES N-04.

## Validación contra el dominio y la arquitectura

- **Dominio:** `AuditSignature` (`through_seq`, `hash`, `signature`, `key_id`, `signed_at`) es una entidad append-only del contexto Audit (`02_domain_model.md` 2.12). La columna `algorithm` que agrega US-140 es desnormalización de lo que ya va en el blob de firma; no cambia invariantes. RN-14 (auditoría y llaves nunca se borran) y RN-16 (cadena) se refuerzan con la firma. No hay eventos de dominio nuevos; la verificación se registra como acción `verify`.
- **Funciones puras:** `core.audit.signature_payload(through_seq, hash) -> bytes` (canónica y versionada: prefijo `apex-audit-sig-v1`), `core.audit.needs_signature(last_seq, last_signed_seq) -> bool`, `modules.audit.service.verify_result(chain_ok, broken_seq, signatures_checked, first_bad_signature_seq) -> VerifyResult`, `core.audit.is_signature_late(last_signed_at, now, threshold_h=48) -> bool`.
- **Ubicación:** el modelo de `audit.signatures` vive en `core/audit.py` junto a `audit_log` y `verifications` (el módulo `audit` no tiene `models.py`, `05_service_design.md` sección 2). La lógica de firma (`sign_latest`) vive en `core/audit.py` porque la usan el worker y el CLI; la lectura y la verificación ampliada viven en `modules/audit/service.py`.
- **Dirección de dependencias:** `core/audit` → `core/crypto/bus` (ya establecida por N-06); `core/crypto` nunca importa `core/audit` desde `bus.py`. `worker/jobs/sign_audit.py` y `cli.py` → `core/audit`. Sin imports de `models` ajenos.
- **Bus y lint:** ningún archivo de esta épica fuera de `core/crypto` importa `cryptography`, `oqs`, `hashlib`, `hmac` ni `jwt`; la firma la hace OpenBao Transit dentro de `OpenBaoProvider.sign` (US-134). `test_banned_imports.py` debe seguir verde.
- **Rol:** `POST /audit/verify` y `GET /audit/signatures/latest` con `require_role("admin")`; coach 403.
- **Concurrencia:** `pg_advisory_xact_lock` con una llave fija de la firma más índice único en `through_seq` evitan dos firmas del mismo tramo (job y CLI simultáneos).
- **Auditoría:** `audit.signatures` no es `__audited__` (sería auditar la auditoría); la creación de la llave queda en `crypto_ops` y en `audit_log` por el flujo de `init-keys`.

## Tablas y migraciones

- `0040_audit_signatures` (US-140): tabla `audit.signatures` con `id` UUID (asignado en Python), `through_seq` bigint NOT NULL con índice único, `hash` text NOT NULL, `signature` text NOT NULL, `key_id` UUID NOT NULL (FK lógica a `crypto.crypto_keys`, sin FK física entre esquemas), `algorithm` text NOT NULL con CHECK (`Ed25519`, `ML-DSA-65`), `signed_at` TIMESTAMPTZ NOT NULL, `created_at`, `updated_at`, `created_by`; índice `signed_at DESC`; función `audit.forbid_signature_mutation()` y trigger `BEFORE UPDATE OR DELETE` que lanza excepción. Downgrade: borra trigger, función y tabla (solo en desarrollo; documentado).
- `0041_audit_verifications_signatures` (US-142): `ALTER TABLE audit.verifications` agrega columnas nulas `signatures_checked` int, `signatures_valid` int, `first_invalid_signature_seq` bigint, `last_valid_signature_seq` bigint, `last_valid_signature_at` TIMESTAMPTZ, `last_valid_signature_algorithm` text. Son nulas para no tocar filas previas (sin paso de llenado; las verificaciones viejas quedan sin datos de firma). El trigger append-only de `0013` se mantiene.
- Sin cambios en `crypto.crypto_keys`: su CHECK de `algorithm` ya admite `Ed25519` y `ML-DSA-65` y `purpose` admite `sign` (US-024). Verificarlo al implementar; si faltara `ML-DSA-65`, `0042_crypto_keys_mldsa_check` dentro del rango.

## Services y eventos

- `core/audit.py`:
  - `signature_payload(through_seq: int, hash: str) -> bytes` (pura; documentada en `docs/adr/ADR-00x-auditoria.md`; cambiarla rompe la verificación).
  - `needs_signature(last_seq: int | None, last_signed_seq: int | None) -> bool` (pura).
  - `is_signature_late(last_signed_at, now, threshold_h=48) -> bool` (pura).
  - `async sign_latest(session, *, by: UUID = SYSTEM_USER_ID) -> SignOutcome` — toma `pg_advisory_xact_lock`, lee el último `seq`/`hash` de `audit_log` y el mayor `through_seq` firmado; si `needs_signature`, llama `bus.sign("audit.signature", signature_payload(...))`, parsea `key_id` y `alg` del blob de firma y guarda la fila; devuelve `signed` | `nothing_new`.
- `modules/audit/service.py`:
  - `verify(by)` ampliado: además de `verify_chain` (US-104), recorre `audit.signatures` en orden de `through_seq`, recalcula `signature_payload(through_seq, hash_de_la_cadena_en_ese_seq)` y llama `bus.verify("audit.signature", payload, signature)`; la verificación usa la llave del `key_id` aunque esté `decrypt_only` o rotada (US-027).
  - `verify_result(...) -> VerifyResult` (pura): íntegra solo si cadena ok y todas las firmas válidas.
  - `latest_signature() -> LatestSignatureOut` — última firma registrada (de `audit.signatures`) y última firma válida conocida (de la última fila de `audit.verifications`), más `is_late`.
  - Persistencia del resultado en `audit.verifications` y entrada `verify` en `audit_log` con el resumen.
- `core/crypto/service.py` / `cli.py`: `init_keys(data_class="audit.signature")` idempotente; consulta capacidades de Transit (`OpenBaoProvider.key_info` / tipos soportados) y crea `ml-dsa-65` o `ed25519`; avisa por consola si cayó a Ed25519 (Q27).
- `worker/jobs/sign_audit.py`: envuelve `sign_latest` con 3 reintentos (espera 2, 4 y 8 s) ante `CryptoUnavailable`; al fallar definitivamente registra log JSON sin datos sensibles, deja `crypto_ops` con `result=error` (lo hace el bus) y llama `core.alerts` (N-34). Tras firmar o al no haber nada nuevo, si `is_signature_late` sigue verdadero, también alerta.
- Eventos: ninguno emitido ni consumido.

## Endpoints

- `POST /api/v1/audit/verify` — roles: admin
- `GET /api/v1/audit/verify/last` — roles: admin
- `GET /api/v1/audit/signatures/latest` — roles: admin

## Componentes de front

- `web/src/features/system/components/SignatureStatus.tsx`: bloque junto al botón "Verificar cadena" con "Última firma válida: seq N, fecha (hora de Bogotá), algoritmo" y `StatusTag` con texto (Íntegra, Alterada, Firma atrasada).
- `web/src/features/system/api.ts`: hook `useLatestSignature()` (TanStack Query) y ampliación del tipo de `useVerifyChain()` con los campos de firmas.
- `web/src/features/system/components/VerifyChainButton.tsx` (de US-104): muestra `signatures_checked`, `signatures_valid` y `first_invalid_signature_seq` con enlace al detalle.
- Pruebas Vitest de los tres estados del bloque y del resultado ampliado; sin colores literales (tokens).

## Worker, CLI e infraestructura

- Job `sign_audit` registrado en `worker/jobs/__init__.py`, 07:00 America/Bogota, con `worker.job_runs` para no repetirlo tras reinicio (US-113).
- `cli init-keys --data-class audit.signature [--as <email>]` (depende de que US-023 acepte `--data-class`, agregado en consolidación).
- `cli sign-audit [--as <email>]`: código 0 al firmar o si no hay nada nuevo; distinto de 0 si falla.
- `cli verify-audit`: imprime el resultado con firmas y sale distinto de 0 si la cadena o una firma no es válida.
- OpenBao de `compose.dev.yml` con Transit; prueba en dos modos (con y sin ML-DSA simulando la respuesta de capacidades).

## Dependencias

- EP-11: US-015 (tabla y cadena), US-104 (verificar desde pantalla), US-105 (verificar por CLI), migración `0013_audit_verifications` (N-30).
- EP-02: US-023 (`cli init-keys --data-class`), US-024 (`crypto_keys`, `crypto_ops`), US-027 (`sign`/`verify` en el bus), US-029 (bitácora).
- EP-15: US-133 (servicio OpenBao con Transit), US-134 (`OpenBaoProvider.sign`/`verify`), US-136 (503 `crypto_unavailable` con OpenBao sellado).
- EP-13: US-113 (worker y `job_runs`), US-119 (ADR de auditoría donde se documenta `signature_payload`).
- EP-14: US-126 corregido por N-34 (`core/alerts.py` con el canal interno del equipo).
- EP-06: US-061 (`PanelLayout`) y `StatusTag` (US-010) para el bloque de estado.

## Riesgos

- Soporte de ML-DSA en Transit: si la versión de OpenBao no lo ofrece, la llave nace Ed25519 (Q27); Transit no cambia el tipo de una llave existente al rotar, así que la "rotación" a ML-DSA-65 es una llave nueva con otro `key_id` — mitigación: documentarlo en el runbook y probar que una firma Ed25519 vieja sigue verificando tras crear la llave ML-DSA.
- OpenBao sellado a las 07:00: se pierde la firma del día — mitigación: 3 reintentos, alerta N-34 y la firma del día siguiente cubre hasta el último `seq` (sin pérdida de cobertura).
- `signature_payload` es irreversible con datos: cambiarla invalida todas las firmas — mitigación: prefijo de versión en el payload y ADR.
- Verificación de muchas firmas contra Transit (una llamada HTTP por firma) puede ser lenta con años de firmas — mitigación: con una firma diaria son unas 365 por año; si crece, verificar por lotes en segundo plano como US-104.
- `core/alerts.py` depende de que EP-14 lo cree según N-34; si no existe al implementar, el job solo registra log y estado en pantalla — mitigación: dependencia explícita y prueba con un doble.
- Riesgo de dependencia entre `core/audit` y `core/crypto`: si `core/crypto/__init__.py` reexporta `service.py` (que escribe auditoría) se forma un ciclo de import — mitigación: `__init__.py` vacío y test de importación.
- Front condicionado a D1.

## Estado y estimación por historia

- US-140 · Registro de firmas de auditoría — **READY** — 12 h — Tabla append-only `0040`, `signature_payload` pura y llave `audit.signature` con caída a Ed25519 resuelta por Q27.
- US-141 · Firma nocturna de la cadena — **READY** — 20 h — Job a las 07:00 con 3 reintentos, bloqueo de aviso y alerta interna; hora, reintentos y umbral fijados por N-32 y alerta por N-34.
- US-142 · Verificación con firmas y estado en pantalla — **READY** — 22 h — Verificación de firmas por el bus, columnas nuevas en `audit.verifications` (`0041`, N-30) y bloque de estado con "Firma atrasada" a las 48 h.

## Total de la épica

- **Total: 54 h**
