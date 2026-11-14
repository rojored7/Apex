# Sprint 6 · verify-delivery (V11)

- Rama: `feat/sprint-06-auditoria-firmada-llaves-adjuntos-tls`
- HEAD: `0fa8a4d` (el código es el de `e4caea2`; los dos commits posteriores son de documentos)
- Fecha: 2026-11-13
- Qué es: la matriz de dos pilares de `verify-delivery`. El pilar 1 compara lo planeado (SPRINT-06.md, historias US-140 a US-153, DECISIONES «Sprint 6») con lo entregado. El pilar 2 dice qué se probó contra el sistema real y qué solo con mocks o una vez. Se construyó solo leyendo documentos, cuadernos y archivos de evidencia; no se corrió ninguna prueba, imagen ni consulta.
- Aviso de árbol: al escribir esto el árbol tiene archivos de `api/` modificados sin commit (`rotate_job.py`, `router.py` de crypto, `attachments/{reencrypt,router,service,storage/*}.py`, `test_rotate_key_cli.py`) y otros de docs, scripts y front. Otros agentes los están corrigiendo. Toda la evidencia de abajo es del código de `e4caea2` o anterior: no cubre esos cambios.
- Seguridad de la evidencia: no transcribí contraseñas, tokens ni llaves. En los archivos de `docs/scratch/ensayo/evidencia/` que leí no vi ninguna. Sí hay secretos fuera de esa carpeta (`docs/scratch/ensayo/admin.txt`, `keys/`, `openbao/`); no los abrí.

Leyenda por criterio:
- `E` entregado como dice la historia.
- `D` entregado con desvío respaldado por una decisión (T-DOC o S6-Dxx).
- `P` parcial.
- `N` no entregado.
- `[viva: sí]` hay evidencia contra el sistema corriendo; `[viva: no]` solo pruebas automáticas (db_test, mocks, MSW, preview).
- `T:` prueba bajo `api/tests/`; `Ev:` archivo de `docs/scratch/ensayo/evidencia/`. Donde no encontré la función exacta dejo el archivo y lo digo.

---

## Pilar 1 · Plan contra entrega

### EP-17 · Auditoría firmada

**US-140 · registro de firmas** (5 E, 1 D)
1. E · tabla con las columnas pedidas, más `payload_version` · T: `migrations/test_0021_audit_signatures.py` · Ev: `paso41-d-signatures.txt` [viva: sí]
2. E · UPDATE, DELETE y TRUNCATE rechazados · T: `migrations/test_0021_audit_signatures.py::test_update_delete_y_truncate_se_rechazan`, `::test_bajo_replica_el_truncate_sigue_rechazado` · Ev: `paso41-dev-tgenabled.txt` (triggers en `A`) [viva: sí]
3. D · la llave es Ed25519, sin sonda ML-DSA (D51, D81); segunda corrida idempotente · T: `cli/test_init_keys_data_class.py::test_la_segunda_corrida_dice_ya_existe_y_no_escribe` · Ev: cuaderno A2 [viva: sí]
4. E · sin material en `crypto_keys` ni en `audit.signatures` (solo clave pública, D81) · T: `crypto/test_router_keys.py::test_la_respuesta_no_trae_material_ni_referencias`, `architecture/test_no_plaintext_at_rest.py` · Ev: `grep -c` = 0 en `paso55-*.json` [viva: sí]
5. E · payload determinista y documentado en ADR-006 · T: `core/test_signature_payload_vector.py`, `core/test_audit_sign_pure.py`, `architecture/test_adr_docs.py` [viva: n/a, función pura]
6. E · fila en `crypto_ops` y auditoría · Ev: cuaderno A2 (`crypto_ops sign/ok`, `audit_log update` sobre `crypto_keys`) [viva: sí]

**US-141 · firma nocturna** (6 E, 1 D)
1. E · firma el último `seq` y guarda la fila · T: `worker/test_sign_audit_job.py::test_firma_la_cadena_y_cuenta_en_enteros` · Ev: `paso115-dev-sign.txt` (`firmadas: 1`), cuaderno A3 con OpenBao real [viva: sí]
2. E · sin filas nuevas no vuelve a firmar · Ev: cuaderno A2 (`nada_nuevo = 1`), `v3-4-sim.txt` [viva: sí]
3. D · los 3 reintentos van dentro de la misma corrida, sin `skipped` (D34); error en `crypto_ops` y alerta · Ev: cuaderno A3, custodio sellado: 3 intentos, alertas `crypto_sealed` y `audit_sign_failed`, exit 1; `paso55-sign-sellado.txt` [viva: sí, en el ensayo]
4. E · `sign-audit` con códigos 0, 1 y 2 · T: `cli/test_sign_audit_cli.py` [viva: no encontré una corrida del CLI en vivo; el job sí]
5. E · `crypto_ops` verbo `sign` · Ev: cuaderno A2 [viva: sí]
6. E · firma por Transit en el ensayo, por el proveedor local en desarrollo · Ev: cuaderno A1 (OpenBao real, clave pública de 32 bytes), `paso24-politicas-firma.txt` [viva: sí]
7. E · dos ejecuciones simultáneas, una sola fila · T: `audit/test_sign_latest_concurrency.py::test_dos_sesiones_firman_una_sola_fila_bajo_el_candado_4270004` [viva: no, solo db_test]

