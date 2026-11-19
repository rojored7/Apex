# Sprint 9 · V8 · Pilar 1 de `verify-delivery` (planeado contra entregado)

- HEAD analizado: `77d54af` (`docs(sprint-09): S9-V5 E2E, preview y nightly disparado`), rama `feat/sprint-09-perfil-atleta`, 75 commits sobre `main` (`git log --oneline main..HEAD`). Cabeza de Alembic: `0044_body_metrics_time_checks`.
- Fecha del análisis: 2026-11-18. Solo lectura del árbol: cada puntero se comprobó con `grep` o lectura del archivo citado. No se corrió Docker, pytest ni Playwright; los conteos de pruebas son los del cuaderno (`docs/scratch/sprint-09.md` y `sprint-09-front.md`), no los repetí.
- Planeado: `docs/ddd/blueprints/sprint-09-plan.md` (§3 punto 8, §8 mapa, §10 enmiendas), `docs/ddd/09_sprint_plan/SPRINT-09.md`, historias `docs/ddd/07_user_stories/EP-24-perfil-del-atleta/`.
- Rutas de prueba: `api/tests/...` salvo que se diga otra cosa; front en `web/`.
- Leyenda: `entregado` (hay código y prueba o evidencia en vivo), `parcial` (falta una parte con motivo), `no`.
- Hashes de slice (checkpoints): W0-1 `d63daf9`, W0-2 `8431263`, W0-3 `ba1b648`, A1 `8019dee`, A2 `97b6b6d`, A3 `b987d41`, B1 `a90afe8`, B2 `62d947f`, B3 `09a4134`, B4 `d4af13f`, B5 `0a6bc08`, B6 `29d268e`, C1 `e98a10c`, C2 `f5b0027`, X1 `39ff8d0`, X2 `c06ad04`, X3 `9e65d41`, F1 `3474ab4`, F2 `2a1c1f0`, F3 `dc06f8c`, V7b `28419f5`, V7f `902216b`/`2d06167`, V1 `d5da64e`, V3 `f670b2b`, V4 `7d58d35`, V6 `31dccac`, V5 `77d54af`.

## 1. Historias US-178 a US-184 (con sus criterios de aceptación)

Las historias llevan al final «Correcciones del Sprint 9 (T-DOC)» (commit `d63daf9`); donde un criterio original cambió, la variante está ahí y en `DECISIONES.md`. Total de criterios originales: 11 + 7 + 9 + 9 + 7 + 8 + 7 = 58.

- US-178 · medidas cifradas · **entregado** (A1 `8019dee`, A3, F1).
  - CA1 a CA11 cumplidos; variantes aprobadas: CA1 y CA6 devuelven `has_weight/has_height/has_body_fat/has_notes` en vez de valores enmascarados (S9-D16); CA4 `measured_on` es fecha civil de Bogotá, no instante (S9-D3); CA5 `weight_g` en gramos 20.000 a 400.000 (S9-D3); CA7 la lectura de un socio dado de baja se permite y solo la escritura da 404 (S9-D14); CA10 hay anulación (`POST /metrics/{id}/void`, S9-D13) pero no edición ni borrado.
  - Código: `api/src/app/modules/athletes/metrics.py` (`add_metric` :74, 409 `ConsentRequired` :92), `rules.py` (`encode_metric` :79, `decode_metric` :117, `validate_metric` :134), `models.py`, migración `api/migrations/versions/0042_athletes_body_metrics.py`, clase en `core/crypto/registry.py:55`.
  - Pruebas: `athletes/test_metrics_service.py:61` (cuatro blobs `apx1`), `:97` (cuatro filas `encrypt`), `:132` (salida solo `has_*`), `:159` (auditoría con blob), `:236` (409 y cero `encrypt`); `athletes/test_router_metrics.py:51` (solo las rutas de medidas), `:97` (403 y 401), `:236`, `:262` (paginación); `architecture/test_no_plaintext_at_rest.py:222` (texto en reposo, la prueba de arquitectura de CA2); `architecture/test_audited_tables.py:72` (CA9); `migrations/test_0042_athletes_body_metrics.py`.
  - Vivo: cuaderno S9-A1 (curl: 201, 409 y blobs de 98/94/93/259 caracteres, una fila `insert`); V4 demo 1 (`7d58d35`); E2E `web/tests/e2e/stack/athlete-profile.spec.ts:40`.
