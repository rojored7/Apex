# EP-24 · Perfil del atleta — desglose técnico de épica

- **Épica:** `docs/ddd/06_epics/EP-24-perfil-del-atleta.md`
- **Versión:** v0.6
- **Historias:** US-178 a US-184 (7 historias, 26 puntos)

## Resumen

La épica crea el módulo `athletes` (esquema `athletes`) con dos entidades: `BodyMetric`, con todas sus medidas cifradas bajo `athlete.metric` (Q21), y `PersonalRecord`, con RMs y récords de benchmark manuales y derivados. Los récords derivados nacen en el handler de `WodResultValidated` (RN-12 por carga sobre el movimiento principal, Q19; y benchmark, Q20). La comparación de benchmarks y los récords de benchmark se agrupan por `benchmark_id` del catálogo `wods.benchmarks` (N-46). El front es la pestaña Atleta de la ficha con subpestañas Resumen, Medidas, RMs, Récords y Benchmarks.

## Correcciones aplicadas por DECISIONES.md

- US-178: todas las medidas (`weight_kg`, `height_cm`, `body_fat_pct` y `notes`) cifradas bajo `athlete.metric`; solo `id`, `member_id`, `measured_at` y columnas comunes en claro: confirmado por DECISIONES Q21 (corrige el `02_domain_model.md` 2.9, que solo cifraba el peso).
- US-178, US-180 y US-181: rangos de medidas (peso 20 a 400 kg, estatura 50 a 250 cm, grasa 1 a 75 %), RM en kg, empate conserva el más antiguo y `scaled` no deriva RM: supuestos aceptados por DECISIONES N-45.
- US-179: `reveal` de una medida para admin y coach, siempre auditado con campo y usuario: confirmado por DECISIONES Q6.
- US-180 pide `wod_id` de un WOD con `is_benchmark = true` para el récord manual de benchmark → el récord de benchmark lleva `benchmark_id` obligatorio (del catálogo `wods.benchmarks`) y `wod_id` opcional (el intento que lo logró, nulo en un manual); el `Score` se valida con el `score_type` del benchmark: corregido por DECISIONES N-46.
- US-181: el movimiento principal es `wod_movements.is_primary` y solo deriva RM si `score_type = load`; un WOD sin principal no deriva: confirmado por DECISIONES Q19. Los resultados que nacen `validated` en la tablet también emiten `WodResultValidated`: DECISIONES N-42.
- US-182 agrupa benchmarks por título normalizado → se agrupan por `benchmark_id`; dos WODs con el mismo `benchmark_id` son el mismo benchmark, sin importar su título: corregido por DECISIONES N-46. "Mejor" lo decide `results.leaderboard_order(score_type)`: DECISIONES Q20.
- US-183 recibe `?wod={wod_id}` → recibe `?benchmark_id={id}`; un id que no existe en el catálogo devuelve 404 y desaparece el caso "wod que no es benchmark" (422): corregido por DECISIONES N-46.
- US-184: el resumen no descifra medidas (enmascaradas por defecto); coherente con DECISIONES N-01 (las listas y resúmenes no muestran valores, ni enmascarados calculados; solo "•••" con `MaskedValue`) y Q6.

## Validación contra el dominio y la arquitectura

