# Sprint 6 · v0.3: auditoría firmada, llaves, adjuntos y TLS híbrido

> Corregido en S6 (S6-W0-1): este documento sigue el plan aprobado `docs/ddd/blueprints/sprint-06-plan.md` y las decisiones S6-D1 a S6-D82 de `docs/ddd/DECISIONES.md` (sección «Sprint 6 · decisiones de implementación»). Donde el texto original de la fase de sprints decía otra cosa, manda el plan; las correcciones están marcadas.

- Versión: v0.3.
- Épicas:
  - EP-17: auditoría firmada;
  - EP-18: administración de llaves;
  - EP-19: adjuntos y autorización de tratamiento de datos;
  - EP-20: acceso cifrado con TLS híbrido.
- Tamaño: 14 historias, 53 puntos y 217 h relativas.
  - EP-17: 54 h.
  - EP-18: 59 h.
  - EP-19: 75 h.
  - EP-20: 29 h.
- Nivel de detalle: slices en orden de ejecución (S6-D56), con pasos numerados en el plan.
- Historias del sprint: US-140, US-141, US-142, US-143, US-144, US-145, US-146, US-147, US-148, US-149, US-150, US-151, US-152, US-153.

## Objetivo

Que la integridad y la custodia criptográfica se puedan demostrar ante un tercero:
- la cadena de auditoría se firma cada noche con la llave `audit.signature`, **Ed25519 en v0.3** (S6-D51: Transit de OpenBao 2.7.2 no ofrece ML-DSA; `ML-DSA-65` queda en EP-26 sin migración);
- el admin ve el inventario de llaves, la bitácora y los trabajos, rota llaves de cifrado desde pantalla (la llave anterior queda en `decrypt_only` al terminar; `retired` es solo de `retire-key`) y exporta el CBOM (Q26);
- la foto y la autorización de tratamiento de datos del socio se guardan (la autorización cifrada, la foto no, ADR-007) y se descargan con auditoría (la foto sin fila por vista);
- el acceso desde fuera del box pasa por Caddy con TLS 1.3 y el grupo híbrido `x25519mlkem768`.

## Demo al final del sprint

1. **Firma nocturna de la cadena** (ensayo con overlay OpenBao, puerto 8280).
   - El job `sign_audit` firma a las 07:00 y deja una fila en `audit.signatures`.
   - La pantalla Auditoría muestra el estado de la firma.
   - Si la firma lleva más de 48 h sin hacerse, el estado pasa a "Firma atrasada" y llega una alerta interna (N-32, N-34). Se simula con `--date --simulate` sobre `apex_sim`, nunca en el ensayo (S6-D71).
   - "Verificar" comprueba la cadena y además las firmas con la clave pública guardada en `crypto_keys`, sin llamar al custodio (S6-D62, S6-D81).
2. **Pantalla Llaves** (ensayo con overlay OpenBao).
   - Muestra el inventario, sin material de llave y con `records_count` por el registro; «Proveedor activo» sale de `crypto_keys` y el estado de `recovery.current_state()`.
   - Muestra la bitácora de `crypto_ops` y los jobs con su porcentaje de avance.
   - "Rotar" sobre `member.document` pide confirmación y lanza el recifrado; al terminar la llave anterior queda `decrypt_only`.
   - "Exportar CBOM" descarga el JSON (sin referencias de llaves `sign`) y queda auditado como `export`.
3. **Foto y autorización de datos** (ensayo, a través de Nginx).
   - Subir la foto del socio por cuerpo crudo con `?kind=photo`: se valida por bytes mágicos; 5.242.880 bytes → 201, 5.242.881 → 413 del api, 6 MiB o más → 413 de Nginx (con Nginx a 6 MB solo en esa ruta).
   - Registrar la autorización de datos (`kind=consent`): fija `data_consent_at` si estaba nulo y copia la versión vigente de la política.
   - La descarga del archivo de autorización queda auditada como `download`; la foto no deja fila por vista (ADR-007).
   - Inicio muestra "socios sin autorización registrada" (Q16) con enlace a `/socios?consent=missing`.
4. **TLS híbrido** (ensayo con `$DCET`).
   - Con el perfil `tls`, `APEX_DOMAIN=apex.localhost:8443` y la CA interna de Caddy, `openssl s_client` negocia el grupo `X25519MLKEM768` (`scripts/ci/tls-smoke.sh`).
   - Hay redirección 308 y HSTS solo con dominio, escalonado desde `max-age=300` sin `includeSubDomains`.
   - En modo LAN no hay HSTS y la cookie no lleva `Secure`.
   - La renovación ACME real y SSL Labs son pasos humanos con dominio público (`docs/operacion/tls.md`).

