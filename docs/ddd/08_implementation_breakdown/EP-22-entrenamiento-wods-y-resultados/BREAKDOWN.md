# EP-22 · Entrenamiento: movimientos, WODs y resultados — desglose técnico de épica

- **Épica:** `docs/ddd/06_epics/EP-22-entrenamiento-wods-y-resultados.md`
- **Versión:** v0.5
- **Historias:** US-165 a US-174 (10 historias, 41 puntos)

## Resumen

La épica crea el contexto Training con dos módulos de código: `wods` (catálogo de movimientos, catálogo de benchmarks, WODs y sus movimientos) y `results` (resultados con corrección por reemplazo, leaderboard y consultas por socio). Toca además `classes` (asignar un WOD a una sesión, lista de asistentes para la tablet) y `dashboard` (campo `wod_today`). El corazón técnico es `results.wod_results`: inmutable por trigger salvo `is_current` y las columnas de validación (Q18), con índice único parcial `(wod_id, member_id) WHERE is_current` (RN-11). El leaderboard ordena con `results.leaderboard_order(score_type)` y nunca toca campos cifrados del socio.

Orden de construcción sugerido (corte natural de la épica): primero `wods` (US-165, US-166, US-167, US-168), después `results` (US-169, US-170, US-171, US-172, US-173) y al final el tablero (US-174).

## Correcciones aplicadas por DECISIONES.md

- US-166 y US-167 tratan `is_benchmark` como columna booleana del WOD → existe el catálogo `wods.benchmarks` (`name` único, `description`, `score_type`); el WOD lleva `benchmark_id` opcional y `is_benchmark` se deriva (`benchmark_id IS NOT NULL`), sin columna propia: corregido por DECISIONES N-46. El filtro `benchmark=true` de US-167 y US-173 se resuelve sobre `benchmark_id IS NOT NULL` y se agrega el filtro `benchmark_id`.
- US-166 deja como pregunta abierta si "un WOD principal por fecha" es unicidad de `date` → se implementa como índice único sobre `wods.wods.date`; `score_type` es inmutable cuando el WOD tiene resultados (422 `score_type_locked`); `PATCH /class-sessions/{id}` entra al contrato: corregido por DECISIONES N-41 (aceptado).
- US-166: `wod_movements.is_primary` con índice único parcial `(wod_id) WHERE is_primary`: confirmado por DECISIONES Q19.
- US-169 y US-170: `is_current` con UPDATE permitido por el trigger y corrección por `supersedes_id`: confirmado por DECISIONES Q18. El trigger solo deja pasar `status` (de `pending` a `validated`), `validated_by` y `validated_at` (de nulo a valor, una vez), `is_current` (de `true` a `false`, una vez) y `updated_at`.
- US-169: el resultado registrado por coach o admin nace `validated` y emite `WodResultRecorded` y `WodResultValidated` en la misma transacción: supuesto aceptado por DECISIONES N-42.
- US-171 deja el time cap como pregunta → `seconds = time_cap_s` con `capped = true`, ordenados después de todos los que terminaron (entre ellos, por `reps` logradas descendente); `rx` y `rx_plus` comparten grupo: corregido por DECISIONES N-43 (aceptado). Implica una columna `capped` en `wod_results` que US-169 no lista.
- US-171: socios con `sex` nulo (y `x`) solo aparecen en "Todos": confirmado por DECISIONES Q22.
- US-168 y US-174: "hoy" es `today_bogota()` de `core/clock.py`: confirmado por DECISIONES Q28.

## Validación contra el dominio y la arquitectura