**US-142 · verificación con firmas y pantalla** (6 E, 1 D, 1 P)
1. E · recorre la cadena y verifica cada firma con la clave pública de `crypto_keys`, sin custodio (D62, D81) · T: `audit/test_verify_signatures.py`, `audit/test_router_verify.py` · Ev: `paso55-verify.json` (`signatures_checked 2`, `signatures_valid 2`), `paso55-verify-sellado.json` [viva: sí, también con OpenBao sellado]
2. D · campos planos (`last_valid_signature_seq`, `_at`, `_algorithm`), no el objeto anidado; decisión del bloque S6-A3 de DECISIONES («Decisiones sobre las dudas del Rojo») · T: `audit/test_router_signatures.py` [viva: sí]
3. E · una cadena reescrita con firma que no coincide marca `first_invalid_signature_seq` · T: `audit/test_verify_signatures.py` [viva: no; solo db_test, nunca contra el ensayo, a propósito]
4. P · la historia habla de una llave Ed25519 previa a una rotación a ML-DSA-65. En v0.3 no hay ML-DSA; el equivalente es `rotate-key audit.signature --provider` (D81), con firmas viejas verificadas por su `key_id` · T: `crypto/test_rotate_sign_provider.py`, `cli/test_rotate_sign_provider.py` [viva: no; V3.5 pendiente del ensayo desellado]
5. E · `GET /audit/signatures/latest`, solo admin · T: `audit/test_router_signatures.py` · Ev: `paso55-sig-latest.json`, `v3-4-pantalla.json` [viva: sí para admin; el 403 de coach solo en prueba]
6. E · «Última firma válida» y «Firma atrasada» en pantalla (F1, D119) · T: `SignatureStatus.test.tsx`, `AuditPage.test.tsx`, E2E preview `tests/e2e/audit.spec.ts` (20 casos) · Ev: `v3-4-pantalla.json` (API con reloj congelado: `is_late=true`, `state` `none` → `ok`) [viva: la API sí, la pantalla no; `stack/audit-signature.spec.ts` escrito y no corrido]
7. E · la verificación queda como acción `verify` · Ev: cuaderno A3 (fila `verify` en la cadena) [viva: sí]
8. E · `verify-audit` imprime y sale ≠ 0 si falla · T: `cli/test_verify_audit.py` · Ev: `paso55-verify-audit-cli.txt` (exit 0 con custodio sellado) [viva: sí el caso feliz; el de salida ≠ 0 solo en prueba]

### EP-18 · Administración de llaves

**US-143 · inventario** (8 E)
1. E · 403 coach y socio, 401 sin token · T: `crypto/test_router_keys.py::test_coach_y_socio_reciben_403` · Ev: 401 en `paso63-ensayo-keys.json` [viva: 401 sí, 403 no; el ensayo solo tiene admin]
2. E · campos del inventario · Ev: `paso63-dev-keys.json`, `paso115-dev-rotacion.txt` [viva: sí]. No verifiqué por nombre la columna `rotate_by`; BRECHAS 14.15 deja «Rotación vencida» como decisión abierta.
3. E · sin `wrapped_material` ni referencias · T: `test_router_keys.py::test_la_respuesta_no_trae_material_ni_referencias` · Ev: `grep -c` = 0 en `paso63-*` [viva: sí]
4. E · paginación y 422 con `limit=201` · Ev: cuaderno B1 [viva: sí]
5. E · filtros combinados · Ev: cuaderno B1 (`?purpose=sign`, `?q=member`) [viva: sí; la combinación AND solo en prueba]
6. E · una `active` por par · Ev: `paso115-dev-rotacion.txt` (v2 `active`, v1 `decrypt_only`) [viva: sí]
7. E · fechas de Bogotá y estado con texto · T: `KeysInventory.test.tsx`, E2E preview `keys.spec.ts` (11 casos) [viva: no]
8. E · no escribe `crypto_ops` · T: `crypto/test_router_keys.py::test_listar_no_escribe_crypto_ops` [viva: no]

**US-144 · bitácora y trabajos** (6 E)
1. E · solo admin · T: `crypto/test_ops_jobs.py` · Ev: `paso68-*` [viva: 200 y 401 sí; 403 no]
2. E · filtros de `/crypto/ops` · Ev: `paso68-dev-ops.json`, `paso68-ensayo-ops.json` [viva: sí]
3. E · `/crypto/jobs` con `percent` · Ev: `paso68-ensayo-jobs.json` (8/8, 100), `paso115-dev-rotacion.txt` (286/286) [viva: sí]
4. E · sin material · Ev: `grep -c` = 0 en seis archivos `paso68-*` [viva: sí]
5. E · refresco cada 5 s mientras hay trabajo (F2 lo extiende a `pending`) · T: `CryptoJobs.test.tsx` [viva: no]
6. E · 422 por rango o fecha mal formada · Ev: cuaderno B2 [viva: sí]

**US-145 · rotar desde pantalla** (7 E, 1 D, 1 P)
1. E · solo admin · T: `crypto/test_rotate_from_screen.py` [viva: no]
2. E · 422 sin `reason` o con `confirm` ≠ `ROTAR`; reglas de `reason` iguales a las del CLI (D122) · T: `test_rotate_from_screen.py` [viva: no]
3. E · 409 `key_not_active` · T: `test_rotate_from_screen.py::test_409_key_not_active_para_una_llave_decrypt_only` [viva: no]
4. E · 409 con un trabajo `running` · T: `crypto/test_rotate_concurrency.py` (D122 lista cinco 409) [viva: no]
5. E · 202 con `job_id`; llave nueva `active`, anterior `decrypt_only`, job y auditoría en una transacción (D121, D121 bis) · Ev: `paso115-dev-rotacion.txt` (202; v2 `active`, v1 `decrypt_only`; auditoría seq 6089) y `paso115-dev-adjuntos.txt` (`attachment.sensitive` 3/3) [viva: sí, en desarrollo; en el ensayo con OpenBao no hay rotación por pantalla]
6. P · lectura durante el recifrado. El job de la corrida real duró unos 80 ms (`started_at` 23:20:54.866, `finished_at` 23:20:54.946), así que la lectura «mid» no fue necesariamente concurrente. La prueba de «lectura a mitad» usa una tabla de prueba (`rotacion_lista`), no `GET /members/{id}` (cuaderno R1, duda f). El E2E de stack que lo haría, `keys-rotate.spec.ts`, no se ha corrido · T: `test_rotate_attachment_class.py`, `test_rotation_engine.py` [viva: débil]
7. D · al terminar, la anterior queda `decrypt_only`, no `retired` (D43, D61, D69); un job fallido deja `failed` y datos legibles · T: `test_rotate_from_screen.py::test_un_error_de_lote_deja_failed_con_un_codigo_y_la_anterior_en_decrypt_only` [viva: no]
8. E · `batch_id` por lote (D116: lotes de 10 archivos) · T: `architecture/test_rotation_batches.py`, `crypto/test_rotate_audit_row.py` [viva: no]
9. E · sin material en ninguna respuesta · Ev: `paso115-dev-rotacion.txt` [viva: sí]