## Dependencias de sprints anteriores

- **Sprint 5:**
  - US-133 y US-134 (Transit y `OpenBaoProvider.sign` y `verify`);
  - US-136 (503 `crypto_unavailable`);
  - US-126 (`core/alerts.py`, G-08).
- **Sprints 4A y 4B:**
  - US-104 y US-105 (verificación y `0013`);
  - US-113 (worker);
  - US-030 (rotación por CLI y `reencrypt_batch`);
  - US-114 (el backup incluye `uploads`);
  - US-119 (ADR de auditoría).
- **Sprint 3:** US-073 y US-075 (ficha y edición).
- **Sprint 2:**
  - US-057 (`current_privacy_version()`, `consent_required_from`);
  - US-069 (alta con `warnings`).
- **Sprint 1:**
  - US-023 (`init-keys --data-class`);
  - US-024 y US-027 (firma en el bus);
  - US-038 (CSP).

## Slices en orden de ejecución (S6-D56)

Wave 0: W0-1 (línea base, T-DOC, decisiones, ADR-006 y ADR-007, dependencias y licencias), W0-5 (`Settings`, cubetas y entorno por servicio), W0-2 (infraestructura y CLI; el ensayo `apex-ensayo` nace de cero aquí y vive hasta V12), W0-3 (políticas de OpenBao), W0-4 (Caddy y perfil `tls`).

1. **Bloque A · Auditoría firmada (EP-17).**
   - A1 · US-140: `audit.signatures` (`0021`), `core/audit_sign.py`, payload `apex-audit-sig-v1`, Ed25519, verificación incremental antes de firmar (H-1).
   - A2 · US-141: job `sign_audit` con reintentos dentro de la corrida, alerta `audit_chain_broken`, keyring por job, `sign-audit` y `rotate-key audit.signature --provider`.
   - A3 · US-142: verificación con la clave pública (sin custodio), `0022` y estado en pantalla.
2. **Bloque B · Llaves, primera parte (EP-18).**
   - B1 · US-143: inventario de llaves, con el router en `core/crypto/router.py` y `__init__.py` vacío.
   - B2 · US-144: bitácora y trabajos.
   - B3 · US-146: exportar CBOM (`cbom-export`).
3. **Bloque C · Adjuntos (EP-19).**
   - C1 · US-147: almacenamiento seguro (`0023`, esquema `attachments`); `StorageProvider` con dos adaptadores (S3 apagado); clase `attachment.sensitive` por el bus; `attachments.key_id`.
   - C2 · US-148: foto del socio.
   - C3 · US-149: autorización de datos (`consent_required_from` nulo no exige; subir la autorización fija `data_consent_at`).
   - C4 · US-150: pestaña Adjuntos y descarga auditada (coach solo foto).
   - C5 · US-151: socios sin autorización.
4. **Bloque D · Rotación desde pantalla (EP-18, cierre).**
   - R1 · US-145: rotar desde la pantalla (`0024`), con el puerto `Reencryptor` registrado por `attachments`; va después de C1.
   - Desde aquí, rotar `attachment.sensitive` deja de responder 409 `rotation_not_supported`.
5. **Bloque E · TLS (EP-20).**
   - E1 · US-153: redirección, HSTS escalonado y modo LAN, con `public_origin` y `validate_origins` puras (US-152 se cierra en W0-4).

Front (worktree `sprint-06-front`, tras C5): F1, F3, F4, F5, F2. Validación: V1 a V12 (cuatro corridas de `run-gates.sh`, en A3, C5, E1 y V10).

## Migraciones que aplica

Cuatro, en orden ascendente (S6-D39; las `0040` a `0051` del texto original sobran):
- `0021` firmas de auditoría (US-140): `audit.signatures` append-only y `crypto_keys.public_key`.
- `0022` verificaciones con firmas (US-142): columnas nulas en `audit.verifications`.
- `0023` adjuntos (US-147): esquema `attachments`, con `key_id` (G-09).
- `0024` guarda de `crypto_keys` por rol (US-145): `active → decrypt_only` acotado para `apex_api` y guardas de `crypto_jobs`.

EP-20 no tiene migraciones; US-143, US-144 y US-151 tampoco (el índice de `crypto_ops` existe, el KPI de socios sin autorización existe desde S5-D240).

## Endpoints que expone

