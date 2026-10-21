# Sprint 6 · v0.3: auditoría firmada, llaves, adjuntos y TLS híbrido

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
- Nivel de detalle: bloques en orden de ejecución, sin slices. Se refina al llegar.
- Historias del sprint: US-140, US-141, US-142, US-143, US-144, US-145, US-146, US-147, US-148, US-149, US-150, US-151, US-152, US-153.

## Objetivo

Que la integridad y la custodia criptográfica se puedan demostrar ante un tercero:
- la cadena de auditoría se firma cada noche con la llave `audit.signature`, ML-DSA si OpenBao la ofrece y Ed25519 si no (Q27);
- el admin ve el inventario de llaves, la bitácora y los trabajos, rota llaves de cifrado desde pantalla y exporta el CBOM (Q26);
- la foto y la autorización de tratamiento de datos del socio se guardan cifradas y se descargan con auditoría;
- el acceso desde fuera del box pasa por Caddy con TLS 1.3 y el grupo híbrido `x25519mlkem768`.

## Demo al final del sprint

1. **Firma nocturna de la cadena.**
   - El job `sign_audit` firma a las 07:00 y deja una fila en `audit_signatures`.
   - La pantalla Auditoría muestra el estado de la firma.
   - Si la firma lleva más de 48 h sin hacerse, el estado pasa a "Firma atrasada" y llega una alerta interna (N-32, N-34).
   - "Verificar" comprueba la cadena y además las firmas.
2. **Pantalla Llaves.**
   - Muestra el inventario, sin material de llave y con `records_count`.
   - Muestra la bitácora de `crypto_ops` y los jobs con su porcentaje de avance.
   - "Rotar" sobre `member.document` pide confirmación y lanza el recifrado.
   - "Exportar CBOM" descarga el JSON y queda auditado como `export`.
3. **Foto y autorización de datos.**
   - Subir la foto del socio: se valida por bytes mágicos y se rechaza por encima de 5 MB (con Nginx a 6 MB solo en esa ruta).
   - Registrar la autorización de datos con la versión vigente de la política.
   - La descarga del archivo de autorización queda auditada como `download`.
   - Inicio muestra "socios sin autorización registrada" (Q16).
4. **TLS híbrido.**
   - Con el perfil `tls` y un dominio, `openssl s_client` negocia el grupo `X25519MLKEM768`.
   - Hay redirección 308 y HSTS solo con dominio.
   - En modo LAN no hay HSTS y la cookie no lleva `Secure`.

## Dependencias de sprints anteriores

- **Sprint 5:**
  - US-133 y US-134 (Transit y `OpenBaoProvider.sign` y `verify`);
  - US-136 (503 `crypto_unavailable`);
  - US-126 (`core/alerts.py`, G-08).
- **Sprint 4:**
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

## Historias en orden de ejecución (por bloques)

1. **Bloque A · Auditoría firmada (EP-17).**
   - US-140: registro de firmas y `signature_payload` con prefijo de versión.
   - US-141: firma nocturna con 3 reintentos y alerta.
   - US-142: verificación con firmas y estado en pantalla.
2. **Bloque B · Llaves, primera parte (EP-18).**
   - US-143: inventario de llaves, con el router en `core/crypto/router.py` y `__init__.py` vacío.
   - US-144: bitácora y trabajos.
   - US-146: exportar CBOM.
3. **Bloque C · Adjuntos (EP-19).**
   - US-147: almacenamiento seguro.
     - `StorageProvider` con dos adaptadores.
     - Clase `attachment.sensitive` por el bus.
     - `attachments.key_id`.
   - US-148: foto del socio.
   - US-149: autorización de datos.
     - Obligatoria desde `consent_required_from`.
     - Para socios anteriores, autorización tardía por `PATCH`.
   - US-150: pestaña Adjuntos y descarga auditada.
   - US-151: socios sin autorización.
4. **Bloque D · Rotación desde pantalla (EP-18, cierre).**
   - US-145: rotar desde la pantalla, con el puerto `Reencryptor` de G-09 registrado por `attachments`.
   - Va después de US-147, que registra la `data_class` `attachment.sensitive`.
   - Desde aquí, rotar esa clase deja de responder 409 `rotation_not_supported`.
5. **Bloque E · TLS (EP-20).**
   - US-152: Caddy con el perfil `tls`, fijado por digest a la versión 2.10 o superior.
   - US-153: redirección, HSTS y modo LAN, con `public_origin` y `validate_origins` puras.

