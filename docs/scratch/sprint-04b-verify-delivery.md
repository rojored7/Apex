# verify-delivery · Sprint 4B (plan contra lo entregado y prueba contra el sistema vivo)

- Rama: `feat/sprint-04b-continuidad-release`. HEAD al empezar y al terminar: `6cc9b8e` (`fix(cli,db): restore-kek sale 1 si no puede registrar la bitácora (S4B-D207); apply.sh cuenta el ARRAY validado (S4B-D201)`). Base del sprint: `280addd` (cierre del Sprint 4A); planificación `483297c`. Último commit que toca código: `6cc9b8e` (2026-11-04 16:04:13Z; `api/src/app/cli_ops/kek.py`, `infra/db/apply.sh`). Árbol: solo `docs/scratch/sprint-04b.md` modificado (el orquestador escribe "V8 · smokes finales").
- Fecha: 2026-11-04 (16:00–16:30Z).
- Alcance: paso V11 del plan (`docs/ddd/blueprints/sprint-04b-plan.md`, §7 líneas 829–834; trazabilidad §10 líneas 870–905; conteo §12). Pilar 1: matriz de las 9 historias del sprint más US-113 heredada, criterio por criterio; los 2 cambios de contrato; la migración `0014`; C1–C10 del impacto; H-1…H-3, M-1…M-10 y L-1…L-10; las decisiones S4B-D1…S4B-D208 agrupadas por slice; la deuda heredada del 4A con dueño 4B; las contradicciones de contrato (T-DOC); la checklist de criterios diferidos de v0.1 (`SPRINT-04B.md`, V11). Pilar 2: lo que V2–V8 dejó en el cuaderno más una comprobación propia de solo lectura (sección 12).
- Método: lectura completa de `SPRINT-04B.md`, del plan (§7, §10, §12), de `docs/ddd/impacto/sprint-04b.md` §5 y §9, de `sprint-04b-seguridad-diseno.md`, del bloque "Sprint 4B" de `DECISIONES.md` (líneas 1453–1840), de los dos cuadernos (`docs/scratch/sprint-04b.md`, 793 líneas en `6cc9b8e` más el bloque sin confirmar de V8 final; `docs/scratch/sprint-04b-front.md`, 60 líneas), de `docs/BRECHAS.md` §12 y de los criterios de `07_user_stories/` con las notas "Corregido en S4B-W0-1" de sus desgloses. Los nombres de prueba citados se comprobaron con `grep "def test_"` en `6cc9b8e`; el contrato, con `node` sobre `docs/openapi.json`. **No se corrió ninguna suite** (V8 final y V9 final los corre otro agente): las cifras de pruebas vienen del cuaderno y se dicen como tales.
- Convención (la del 4A): **entregado** (criterio vigente con prueba o evidencia en vivo), **parcial** (falta parte del criterio, su prueba o su ejecución en el lugar que el criterio nombra; se dice si está declarado y quién es el dueño), **no**. "Criterio vigente" = el de la historia corregido por la nota "Corregido en S4B-W0-1" de su desglose, por `SPRINT-04B.md` o por `DECISIONES.md` (regla S2-D2). "Solo aquí" = probado en este equipo (Windows, contenedor Linux auxiliar `docker:cli` o contenedor `uv` con `age` de Debian) y pendiente de la CI de GitHub Actions, que no ha corrido nunca sobre esta rama.

## 1. Historias (9 del sprint + US-113 heredada) y criterios vigentes

Checkpoints verificados con `git log --oneline 280addd..HEAD` (28 commits; 10 checkpoints, 1 fusión).

### US-030 · Rotación de llave por CLI (B3b, `f21faa1`)

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Llave `active` nueva versión +1; la anterior `decrypt_only` con `rotated_at` y `rotated_by` (`--as` admin) | entregado | `tests/crypto/test_rotate.py::test_rotacion_completa_deja_v2_activa_y_v1_en_decrypt_only`; `tests/cli/test_rotate_key_cli.py::test_rotate_key_rota_y_deja_la_anterior_en_decrypt_only`, `test_as_de_un_coach_sale_2`; vivo B3b demo 5 (`apex_rehearsal`, 265 socios) y V7.5 (ensayo, 37 socios) |
| 2 | Lectura sin error durante el recifrado | entregado | `test_rotate.py::test_los_datos_se_leen_durante_el_recifrado` |
| 3 | Lotes (500 por omisión), transacción por lote, `done` tras cada lote | entregado | `test_rotate_key_cli.py::test_informa_el_total_antes_de_empezar_y_el_avance_por_lote`, `test_batch_size_cambia_el_tamano_del_lote`; V7.5 (`hecho=5/37` → `37/37`) |
| 4 | (enmendado) cierra en `decrypt_only` + job `done`; `retired` solo con `retire-key` y conteo confirmado (blobs de `audit_log` incluidos) | entregado | `test_rotate.py::test_la_rotacion_nunca_deja_retired_a_la_llave_anterior`, `test_finish_rotation_no_cierra_si_quedan_filas_con_la_llave_anterior`; `tests/crypto/test_retire_key.py` (17); `tests/cli/test_retire_key_cli.py` (17); V7.5 (`--confirm-audit-blobs 0` → 2 con `audit_blobs=37`; `37` → 0; `reveal` 37/37) |
| 5 | Interrumpir y repetir reanuda el mismo job | entregado | `test_rotate.py::test_interrumpida_tras_el_lote_1_se_reanuda_sin_version_3_ni_recifrar_lo_migrado`; vivo B3b (SIGINT 190/265) y V7.5 (SIGINT 5/37, salida 130, un solo `crypto_jobs`) |
| 6 | Segunda rotación con job `running` → "rotación en curso", sin llave | entregado | `tests/crypto/test_rotate_concurrency.py::test_con_el_candado_tomado_la_segunda_falla_sin_crear_llave`; `test_rotate_key_cli.py::test_con_el_candado_tomado_sale_1_rotacion_en_curso` |
| 7 | `crypto_ops` `encrypt` con `batch_id` y `count`; fila `rotate` | entregado | `test_rotate.py::test_crypto_ops_deja_una_fila_rotate_y_filas_de_lote_con_count`; V7.5 (5 + 32 con `batch_id`) |
| 8 | Lote fallido → `failed`, anterior `decrypt_only`, datos legibles | entregado | `test_rotate.py::test_falla_inyectada_en_el_lote_2_deja_failed_y_repetir_reanuda_ese_job`; ídem en `test_rotate_key_cli.py` |
| 9 | `--reason` obligatorio | entregado | `test_sin_reason_sale_2_sin_tocar_llaves`, `test_un_reason_invalido_sale_2_sin_tocar_llaves`; V8 |
| 10 | Auditoría con el motivo | entregado | `test_audita_un_update_sobre_crypto_keys_con_el_motivo`; `test_retire_key_cli.py::test_retire_key_audita_ambos_conteos_y_deja_una_fila_rotate` |

Además: `--index` (`test_con_index_rota_la_llave_de_indice_y_no_la_de_cifrado`), G-09 (`test_attachment_sensitive_sale_2_con_el_texto_de_g09`: salida 2 del CLI, no el "409 `rotation_not_supported`" que dice `SPRINT-04B.md`), `busy` (`test_base_ocupada_reintenta_tres_veces_con_espera_de_1_s_y_sale_1`). **10/10 → entregada.**