- US-179 · mostrar una medida auditada · **entregado** (A2 `97b6b6d`, F1).
  - CA1 a CA7 cumplidos. Variante: un campo nulo SÍ deja fila `reveal` (P6, S9-D37), contra el CA7 original.
  - Código: `athletes/metrics.py:149` (`reveal_metric`), puerta única `_decrypt_metric_field`; cubetas `members-reveal*` en `athletes/router.py`.
  - Pruebas: `athletes/test_router_reveal.py:83` (admin y coach), `:119` (403 y 401), `:166` (422 con `field`), `:217` (404 de otro socio), `:252` (409 anulada), `:272` (baja: admin 200, coach 403), `:346` y `:388` (429), `:451` (logs sin valor); `athletes/test_reveal_service.py` (19); `architecture/test_reveal_single_door.py:28` (tres puertas).
  - Vivo: V4 demo 1: 0 `/reveal` al abrir, tras «Mostrar peso» 1 `reveal` y 1 `decrypt`.
- US-180 · récords manuales · **entregado** (B1 `a90afe8`, B2, B5, F2).
  - CA1 a CA9 cumplidos con variantes aprobadas: `value_g` en gramos (S9-D3, S9-D8); el benchmark manual lleva `benchmark_id`, no `wod_id` (S9-D8); `achieved_on` fecha civil; hay `POST /records/{id}/invalidate` (S9-D13), no edición ni borrado; un duplicado vivo da 409 `record_duplicate`.
  - Pruebas: `athletes/test_manual_records_service.py:66` (RM manual vigente), `:96`, `:113`, `:132` (evento solo si queda vigente, CA7), `:188` (422 si el movimiento no es kg, CA2), `:255` y `:281` (benchmark, CA3), `:302` (un `scaled` no gana a un `rx`); `athletes/test_router_records.py:72` (sin rutas de edición), `:143`, `:256` (404 y baja), `:307` (paginación); `athletes/test_records_review_b1.py:89` (duplicado).
  - Código: `athletes/records.py`, migración `0043_athletes_personal_records.py`.
- US-181 · RM derivado por carga · **entregado con una variante grande** (B3 `09a4134`, B5, B6, F2).
  - CA1 a CA7 y CA9 cumplidos. **CA8 cambió**: el criterio decía que un error del handler revierte la validación completa; S9-D7 (4), S9-D42 y P10 lo cambiaron a fallo blando en savepoint (la clase no se queda sin registrar por un fallo de `athletes`), con alerta sin ids. Es la decisión H-2, no un incumplimiento.
  - Pruebas: `athletes/test_derive_rm_service.py:48` (100 kg sobre 95), `:79` (90 sobre 95), `:104` (marcas que no derivan, incluye `scaled`, N-45), `:151` (auditoría con el actor), `:169` y `:191` (idempotencia por `result_id`); `athletes/test_derive_soft_fail.py:77`, `:105`, `:141`, `:163`, `:241` (503 `busy`); `athletes/test_derive_rm_pure.py`.
  - Invalidación (refinamiento de la historia): `athletes/test_invalidation_service.py:65`, `:113` (hueco 90/1000/95), `:194` (anular), `:337` (la base rechaza revivir); vivo en V4 demo 2.
  - Eventos: `results/events.py:43` (`WodResultSuperseded`), `athletes/events.py:19` (`PersonalRecordSet`).
- US-182 · récord derivado de benchmark · **entregado** (B4 `d4af13f`).
  - CA1 a CA6 cumplidos. CA7 cambió: el agrupamiento es por `benchmark_id` del catálogo (US-166), no por título normalizado (T-DOC y S9-D8/D9).
  - Pruebas: `athletes/test_derive_benchmark_service.py:91` (245 s sobre 260 s), `:120` (270 s), `:138` (empate), `:156` (dos WODs, mismo benchmark), `:195` (capped), `:222` y `:254` (benchmark de carga, dos récords), `:380` (idempotente); `athletes/test_derive_benchmark_pure.py`.
