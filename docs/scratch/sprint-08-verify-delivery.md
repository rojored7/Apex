# Sprint 8 · verify-delivery (V8) · 2026-11-15

HEAD `2f597c2` (rama `feat/sprint-08-wods-resultados-tv`). Imágenes `apex-api:local` y `apex-web:local` reconstruidas desde la carpeta principal con `GIT_SHA=2f597c259755` y api, worker y web recreados (health `ok`, `migrations ok`).

## Resultado

- Pilar 1: **51 entregados, 2 parciales, 0 no, de 53 puntos** (US-172 y M-2; ver matriz).
- Pilar 2: la clase completa corrió por la interfaz real, sin pasos humanos. 1 defecto de producto nuevo (D-V8-1, abajo).

## Pilar 1 · matriz (E = entregado, P = parcial)

| Punto | Est. | Evidencia |
|---|---|---|
| US-165 Movimientos | E | A1 `22a0aac`, A1b `90b3f5f`; `movements.spec.ts` (V5 stack); demo 1 en V4 |
| US-166 WOD con benchmarks | E | A2 `31850e9`, A3 `5305a6d`; `seed-benchmarks` dos veces = 0 nuevos y 12 (V4) |
| US-167 Calendario de WODs | E | A3, F2 `c96f937`; `wods.spec.ts` verde tras V5b (contraste) |
| US-168 WOD del día y asignación | E | A4 `c575077`; V8: `PATCH /class-sessions/{id}` con `wod_id` 200 y la sesión de hoy lo hereda |
| US-169 Resultados en tablet | E | B1 `0447dbc`, B3 `7788dd6`, F4 `7b08832`; V8: 15 resultados en quiosco, 9 s (E2E de F4: 10 s; tope 300 s) |
| US-170 Corregir resultado | E | B2 `f0cfea2`; V8: corrección 5:55 con `supersedes_id`, anterior `is_current = false` |
| US-171 Leaderboard | E | B4 `cd9e756`; V4: F 9, M 7, Todos 17, sexo nulo solo en Todos; V8: captura con filtros Mujeres/Hombres |
| US-172 Detalle de WOD | P | B4, F3 `0290dcf`; leaderboard e historial bien. Defecto D-V8-1: el panel «Sesiones con este WOD» muestra solo las 50 primeras (orden ascendente) sin aviso |
| US-173 Pestaña Resultados de la ficha | E | B4, F5 `308397b`; `member-results.spec.ts`; captura `ficha-resultados.png` |
| US-174 Tarjeta WOD de hoy | E | B5 `bb6e4da`, F5; V8: tarjeta con «Ver» y «Registrar resultados»; `inicio-wod-de-hoy.png` |
| US-175 Token de dispositivo | E | C1 `1c4d107`, C1b `2e967ee`; V8: regenerar y revocar 200 |
| US-176 `/tv/today` | E | C2 `5960e8f`, C2b `307752b`; V8: 200 con token, 401 sin token y tras revocar |
| US-177 Pantalla de TV | E | F6 `ff2b06a`, F6b `4e4dff4`; `tv.spec.ts`; soak de 12 h con reloj falso en V5 (heap +3,4 %, tope 20 %); no se corrieron 12 h reales |
| Demo 1 catálogo y WOD | E | V4 (por curl) y V5 (`movements`, `wods` por la interfaz). Desviación: V4 no fue por la interfaz |
| Demo 2 resultados en tablet | E | V4 (curl) y V8 (interfaz): `capped` tras los que terminan, corrección con `supersedes_id` |
| Demo 3 leaderboard F/M/Todos | E | V4 (curl) y captura de V8 con los filtros |
| Demo 4 ficha e Inicio | E | V4 y capturas de V8 |
| Demo 5 TV | E | V4 (rotar: viejo 401, nuevo 200) y V8 (TV abierta con `#token=`, URL limpia, ranking en vivo) |
| C1 numeración | E | S8-D2, W0-1 `52ffdce` (cabeza real `0041_results_session_index`; no `0038`) |
| C2 sin FK en `wod_id` y GRANT | E | A4 `c575077` (`test_apex_api_escribe_wod_id`); `dbsetup` V2 exit 0 |
| C3 grants y triggers por tabla | E | A1, A2, A3, B1; V2: 30 tablas clasificadas, 19 guardas con `tgenabled = A` |
| C4 grafo y `MODULES` | E | A1, A4, B1, B5, C2; pruebas de arquitectura en los gates |
| C5 token viejo inválido | E | C1; V4 y V8: tras rotar el viejo da 401 |
| C6 deudas de S7 y reconstruir | E | W0-1, B5; V8: imágenes con SHA actual |
| H-1 sección `tv` solo por rutas propias | E | C1 (S8-D30), C1b |
| M-1 origen `kiosk` | E | B3 (S8-D31); V8: `source = kiosk` x16 y `after.source = kiosk` en 16 auditorías |
| M-2 token en el fragmento | P | C1, F5, F6, F6b; V8: ruta `/tv`, hash vacío, cabecera con token, sin `authorization`, token ausente de logs. Falta V3 (prod-smoke), que no tiene bloque en el cuaderno |
| M-3 dos cubetas | E | W0-3, C2; V4: 260 con token 200 x29 y 429 x231; 300 falsos 401 x12 y 429 x288 |
| M-4 TV sin bajas ni sin autorización | E | C2 (S8-D34); V4: 16 a 15 tras la baja |
| M-5 forma protegida en la base | E | B1 (S8-D35), B1d, B3b; V2: guardas activas |
| M-6 orden de candados | E | B1, A4 (S8-D36) |
| L-1 `verify_tv_token` sin 500 | E | C1 / C1b |
| L-2 `scaled_movement_ids` | E | B1 |
| L-3 orden en `PUT /results` | E | B1 (S8-D36) |
| L-4 `gcTime: 0` y `logout` en TV | E | F5, F6, F6b |
| L-5 `downgrade` de `0038` | E | B3 |
| L-6 benchmarks paginados y siembra idempotente | E | A2, A2b, B4 |
| L-7 revocar token | E | C1; V8 revoke 200 y luego 401 |
| P1 ranking único en la TV | E | S8-D19, F6; V8: ranking «Todos» único |
| P2 sin `validate` ni `pending` | E | S8-D29 (EP-25); resultados del coach nacen `validated` |
| P3 exclusión de bajas y sin consentimiento | E | S8-D34, C2; V4 |
| S8-D24 token de la tablet | E | cerrado sin código; V8: quiosco con cuenta coach |
| S8-D25 canceladas al final en Inicio | E | B5 |
| S8-D26 residual de `finish_rotation` | E | aceptado sin código; v0.5 no suma escritores cifrados |
| S8-D41 gramos enteros | E | A3, B1, C2; TV muestra «43 / 30 kg» desde gramos |
| S8-D42 banderas de exclusión | E | W0-1; V8 creó y borró `apex-migracion.flag` |
| S8-D43 proceso | E | plan, dos críticas y revisiones; V9 registra las evidencias (pendiente) |
| S8-D44 detalles de B1 | E | B1, `ck_wod_results_capped_shape`; V8: un `capped` en la base (V4) |
| S8-D45 correcciones de A4 | E | A4b `50beea7` |
| S8-D46 bloqueo por resultados y anulación | E | B1d, B3b (`0039`, `0040`) |
| S8-D47 correcciones de B4 y B3b | E | B4b `a5128e5` |
| S8-D48 correcciones de C1 | E | C1b `2e967ee` |
| S8-D49 revisión final | E | V7b `3599d2e` (`0041`) |