### US-111 · Datos de demostración (B1, `b8f80dd`)

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | `tools seed --demo` sale 0: 3 planes, 30 socios, todos los estados | entregado | `tests/cli/test_seed_demo.py::test_base_vacia_crea_el_catalogo_exacto`; `test_demo_dataset.py::test_hay_al_menos_un_caso_por_estado`; B1.9 (`apex_demo`, 12/5/6/2/4/2) y V2 (ensayo: `planes=3 socios=30 membresias=31 pagos=33`) |
| 2 | Solo por `service.py` | entregado | `tests/architecture/test_app_layer_importers.py`, `test_no_cross_models.py` |
| 3 | Montos enteros en COP | entregado | `test_demo_dataset.py::test_montos_enteros_positivos_y_pagos_a_nombre_de_un_medio_conocido` |
| 4 | Cinco campos cifrados | entregado | `test_seed_demo.py::test_los_cinco_datos_sensibles_estan_cifrados_en_reposo`; B1.9 psql (`apx1.`) |
| 5 | Estados = `compute_status` | entregado | `test_estados_guardados_son_los_del_catalogo_y_coinciden_con_compute_status` |
| 6 | Auditoría `SYSTEM_USER_ID`/`--as`; cadena válida | entregado | `test_sin_as_la_auditoria_va_al_usuario_tecnico`, `test_con_as_la_auditoria_va_a_nombre_del_admin`, `test_la_cadena_de_auditoria_queda_integra`; B1.9 `verify-audit` 132 |
| 7 | Pago anulado coherente (RN-03) | entregado | `test_demo_dataset.py::test_hay_una_renovacion_un_anulado_y_una_cancelacion` |
| 8 | Segunda corrida 0 "ya aplicado" (enmienda: reanuda) | entregado | `test_segunda_corrida_no_cambia_nada`, `test_corte_a_mitad_y_reanudacion_sin_duplicar`; V2 |
| 9 | Socios reales → se niega salvo `--force-demo-on-non-empty`; producción solo en `*_demo/_ensayo/_smoke` | entregado | `test_socio_real_sale_2_sin_escribir`, `test_force_demo_on_non_empty_siembra_junto_al_socio_real`, `test_allow_production_con_un_nombre_sin_sufijo_seguro_sale_2`, `test_base_con_nombre_no_demo_sale_2_antes_de_crear_llaves` |
| 10 | Documentos ficticios con prefijo reservado | entregado | `test_treinta_socios_con_documentos_telefonos_y_correos_ficticios`; correos `@ejemplo.invalid` (S4B-D113) |

Enmiendas: dos transacciones por socio (`test_por_socio_exactamente_dos_transacciones`, `test_lock_member_precede_a_la_venta_de_cada_socio`); tablero (`test_el_tablero_cuadra_con_los_datos_de_demostracion`). **10/10 → entregada.**

### US-112 · Importar socios desde Excel (B1)

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Cabecera distinta a Q17 → ≠0 sin escribir | entregado | `tests/cli/test_import_members.py::test_cabecera_distinta_a_q17_sale_con_2_sin_escribir`; `test_members_xlsx_parse.py::test_cabecera_distinta_se_rechaza` |
| 2 | Cifrado e índices | entregado | `test_tres_filas_validas_crean_tres_socios`; V4 (`created=3`) |
| 3 | Fila inválida rechazada con motivo sin detener el resto | entregado | `test_una_fila_rechazada_no_impide_crear_el_resto`; `test_documento_nombres_y_apellidos_son_obligatorios`, `test_fecha_que_no_es_aaaa_mm_dd_se_rechaza`, `test_sexo_fuera_de_f_m_x_se_rechaza` |
| 4 | Idempotente por índice ciego | entregado | `test_reimportar_salta_los_tres_sin_escribir_socios_ni_cifrado`; B1.9 y V4 (`skipped_existing=3`) |
| 5 | Repetido en el archivo → `rejected` | entregado | `test_variantes_del_mismo_documento_dentro_del_archivo` |
| 6 | `--dry-run` sin escribir | entregado | `test_dry_run_no_escribe_nada_ni_llama_a_create_y_da_el_mismo_reporte`; B1.9 |
| 7 | Reporte y logs sin PII | entregado | `test_el_reporte_es_un_csv_con_bom_modo_600_y_documentos_enmascarados`, `test_ni_la_salida_ni_el_reporte_ni_el_log_repiten_documento_telefono_o_correo` |
| 8 | Auditoría por socio y resumen | entregado | `test_cada_alta_se_audita_a_nombre_de_as_y_hay_un_resumen_sin_nombre_de_archivo` |
| 9 | `data_consent_at` nulo con aviso | entregado | `test_los_importados_quedan_sin_autorizacion_y_la_salida_advierte`; V4 (`consent_missing=3`) |
| 10 | 1.000 filas < 2 min (enmienda: sin `bus.batch()`, `perf` con 5.000) | entregado (desviación declarada) | `tests/cli/test_import_members_perf.py`: 1.000 en 19,2 s (B1) y 17,9 s (V5); 5.000 en 95,4 y 88,6 s |
| 11 | `sexo` y contacto de emergencia | entregado | `test_sexo_se_normaliza_a_minuscula`, `test_contacto_incompleto_deja_al_socio_sin_contacto`, `test_fila_valida_da_un_member_create_completo` |

Límites (demo 3): `test_archivo_de_10_mb_mas_uno_sale_con_2`, `test_mas_de_5000_filas_salen_con_2_sin_escribir`, `test_bomba_de_zip_sale_con_2`, `test_xxe_con_entidad_externa_se_rechaza_sin_leer_el_archivo`, `test_archivo_fuera_de_import_dir_sale_con_2`; V4 (5.001 → 2). **11/11 → entregada.**

### US-113 · Proceso worker programado (heredada del 4A)

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1–5, 7, 8 | Arranque, 07:00 Bogotá, `today_bogota()`, aislamiento, `--run-once`, recuperación, reintento | entregado (4A) | `docs/scratch/sprint-04a-verify-delivery.md` §1; 4B suma `backup_check` (`tests/worker/test_schedule.py`, `test_main.py` `EXIT_BY_RESULT`) |
| 6 | Log con `started_at`, `finished_at`, `duration_ms` | entregado (cierre del 4A, S4A-D128) | `api/src/app/worker/runner.py:195-205`; `tests/worker/test_runner.py:200-217` |

**Entregada.**

### US-114 · Backup nocturno cifrado (W0-1, B2)

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Servicio `backup`, `uploads:ro`, sin puertos | entregado | `scripts/ci/test_compose_config.sh` (W0-1: 19 rojas → 0) |
| 2 | (enmendado) Dos archivos `age` por juego y manifiesto firmado; solo la pública en el servidor | entregado | `infra/backup/tests/test_lib.sh`, `test_manifest.sh` (73), `check-image-secrets.sh`; V6 (cabecera `age-encryption.org/v`, `minisign -V` ok) |
| 3 | Sin remoto → `upload: skipped`; remoto fallido conserva el local | entregado | `test_manifest.sh`, `test_scripts_static.sh:135`; W0-1.10 (remoto `local` → `upload=ok`); V6 |
| 4 | Fallo de `pg_dump`/`age` → ≠0 sin archivo final parcial | entregado (solo prueba estática) | `infra/backup/run.sh:14,79,114` (`pipefail`, `.partial` + `mv`, `trap`); `test_scripts_static.sh:133,138`. Sin caso dinámico |
| 5 | Retención sin borrar el último exitoso | entregado | `test_lib.sh:49-55`; V8 (`run.sh` ×2: 32 → 36 entradas, nada borrado) |
| 6 | Manifiesto con nombre, tamaño, `sha256`, `created_at`, subida | entregado | `infra/backup/manifest.schema.json`, `test_manifest.sh`; V6 |
| 7 | Sin secretos en logs | entregado | `scripts/ci/test_env_isolation.sh`; V6 (0 coincidencias); S4B-D104 |
| 8 | `age` y `rclone` en `NOTICE` | entregado | V9.6 (`check-licenses-api.sh` ok, `notice.sh` sin cambios) |
| 9 | Corrida manual = programada | entregado | `scripts/ci/compose-smoke.sh` (bloque `backup`); V8 smoke de desarrollo final |

**9/9 → entregada.**