- US-183 · comparar benchmarks · **entregado** (C1 `e98a10c`, F3).
  - CA1 a CA8 cumplidos con variante de ruta: `GET /benchmarks/{benchmark_id}` (la serie) y `GET /benchmarks` (la lista), en vez de `?wod=` (T-DOC). `GET /benchmarks` pagina y acepta `q`.
  - Pruebas: `athletes/test_benchmarks_service.py:113`, `:170` (solo vigentes y validados, CA3), `:192` (un solo mejor, CA4), `:227` (404), `:274` (sin campos cifrados, CA8); `athletes/test_router_benchmarks.py:69`, `:133` (403 y 401), `:202`.
  - Vivo: V4 demo 3; E2E `athlete-profile.spec.ts:99`.
- US-184 · perfil del atleta en la ficha · **entregado** (C2 `f5b0027`, F1 `3474ab4`, F2, F3).
  - CA1 a CA7 cumplidos. Notas: CA4 usa `?tab=` y, para el benchmark elegido, `?bm=` (V7f, choque de parámetros); CA7 «44 px» se cumple por `--control: 44px` (`web/src/core/styles/tokens.css:44`) usado en `MetricField.module.css:21` y `MetricsTab.module.css:21`, más axe en `AthleteTab.test.tsx:220`; ninguna prueba mide los 44 px en un navegador real (jsdom no calcula layout).
  - Pruebas api: `athletes/test_summary_service.py:200` (no descifra ni audita), `:224` (con el custodio sellado), `:241` (a lo sumo seis consultas); `athletes/test_rms_service.py:242`; `athletes/test_router_profile.py:67`, `:119`.
  - Pruebas front: `web/src/features/athletes/tabs/AthleteTab.test.tsx:46` (cinco subpestañas en `?tab=`), `:123` (baja: sin «Registrar medidas»); E2E `web/tests/e2e/stack/athlete-guards.spec.ts:40` (baja sin botones de escritura) y `:62` (sin autorización).
  - Vivo: V4 demo 4.

Conteo del grupo: **7 de 7 historias entregadas** (0 parciales, 0 no). Criterios: 58 de 58 cubiertos; los que tienen variante aprobada y numerada están señalados arriba.

## 2. Demos 1 a 4 de `SPRINT-09.md`

Evidencia común: `docs/scratch/sprint-09.md`, bloque «S9-V2 (repaso) y S9-V4», commit `7d58d35`, hecha por la interfaz de 8180 con conteos en la base; más los E2E de stack (V5, `77d54af`: 72 passed, 0 failed, dos corridas).

- Demo 1 · medidas · **entregado**. Cuatro columnas `apx1.`, 0 filas en claro, 409 `consent_required` sin autorización y 0 filas; «Mostrar peso» deja 1 `reveal` y 1 `decrypt`; `encrypt` 4 por la medición. Además `athletes-smoke.sh` (V3 `f670b2b`): 18 ok.
- Demo 2 · RM derivado por carga · **entregado**. `rx` 100 kg crea el RM; `scaled` 100 kg no crea ninguno; corregir a 90 kg deja el de 100 kg `invalidated_reason = superseded` sin borrarlo; anular deja el de 90 kg `voided`; auditoría `insert` 2 y `update` 2. E2E `athlete-records.spec.ts:44` y `athlete-live.spec.ts:57`.
- Demo 3 · benchmark · **entregado**. Dos Fran (5:00 y 4:10): 2 récords `benchmark` con `benchmark_id`, 4:10 marcado «Mejor», serie de 2 puntos.
- Demo 4 · ficha · **entregado**. Cinco subpestañas, 0 peticiones `/reveal`, 0 filas `reveal` y 0 `decrypt` de `athlete.metric` al abrirlas.

Conteo del grupo: **4 de 4**.

## 3. Condiciones del impacto C1 a C7

