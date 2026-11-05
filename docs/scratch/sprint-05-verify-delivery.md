# verify-delivery · Sprint 5 (v0.2: OpenBao, avisos, recibos y exportaciones)

- Rama `feat/sprint-05-openbao-avisos-recibos`, HEAD `b3a71c9` (58 commits sobre `main`, que sigue en `a1ad4cb`). Borrador provisional sobre `4b08f02` (2026-11-05 ~19:00Z); cierre final sobre `b3a71c9` (2026-11-05, paso V11).
- Alcance: paso V11 de `docs/ddd/blueprints/sprint-05-plan.md` (líneas 1538–1542). Pilar 1: US-120 a US-139 criterio por criterio (147 criterios), DoD de `SPRINT-05.md` (seis puntos) y demos 1 a 5. Pilar 2: sistema vivo (`apex` en 8181 y `apex-ensayo` en 8280 con overlay OpenBao).
- Método: lectura de `SPRINT-05.md`, criterios de las 20 historias (con sus notas «Corregido en S5-W0-1», «Corregido en S5» y «Corregido en S5-V11c»), bloque S5 de `DECISIONES.md` (D1..D270, revisiones, aceptados con dueño), `docs/scratch/sprint-05.md` (W0-1..W0-4, B1, B13, B2..B12, V2..V10, **V11c Rojo/Verde/Revisiones, V9 gates completos, V5 E2E**), `docs/scratch/sprint-05-front.md`, `BRECHAS.md` §13, `docs/openapi.json`, `.github/workflows/ci.yml` y `git log main..HEAD`; nombres de prueba por `grep`. Solo lectura del repo y de Docker. En el cierre: `docker ps`, `docker inspect` y `curl /health` de 8181 y 8280; sin `psql` (otro agente hace `rotate-kek` y V12 en paralelo). No se corrió pytest, npm ni Playwright; no se escribió en ninguna base.
- Convención (la del 4A y 4B): **entregado** (criterio vigente con prueba o evidencia en vivo), **parcial** (falta parte del criterio, su prueba o su ejecución; se dice si hay decisión y dueño), **no**. «Criterio vigente» = el de la historia corregido por sus notas y por las decisiones S5 que lo enmiendan.
- Cambios de código después de V9 (`051751a`): `43113df` (versión de ruff del hook y tres saltos de línea finales, uno en `infra/openbao/config.hcl`), `e411df0` (versión 0.2.0 en `pyproject`, `package.json`, locks y CHANGELOG) y `b3a71c9` (solo specs E2E y cuaderno). `git diff --stat 051751a..HEAD -- api/src web/src infra` = 1 línea de `config.hcl`. Los gates de V9 siguen siendo válidos para el código en ejecución.

## 1. Pilar 1 · Historias y criterios

### EP-15 · Custodia de llaves con OpenBao

**US-133 · Servicio OpenBao con Transit (W0-2, `e40c5f3`)** — 7/7 entregado

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Sin puertos publicados; solo api y worker por `custody` | entregado | `scripts/ci/test_compose_config.sh` (240/0, W0-2; V9 «0 fallas»); W0-2.7: desde el api `openbao:8200` 200 y `8210` rechazado; `backup` en `custody` aceptado (S5-D175, D180) |
| 2 | `bootstrap.sh` idempotente | entregado | S5-D76 (`--first-install` + `INICIALIZAR`); `test_openbao_infra.sh` (101 ok en V9); `--reissue-tokens` repetido en B13.7 y B2.7 sin crear llaves |
| 3 | (enmendado S5-D2) una llave `apex-kek` + `apex-sign-audit` | entregado (desvío decidido) | S5-D2; W0-2.7, V2.5; la CI las crea (S5-D264) |
| 4 | Política sin exportar ni administrar | entregado | S5-D52, D191; `test_openbao_infra.sh`; `openbao_restore_e2e.sh`: token de api 403 a la instantánea, de backup 403 a `decrypt` |
| 5 | Llaves de desello y raíz nunca en repo, imagen ni logs | entregado | W0-2.7 (`LogConfig.Type=none`, grep 0), S5-D103 (`read -rs`), raíz revocada; V9 gitleaks limpio y `check-image-secrets.sh` ×3; V9 desello por `wget --post-file` sin imprimirlas |
| 6 | Reinicio → sellado; desello con 3 de 5 | entregado | W0-2.7, V3 (dos ciclos), V9 cierre del ensayo (llegó sellado, desellado 3/5), `openbao-smoke.sh` en `prod-smoke.sh --provider openbao` (V2.6, 180 ok) |
| 7 | Versión fijada y MPL-2.0 en `NOTICE` | entregado | `openbao/openbao:2.7.2`; V9 `test_images_pinned` ok, NOTICE sin diff |

**US-134 · Proveedor OpenBao (B1, `2390d22`)** — 7/7 entregado

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Con `CRYPTO_PROVIDER=openbao` los cinco campos se leen y escriben igual | entregado | B2.7, V2.5, V3, V6; V5 en el ensayo con OpenBao: `members-export` (descifra) y WhatsApp (descifra teléfono) verdes |
| 2 | Suite de contrato contra local y OpenBao real | entregado (CI remota: paso humano) | `tests/crypto/test_provider_contract.py`; V9 en Linux con OpenBao 2.7.2 real y token no raíz: 434 passed, 8 skipped (solo ramas «no aplica» del contrato), **0 saltos de `openbao`**; `ci.yml:120-121` exporta `OPENBAO_TEST_ADDR`/`OPENBAO_TEST_TOKEN_FILE` y el paso de la línea 136 falla si un salto se debe a su falta (S5-D264). La corrida en GitHub llega con el push |
| 3 | Nada fuera de `core/crypto` cambia; `banned-api` verde | entregado | `test_third_party_confinement.py`, `test_crypto_bus_importers.py`; V9 arquitectura y ruff verdes |
| 4 | Token por archivo; fuera de logs y `crypto_ops` | entregado | `test_openbao_provider.py`; `test_kek_path_single_door.py`; grep vivo 0 |
| 5 | Timeout → error de dominio y `crypto_ops` `error` | entregado | `test_openbao_provider.py` (tabla de `map_error`), S5-D162..D168 |
| 6 | `crypto_keys` solo metadatos y `vault:v<n>:` | entregado | SQL vivo del ensayo (borrador): 8 filas `openbao`, `wrapped_material` empieza por `vault:` |
| 7 | Proveedor desconocido no arranca y lo nombra | entregado | `tests/crypto/test_provider_startup.py::test_proveedor_desconocido` |

