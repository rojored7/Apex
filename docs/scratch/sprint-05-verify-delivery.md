# verify-delivery · Sprint 5 (v0.2: OpenBao, avisos, recibos y exportaciones)

- Rama `feat/sprint-05-openbao-avisos-recibos`, HEAD `4b08f02` (51 commits sobre `main`). Fecha: 2026-11-05 (~19:00–19:15Z).
- Alcance: paso V11 de `docs/ddd/blueprints/sprint-05-plan.md` (líneas 1538–1542). Pilar 1: US-120 a US-139 criterio por criterio (147 criterios), DoD de `SPRINT-05.md` (seis puntos) y demos 1 a 5. Pilar 2: sistema vivo (`apex` en 8181 y `apex-ensayo` en 8280 con overlay OpenBao).
- Método: lectura de `SPRINT-05.md`, criterios de las 20 historias (con su nota «Corregido en S5-W0-1»), bloque S5 de `DECISIONES.md` (D1..D264, revisiones, aceptados con dueño), `docs/scratch/sprint-05.md` (W0-1..W0-4, B1, B13, B2..B12, V2, V3, V4, V6, V7, V8, V10), `docs/scratch/sprint-05-front.md` (F1..F5, V10 TS), `BRECHAS.md` §13, `docs/openapi.json` y `git log main..HEAD`; nombres de prueba por `grep` en `api/tests` y `web/src`. Solo lectura del repo y de Docker (`docker ps|inspect|logs`, `curl /health`, `psql` en `BEGIN READ ONLY ... ROLLBACK`). No se corrió pytest, npm ni Playwright; no se escribió en ninguna base.
- Convención (la del 4A y 4B): **entregado** (criterio vigente con prueba o evidencia en vivo), **parcial** (falta parte del criterio, su prueba o su ejecución; se dice si hay decisión y dueño), **no**. «Criterio vigente» = el de la historia corregido por la nota «Corregido en S5-W0-1» y por las decisiones S5 que lo enmiendan. **PENDIENTE (V5|V9)**: depende de la E2E o de los gates completos, que corren después; las completa el orquestador.
- Actividad concurrente observada: el log del api del ensayo registra ciclos de sellado/desello entre 18:51 y 19:04Z (api recreado ~19:04Z). Es otro agente (V5/V9); no se tocó.

## 1. Pilar 1 · Historias y criterios

### EP-15 · Custodia de llaves con OpenBao

**US-133 · Servicio OpenBao con Transit (W0-2, `e40c5f3`)** — 7/7 entregado

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Sin puertos publicados; solo api y worker por `custody` | entregado | `scripts/ci/test_compose_config.sh` (240/0, W0-2 Revisiones); W0-2.7: desde el api `openbao:8200` 200 y `8210` rechazado; `backup` en `custody` aceptado (S5-D175, D180) |
| 2 | `bootstrap.sh` idempotente | entregado | S5-D76 (`--first-install` + `INICIALIZAR`; sin él aborta «volumen de OpenBao vacío»); `test_openbao_infra.sh` (101/0 en B3); `--reissue-tokens` repetido en B13.7 y B2.7 sin crear llaves |
| 3 | (enmendado S5-D2) una llave `apex-kek` + `apex-sign-audit` | entregado (desvío decidido) | S5-D2; W0-2.7 y V2.5 |
| 4 | Política sin exportar ni administrar | entregado | S5-D52, D191; `test_openbao_infra.sh`; `openbao_restore_e2e.sh`: token de api 403 a la instantánea, de backup 403 a `decrypt` |
| 5 | Llaves de desello y raíz nunca en repo, imagen ni logs | entregado | W0-2.7 (`LogConfig.Type=none`, grep 0), S5-D103 (`read -rs`), raíz revocada; grep vivo de logs del ensayo: 0 |
| 6 | Reinicio → sellado; desello con 3 de 5 | entregado | W0-2.7, V3 (dos ciclos), `openbao-smoke.sh` en `prod-smoke.sh --provider openbao` (V2.6, 180 ok) |
| 7 | Versión fijada y MPL-2.0 en `NOTICE` | entregado | `openbao/openbao:2.7.2` (`5046911075e1`, label `v2.7.2`); W0-1 (`notice.sh`, `test_licenses.sh`) |

**US-134 · Proveedor OpenBao (B1, `2390d22`)** — 7/7 entregado (parte de CI PENDIENTE V9)

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Con `CRYPTO_PROVIDER=openbao` los cinco campos se leen y escriben igual | entregado | B2.7, V2.5 (`GET /members/{id}` 200 en 8280), V3, V6 (`seed --demo` sobre OpenBao y export descifrado) |
| 2 | Suite de contrato contra local y OpenBao real | entregado local; CI **PENDIENTE (V9)** | `tests/crypto/test_provider_contract.py`; real: B1.7 13 passed, B2.7 14 passed (`-m openbao`); S5-D264 obliga a la CI a no saltar |
| 3 | Nada fuera de `core/crypto` cambia; `banned-api` verde | entregado | `tests/architecture/test_third_party_confinement.py`, `test_crypto_bus_importers.py` |
| 4 | Token por archivo; fuera de logs y `crypto_ops` | entregado | `test_openbao_provider.py` (permisos, tamaño, huella); `test_kek_path_single_door.py`; V10 DoD punto 1; grep vivo 0 |
| 5 | Timeout → error de dominio y `crypto_ops` `error` | entregado | `test_openbao_provider.py` (tabla de `map_error`, `CryptoUnavailable("unreachable")`), S5-D162..D168 |
| 6 | `crypto_keys` solo metadatos y `vault:v<n>:` | entregado | SQL vivo del ensayo: 8 filas `openbao`, `wrapped_material` empieza por `vault:` |
| 7 | Proveedor desconocido no arranca y lo nombra | entregado | `tests/crypto/test_provider_startup.py::test_proveedor_desconocido` |