- C1 · numeración, gramos, rutas y E2E en `stack/` · **entregado**. `SPRINT-09.md:64` y `DECISIONES.md` S9-D2 (`0042` y `0043`); gramos en `athletes/rules.py:79`; 11 rutas en `athletes/router.py` (9 rutas únicas en `docs/openapi.json`, que agrupa GET y POST de un mismo camino); E2E en `web/tests/e2e/stack/athlete-*.spec.ts`. Commit `d63daf9`.
- C2 · eventos y `get_mark` con pruebas en `results` · **entregado**. `results/events.py:43`, `results/reads.py:287` (`get_mark`) y `:311` (`member_marks`), `results/leaderboard.py:126` (`score_key`); consumidos por B3 y B5 (`09a4134`, `0a6bc08`).
- C3 · sin `init-keys`, prueba de arranque · **entregado**. `tests/crypto/test_boot_data_classes.py` (W0-3 `ba1b648`); V3 comprueba la fila `encrypt` de `athlete.metric` creada sin `init-keys` (`athletes-smoke.sh`, cuaderno V3).
- C4 · tercera puerta, importadores, texto en reposo y auditadas con `0042` · **entregado**. `athletes/metrics.py` (`_decrypt_metric_field`), `architecture/test_reveal_single_door.py:28`, `architecture/test_no_plaintext_at_rest.py:222`, `architecture/test_audited_tables.py:72`.
- C5 · grants, guardas, aristas, `MODULES`, privados · **entregado**. `infra/db/grants.sql:67` (tres listas y por columna), guardas en `0042` y `0043` (`tests/migrations/test_0042_...py`, `test_0043_...py`), `architecture/test_service_import_graph.py:60-67` (las cuatro aristas), `main.py:80` (`MODULES`), `architecture/_imports.py` (privados), `architecture/test_athletes_handlers_no_locks.py`; roles reales en V3 (23 comprobaciones de `test_db_roles.sh`, con rojo por sabotaje).
- C6 · cubetas por escrito antes de las rutas · **entregado**. `core/ratelimit.py:360` (`athletes-write`, 30/min), `tests/core/test_env_example.py:186` (28 cubetas y 27 variables); W0-2 `8431263`.
- C7 · tres deudas de v0.5 y resultados previos · **entregado en código y prueba**, con dos cierres vivos pendientes (ver S9-D23 y S9-D24 en el grupo 7): `derive-records` (D21), `can_whatsapp` (D22), E2E del quiosco (D23), TV en tiempo real (D24).

Conteo del grupo: **7 de 7** (C7 con los pendientes dichos en el grupo 7).

## 4. Revisión de seguridad del diseño: H-1, H-2, M-1 a M-6, L-1 a L-8