- Dominio: `BodyMetric` y `PersonalRecord` como entidades bajo la raíz lógica `Member` (`02_domain_model.md` 2.9) con Q21, Q20, N-45 y N-46. Funciones puras del contrato de pruebas: `athletes.derive_record(result, current_rm)` (sección 4 del modelo) más `validate_metric`, `current_record`, `derive_benchmark_record`, `benchmark_series`, `summary`.
- Invariantes: RN-12 y Q19 (derivación de RM), Q20 (benchmark), RN-13 (medidas cifradas, mostrar en claro se audita), RN-14 (ni medidas ni récords se borran ni se editan por API; una corrección es una medición nueva), idempotencia del handler por `result_id` (índice único parcial).
- Eventos: consume `WodResultValidated` (results, EP-22) con payload que trae la marca completa; emite `PersonalRecordSet(member_id, record_id, kind, movement_id | None, benchmark_id | None, value, achieved_at)` (lo consume EP-25, US-195); `SensitiveFieldRevealed` en US-179.
- El handler corre dentro de la transacción del emisor (`02_domain_model.md` sección 3): si falla, se revierte el registro o la validación del resultado.
- Llamadas service a service: `athletes` → `members.service` (existe y no está dado de baja), `athletes` → `wods.service` (`get_movement`, `score_meta`, `primary_movement`, `get_benchmark`, `wod_ids_for_benchmark`), `athletes` → `results.service` (`member_results(member_id, benchmark_id, only_current=True, status="validated")` para la comparación, y la función pura `leaderboard_order`). Ningún módulo importa `athletes`; `results` no conoce a `athletes` (solo emite el evento). Sin ciclos. Nunca se leen models de `results` ni de `wods`.
- Bus de criptografía: las columnas cifradas usan `Encrypted("athlete.metric")` de `core/crypto/types.py` con AAD = id del registro (asignado en Python antes del flush, US-012); `athlete.metric` se registra en `core/crypto/registry.py` (N-04) y su DEK se crea con `cli init-keys --data-class athlete.metric`. El valor se convierte a texto decimal antes de cifrar. `reveal_metric` descifra por el bus. Ninguna primitiva fuera de `core/crypto`.
- Auditoría: `__audited__ = True` en `body_metrics` y `personal_records`; la auditoría guarda el blob, nunca el valor. La fila `reveal` la escribe `athletes.service` con `core.audit.record(...)` en la misma transacción, igual que el patrón resuelto en US-074/US-107.
- Roles: todas las rutas `/athletes/*` con `require_role("admin", "coach")`; el socio accede por `/me/*` en EP-25.
- Paginación en listas de medidas, récords, RMs y benchmarks.

## Tablas y migraciones

- `0085_athletes_schema_body_metrics` (US-178): `CREATE SCHEMA athletes`; `athletes.body_metrics` (`member_id` uuid sin FK entre esquemas, `measured_at` timestamptz, `weight_kg` text nulo, `height_cm` text nulo, `body_fat_pct` text nulo, `notes` text nulo — las cuatro como blob `apx1.*` —, `recorded_by` uuid, columnas comunes); índice `(member_id, measured_at DESC)`; CHECK de que al menos una de las tres medidas no es nula.
- `0086_athletes_personal_records` (US-180, US-181): `athletes.personal_records` (`member_id`, `kind` CHECK en `rm`/`benchmark`, `movement_id` uuid nulo, `benchmark_id` uuid nulo, `wod_id` uuid nulo, `value_kg` numeric(6,2) nulo, `level`, `seconds`, `rounds`, `reps`, `load_kg`, `capped` para la marca de benchmark, `achieved_at` timestamptz, `source` CHECK en `manual`/`derived`, `result_id` uuid nulo, columnas comunes); CHECK de coherencia (`kind = rm` exige `movement_id` y `value_kg`, `kind = benchmark` exige `benchmark_id`; `source = derived` exige `result_id`); índices `(member_id, kind, movement_id)` y `(member_id, kind, benchmark_id)`; índice único parcial `(result_id) WHERE result_id IS NOT NULL` (idempotencia de US-181 y US-182).
- Si se acepta la propuesta de US-181: `0087_athletes_personal_records_invalidated` agrega `invalidated_at` timestamptz nulo e `invalidated_by_result_id` uuid nulo (columnas nulas, sin datos que llenar).
- Números 0088 y 0089 libres.

## Services y eventos

