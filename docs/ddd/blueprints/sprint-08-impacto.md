# Sprint 8 (v0.5) · Análisis de impacto previo (Fase 0)

Anclado a HEAD `8b2db15` (= main, árbol limpio, rama `feat/sprint-08-wods-resultados-tv`). Solo lectura.

Veredicto: AMARILLO

## 1. Blast radius (archivos de `api/src` + `api/tests` que importan el módulo; conteo por grep)

- classes: 115 (PATCH de sesión; `wod_id` hoy sin FK ni validación: `models.py:138`; filtro `wod_id` de la lista; `attendees` para el registro en tablet).
- members: 317 (`names_for` con sexo ya existe, `service.py:637`; pestaña Resultados; sexo nulo solo en "Todos", Q22).
- dashboard: 16 (`schemas.py:92` `wod_today: str | None` pasa a objeto: `api/tests/dashboard/{test_dashboard_contract,_apoyo}.py`; web: `FutureKpis.tsx` y su test, `features/dashboard/schemas.ts`, `web/src/test/dashboard.tsx`).
- settings: 112 (la clave `tv` existe en el CHECK de `0005` y en `SectionKey.tv`, pero NO está en `ENABLED_SECTIONS` ni en `SECTION_REGISTRY`: hay que habilitarla con esquema, vista sin hash y `regenerate-token`; cambian las pruebas que fijan el número de secciones).
- auth/security: auth 179, `core.security` 197. `PUBLIC_ROUTES` ya trae `GET /api/v1/tv/today` y `DEVICE_TOKEN_ROUTES` (`security.py:550,571`); falta la dependencia `__apex_device_token__` (`_route_has_device_token`, línea 628). `test_every_route_has_role.py:76` fija `len(PUBLIC_ROUTES) == 8`: se mantiene si no se agrega otra ruta pública.
- audit / `core.audit`: 55 / 207 (corrección de resultados; regeneración del token con hash, nunca en claro, Q12).
- `core.ratelimit`: 46 (cubeta TV 12/min y cubetas de escritura de resultados; sube el catálogo de cubetas fijado en `tests/core/test_ratelimit*.py`, ver `CATALOGO` hacia la línea 398).
- `core.events`: 43 (`WodResultValidated`, tipo definido en `results` y exportado por su `service.py`).
- `core.locks`: 26 (`FOR UPDATE` del resultado anterior pasa por `core/locks.py`).
- `worker.registry`: 25 (sin job de producción nuevo; solo el job nocturno de 12 h en CI, fuera del gate de PR).
- Módulos nuevos (no existen): `wods`, `results`, `tv`. Van en `main.MODULES` (tras `classes`, antes de `dashboard`), en `test_service_import_graph.py` (`wods`→`classes` en un solo sentido; `results`→`wods`/`members`/`classes`; `dashboard`→`wods`; `tv`→`wods`/`results`/`members`/`settings`), en `test_no_cross_models.py` y en el árbol de `CLAUDE.md`.
- Contrato: `docs/openapi.json` (20 184 líneas) y `web/src/core/api/types.ts` (13 401) se regeneran; el release sube a `0.5.0` en 5 archivos (`check-release-version.sh`).
- Front: `/tv` ya está en `routeTable.ts` (layout `tv`, pública) y `TvLayout.tsx`/`GymLayout.tsx` existen. Faltan features `movements`, `wods`, `results`, `tv`, la pestaña TV de Config y la pestaña Resultados de la ficha; referencia en `docs/design/screens/` (Movimientos, WOD_Lista, WOD_Form, WOD_Detalle, Resultados_Registro en `GymLayout` y TV). Una feature no importa de otra: lo común va en `shared/data/`.

## 2. Capa de datos

- Head actual `0031_refresh_kiosk_path` (cadena lineal). El plan nombra `0070`-`0075` y cita `0061_class_sessions`: no existen (la sesión es `0027`). Propuesta, a registrar en DECISIONES y en SPRINT-08.md antes de crear nada (ids ≤ 32 caracteres):
  - `0032_wods_movements` (`name_norm` único), `0033_wods_benchmarks` (N-46, `score_type`), `0034_wods_wods` (`score_type`, `benchmark_id`, `date`, unicidad del WOD principal por fecha, N-41), `0035_wods_wod_movements` (`is_primary`, único parcial por WOD), `0036_results_wod_results` (`is_current`, `supersedes_id`, `capped`; único parcial `(wod_id, member_id) WHERE is_current`; índice `(wod_id, status) WHERE is_current`), `0037_results_immutability` (trigger: solo columnas de validación e `is_current`; sin `DELETE`).
  - No crear FK `class_sessions.wod_id` → `wods.wods` (cruza esquemas; `0027` la dejó sin FK): validar en `service`.