- Aggregates: `Movement` (raíz, nombre único, no se borra), `Benchmark` (raíz de catálogo nueva por N-46), `Wod` con entidad interna `WodMovement` (copia de valores: reps, cargas y además el nombre del movimiento como `movement_name` para que un renombre del catálogo no cambie WODs pasados, dominio 2.7), `WodResult` con value object `Score`. Coincide con `02_domain_model.md` 2.6 a 2.8 más Q18, Q19, N-43 y N-46.
- Invariantes: RN-11 (índice único parcial y 409 en service), RN-14 (sin DELETE, trigger), `validate_score` por `score_type`, a lo sumo un movimiento principal (función pura y índice), un WOD por fecha (índice único), `score_type` del WOD con `benchmark_id` igual al del benchmark (derivado de N-46: sin eso no se pueden comparar intentos; se valida en `validate_wod`).
- Eventos emitidos: `WodPublished(wod_id, date)` (wods); `WodResultRecorded(result_id, member_id, wod_id, load_kg, primary_movement_id)` y `WodResultValidated(result_id, member_id, wod_id, level, seconds, rounds, reps, load_kg, capped, validated_by)` (results). El payload de `WodResultValidated` lleva la marca completa para que el handler de Athletes (EP-24) no tenga que volver a pedir el resultado. Ningún evento consumido en esta épica.
- Reglas de módulos: `wods` no depende de nadie. `results` llama a `wods.service` (WOD, `score_type`, time cap), a `classes.service` (sesión, WOD efectivo, asistentes, verificación de asistencia) y a `members.service.public_names(ids)` (nombre, apellido y sexo, nunca campos cifrados). `classes` llama a `wods.service.exists` y `wods.service.for_date` para asignar y resolver el WOD efectivo. `dashboard` llama a `wods.service.today()`. No hay ciclos: `wods` no importa `classes` ni `results`. La lista "sesiones que usan este WOD" de `WOD_Detalle` la sirve `classes` (`GET /class-sessions?wod_id=`), no `wods`, para no crear el ciclo `wods` ↔ `classes`.
- Escritura con varios módulos: `PUT /results` hace lecturas de validación en `wods`, `classes` y `members` y una sola escritura propia; los efectos cruzados (récords) van por evento. Es el mismo patrón que `memberships.sell` en v0.1; no se encadenan escrituras de tres módulos.
- Las rutas que cuelgan de otros recursos viven en el router del módulo dueño de los datos que devuelven: `GET /members/{id}/results` y `GET /class-sessions/{id}/attendance` en `results/router.py` (supuesto de US-173, así Members no depende de Training); `GET /wods/{id}/leaderboard` y `GET /wods/{id}/results` en `results/router.py`; `PATCH /class-sessions/{id}` en `classes/router.py`.
- Bus de criptografía: no se usa. Training no lee campos cifrados; prueba de arquitectura `api/tests/architecture/test_training_no_crypto.py` falla si `wods` o `results` importan `core.crypto` o llaman `members.service.reveal`/`get`.
- Lint banned-api: sin primitivas en `wods` ni `results`.
- Roles: todas las rutas `require_role("admin", "coach")`; `GET /wods/today` se abre a `member` en EP-25 (US-189).
- Paginación: `limit` 1 a 200 (25 por defecto) y `offset` con `{items, total, limit, offset}` en movimientos, WODs, asistentes, leaderboard, resultados por WOD y por socio.
- Auditoría: `__audited__ = True` en `wods.movements`, `wods.benchmarks`, `wods.wods`, `wods.wod_movements`, `results.wod_results` y el cambio de `wod_id` en `classes.class_sessions`.
- Columnas comunes en todas las tablas (mixin `CommonColumnsMixin`, UUID asignado en Python).

## Tablas y migraciones