**US-135 · Migrar proveedor de llaves (B2, `7c13e67`)** — 8/8 entregado

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Todo `openbao`; blobs sin recifrar | entregado | SQL vivo: `openbao encrypt 5`, `openbao index 3`; `test_migrate_provider.py` |
| 2 | Borrar la KEK local y reiniciar no afecta | entregado | V3 (`retire-local-kek`, `kek.bin` ausente, reinicios, `GET /members/{id}` 200); `test_retire_local_kek_cli.py::test_despues_del_retiro_el_keyring_carga_con_openbao_sin_el_archivo` |
| 3 | Segunda corrida «nada que migrar», 0 | entregado | V2.5 y V3; `test_migrate_provider_cli.py::test_la_segunda_corrida_dice_nada_que_migrar_y_sale_0` |
| 4 | Interrumpir y reanudar | entregado (solo prueba, como pide el plan) | `test_migrate_provider.py::test_una_interrupcion_a_la_mitad_se_reanuda_hasta_done_igual_a_total` |
| 5 | `CryptoJob` con total, done, fechas, error | entregado | SQL vivo: `migrate_provider done 8/8` |
| 6 | `unwrap`+`wrap` con mismo `batch_id`; auditoría con `--as` | entregado | SQL vivo: 80 filas en 4 `batch_id`; `audit_log update {from local, to openbao, total 8, done 8}` |
| 7 | `--dry-run` sin escribir | entregado | V2.5; `test_dry_run_imprime_el_plan_sin_exigir_h1_y_sin_escribir` |
| 8 | Confirmación `MIGRAR` y precondiciones H-1 | entregado | `test_una_confirmacion_distinta_de_migrar_sale_2_sin_escribir`, `test_sin_un_verify_kek_backup_reciente_de_una_persona_sale_2`, `test_un_manifiesto_sin_firma_o_sin_instantanea_valida_sale_2_con_el_mensaje_fijo`; V2.5 |

**US-136 · Estado degradado con OpenBao sellado (B3, `d383531`)** — 6/6 entregado

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Sellado: api arranca, `/health` 503 `crypto: sealed` | entregado | V3; `test_health_crypto.py::test_con_el_proveedor_sellado_responde_503_degraded_y_crypto_sealed` |
| 2 | `GET /members/{id}` 503 `crypto_unavailable` | entregado | V3 (`Retry-After: 30`, `no-store`); `test_errors_crypto_unavailable.py`, `tests/members/test_router_crypto_unavailable.py` |
| 3 | `GET /plans` 200 sellado | entregado | V3 |
| 4 | Desello → 200 en ≤ 25 s sin reiniciar | entregado | V3: 8 s y 12 s; B3.8: 9 s; `test_crypto_recovery.py::test_el_sondeo_espera_20_segundos_recupera_y_avisa_una_vez_por_transicion` |
| 5 | Worker no ejecuta jobs del bus sellado (D86) | entregado | `tests/worker/test_notify_sealed.py`; V3 |
| 6 | Log del cambio una vez por transición, sin datos | entregado | prueba de la fila 4; log vivo de pares `crypto_sealed`/`crypto_recovered` |

### EP-14 · Avisos de vencimiento

**US-120 · Plantillas de aviso (B6, `624ab98`)** — 9/9 entregado

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | POST 201; nombre único 409 | entregado | `test_router_templates_rules.py::test_crear_plantilla_da_201_con_el_contrato_y_no_store`, `::test_crear_plantilla_con_nombre_repetido_da_409_con_existing_id` |
| 2 | Variable desconocida 422 con `field` | entregado | `::test_crear_plantilla_invalida_da_422_con_field_y_no_crea_nada`; B6.8 |
| 3 | `render` | entregado | `test_rules_pure.py` (86); S5-D216 |
| 4 | Lista paginada con `q` | entregado | `::test_listar_plantillas_pagina_busca_y_valida` |
| 5 | PATCH auditado | entregado | `test_templates_service.py::test_update_template_audita_un_update_a_nombre_del_actor` |
| 6 | Sin `DELETE` | entregado | `::test_el_router_publica_las_nueve_rutas_de_plantillas_y_reglas` |
| 7 | Preview con contexto de ejemplo | entregado | `::test_la_vista_previa_renderiza_con_el_contexto_de_ejemplo_y_no_escribe`; B6.8 |
| 8 | Admin escribe; coach 403 al escribir, 200 al listar | entregado | `::test_el_coach_lee_y_recibe_403_al_escribir_sin_efectos` |
| 9 | Fechas ISO 8601 UTC | entregado (convención común) | `docs/openapi.json` (`date-time`) |

**US-121 · Reglas de aviso (B6)** — 11/11 entregado

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | POST 201 | entregado | `::test_crear_regla_da_201_con_el_contrato` |
| 2 | `trigger`/`channel` fuera de lista 422 (incluido `push`) | entregado | `::test_crear_regla_invalida_da_422_con_field_y_no_crea_nada`; `test_0018_notification_rules.py` |
| 3 | Signo del desfase | entregado | `test_rules_service.py::test_create_rule_con_el_signo_equivocado_da_422_y_no_escribe` |
| 4 | `template_id` inexistente 422 | entregado | `::test_create_rule_con_plantilla_inexistente_da_422_con_template_id` |
| 5 | Dos activas iguales 409 | entregado | `::test_create_rule_activa_duplicada_da_409_con_el_id_de_la_existente`, `::test_dos_altas_activas_iguales_a_la_vez_dejan_una_y_la_otra_recibe_409` |
| 6 | Lista con filtros | entregado | `::test_list_rules_aplica_los_filtros`, `::test_list_rules_pagina` |
| 7 | PATCH; desactivar no borra ni cancela avisos ya generados | entregado (S5-V11c, D267) | `tests/notifications/test_generate_rule_off.py::test_desactivar_una_regla_no_toca_los_avisos_ya_generados_y_se_envian` |
| 8 | Sin borrado | entregado | nueve rutas, sin `DELETE` |
| 9 | Siembra idempotente de cinco reglas | entregado | `test_seed_defaults.py` (9); B6.8 |
| 10 | Admin escribe | entregado | `::test_el_coach_lee_y_recibe_403_al_escribir_sin_efectos` |
| 11 | Auditado | entregado | `test_rules_service.py::test_create_rule_audita_un_insert_a_nombre_del_actor`, `::test_update_rule_aplica_solo_lo_enviado_y_audita` |