**US-135 · Migrar proveedor de llaves (B2, `7c13e67`)** — 8/8 entregado

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Todo `openbao`; blobs sin recifrar | entregado | SQL vivo: `openbao encrypt 5`, `openbao index 3`; `tests/crypto/test_migrate_provider.py` |
| 2 | Borrar la KEK local y reiniciar no afecta | entregado | V3 (`retire-local-kek`, `kek.bin` ausente en api y worker, reinicios, `GET /members/{id}` 200); `test_retire_local_kek_cli.py::test_despues_del_retiro_el_keyring_carga_con_openbao_sin_el_archivo` |
| 3 | Segunda corrida «nada que migrar», 0 | entregado | V2.5 y V3; `test_migrate_provider_cli.py::test_la_segunda_corrida_dice_nada_que_migrar_y_sale_0` |
| 4 | Interrumpir y reanudar | entregado (solo prueba, como pide el plan) | `test_migrate_provider.py::test_una_interrupcion_a_la_mitad_se_reanuda_hasta_done_igual_a_total` |
| 5 | `CryptoJob` con total, done, fechas, error | entregado | SQL vivo: `migrate_provider done 8/8` |
| 6 | `unwrap`+`wrap` con mismo `batch_id`; auditoría con `--as` | entregado | SQL vivo: 80 filas `unwrap`/`wrap` en 4 `batch_id`; `audit_log update {from local, to openbao, total 8, done 8}`; `test_audita_un_update_con_from_to_total_y_done` |
| 7 | `--dry-run` sin escribir | entregado | V2.5 (`total=8`); `test_dry_run_imprime_el_plan_sin_exigir_h1_y_sin_escribir` |
| 8 | Confirmación `MIGRAR` y precondiciones H-1 | entregado | `test_una_confirmacion_distinta_de_migrar_sale_2_sin_escribir`, `test_sin_un_verify_kek_backup_reciente_de_una_persona_sale_2`, `test_un_manifiesto_sin_firma_o_sin_instantanea_valida_sale_2_con_el_mensaje_fijo`; V2.5 en vivo |

**US-136 · Estado degradado con OpenBao sellado (B3, `d383531`)** — 6/6 entregado

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Sellado: api arranca, `/health` 503 `crypto: sealed` | entregado | V3; `tests/core/test_health_crypto.py::test_con_el_proveedor_sellado_responde_503_degraded_y_crypto_sealed` |
| 2 | `GET /members/{id}` 503 `crypto_unavailable` | entregado | V3 (`Retry-After: 30`, `no-store`); `test_errors_crypto_unavailable.py`, `tests/members/test_router_crypto_unavailable.py` |
| 3 | `GET /plans` 200 sellado | entregado | V3 (plans, lista, payments y recibo 200) |
| 4 | Desello → 200 en ≤ 25 s sin reiniciar | entregado | V3: 8 s y 12 s; B3.8: 9 s; `test_crypto_recovery.py::test_el_sondeo_espera_20_segundos_recupera_y_avisa_una_vez_por_transicion` |
| 5 | Worker no ejecuta jobs del bus sellado (D86: `details.sellado`) | entregado | `tests/worker/test_notify_sealed.py` (5); V3 `--run-once expirations` 0 tras desellar |
| 6 | Log del cambio una vez por transición, sin datos | entregado | prueba de la fila 4; log vivo: pares `crypto_sealed`/`crypto_recovered` sin contexto (dos `sealed` por ciclo = proceso que observa + proceso reiniciado, B3.8) |

### EP-14 · Avisos de vencimiento

**US-120 · Plantillas de aviso (B6, `624ab98`)** — 9/9 entregado

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | POST 201; nombre único 409 | entregado | `test_router_templates_rules.py::test_crear_plantilla_da_201_con_el_contrato_y_no_store`, `::test_crear_plantilla_con_nombre_repetido_da_409_con_existing_id` |
| 2 | Variable desconocida 422 con `field` | entregado | `::test_crear_plantilla_invalida_da_422_con_field_y_no_crea_nada`; B6.8 en vivo |
| 3 | `render` (`{vence}` Bogotá, `{dias}` entero, sin valor lanza) | entregado | `test_rules_pure.py` (86); S5-D216 |
| 4 | Lista paginada con `q` | entregado | `::test_listar_plantillas_pagina_busca_y_valida` |
| 5 | PATCH auditado | entregado | `test_templates_service.py::test_update_template_audita_un_update_a_nombre_del_actor` |
| 6 | Sin `DELETE` | entregado | `::test_el_router_publica_las_nueve_rutas_de_plantillas_y_reglas` |
| 7 | Preview con contexto de ejemplo | entregado | `::test_la_vista_previa_renderiza_con_el_contexto_de_ejemplo_y_no_escribe`; B6.8 en vivo |
| 8 | Admin escribe; coach 403 al escribir, 200 al listar | entregado | `::test_el_coach_lee_y_recibe_403_al_escribir_sin_efectos` |
| 9 | Fechas ISO 8601 UTC | entregado (convención común, sin prueba propia) | `docs/openapi.json` (`date-time`) |