- `0070_wods_schema_movements` (US-165): `CREATE SCHEMA wods`; `wods.movements` (`name` text, `category` text CHECK en `weightlifting`/`gymnastics`/`monostructural`/`other`, `unit` text CHECK en `kg`/`reps`/`m`/`cal`/`s`, `is_active` bool por defecto true, columnas comunes); índice único sobre `lower(btrim(name))`; downgrade borra tabla y esquema.
- `0071_wods_benchmarks` (US-166, N-46): `wods.benchmarks` (`name`, `description`, `score_type` CHECK en `time`/`rounds_reps`/`reps`/`load`, `is_active`, columnas comunes); índice único sobre `lower(btrim(name))`.
- `0072_wods_wods` (US-166): `wods.wods` (`date` date, `title`, `score_type` CHECK, `time_cap_s` int nulo CHECK `>= 0`, `benchmark_id` uuid nulo FK a `wods.benchmarks`, `description`, columnas comunes); índice único sobre `date` (N-41); índice sobre `benchmark_id`; índice `lower(title)` para la búsqueda.
- `0073_wods_wod_movements` (US-166): `wods.wod_movements` (`wod_id` FK a `wods.wods` ON DELETE RESTRICT, `movement_id` FK a `wods.movements`, `movement_name` text copia, `order` smallint, `reps` text, `load_rx_m_kg` numeric(6,2) nulo CHECK `>= 0`, `load_rx_f_kg` numeric(6,2) nulo CHECK `>= 0`, `notes`, `is_primary` bool por defecto false, columnas comunes); índice único `(wod_id, order)`; índice único parcial `(wod_id) WHERE is_primary` (Q19).
- `0074_results_schema_wod_results` (US-169): `CREATE SCHEMA results`; `results.wod_results` (`wod_id` uuid, `member_id` uuid, `session_id` uuid nulo, sin FK entre esquemas; `level` CHECK en `rx`/`rx_plus`/`scaled`; `seconds`, `rounds`, `reps` int nulos CHECK `>= 0`; `load_kg` numeric(6,2) nulo CHECK `>= 0`; `capped` bool por defecto false (N-43); `scaled_notes`; `status` CHECK en `validated`/`pending`; `recorded_by`, `validated_by` uuid nulo, `validated_at` timestamptz nulo; `supersedes_id` uuid nulo FK a sí misma; `is_current` bool por defecto true; columnas comunes); índice único parcial `(wod_id, member_id) WHERE is_current` (Q18); índices parciales `(wod_id, status) WHERE is_current` y `(member_id) WHERE is_current` (US-171, US-173); índice único parcial `(supersedes_id) WHERE supersedes_id IS NOT NULL` (un resultado se reemplaza una sola vez).
- `0075_results_immutability` (US-169): función PL/pgSQL `results.forbid_mutation()` y trigger `BEFORE UPDATE OR DELETE` en `results.wod_results`: rechaza todo DELETE; en UPDATE compara `OLD` y `NEW` columna por columna y solo permite `status` `pending → validated`, `validated_by` y `validated_at` de nulo a valor, `is_current` `true → false` y `updated_at`; cualquier otra diferencia lanza excepción. Downgrade borra trigger y función.
- `classes.class_sessions.wod_id` ya existe desde US-156 (EP-21): no hay migración en esta épica para esa columna.
- Números 0076 a 0079 quedan libres en el rango.

## Services y eventos