**US-122 · Configurar canales (B4, `1a75ca3`; S5-V11c)** — 7/7 entregado con desvíos decididos (nota «Corregido en S5» en la historia, `15d4731`)

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Sección cerrada con las claves de S5-D30 | entregado (desvío D30/D204) | `test_channels_schema.py` (28); B4.7. **MAJOR-1 corregido** (S5-D265): `whatsapp.enabled`, `whatsapp.country_code` y `telegram.enabled` ahora se leen (`generate`, `wa_link`, `build_link(country_code=)`, puerta de Telegram). Pruebas `test_generate_channels.py`, `test_whatsapp_country.py`, `test_alerts_telegram_gate.py`, `test_wa_link.py` |
| 2 | Nombres de secreto 422; `extra=forbid` | entregado | `test_channels_router.py::test_un_valor_invalido_o_un_secreto_da_422_con_field_sin_crear_fila`, `::test_una_clave_ajena_en_la_raiz_da_422` |
| 3 | PATCH 200 con auditoría sin secretos | entregado | `::test_la_auditoria_del_guardado_no_lleva_secretos_de_settings`; V5 usa el PATCH (`habilitarWhatsapp`) en el stack |
| 4 | `credentials_present` (D204) | entregado (desvío decidido) | `::test_el_get_refleja_las_credenciales_de_settings_sin_exponer_ningun_valor` |
| 5 | Activar sin credenciales (D231) | entregado (enmendado D231) | `::test_activar_el_correo_sin_credenciales_se_permite`; `test_notify_job.py::test_sin_credenciales_smtp_los_avisos_esperan_y_se_avisa_una_vez` |
| 6 | Solo admin | entregado | `::test_coach_403_en_get_y_patch_sin_escribir` |
| 7 | `.env.example` (D28/D64) | entregado (desvío decidido) | `.env.example:151-161`, `.env.ops.example:101,103` |

**US-123 · Preferencias de canal del socio (B5, `dc0db25`)** — 7/7 entregado

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Sin filas no hay opt-in de correo (D31) | entregado | `test_channels_rules.py` (22); B5.7 |
| 2 | PATCH; canal desconocido o `push` 422 | entregado | `test_channels_router.py`; B5.7; V5 `PATCH /members/{id}/channels` 200 en vivo |
| 3 | (enmendado N-20) baja: GET 200, PATCH 409 | entregado | `::test_el_get_responde_200_sobre_un_dado_de_baja`, `::test_el_patch_de_un_dado_de_baja_da_409_member_deleted` |
| 4 | `channels_for` solo activos; notifications no lee la tabla | entregado | `test_channels_service.py` (ahora `MemberChannelState`, D269); `test_no_cross_models.py` |
| 5 | Auditoría y `MemberUpdated` | entregado | `test_channels_service.py::test_set_channels_emite_member_updated_sin_valores`; V5: `insert` de `members.member_channel_preferences` |
| 6 | Admin y coach; member 403 | entregado | `test_channels_router.py::test_el_rol_member_recibe_403_en_las_dos_rutas` |
| 7 | Sin datos cifrados ni contacto | entregado | `0016`; `test_0016_member_channel_preferences.py` (18) |

**US-124 · Generar avisos del día (B7, B8; S5-V11c `051751a`)** — 11/11 entregado (nota «Corregido en S5-V11c» en la historia)

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | `target_dates` = `end_date + offset` | entregado | `test_rules_pure.py` |
| 2 | Un aviso por regla activa y membresía, `pending` y renderizado | entregado | `test_generate.py::test_genera_un_aviso_pendiente_con_el_texto_de_la_plantilla`, `::test_varias_reglas_para_la_misma_membresia_dan_un_aviso_por_regla`; V5 (generados 6 y 8 en el ensayo) |
| 3 | `expiring` solo vigente; `expired` solo sin renovación | entregado | `test_notification_candidates.py::test_no_se_avisa_como_vencido_a_quien_ya_renovo`, `::test_una_renovacion_pendiente_de_pago_cuenta_como_ya_renovo` |
| 4 | Canal no activo para el socio → fila `skipped` | entregado (S5-D266, D269) | `skipped canal_desactivado_socio`; `test_generate_channels.py` (8); sin consentimiento sigue sin fila (D54) |
| 5 | Canal deshabilitado en `settings.channels` → `skipped` | entregado (S5-D265) | `skipped canal_no_configurado` para correo y WhatsApp al generar; `test_generate_channels.py`; correo al enviar `test_sending.py::test_canal_apagado_en_la_configuracion_omite_aunque_haya_credenciales` |
| 6 | Único; dos corridas sin duplicar | entregado | `test_0019_notifications.py`; `test_generate_concurrency.py` (D223); V4; SQL vivo duplicados 0 |
| 7 | Congelada no genera mientras lo esté | entregado (S5-D267) | `notification_candidates` excluye `frozen`; `test_generate.py::test_una_membresia_congelada_no_genera_avisos_mientras_lo_este`, `::test_al_descongelar_la_membresia_vuelve_a_generar` |
| 8 | No descifra al generar | entregado | `test_notify_sealed.py::test_con_el_custodio_caido_genera_pero_no_envia_y_queda_ok` |
| 9 | `target_date` DATE; `created_at` UTC | entregado | `0019`; `test_0019_notifications.py` (47) |
| 10 | Auditado y `NotificationQueued` | entregado | `test_generate.py::test_notification_queued_solo_lleva_ids_canal_y_fecha_y_sale_tras_el_flush`; los `skipped` por canal no emiten el evento (D269, decidido) |
| 11 | Recupera 15 días (D220) | entregado (precisado D220) | `test_notification_candidates.py::test_la_ventana_de_vencida_va_de_hoy_menos_15_a_hoy`; `test_generate.py::test_al_registrar_el_consentimiento_la_corrida_siguiente_lo_recupera` |