## Desviaciones honestas

- TDD sin rojo medido en B1 y en F3 (según el encargo; el cuaderno de cada slice tiene su detalle).
- `0040` se editó en su sitio (B4b y C1b) bajo S8-D47: ninguna base persistente la tenía. Se aplicó en V2 ya final; el cambio posterior (V7b) fue una migración nueva, `0041`.
- Incidente del stack roto: de B1 a C2 el api de desarrollo estuvo caído; los E2E de F1 a F6 se escribieron sin correr y se corrieron en V5 (2 fallos reales, corregidos en V5b).
- V4 se hizo por curl y no por la interfaz; lo cubren los E2E de V5 y esta clase por la interfaz.
- Contraseña del coach de desarrollo (`desarrollo-coach-v8.txt`) que un agente dejó ver en V4: esa cuenta está dada de baja (`deleted_at`) y el archivo sigue en `apex-claves`. Esta corrida usó otro coach ficticio y también lo dio de baja.
- V3 (prod-smoke) no tiene bloque en el cuaderno y V1 (gates) corre en paralelo: no se cuentan aquí.
- Hoy ya existía el WOD de V4 y la fecha está bloqueada por sus resultados (`locked_by_results`, correcto); la clase de V8 reutilizó ese WOD de hoy, por lo que el conteo por WOD incluye los resultados de V4.

