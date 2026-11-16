# Sprint 9 (v0.6) · Análisis de impacto previo (Fase 0)

Anclado a HEAD `cd0cc0b` (= main = v0.5.0, árbol limpio, rama `feat/sprint-09-perfil-atleta`). Solo lectura.

Veredicto: AMARILLO

## 1. Blast radius (el módulo `athletes` no existe: todo es alta nueva; lo que cambia es lo que toca)

- results: `mod/results/events.py` (evento nuevo `WodResultSuperseded`), `record.py:176-214` (emitirlo al corregir), `service.py` (`__all__`, reexportar `leaderboard_order`), `reads.py:196` (`member_results` con `benchmark_id` y orden). Lo importan `tv`, `classes` (puertos), `wods` (sonda) y `dashboard`: cambio aditivo, sin romper firmas si los parámetros nuevos son opcionales. Prueba: `tests/results/` (NV conteo exacto) y `test_events_without_pii`.
- wods: sin cambios obligatorios (`scoring_for`, `get_movement`, `get_benchmark` bastan); opcional una lectura `primary_movement` sin candado.
- members: sin cambios de código; `ensure_exists` ya sirve. Cambia solo el front (la pestaña Atleta se habilita en `MemberDetailPage.tsx:57,70`).
- core/crypto: `registry.py` (clase nueva). Lo leen `bootstrap.py` (crea la DEK), `inventory.py` y `cbom.py` (aparece `athlete.metric` en inventario y CBOM: ajustar los conteos que fijan `tests/crypto/` y `tests/architecture/test_cbom_no_key_material.py`), `service_pending.py` (rotación) y `test_no_plaintext_at_rest.py`. Cualquier prueba que cuente las clases cifradas (inventario, `crypto_keys`, `LIMPIAR_LLAVES`) cambia: buscar con grep `encrypting_specs` y `REGISTRY` en `api/tests` antes de tocar.
- core/ratelimit y Settings: 3 a 4 cubetas nuevas (reveal de medidas, escritura de athletes), con sus variables `USER_*`, `.env.example`, `infra/compose.yml`, `ci.yml` (el `sed` de límites) y los catálogos de pruebas (`test_user_limits_catalog.py`, `tests/core/test_ratelimit*.py`, `test_env_example`).
- audit: `mod/audit/queries.py` (`AUDITABLE_TABLES` suma `athletes.body_metrics` y `athletes.personal_records`), frases del historial (`audit/diff.py`, NV) y `tests/architecture/test_audited_tables.py`. El historial del socio (`members.service.history`) mostrará filas `reveal` de medidas: confirmar que `after` solo lleva `field` e `ip`.
- Pruebas de arquitectura que cambian: `test_reveal_single_door`, `test_crypto_bus_importers`, `test_service_import_graph`, `test_no_cross_models`, `test_no_cross_schema_sql`, `_imports.py` (`PRIVATE_HELPERS`), `test_audited_tables`, `test_every_route_has_role`, `test_no_store_routes`, `test_list_rows_without_sensitive_fields`, `test_error_codes_per_route`, `test_writes_have_user_limit`.
- main.py: `MODULES` suma `athletes` tras `tv`. Front: `features.ts` (`ENABLED_FEATURES`), `MemberDetailPage.tsx`, `routeTable.ts` (ya declarada), `web/src/core/api/types.ts` (se regenera) y `docs/openapi.json` (25.261 líneas, se regenera con `npm run gen:api`).

## 2. Capa de datos y migraciones

- Cabeza actual `0041_results_session_index` (cadena lineal). Propuesta (ids de 32 caracteres o menos), a registrar en DECISIONES y SPRINT-09.md antes de crear nada: `0042_athletes_body_metrics` (esquema, tabla, índice `(member_id, measured_at DESC)`, CHECK de al menos una medida, trigger append-only) y `0043_athletes_personal_records` (tabla con `value_g int`, `invalidated_at`, `invalidated_by_result_id`, índice único parcial por `result_id`, CHECK de coherencia, trigger que solo deja mutar las columnas de invalidación). La `0044` del párrafo anterior de la exploración solo hace falta si se prefiere separar la invalidación (no recomendado).
- Sin FK entre esquemas (`member_id`, `wod_id`, `movement_id`, `benchmark_id`, `result_id` como uuid): la existencia se valida en `service`.
- Tablas nuevas vacías, sin backfill. Los resultados ya validados en v0.5 NO generan récords retroactivos (el handler solo ve eventos nuevos): decidir y documentar. Si se quiere, es un comando CLI idempotente (regla de datos 8), no una migración: `athletes-backfill`, fuera del alcance del plan.
- Grants y clasificación: `infra/db/grants.sql` y `tests/migrations/test_db_grants.py` en el mismo slice de cada migración (`dbsetup` falla cerrado). Sin DELETE para ningún rol; `test_0014*` (triggers de auditoría) y las pruebas de inmutabilidad por columna.
- Cifrado: cuatro columnas `Encrypted("athlete.metric")` con blob `apx1.`; la auditoría guarda el blob. DEK creada por `ensure_keys` al arrancar el api; en producción el orden de `deploy.sh` (migrate, dbsetup, api) la crea sola. Prueba de arranque: `crypto_keys` tiene fila `encrypt` activa para `athlete.metric` tras el primer arranque del api.