**US-125 · Enviar avisos por correo (B4, B8)** — 10/10 entregado

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Éxito → `sent`, `sent_at`, `attempts+1`, `NotificationSent` | entregado | `test_sending.py::test_envia_y_marca_sent_con_hora_actor_e_intento`; V4 |
| 2 | Fallo → `failed` con código cerrado | entregado | `::test_un_fallo_deja_failed_con_el_codigo_cerrado_y_sigue_elegible` |
| 3 | Un fallo no detiene el resto | entregado | `::test_un_canal_que_lanza_cuenta_como_unknown_y_el_lote_sigue` |
| 4 | Reintento hasta el máximo; visible | entregado | `::test_al_tercer_fallo_queda_failed_para_siempre_y_emite_el_evento`, `::test_failed_de_dias_anteriores_se_reintenta_y_pending_viejo_no` |
| 5 | Contacto por `contact_for_notification`; correo nunca guardado ni en logs | entregado | `::test_service_send_pending_descifra_solo_el_correo_con_proposito_notify`, `::test_los_logs_no_llevan_correo_nombre_ni_cuerpo` |
| 6 | Timeout explícito | entregado | `tests/core/test_mail.py`; `test_email_channel.py` |
| 7 | (D231) apagado → `skipped`; sin credenciales → `pending` + alerta | entregado | `::test_canal_apagado_en_la_configuracion_omite_aunque_haya_credenciales`, `::test_canal_habilitado_sin_credenciales_espera_sin_descifrar` |
| 8 | Auditoría de envío y fallo | entregado | `::test_el_cambio_de_estado_deja_update_en_la_auditoria_por_orm` |
| 9 | Asunto renderizado | entregado | `::test_el_canal_recibe_el_correo_descifrado_y_el_texto_ya_renderizado`; V4 (Mailpit) |
| 10 | Solo en el worker | entregado | `test_worker_boundaries.py`; `::test_el_envio_ocurre_fuera_de_la_transaccion_y_sin_candado` |

**US-126 · Telegram como canal interno (B4, B8; S5-V11c)** — 6/6 entregado (nota «Corregido en S5-V11c»)

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | Envío al `TELEGRAM_CHAT_ID`; ok en el log | entregado | `tests/core/test_alerts_telegram.py`; B4.7 y V4 (`telegram-fake`) |
| 2 | Fallo registrado sin token ni URL | entregado | `::test_un_fallo_de_red_no_propaga_y_el_log_lleva_solo_el_tipo`, `::test_una_respuesta_de_error_con_el_token_en_el_cuerpo_no_llega_al_log` |
| 3 | (enmendado S5-D268) mejor esfuerzo, sin reintentos; cola acotada y deduplicación (D206) | entregado (enmienda decidida) | S5-D268; nota en la historia (`d6f14fc`); `test_alerts_telegram.py`. Además `telegram.enabled` apaga el sink (D265d): `test_alerts_telegram_gate.py` (6) |
| 4 | Token nunca en base, auditoría ni logs | entregado | `test_alerts_telegram.py`; B4.7 y B8 (`grep bot123` 0) |
| 5 | CI de licencias rechaza `python-telegram-bot` | entregado | `scripts/ci/test_licenses.sh` caso 1b; V9 ok |
| 6 | Timeout 10 s | entregado | `::test_usa_la_base_configurada_y_el_timeout` |

**US-127 · Por avisar hoy y enlace de WhatsApp (B7, F1; S5-V11c)** — 9/9 entregado (nota «Corregido en S5-V11c»)

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | `today` (D219) | entregado (precisado D219) | `test_today_and_skip.py::test_hoy_incluye_pendientes_y_fallidos_de_hoy_y_fallidos_anteriores`, `::test_hoy_pagina_con_limit_y_offset` |
| 2 | Sin teléfono ni correo | entregado | `::test_cada_fila_trae_el_nombre_del_socio_y_ningun_dato_de_contacto` |
| 3 | POST `wa-link` descifra con `notify`, `{url}`, marca `sent` | entregado | `test_wa_link.py::test_devuelve_la_url_y_marca_sent_con_quien_y_cuando`, `::test_cada_llamada_audita_reveal_y_escribe_crypto_ops_solo_del_telefono`; **V5 en vivo**: 200, aviso `sent`, `reveal {"field":"phone","purpose":"notify"}` sin el número, `update` pending→sent con `sent_by`. Con el canal apagado 409 `channel_disabled` antes de descifrar (D265b) |
| 4 | Repetir: misma URL, sin cambiar `sent_at`, con auditoría | entregado | `::test_la_segunda_llamada_devuelve_la_misma_url_sin_cambiar_la_marca`; B7.7 |
| 5 | `skipped` → 409 | entregado | `::test_un_aviso_omitido_da_409_sin_descifrar_nada` |
| 6 | Sin teléfono 422 `member_without_phone` | entregado | `::test_un_socio_sin_telefono_da_422_y_el_aviso_sigue_pendiente`; indicativo distinto de 57 siempre nacional (D270), `test_whatsapp_country.py` |
| 7 | (enmendado S5-D217/D268) aviso `email` → 409 `wrong_channel` | entregado (desvío decidido, nota en la historia) | `::test_un_aviso_de_correo_da_409_sin_descifrar_nada`; F1 no ofrece el botón |
| 8 | Admin y coach; member 403 | entregado | `test_router_notifications.py::test_member_recibe_403_en_todo_sin_efectos` |
| 9 | Abre `wa.me` solo tras el 200 | entregado | `WaButton.test.tsx`; **V5** `stack/avisos.spec.ts` verde ×2 en el ensayo |

**US-128 · Omitir aviso con motivo (B7, F1)** — 5/5 entregado

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | `skip` 3–500, `sent_by`, `NotificationSkipped` auditado | entregado | `test_today_and_skip.py::test_omitir_un_aviso_pendiente_o_fallido_lo_deja_skipped_con_su_motivo`, `::test_omitir_deja_un_update_auditado_a_nombre_de_quien_omite`; **V5 en vivo**: `POST .../skip` 200, `update` pending→skipped con `skip_reason` |
| 2 | Sin motivo 422 | entregado | `::test_skip_con_un_cuerpo_invalido_da_422_y_no_cambia_el_aviso` |
| 3 | `sent`/`skipped` 409 | entregado | `::test_skip_de_un_aviso_cerrado_da_409_y_de_uno_inexistente_404` |
| 4 | Desaparece de hoy, queda en historial | entregado | `::test_un_omitido_deja_de_aparecer_en_por_avisar_hoy`; V5 `avisos.spec.ts` |
| 5 | Admin y coach; member 403 | entregado | `::test_admin_y_coach_pueden_las_seis_operaciones` |