- H-1 · datos de salud sin autorización · **entregado**. `athletes/metrics.py:92` (409 antes de codificar), `members/service.py:397` (`consent_missing_for`), `athletes/test_metrics_service.py:236` y `athletes/test_router_metrics.py:236` (cero `encrypt`); front `athlete-guards.spec.ts:62`; V3 y V4 (409 vivo).
- H-2 · el handler no deja la tablet sin resultados y la corrección no dispara 2.000 marcas · **entregado**. `athletes/test_derive_soft_fail.py:77` (fallo blando), `:105` y `:141` (una alerta que falla no revierte), `:163` (sesión usable y cadena verifica), `:241` y `:318` (base ocupada, 503 `busy`); tope de 200 marcas `athletes/test_invalidation_service.py:442`, `:466`, `:484`; V6: corrección con 2.000 marcas en 95,8 y 171,4 ms contra `statement_timeout` de 30.000 ms (`athletes/test_athletes_perf.py`, `31dccac`).
- M-1 · guarda de `body_metrics` frente a `apex_api` · **entregado**. `0042` (guardas con `FOR SHARE` de la llave, S9-D31, S9-D48), `migrations/test_0042_athletes_body_metrics.py:412` y siguientes; V3: `apex_api` sin DELETE y sabotaje de `REVOKE INSERT` detectado.
- M-2 · blob movible entre columnas · **entregado**. Marca de campo en `athletes/rules.py:79` y `:117`; `athletes/test_metrics_service.py:368` (un blob de peso copiado a otra columna no revela nada).
- M-3 · coach anula o invalida solo lo suyo y en 24 h · **entregado**. `athletes/rules.py:43` (`SELF_UNDO_WINDOW_H = 24`); `athletes/test_router_void_metric.py:123`, `:140`, `:160`; `athletes/test_router_invalidate.py:149`, `:165`, `:185`.
- M-4 · baja: `reveal` solo admin · **entregado**. `athletes/test_router_reveal.py:272`; guía `docs/operacion/atleta.md:81` («Socio dado de baja y supresión»).
- M-5 · volumen de `reveal` · **entregado**. Cupo compartido (`athletes/test_router_reveal.py:346`, `:369`, `:388`) y alerta `reveal_volume` (`:407` y `:423`; `core/alerts.py:41`; `tests/core/test_reveal_volume.py`; `tests/core/test_alerts_telegram.py:545`); guía `atleta.md:67`.
- M-6 · reposición acotada, alerta y salida 1 · **entregado**. `athletes/test_invalidation_service.py:442` (alerta con el conteo y sin reponer); `tests/cli/test_derive_records.py:286` (el vigente es el máximo real), `:314` y `:360` (salida 1); `docs/operacion/atleta.md:30` y `:117`.
- L-1 · relleno de `notes` · **entregado**. `athletes/test_metric_rules_pure.py` (relleno a múltiplo de 128 bytes; `decode_metric` exige el relleno mínimo); `athletes/test_metrics_service.py:176` (blobs de un campo miden lo mismo).
- L-2 · puerta con un solo campo, `Literal["reveal"]`, fila anulada y 500 opaco · **entregado**. `athletes/test_metrics_service.py:387`, `:403`, `:415`, `:427`, `:444`; `athletes/test_router_reveal.py:296`.
- L-3 · `FOR UPDATE` y 409 en la segunda · **entregado**. `athletes/test_void_concurrency.py`, `athletes/test_invalidation_concurrency.py`, `athletes/test_invalidate_manual.py:284` (200 y 409, nunca 500).
- L-4 · origen del RM (`result_source`) · **entregado**. `athletes/test_derive_rm_service.py:261`; texto «Automático (tablet)» en `web/src/core/api/types.ts:2061` y F2 (`2a1c1f0`).
- L-5 · `can_whatsapp` con las condiciones reales de `wa_link` · **entregado**. `members/contact.py:179` (`whatsapp_ready`); `notifications/test_can_whatsapp.py:64` a `:100` (cinco condiciones), `:121` y `:139` (coherencia con `wa-link`); E2E `avisos.spec.ts` ajustada en V5 (`12d4393`).
- L-6 · `real_hours` sin inyección · **entregado**. `.github/workflows/nightly.yml:70-81` (`env:`, `if`, validación como primer paso), `scripts/ci/test_nightly_workflow.sh:38`; rojo por mutación en el cuaderno S9-X3.
- L-7 · la respuesta del `reveal` no queda en caché · **entregado**. `web/src/features/athletes/components/MetricField.test.tsx:160` (`visibilitychange`) y `:218` (`gcTime` 0 y `reset()`).
- L-8 · el detalle de auditoría oculta los blobs · **entregado**. `api/tests/audit/test_detail_hides_metric_blobs.py` (sustituye por «cifrado» en `before` y `after`).

Conteo del grupo: **16 de 16** (2 HIGH, 6 MEDIUM, 8 LOW); ninguno quedó aceptado sin corregir.

## 5. Preguntas P1 a P11 (S9-D37, respondidas por la opción por defecto)

