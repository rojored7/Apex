# Sprint 8 · v0.5: movimientos, WODs, resultados y TV

- Versión: v0.5.
- Épicas: EP-22 (entrenamiento: movimientos, WODs y resultados) y EP-23 (pantalla de TV del box).
- Tamaño: 13 historias, 49 puntos y 213 h relativas (EP-22: 178 h; EP-23: 35 h).
- Nivel de detalle: bloques en orden de ejecución, sin slices. Se refina al llegar.
- Historias del sprint: US-165, US-166, US-167, US-168, US-169, US-170, US-171, US-172, US-173, US-174, US-175, US-176, US-177.

## Objetivo

Que el coach programe el WOD del día sobre un catálogo de movimientos y de benchmarks, lo asigne a las sesiones y registre los resultados de la clase en la tablet. El leaderboard del día ordena según el tipo de puntaje, y la TV del box lo muestra en vivo con un token de dispositivo de solo lectura, sin datos personales.

## Demo al final del sprint

1. **Catálogo y WOD.**
   - Crear movimientos.
   - `cli seed-benchmarks` carga los benchmarks clásicos.
   - Crear el WOD "Fran" con `benchmark_id`, movimiento principal (Q19) y `score_type = time`.
   - Asignarlo a las sesiones de hoy con `PATCH /class-sessions/{id}`.
2. **Resultados en la tablet.**
   - Registrar los resultados de 15 asistentes. Al venir del coach, nacen `validated` (N-42).
   - Un resultado con time cap queda `capped` y aparece después de los que terminaron (N-43).
   - Corregir un resultado crea uno nuevo con `supersedes_id`, y el anterior pasa a `is_current = false` (Q18).
3. **Leaderboard.** Filtra por F, M y Todos. Un socio con sexo nulo solo aparece en Todos (Q22).
4. **Ficha e Inicio.** La pestaña Resultados de la ficha muestra los resultados del socio, e Inicio muestra la tarjeta "WOD de hoy".
5. **TV.**
   - Abrir `/tv?token=…`: el front guarda el token, limpia la query y desde ahí lo envía en `X-Device-Token` (N-44).
   - Se muestra el WOD y el leaderboard con nombre e inicial del apellido.
   - Al regenerar el token desde Configuración, la TV muestra "Token inválido".

## Dependencias de sprints anteriores

- **Sprint 7:**
  - US-156 (`class_sessions`, con la columna `wod_id`);
  - US-157 (lista de sesiones con el filtro `wod_id`);
  - US-159 y US-161 (asistencia con `removed_at`, `classes.service.attendees`).
- **Sprint 4A:** US-108 (contrato del tablero con `wod_today` en `null`).
- **Sprint 3:** US-073 (ficha y sus pestañas).
- **Sprint 2:**
  - US-069 y US-070 (`members.service.names_for` con sexo; no se crea `public_names`);
  - US-054 (secciones validadas, para la sección `tv`);
  - US-062 (`GymLayout` y `TvLayout`).
- **Sprint 1:**
  - US-035 (lista blanca de rutas);
  - US-036 (`core/ratelimit.py`);
  - US-041 (hash de tokens en `core/security`).

## Historias en orden de ejecución (por bloques)

1. **Bloque A · Catálogo y WOD (EP-22).**
   - US-165 · Movimientos: nombre normalizado y único.
   - US-166 · WOD con benchmarks: refinamiento aceptado.
     - CRUD mínimo de `/benchmarks` para admin y coach.
     - `cli seed-benchmarks`.
     - El `score_type` del WOD es igual al de su benchmark.
     - Un solo movimiento principal por WOD.
   - US-167 · Calendario de WODs.
   - US-168 · WOD del día y asignación a sesiones: `PATCH /class-sessions/{id}` en el router de `classes` (N-41).
2. **Bloque B · Resultados (EP-22).**
   - US-169 · Registrar resultados en tablet: trigger, índice parcial y E2E.
   - US-170 · Corregir resultado: `SELECT … FOR UPDATE` sobre el resultado anterior.
   - US-171 · Leaderboard: `leaderboard_order` con N-43 y Q22.
   - US-172 · Detalle de WOD.
   - US-173 · Pestaña Resultados de la ficha.
   - US-174 · Tarjeta WOD de hoy en Inicio.
3. **Bloque C · TV (EP-23).**
   - US-175 · Token de dispositivo: sección `tv` con el hash del token; regeneración auditada.
   - US-176 · Endpoint público de TV.
     - Módulo `tv`, sin models.
     - Token por `X-Device-Token`.
     - Límite de 12 peticiones por minuto.
     - La proyección solo devuelve campos de una lista blanca.
   - US-177 · Pantalla de TV, con refresco y prueba de 12 h con reloj acelerado.

Waves:
- **Wave 0:**
  - Nginx sin registrar las query strings de `/api/v1/tv/` ni de `location = /tv`;
  - job nocturno separado para la prueba de 12 h de la TV.