**US-146 · CBOM** (6 E)
1. E · solo admin · T: `crypto/test_router_cbom.py` [viva: admin sí, 403 no]
2. E · JSON con `Content-Disposition` y fecha de Bogotá · Ev: `paso75-dev-cabeceras.txt`, `paso75-ensayo-cabeceras.txt` [viva: sí]
3. E · llaves más algoritmos fijos; sin referencias de las `sign` (D57) · Ev: `paso75-dev-cbom.json`, `paso75-ensayo-cbom.json` (9 llaves) [viva: sí]
4. E · sin material · Ev: `grep -c` = 0 [viva: sí]
5. E · fila `export` por descarga · Ev: `paso75-dev-audit.txt`, `paso75-ensayo-audit.txt` [viva: sí]
6. E · `build_cbom` pura · T: `crypto/test_cbom_pure.py` [viva: n/a]
Extra: cubeta `cbom-export`, la tercera descarga da 429 (`paso75-dev-429.txt`).

### EP-19 · Adjuntos y autorización

**US-147 · almacenamiento seguro** (7 E, 2 D)
1. E · 5.242.880 pasa; 5.242.881 da 413 antes de escribir · T: `attachments/test_rules_pure.py::test_el_tope_exacto_pasa_y_un_byte_mas_es_file_too_large`, `members/test_attach_photo.py::test_un_cuerpo_de_5_mib_mas_un_byte_da_413_file_too_large_con_field_file` · Ev: `paso90-dev-padj.txt`, `paso90-ensayo-padj.txt` [viva: sí, por Nginx]
2. E · tipo por bytes mágicos; `elf.jpg` da 422 `unsupported_type` · T: `test_rules_pure.py::test_detect_mime_decide_por_los_bytes_magicos` · Ev: `paso90-dev-padj.txt` [viva: sí]
3. E · nombre aleatorio de 32 hex, modo 600 · Ev: `paso90-dev-uploads.txt`, `paso90-ensayo-uploads.txt` [viva: sí]
4. E · el sensible va cifrado en reposo (`apx1.`, sin `%PDF`) · Ev: `paso102-dev-reposo.txt` [viva: sí]
5. D · auditoría: `insert` al subir y fila `download` al abrir, no `reveal` ni `export` (D53) · Ev: `paso102-dev-auditoria.txt` [viva: sí]
6. D · `STORAGE_PROVIDER=local|s3`; S3 apagado en producción salvo `S3_ENABLE_PRODUCTION=true`; `boto3` solo en el grupo opcional · T: `attachments/test_s3_flags.py`, `test_storage_contract.py` con apoyo de pruebas [viva: S3 nunca contra un S3 real]
7. E · `owner_table` con lista blanca · T: `attachments/test_service_store.py` (función no localizada) [viva: no]
8. E · sin importar `models` de `members` · T: pruebas de `architecture/` [viva: n/a]
9. E · licencias · Ev: D131 (`license-checker`, `check-licenses-api`, `test_licenses` en verde) [viva: sí, local]

**US-148 · foto del socio** (6 E, 1 D)
1. E · admin y coach suben; socio 403 · Ev: `paso90-dev-coach.txt` [viva: sí]
2. E · 201 con la foto vigente · Ev: `paso90-dev-padj.txt`, `paso90-dev-ficha.json` (`photo_attachment_id`) [viva: sí]
3. D · PDF o más de 5 MiB: 422 `unsupported_type` o 413 `file_too_large` (D59), no 422 con `field: "file"` para el tamaño · Ev: `paso90-dev-padj.txt` [viva: sí]
4. E · 404 con socio inexistente o de baja · T: `members/test_attach_photo.py` [viva: no]
5. E · se sirve solo por el api · Ev: `paso102-dev-foto.txt`, `paso102-dev-foto-cabeceras.txt` [viva: sí]
6. E · la anterior no se borra · Ev: `paso90-dev-padj.txt` (lista con 2 adjuntos) [viva: sí]
7. E · la subida se audita; la vista de la foto no (ADR-007) · Ev: `paso102-dev-foto.txt` (conteos iguales antes y después) [viva: sí]

**US-149 · autorización de datos** (3 E, 4 D)
1. D · el contrato de `POST /members` no cambia: `data_consent: bool`; el 422 sale solo si hay `consent_required_from` (D46) · Ev: `paso96-dev-alta.txt` (sin `data_consent` → 422 `field = data_consent_at`) [viva: sí, en desarrollo]
2. D · la fecha la fija el servidor, ya no hay fecha futura que validar (D46) [viva: n/a]
3. E · versión copiada de `privacy`; sin versión → 409 `privacy_version_missing` · T: `members/test_consent_create.py::test_con_el_corte_vigente_pero_sin_politica_publicada_da_409_privacy_version_missing` · Ev: `paso96-dev-alta.txt` [viva: sí]
4. D · el campo `sensitive` no existe: lo decide el servidor y un extra da 422 (D46, D59) · Ev: `paso102-dev-subida.json` (`sensitive = true`) [viva: sí]
5. E · socios antiguos siguen funcionando · Ev: `paso96-dev-consent-adjunto.txt` (68 socios previos, control 201) [viva: sí]
6. E · registrar la autorización de un socio antiguo fija fecha y versión, con auditoría `update` · T: `members/test_consent_by_attachment.py`, `test_consent_late_patch.py` · Ev: `paso96-dev-consent-adjunto.txt` (seq 6048) [viva: sí]
7. D · solo el admin sube `consent` y `other`; el coach solo foto (D45); socio 403 [viva: coach en `paso90-dev-coach.txt`]