### US-115 · Verificación de backup (B2, `2c6b194`)

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Reciente y verificado → `ok` | entregado | `tests/worker/test_backup_check_evaluate.py::test_un_juego_de_hace_cinco_horas_verificado_es_ok`; `test_backup_check.py::test_el_juego_de_las_siete_verificado_es_ok_con_details_enteros`; V7.4 |
| 2 | (enmendado) > 24 h → `stale`; `/health` `backup: "attention"` con 200 | entregado | `test_exactamente_24_horas_es_stale`; `tests/core/test_backup_status.py::test_cada_resultado_se_colapsa_al_valor_publico`; `test_health.py::test_backup_informativo_en_attention_no_cambia_el_200_con_migrations_ok`; B2 vivo |
| 3 | `missing` | entregado | `test_directorio_vacio_es_missing`, `test_archivo_db_ausente_es_missing`; B2 y V2 (exit 1, alerta) |
| 4 | `corrupt` | entregado | `test_manifiesto_o_archivos_alterados_son_corrupt`, `test_el_contenido_del_archivo_cambiado_tras_el_manifiesto_es_corrupt` |
| 5 | (G-07) `verify: failed` → `undecryptable` | entregado | `test_verify_failed_es_undecryptable` |
| 6 | Sin identidad → máximo `ok_unverified` | entregado | `test_verify_skipped_es_ok_unverified`; V7.4 |
| 7 | (enmendado) descifrado en streaming en `backup` | entregado (desviación G-07) | `run.sh` (`age -d \| sha256sum`); `test_el_job_no_abre_age_ni_lanza_procesos`; B2 (`verify=ok`) |
| 8 | Edad por `Clock`/`FrozenClock` | entregado | `test_23_horas_59_minutos_59_segundos_es_valido`, `test_created_at_a_mas_de_cinco_minutos_en_el_futuro_es_corrupt` |
| 9 | Dos corridas el mismo día; `/health` la última | entregado (forma enmendada: una fila por día que el intento actualiza) | `test_la_segunda_corrida_del_dia_deja_dos_intentos`, `test_solo_cuenta_la_corrida_mas_reciente`; V8 (×2, una fila `15a67641-…`, `ok_unverified` → `ok`) |

**9/9 → entregada.**

### US-116 · Respaldo de la KEK y prueba de restauración (B3a, `5e4ad47`)

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | (enmendado) `export-kek` con `age -p`, frase por terminal, nunca por argumento; sin KEK en claro | entregado (solo aquí en Linux) | `tests/cli/test_export_kek.py::test_no_existe_passphrase_ni_passphrase_file`; `tests/crypto/test_archive_kek.py::test_export_no_pasa_la_kek_por_argv_ni_por_el_entorno`; `test_archive_real_age.py` (3) y `test_kek_real_age.py` (2) **saltadas en Windows**, 62/62 en el contenedor `uv` + `age` 1.1.1 (V10) y 78/78 (B3a); V7.5 con pty |
| 2 | `crypto_ops` (`export`, `verify`, `kek.backup`) y auditoría | entregado | `test_export_kek_deja_una_fila_de_crypto_ops_y_una_entrada_de_auditoria`; V8 (tres `export`, tres `verify`) |
| 3 | `verify-kek-backup` 0 / ≠0 | entregado | `test_verify_kek_backup_sale_0_cuando_abre_todas_las_dek`, `test_verify_kek_backup_sale_1_si_alguna_dek_no_se_abre`; V7.5 (`total=9 failed=0`) |
| 4 | Restauración **en CI**: base vacía, arranca y revela con la KEK respaldada; con otra no arranca | **parcial (solo aquí; CI pendiente, no declarado)** | `infra/tests/restore_e2e.sh`: 23/0 en el ensayo (B3a.7; V7.4 36,5 s) y dentro de `prod-smoke.sh` en el auxiliar Linux (B4.10 ×2, V8 final); job `images` de Actions sin correr |
| 5 | `restore.sh` se niega con datos salvo `--i-know-this-overwrites` (firma y `--confirm-database`) | entregado | `infra/backup/tests/test_restore_guard.sh` (73 ok Windows / 74 Linux); `restore_e2e.sh` (negativas → 2) |
| 6 | Guía en pasos **seguida por alguien distinto (registro en el PR)** | **parcial (humano, no declarado)** | `docs/operacion/respaldo-y-restauracion.md` existe; nadie distinto la siguió; no hay PR |
| 7 | Nada muestra la KEK, la frase ni la identidad | entregado | `test_los_registros_no_llevan_la_kek_ni_su_base64`, `test_kek_backup.py::test_verify_wrapped_no_deja_la_kek_en_el_resultado_ni_en_su_repr`; V6; `prod-smoke` (grep = 0, ×3) |

S4B-D207: `test_restore_kek_con_la_base_arriba_y_la_bitacora_rota_sale_1_y_deja_el_archivo` (solo Linux). **5/7 → parcial.**

### US-117 · Despliegue seguro (B4, `daa6d56`)

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Sin `.env` o sin KEK → ≠0 | entregado | `scripts/ci/test_deploy_script.sh` (191 ok): "sin .env", "sin .env.ops", "sin --kek-file", "KEK que no existe", "KEK sin cabecera age" |
| 2 | (enmendado) `pre-deploy` firmado antes de construir; aborta sin `up`; sin `pull` | entregado | `test_deploy_script.sh`; V7.6 (juegos `pre-deploy-*` con `age`, manifiesto y firma; `latest.json` intacto) |
| 3 | Salud con `migrations: ok` en `DEPLOY_HEALTH_TIMEOUT` → 0 e imprime versión | entregado | V7.6 camino feliz y 1b |
| 4 | Sin salud → ≠0, respaldo conservado, `rollback-*.txt` | entregado | V7.6 (sale 1, `rollback-20261104-154731.txt`, recuperación 0); `infra/tests/deploy_e2e.sh` en `prod-smoke` ×3 |
| 5 | Nunca `down -v`, `push`, `--force`, `pull` | entregado | `infra/backup/tests/test_scripts_static.sh` (palabras prohibidas en todo el archivo, S4B-D159) |
| 6 | No restaura la base y lo dice | entregado | `rollback-*.txt` (V7.6) |
| 7 | No imprime secretos | entregado | V7.6 (`PASSWORD\|SECRET` = 0); `test_deploy_script.sh` |

Desviación declarada: sin firma de etiqueta (`--i-know-unsigned-ref`, S4B-D181/D208). **7/7 → entregada.**

### US-118 · Arranque ordenado (W0-3, B4)

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | `worker` y `web` esperan a `api` healthy (`migrate`/`dbsetup` antes) | entregado | `test_compose_config.sh`; V2 (StartedAt: db → migrate 0 → dbsetup 0 → web/worker) |
| 2 | (enmendado) migra `migrate`; el api no migra en producción | entregado | `tests/core/test_startup_failure.py::test_sin_la_variable_create_app_sin_argumento_no_migra`; W0-3.10 (log del api sin "alembic") |
| 3 | Migración fallida → ≠0 y el log nombra la revisión | entregado | `test_una_migracion_rota_con_true_relanza_y_el_log_nombra_la_revision_sin_url`, `test_uvicorn_termina_con_codigo_distinto_de_cero` |
| 4 | Tras reinicio, todo healthy | entregado | V2 (`restart worker`), V7 (ensayo `stop` → `up`: cinco healthy en 15 s), B2 (Docker Desktop reiniciado), V8 final |
| 5 | `/health` 200 solo con `migrations == "ok"` | entregado | `tests/core/test_health_migrations.py` (11; `test_tras_downgrade_menos_uno_responde_503_degraded_con_mismatch`); comprobación propia (8181 `migrations: ok`) |
| 6 | Sin `create_all` | entregado | `tests/architecture/test_no_create_all.py` |

**6/6 → entregada.**