- Funciones puras de `athletes.service`: `validate_metric(weight_kg, height_cm, body_fat_pct, measured_at, now) -> None | MetricError`; `current_record(records, kind, target) -> PersonalRecord | None` (mayor valor; empate, el de `achieved_at` más antiguo; excluye invalidados si aplica la propuesta de US-181); `derive_record(result, primary, current_rm) -> RecordDraft | None` (solo `score_type = load`, con principal, `level` distinto de `scaled`, `load_kg` estrictamente mayor que el vigente o mayor que 0 sin vigente); `derive_benchmark_record(result, current_best, order_key) -> RecordDraft | None` (estrictamente mejor según `leaderboard_order`; empate no crea); `benchmark_series(attempts, order_key) -> list[Attempt]` (exactamente un `is_best`, diferencia con el anterior); `summary(last_metric_at, rms, records, benchmarks_count) -> AthleteSummary`.
- Casos de uso: `add_metric(member_id, data, by)`, `list_metrics(member_id, limit, offset)` (enmascarado, sin descifrar), `reveal_metric(member_id, metric_id, field, by)` (404 si la medición no es del socio; `value = null` sin fila `reveal` si el campo es nulo), `add_manual_record(member_id, data, by)` (emite `PersonalRecordSet` solo si queda vigente), `list_records(member_id, kind, limit, offset)` con `is_current` por ítem, `rms(member_id, limit, offset)`, `benchmarks(member_id, benchmark_id | None, limit, offset)`, `summary_for(member_id)`.
- Handler: `on_wod_result_validated(event)` registrado con `core.events.subscribe` al importar `athletes/service.py`; pide `wods.service.score_meta(event.wod_id)`; si es `load` con principal, compara con el RM vigente propio; si tiene `benchmark_id`, compara con el mejor récord de ese benchmark; inserta con `created_by = event.validated_by` y emite `PersonalRecordSet`.
- Contratos que esta épica pide a otras: `wods.service.primary_movement(wod_id)`, `get_movement(id)`, `get_benchmark(id)`, `score_meta(wod_id)` (EP-22); `results.service.member_results(member_id, benchmark_id, only_current, status)` (nueva consulta en EP-22 o aquí, en el service de results); `members.service.ensure_active(member_id)` (404 si no existe o está dado de baja).
- Contratos que esta épica expone a EP-25: `list_metrics_revealed(member_id, by)` (descifra y deja una fila `reveal` por petición, US-191), `add_metric(member_id, data, by, allowed_fields={"weight_kg", "notes"})`, `list_records`, `rms`, `benchmarks`.

## Endpoints

- `POST /api/v1/athletes/{member_id}/metrics` — roles: admin, coach
- `GET /api/v1/athletes/{member_id}/metrics` — roles: admin, coach
- `POST /api/v1/athletes/{member_id}/metrics/{metric_id}/reveal` — roles: admin, coach
- `POST /api/v1/athletes/{member_id}/records` — roles: admin, coach
- `GET /api/v1/athletes/{member_id}/records` — roles: admin, coach
- `GET /api/v1/athletes/{member_id}/benchmarks` — roles: admin, coach
- `GET /api/v1/athletes/{member_id}/summary` — roles: admin, coach
- `GET /api/v1/athletes/{member_id}/rms` — roles: admin, coach

## Componentes de front

- `web/src/features/athletes/`: `api.ts` (`useMetrics`, `useAddMetric`, `useRevealMetric`, `useRecords`, `useAddRecord`, `useRms`, `useBenchmarks`, `useAthleteSummary`), `schemas.ts` (Zod de medición con los rangos de N-45 y de récord por `kind`), `pages/AthleteProfile.tsx` (ruta `/socios/:id/atleta`, `Tabs` con la subpestaña en `?tab=`), `components/MetricsTab.tsx` (tabla con `MaskedValue` conectado a `reveal`, formulario en `SidePanel`), `components/RmsTab.tsx` y `components/RecordsTab.tsx` (vigente con texto "Vigente", origen "Manual"/"Derivado" con texto), `components/BenchmarksTab.tsx` (selector de benchmark, tabla y gráfica de línea con tokens; el mejor marcado "Mejor"), `components/SummaryCards.tsx` (`KpiCard`).
- Socio dado de baja: pestaña en solo lectura sin botones de registrar.
- Pruebas Vitest por subpestaña y del `MaskedValue` conectado; capturas en 768, 1024 y 1440 en claro y oscuro; Playwright `web/tests/e2e/athlete-profile.spec.ts` (abrir ficha, pestaña Atleta, registrar medición, revelar peso).

## Worker, CLI e infraestructura