**US-121 · Reglas de aviso (B6)** — 10/11 entregado, 1 parcial

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | POST 201 | entregado | `::test_crear_regla_da_201_con_el_contrato` |
| 2 | `trigger`/`channel` fuera de lista 422 (incluido `push`) | entregado | `::test_crear_regla_invalida_da_422_con_field_y_no_crea_nada`; `test_0018_notification_rules.py` |
| 3 | Signo del desfase | entregado | `test_rules_service.py::test_create_rule_con_el_signo_equivocado_da_422_y_no_escribe` |
| 4 | `template_id` inexistente 422 | entregado | `::test_create_rule_con_plantilla_inexistente_da_422_con_template_id` |
| 5 | Dos activas iguales 409 | entregado | `::test_create_rule_activa_duplicada_da_409_con_el_id_de_la_existente`, `::test_dos_altas_activas_iguales_a_la_vez_dejan_una_y_la_otra_recibe_409` |
| 6 | Lista con filtros | entregado | `::test_list_rules_aplica_los_filtros`, `::test_list_rules_pagina` |
| 7 | PATCH; desactivar no borra ni cancela avisos ya generados | **parcial** | PATCH probado; «no cancela» se cumple por construcción (sin `DELETE`, FK `RESTRICT`, `generate` solo lee activas) pero ninguna prueba lo fija |
| 8 | Sin borrado | entregado | nueve rutas, sin `DELETE` |
| 9 | Siembra idempotente de cinco reglas | entregado | `test_seed_defaults.py` (9); B6.8 (2/5 y luego 0/0); SQL vivo: 2 plantillas, 5 reglas (-3, 0, 1, 7, 15), `insert` exactamente 2 y 5 |
| 10 | Admin escribe | entregado | `::test_el_coach_lee_y_recibe_403_al_escribir_sin_efectos` |
| 11 | Auditado | entregado | `test_rules_service.py::test_create_rule_audita_un_insert_a_nombre_del_actor`, `::test_update_rule_aplica_solo_lo_enviado_y_audita` |

**US-122 · Configurar canales (B4, `1a75ca3`)** — 7/7 entregado con desvíos decididos (la historia no tiene nota de corrección)

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Sección cerrada con las claves de S5-D30 | entregado (desvío D30/D204) | `tests/settings/test_channels_schema.py` (28); B4.7 GET en vivo. **Ver MAJOR-1**: `whatsapp.enabled`, `whatsapp.country_code` y `telegram.enabled` se guardan pero nada los lee |
| 2 | Nombres de secreto 422; `extra=forbid` | entregado | `test_channels_router.py::test_un_valor_invalido_o_un_secreto_da_422_con_field_sin_crear_fila`, `::test_una_clave_ajena_en_la_raiz_da_422` |
| 3 | PATCH 200 con auditoría sin secretos | entregado | `::test_la_auditoria_del_guardado_no_lleva_secretos_de_settings` |
| 4 | `credentials_present` (en la raíz, D204) | entregado (desvío decidido) | `::test_el_get_refleja_las_credenciales_de_settings_sin_exponer_ningun_valor` |
| 5 | Activar sin credenciales se permite (D231: avisos `pending` + alerta) | entregado (enmendado D231) | `::test_activar_el_correo_sin_credenciales_se_permite`; `test_notify_job.py::test_sin_credenciales_smtp_los_avisos_esperan_y_se_avisa_una_vez` |
| 6 | Solo admin | entregado | `::test_coach_403_en_get_y_patch_sin_escribir` |
| 7 | `.env.example` (sin Brevo, D28/D64; secretos en `.env.ops.example`) | entregado (desvío decidido) | `.env.example:151-161`, `.env.ops.example:101,103` |

**US-123 · Preferencias de canal del socio (B5, `dc0db25`)** — 7/7 entregado

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Sin filas no hay opt-in de correo (D31) | entregado | `test_channels_rules.py` (22); B5.7 en vivo |
| 2 | PATCH; canal desconocido o `push` 422 | entregado | `test_channels_router.py`; B5.7 |
| 3 | (enmendado N-20) baja: GET 200, PATCH 409 | entregado | `::test_el_get_responde_200_sobre_un_dado_de_baja`, `::test_el_patch_de_un_dado_de_baja_da_409_member_deleted` |
| 4 | `channels_for` solo activos; notifications no lee la tabla | entregado | `test_channels_service.py`; `test_no_cross_models.py` |
| 5 | Auditoría y `MemberUpdated` | entregado | `test_channels_service.py::test_set_channels_emite_member_updated_sin_valores`; B5.7 SQL |
| 6 | Admin y coach; member 403 | entregado | `test_channels_router.py::test_el_rol_member_recibe_403_en_las_dos_rutas` |
| 7 | Sin datos cifrados ni contacto | entregado | `0016`; `test_0016_member_channel_preferences.py` (18) |

**US-124 · Generar avisos del día (B7 `0b3b451`, B8 `8f750b9`)** — 8/11 entregado, 3 parcial

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | `target_dates` = `end_date + offset` | entregado | `test_rules_pure.py` |
| 2 | Un aviso por regla activa y membresía, `pending` y renderizado | entregado | `test_generate.py::test_genera_un_aviso_pendiente_con_el_texto_de_la_plantilla`, `::test_varias_reglas_para_la_misma_membresia_dan_un_aviso_por_regla` |
| 3 | `expiring` solo vigente; `expired` solo sin renovación | entregado | `test_notification_candidates.py::test_no_se_avisa_como_vencido_a_quien_ya_renovo`, `::test_una_renovacion_pendiente_de_pago_cuenta_como_ya_renovo`; S5-D217 (5) |
| 4 | Canal no activo para el socio → fila `skipped` «canal desactivado por el socio» | **parcial** | El par se descarta «en silencio», sin fila (`generate.py:11-13`; `test_generate.py::test_el_canal_del_aviso_es_el_de_la_regla_y_exige_que_el_socio_lo_tenga`). Ninguna decisión S5 enmienda el criterio; el historial no muestra la omisión. Sin dueño |
| 5 | Canal deshabilitado en `settings.channels` → `skipped` | **parcial** | Correo: entregado al enviar (`canal_no_configurado`, D222/D231; `test_sending.py::test_canal_apagado_en_la_configuracion_omite_aunque_haya_credenciales`). WhatsApp: **no**; `channels.whatsapp.enabled` no lo lee nadie; con el valor por defecto `false` (sin fila en el ensayo) se generaron 6 avisos `whatsapp_link`. MAJOR-1 |
| 6 | Único (`rule_id, membership_id, target_date`); dos corridas sin duplicar | entregado | `test_0019_notifications.py`; `test_generate_concurrency.py` (D223); V4; SQL vivo duplicados 0 |
| 7 | Congelada no genera mientras lo esté | **parcial** | Sin prueba en `generate` (solo `test_notification_candidates.py::test_entran_las_membresias_vigentes_vencidas_o_congeladas`); `generate._pairs` no excluye `frozen` para `membership_expiring`, depende de que RN-07 corra `end_date` |
| 8 | No descifra al generar | entregado | `test_notify_sealed.py::test_con_el_custodio_caido_genera_pero_no_envia_y_queda_ok` |
| 9 | `target_date` DATE; `created_at` UTC | entregado | `0019`; `test_0019_notifications.py` (47) |
| 10 | Auditado y `NotificationQueued` | entregado | `test_generate.py::test_notification_queued_solo_lleva_ids_canal_y_fecha_y_sale_tras_el_flush`; SQL vivo `insert` 6 = 6 avisos |
| 11 | Recupera 15 días (D220: solo la vencida más reciente) | entregado (precisado D220) | `test_notification_candidates.py::test_la_ventana_de_vencida_va_de_hoy_menos_15_a_hoy`; `test_generate.py::test_al_registrar_el_consentimiento_la_corrida_siguiente_lo_recupera` |