- P1 · dos salidas, anular medición e invalidar récord manual · **entregado**: A3 `b987d41`, B5 `0a6bc08`; pruebas del grupo 4 (M-3).
- P2 · reponer el mejor al invalidar · **entregado**: B5; `athletes/test_invalidation_service.py:113`, `:210`.
- P3 · enteros y `measured_on` como fecha · **entregado**: `athletes/test_metric_rules_pure.py:358`, migración `0042`.
- P4 · `members.hide_on_tv` pasa a EP-25 · **entregado como decisión documentada**: `docs/BRECHAS.md:665` (fila 17.4) y S9-D25; no hay código por diseño.
- P5 · cupo compartido más alerta · **entregado**: ver M-5.
- P6 · un `reveal` de campo vacío deja fila de auditoría · **entregado**: S9-D37; `athletes/test_router_reveal.py:103` cubre el campo vacío (`null`); la fila de auditoría de ese caso está dicha en la decisión, no la afirmo por una prueba aparte que no localicé por nombre.
- P7 · 12 h aceleradas más 5 h reales en GitHub · **parcial**: `tv-soak` (12 h aceleradas) `success`; `tv-soak-real` disparado (`nightly.yml`, corrida `44460676543` sobre `12d4393`) y **en curso al corte del cuaderno**, sin resultado final (V5, `77d54af`).
- P8 · `derive-records` · **entregado**: B6 `29d268e`, `api/src/app/cli_ops/derive_records.py`, `tests/cli/test_derive_records.py` (17 casos); V2: dos corridas, la segunda con 0 creados.
- P9 · 409 `consent_required` · **entregado**: ver H-1.
- P10 · derivar en blando e invalidar cerrado · **entregado**: `athletes/test_derive_soft_fail.py:77` (blando) y `athletes/test_invalidation_failures.py:96`, `:117` (un fallo al invalidar revierte la corrección y la anulación).
- P11 · sin supresión en v0.6, reveal de bajas solo admin y la guía lo declara · **entregado**: `docs/operacion/atleta.md:81`; ADR-002 sin tocar.

Conteo del grupo: **10 entregados, 1 parcial (P7), 0 no; 11 en total**.

## 6. Los diez hallazgos de la crítica 1 (plan §9)

- Hallazgo 1 · `alert()` rechazaba las claves · **entregado**: claves `revelados` y `marcas` en `core/alerts.py:40-41`, entradas dinámicas en `core/alerts_telegram.py:138-171`, `tests/core/test_alerts.py:262`, `tests/core/test_alerts_telegram.py:545`; W0-3 `ba1b648` y W0-3b `37c5d3a`.
- Hallazgo 2 · `DatabaseBusy` no se lanza dentro de un service · **entregado**: `translate_busy` en `athletes/derive.py`; 503 `busy` en `athletes/test_derive_soft_fail.py:241` y `:318`, `athletes/test_invalidation_failures.py:259`; tratamiento propio con salida 1 en `tests/cli/test_derive_records.py:314`.
- Hallazgo 3 · patrón del savepoint · **entregado**: `begin_nested` en `athletes/derive.py`; `athletes/test_derive_soft_fail.py:163` (sesión usable y cadena verifica), `athletes/test_invalidation_failures.py:201`; `verify-audit` al final queda como paso del Pilar 2.
- Hallazgo 4 · invalidación sin auditoría · **entregado**: `athletes/test_invalidation_audit.py:47`, `:67`, `:105`, `:131` (fila `update` con el actor); V4 demo 2 (`update` 2).
- Hallazgo 5 · condición inexistente en `wa_link` · **entregado**: ver L-5.
- Hallazgo 6 · fábrica contra la guarda · **entregado**: `athletes/test_factory_metrics.py:41` y `api/tests/factories/athletes.py`.
- Hallazgo 7 · `tests/core/crypto/` no existe · **entregado**: la prueba vive en `api/tests/crypto/test_boot_data_classes.py`.
- Hallazgo 8 · rollback a v0.5.0 con la llave nueva · **entregado y medido**: V3 (`f670b2b`): `downgrade` `0044 → 0041` en `apex-smoke`, imagen `apex-api:v050` con `/health` 200, `crypto ok`, `migrations ok`, login y `reveal` de `document` con 200; plan §6.2 (línea 567) y `docs/operacion/actualizar.md:144` («Volver de v0.6 a v0.5»).
- Hallazgo 9 · credencial y push · **entregado**: S9-D38 y S9-D41; el push de la rama y el disparo de `nightly.yml` por REST (HTTP 204) están en V5 (`77d54af`); el push de `main` y de la etiqueta pertenece a V9.
- Hallazgo 10 · orden de P-MIG en el ciclo · **entregado**: plan, «Ciclo estándar», pasos 4 y 7; cada checkpoint del cuaderno registra P-MIG 5 a 7 (A1, B1).