### US-119 · ADR iniciales (B4)

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | (enmendado) Cuatro ADR con seis secciones | entregado | `tests/architecture/test_adr_docs.py::test_estan_los_cuatro_archivos_con_el_nombre_exacto`, `test_cada_adr_tiene_las_seis_secciones_en_orden_y_con_contenido` |
| 2 | ADR-002: blob, AAD, `normalize_for_index`, imports prohibidos, `age -p` | entregado (sin prueba del contenido) | `docs/adr/ADR-002-criptografia.md:34,46,52` |
| 3 | ADR-003: columnas de anulación, una vez, sin `DELETE` | entregado (sin prueba del contenido) | `docs/adr/ADR-003-pagos-inmutables.md:9-16` |
| 4 | Vector de la serialización canónica | entregado | `tests/core/test_chain_hash_vector.py::test_el_hash_del_adr_es_el_que_calcula_chain_hash` |
| 5 | "Cómo se verifica" cita pruebas existentes | entregado | `test_cada_adr_cita_al_menos_una_prueba_y_todas_las_citadas_existen` |
| 6 | "Detenerse y preguntar" | entregado | `test_cada_adr_dice_que_cambiar_la_decision_exige_detenerse_y_preguntar` |

**6/6 → entregada.**

**Conteo de historias: 9/10 entregadas, 1 parcial (US-116), 0 no. Criterios: 81/83 entregados, 2 parciales (US-116 c4 y c6).**

## 2. Contrato (0 endpoints nuevos, 2 campos)

| Cambio | Estado | Evidencia |
|---|---|---|
| `HealthOut.backup` ∈ {`ok`,`attention`,`unknown`}, por omisión `unknown`, informativo | entregado | `docs/openapi.json` (enum comprobado); `tests/core/test_health.py::test_health_out_backup_por_defecto_es_unknown`, `test_create_app_registra_backup_informativo_con_los_tres_valores`, `test_un_valor_ajeno_a_allowed_se_degrada_a_unknown_sin_500`; P-API B2 (`export-openapi` ×2 idénticas); vivo 8181 |
| `HealthOut.migrations` ∈ {`ok`,`mismatch`,`unknown`}, crítico | entregado | `docs/openapi.json`; `test_health_migrations.py::test_create_app_registra_migrations_como_critico_con_los_tres_valores`, `test_el_cuerpo_no_trae_la_revision`; P-API B4 (63 operaciones, `types.contract.test.ts` 5/5); V9.10 sin deriva |

**Conteo: 2/2.**

## 3. Migración `0014_audit_log_triggers_always`

| Elemento | Estado | Evidencia |
|---|---|---|
| `down_revision = 0013`; ocho `ENABLE ALWAYS`; `forbid_mutation` con `TG_TABLE_SCHEMA`/`TG_TABLE_NAME`; `downgrade` simétrico | entregado | `api/migrations/versions/0014_audit_log_triggers_always.py:26-39`; `tests/migrations/test_0014_audit_log_triggers_always.py` (16 funciones, 44 casos: `test_update_se_rechaza_bajo_replica`, `test_downgrade_deja_ocho_en_o_verifications_en_a_y_la_funcion_de_0002`); `test_triggers_siempre_activos.py` (+9); W0-2.7 y V2 (ciclo en `apex-db-1`, 5.625 filas antes y después); V6 (13 `%forbid%` en `A` en dev y ensayo; `replica` no los apaga); comprobación propia (13 en `A`, `0014`) |

**Conteo: 1/1.** El volcado `docs/scratch/sprint-04b-antes-0014.dump` sigue en disco (V12).

## 4. Condiciones para VERDE (C1–C10, `docs/ddd/impacto/sprint-04b.md` §9)

| C | Resumen | Estado | Evidencia |
|---|---|---|---|
| C1 | T-DOC y destino de la deuda del 4A | entregado | W0-1.8 (`f35ff39`: 9 desgloses, 54 viñetas, `SPRINT-04B.md`, `CLAUDE.md`, constancia S4A-D60/D61); V1.3 (`05556c6`: 58 líneas en 16 archivos; 0 referencias vivas) |
| C2 | Imagen `backup`, `age`, variables, CI | entregado | W0-1 (`test_images_pinned`, `test_api_image.sh`, `check-image-secrets.sh`, `test_env_example.py`, `ci.yml`); Alpine 3.24 (desviación anotada); `rclone 1.75.2-r0` (S4B-D196) con `scripts/ci/test_backup_apk_pins.sh` |
| C3 | Rol de base, arranque, `deploy.sh` sin `pull`, `restore.sh` | entregado | `migrate` + `dbsetup` + tres roles (S4B-D7, D83); `test_db_grants.py` (130), `test_db_roles.sh` 0 fallas en dev, ensayo y smoke; V7.4, V7.6 |
| C4 | Partir el CLI, gate, transacción por socio, `--as`, perf | entregado | B0 (`cli.py` 760 → 323; `test_cli_base.py`, `test_slice_gate.sh` 45 ok); B1 |
| C5 | Worker: `JobResult.status`, `DETAIL_KEYS`, `JOBS` | entregado | B2 (`test_runner.py` +8, `test_jobs_core.py` +3, `test_main.py` +9) |
| C6 | Bus y salud | entregado (forma enmendada) | sin `verify_age_archive` (G-07); `core/crypto/file_digest.py` (S4B-D139); `test_archive_importers.py`, `test_backup_status_imports.py`, `test_health_check_registrars.py`; `test_peticiones_concurrentes_ejecutan_el_check_una_sola_vez` |
| C7 | `0014` | entregado | Sección 3 |
| C8 | KEK, `core/crypto` sin auditoría, candado, G-09, `--as` | entregado (forma enmendada) | sin `pyrage` ni `--passphrase-file` (S4B-D58); `test_kek_path_single_door.py`, `test_third_party_confinement.py`, `test_guarded_calls.py`, `test_sql_literals_constant.py`; `apex-db-1` sin rotación (comprobación propia) |
| C9 | `migrations`, ADR, contrato, release | entregado | B4 (`daa6d56`); V9.11 (`check-release-version.sh` 0); regla de `sessionStorage` movida a F1 |
| C10 | Validación y release | **parcial** | Hechos: E2E críticos contra el ensayo (V4, 8 passed), restauración (V7.4), rotación interrumpida (V7.5), perf 5.000 (V5), R-3 (V5), V10 (0/0/0/2). Abiertos: V9 final, V12, paso humano, T8 sin `member → /mi` |

**Conteo: 9/10 cumplidas, 1 parcial (C10).**

## 5. Revisión de seguridad del diseño (`sprint-04b-seguridad-diseno.md`)