- **Waves 3a y 3b:** los bloques A, B y C, en ese orden.
- **Waves 5a y 5b:**
  - las pantallas Movimientos, WOD_Lista, WOD_Form, WOD_Detalle y Resultados_Registro (esta en `GymLayout`);
  - la pestaña Resultados de la ficha;
  - la tarjeta de Inicio;
  - la pestaña TV de Configuración;
  - la pantalla TV (en `TvLayout`).

## Migraciones que aplica

En orden ascendente:
- `0070_wods_schema_movements` (US-165).
- `0071_wods_benchmarks` (US-166, N-46).
- `0072_wods_wods` (US-166).
- `0073_wods_wod_movements` (US-166): `is_primary`, con índice único parcial.
- `0074_results_schema_wod_results` (US-169): `is_current`, `supersedes_id` y `capped`, con índice único parcial sobre (`wod_id`, `member_id`) `WHERE is_current`.
- `0075_results_immutability` (US-169): trigger que solo deja hacer `UPDATE` sobre las columnas de validación y sobre `is_current`.
- La columna `class_sessions.wod_id` ya existe desde `0061_class_sessions` (US-156, Sprint 7). Este sprint solo la usa.
- EP-23 no tiene migración propia: la sección `tv` vive en `settings_sections` (`0005`).

## Endpoints que expone

- **Movimientos:** `GET` y `POST /api/v1/movements`; `PATCH /api/v1/movements/{id}`.
- **Benchmarks:** `GET` y `POST /api/v1/benchmarks`; `PATCH /api/v1/benchmarks/{id}`.
- **WODs:**
  - `GET` y `POST /api/v1/wods`;
  - `GET /api/v1/wods/today`, registrado antes de `/wods/{id}`;
  - `GET` y `PATCH /api/v1/wods/{id}`.
- **Resultados:**
  - `GET /api/v1/wods/{id}/results`, con `include_superseded`;
  - `GET /api/v1/wods/{id}/leaderboard`;
  - `PUT /api/v1/results`;
  - `GET /api/v1/members/{id}/results`.
- **Class sessions:**
  - `PATCH /api/v1/class-sessions/{id}`;
  - `GET /api/v1/class-sessions/{id}/attendance`;
  - filtro `wod_id` en `GET /api/v1/class-sessions`.
- **TV:**
  - `GET /api/v1/settings/tv` y `PATCH /api/v1/settings/tv`;
  - `POST /api/v1/settings/tv/regenerate-token`;
  - `GET /api/v1/tv/today`: público, autenticado por token de dispositivo.
- **Cambio en un endpoint existente:** `GET /api/v1/dashboard` llena `wod_today`.

## Tests de arquitectura que deben pasar

- Toda la suite anterior.
- `test_every_route_has_role.py`, que reconoce `__apex_device_token__` para `/tv/today` (US-035 y US-175).
- `test_service_import_graph.py`, con el sentido único entre `wods` y `classes`, sin ciclo nuevo.
- `test_no_cross_models.py` sobre `wods`, `results` y `tv`.

## Riesgos y mitigación

1. [HIGH] Un trigger de `wod_results` mal escrito bloquea correcciones y validaciones legítimas, o deja editar marcas.
   - Mitigación: una prueba por cada columna permitida y por cada columna prohibida, más la prueba de `DELETE`.
2. [MEDIUM] Dos coaches corrigen el mismo resultado al mismo tiempo.
   - Mitigación: `FOR UPDATE`, índice parcial y prueba con dos sesiones (una gana, la otra recibe 409).
3. [MEDIUM] La prueba de uso de la tablet (15 socios en menos de 5 minutos) depende de un coach real.
   - Mitigación: sesión de prueba registrada como evidencia antes de cerrar US-169.
4. [MEDIUM] Un token de TV filtrado muestra nombres con inicial y marcas. Es un riesgo aceptado por la arquitectura.
   - Mitigación: rotación inmediata y token solo en cabecera.
5. [LOW] Rendimiento del leaderboard: 300 ms con 60 resultados.
   - Mitigación: índice parcial `(wod_id, status) WHERE is_current` y una prueba de tiempo.

## Definición de hecho del sprint

- Definición de hecho común del README.
- E2E:
  - resultados en la tablet;
  - corrección;
  - leaderboard;
  - TV con token y rotación.
- Prueba de 12 h de la TV en el job nocturno, con reloj acelerado.
- Seguridad, revisada por `security-reviewer`:
  - `/tv/today` limitado a 12 por minuto, sin datos cifrados y con proyección de lista blanca;
  - el token se guarda como hash y nunca aparece en la auditoría ni en los logs;
  - Nginx no registra la query `token`.
- `verify-delivery`, con una clase real: asistencia, resultados y leaderboard en la TV.