**US-129 · Historial de envíos (B7, F2)** — 6/6 entregado

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | Filtros, paginación y orden | entregado | `test_history_and_member_tab.py` |
| 2 | Rango invertido o `limit` fuera 422 | entregado | `test_router_notifications.py::test_parametros_invalidos_dan_422` |
| 3 | Campos sin contacto | entregado | `::test_get_devuelve_el_aviso_con_el_nombre_y_sin_contacto` |
| 4 | Detalle con `rendered_body` | entregado | `::test_el_detalle_devuelve_el_aviso_y_404_si_no_existe` |
| 5 | Admin y coach; member 403 | entregado | `::test_member_recibe_403_en_todo_sin_efectos` |
| 6 | 10.000 avisos por socio < 500 ms | entregado | `api/tests/notifications/test_history_perf.py::test_el_historial_de_un_socio_con_diez_mil_avisos_responde_en_menos_de_500_ms_p95` (`7deb573`, 10.000 avisos, 1 passed; antes 1.000) (S5-V11c): p95 de 20 = 0,12 s, pero con `AVISOS = 1_000` (línea 24), una décima del volumen del criterio (US-129 línea 38). Índice `ix_notifications_member_target_date` (`0019`) y consulta paginada hacen muy probable el cumplimiento, pero no está medido a 10.000 ni hay decisión que rebaje el volumen. Ver MINOR-3 |

**US-130 · Pestaña Avisos de la ficha (B7, F3)** — 5/5 entregado

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | Misma forma y paginación | entregado | `test_history_and_member_tab.py::test_la_pestana_trae_solo_los_avisos_del_socio_del_mas_nuevo_al_mas_viejo` |
| 2 | Inexistente 404; de baja muestra historial | entregado | `::test_la_pestana_de_un_socio_inexistente_es_404`, `::test_la_pestana_incluye_a_un_socio_dado_de_baja` |
| 3 | Pestaña sin contacto | entregado | `NotificationsTab.test.tsx`; preview `member-tabs.spec.ts` (V5 preview 189/189) |
| 4 | Admin y coach; member 403 | entregado | `test_router_notifications.py` |
| 5 | Carga diferida | entregado | `NotificationsTab.test.tsx` |

**US-131 · Recuperar y activar cuenta por correo (B9 `8860b03`, F5)** — 6/6 entregado

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | `forgot` envía a activa; nada a inexistente; 204 siempre | entregado | `tests/auth/test_forgot_delivery.py` (15); V4 |
| 2 | Alta y reenvío envían y devuelven el enlace | entregado | `test_user_link_mail.py::test_post_users_con_smtp_y_canal_responde_201_con_email_sent_true`, `::test_el_reenvio_http_con_smtp_y_canal_envia_y_responde_email_sent_true`; V4; V5 `users-activation.spec.ts` |
| 3 | Token fuera de logs y auditoría | entregado | `::test_el_enlace_enviado_nunca_aparece_en_los_logs`, `test_forgot_delivery.py::test_ni_el_enlace_ni_el_correo_llegan_a_los_logs`; V4 |
| 4 | Correo apagado o fallido: 204 / `email_sent=false` | entregado | `::test_post_users_sin_smtp_responde_201_con_email_sent_false`, `test_forgot_delivery.py::test_un_fallo_de_smtp_no_cambia_la_respuesta` |
| 5 | Enlace usado o vencido | entregado (heredado S2) | `ResetPage.test.tsx` |
| 6 | Sexto `forgot` por IP 429 | entregado (heredado S2) | `test_reset_forgot_router.py::test_forgot_el_sexto_por_ip_da_429`; V5 restauración: 6 logins → `401 ×5, 429` |

**US-132 · KPI por avisar en Inicio (B10 `8eff83e`, F3)** — 4/4 entregado

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | `notifications_today` = total de `today` | entregado | `tests/dashboard/test_service.py`, `test_router.py::test_get_dashboard_trae_los_dos_kpi_enteros_y_con_los_valores_sembrados`; B10 en vivo |
| 2 | Contrato sin otros cambios | entregado | `docs/openapi.json`; `::test_el_cuerpo_tiene_las_claves_del_contrato_y_los_tres_futuros_en_null` |
| 3 | Tarjeta a `/avisos/hoy`; «Nadie por avisar» | entregado | `NotificationKpis.test.tsx`; **V5** `stack/home.spec.ts` verde ×2 (el ajuste de `b3a71c9` corrige la consulta SQL de la prueba, no el producto) |
| 4 | Admin y coach | entregado | `::test_el_coach_recibe_los_dos_kpi_igual_que_el_admin` |

### EP-16 · Recibos y exportaciones

**US-137 · Descargar recibo (B11 `a098f67`, F4)** — 8/8 entregado

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | 200 `application/pdf` admin y coach | entregado | `test_router_receipt.py::test_admin_y_coach_descargan_el_recibo`; V6; V5 `payments-receipt-export.spec.ts` |
| 2 | Monto, medio, referencia, fecha Bogotá, nombre | entregado | `test_receipt_pure.py` (30), `test_receipt_service.py::test_el_recibo_trae_frase_id_socio_plan_medio_referencia_y_monto`; V6 |
| 3 | Sin documento, teléfono, correo ni cifrados | entregado | `::test_el_recibo_no_lleva_documento_telefono_correo_ni_contacto_de_emergencia`; V6 |
| 4 | Anulado con «ANULADO», motivo y fecha | entregado (prueba) | `::test_el_recibo_de_un_anulado_dice_anulado_con_el_motivo` |
| 5 | Una fila `download` por descarga | entregado | `::test_una_descarga_deja_exactamente_una_fila_download`; SQL vivo `download` 3 |
| 6 | member 403, 401, 404 | entregado | `::test_member_recibe_403_sin_auditar_y_sin_token_401`, `::test_un_pago_inexistente_da_404_json_y_no_audita`; V6 |
| 7 | Licencias | entregado | `test_licenses.sh`, `test_third_party_confinement.py`; V9 pip-audit 0 y licencias ok |
| 8 | Generar < 1 s | entregado (S5-V11c) | `api/tests/payments/test_receipt_perf.py::test_el_recibo_responde_en_menos_de_1_s_p95`: p95 de 20 = 0,51 s (marcada `perf`, no gate; S2-D27) |

**US-138 · Exportar socios a CSV (B12 `00b4289`, F4)** — 8/8 entregado