**US-125 · Enviar avisos por correo (B4, B8)** — 10/10 entregado

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Éxito → `sent`, `sent_at`, `attempts+1`, `NotificationSent` | entregado | `test_sending.py::test_envia_y_marca_sent_con_hora_actor_e_intento`; V4 |
| 2 | Fallo → `failed` con código cerrado | entregado | `::test_un_fallo_deja_failed_con_el_codigo_cerrado_y_sigue_elegible` |
| 3 | Un fallo no detiene el resto | entregado | `::test_un_canal_que_lanza_cuenta_como_unknown_y_el_lote_sigue` |
| 4 | Reintento hasta el máximo; visible | entregado | `::test_al_tercer_fallo_queda_failed_para_siempre_y_emite_el_evento`, `::test_failed_de_dias_anteriores_se_reintenta_y_pending_viejo_no` |
| 5 | Contacto por `contact_for_notification`; correo nunca guardado ni en logs | entregado | `::test_service_send_pending_descifra_solo_el_correo_con_proposito_notify`, `::test_los_logs_no_llevan_correo_nombre_ni_cuerpo` |
| 6 | Timeout explícito | entregado | `tests/core/test_mail.py`; `test_email_channel.py` |
| 7 | (enmendado D231) apagado → `skipped`; sin credenciales → `pending` + alerta | entregado | `::test_canal_apagado_en_la_configuracion_omite_aunque_haya_credenciales`, `::test_canal_habilitado_sin_credenciales_espera_sin_descifrar` |
| 8 | Auditoría de envío y fallo | entregado | `::test_el_cambio_de_estado_deja_update_en_la_auditoria_por_orm` |
| 9 | Asunto renderizado | entregado | `::test_el_canal_recibe_el_correo_descifrado_y_el_texto_ya_renderizado`; V4 (Mailpit) |
| 10 | Solo en el worker | entregado | `test_worker_boundaries.py`; `::test_el_envio_ocurre_fuera_de_la_transaccion_y_sin_candado` |

**US-126 · Telegram como canal interno (B4, B8)** — 5/6 entregado, 1 parcial

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Envío al `TELEGRAM_CHAT_ID`; ok en el log | entregado | `tests/core/test_alerts_telegram.py`; B4.7 y V4 (`telegram-fake`) |
| 2 | Fallo registrado sin token ni URL | entregado | `::test_un_fallo_de_red_no_propaga_y_el_log_lleva_solo_el_tipo`, `::test_una_respuesta_de_error_con_el_token_en_el_cuerpo_no_llega_al_log` |
| 3 | Reintentos con la política de US-125 | **parcial** | No hay reintento: envío único con cola de 20 y deduplicación de 60 s (S5-D206); ninguna decisión dice «sin reintento». Sin dueño |
| 4 | Token nunca en base, auditoría ni logs | entregado | `test_alerts_telegram.py`; B4.7 y B8 (`grep bot123` 0) |
| 5 | CI de licencias rechaza `python-telegram-bot` | entregado | `scripts/ci/test_licenses.sh` caso 1b |
| 6 | Timeout 10 s | entregado | `::test_usa_la_base_configurada_y_el_timeout` |

**US-127 · Por avisar hoy y enlace de WhatsApp (B7, F1)** — 8/9 entregado, 1 no (decidido)

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | `today` (D219: pendientes de hoy y 15 días atrás, más fallidos) | entregado (precisado D219) | `test_today_and_skip.py::test_hoy_incluye_pendientes_y_fallidos_de_hoy_y_fallidos_anteriores`, `::test_hoy_pagina_con_limit_y_offset` |
| 2 | Sin teléfono ni correo | entregado | `::test_cada_fila_trae_el_nombre_del_socio_y_ningun_dato_de_contacto` |
| 3 | POST `wa-link` descifra con `notify`, `{url}`, marca `sent` | entregado | `test_wa_link.py::test_devuelve_la_url_y_marca_sent_con_quien_y_cuando`, `::test_cada_llamada_audita_reveal_y_escribe_crypto_ops_solo_del_telefono`; B7.7 en vivo (ensayo anterior a V2) |
| 4 | Repetir: misma URL, sin cambiar `sent_at`, con auditoría | entregado | `::test_la_segunda_llamada_devuelve_la_misma_url_sin_cambiar_la_marca`; B7.7 |
| 5 | `skipped` → 409 | entregado | `::test_un_aviso_omitido_da_409_sin_descifrar_nada` |
| 6 | Sin teléfono 422 `member_without_phone` | entregado | `::test_un_socio_sin_telefono_da_422_y_el_aviso_sigue_pendiente` |
| 7 | Aviso `email` `failed` también por WhatsApp | **no** (desvío decidido) | S5-D217 (11): 409 `wrong_channel`; `::test_un_aviso_de_correo_da_409_sin_descifrar_nada`; F1 no ofrece el botón. Historia sin enmendar |
| 8 | Admin y coach; member 403 | entregado | `test_router_notifications.py::test_member_recibe_403_en_todo_sin_efectos` |
| 9 | Abre `wa.me` solo tras el 200 | entregado (unidad); E2E **PENDIENTE (V5)** | `WaButton.test.tsx`; `stack/avisos.spec.ts` |