**US-150 · pestaña y descarga** (5 E, 2 D)
1. D · admin y coach, pero el coach solo ve y baja fotos (D45) · T: `attachments/test_router_download.py` [viva: sí para el coach con la foto]
2. E · lista paginada sin contenido ni nombre en disco · Ev: `paso90-dev-ficha.json` [viva: sí]
3. D · fila `download` por descarga; el evento `SensitiveFieldRevealed` no existe (D53) · Ev: `paso102-dev-auditoria.txt` [viva: sí]
4. E · bytes idénticos y `crypto_ops decrypt` · Ev: `paso102-dev-descarga.txt` (`cmp` idéntico) y `paso115-dev-adjuntos.txt` (tras la rotación sigue leyendo `%PDF-`) [viva: sí]
5. E · `no-store` y `nosniff` · Ev: `paso102-dev-cabeceras.txt` [viva: sí]
6. E · 404 de un id inexistente y adjunto de un socio dado de baja descargable para admin y coach · T: `attachments/test_router_download.py::test_los_adjuntos_de_un_socio_de_baja_siguen_descargables` (corrección del orquestador: la primera pasada no localizó la función) [viva: no]
7. E · fechas de Bogotá · T: `AttachmentsTab.test.tsx`, E2E preview `member-tabs.spec.ts` (16 casos) [viva: no]

**US-151 · socios sin autorización** (6 E)
1. E · el KPI `members_without_consent` existe desde S5-D240 (D39) · T: `members/test_count_without_consent.py` · Ev: `paso107-dev-filtro.txt` [viva: sí, con N = 0]
2. E · `GET /members?consent=missing` paginado · T: `members/test_filter_consent_missing.py` · Ev: `paso107-dev-filtro.txt` (`total` 0, `consent=x` → 422) [viva: sí, pero solo con N = 0]
3. E · ninguna operación falla por fecha nula · Ev: `paso96-dev-consent-adjunto.txt` [viva: sí]
4. E · marca con texto en la ficha · T: `MemberDetailPage.test.tsx` [viva: no]
5. E · el contrato solo suma · Ev: `gen:api` sin diff (D128) [viva: n/a]
6. E · sigue siendo admin o coach · T: pruebas de `dashboard/` [viva: no]
Hueco: la tarjeta, el chip y el filtro nunca se vieron con N > 0 en un sistema vivo.

### EP-20 · TLS

**US-152 · TLS con Caddy híbrido** (6 E, 1 P, 1 N)
1. E · Caddy sirve front y api por 443 · Ev: `paso32b-tls-smoke-dominio.log`, `paso122-ensayo-tls-smoke.txt`, `paso32c-prod-smoke-tls.log` [viva: sí, CA interna y `apex.localhost`]
2. E · negocia `X25519MLKEM768` · Ev: `paso32b-tls-smoke-dominio.log`, `paso32-x25519-hsts-manual.txt` [viva: sí]
3. E · cae a `X25519` · Ev: `paso32b-tls-smoke-dominio.log` [viva: sí]
4. E · TLS 1.1 rechazado (TLS 1.0 no aparece por nombre) · Ev: `paso32b-tls-smoke-dominio.log` [viva: sí]
5. P · la renovación contra staging es paso humano (D64) y no localicé evidencia de que los certificados persistan en `caddy_data` tras reiniciar [viva: no]
6. E · `web` no publica puertos con `compose.tls.yml` · Ev: `paso122-ensayo-tls-smoke.txt` («ok web no publica puertos») [viva: sí]
7. E · imagen oficial 2.11.3 por digest y `NOTICE` · T: `scripts/ci/test_images_pinned.sh` · Ev: D131 [viva: sí]
8. N · SSL Labs con dominio real: paso humano, sin ejecutar

**US-153 · redirección, HSTS y LAN** (6 E, 2 D)
1. E · 308 a HTTPS · Ev: `paso32b-tls-smoke-dominio.log`, `paso122-ensayo-tls-smoke.txt` [viva: sí]
2. D · HSTS escalonado `max-age=300` sin `includeSubDomains` (D64) · Ev: mismos logs [viva: sí]
3. E · LAN sin HSTS y sin `Secure` en la cookie · Ev: `paso32b-tls-smoke-lan.log`, `paso122-ensayo-lan.txt`, `paso122-dev-cookie.txt` [viva: sí]
4. E · CORS: el origen `https` del dominio pasa; `http` y otros no (D127) · Ev: `paso122-ensayo-cookie-cors.txt` [viva: sí]
5. E · CSP del dominio sin orígenes `http:`: la CSP de Nginx es `'self'` en todos los modos (`infra/nginx/default.conf`) y desde V11 `tls-smoke.sh` lo afirma por HTTPS (`CSP servida por HTTPS sin orígenes http: (US-153.5)`); se ejerce en el próximo `tls-smoke` o `prod-smoke --tls` [viva: no, pendiente de la próxima corrida]
6. E · sin dominio ni perfil, usable por IP como en v0.1 · Ev: `paso32b-tls-smoke-lan.log` [viva: sí]
7. D · el arranque falla con `CORS_ORIGINS` `http:` y dominio; variables `FRONT_BASE_URL` y `COOKIE_SECURE` (D65) · T: `core/test_public_origin.py`, `core/test_config_error_message.py` · Ev: `paso122-ensayo-config-error.txt` (exit 1 con la variable nombrada) [viva: sí]. El mensaje nombra la variable pero es el genérico «Configuración inválida»; no explica el motivo ni propone arreglo.
8. E · runbook de LAN a dominio y vuelta · `docs/operacion/tls.md` (hoy con cambios sin commit) [viva: n/a]