Waves:
- **Wave 0:**
  - Caddy y su perfil `tls`, con los volúmenes persistentes;
  - excepción de 6 MB en Nginx solo en la ruta de subida;
  - volumen `uploads` dentro del backup.
- **Waves 3a y 3b:** los bloques A a D. El bloque E es casi todo de infraestructura y se cierra en Wave 0 y en la validación.
- **Waves 5a y 5b:**
  - bloque de estado de la firma en Auditoría;
  - pantalla Llaves;
  - foto y autorización en `Socio_Form`;
  - pestaña Adjuntos;
  - tarjeta de Inicio.

## Migraciones que aplica

En orden ascendente:
- `0040_audit_signatures` (US-140).
- `0041_audit_verifications_signatures` (US-142).
- `0042_crypto_keys_mldsa_check` (EP-17). Extiende la guarda de `crypto_keys`.
- `0045_crypto_ops_indexes` (US-144), si faltan índices.
- `0046_crypto_jobs_one_running` (EP-18).
- `0050_attachments` (US-147), con `attachments.key_id` (G-09).
- `0051_members_consent_missing_idx` (US-151).

EP-20 no tiene migraciones.

## Endpoints que expone

- **Auditoría:** `GET /api/v1/audit/signatures/latest`.
  - `POST /api/v1/audit/verify` y `GET /api/v1/audit/verify/last` amplían su respuesta con las firmas.
- **Llaves (admin):**
  - `GET /api/v1/crypto/keys`, `GET /api/v1/crypto/ops` y `GET /api/v1/crypto/jobs`;
  - `POST /api/v1/crypto/keys/{id}/rotate`;
  - `GET /api/v1/crypto/cbom`.
- **Adjuntos:**
  - `POST /api/v1/members/{id}/attachments` y `GET /api/v1/members/{id}/attachments`;
  - `GET /api/v1/attachments/{id}`.
- **Cambios en endpoints de v0.1:**
  - `POST /api/v1/members` y `PATCH /api/v1/members/{id}` agregan la autorización;
  - `GET /api/v1/members?consent=missing`;
  - `GET /api/v1/dashboard` llena `members_without_consent`.

## Tests de arquitectura que deben pasar

- Toda la suite anterior.
- La prueba de independencia de `core` (`test_core_independent.py` en el desglose de EP-18), consolidada en `test_core_import_direction.py`. Comprueba tres cosas:
  - el router de `core/crypto` no importa módulos;
  - `records_count` usa el registro, no `models` ajenos;
  - `core/crypto/__init__.py` está vacío, sin ciclo con `core/audit`.
- `test_no_plaintext_at_rest.py`, ampliada a `attachment.sensitive`.
- `test_audited_tables.py`: `crypto_keys.wrapped_material` excluido del diff.
- `test_every_route_has_role.py` sobre las rutas de `crypto` y de `attachments`.

## Riesgos y mitigación

1. [MEDIUM] OpenBao sin ML-DSA en Transit.
   - Mitigación: la llave nace Ed25519 y después se rota a ML-DSA-65 como llave nueva (Q27). Se documenta en el ADR.
2. [MEDIUM] `signature_payload` es irreversible con datos.
   - Mitigación: prefijo de versión y ADR.
3. [MEDIUM] Caddy sin `x25519mlkem768`.
   - Mitigación: versión fijada por digest y verificada en el smoke.
4. [MEDIUM] Si `TRUSTED_PROXIES` no se ajusta detrás de Caddy, el rate limit bloquea a todos a la vez.
   - Mitigación: prueba del limitador detrás de los dos proxies.
5. [MEDIUM] Objetos huérfanos en el storage, o `uploads` fuera del backup.
   - Mitigación:
     - borrado compensatorio;
     - la prueba de restauración incluye un adjunto.

## Definición de hecho del sprint

- Definición de hecho común del README.
- E2E:
  - estado de la firma;
  - rotación desde pantalla;
  - subida de foto, con pruebas de borde de 5.242.880 y 5.242.881 bytes a través de Nginx;
  - descarga de la autorización.
- Smoke con el perfil `tls`, usando una CA interna, más el smoke en modo LAN.
- El worker con `--run-once sign_audit`, con OpenBao abierto y con OpenBao sellado (debe reintentar y alertar).
- Seguridad, revisada por `security-reviewer`:
  - adjuntos servidos solo por el api, con rol, `no-store` y `nosniff`;
  - validación por bytes mágicos;
  - HSTS solo con dominio;
  - ningún material de llave en la auditoría ni en el CBOM.
- `verify-delivery`.