## Pilar 2 · clase completa en vivo

Datos ficticios «Prueba S8 V8 …». Guion temporal en el scratchpad (fuera de `web/tests`); contraseñas leídas de archivo, nunca impresas.

- Preparación (api con el admin): sesión de hoy con WOD asignado, 15 socios con plan, pago y check-in por `POST /attendance`. El check-in fue por api, no por la pantalla.
- TV abierta en otra pestaña (contexto limpio) con `/tv#token=`: ruta `/tv`, hash limpio, petición con `X-Device-Token`, sin `authorization`, sin token en la URL.
- Tablet (coach, quiosco, 1024x768, oscuro): 15 resultados con pausas de tecleo (14 tiempos y 1 «No terminó» con 135 reps), **9 s en total** (tope 300 s), una corrección del primero a 5:55. Sin llamadas a `/reveal` ni a `/members/{id}`.
- La TV mostró 5:55 en el siguiente refresco (15 s); ranking solo con nombre e inicial, `/tv/today` sin `member_id`, documento, teléfono, correo ni sexo.
- Base (solo SELECT), sesión de la clase: 16 filas, **15 vigentes**, 1 corrección, 1 `capped`, `source = kiosk` x16, todos `validated`, 15 asistencias vivas. Anterior `is_current = f` y sucesor `t` con `supersedes_id` correcto. Ningún socio con dos vigentes. WOD completo: 37 filas, 33 vigentes; `desk` 18 y `kiosk` 19 (incluye V4 y 1 resultado de un intento abortado de esta corrida).
- Auditoría de esas filas: `insert` 16 (todas con `after.source = kiosk`) y `update` 1.
- Token de TV en logs: `grep -cF` en api, web y worker = 0 (544, 618 y 30 líneas). Las URIs de Nginx no llevan query.
- Revocar: `regenerate`, `/tv/today` 200, `revoke-token` 200, después 401; sin cabecera 401. TV restaurada a refresco 30 s y sin token vivo.
- Artefactos: `apex-api:local` y `apex-web:local` con `org.opencontainers.image.revision = 2f597c259755`, igual que `git rev-parse --short=12 HEAD`; los contenedores usan esos ids.
- Capturas en `docs/scratch/evidencia-s8/`: `tablet-inicio-oscuro`, `tablet-registrando-oscuro`, `tablet-completa-oscuro`, `wod-detalle-ranking`, `ficha-resultados`, `inicio-wod-de-hoy`, `tv-ranking-1920`.

## Defectos de producto (no corregidos)

- **D-V8-1 (baja o media): «Sesiones con este WOD» corta en 50 sin aviso.** `web/src/shared/data/results.ts:120` pide `limit: 50, offset: 0` a `GET /class-sessions?wod_id`, orden ascendente. Con 51 sesiones del WOD (la de esta clase, la más nueva, a las 21:53) quedó fuera y no hay «ver más». Esperado: ver al menos las sesiones vigentes o pendientes, o un aviso de que hay más. El acumulado viene de las sesiones de los E2E; en un box real es raro.
- Observación: en la TV los socios de esta clase salen como «Prueba A.» porque el nombre «Prueba S8 V8» se muestra como «Prueba»; es del nombre ficticio, no un defecto.

## Residuos de datos ficticios

3 sesiones programadas «Prueba S8 V8 Clase» (una vacía de un intento abortado; las otras dos con resultados), 30 socios de esta corrida (15 de un intento abortado y 15 de la clase) y 2 planes «Prueba S8 V8 Plan». Los coaches de esta corrida están dados de baja.