| Hallazgo | Estado | Evidencia |
|---|---|---|
| H-1 api con secretos del propietario | cerrado | S4B-D56; `test_compose_config.sh`; `scripts/ci/test_env_isolation.sh` (0 fallas en ensayo y smoke); `test_config.py` (producción rechaza `POSTGRES_PASSWORD`, `APEX_*`, `RCLONE_*`); `deploy.sh` rechaza `.env` con `POSTGRES_`/`DATABASE_URL=` |
| H-2 respaldo fabricado restaurado | cerrado | S4B-D57; `minisign` en `run.sh`; `test_restore_guard.sh`; `restore_e2e.sh` (sin firma, firma inválida, sin `-P`, base distinta, enlace → 2) |
| H-3 respaldo de la KEK débil | cerrado (solo aquí en Linux) | S4B-D58; `test_archive_kek.py`, `test_archive_real_age.py::test_age_d_a_mano_con_la_misma_frase_reproduce_la_kek` |
| M-1 identidad en el worker | cerrado | S4B-D59; `compose.verify.yml`; `test_el_job_no_abre_age_ni_lanza_procesos`; worker solo `backups:ro` |
| M-2 `/health` | cerrado | S4B-D60; caché y `Lock` (`test_health.py`); zona `apex_health` (`test_nginx_conf.sh`; V4 45 GET → 11×200, 34×429) |
| M-3 grants | cerrado con residual | S4B-D61; `grants.sql` con fallo cerrado; `test_db_grants.py` (130); residuales D202–D204 (v0.2) |
| M-4 comandos de la KEK | cerrado | S4B-D62; `test_export_kek_no_llama_ensure_keys_ni_configure_provider`, `test_export_kek_con_la_kek_ausente_sale_2_y_restore_kek_si_corre` |
| M-5 `retired` es bandera | cerrado con residual | S4B-D63; `test_las_exigencias_se_revisan_antes_de_contar_o_cambiar_nada` |
| M-6 importación sin confinar | cerrado | S4B-D64; 12 casos de ruta, zip y XXE en `test_import_members.py` |
| M-7 demo en base real | cerrado | S4B-D65; `test_allow_production_*` |
| M-8 Caddy a medias | cerrado fuera de 4B | S4B-D66; dueño v0.2 |
| M-9 despliegue sin verificar origen | cerrado con residual | S4B-D67, D158, D181; `test_deploy_script.sh`; firma de etiquetas v0.2 (D208) |
| M-10 retención y remoto | cerrado | S4B-D68, D104; `test_scripts_static.sh` |
| L-1 | cerrado | S4B-D69; `test_created_at_a_mas_de_cinco_minutos_en_el_futuro_es_corrupt`, `test_name_que_no_coincide_con_created_at_es_corrupt` |
| L-2 | cerrado | S4B-D70; `test_el_log_lleva_el_nombre_y_no_la_ruta_ni_upload_error_ni_el_sha_completo` |
| L-3 | cerrado | S4B-D71; `test_backup_status_imports.py` |
| L-4 | cerrado | S4B-D72; `test_db_apply.py` |
| L-5 | cerrado | S4B-D73; `test_scripts_static.sh`, `test_lib.sh` |
| L-6 | cerrado | S4B-D74; `test_el_proposito_restore_existe_en_la_bitacora`; S4B-D153 |
| L-7 | cerrado | S4B-D75; `test_compose_config.sh`; W0-3.10 |
| L-8 | cerrado | S4B-D76; `test_app_layer_importers.py`, `test_kek_path_single_door.py` |
| L-9 | cerrado con dueño | S4B-D77; regla hacia adelante, Sprint 5 |
| L-10 | cerrado | S4B-D78; `::add-mask::`; V9.8 gitleaks "no leaks found" (`c236ef4`) |

**Conteo: 23/23 cerrados (H 3/3, M 10/10, L 10/10); residual con dueño en M-3, M-5, M-8, M-9 y L-9.**

## 6. Decisiones S4B-D1…S4B-D208 (agrupadas)

| Grupo | Ids | Estado | Evidencia |
|---|---|---|---|
| Blueprint | D1–D55 | 55/55 en forma final | `DECISIONES.md:1476-1521`; superadas lo dicen (D15/D16/D18/D20/D25/D37/D38/D42 → D57–D63; D22 → D85; D44 → D67/D81). D6, D16, D17, D24, D27, D29, D33, D35, D36, D40 y D54 sin viñeta propia (citadas dentro de otras) |
| Seguridad del diseño | D56–D78 | 23/23 | Sección 5 |
| Plan y crítica 1 | D79–D103 | 25/25 | D79 (dos archivos de entorno), D81 (etiqueta local en V12), D83 (P-ROL, W0-3.11), D84 (B3a/B3b), D88 (T8 contra el ensayo, V4), D92, D98 (buildx), D100 (siete jobs), D103 (`age` real sin saltos: **pendiente de CI**) |
| W0-1 | D104 | 1/1 | cuaderno W0-1 |
| B1 | D105–D113 | 9/9 | `test_import_members.py::test_un_fallo_a_mitad_deja_resumen_parcial_y_reporte_y_sale_con_1` y demás |
| B2 | D114–D120 | 7/7 | `test_backup_check.py` (FIFO, `MAX_FILES`, tope), `test_health_check_registrars.py` |
| B3a | D121–D138 | 18/18 | D131–D136 con prueba; D137 aceptado (v0.2) |
| B3b | D139–D153 | 15/15 | D150 `test_una_fila_bloqueada_no_detiene_el_lote_y_se_migra_en_la_pasada_siguiente`; D151–D153 aceptados |
| B4 scripts | D154–D168 | 15/15 | `test_deploy_script.sh`, `test_check_release_version.sh` |
| — | D169 | no existe | reservada (`DECISIONES.md:1745`) y no usada: salto de numeración |
| B4 api y ADR | D170–D179 | 10/10 | `test_health_migrations.py`, `test_migrations_status_unit.py`, `test_gc_after_startup.py` |
| B4 revisión | D180–D189 | 10/10 | `test_deploy_script.sh` 141 → 190 ok |
| Smoke real | D190–D196 | 7/7 | segunda corrida sin parches verde (B4.10) y V8 final verde |
| F1 | D197–D199 | 3/3 | D197 aceptado (dueño el usuario); `no-session-storage.test.ts` 11/11 |
| Validación | D200–D208 | 9/9 | D200 `test_slice_gate.sh`; D201 `test_las_tres_listas_de_tablas_de_grants_sql_coinciden`; D207 (solo Linux); D202–D204, D206, D208 aceptados con dueño |

**Conteo: 207/207 con evidencia (D1–D208 menos D169).**

## 7. Deuda heredada del 4A con dueño 4B

| # | Ítem | Estado | Evidencia |
|---|---|---|---|
| 7.1 | `0014` y texto de `forbid_mutation` | entregado | Sección 3 |
| 7.2 | Índices de `audit_log` con condición escrita | entregado (condición no disparada) | S4B-D5; V5 (`max(seq)` 5.959 ≪ 500.000; todo `perf` de `tests/audit` bajo tope; EXPLAIN < 1 ms). `0015` queda con condición |
| 7.3 | Rol de base y credencial compartida | entregado | Sección 4 C3; V6 roles `f/f/f/t`; comprobación propia (`apex_api`, `apex_backup`, `apex_worker`) |
| 7.4 | `.env` del worker | entregado | `test_env_isolation.sh`; `test_compose_config.sh` |
| 7.5 | MEDIUM-1 (`25P03` → 503) | entregado | `tests/core/test_errors_busy.py`, `test_db_timeouts.py` (W0-3) |
| 7.6 | MEDIUM-2 (rollback de `crypto_ops`) | entregado | `tests/crypto/test_oplog_rollback_failure.py` |
| 7.7 | N-6 y N-7 como lista del operador | entregado (documento); ejecución humana | `docs/operacion/instalar-en-servidor.md:207,217`; RUNBOOK §1 y "Comprobaciones del operador" |
| 7.8 | R-3 | entregado | `tests/core/test_gc_after_startup.py` (`perf`): 2,1 ms (B4), 3,1 / 4,6 ms (V5), tope 100 ms; `gc.collect()` + `gc.freeze()` (D179) |
| 7.9 | `sessionStorage` | entregado (por `npm test`, no `npm run lint`) | `web/tests/lint/no-session-storage.test.ts` (11/11); S4B-D197 HIGH aceptado: `eslint.config.js` no importa la regla (decisión del usuario pendiente) |
| 7.10 | `Tabs` a 1440 px | entregado | `web/src/shared/ui/Tabs.test.tsx` (22/22); `tests/e2e/member-tabs.spec.ts` (preview); V4 stack ×2; BRECHAS 12.1 |
| 7.11 | Contraste de "automático (aviso)" | entregado (sin cambio de CSS) | `tests/e2e/member-history.spec.ts` (axe en claro y oscuro); BRECHAS 12.2 |
| 7.12 | T8 de US-109 | **parcial** | `web/tests/e2e/stack/home.spec.ts` contra el ensayo (V4): 4 passed, 1 skipped. KPI = `GET /dashboard` = psql, Por vencer y grilla < 10 s. **`member → /mi` omitido**: no hay forma de crear un usuario `member` (`POST /users` solo admin/coach) hasta el portal v1.0. Sin decisión ni dueño escrito; BRECHAS 12.5 sigue "pendiente de V4" |
| 7.13 | S4A-D60 y S4A-D61 revisados | entregado | W0-1.8; `DECISIONES.md` (D60 condición v0.2, D61 dueño v0.3); lectura humana en V12 |
| 7.14 | `cli.py` partido | entregado | B0: 760 → 323 líneas; `test_cli_base.py`; `test_file_and_function_size.py` |
| 7.15 | Planes E2E del 4A limpiados | **no (paso de V12)** | Pendiente: limpieza por API con el admin desechable (S4B-D93) |