### Conteo real de criterios (Pilar 1)

- Criterios: 102 en 14 historias.
- `E` entregado literal: 81.
- `D` entregado con desvío respaldado por decisión: 15.
- `P` parcial: 3 (US-142.4, US-145.6, US-152.5).
- `N` no entregado: 1 (US-152.8, SSL Labs, humano).
- **Entregados (E + D): 98 de 102 (96 %).** Solo `E`: 83 de 102 (81 %).
- Historias sin `P` ni `N`: 9 (US-140, 141, 143, 144, 146, 147, 148, 149, 151). Con al menos uno: 5 (US-142, 145, 150, 152, 153).
- Con prueba viva en al menos un camino: casi todos; los que son solo de prueba: los 403 de coach y socio en `crypto/*`, la rotación por pantalla sin ningún E2E de stack, y todo el front contra el stack real.

### Desvíos T-DOC y decisiones que cambian criterios

- D51 y D81: Ed25519 único; la llave `sign` no migra de proveedor, se rota con `rotate-key audit.signature --provider`; clave pública en `crypto_keys.public_key` (US-140.3, US-142.4).
- D99: CHECK `NOT VALID` en `0021` y `VALIDATE` en `0022`; un `downgrade` previo obliga a `init-keys` antes de subir (D129).
- D34 y D60: reintentos dentro de la corrida (US-141.3).
- D62 y D104: verificación con clave pública, completa aun sellado; sin estado parcial.
- D116: lotes de 10 archivos (no 50). D121 y D121 bis: guarda de `crypto_keys` en dos triggers, uno diferido. D122: `nothing_to_rotate` y cinco 409. D43, D61 y D69: la anterior queda `decrypt_only`, no `retired` (US-145.7).
- D45, D53 y D59: el coach solo foto; sin `SensitiveFieldRevealed`; cuerpo crudo sin multipart.
- D46: contrato de `POST /members` intacto; subir el `consent` fija `data_consent_at` (US-149.1, .2, .4, .7).
- D64 y D65: HSTS escalonado, `FRONT_BASE_URL` y `COOKIE_SECURE`; ACME real y SSL Labs son humanos (US-152.5, .8; US-153.2, .7).
- D117, D118 y D129: arreglos de `prod-smoke.sh` y `restore_e2e.sh` (cambio de clave del admin, `uploads/attachments/`, CA interna en modo TLS).
- D119, D120, D123 y D126: front (estado `none` sin etiqueta, CBOM JSON por llamada, 413 y 422 con mensajes distintos, tope del cliente en 35 s).
- D124: `verify-kek-backup` no abre las filas `sign` (defecto heredado de A3, hallado en el Docker del paso 115).
- D127 y D127 bis: `tls-smoke.sh` comprueba cookie `Secure` y CORS con login real; dos defectos del guion en Git Bash.
- D128 a D132: resultados de V1, V2, V9 (0C/0H/1M/5L), V10 y V3.4.
- **D133** la escribe el orquestador con el cierre de las revisiones V11 (bloque «S6-V11»); el backlog `0025` está en D130 y D133.

### Definición de hecho de SPRINT-06.md

- DoD común del README: no la evalué punto por punto. `run-gates.sh` pasó tres de cuatro veces con el árbol de entonces; la cuarta, «sobre el árbol final» (D131), no figura cerrada y hoy el árbol tiene cambios sin commit. Parcial.
- E2E del estado de la firma: preview 20 casos; el de stack está escrito y no corrido (V7). Parcial.
- E2E de la rotación desde pantalla: preview 11 casos; `stack/keys-rotate.spec.ts` no corrido. Parcial; el equivalente vivo es `paso115-dev-rotacion.txt`, por API.
- E2E de la subida de foto con bordes 5.242.880 y 5.242.881 por Nginx: hecho con curl en `paso90-dev-padj.txt` y `paso90-ensayo-padj.txt`; `stack/members-photo.spec.ts` no corrido. Entregado por curl, parcial como E2E.
- E2E de la descarga de la autorización: `paso102-dev-descarga.txt` y `paso115-dev-adjuntos.txt` por curl; `stack/members-attachments.spec.ts` no corrido. Igual que el anterior.
- Smoke con perfil `tls`, CA interna y `apex.localhost`, y smoke LAN: entregado (`paso32b-*`, `paso122-*`, `prod-smoke --tls` con 252 `ok`).
- `restore_e2e.sh` con un adjunto y `attachments-check` sin huérfanos: entregado (V2.6 bis, 252 `ok`, 0 fallas; `paso107-restore-e2e.txt`).
- `--run-once sign_audit` con OpenBao abierto y sellado: entregado (cuaderno A2 y A3, `paso55-sign-sellado.txt`); la última vez fue antes de los cambios de R1, E1 y V9.
- Seguridad: cada punto tiene evidencia propia (el api no firma por política de Transit, `paso24-politicas-firma.txt`; adjuntos solo por el api con `no-store` y `nosniff`; bytes mágicos; HSTS escalonado; sin material en auditoría ni CBOM, `grep -c` = 0; rotación deja `decrypt_only`; foto sin fila por vista). La revisión de `security-reviewer` de V11 «sobre el árbol fusionado» no aparece en el cuaderno: pendiente.
- Ed25519 como algoritmo: entregado.
- `verify-delivery`: este archivo.

### Demos 1 a 4 por pasos