## 3. Servicios Docker

- api y worker (misma imagen, `COPY src` y `migrations` en producción; en desarrollo el api monta `src` y `migrations` y migra solo): reconstruir tras la migración. El worker no tiene reload: `restart worker` porque importa los services de los módulos (el handler vive en el mismo proceso del emisor; el worker no registra resultados, pero carga `load_module_services`). `tools` monta `src`.
- web: reconstruir (`up -d --build web`). Sin cambios de Nginx ni compose salvo las variables `USER_*`.
- `docker ps` hoy: web, worker, api, db, backup y db_test arriba y healthy. Ninguna imagen de terceros nueva; sin dependencias nuevas (licencias sin cambio).

## 4. Contratos API (todas admin y coach)

- Nuevos (prefijo `/api/v1/athletes/{member_id}`): `POST` y `GET /metrics`, `POST /metrics/{metric_id}/reveal`, `POST` y `GET /records`, `GET /rms`, `GET /benchmarks?benchmark_id=`, `GET /summary`. Todas paginadas salvo `summary`; `metrics` y `reveal` con `no-store`.
- No cambia ningún contrato existente (`results` suma un evento interno y un parámetro opcional de servicio, no de HTTP). `GET /members/{id}/results` no cambia.
- Errores nuevos a registrar en `core/api/errorCodes.ts` y `test_error_codes_per_route`: medida fuera de rango (422), sin ninguna medida (422), unidad no kg (422), `benchmark_id` inexistente (404), `metric_id` ajeno al socio (404), socio dado de baja en escritura (409 o 404, decidir).

## 5. Línea base de pruebas

- Cierre del Sprint 8 (CHANGELOG 0.5.0, V1, sobre `cd0cc0b`): api 11.006 pasan y 103 omitidas (Windows, solo Linux), cobertura 95,70 %; web 4.537 pruebas en 261 archivos. E2E `stack`: 61 pasan; `preview`: 219.
- Conteo de archivos hoy: 643 `test_*.py` en `api/tests` y 248 `*.test.ts(x)` en `web/src` (el cierre cuenta 261 archivos web: diferencia por extensiones o `tests/`, NV). No se corrió la suite ni `--collect-only` (poca memoria; la regla es no correr la suite completa en Fase 0).
- Este sprint debe subir lo anterior sin bajar la cobertura global de 80 %: el módulo `athletes` entra con las pruebas del Rojo de cada historia.

## 6. Riesgos por severidad

1. [ALTA] Falta el evento de corrección y la marca en el evento (hallazgos 2 y 3): sin ellos US-181 no puede invalidar el RM ni el handler saber qué comparar. Toca `results` (US-170), que ya está cerrado en v0.5.
2. [ALTA] Unidades: `numeric` en `value_kg` rompe la auditoría (`_normalize` rechaza `Decimal`). Usar gramos enteros (S8-D41).
3. [ALTA] Privacidad de medidas: un `reveal` fuera de la tercera puerta, un valor en una lista, en un log, en `crypto_ops` o en `after` de la auditoría. Pruebas: `test_reveal_single_door` ampliada, `test_list_rows_without_sensitive_fields`, `test_no_sensitive_in_logs`, prueba de "Mostrar" que deja una fila `reveal` y otra `decrypt`, `security-reviewer` antes del cierre.
4. [ALTA] El comando `init-keys --data-class athlete.metric` del plan falla con `unknown_data_class`; la Wave 0 debe cambiar (hallazgo 5).
5. [MEDIA] Un resultado anulado (`WodResultVoided`) o corregido deja un RM derivado vigente si no se suscribe a los dos eventos; error de digitación de 1000 kg (riesgo 1 del plan).
6. [MEDIA] Concurrencia: dos validaciones simultáneas del mismo socio derivan RM a la vez. El emisor ya tiene `lock_member`; el índice único parcial por `result_id` da 23505 en un reintento: traducirlo a no-op, nunca 500.
7. [MEDIA] Handler dentro de la transacción del emisor: si falla, revierte la validación del resultado (decisión de diseño del dominio, 02_domain_model sección 3). Un error de `athletes` bloquea la tablet; prueba de que el 503 `crypto_unavailable` NO afecta al handler (el RM derivado no descifra nada) y de que un WOD sin principal no falla.
8. [MEDIA] Rendimiento: `GET /metrics` no descifra; la gráfica de peso (descifra N filas) necesita paginación y un solo `crypto_ops.count` por lote (N-05) o se difiere a v1.0; decidir. `summary` debe resolverse en pocas consultas (RMs, récords, última medida por fecha, conteo).
9. [MEDIA] Rotación de la clave `athlete.metric`: confirmar que `rotate-key` recifra las cuatro columnas y `retire-key` cuenta bien (`count_rows_by_key`).
10. [BAJA] Reglas de benchmark no definidas: qué es "mejor" con `capped` en `rounds_reps`, `reps` o `load` (N-43 solo habla de `time`); empate; benchmark con `score_type` cambiado después. Anotar en DECISIONES.
11. [BAJA] Documentos desfasados (hallazgo 19) y front condicionado a que `ENABLED_FEATURES` suba sin romper las pruebas de menú de otros roles.
12. [BAJA] Memoria de vitest (2 hilos) y capturas 768, 1024 y 1440 en claro y oscuro.