Conteo del grupo: **10 de 10**.

## 7. Decisiones S9-D21 a S9-D25

- S9-D21 · `derive-records` · **entregado**: `api/src/app/cli_ops/derive_records.py`; `tests/cli/test_derive_records.py:195` (la segunda crea 0), `:217` (`--dry-run`), `:241` (en producción exige `--as` admin), `:492` (auditoría), `:517` (no emite el evento); V2: «socios 35, creados 0, ocupados 0, fallidos 0», salida 0. Pasa al CHANGELOG en V9.
- S9-D22 · WhatsApp a un socio sin teléfono · **entregado con corrección de la propia decisión**: no se hizo `phone_presence` ni «Sin teléfono»; S9-D36 (L-5) y S9-D65 lo cambiaron a `can_whatsapp` con cinco condiciones y botón «No se puede abrir WhatsApp» con «Revisar la ficha». Pruebas: `notifications/test_can_whatsapp.py:64-176`; front `web/src/features/notifications/components/WaButton.test.tsx`; V5 `12d4393`.
- S9-D23 · inactividad del quiosco · **parcial**. Entregado: E2E `web/tests/e2e/stack/kiosk-idle.spec.ts:53` y `:94` (dos corridas verdes y rojo por mutación, X2 `c06ad04`); respuesta a E6 (el servidor no tiene plazo propio). Pendiente: la espera REAL de 10 minutos con Monitor y la fila de `auth.refresh_tokens`, que el plan asigna al Pilar 2 de V8.
- S9-D24 · TV en tiempo real · **parcial**. Entregado: job `tv-soak-real` y sus guardas (`nightly.yml:68-90`, `scripts/ci/test_nightly_workflow.sh`), spec con modo real, corrida local corta, `docs/operacion/tv.md` (X3 `9e65d41`); `tv-soak` acelerado `success` en GitHub. Pendiente: el resultado de `tv-soak-real` (5 h reales), en curso al corte.
- S9-D25 · pendientes de S8 que no son de este sprint · **entregado** (decisión de alcance): `docs/BRECHAS.md` §17 (línea 656, filas 17.1 a 17.9) y `ROUTES.md`; sin código por diseño.

Conteo del grupo: **3 entregados, 2 parciales (D23, D24), 0 no; 5 en total**.

## Conteo final

- Historias US-178 a US-184: 7 de 7.
- Demos 1 a 4: 4 de 4.
- C1 a C7: 7 de 7.
- H-1, H-2, M-1 a M-6, L-1 a L-8: 16 de 16.
- P1 a P11: 10 de 11 entregados, 1 parcial.
- Hallazgos de la crítica 1: 10 de 10.
- S9-D21 a D25: 3 de 5 entregados, 2 parciales.
- **Total: 57 de 60 entregados, 3 parciales (P7, S9-D23, S9-D24), 0 no.** Los tres parciales son la misma clase de cosa: una comprobación en tiempo real que no puede terminar dentro de una sesión (5 h reales de GitHub y 10 min reales del quiosco).

## Desviaciones (cambiadas, aplazadas o aceptadas con decisión)