- `wods.service`, funciones puras: `normalize_movement_name(name) -> str`; `validate_wod(score_type, time_cap_s, movements, benchmark_score_type | None) -> None | WodError` (lista vacía, dos principales, time cap negativo, cargas negativas, `score_type` distinto del benchmark); `week_range(week_iso) -> tuple[date, date]`; `effective_wod_id(session_wod_id, day_wod_id) -> UUID | None`.
- `wods.service`, casos de uso: `list_movements(q, category, active, limit, offset)`, `create_movement(data, by)`, `update_movement(id, data, by)` (incluye `is_active`); `list_benchmarks`, `create_benchmark`, `update_benchmark` (sujeto a la pregunta de US-166); `create(data, by) -> Wod` (reemplaza la lista de movimientos en la transacción, copia `movement_name`, emite `WodPublished`); `update(id, data, by)` (bloquea `score_type` si `results.service.count_for_wod(id) > 0` — ver nota de dependencia abajo); `get(id)`; `list(week | q, benchmark, benchmark_id, limit, offset)` con `movement_count`; `today()`; `for_date(date)`; `exists(id)`.
- Contratos que `wods.service` expone a otros: `today()` (dashboard, tv, portal), `for_date(date)` y `exists(id)` (classes), `get(id)` y `score_meta(wod_id) -> {score_type, time_cap_s, date, benchmark_id, primary_movement_id}` (results, athletes), `primary_movement(wod_id)` y `get_movement(id)` (athletes, EP-24), `wod_ids_for_benchmark(benchmark_id)` (results, athletes), `get_benchmark(id)` (athletes).
- Nota de dependencia: para bloquear `score_type` con resultados, `wods` necesitaría preguntar a `results`, y `results` ya depende de `wods` (ciclo). Se resuelve sin ciclo: `results` se suscribe a nada y en cambio `wods.update` recibe la cuenta desde el router de `wods`, que llama a `results.service.count_for_wod(id)` antes de llamar a `wods.service.update(id, data, by, has_results=...)`. El router puede importar dos services sin ciclo de imports entre services.
- `results.service`, funciones puras: `validate_score(score_type, seconds, rounds, reps, load_kg, capped, time_cap_s) -> None | ScoreError`; `leaderboard_order(score_type) -> Callable` (grupo `rx`/`rx_plus` antes que `scaled`; `time` ascendente con `capped` después de los terminados y entre ellos `reps` descendente; `rounds_reps` por rondas y luego reps descendente; `reps` y `load` descendente; desempate estable por apellido); `rank(results, order_key) -> list[Ranked]` (posiciones compartidas en empate); `filter_by_sex(rows, sex)` (Q22).
- `results.service`, casos de uso: `record(data, by) -> WodResult` (sin `supersedes_id`; valida WOD por `wods.service.score_meta`, asistencia por `classes.service.has_attendance(session_id, member_id)` cuando hay `session_id`, socio por `members.service.public_names([member_id])` cuando no; 409 `existing_id` si hay vigente; emite `WodResultRecorded` y `WodResultValidated`); `correct(supersedes_id, data, by)` (bloquea la fila anterior con `SELECT … FOR UPDATE`, valida que sea vigente, del mismo socio y WOD; pone `is_current = false` y luego inserta el nuevo; 409 `invalid_supersedes`; emite los mismos eventos); `attendance_for_session(session_id, limit, offset)` (pide `classes.service.attendees(session_id, limit, offset)` y agrega `has_result`); `leaderboard(wod_id, level, sex, limit, offset)` (solo `is_current` y `validated`; nombres por `members.service.public_names`); `list_for_wod(wod_id, include_superseded, status, limit, offset)`; `list_by_member(member_id, benchmark, limit, offset)`; `count_for_wod(wod_id)`.
- `results.service.submit` y `validate` (estado `pending` y validación) son de EP-25; el modelo y el trigger ya los soportan desde aquí.
- `classes.service` (cambios de esta épica): `assign_wod(session_id, wod_id | None, by)` (422 si `wods.service.exists` es falso, 409 si la sesión está `cancelled`, auditado); `get(session_id)` devuelve `effective_wod_id` con `wods.service.for_date(fecha Bogotá de starts_at)`; `attendees(session_id, limit, offset)` (solo asistencias con `removed_at IS NULL`, N-40, con `first_name` y `last_name`); `has_attendance(session_id, member_id)`; filtro `wod_id` en la lista de sesiones.
- `members.service.public_names(ids) -> dict[UUID, {first_name, last_name, sex}]` (contrato nuevo de US-171; puede extender `names_for` de v0.1 agregando `sex`).
- `dashboard.service.summary` llena `wod_today` con `wods.service.today()` proyectado a `{id, title, score_type, is_benchmark}`.

## Endpoints

- `GET /api/v1/movements` — roles: admin, coach
- `POST /api/v1/movements` — roles: admin, coach
- `PATCH /api/v1/movements/{id}` — roles: admin, coach
- `GET /api/v1/benchmarks` — roles: admin, coach
- `POST /api/v1/benchmarks` — roles: admin, coach
- `PATCH /api/v1/benchmarks/{id}` — roles: admin, coach
- `GET /api/v1/wods` — roles: admin, coach
- `POST /api/v1/wods` — roles: admin, coach
- `GET /api/v1/wods/{id}` — roles: admin, coach
- `PATCH /api/v1/wods/{id}` — roles: admin, coach
- `GET /api/v1/wods/today` — roles: admin, coach
- `PATCH /api/v1/class-sessions/{id}` — roles: admin, coach
- `GET /api/v1/class-sessions/{id}/attendance` — roles: admin, coach
- `PUT /api/v1/results` — roles: admin, coach
- `GET /api/v1/wods/{id}/leaderboard` — roles: admin, coach
- `GET /api/v1/wods/{id}/results` — roles: admin, coach
- `GET /api/v1/members/{id}/results` — roles: admin, coach
- `GET /api/v1/dashboard` — roles: admin, coach