**Conteo: 13/15 entregadas, 1 parcial (T8), 1 no (V12, por diseño).**

## 8. Contradicciones de contrato (T-DOC) cerradas en W0-1.8

Fuente: impacto §5 y plan §1 "Contradicciones de contrato cerradas en los desgloses". Evidencia común: notas "Corregido en S4B-W0-1" de los desgloses (`f35ff39`) y la limpieza de V1.3 (`05556c6`, 0 referencias vivas fuera de negaciones o historial).

| # | Del desglose → lo vigente | Estado | Evidencia en código |
|---|---|---|---|
| 1 | `register_health_check(informative=True)` → `critical=False/True`, `allowed`, `healthy` | entregado | `test_health.py::test_create_app_registra_backup_informativo_con_los_tres_valores` |
| 2 | `details` con cadenas → solo enteros de `DETAIL_KEYS` | entregado | `test_jobs_core.py::test_detail_keys_es_el_conjunto_cerrado_del_plan`, `test_job_runs_no_guarda_nombres_ni_rutas` |
| 3 | `JobOutcome` → `JobResult(status=)` | entregado | `test_runner.py` (+8) |
| 4 | `sell(max_retroactive_days=None)` → `enforce_retroactive_limit=False, role="admin"` | entregado | `test_guarded_calls.py` (una llamada, en `seed/apply.py`) |
| 5 | `create(data, by=)` → `create(session, data)` | entregado | `test_import_members.py` |
| 6 | `DuplicateDocument` → `MemberDocumentDuplicated` | entregado | `test_variantes_del_mismo_documento_dentro_del_archivo` |
| 7 | `recompute_statuses(today)` en la transacción → `(session_factory, today=)` tras el commit | entregado | `test_seed_demo.py::test_estados_guardados_son_los_del_catalogo_y_coinciden_con_compute_status` |
| 8 | `resolve_cli_actor` → `resolve_actor`/`resolve_admin_actor` | entregado | `tests/cli/test_cli_base.py` |
| 9 | `0014_crypto_ops_export_verb` → no existe; `0014` es la de triggers | entregado | `alembic heads` = 1 (V2) |
| 10 | `slow` → `perf` | entregado | `run-gates.sh -m "not perf"`; 29 `perf` en V5 |
| 11 | `shellcheck` → `bash -n` | entregado | `wave0-gate.sh`, `test_infra_scripts.sh` |
| 12 | `bats` → arnés Bash propio | entregado | `infra/backup/tests/run.sh`, `harness.sh` |
| 13 | `docker compose pull`/`IMAGE_TAG` → construir local y `prev-*` | entregado | `test_scripts_static.sh`; V7.6 |
| 14 | `uv run` en contenedores → `tools ...` / `worker python -m ...` | entregado | RUNBOOK, `docs/operacion/*`; V2–V8 |
| 15 | `ADR-002-bus-de-criptografia.md` → `ADR-002-criptografia.md` | entregado | `test_adr_docs.py::test_estan_los_cuatro_archivos_con_el_nombre_exacto` |
| 16 | `members_import` → `members.import_runs` | entregado | `web/src/shared/lib/audit-labels.test.ts` (crudo), BRECHAS 12.3 |
| 17 | `digest_file` desde el bus → `core/crypto/file_digest.py` con importadores exactos | entregado | `test_archive_importers.py` (S4B-D139) |
| 18 | `CLAUDE.md` "desde v0.2" en la regla 1 del bus → v0.1 | entregado | `CLAUDE.md` (bus, regla 1) |
| 19 | `verify_age_archive` (G-07) → no existe | entregado | `grep` vacío en `api/src`; V1.3 |
| 20 | `BACKUP_AGE_VERIFY_IDENTITY_PATH` en el worker → identidad solo en `backup` | entregado | `test_config.py`, `test_compose_config.sh` |
| 21 | `/health` con seis estados y `head/behind` → colapsado | entregado | Sección 2 |

**Conteo: 21/21.**

## 9. Checklist de criterios diferidos de v0.1 (`SPRINT-04B.md`, V11; impacto C10)

| Historia | Criterio diferido | Estado | Evidencia |
|---|---|---|---|
| US-004 | Licencias del web (`licencias-web`) | cerrado (Sprint 0) | `docs/scratch/sprint-00.md`; V9.6 (`npm run licenses` ok) |
| US-005 | `tools` y volumen `keys` | cerrado (Sprint 1) | `SPRINT-01.md:85,154` |
| US-006 | Build real y 200 de `/api/v1/health` | cerrado (Sprint 0) | `docs/scratch/sprint-00.md:128`; vivo 8181 |
| US-007 | Medición T6 del arranque | cerrado (Sprint 1) | `docs/scratch/sprint-01.md:376` |
| US-012 | `created_by` automático | cerrado (Sprint 1) | `SPRINT-01.md:117` |
| US-018 | T8 de redacción con `reveal` real | cerrado (Sprint 3) | `docs/scratch/sprint-03-verify-delivery.md:156` |
| US-020 | `backup` y arranque ordenado en `/health` | cerrado (4B) | US-115 y US-118 (secciones 1 y 2) |
| US-066 | `onReveal` y el historial | cerrado (Sprints 3 y 4A) | `SPRINT-03.md:227`; US-106 en el 4A |
| US-109 | T8 (< 10 s y cuadre con demo) | **parcial** | Deuda 7.12 (`member → /mi`) |

**Conteo: 8/9 cerrados, 1 parcial.**

## 10. Validación V1–V12

| Paso | Estado | Evidencia (cuaderno `docs/scratch/sprint-04b.md`) |
|---|---|---|
| V1 | hecho | `fae9fd0`, `05556c6`, `a0025e0` |
| V2 | hecho | imágenes `817416dd6e28`/`00945ee80d1f`/`07ab63d194f4` (`fae9fd0`), ensayo desde cero, ciclo de Alembic |
| V3 | hecho | admin desechable, psql de lectura, `--run-once` |
| V4 | hecho (con T8 parcial) | stack 39/39 ×2, preview 170, ensayo T8 4+1 saltada, críticos 8, `import-members` |
| V5 | hecho | 29 `perf` ×2, EXPLAIN |
| V6 | hecho | triggers, roles, `job_runs`, backup, `verify-audit`, logs |
| V7 | hecho | seis puntos de la demo sobre el ensayo (`78be9fb`) |
| V8 | preparación y revisión de base hechas; **smokes finales: pendiente de la corrida final; lo completa el orquestador** (bloque sin confirmar: smoke de desarrollo 84 s y `prod-smoke` 2 min 38 s, ambos verdes con imágenes de `78be9fb`). Falta del plan: `export-openapi` ×2 en V8 (hecho en B2 y B4) |
| V9 | **parcial: pendiente de la corrida final; lo completa el orquestador** (faltan `run-gates.sh` final, `check-image-secrets.sh`, `test_api_image.sh`, `pre-commit` final) |
| V10 | hecho | 0/0/0/2 (D207 corregido, D208 aceptado) |
| V11 | este archivo | — |
| V12 | no empezado | — |

## 11. Desviaciones declaradas