- Tercera migración `0044_body_metrics_time_checks` (V7b, `28419f5`): el plan decía solo `0042` y `0043` y `SPRINT-09.md:64` dice que la `0044` quedó sin usar. La añadió la revisión de Fase 4 (CHECK `voided_after_created` y `updated_after_created`, con `clock_timestamp()` en `void_metric`). Está en `CLAUDE.md:115` y en `actualizar.md:165`, pero no en `SPRINT-09.md` ni en `DECISIONES.md` (ver Huecos).
- US-181 CA8: la validación ya no se revierte si falla el handler (fallo blando, S9-D7 (4), S9-D42, P10, H-2).
- US-182 CA7 y US-183 CA1: agrupamiento por `benchmark_id` y rutas `/benchmarks/{benchmark_id}` en vez de título normalizado y `?wod=`.
- US-179 CA7: un `reveal` de campo nulo sí deja fila (P6).
- US-178 y US-180: unidades enteras (gramos), `measured_on` y `achieved_on` como fecha civil, `has_*` en las listas, anulación e invalidación como acciones (S9-D3, S9-D13, S9-D16).
- S9-D22 se corrigió a sí misma: `can_whatsapp` con cinco condiciones y texto «No se puede abrir WhatsApp» (S9-D36, S9-D65); no hay `phone_presence`.
- `real_hours` vale `"0"` por defecto, no 5 (plan, precisión posterior a la primera versión; DECISIONES.md:3460).
- Wave 0 creció de 3 slices a 9 entradas del cuaderno (W0-3b, W0-4, W0-4b, W0-4c, W0-4d, W0-4e: avisos sin envío doble, candado y cronómetro de health, código `notification_in_flight`); no estaban en el plan de 29 slices. Cierre en `b27a431`.
- Los números S9-D43 en adelante (más de 25 decisiones adicionales hasta S9-D69) no figuran en el plan, que cuenta S9-D1 a D42.
- V3: el `prod-smoke` corrió con el api en `CRYPTO_PROVIDER=local` incluso en la variante `--provider openbao`; el alta y el `reveal` de medidas con OpenBao como proveedor del api quedaron «omitida» (lo dice el propio log).
- V5: la primera tanda E2E falló por variables `USER_*` ausentes del `.env` de desarrollo (defecto de preparación, no de producto) y por dos defectos reales corregidos en `12d4393` (contraste de «+ Crear» y spec de avisos); la preview falló 15 por mocks viejos, corregidos en `47677ba`.
- V6: la mediana de 15 `PUT /results` se midió contra el mismo flujo sin las suscripciones de `athletes` (diferencia 12,7 a 12,9 ms; tope 20 ms), no contra la mediana de S8. `member_marks` de 2.000 marcas y `movement_has_records` de un movimiento caliente usan `Seq Scan` en una tabla de pocos miles de filas; el cuaderno lo declara informativo.

## Huecos (sin evidencia o con evidencia incompleta)

- Resultado final de `tv-soak-real` (corrida `44460676543`): el último dato del cuaderno es «en curso». Sin él, S9-D24 y P7 no se pueden dar por cerrados.
- Espera real de 10 minutos del quiosco con Monitor (S9-D23 parte 2): no hecha todavía; es del Pilar 2 de V8.
- V5 dejó cuatro specs omitidas por hora o por datos (`home` x2, `checkin`, `results` después de las 21:00 de Bogotá, y `avisos` WhatsApp sin avisos pendientes con teléfono); el cuaderno dice que se repiten después de medianoche, y no hay constancia de esa repetición.
- No hay prueba que mida los 44 px de US-184 CA7 en un navegador real; solo el token `--control: 44px`, su uso en el CSS y axe en jsdom.
- No localicé una prueba con nombre propio para «un `reveal` de campo vacío deja fila de auditoría» (P6); `athletes/test_router_reveal.py:103` cubre la respuesta `null`, pero no afirma la fila.
- La `0044` no consta en `SPRINT-09.md` (que aún dice que quedó sin usar y lista dos migraciones) ni en un `S9-D` de `DECISIONES.md`; el cuaderno V7b la explica. Hay que corregir ambos documentos antes del cierre (V9).
- V7d declara «no comprobado en ejecución» que la pantalla Auditoría ofrezca el filtro por acción en la interfaz (sí lo ofrece el contrato de `GET /audit`).
- V9 no está hecho (esperado): `CHANGELOG.md` no tiene `## [0.6.0]`, no hay etiqueta `v0.6.0` y falta el cierre en `DECISIONES.md`.
- `verify-audit` en verde al final, `derive-records` otra vez, la clase de carga en la tablet con dos correcciones y los avisos de WhatsApp bloqueados: todo eso es Pilar 2 y no se evaluó aquí.