Las tres rutas de `/benchmarks` dependen de la respuesta a la pregunta de US-166.

## Componentes de front

- `web/src/features/wods/`: `api.ts` (hooks `useMovements`, `useCreateMovement`, `useUpdateMovement`, `useBenchmarks`, `useWods`, `useWod`, `useWodToday`, `useSaveWod`), `schemas.ts` (Zod de movimiento, WOD y movimientos del WOD, con la regla de un solo principal), `pages/MovementsPage.tsx` (`FilterBar`, `DataTable`, `Pagination`, `SidePanel`), `pages/WodFormPage.tsx` (react-hook-form + Zod, lista ordenable de movimientos, selector de benchmark), `pages/WodListPage.tsx` (semana ISO con navegación, búsqueda con "solo benchmarks"), `pages/WodDetailPage.tsx` (encabezado, movimientos con principal marcado por texto, sesiones que lo usan, leaderboard y pestaña "Todos los resultados"), `components/Leaderboard.tsx` (`Chips` de nivel y sexo).
- `web/src/features/classes/components/SessionWodSelector.tsx` en `Sesiones` (selector "WOD de esta sesión", `DESIGN-GAP` si falta).
- `web/src/features/results/`: `api.ts` (`useSessionAttendance`, `useRecordResult`, `useCorrectResult`, `useWodResults`, `useMemberResults`), `schemas.ts` (Zod del `Score` por `score_type`, espejo de `validate_score`), `pages/ResultsEntryPage.tsx` en `GymLayout` (controles de 56 px, formulario por fila, acción "Corregir" con `ConfirmModal`), `components/ScoreFields.tsx`, `lib/formatScore.ts` (compartido con TV).
- `web/src/features/members/components/ResultsTab.tsx` (pestaña Resultados de la ficha, filtro "solo benchmarks", marca "por validar").
- `web/src/features/dashboard/components/WodTodayCard.tsx` (`KpiCard`, estado "Sin WOD publicado").
- Pruebas Vitest por página y por componente; Playwright `web/tests/e2e/results-entry.spec.ts` (registrar la clase de 15 socios) en 1024 × 768 tema oscuro. Nada de colores literales.

## Worker, CLI e infraestructura

- Worker: ningún job nuevo.
- CLI: si se acepta la propuesta de US-166, `cli seed-benchmarks [--as <email>]` idempotente por nombre normalizado, auditado, con `SYSTEM_USER_ID` por defecto (N-15), para sembrar los benchmarks clásicos.
- Infra: ninguna. `docs/openapi.json` se regenera con las rutas nuevas.
- Pruebas de arquitectura nuevas o ampliadas: `api/tests/architecture/test_no_cross_models.py` sigue verde con `wods` y `results`; `api/tests/architecture/test_training_no_crypto.py` (nuevo); `api/tests/architecture/test_every_route_has_role.py` cubre las rutas nuevas.

## Dependencias

- EP-21 · US-156 (columna `class_sessions.wod_id`), US-157 (lista de sesiones, se agrega el filtro `wod_id`), US-159 (asistencia), US-161 y N-40 (asistencias con `removed_at`).
- EP-07 · US-069 y US-070 (`names_for`, base de `public_names`), US-073 (ficha del socio para la pestaña Resultados).
- EP-12 · US-108 (contrato del tablero con `wod_today` en `null`).
- EP-01 · US-012 (mixin), US-016 (hook de auditoría), US-017 (bus de eventos), `core/clock.py` (`today_bogota`).
- EP-03 · US-034 (`require_role`), US-035 (prueba de rutas con rol).
- EP-06 · US-061 (`PanelLayout`), US-062 (`GymLayout`), kit compartido (`DataTable`, `Chips`, `SidePanel`, `ConfirmModal`, `KpiCard`).
- Consumidores aguas abajo: EP-23 (US-176 usa `wods.service.today` y `results.service.leaderboard`), EP-24 (US-180 a US-183 usan `primary_movement`, `get_movement`, `get_benchmark`, `wod_ids_for_benchmark` y el payload de `WodResultValidated`), EP-25 (US-189 y US-190 usan el modelo, el trigger y la bandeja).