**US-128 · Omitir aviso con motivo (B7, F1)** — 5/5 entregado

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | `skip` 3–500, `sent_by`, `NotificationSkipped` auditado | entregado | `test_today_and_skip.py::test_omitir_un_aviso_pendiente_o_fallido_lo_deja_skipped_con_su_motivo`, `::test_omitir_deja_un_update_auditado_a_nombre_de_quien_omite`; `test_router_notifications.py::test_skip_acepta_los_extremos_de_3_y_500_caracteres`; B7.7 |
| 2 | Sin motivo 422 | entregado | `::test_skip_con_un_cuerpo_invalido_da_422_y_no_cambia_el_aviso` |
| 3 | `sent`/`skipped` 409 | entregado | `::test_skip_de_un_aviso_cerrado_da_409_y_de_uno_inexistente_404` |
| 4 | Desaparece de hoy, queda en historial | entregado | `::test_un_omitido_deja_de_aparecer_en_por_avisar_hoy` |
| 5 | Admin y coach; member 403 | entregado | `::test_admin_y_coach_pueden_las_seis_operaciones` |

**US-129 · Historial de envíos (B7, F2)** — 5/6 entregado, 1 parcial

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | Filtros, paginación y orden | entregado | `test_history_and_member_tab.py` |
| 2 | Rango invertido o `limit` fuera 422 | entregado | `test_router_notifications.py::test_parametros_invalidos_dan_422` |
| 3 | Campos sin contacto | entregado | `::test_get_devuelve_el_aviso_con_el_nombre_y_sin_contacto` |
| 4 | Detalle con `rendered_body` | entregado | `::test_el_detalle_devuelve_el_aviso_y_404_si_no_existe` |
| 5 | Admin y coach; member 403 | entregado | `::test_member_recibe_403_en_todo_sin_efectos` |
| 6 | 10.000 avisos por socio < 500 ms | **parcial** | Índice `ix_notifications_member_target_date` (`0019`); sin `perf` ni `EXPLAIN` de esta consulta (V7 midió hoy, `_existing` y exportaciones). V8 LOW 5 aceptado con dueño v0.3 |

**US-130 · Pestaña Avisos de la ficha (B7, F3)** — 5/5 entregado

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | Misma forma y paginación | entregado | `test_history_and_member_tab.py::test_la_pestana_trae_solo_los_avisos_del_socio_del_mas_nuevo_al_mas_viejo` |
| 2 | Inexistente 404; de baja muestra historial | entregado | `::test_la_pestana_de_un_socio_inexistente_es_404`, `::test_la_pestana_incluye_a_un_socio_dado_de_baja` |
| 3 | Pestaña sin contacto | entregado | `NotificationsTab.test.tsx`; E2E preview `member-tabs.spec.ts` (F3) |
| 4 | Admin y coach; member 403 | entregado | `test_router_notifications.py` |
| 5 | Carga diferida | entregado | `NotificationsTab.test.tsx` |

**US-131 · Recuperar y activar cuenta por correo (B9 `8860b03`, F5)** — 6/6 entregado

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | `forgot` envía a activa; nada a inexistente; 204 siempre | entregado | `tests/auth/test_forgot_delivery.py` (15); V4 en vivo |
| 2 | Alta y reenvío envían y devuelven el enlace | entregado | `test_user_link_mail.py::test_post_users_con_smtp_y_canal_responde_201_con_email_sent_true`, `::test_el_reenvio_http_con_smtp_y_canal_envia_y_responde_email_sent_true`; V4 |
| 3 | Token fuera de logs y auditoría | entregado | `::test_el_enlace_enviado_nunca_aparece_en_los_logs`, `test_forgot_delivery.py::test_ni_el_enlace_ni_el_correo_llegan_a_los_logs`; V4 (0 en 36 líneas) |
| 4 | Correo apagado o fallido: 204 / `email_sent=false` | entregado | `::test_post_users_sin_smtp_responde_201_con_email_sent_false`, `test_forgot_delivery.py::test_un_fallo_de_smtp_no_cambia_la_respuesta` |
| 5 | Enlace usado o vencido: «El enlace ya no es válido» | entregado (heredado S2) | `web/src/features/auth/pages/ResetPage.test.tsx` |
| 6 | Sexto `forgot` por IP 429 | entregado (heredado S2) | `tests/auth/test_reset_forgot_router.py::test_forgot_el_sexto_por_ip_da_429` |

**US-132 · KPI por avisar en Inicio (B10 `8eff83e`, F3)** — 4/4 entregado (E2E PENDIENTE V5)

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | `notifications_today` = total de `today` | entregado | `tests/dashboard/test_service.py`, `test_router.py::test_get_dashboard_trae_los_dos_kpi_enteros_y_con_los_valores_sembrados`; B10 en vivo (9 = SQL 9) |
| 2 | Contrato sin otros cambios | entregado | `docs/openapi.json`; `test_router.py::test_el_cuerpo_tiene_las_claves_del_contrato_y_los_tres_futuros_en_null` |
| 3 | Tarjeta a `/avisos/hoy`; «Nadie por avisar» | entregado (unidad); E2E **PENDIENTE (V5)** | `NotificationKpis.test.tsx`; `stack/home.spec.ts` |
| 4 | Admin y coach | entregado | `::test_el_coach_recibe_los_dos_kpi_igual_que_el_admin` |

### EP-16 · Recibos y exportaciones