- CLI: `cli init-keys --data-class athlete.metric` (comando existente de US-023 con `--data-class`, requisito de US-140) para crear la DEK; documentado en el runbook de despliegue de v0.6.
- Worker: nada.
- Pruebas de arquitectura: `api/tests/architecture/test_no_plaintext_columns.py` ampliada a `athletes.body_metrics` (ninguna fila con un número en claro en las cuatro columnas); `test_no_cross_models.py` verde con `athletes`; `test_banned_imports.py` verde.

## Dependencias

- EP-22 · US-165 (movimientos con `unit`), US-166 (WOD, principal y catálogo de benchmarks, incluida su pregunta abierta), US-169 y US-170 (emisión de `WodResultValidated` con payload completo; corrección), US-171 (`leaderboard_order`).
- EP-02 · US-023 (`init-keys`), US-025 o US-027 (registro de `data_class`), US-028 (tipos `Encrypted`).
- EP-07 · US-073 (ficha y pestañas), US-074 (patrón de `reveal` auditado).
- EP-11 · US-107 (acción `reveal` en auditoría).
- EP-06 · `Tabs`, `MaskedValue`, `SidePanel`, `KpiCard`.
- Consumidores: EP-25 (US-191 rutas `/me/*` de progreso; US-195 consume `PersonalRecordSet`).

## Riesgos

- Front condicionado a D1: si el gate no aprueba S1, salen las subpestañas (unas 35 h).
- Un error tipográfico en la tablet (por ejemplo 1000 kg en vez de 100) crea un RM derivado que nunca se borra (RN-14) y queda vigente para siempre aunque se corrija el resultado — mitigación: pregunta de US-181.
- Catálogo de benchmarks sin mantenimiento definido (pregunta de US-166 en EP-22): sin catálogo no hay récords de benchmark ni comparación — mitigación: la propuesta por defecto de US-166.
- La DEK de `athlete.metric` debe existir antes del primer alta; si falta, el alta falla con 503 — mitigación: paso de despliegue de v0.6 y prueba de arranque que verifica las `data_class` registradas.
- Volumen de descifrados en `/me/metrics` (EP-25) y en la gráfica de peso: cada lectura descifra N filas — mitigación: paginación y `crypto_ops.count` por lote (N-05).
- Coherencia de unidades: un RM manual sobre un movimiento con `unit` distinta de kg se rechaza (422); los movimientos de gimnasia no tienen RM en v0.6.

## Estado y estimación por historia

- US-178 · Registrar medidas corporales cifradas — **READY** — 22 h — Tabla con las cuatro columnas bajo `athlete.metric` (Q21) y rangos de N-45.
- US-179 · Mostrar medida en claro auditada — **READY** — 7 h — `reveal` por campo con fila de auditoría y `crypto_ops`, patrón de US-074 (Q6).
- US-180 · Registrar récords manuales — **READY** — 14 h — Tabla de récords; el de benchmark usa `benchmark_id` y no `wod_id` (corregido por N-46).
- US-181 · Récord derivado por carga — **NEEDS_REFINEMENT** — 22 h — Cuando US-170 corrige un resultado que ya derivó un RM, ¿el RM sigue vigente (supuesto de la historia) o se marca invalidado sin borrarse? Propuesta por defecto: `results.correct` emite `WodResultSuperseded(old_result_id, new_result_id)` y `athletes` marca `invalidated_at` en el récord derivado de `old_result_id`, que deja de contar para `current_record` (incluido en las 22 h, unas 4 h, y toca US-170).
- US-182 · Récord derivado de benchmark — **READY** — 11 h — Mismo handler; agrupa por `benchmark_id` (corregido por N-46) y compara con `leaderboard_order` (Q20).
- US-183 · Comparar benchmarks — **READY** — 13 h — Serie por `benchmark_id` (corregido por N-46) leyendo `results.service.member_results`, sin models ajenos.
- US-184 · Perfil del atleta en la ficha — **READY** — 20 h — Resumen y RMs vigentes sin descifrar; pestaña con cinco subpestañas.

## Total de la épica

- **Total: 109 h**