| # | Criterio vigente | Estado | Evidencia |
|---|---|---|---|
| 1 | 200 admin, 403 coach, 401 | entregado | `tests/members/test_export.py::test_el_coach_recibe_403_y_no_se_descifra_ni_se_audita_nada`, `::test_member_recibe_403_y_sin_token_401`; V6 |
| 2 | Filtros de la lista; bajas solo con su filtro | entregado | `::test_sin_filtro_no_salen_los_dados_de_baja_y_con_status_deleted_solo_ellos`, `::test_los_filtros_son_los_de_la_lista` |
| 3 | Lotes de 500 con `batch_id` | entregado | `::test_501_socios_se_descifran_en_un_lote_de_500_y_otro_de_1`; SQL vivo 12 `decrypt` `purpose=export` |
| 4 | Auditoría `export` (D82) | entregado | `::test_la_exportacion_deja_la_fila_de_apertura_y_la_de_cierre`; SQL vivo 8 = 4 × 2 |
| 5 | Escape de fórmulas | entregado | `::test_los_valores_con_disparador_de_formula_salen_con_apostrofo_l6`; V6 |
| 6 | 1.000 socios < 10 s | entregado | `test_export_perf.py`; V7 |
| 7 | Streaming, nada en disco ni logs | entregado | `::test_el_generador_abre_su_propia_sesion_al_menos_una_por_lote`, `::test_si_el_cliente_se_desconecta_a_mitad_el_cierre_queda_y_el_flujo_se_libera` |
| 8 | Botón oculto al coach; confirmación | entregado | `ExportButton.test.tsx`; **V5** `stack/members-export.spec.ts` verde ×2 sobre OpenBao |

**US-139 · Exportar pagos a CSV (B12, F4)** — 7/7 entregado

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | 200 admin, 403 coach, 401 | entregado | `tests/payments/test_export.py::test_coach_y_member_reciben_403_sin_auditar_y_sin_token_401` |
| 2 | Suma de no anulados = `summary.total` | entregado | `::test_la_suma_y_el_conteo_de_los_no_anulados_cuadran_con_summary_cruzando_medianoche`; V6 (`awk`) |
| 3 | `monto_cop` entero | entregado | `::test_admin_descarga_el_csv_del_mes_con_las_nueve_columnas_de_n29`; V6 |
| 4 | Anulados con `si` y motivo | entregado | `::test_los_anulados_salen_con_anulado_si_y_su_motivo`; V6 |
| 5 | Sin documento, teléfono ni correo | entregado | `::test_el_csv_no_trae_documento_telefono_ni_correo_del_socio` |
| 6 | Auditoría `export` | entregado | `::test_la_exportacion_deja_la_fila_de_apertura_y_la_de_cierre`; SQL vivo 4 = 2 × 2 |
| 7 | Fechas mal formadas 422 | entregado | `::test_rangos_invalidos_dan_422_con_field`; V6; V5 `payments-receipt-export.spec.ts` |

### Resumen del Pilar 1

- Criterios: **147/147 entregados**, 0 parciales (129.6 cerrado en `7deb573`: la prueba `perf` mide con 10.000 avisos), 0 «no». Respecto del borrador: 121.7, 124.4, 124.5, 124.7 y 137.8 cerrados por S5-V11c (D265–D267, pruebas nuevas); 126.3 y 127.7 por enmienda decidida (D268, D217) con nota en la historia; 127.9, 132.3 y 138.8 por V5; 134.2 por V9 en Linux con OpenBao real (0 saltos) y `ci.yml` (S5-D264).
- Historias: **20/20 COMPLETE** (US-129 cerrada con la medición a 10.000 avisos, `7deb573`). Ninguna NOT_IMPLEMENTED ni IMPLEMENTED_INCORRECTLY.
- Épicas: **EP-15 COMPLETE** (4/4). **EP-16 COMPLETE** (3/3). **EP-14 PARTIAL** formalmente (12/13 historias completas); el valor de negocio está entregado entero (plantillas y reglas, canales que se respetan, avisos, WhatsApp, correo con opt-in, resumen de Telegram con interruptor, cuentas por correo, historial, KPI); el único hueco es una prueba `perf` con una décima del volumen pedido.
- Contrato: las 15 rutas nuevas y los cambios (`email_sent`, `notifications_today`, `members_without_consent`, `crypto`, 409 `channel_disabled` ya declarado en `responses_for`) están en `docs/openapi.json`; `test_openapi_export` verde (V11c). Migraciones `0015`–`0020`; V11c no añadió migración.
- Versión: `0.2.0` en `api/pyproject.toml`, `web/package.json` y `CHANGELOG.md` (`e411df0`); `check-release-version` ok según el orquestador (no hay línea de esa corrida en el cuaderno).

### DoD de `SPRINT-05.md` (seis puntos) — 6/6

| # | Punto | Estado | Evidencia |
|---|---|---|---|
| 1 | DoD común: `run-gates.sh`, arquitectura, ciclo de Alembic, OpenAPI, licencias | entregado | V9 sobre `051751a` (árbol limpio, en solitario): api ruff/format/mypy limpios; pytest 7987 passed, 0 fallos, 87 skipped (Windows); cobertura global 95 %, exigidos 85–100 %; Linux: los 15 archivos con saltos, 434 passed / 8 skipped «no aplica», 0 de `age`/`pty`/`openbao`; web lint, tsc, 3542 pruebas, 97,26 %, build ok; 7 scripts de infra «0 fallas»; `npm audit` y `pip-audit` 0; licencias ok; gitleaks limpio; `check-image-secrets` ×3. Ciclo de Alembic en V2.3. pre-commit falló en V9 por versión de ruff del hook y tres saltos finales: corregido en `43113df` (7/7 Passed según el orquestador; sin registro en el cuaderno, MINOR-2). Después de V9 solo cambió una línea vacía de `config.hcl` fuera de specs, docs y versiones |
| 2 | E2E: por avisar hoy (WhatsApp y omitir), recibo, exportación | entregado | V5 sobre `e411df0` en el ensayo con OpenBao: 48 passed + 1 skipped ×2 seguidas (0 fallos, 0 flaky); el skip es el rol `member` en `home.spec.ts` (el rol llega con el portal, v1.0); preview 189/189. Ajustes de `b3a71c9` solo en la preparación de las specs (habilitar WhatsApp por la nueva regla D265, carrera de `first()`, consulta SQL de la prueba) |
| 3 | Smoke con OpenBao | entregado | V2.6 `prod-smoke.sh --provider openbao` 180 ok; V3 (sellado, 503, desello 8 s y 12 s) |
| 4 | `notify` ×2 el mismo día sin duplicar | entregado | V4; `worker.job_runs` del ensayo `notify ok` con dos intentos, duplicados 0; `test_generate_concurrency.py` |
| 5 | Revisión de seguridad de los seis puntos | entregado | «S5-V10 · Revisión de seguridad DoD del backend» (0 C / 0 H / 0 M / 2 L); V11c: 0 C / 0 H / 1 M (D270, corregido) / 2 L (1 corregido, 1 aceptado) |
| 6 | `verify-delivery` sobre el stack con OpenBao | entregado | este documento (cerrado sobre `b3a71c9`); queda la parte de V12 anotada en P2-1 y P2-9 |