**US-137 · Descargar recibo (B11 `a098f67`, F4)** — 7/8 entregado, 1 parcial

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | 200 `application/pdf` admin y coach | entregado | `test_router_receipt.py::test_admin_y_coach_descargan_el_recibo`; V6 (admin) |
| 2 | Monto, medio, referencia, fecha Bogotá, nombre | entregado | `test_receipt_pure.py` (30), `test_receipt_service.py::test_el_recibo_trae_frase_id_socio_plan_medio_referencia_y_monto`; V6 |
| 3 | Sin documento, teléfono, correo ni cifrados | entregado | `::test_el_recibo_no_lleva_documento_telefono_correo_ni_contacto_de_emergencia`; V6 |
| 4 | Anulado con «ANULADO», motivo y fecha | entregado (solo prueba) | `::test_el_recibo_de_un_anulado_dice_anulado_con_el_motivo` |
| 5 | Una fila `download` por descarga | entregado | `::test_una_descarga_deja_exactamente_una_fila_download`; SQL vivo `download` 3 |
| 6 | member 403, 401, 404 | entregado | `::test_member_recibe_403_sin_auditar_y_sin_token_401`, `::test_un_pago_inexistente_da_404_json_y_no_audita`; V6 |
| 7 | Licencias (`fpdf2`, `python-telegram-bot` fuera; `pypdf` solo dev) | entregado | `test_licenses.sh`, `test_third_party_confinement.py` |
| 8 | Generar < 1 s | **parcial** | Sin medición ni prueba `perf` (V7 no lo incluye). Plausible (1,9 KB, sin dependencias), no probado |

**US-138 · Exportar socios a CSV (B12 `00b4289`, F4)** — 8/8 entregado (E2E PENDIENTE V5)

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | 200 admin, 403 coach, 401 | entregado | `tests/members/test_export.py::test_el_coach_recibe_403_y_no_se_descifra_ni_se_audita_nada`, `::test_member_recibe_403_y_sin_token_401`; V6 |
| 2 | Filtros de la lista; bajas solo con su filtro | entregado | `::test_sin_filtro_no_salen_los_dados_de_baja_y_con_status_deleted_solo_ellos`, `::test_los_filtros_son_los_de_la_lista` |
| 3 | Lotes de 500 con `batch_id` en `crypto_ops` | entregado | `::test_501_socios_se_descifran_en_un_lote_de_500_y_otro_de_1`; SQL vivo 12 `decrypt` `purpose=export` |
| 4 | Auditoría `export` (apertura y cierre, D82) | entregado | `::test_la_exportacion_deja_la_fila_de_apertura_y_la_de_cierre`; SQL vivo 8 = 4 × 2 |
| 5 | Escape de fórmulas | entregado | `::test_los_valores_con_disparador_de_formula_salen_con_apostrofo_l6`; V6 |
| 6 | 1.000 socios < 10 s | entregado | `test_export_perf.py`; V7 (dos corridas) |
| 7 | Streaming, nada en disco ni logs | entregado | `::test_el_generador_abre_su_propia_sesion_al_menos_una_por_lote`, `::test_si_el_cliente_se_desconecta_a_mitad_el_cierre_queda_y_el_flujo_se_libera` |
| 8 | Botón oculto al coach; confirmación | entregado (unidad); E2E **PENDIENTE (V5)** | F4 `ExportButton.test.tsx`; `stack/members-export.spec.ts` |

**US-139 · Exportar pagos a CSV (B12, F4)** — 7/7 entregado (E2E PENDIENTE V5)

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | 200 admin, 403 coach, 401 | entregado | `tests/payments/test_export.py::test_coach_y_member_reciben_403_sin_auditar_y_sin_token_401` |
| 2 | Suma de no anulados = `summary.total` | entregado | `::test_la_suma_y_el_conteo_de_los_no_anulados_cuadran_con_summary_cruzando_medianoche`; V6 (`awk`: nov 735.000 / 7; oct 1.245.000 / 10 + 1 anulado) |
| 3 | `monto_cop` entero | entregado | `::test_admin_descarga_el_csv_del_mes_con_las_nueve_columnas_de_n29`; V6 |
| 4 | Anulados con `si` y motivo | entregado | `::test_los_anulados_salen_con_anulado_si_y_su_motivo`; V6 |
| 5 | Sin documento, teléfono ni correo | entregado | `::test_el_csv_no_trae_documento_telefono_ni_correo_del_socio` |
| 6 | Auditoría `export` | entregado | `::test_la_exportacion_deja_la_fila_de_apertura_y_la_de_cierre`; SQL vivo 4 = 2 × 2 |
| 7 | Fechas mal formadas 422 | entregado | `::test_rangos_invalidos_dan_422_con_field`; V6 |

### Resumen del Pilar 1

- Criterios: **139/147 entregados**, 7 parciales (121.7, 124.4, 124.5, 124.7, 126.3, 129.6, 137.8), 1 «no» con decisión (127.7). E2E **PENDIENTE (V5)** en 127.9, 132.3 y 138.8 (más recibo y exportaciones por la DoD); CI **PENDIENTE (V9)** en 134.2.
- Historias: **14/20 COMPLETE** (120, 122, 123, 125, 128, 130, 131, 132, 133, 134, 135, 136, 138, 139); **6 PARTIALLY_COMPLETE** (121, 124, 126, 127, 129, 137). Ninguna NOT_IMPLEMENTED ni IMPLEMENTED_INCORRECTLY.
- Épicas: EP-15 COMPLETE (4/4). EP-14 PARTIAL (8/13 historias completas; valor de negocio entregado: avisos, WhatsApp, correo con opt-in, resumen de Telegram, cuentas por correo, KPI). EP-16 PARTIAL (2/3; el parcial es solo la medición del recibo < 1 s).
- Contrato: las 15 rutas nuevas y los cambios (`email_sent`, `notifications_today`, `members_without_consent`, `crypto`) están en `docs/openapi.json`. Migraciones `0015`–`0019` más `0020` (V8, S5-D255) en `apex-db-1` y en el ensayo (`0020_notifications_indexes`).