## Riesgos

- Front condicionado a D1: si el gate no aprueba S1, salen las tareas de `web/` de las diez historias (unas 60 h).
- Trigger de `wod_results` mal escrito: bloquea correcciones y validaciones legítimas o deja editar marcas — mitigación: prueba de service por cada columna permitida y por cada columna prohibida, y prueba de DELETE.
- Concurrencia en la corrección: dos coaches corrigen el mismo resultado a la vez — mitigación: `SELECT … FOR UPDATE` sobre el anterior, índice único parcial y prueba de dos sesiones concurrentes (una gana, la otra 409).
- Catálogo de benchmarks sin dueño de mantenimiento (N-46 lo crea, ninguna historia lo administra): bloquea el WOD benchmark y toda la EP-24 — mitigación: pregunta de US-166 con propuesta por defecto.
- `members.service.public_names` duplicando `names_for`: dos contratos parecidos — mitigación: un solo método con `sex` incluido.
- Unicidad de `date`: un box que programe dos WODs nuevos el mismo día no puede (N-41 lo acepta) — mitigación: la sesión puede apuntar a un WOD de otra fecha (benchmark).
- Rendimiento del leaderboard (300 ms con 60 resultados): el ranking se calcula en Python sobre los vigentes del WOD — mitigación: índice parcial `(wod_id, status) WHERE is_current` y prueba de tiempo.
- Prueba de uso de la tablet (15 socios en menos de 5 minutos) depende del coach real — mitigación: sesión de prueba registrada como evidencia antes de cerrar US-169.

## Estado y estimación por historia

- US-165 · Catálogo de movimientos — **READY** — 20 h — CRUD sobre `wods.movements` con unicidad por nombre normalizado, sin dudas abiertas.
- US-166 · Crear y editar WOD — **NEEDS_REFINEMENT** — 40 h — N-46 crea el catálogo `wods.benchmarks` pero ninguna historia lo mantiene: ¿se agrega a US-166 un CRUD mínimo `GET/POST/PATCH /benchmarks` (admin y coach) con selector en `WOD_Form` y `cli seed-benchmarks` con los clásicos? Propuesta por defecto: sí (incluido en las 40 h, unas 6 h), y un WOD con `benchmark_id` debe tener el mismo `score_type` del benchmark.
- US-167 · Calendario de WODs — **READY** — 12 h — Lista por semana ISO y búsqueda; el filtro benchmark usa `benchmark_id` (N-46).
- US-168 · WOD del día y asignación a sesiones — **READY** — 13 h — `GET /wods/today` y `PATCH /class-sessions/{id}` en el router de classes (N-41), sin ciclo entre `wods` y `classes`.
- US-169 · Registrar resultados en tablet — **READY** — 38 h — Tabla, trigger, índice parcial (Q18), columna `capped` (N-43), eventos en la transacción (N-42) y pantalla de tablet con E2E.
- US-170 · Corregir resultado — **READY** — 12 h — Corrección por reemplazo con bloqueo de fila e índice parcial; ninguna fila se borra.
- US-171 · Leaderboard del día — **READY** — 20 h — `leaderboard_order` con N-43 y Q22; nombres por `members.service.public_names`, sin campos cifrados.
- US-172 · Detalle de WOD — **READY** — 11 h — `GET /wods/{id}/results` con `include_superseded`; página de detalle.
- US-173 · Pestaña Resultados de la ficha — **READY** — 8 h — Ruta en el router de results; filtro benchmark por `benchmark_id` (N-46).
- US-174 · Tarjeta WOD de hoy en Inicio — **READY** — 4 h — Llena `wod_today` del contrato estable del tablero con `today_bogota()`.

## Total de la épica

- **Total: 178 h**