### Demos 1 a 5 — 5/5

| Demo | Estado | Evidencia |
|---|---|---|
| 1 · OpenBao | entregado (`rotate-kek --trim` lo repite V12) | V2.5, V3; reanudación por prueba; SQL vivo (`openbao` 8/8, `kek_local` 1, job `done 8/8`); rotación de KEK en B2.7 |
| 2 · Avisos | entregado | V4 (correo con opt-in, Telegram sin nombres); V5 en vivo `wa-link` 200 y `skip` 200 con su auditoría; interruptores de Canales respetados (D265) |
| 3 · Cuentas por correo | entregado | V4; V5 `users-activation.spec.ts` |
| 4 · Recibo y CSV con cuadre | entregado | V6 + SQL vivo; V5 `payments-receipt-export` y `members-export` |
| 5 · Inicio con los dos KPI | entregado | B10 (api); V5 `home.spec.ts` (front) |

## 2. Pilar 2 · Sistema real (borrador ~19:10Z; cierre con `docker inspect` y `/health` sobre `b3a71c9`)

| # | Comprobación | Resultado | Estado |
|---|---|---|---|
| P2-1 | Imágenes vigentes | Cierre: api y web de `apex` y del ensayo con `apex-api:local` `04cdf608ece9` y `apex-web:local` `5f9e12ee8203`, label `revision e411df0` (V5); **`apex-worker-1` y `apex-ensayo-worker-1` siguen en `4b5f6d77f672`, label `e2a6329`**, anterior a S5-V11c: el worker vivo no tiene la generación con `skipped` por canal (D265a, D266), la exclusión de `frozen` (D267) ni la puerta de Telegram (D265d). V5 generó con `tools notify --generate-only` (imagen nueva), así que el camino programado del worker no se ejercitó con el código de cierre. `apex-backup:local` sin label de revisión. `e411df0..b3a71c9` no toca `api/src`, `web/src` ni `infra` (solo specs y docs). **V12 debe reconstruir las tres imágenes con el SHA de cierre y recrear también el worker** (y añadir la etiqueta a `apex-backup`) | **parcial** (MAJOR-2) |
| P2-2 | `/health` | Cierre: 8181 y 8280 200 `{status ok, db ok, version e411df0, backup attention, migrations ok, crypto ok}`. `attention`: el último `backup_check` es anterior a los respaldos de la tarde; la corrida diaria lo refresca | entregado con nota |
| P2-3 | Avisos generados | Ensayo: 6 `whatsapp_link` (borrador) y luego 6 y 8 en V5; duplicados 0 | entregado |
| P2-4 | `wa-link`, `skip`, PATCH canales | V5 en el ensayo (admin): `wa-link` 200 (`sent`), `skip` 200 (`skipped`), `PATCH /members/{id}/channels` 200; auditoría: `reveal` del teléfono con `purpose notify` sin el número, `update` pending→sent con `sent_by`, `update` pending→skipped con `skip_reason`, `insert` de preferencias; `PATCH /settings/channels` por `habilitarWhatsapp` | entregado |
| P2-5 | `forgot` y alta con `email_sent` | V4 sobre `apex_avisos_demo` con Mailpit; V5 `users-activation.spec.ts` | entregado |
| P2-6 | Recibo | SQL vivo `download payments.payments` 3; V5 E2E | entregado |
| P2-7 | Export socios y pagos | SQL vivo: `export members.members` 8, `export payments.payments` 4, `crypto_ops export decrypt ok` 12; 409 (V6); V5 E2E con topes ×100 | entregado |
| P2-8 | `migrate-provider` y `retire-local-kek` | SQL vivo: `crypto_keys` `openbao` 5 + 3 `active`; `migrate_provider done 8/8`; auditoría `update local→openbao 8/8`, `kek_local: retirada`, `verify` ×3, `export` ×2 | entregado |
| P2-9 | `rotate-kek` y `--trim` | Solo B2.7 en el ensayo anterior (`version 2`, `rewrap 8/8`, `min_decryption_version 2`); el ensayo actual no lo tenía al cierre del borrador. **PENDIENTE DE V12**: otro agente lo está repitiendo en el ensayo antes de destruirlo; su evidencia va al cuaderno de V12 | **PENDIENTE DE V12** |
| P2-10 | Snapshot de OpenBao en el respaldo | `latest.json` = `apex-20261105-184323` con `openbao_snapshot.verified = true`, `.snap.age` 31.043 B y `latest.json.minisig` | entregado |
| P2-11 | `notify` ×2 e idempotencia | `notify ok` con dos intentos el mismo día, sin duplicados; `seed-notifications` 2/5 exactos; `generate` 0 en la segunda corrida; `seed --demo` no reescribe canales en la 2.ª corrida (V11c) | entregado |
| P2-12 | Secretos en logs | logs de api, worker, openbao y backup: 0 de `hvs.`, `AGE-SECRET`, `X-Vault-Token:`; V9 gitleaks y `check-image-secrets` | entregado |
| P2-13 | Desarrollo (`apex`) | `crypto_keys` `local` 8 (por diseño, D68); en el borrador `notification_templates` 0 tras el downgrade de V2.3 (sin re-siembra verificada en el cierre: no se usó `psql`) | observación |

**Pilar 2: 10/13 entregados** (P2-1 parcial por el worker sin recrear; P2-9 PENDIENTE DE V12; P2-13 observación).

## 3. Hallazgos