### DoD de `SPRINT-05.md` (seis puntos)

| # | Punto | Estado | Evidencia |
|---|---|---|---|
| 1 | DoD común: `run-gates.sh`, arquitectura, ciclo de Alembic, OpenAPI, licencias (OpenBao MPL-2.0) | **PENDIENTE (V9)** | Tres `run-gates` registrados (B3: 6.658, 95,0 %; B8: 7.661, 95,3 %; B12: 7.917, 95,2 %); ciclo de Alembic V2.3; licencias W0-1. Falta la cuarta corrida sobre el árbol fusionado (front F1–F5 y V10) |
| 2 | E2E: por avisar hoy (WhatsApp y omitir), recibo, exportación | **PENDIENTE (V5)** | `web/tests/e2e/stack/{avisos,payments-receipt-export,members-export,users-activation,home}.spec.ts` escritas; preview verdes en F1–F5 |
| 3 | Smoke con OpenBao | entregado | V2.6 `prod-smoke.sh --provider openbao` 180 ok (incluye `openbao-smoke.sh`); V3 (sellado con api arriba, api reiniciado sellado, 503, desello 8 s y 12 s). El smoke aún no apila el overlay (`kek.bin` «omitida»); lo cubre V3 |
| 4 | `notify` ×2 el mismo día sin duplicar | entregado | V4; vivo: `worker.job_runs` del ensayo `notify ok` con dos intentos (18:23 y 18:44Z), duplicados 0 |
| 5 | Revisión de seguridad de los seis puntos | entregado | DECISIONES «S5-V10 · Revisión de seguridad DoD del backend» (0 C / 0 H / 0 M / 2 L) |
| 6 | `verify-delivery` sobre el stack con OpenBao | en curso | este documento; se cierra tras V5 y V9 |

### Demos 1 a 5

| Demo | Estado | Evidencia |
|---|---|---|
| 1 · OpenBao | entregado | V2.5, V3; reanudación por prueba citada; SQL vivo (`openbao` 8/8, `kek_local` 1, job `done 8/8`) |
| 2 · Avisos | entregado con nota | V4 (correo con opt-in, Telegram sin nombres); `wa-link` y `skip` en vivo solo en B7.7 (ensayo destruido por V2); se repiten en V5. «Enviar por WhatsApp» ignora `whatsapp.enabled` (MAJOR-1) |
| 3 · Cuentas por correo | entregado | V4 |
| 4 · Recibo y CSV con cuadre | entregado | V6 + SQL vivo |
| 5 · Inicio con los dos KPI | entregado (api); front **PENDIENTE (V5)** | B10 en vivo (9 y 1 = SQL); `home.spec.ts` |

## 2. Pilar 2 · Sistema real (lectura del 2026-11-05 ~19:10Z)

| # | Comprobación | Resultado | Estado |
|---|---|---|---|
| P2-1 | Imágenes vigentes | `apex-api:local` `4b5f6d77f672` (label `revision e2a6329`) en api y worker de `apex` y del ensayo; `apex-web:local` `41489ba76e66` (`e2a6329`); `apex-backup:local` `e4b7372848c3` (**sin label de revisión**: su Dockerfile no lleva `LABEL`); `openbao/openbao:2.7.2`. `/health.version = e2a6329` en 8181 y 8280. HEAD `4b08f02`: `git diff e2a6329..HEAD -- api web infra` = solo el borrado de `channels/whatsapp_link.py` (stub sin importadores, S5-D263); el resto son docs. Equivalente en ejecución; **V12 reconstruye con el SHA de cierre** | entregado con nota |
| P2-2 | `/health` | 8181 y 8280: 200 `{status ok, db ok, migrations ok, crypto ok, backup attention}`. `attention`: el último `backup_check` corrió a las 18:23Z (`missing`) y los respaldos son de 18:30 y 18:43Z; la siguiente corrida diaria lo refresca | entregado con nota |
| P2-3 | Avisos generados | Ensayo: 6 `whatsapp_link pending`, `audit_log insert` 6, duplicados 0 | entregado |
| P2-4 | `wa-link`, `skip`, PATCH canales | En vivo en B7.7 y B5.7 sobre el ensayo anterior; el ensayo actual (recreado en V2) tiene 0 `reveal`, 0 `sent`/`skipped`, 0 preferencias | **PENDIENTE (V5)** |
| P2-5 | `forgot` y alta con `email_sent` | V4 sobre `apex_avisos_demo` (desechable, borrada) con Mailpit | entregado (evidencia de V4) |
| P2-6 | Recibo | SQL vivo `download payments.payments` 3 | entregado |
| P2-7 | Export socios y pagos | SQL vivo: `export members.members` 8, `export payments.payments` 4, `crypto_ops export decrypt ok` 12; 409 (V6) | entregado |
| P2-8 | `migrate-provider` y `retire-local-kek` | SQL vivo: `crypto_keys` `openbao` 5 + 3 `active`; `crypto_jobs migrate_provider done 8/8`; auditoría de `crypto.crypto_keys`: `update local→openbao 8/8`, `update kek_local: retirada` (1), `verify` ×3, `export` ×2 | entregado |
| P2-9 | `rotate-kek` y `--trim` | Solo B2.7 (ensayo anterior: `version 2`, `rewrap 8/8`, `min_decryption_version 2`); el ensayo actual no tiene job `rewrap` ni auditoría `rotate_kek` | entregado (evidencia histórica, no repetido tras V2) |
| P2-10 | Snapshot de OpenBao en el respaldo | `apex-ensayo-backup-1:/data/backups/latest.json` = `apex-20261105-184323` con `openbao_snapshot.verified = true`, `.snap.age` 31.043 B y `latest.json.minisig` | entregado |
| P2-11 | `notify` ×2 e idempotencia | `notify ok` con dos intentos el mismo día, sin duplicados; `seed-notifications` 2/5 `insert` exactos (B6.8 2/5 y 0/0); `generate` 0 en la segunda corrida (B7.7, V4); export 409 (V6) | entregado |
| P2-12 | Secretos en logs | `docker logs` de api, worker, openbao y backup del ensayo y api/worker de `apex`: 0 de `hvs.`, `AGE-SECRET`, `X-Vault-Token:` | entregado |
| P2-13 | Desarrollo (`apex`) | `crypto_keys` `local` 8 (por diseño, D68); `notification_templates` 0 y `notify` con `sin_reglas = 1`: el downgrade de V2.3 borró el esquema y no se re-sembró | observación |