## 7. Deuda del CHANGELOG 0.5.0 con dueño Sprint 9

- Inactividad del quiosco (10 minutos) sin E2E: la lógica es del front (`web/src/layouts/GymLayout.tsx:20`, `TABLET_IDLE_MS = 10 * 60 * 1000`, y `tabletMode.ts`), solo con prueba unitaria. Cerrarla toca: una spec en `web/tests/e2e/stack/` que entre al quiosco (`POST /auth/kiosk`), avance el reloj con `page.clock` de Playwright 10 minutos y compruebe el cierre de la sesión; sin cambios de código si pasa. Esfuerzo: 3 a 4 h. Riesgo: el reloj falso y el refresh de sesión del servidor (`mod/auth/kiosk.py`) pueden pelearse; si el servidor tiene su propio plazo, dos plazos que acordar.
- TV con 12 h reales: hoy solo `tv-soak` con reloj acelerado (`.github/workflows/nightly.yml:32`, `web/tests/soak/tv.soak.spec.ts`). Cerrarla es un job largo aparte (timeout de 30 min hoy; 12 h reales exceden el máximo de un job de GitHub, que es 6 h en runners alojados, NV por plan) o una corrida manual en el equipo de la pared con medición de heap. Propuesta: declararla evidencia manual con registro en `docs/operacion/` y mantener `tv-soak` como gate nocturno; decidir con el usuario antes de gastar horas.
- «Abrir WhatsApp» sin teléfono: `NotificationOut` (`mod/notifications/schemas.py:150-171`) no trae teléfono y el contrato prohíbe llevarlo (nunca teléfono ni correo en la lista). Cerrarla sin descifrar: agregar un booleano `has_phone` calculado por el índice o por la columna `phone_idx` no nula (`members.service.contact`, `mod/members/contact.py`, sin descifrar), deshabilitar el botón y explicar. Toca `schemas.py`, `service.py` y `queries.py` de notifications, `docs/openapi.json`, `types.ts`, `NotificationRow` en el front y sus pruebas, y `test_notifications_details_clean.py`. Es cambio aditivo de contrato. Esfuerzo: 4 a 6 h. No depende de EP-24.
- La cuarta deuda (contraseña de desarrollo de un coach en una salida) queda como está por orden del usuario.

## Condiciones para VERDE

- C1: registrar en DECISIONES y corregir SPRINT-09.md y BREAKDOWN: migraciones `0042` y `0043`, `value_g` en gramos, rutas `athletes` y E2E en `web/tests/e2e/stack/`.
- C2: decidir el contrato de eventos: `WodResultSuperseded` nuevo, suscripción a `WodResultVoided` y lectura `get_mark` de `results` (o payload ampliado), todo dentro del slice de US-181, con pruebas en `results`.
- C3: sustituir el paso `init-keys --data-class athlete.metric` por registro de la clase y prueba de arranque (DEK creada por `ensure_keys`); corregir RUNBOOK y guías.
- C4: tercera puerta de descifrado con su prueba de control, ampliación de `IMPORTADORES_REALES`, `test_no_plaintext_at_rest` (fábrica) y `test_audited_tables`, en el mismo slice que la migración 0042.
- C5: `grants.sql`, `test_db_grants.py`, triggers append-only y `LIMPIEZA_DE_SESION` en el mismo slice que cada migración; aristas de `test_service_import_graph`, `MODULES` y `PRIVATE_HELPERS` antes de US-178.
- C6: cubetas y variables `USER_*` decididas por escrito antes de las rutas (reveal y escritura), con sus catálogos de pruebas.
- C7: decidir por escrito el destino de las tres deudas de la sección 7 (sugerencia: quiosco y WhatsApp se cierran en el sprint; las 12 h reales de la TV pasan a evidencia manual) y qué pasa con los resultados de v0.5 sin récord retroactivo.