Nueve endpoints nuevos; `GET /api/v1/dashboard` y `GET /api/v1/health` no cambian de forma.
- **Auditoría:** `GET /api/v1/audit/signatures/latest`.
  - `POST /api/v1/audit/verify` y `GET /api/v1/audit/verify/last` amplían su respuesta con las firmas (campos opcionales).
- **Llaves (admin):**
  - `GET /api/v1/crypto/keys`, `GET /api/v1/crypto/ops` y `GET /api/v1/crypto/jobs`;
  - `POST /api/v1/crypto/keys/{id}/rotate`;
  - `GET /api/v1/crypto/cbom`.
- **Adjuntos:**
  - `POST /api/v1/members/{id}/attachments?kind=photo|consent|other` con el archivo como cuerpo crudo (sin multipart, S6-D59);
  - `GET /api/v1/members/{id}/attachments`;
  - `GET /api/v1/attachments/{id}`.
- **Cambios en endpoints de v0.1 y v0.2:**
  - `POST /api/v1/members` conserva su contrato (`data_consent: bool`); la obligación nace de `consent_required_from` (S6-D46);
  - `GET /api/v1/members?consent=missing` (filtro nuevo);
  - `GET /api/v1/dashboard` ya trae `members_without_consent` (sin cambio de contrato).

## Tests de arquitectura que deben pasar

- Toda la suite anterior.
- `test_core_import_direction.py` (la prueba `test_core_independent.py` del desglose de EP-18 se consolidó aquí). Comprueba tres cosas:
  - el router de `core/crypto` no importa módulos;
  - `records_count` usa el registro, no `models` ajenos;
  - `core/crypto/__init__.py` está vacío, sin ciclo con `core/audit`.
- `test_no_plaintext_at_rest.py`, ampliada a `attachment.sensitive`.
- `test_audited_tables.py`: `crypto.crypto_keys` y `attachments.attachments` entran en `AUDITABLE_TABLES`; la auditoría de una rotación es explícita y sin material (`crypto_keys` no es `__audited__`).
- `test_every_route_has_role.py` sobre las rutas de `crypto` y de `attachments`.
- `test_third_party_confinement.py`: `python-multipart` prohibido por nombre; `boto3` solo en `storage/s3.py`.

## Riesgos y mitigación

1. [MEDIUM] OpenBao sin ML-DSA en Transit.
   - Mitigación: Ed25519 único en v0.3 (S6-D51); `ML-DSA-65` llega con EP-26 como llave nueva. Se documenta en ADR-006.
2. [MEDIUM] `signature_payload` es irreversible con datos.
   - Mitigación: prefijo de versión, `payload_version` por fila y ADR-006 con vector.
3. [MEDIUM] Caddy sin `x25519mlkem768`.
   - Mitigación: Caddy 2.11.3 por digest y verificado en `tls-smoke.sh`.
4. [MEDIUM] Si el limitador cuenta la IP de Caddy, bloquea a todos a la vez.
   - Mitigación: `real_ip` de Nginx restaurado desde Caddy y prueba con dos clientes de IP distinta (S6-D64).
5. [MEDIUM] Objetos huérfanos en el storage, o `uploads` fuera del backup.
   - Mitigación: borrado compensatorio, `attachments-check` y la prueba de restauración con un adjunto.

## Definición de hecho del sprint

- Definición de hecho común del README.
- E2E:
  - estado de la firma;
  - rotación desde pantalla;
  - subida de foto, con pruebas de borde de 5.242.880 y 5.242.881 bytes a través de Nginx;
  - descarga de la autorización.
- Smoke con el perfil `tls`, usando la CA interna y `apex.localhost`, más el smoke en modo LAN.
- `restore_e2e.sh` con un adjunto: la restauración devuelve el archivo y `attachments-check` no halla huérfanos.
- `docker compose run --rm worker python -m app.worker.main --run-once sign_audit`, con OpenBao abierto y con OpenBao sellado (debe reintentar y alertar).
- Seguridad, revisada por `security-reviewer`:
  - adjuntos servidos solo por el api, con rol, `no-store` y `nosniff`;
  - validación por bytes mágicos;
  - HSTS solo con dominio y escalonado (`max-age=300` inicial, sin `includeSubDomains`);
  - ningún material de llave en la auditoría ni en el CBOM;
  - el api no firma (política de Transit) y la rotación deja la llave anterior en `decrypt_only`;
  - la foto no deja fila por vista (ADR-007).
- Ed25519 como algoritmo de la firma en v0.3.
- `verify-delivery`.