**Pilar 2: 11/13 entregados (P2-4 PENDIENTE V5; P2-13 observación).**

## 3. Hallazgos nuevos de esta verificación

- **MAJOR-1 · Interruptores de canal sin efecto.** `settings.channels.whatsapp.enabled`, `whatsapp.country_code` y `telegram.enabled` se validan, guardan y muestran en la pestaña Canales, pero ningún código los lee (en `api/src/app` solo `email.enabled`, `notifications/sending.py:397,428`). Con el valor por defecto `whatsapp.enabled = false` (sin fila `channels` en el ensayo) se generaron 6 avisos `whatsapp_link` y `wa-link` responde; `whatsapp.build_link` usa `COUNTRY_CODE = "57"` fijo; el sink de Telegram se registra solo por entorno. Contradice US-124.5 y la intención de US-122; ninguna decisión S5 lo acepta. Riesgo: el admin apaga WhatsApp o Telegram en Config y nada cambia. Acción: respetar el interruptor (`generate`, `wa_link`, sink) o quitar los campos del esquema y de la pestaña, o aceptar con dueño.
- **MINOR-1 · Deriva documental.** US-122 no tiene nota «Corregido en S5» aunque choca con D30/D204/D231/D28; US-124 (4, 5), US-126 (3) y US-127 (7) no reflejan lo implementado (D217 punto 11, D206).
- **MINOR-2 · Sin prueba:** US-121.7, US-124.7, US-129.6 y US-137.8.
- **OBS-1** `apex-backup:local` sin `org.opencontainers.image.revision`: no se puede atar a un SHA por `docker inspect`.

## 4. Pasos humanos declarados

1. Custodia de las 5 llaves de desello 2/2/1 (titular, operador, tercero) — S5-D106, Q10, ADR-005.
2. Ensayo de `rekey` por una segunda persona — S5-D106, plan V11.
3. Desello del ensayo si queda sellado (llaves en `docs/scratch/ensayo/openbao/`; V12 las borra).
4. ADR-005 punto 2 (cambiar un ADR exige preguntar, S4B-D47).
5. Push, PR con la CI en verde (`api` con 0 saltos de `openbao`, S5-D264; `prod-smoke` con `openbao-smoke`), merge y firma de la etiqueta `v0.2.0` (S5-D93, D83; si no firma, v0.3 con el titular).
6. Titular de `LICENSE`, `allowed_signers`, N-6/N-7 (heredados del 4B).
7. Regla `eslint` de imports (S4B-D197) y restauración por otra persona (S4B-D210), heredados.
8. Traspaso de servidores existentes a `apex_owner` con `infra/db/reown.sql` (S5-D143, D146) y migración real a OpenBao con el orden de `.env` de V2.

## 5. Deudas aceptadas con dueño (v0.3 salvo indicación)

- Índice `memberships(end_date)` y CHECK `status='sent' ⇒ sent_at` (B7, MEDIUM BD 4 y LOW BD 9; S5-D226).
- SMTP 465 / TLS implícito (S5-D207). Volumen `keys` con `subpath` para separar JWT y custodia (S5-D201).
- TLS en `custody` y Caddy (EP-20, titular), AppRole y rotación de tokens (operador), `audit.append()` y trazabilidad por socio de las exportaciones (titular), `display_name` (titular), retención de `rendered_body` (L-4, titular) — S5-D83, D63. Índices de `audit_log`: V7 no los pidió.
- LOW aceptados de V8 (índices del historial y de reglas, dueño v0.3 EP-14) y de V10 (segundo listener 8210, D107; `set -uo` en scripts de prueba; `single_flight` por proceso, D258, dueño: quien añada réplicas; `useBlobDownload` por instancia, dueño: quien lo reutilice).
- BRECHAS §13: 13.6 y 13.11 aceptadas con dueño; 13.17 abierta (entrada «Por avisar hoy» del SideNav hasta v0.4, Q25).

## 6. Veredicto provisional

- Pilar 1: 139/147 criterios; 14/20 historias COMPLETE y 6 PARTIALLY_COMPLETE; DoD 3/6 entregados + 1 en curso + 2 PENDIENTE (V5, V9); demos 5/5 con nota en la 2 y el front de la 5 en V5.
- Pilar 2: 11/13 (P2-4 PENDIENTE V5; P2-13 observación).
- **Provisional: NOT_READY_FOR_RELEASE** mientras falten V5 y V9 y MAJOR-1 no tenga decisión. Pasa a **READY_WITH_WARNINGS** si: (a) V5 dos corridas verdes en el ensayo (incluye `wa-link`, `skip`, PATCH de canales, recibo, exportaciones y `home`); (b) V9 `run-gates` 4/4 con cobertura ≥ 80 % en los módulos nombrados y la CI con 0 saltos de `openbao`; (c) MAJOR-1 corregido o aceptado con dueño en DECISIONES; (d) los parciales anotados con dueño. Para **READY** harían falta además: cerrar 124.4, 124.5 y 124.7, la política de reintento de Telegram (126.3) o su enmienda, las pruebas de 121.7, 129.6 y 137.8 y enmendar US-122, US-124, US-126 y US-127.