**Demo 1 · firma nocturna**
- `sign_audit` firma y deja fila en `audit.signatures`: hecho en desarrollo y en el ensayo (`paso115-dev-sign.txt`, cuaderno A3). La hora de las 07:00 por el planificador no se esperó nunca: siempre `--run-once`.
- Pantalla Auditoría con el estado de la firma: API sí (`paso55-sig-latest.json`); la pantalla no se vio contra el stack.
- «Firma atrasada» a las 48 h con alerta: hecho sobre `apex_sim` (D132; `v3-4-sim.txt`, `v3-4-atrasada.txt`: `age_h=61`, alerta `audit_sign_late`). En el ensayo no, a propósito (D71).
- «Verificar» con la clave pública sin custodio: hecho con el custodio sellado (`paso55-verify-sellado.json`).
- V3.1 a V3.3 y V3.5 del ensayo desellado: pendientes.

**Demo 2 · pantalla Llaves**
- Inventario sin material y `records_count`: hecho en desarrollo y ensayo (`paso63-*`); «Proveedor activo» muestra `names [openbao]` en el ensayo.
- Bitácora y trabajos con porcentaje: hecho (`paso68-*`).
- «Rotar» `member.document` con confirmación: hecho por API en desarrollo (`paso115-dev-rotacion.txt`); en el ensayo no; por la pantalla no.
- La anterior queda `decrypt_only`: hecho (mismo archivo).
- «Exportar CBOM» auditado como `export`: hecho (`paso75-*`).

**Demo 3 · foto y autorización**
- Foto por cuerpo crudo: 5.242.880 da 201, 5.242.881 da 413 del api, 6 MiB o más da 413 de Nginx: hecho (`paso90-dev-padj.txt`, `paso90-ensayo-padj.txt`; `Content-Length` falso da 400 de Nginx, `paso90-dev-cl-falso.txt`).
- La autorización fija `data_consent_at` y la versión: hecho en desarrollo (`paso96-*`); el ensayo estaba sellado y no se podían crear socios.
- Descarga del `consent` auditada como `download` y la foto sin fila: hecho en desarrollo (`paso102-*`).
- Inicio con «socios sin autorización» y enlace: la tarjeta solo con pruebas de front; el filtro vivo solo con N = 0 (`paso107-dev-filtro.txt`).

**Demo 4 · TLS híbrido**
- `tls-smoke.sh` con CA interna y `apex.localhost:8443`: hecho, 19/19 y luego 25 `ok` (`paso32b-*`, `paso122-ensayo-tls-smoke.txt`, D127 bis).
- Grupo `X25519MLKEM768` con `openssl s_client`: hecho.
- 308 y HSTS escalonado solo con dominio: hecho.
- LAN sin HSTS ni `Secure`: hecho (`paso122-ensayo-lan.txt`, 8 `ok`).
- ACME real y SSL Labs: humanos, pendientes.
- Parte sellada: el ensayo estaba sellado; la cookie y CORS se probaron con un login que no necesita cifrado.

---

## Pilar 2 · Sistema real

### Imágenes vigentes

Referencia: la evidencia más reciente es `v2-imagenes-antes-smoke.txt` y `v2-smoke-limpieza.txt` (V2.6 bis, checkpoint `e4caea2`).
- api y worker: `apex-api:local` `61cf391f84b6`, una sola imagen para los dos (`/health.version` = `e4caea23ee10`, `v2-dev-health.json`).
- web: `apex-web:local` `90c06d37def6`.
- backup: `apex-backup:local` `825160bd313f`.
- caddy: imagen oficial 2.11.3 por digest, sin módulos; no se reconstruye. La etiqueta `revision` de las imágenes locales que cita D131 es `85b3919096d3` (`test_api_image`); las de V2.1 (`acdd90d2a096`, `92176977fb66`, `dda02863aa5a`) ya no son las vigentes.
- Ensayo (`apex-ensayo`): la última imagen del api que cita el cuaderno es `cf16102456f7` (`5fb648879410`). No hay evidencia de que se reconstruyera para `e4caea2`, y hoy está parado y sellado: su imagen está vieja respecto de HEAD.
- Árbol de trabajo: tiene cambios de código sin commit; ninguna imagen los contiene.

### Una escritura real por camino

- Firma: `--run-once sign_audit` crea fila en `audit.signatures` (`paso115-dev-sign.txt`, `firmadas: 1`); con OpenBao real en el ensayo (cuaderno A3, `through_seq 14`). Hecho.
- Rotación: `POST /crypto/keys/{id}/rotate` sobre `member.document` (202, 286/286) y `attachment.sensitive` (3/3), solo en desarrollo (`paso115-dev-rotacion.txt`, `paso115-dev-adjuntos.txt`). En el ensayo con OpenBao, ninguna. Hecho a medias.
- Subida: foto 201 y los rechazos, en desarrollo y en el ensayo (`paso90-*`); `consent` PDF cifrado en desarrollo (`paso102-dev-subida.json`). Hecho.
- Descarga: `GET /attachments/{id}` con `cmp` idéntico, auditoría `download` y `crypto_ops decrypt` (`paso102-*`), repetida tras la rotación (`paso115-dev-adjuntos.txt`). Hecho, en desarrollo.
- Alta con autorización: `POST /members` da 422 sin `data_consent` y 201 con él, con la versión copiada (`paso96-dev-alta.txt`). Hecho, en desarrollo.
- Filtro `consent=missing`: `paso107-dev-filtro.txt` y `paso107-ensayo.txt`, los dos con `total` 0. Solo se probó el caso vacío.
- Cambio de modo TLS: ensayo LAN → dominio → LAN con `.env` restaurado (`paso32b-*`, `paso122-*`). Hecho.

### Base cruzada (consultas citadas)