1. **`age -p` en vez de `apx-kek1`** (S4B-D58, H-3): sin formato propio, `pyrage` ni `--passphrase-file`; la frase la pide `age` por la terminal.
2. **Dos archivos por respaldo con manifiesto firmado** (S4B-D15 → D57): `db.dump.age`, `uploads.tar.age`, `latest.json` + `.minisig`.
3. **Verificación en `backup` y no en el worker** (G-07 enmendada, S4B-D59/D80): el worker evalúa el manifiesto sin descifrar ni verificar la firma (dueño v0.2).
4. **`/health` colapsado** (S4B-D60): `backup` ∈ {ok, attention, unknown}, `migrations` ∈ {ok, mismatch, unknown}.
5. **`retire-key` aparte** (S4B-D63): `rotate-key` cierra en `decrypt_only`.
6. **`.env` y `.env.ops`** (S4B-D56, D79).
7. **Roles también en `apex-db-1`** (S4B-D83, P-ROL): aditivo y reversible; el desarrollo sigue con el propietario (S4B-D11).
8. **Caddy fuera** (S4B-D66): dueño v0.2; v0.1 es de LAN.
9. **`deploy.sh --ref --expect-sha` sin firma de etiqueta**: `--i-know-unsigned-ref` obligatorio en v0.1 sin `.github/allowed_signers` (S4B-D181, D208; dueño v0.2 y el titular).
10. **T8 contra el ensayo** (S4B-D88), no contra el desarrollo.
11. **`home.spec.ts` fuera de las corridas ×2 de desarrollo** (`--grep-invert home`, V4).
12. **`member → /mi` omitido en T8**: no hay forma de crear un usuario `member` hasta el portal v1.0. **No tiene decisión escrita ni dueño**: se anota como parcial con dueño propuesto "v1.0 (portal) o una fixture de `member` en 4B-V12".
13. **Pruebas con `age` real saltadas aquí**: `test_archive_real_age.py` (3), `test_kek_real_age.py` (2), más las del `age` falso (`test_archive_kek.py` 16, `test_export_kek.py` 14) por `cmd.exe` con `env={}`; corrieron en el contenedor `uv` (B3a 78/0, V10 62/0). La CI las exige sin saltos (S4B-D103).
14. **La regla de `sessionStorage` solo por `npm test`** (S4B-D197): `eslint.config.js` está protegido por el hook `config-protection` del usuario.
15. **Smoke de producción en Linux por contenedor auxiliar `docker:cli`** (no WSL): B4.10 ×2 y V8 final.
16. **Siete correcciones destapadas por ese smoke** (S4B-D190–D196): guardas de `cambiar-esto` con comentarios, `/t/ptyrun.py`, permisos de `restore_e2e.sh`, firma alterada siempre, `umask` y `tar` portable en `deploy_e2e.sh`, pin de `rclone`.
17. **`file_digest.py`** (S4B-D139): `digest_file` sale de `digest.py` para que este importe solo `hashlib`.
18. Menores: Alpine 3.24 y versiones nuevas de `age`, `minisign`, `rclone`, `supercronic` (W0-1); `total=8` en vez de 10 en `verify-kek-backup` (S4B-D123; con la rotación del ensayo son 9); `retire-key` repetida dice "no admite el evento retire" (no "ya retirada") y `rotate-key` tras `done` con `--reason` inicia otra rotación (V8, "se anota el comportamiento" del plan).

## 12. Pilar 2 · contra el sistema real

### 12.1 Lo que V2–V8 dejó probado

- **Dos stacks.** Desarrollo (`apex`, `apex-db-1` solo lectura salvo `0014`, P-ROL y el ciclo autorizado de V2) y ensayo de producción `apex-ensayo` (`ENV=production`, `migrate` → `dbsetup` → api/worker/web, api como `apex_api`, worker como `apex_worker`): `test_db_roles.sh` y `test_env_isolation.sh` 0 fallas en ambos (V2, V6).
- **Imágenes.** Reconstruidas con buildx en cada slice (S4B-D98); en V7 (`78be9fb`): `apex-api:local` `5c40e21c1b38`, `apex-web:local` `c1abdde010fb`, `apex-backup:local` `efe44b7ac28e`, etiqueta OCI `78be9fb` en api y web.
- **Restauración real con la KEK respaldada** (V7.4, `restore_e2e.sh` 23/0): `reveal` con la KEK restaurada; con otra, `unwrap_failed` sin datos.
- **Rotación y retiro reales sobre demo**: `apex_rehearsal` (B3b, 265) y ensayo (V7.5, 37; V8 v3).
- **`deploy.sh` ×2 y con fallo** (V7.6): dos `pre-deploy`, rollback sin secretos, `db` detenida → 2.
- **Specs `stack` dos veces** (V4: 39/39 ×2, 0 flaky) y críticos contra el ensayo (8/8).
- **Evidencia SQL de V6**: 13 triggers en `A` en las dos bases; `replica` no los apaga; roles sin superusuario; `job_runs` sin `_sim`; `verify-audit` 0; logs sin secretos ni PII.
- **Smokes finales** (V8, sin confirmar): desarrollo 84 s y `prod-smoke` 2 min 38 s, ambos verdes con imágenes de `78be9fb`.

### 12.2 Comprobación propia (2026-11-04 16:05–16:10Z, solo lectura)

- `docker image ls`: `apex-api:local` `5c40e21c1b38` (revision `78be9fb`), `apex-web:local` `c1abdde010fb` (`78be9fb`), `apex-backup:local` `efe44b7ac28e`. Coinciden con V7 y con V8 final (reetiquetados tras `deploy_e2e`).
- `curl 127.0.0.1:8181/api/v1/health` → `{"status":"ok","db":"ok","version":"78be9fb","backup":"ok","migrations":"ok"}`. `:8280` sin respuesta: el ensayo estaba parado (`apex-ensayo-*` `Exited (0)` hace 30 s; `migrate` y `dbsetup` `Exited (0)` hace 2 min).
- `docker inspect`: `apex-worker-1` running, healthy, `StartedAt 2026-11-04T16:03:32Z`, `RestartCount 0` (recreado por V8 final 2,5 min antes); `apex-ensayo-worker-1` exited, `StartedAt 16:03:53Z`, `RestartCount 0`.
- `apex-db-1` (psql de lectura): `alembic_version` = `0014_audit_log_triggers_always`; roles `apex`, `apex_api`, `apex_backup`, `apex_worker`; `crypto.crypto_keys` 8 filas, todas versión 1 `active` (ninguna rotación llegó a la base viva); 13 triggers `%forbid%` en `A`; `max(seq)` 5.960; `job_runs` de hoy: `expirations` ok 15:58Z, `backup_check` ok 14:48Z.

### 12.3 Hallazgos del Pilar 2

1. **P2-A · Imágenes un commit atrás.** Las tres imágenes son de `78be9fb`; `6cc9b8e` cambió `api/src/app/cli_ops/kek.py` (S4B-D207) e `infra/db/apply.sh` (S4B-D201; este va por bind de solo lectura y sí está vigente). `tools restore-kek` en la imagen desplegada no tiene D207. El `prod-smoke` de V8 copió el árbol de trabajo con esos cambios sin confirmar pero corrió con `--no-build`, así que la imagen probada tampoco lo trae; la prueba de D207 solo corrió en el contenedor `uv` (62/0). Hace falta reconstruir `apex-api:local` (y `web` para la etiqueta) en `6cc9b8e` o en el SHA final y recrear api, worker y tools antes de cerrar.
2. **P2-B · "Más de una hora `healthy` sin reinicios" no se cumple ahora.** `apex-worker-1` arrancó a las 16:03:32Z (recreado por V8 final) y el worker del ensayo está detenido. `RestartCount` es 0 en los dos, pero falta la hora de observación: **pendiente de la corrida final; lo completa el orquestador** (`docker inspect -f '{{.State.StartedAt}} {{.RestartCount}}' apex-worker-1 apex-ensayo-worker-1` una hora después de la última recreación, con el ensayo arriba).
3. **P2-C · Lo probado solo aquí y lo que espera la CI.** `age` real y `pty` (5 pruebas) y el `age` falso (30) solo en el contenedor `uv`; `mkfifo` (3), enlaces simbólicos (6) y modos POSIX (3) solo en CI; `restore_e2e.sh` y `deploy_e2e.sh` en el ensayo y en el auxiliar `docker:cli`, no en Actions; `prod-smoke.sh` en el auxiliar; `scripts/ci/test_backup_apk_pins.sh` solo aquí. La CI debe correr: job `api` con `age` 1.1.1 por `apt` y 0 saltadas en `test_archive_real_age.py`/`test_kek_real_age.py` (S4B-D103), `images` con `compose-smoke.sh`, `restore_e2e.sh` y `test_backup_apk_pins.sh` en un build limpio (sin caché de buildx), `e2e-stack` con roles y `test_db_roles.sh`, `prod-smoke` con `test_db_roles.sh` y `test_env_isolation.sh`, `scripts`, `web`, `secrets-scan`. Ningún job ha corrido.
4. **P2-D · Un build limpio aún no se ha visto en CI.** D196 nació porque la caché de buildx ocultaba un pin de `apk` desaparecido; `test_backup_apk_pins.sh` lo vigila, pero los pines pueden volver a caducar antes del push.

