# Sprint 8 · v0.5: movimientos, WODs, resultados y TV

- Versión: v0.5.
- Épicas: EP-22 (entrenamiento: movimientos, WODs y resultados) y EP-23 (pantalla de TV del box).
- Tamaño: 13 historias, 49 puntos y 213 h relativas (EP-22: 178 h; EP-23: 35 h).
- Nivel de detalle: bloques en orden de ejecución y slices S8-W0-1 a S8-V9 (`docs/ddd/blueprints/sprint-08-plan.md`; decisiones S8-D1 a S8-D43 en `DECISIONES.md`).
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
3. **Leaderboard.** En el panel filtra por F, M y Todos. Un socio con sexo nulo solo aparece en Todos (Q22). La TV muestra un solo ranking «Todos» (S8-D19).
4. **Ficha e Inicio.** La pestaña Resultados de la ficha muestra los resultados del socio, e Inicio muestra la tarjeta "WOD de hoy".
5. **TV.**
   - Abrir `/tv#token=…` (el token va en el fragmento, que nunca sale en una petición; `?token=` solo por compatibilidad, S8-D32): el front guarda el token, limpia la URL con `history.replaceState` y desde ahí lo envía en `X-Device-Token` (N-44).
   - Se muestra el WOD y un ranking único con nombre e inicial del apellido, sin bajas ni socios sin autorización de datos vigente (S8-D34).
   - Al regenerar o revocar el token desde Configuración (`POST /settings/tv/regenerate-token` o `/revoke-token`), la TV muestra "Token inválido".

## Dependencias de sprints anteriores

- **Sprint 7:**
  - US-156 (`class_sessions`, con la columna `wod_id`, creada por `0027_class_sessions`; sin FK, S8-D3);
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
     - Solo cabecera `X-Device-Token`. Dos cubetas, token primero: `tv` por token (30/min, `TV_TOKEN_LIMIT`) y `tv-fail` por IP solo para intentos con token inválido (12/min, `TV_IP_LIMIT`; S8-D33).
     - Excluye bajas y socios sin autorización de datos vigente (S8-D34).
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
Cabeza actual: `0031_refresh_kiosk_path`. Este sprint suma siete migraciones, de 32 caracteres o menos (S8-D2); los números `0070` a `0075` y la cita `0061_class_sessions` del plan original quedan sin usar.
- `0032_wods_movements` (US-165): crea el esquema `wods`.
- `0033_wods_benchmarks` (US-166, N-46).
- `0034_wods_wods` (US-166): cargas en gramos enteros (S8-D41).
- `0035_wods_wod_movements` (US-166): `is_primary`, con índice único parcial.
- `0036_results_wod_results` (US-169): crea el esquema `results`; `is_current`, `supersedes_id`, `capped`, `source` y los CHECK de S8-D35, con índice único parcial sobre (`wod_id`, `member_id`) `WHERE is_current`.
- `0037_results_immutability` (US-169): triggers que solo dejan `UPDATE` sobre las columnas de validación y sobre `is_current` (S8-D35).
- `0038_kiosk_results_path` (US-169, S8-D15): la ruta de resultados entra en la lista del quiosco de `auth.refresh_tokens`.
- La columna `class_sessions.wod_id` ya existe desde `0027_class_sessions` (US-156, Sprint 7). Este sprint solo la usa.
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
  - `GET /api/v1/settings/tv` y `PATCH /api/v1/settings/tv` (solo `refresh_seconds` de 15 a 300 y `show_leaderboard`; S8-D30);
  - `POST /api/v1/settings/tv/regenerate-token` (devuelve `url` con `/tv#token=`, S8-D32);
  - `POST /api/v1/settings/tv/revoke-token` (S8-D37);
  - `GET /api/v1/tv/today`: público, autenticado por token de dispositivo.
- **Cambio en un endpoint existente:** `GET /api/v1/dashboard` llena `wod_today` (cambio de tipo, api y web juntos, S8-D16).
- **Quiosco:** las rutas de resultados entran en la lista del quiosco (S8-D15); la corrección en quiosco solo sobre resultados de la misma sesión y origen `kiosk` (S8-D31).
- **CLI:** `seed-benchmarks` (idempotente, `ON CONFLICT (name_norm) DO NOTHING`).

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
   - Mitigación (S8-D40, sin paso humano): el E2E de F4 registra 15 resultados en quiosco con pausas de tecleo y mide el tiempo (menos de 5 minutos), y en V8 una clase completa por la interfaz real; ambas son la evidencia de US-169.
4. [MEDIUM] Un token de TV filtrado muestra nombres con inicial y marcas. Es un riesgo aceptado por la arquitectura.
   - Mitigación: rotación o revocación inmediata, token solo en cabecera, enlace con el token en el fragmento y sin registro en logs (S8-D32).
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
  - `/tv/today` con las dos cubetas de S8-D33, sin datos cifrados y con proyección de lista blanca;
  - el token se guarda como hash y nunca aparece en la auditoría ni en los logs;
  - Nginx no registra la consulta (el formato `apex` usa `$uri`) y `x-device-token` se redacta en `core/logging.py`.
- `verify-delivery`, con una clase real: asistencia, resultados y leaderboard en la TV.

## Deuda del Sprint 7 resuelta (S7-D43(5))

- Token de dispositivo de la tablet: se cierra sin hacerlo (S8-D24); el quiosco con cuenta coach ya da lo que buscaba.
- Sesiones canceladas en Inicio: al final y plegadas (S8-D25, slice B5).
- Residual de `finish_rotation`: aceptado sin código (S8-D26).

## Slices

Orden: S8-W0-1, W0-2, W0-3 · A1, A2, A3, A4 · B1, B2, B3, B4, B5, C1, C2 · F1, F2, F3 · F4, F5, F6 · V1 a V9. Detalle, archivos, pruebas y gates en `docs/ddd/blueprints/sprint-08-plan.md` §3.