- Triggers y estructura de `audit.signatures`, `crypto_keys`, `crypto_jobs` y `attachments`: `paso41-d-signatures.txt`, `paso41-tgenabled.txt`, `paso83-dev-db.txt`, `paso115-dev-esquema.txt`, `v2-dev-triggers.txt` (25 triggers en `A`).
- Grants por rol: `paso41-privs.txt`, `paso41-db-roles.txt`, `paso6-db-roles.txt`, `v2-dev-roles.txt` (0 fallas con `DB_OWNER_MODE=existente`).
- Filas de auditoría y de `crypto_ops` de rotación, subida y descarga: `paso115-dev-rotacion.txt`, `paso102-dev-auditoria.txt`, `paso96-dev-consent-adjunto.txt`.
- Objetos en reposo: `paso90-dev-uploads.txt` y `paso102-dev-reposo.txt`.
- Guarda de `0024` como `apex_api`: `paso115-dev-guarda.txt`.
- Ciclo Alembic `0020` ↔ `0024`: `paso115-dev-ciclo.txt`, `v2-dev-pmig.txt`.

### Repetición e idempotencia

- `sign_audit` ×2: primera `firmadas = 1`, segunda `nada_nuevo = 1`, en desarrollo (cuaderno A2) y en `apex_sim` (`v3-4-sim.txt`). Matiz conocido: `worker.job_runs` guarda una fila por (job, fecha), así que la segunda sobrescribe los `details` de la primera. `paso115-dev-sign.txt` muestra una sola corrida.
- `attachments-check` ×2: `v2-dev-attachments-check.txt` (16 objetos sin fila, borrados por nombre) y segunda corrida 0/0 (D129). Con el código nuevo de D130 (compara `key_id` con el blob) no hay corrida viva registrada.
- `init-keys --data-class` ×2: «ya existe» (cuaderno A2 y C1).
- Reanudar una rotación con un job `failed`: solo en prueba; la duda (d) del Rojo de R1 no se probó viva.
- `prod-smoke.sh`: se repitió tras el primer fallo de V2.6 y cerró en 252 `ok` (`v2-smoke.txt`).

### Lo que solo se probó con mocks, solo una vez o no se probó

- Front contra el api real: no. Los E2E de stack (`audit-signature`, `keys-rotate`, `members-photo`, `members-attachments`, `home`) están escritos y no corridos (V7). Todo el front se probó con MSW y preview.
- 403 de coach y socio en `crypto/*` y en `audit/signatures/latest`: solo en prueba (el ensayo solo tiene admin).
- Rotación en el ensayo con OpenBao y lectura concurrente real: no.
- S3 real: nunca; solo el apoyo de pruebas.
- Cadena reescrita con firma inválida: solo en db_test, a propósito.
- Firma a las 07:00 por el planificador: nunca esperada.
- Socio con `data_consent_at` nulo y N > 0 en vivo: no.
- Una sola vez: la rotación de `member.document` y la de `attachment.sensitive` en desarrollo.
- `security-reviewer`: por slice sí; sobre el árbol fusionado (V11), sin registro.

---

## Pendiente y bloqueado

### Exige el ensayo desellado (decisión humana, bloque S6-C1 y D132)
- V3.1 a V3.3: firma en el ensayo, pantalla Auditoría, sellado y desello. V3.5: D81 con `rotate-key audit.signature --provider`. V4, V5 y V6: no los encontré detallados en el cuaderno que leí; los doy por pendientes del desello.
- Parte sellada de las demos 2 a 4: crear socios con el custodio abierto (demo 3), rotar en OpenBao (demo 2) y la parte cifrada de la demo 4.

### Exige autorización del usuario
- V2.5: `$DCE down -v` del ensayo (ensayo desde cero). Omitida; la regla vigente es que el ensayo solo se para.

### Escrito y no corrido
- V7: E2E `stack` (cinco specs). Nada corrido contra el stack real.
- V8: rendimiento (`perf`), fuera del gate.

### Pasos humanos de la DoD
- PR y merge del Sprint 5 (la rama lleva unos 90 commits sobre `main`; `v0.2.0` local = `3cd752a`).
- Dominio real, renovación ACME contra staging y SSL Labs (US-152.5 y .8).
- `consent_required_from` en producción: fijar el corte, hoy nulo.
- Rotar la clave del admin de desarrollo, impresa una vez en una salida de herramienta (D132), y las cinco llaves de desello del ensayo, impresas en un incidente anterior (cuaderno A3).

### Backlog `0025` (Sprint 7, sin implementar; D130)
1. FK `fk_attachments_key_id` hacia `crypto_keys` (`RESTRICT`, `NOT VALID` y luego `VALIDATE`). Hoy `apex_api` puede fijar `key_id` a cualquier UUID; `attachments-check` lo cubre a medias.
2. `guard_jobs_update`: la rama de `apex_api` debe exigir `OLD.kind = 'rotate'`. Hoy podría reabrir o cerrar un job `migrate_provider` o `rewrap` del CLI.
3. `CHECK ((purpose = 'sign') = (public_key IS NOT NULL))`.
4. `CHECK (kind <> 'photo' OR NOT sensitive)`.
- Además, la FK de `signatures.key_id` no tiene índice (L6, informativa). No hay D133 que lo respalde (ver arriba).

### Otros abiertos
- `CHANGELOG.md` y las versiones `0.3.0` se hacen en V12; la etiqueta `v0.3.0` no existe.
- Cuarta `run-gates.sh` sobre el árbol final, con V9, V10 y las correcciones de hoy.
- V11 formal (`security-reviewer` sobre el árbol fusionado).
- DESIGN-GAP abiertos en BRECHAS §14: 14.10 (nombre de quien sube), 14.12 (el coach no puede leer la versión de política) y 14.15 (plazo de «Rotación vencida»).
- Cambios sin commit en `docs/operacion/tls.md`, `scripts/workflow/*`, `web/src/core/api/client*` y los de `api/` ya citados.

---