### 12.4 Checklist del Pilar 2

- Artefactos desplegados al día con HEAD: **no** (P2-A).
- Interfaz real con escritura en el camino cambiado: sí (V4 críticos contra el ensayo; V7 respaldo, restauración, rotación, retiro, despliegue).
- Cruce con la base: sí (V6; V7.5 `crypto_ops`/`crypto_jobs`; comprobación propia).
- Caminos repetidos más de una vez: sí (V8: `dbsetup`, `run.sh`, `backup_check`, `init-keys`, `verify-audit`, `export-kek`, `verify-kek-backup`, `retire-key`, `rotate-key`, `deploy.sh`; V2/V4 `seed --demo` e `import-members`).
- Idempotencia: sí (V8, `cmp` de grants byte a byte).
- Worker más de una hora sin reinicios: **pendiente** (P2-B).
- Evidencia capturada: cuaderno V2–V8, capturas de V4 en `web/test-results/` (ignoradas), volcado de grants `v8-grants-ensayo.txt` en el scratchpad.

## 13. Discrepancias entre documentos y código

1. `SPRINT-04B.md` dice que `attachment.sensitive` responde "409 `rotation_not_supported`"; es un CLI y sale 2 con el texto de G-09.
2. `docs/BRECHAS.md` fila 12.5 sigue "pendiente de V4 (S4B-D88)" aunque V4 corrió y cambió la spec (regex y consulta de pendientes); no menciona la omisión de `member → /mi`.
3. `SPRINT-04B.md` y `DECISIONES.md:1671` dejan "Pendiente de B4: `tools` no monta `IMPORT_DIR`"; ningún bloque de B4 lo cierra. El `-v` de S4B-D90 sigue vigente y funcionó en V4, pero falta la línea de decisión.
4. S4B-D169 reservada y no usada (`DECISIONES.md:1745`).
5. `SPRINT-04B.md` (demo 6) dice `--ref <rama o SHA>`; lo vigente es `--ref vX.Y.Z` (S4B-D158).
6. El plan (V8) esperaba "ya retirada" en `retire-key` repetida y "nada que rotar"; el código responde "no admite el evento retire" e inicia otra rotación con `--reason` (anotado en V8 como comportamiento).
7. Las historias de `07_user_stories/` conservan el texto del gate (S2-D2): US-030 c4 ("`retired`"), US-114 c2 (un archivo `.sql.age`), US-115 c2 (`backup: "stale"`), US-117 c2 (`pull`, `.sql.age`), US-118 c5 ("`head`"), US-119 c1 (tres ADR).

## 14. Pendientes humanos

1. Push de la rama y de `main` tras el merge; ver los **siete jobs** de GitHub Actions en verde (`api` con `age` real y 0 saltadas, `web`, `images` con `restore_e2e`, `scripts`, `secrets-scan`, `e2e-stack` con roles, `prod-smoke`).
2. Con la CI en verde, `git push origin v0.1.0` (la etiqueta es local, S4B-D81) y publicar el borrador de `release.yml`.
3. Confirmar el titular de `LICENSE` (`rojored7`) y generar `.github/allowed_signers` antes del primer despliegue real (S4B-D208).
4. Ejecutar N-6 y N-7 en el servidor del gimnasio (`instalar-en-servidor.md:207,217`); si fallan, defecto con dueño (no bloquean la etiqueta).
5. Decidir sobre `web/eslint.config.js` (S4B-D197): importar `restricted-config.ts` o mantener la regla solo en `npm test`.
6. Que alguien distinto siga `docs/operacion/respaldo-y-restauracion.md` y lo registre en el PR (US-116 c6).
7. Leer la constancia de S4A-D60/D61 y decidir el propietario no superusuario antes de datos reales (S4B-D206).

## 15. Veredicto

> **READY_WITH_WARNINGS** (condicionado a V8 final y V9 final en verde con imágenes reconstruidas en el SHA final; si V9 falla o la CI no queda verde, pasa a NOT_READY_FOR_RELEASE)

Justificación:

- Pilar 1: 9/10 historias entregadas y 1 parcial (US-116: CI y paso humano), 81/83 criterios; 2/2 cambios de contrato; 1/1 migración con ciclo en `db_test` y `apex-db-1`; 9/10 condiciones (C10 abierta por diseño); 23/23 hallazgos del diseño; 207/207 decisiones; 13/15 deudas del 4A (T8 parcial, planes E2E en V12); 21/21 contradicciones T-DOC; 8/9 diferidos de v0.1. 0 CRITICAL y 0 HIGH abiertos (el único HIGH, D197, aceptado por el usuario).
- Pilar 2: dos stacks reales con roles separados, restauración real con la KEK respaldada, rotación interrumpida y retiro sobre demo, `deploy.sh` ×2 y con fallo, specs `stack` ×2, SQL de V6, smokes de desarrollo y producción verdes.

Warnings:

1. **P2-A (MAJOR, se corrige en V12):** imágenes en `78be9fb`, HEAD `6cc9b8e` cambió `cli_ops/kek.py`; reconstruir y recrear antes de la etiqueta.
2. **P2-B:** worker con más de una hora sin reinicios no observado tras la última recreación.
3. **CI nunca corrida (MAJOR):** todo lo de P2-C queda solo aquí; la etiqueta depende de los siete jobs.
4. **US-116 parcial:** restauración en CI pendiente; guía no seguida por otra persona.
5. **T8 sin `member → /mi`** y sin decisión con dueño; BRECHAS 12.5 desactualizada.
6. **Residuales aceptados que tocan la integridad:** propietario `apex` superusuario (D206; los triggers `ALWAYS` no lo detienen), `apex_api` con `INSERT` en `audit_log` y `UPDATE` completo en `users`/`members` (D202–D204), firma del manifiesto no verificada por el worker, sin firma de etiquetas, sin `rewrap` ante KEK comprometida.
7. **V12 abierto:** planes E2E, admin desechable, `apex_demo`, ensayo, volcado `.dump`, `docs/scratch/ensayo/` (llaves, KEK exportada), 42+ etiquetas `prev-*`, "Estado al cierre" y "Dueños asignados".
8. **Pendientes humanos** de la sección 14 (CI, push de la etiqueta, titular de LICENSE, N-6/N-7, `eslint.config.js`).

Condiciones para el release:

- V8 final y V9 final en verde (`run-gates.sh` con cobertura ≥ 80 %, `tests/architecture` sin saltadas, `check-image-secrets.sh`, `test_api_image.sh`, `pre-commit`).
- Reconstruir las tres imágenes en el SHA final, recrear dev y ensayo, repetir `/health` y observar el worker una hora.
- Decisión escrita con dueño para `member → /mi` (T8) y para el bind de `IMPORT_DIR` en `tools`; BRECHAS 12.5 al día.
- V12 completo y paso humano con los siete jobs en verde antes de empujar `v0.1.0`.