- **MAJOR-1 · Interruptores de canal sin efecto — CORREGIDO** en S5-V11c (`051751a`, S5-D265, D269, D270): generación con `skipped canal_no_configurado` / `canal_desactivado_socio`, 409 `channel_disabled` antes de descifrar, `country_code` desde Configuración sin adivinar prefijos, puerta de Telegram con caché de 30 s. Pruebas nuevas y V9 verde sobre ese commit. Revisión de seguridad 0 C / 0 H / 1 M corregido.
- **MAJOR-2 · Worker vivo anterior a V11c (nuevo en el cierre).** `apex-worker-1` y `apex-ensayo-worker-1` corren `e2a6329`; V5 recreó solo api y web. Es exactamente el caso «reconstruir un servicio no prueba los demás». No es defecto del código (el despliegue real construye todo desde la etiqueta con `infra/deploy.sh`) ni afecta a la release, pero el pilar 2 del job `notify` programado con D265–D267 no está probado en vivo. Dueño: V12 (reconstruir las tres imágenes con el SHA de cierre, `--force-recreate` de api, worker y web en `apex`, comprobar `docker inspect` del worker y una corrida `--run-once notify`).
- **MINOR-1 · Deriva documental — CERRADO**: US-122 («Corregido en S5»), US-124, US-126 y US-127 («Corregido en S5-V11c») llevan su nota (`15d4731`, `d6f14fc`).
- **MINOR-2 · Evidencia no registrada en el cuaderno**: la corrida de pre-commit 7/7 tras `43113df` y la de `check-release-version` tras `e411df0` solo constan en el informe del orquestador. Dueño: orquestador, una línea en `docs/scratch/sprint-05.md` antes del PR.
- **MINOR-3 · US-129.6 medida a 1.000 avisos (CERRADO en `7deb573`: `AVISOS = 10_000`, 1 passed)**: `test_history_perf.py` (`AVISOS = 1_000`) frente a 10.000 del criterio. Opciones: subir la constante a 10.000 (prueba `perf`, no gate) o enmendar el criterio en DECISIONES. Dueño: orquestador (V12 o v0.3 EP-14).
- **MINOR-4 · Dos pruebas web flaky bajo carga** (`routes.render.test.tsx` H1 y `features/system/api.test.tsx` recarga): pasan solas y en la repetición completa (V9). Dueño: front, v0.3.
- **OBS-1** `apex-backup:local` sin `org.opencontainers.image.revision` (V12 añade la etiqueta).
- **OBS-2** Cobertura en Windows bajo 80 % en archivos no exigidos (`cli_ops/kek.py` 56 %, `core/crypto/archive.py` 51 %, `cli_ops/keys.py` 78 %) por ramas solo Linux; la corrida Linux de V9 las ejecutó sin saltos. Global 95 %.

## 4. Pasos humanos declarados

1. Custodia de las 5 llaves de desello 2/2/1 (titular, operador, tercero) — S5-D106, Q10, ADR-005.
2. Ensayo de `rekey` por una segunda persona — S5-D106, plan V11.
3. Desello del ensayo si queda sellado (llaves en `docs/scratch/ensayo/openbao/`; V12 las borra).
4. **ADR-005 punto 2**: cambiar un ADR exige detenerse y preguntar (S4B-D47); queda para el titular.
5. Push, PR con la CI en verde (`api` con 0 saltos de `openbao` por S5-D264, `prod-smoke` con `openbao-smoke`), merge a `main` (hoy en `a1ad4cb`), etiqueta `v0.2.0` y su firma (S5-D93, D83; si no firma, v0.3 con el titular). Ninguno lo hace un agente.
6. Titular de `LICENSE`, `allowed_signers`, N-6/N-7 (heredados del 4B).
7. Regla `eslint` de imports (S4B-D197) y restauración por otra persona (S4B-D210), heredados.
8. Traspaso de servidores existentes a `apex_owner` con `infra/db/reown.sql` (S5-D143, D146) y migración real a OpenBao con el orden de `.env` de V2. En una instalación nueva, habilitar los canales en Configuración antes de que se generen avisos (sin fila = apagado, S5-D265; RUNBOOK §2 y `docs/operacion/avisos.md`).

## 5. Deudas aceptadas con dueño (v0.3 salvo indicación)

- Índice `memberships(end_date)` y CHECK `status='sent' ⇒ sent_at` (B7, MEDIUM BD 4 y LOW BD 9; S5-D226).
- SMTP 465 / TLS implícito (S5-D207). Volumen `keys` con `subpath` (S5-D201).
- TLS en `custody` y Caddy (EP-20, titular), AppRole y rotación de tokens (operador), `audit.append()` y trazabilidad por socio de las exportaciones (titular), `display_name` (titular), retención de `rendered_body` (L-4, titular) — S5-D83, D63.
- LOW aceptados de V8 (índices del historial y de reglas, v0.3 EP-14), de V10 (segundo listener 8210, D107; `set -uo`; `single_flight` por proceso, D258; `useBlobDownload` por instancia) y de V11c (LOW 2: caché de la puerta de Telegram sin candado).
- Etiquetas legibles para los códigos `skip_reason` en el historial (hoy «motivo: <código>»; V11c Verde, front, v0.3).
- BRECHAS §13: 13.6 y 13.11 aceptadas con dueño; 13.17 abierta (entrada «Por avisar hoy» del SideNav hasta v0.4, Q25).
- **Contraseña del admin de desarrollo en el scratchpad** de las sesiones (usada por V5 y las demos): dueño V12, borrarla con el resto de llaves y `.env` del ensayo; el titular la cambia en `apex` de desarrollo si se compartió fuera de la máquina.
- MINOR-2, MINOR-3 y MINOR-4 de la sección 3.

## 6. Veredicto final

- **Pilar 1:** 147/147 criterios; 20/20 historias COMPLETE; épicas EP-14, EP-15 y EP-16 COMPLETE; DoD 6/6; demos 5/5.
- **Pilar 2:** 10/13 (P2-1 parcial por el worker sin recrear, P2-9 PENDIENTE DE V12, P2-13 observación).
- **Decisión: READY_WITH_WARNINGS.** Razones: 0 CRITICAL; MAJOR-1 corregido con pruebas, revisión y gates; gates completos V9 en verde (7987/0, 95 %; web 3542, 97,26 %; Linux 0 saltos de `age`/`pty`/`openbao`); E2E V5 48/48 ×2 sobre OpenBao y preview 189/189; P2-4 probado en vivo con su auditoría. No es READY porque: (a) MAJOR-2, el worker vivo no corre el código de cierre y el camino programado de `notify` con D265–D267 no está probado en vivo; (b) `rotate-kek --trim` no está repetido sobre el ensayo actual; (c) US-129.6 medido a una décima del volumen.
- **Condiciones para la fusión** (antes del PR): V12 reconstruye api, web y backup con el SHA de cierre, recrea api, worker y web, y deja `docker inspect` del worker con esa revisión y una corrida `--run-once notify` ok; V12 registra `rotate-kek --trim` en el ensayo; el orquestador anota pre-commit 7/7 y `check-release-version` en el cuaderno y decide MINOR-3 (subir a 10.000 o enmendar). La CI remota con 0 saltos de `openbao`, el merge y la etiqueta firmada son pasos humanos (sección 4).