## Actualización del 2026-11-14 (V3 a V8, S6-D134 a D140; HEAD `af23e51`, imágenes `29cbe00b8c5f`)

Lo que la sección anterior daba por pendiente o bloqueado, ya ejecutado contra el sistema real:

- **Ensayo desellado** con autorización del usuario (2026-11-13), sin imprimir llaves; imágenes de api, web, worker y backup reconstruidas (`2c85c3e4813a` y luego `29cbe00b8c5f`) y `/health` 8280 con esa versión y `crypto ok`. La imagen vieja del ensayo queda resuelta.
- **V3 (demo 1)**: `sign_audit` ×2 (`ok` y `nada_nuevo`), verificación con 3 de 3 firmas, sellado → 4 intentos y alertas, verificación completa con el custodio sellado, desello y firma (S6-D135).
- **V4 (demo 2)**: inventario sin material con `records_count` = `count(*)`, bitácora y trabajos, rotación de `member.phone` desde la API con lectura del socio durante el proceso, CBOM sin material; **V4.5 `retire-key` → `retired`** tras corregir la prueba de custodia (S6-D136, D139).
- **V5 (demo 3)** y **V6 (demo 4)** completas en el ensayo, sin defectos (S6-D137): bordes de 5 MiB por Nginx, autorización cifrada en reposo, descarga auditada con `cmp`, coach 403, foto sin fila, KPI = filtro, TLS híbrido desellado con `/health` 200, cookie `Secure`, CORS, CSP (cierra el «pendiente de la próxima corrida» de US-153.5), CBOM `tls.declared true`, vuelta a LAN.
- **V7**: E2E `stack` dos corridas 53 passed, 1 skipped, 0 flaky (incluye `audit-signature`, `keys-rotate`, `members-attachments`, `members-photo`, `home`); `preview` 219 passed con capturas (S6-D140). Cierra los cuatro «E2E … no corrido» de la DoD.
- **V8**: pruebas `perf` del sprint escritas y corridas dos veces, todas bajo tope (S6-D134).
- **V11 formal**: `security-reviewer` sobre el árbol fusionado hecho (S6-D133) y otra revisión de seguridad sobre la corrección D136 (0C/0H, M1 y L2-L4 corregidos).
- **Defectos que destapó el sistema real y se corrigieron con pruebas**: proveedor `local` por fila con OpenBao; `rotate-key` de la firma a `local` rechazado con OpenBao; prueba de custodia sin KEK local (S6-D136); fuga de auditoría en `rotacion_lista` (S6-D138); tres pruebas del menú sin «Llaves» (D133).

Criterios que cambian:
- US-145.6 (lectura durante el recifrado): `P` → `E`. V4.3 leyó el socio por API durante la rotación en el ensayo y `stack/keys-rotate.spec.ts` lo hace desde la pantalla, dos veces en verde.
- US-142.4 (rotación de la llave de firma): sigue `P`. La ida y vuelta entre proveedores en vivo no se puede hacer en el ensayo (con OpenBao el worker no monta `keys`, S5-D50) ni en desarrollo sin conectar tokens de OpenBao; queda por pruebas con `FakeTransit` y `openbao-smoke` (S6-D139).
- US-152.5 (renovación ACME contra staging): sigue `P`, paso humano.
- **Conteo: E + D = 99 de 102 (97 %)**; `P` 2, `N` 1 (SSL Labs, humano).
- Gates completos sobre `af23e51` (cierre, tras D136): api 9544 pasan, 100 saltadas, 38 `perf` fuera, cobertura sobre 80 %; ruff, formato y mypy en verde; los guiones de `scripts/ci`, `infra` y Caddy con 0 fallas; web: lint, tipos, 3930 de 3930 pruebas (98,37 % de líneas, con 2 hilos: la corrida con todos los hilos la cortó el equipo por falta de memoria) y build en verde.

Sigue abierto: V2.5 y el `down -v` del ensayo de V12 (sin autorización del usuario: el ensayo queda parado con `stop`), los pasos humanos (PR y merge del Sprint 5, push y PR del Sprint 6, dominio con ACME, SSL Labs, `consent_required_from` en producción, rotar la clave del admin de desarrollo y la contraseña del propietario de la base del ensayo, impresas en salidas de herramientas), el backlog `0025` (D130, D133) y el cambio propuesto a ADR-006 (S6-D136, exige preguntar).

## Veredicto

**READY_WITH_WARNINGS** para el cierre técnico del sprint en esta máquina. Condición: los cambios de código sin commit se confirman y pasan la cuarta `run-gates.sh`. Si no la pasan, el veredicto baja a `NOT_READY`.

Razones:
- 98 de 102 criterios entregados (83 literales y 15 con desvío respaldado por decisión); 3 parciales y 1 no entregado, que es humano.
- Los cuatro caminos principales se probaron contra el sistema vivo, en desarrollo y en parte en el ensayo: firma con OpenBao, rotación, subida y descarga con auditoría, TLS híbrido con CA interna. V9 cerró 0 críticos y 0 altos; el único medio se corrigió y el resto va a `0025`.
- El ensayo lleva días sellado y su imagen es anterior a HEAD; la mitad de las demos 2 a 4 solo se probó en desarrollo.
- Ningún E2E de stack se ha corrido; el front nunca se vio contra el api real.
- La rotación por pantalla no tiene prueba viva de lectura concurrente.
- El filtro `consent=missing` y la tarjeta solo se vieron con N = 0.
- Los puntos 1 y 2 de `0025` son huecos reales de integridad, aunque solo los alcanza un api comprometido.
- Hay cambios de código sin commit de otros agentes que la evidencia no cubre.
- Los pasos humanos (merge de S5, ACME, SSL Labs, corte de consentimiento, rotar claves de desarrollo) siguen abiertos; no bloquean el cierre técnico pero sí el despliegue.