- `class_sessions.wod_id` existe desde `0027` (nulo, sin FK). El grant por columna de `infra/db/grants.sql:126` NO incluye `wod_id`: añadirlo a `GRANT UPDATE (...) ON classes.class_sessions TO apex_api` o el `PATCH` falla en runtime con el rol real.
- Grants: 5 tablas nuevas (movements, benchmarks, wods, wod_movements, wod_results) en `grants.sql` (encabezado "clasificada:", matriz y concesiones) y en `tests/migrations/test_db_grants.py` (`PRIVILEGIOS`; `dbsetup` falla cerrado); `GRANT USAGE` de los esquemas `wods` y `results`; `wod_results` sin DELETE para ningún rol y UPDATE por columna; trigger de auditoría y su entrada en `tests/migrations/test_0014*`.
- Datos: tablas nuevas vacías, sin backfill; `members.sex` ya admite nulo. `cli seed-benchmarks` es migración de datos por CLI (regla de datos 8): idempotente por nombre normalizado, con `SYSTEM_USER_ID` por defecto.
- Sección `tv` en `settings_sections`: sin migración (el CHECK de `0005` ya la incluye); el hash vive en el JSONB.

## 3. Servicios Docker

- api y worker (misma imagen: `COPY src`, `alembic.ini`, `migrations`): reconstruir tras cada wave con migraciones o contrato; `migrate` corre `0032-0037` y `dbsetup` reaplica `grants.sql`.
- web: reconstruir (rutas, tipos, pantallas, TV).
- Nginx (`infra/nginx/default.conf:50-56`): `location /api/v1/tv/` con su `access_log` ya existe; falta `location = /tv` sin query en el log (Wave 0 del plan).
- CI: job nocturno aparte para la prueba de 12 h; sin infraestructura nueva.

## 4. Contratos API

- Nuevos: movements 3, benchmarks 3, wods 6 (`/wods/today` antes de `/{id}`), results 4 (`PUT /results`, `GET /wods/{id}/results|leaderboard`, `GET /members/{id}/results`), `PATCH /class-sessions/{id}`, `settings/tv` 3, `GET /tv/today` público por `X-Device-Token`. Admin/coach en todas salvo la TV (`test_every_route_has_role`). `GET /class-sessions/{id}/attendance` ya puede existir de S7: verificar.
- Cambian: `GET /dashboard` (`wod_today` de `null` a objeto: ruptura de `types.ts`, `FutureKpis`, `schemas.ts` y pruebas, en el mismo cambio); `GET /class-sessions` (filtro `wod_id`, aditivo); `settings` suma la sección `tv` (`SectionKey` en `types.ts`).
- TV: proyección con lista blanca (nombre e inicial del apellido, marca; sin documento ni contacto); 12/min; token por hash en tiempo constante, sin caché.

## 5. Línea base de pruebas

- Cierre del Sprint 7 (S7-D43, sobre `e38b65b`): api 10 375 pasan y 103 omitidas, cobertura 95,39 %; web 4 261 pasan, 98,19 % de líneas (2 hilos).
- Hoy, `tests/architecture` en `8b2db15`: 847 passed en 113,3 s (`db_test` en 5443). Suite completa, mypy y web no corridos (poca memoria); se toman del cierre de S7.

## 6. Riesgos por severidad

1. [ALTA] Numeración `0070-0075` del plan frente a la cadena en `0031`: sin decisión se rompen `alembic heads`, `migrations_status` y las guías.
2. [ALTA] Trigger de inmutabilidad de `wod_results` mal escrito bloquea correcciones o deja editar marcas; `is_current` e índice único parcial se prueban con dos sesiones (409).
3. [ALTA] Token de TV: falta la dependencia `__apex_device_token__` (la ruta ya está en las listas blancas). Sin comparación por hash, sin caché y con regeneración inmediata, el token viejo sigue valiendo; el token no va a logs ni a auditoría (Q12, N-44).
4. [MEDIA] `GRANT UPDATE (wod_id)` omitido: falla solo con `apex_api`; exigir prueba de grants y E2E con rol real.
5. [MEDIA] `wod_today` cambia el contrato del dashboard (api, web, `types.ts`): un solo cambio.
6. [MEDIA] Ciclos de imports `wods`/`classes`, `results`/`members`, `dashboard`/`wods`; sección `tv` sin habilitar en `ENABLED_SECTIONS`.
7. [MEDIA] Deuda con dueño Sprint 8 (S7-D43): token de dispositivo de la tablet (S7-D24; hoy el quiosco es una sesión coach), residual de `finish_rotation` (S7-D36) y sesiones canceladas del día en Inicio; SPRINT-08.md no las incluye: decidir por escrito.
8. [BAJA] Leaderboard <300 ms con 60 resultados (prueba `perf`), prueba de tablet con coach real (evidencia manual), memoria de vitest (2 hilos).

## Condiciones para VERDE

- C1: registrar la numeración `0032-0037` y corregir SPRINT-08.md, BREAKDOWN y guías antes de crear migraciones.
- C2: decidir sin FK en `class_sessions.wod_id` (validar en `service`) y añadir `wod_id` al `GRANT UPDATE` con prueba.
- C3: `grants.sql`, `test_db_grants.py` y triggers de auditoría de las 5 tablas en el mismo slice que cada migración.
- C4: grafo de imports de `wods`/`results`/`tv` y `MODULES` antes de US-168; dashboard (api, web, tipos) en un solo cambio.
- C5: dependencia `__apex_device_token__` y habilitación de la sección `tv` antes de US-176, con prueba de token viejo tras regenerar.
- C6: decidir el destino de las tres deudas de S7-D43; reconstruir api, worker y web tras cada wave; regenerar `openapi.json` y `types.ts`.
