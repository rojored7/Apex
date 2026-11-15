# Sprint 7 · verify-delivery (V8), 2026-11-15

HEAD verificado: `a80ac57` (sobre `b4a93e5`; el único cambio posterior es la prueba `perf` de V6). Stack de desarrollo `apex`: web 8180 y api 8181.

## Resultado: 57 de 58 entregados, 1 parcial, 0 no

Convención: E = entregado, P = parcial, N = no. Punteros: commit, prueba o bloque de `docs/scratch/sprint-07.md` (cuaderno).

### Pilar 1 · matriz

**Historias (11 de 11 E)**

| Historia | Estado | Evidencia |
|---|---|---|
| US-154 Horas y clases | E | A1 `bc9e709`, F1 `d626c04`; demo 1 en V4; `settings-config.spec.ts` |
| US-155 Franjas | E | A2 `0769790`, A2b `2bea58e`, F2 `6bdedf9`; V4 (franja «Lunes 6:00 CrossFit») |
| US-156 Generar sesiones | E | B1 `5753e0b`; V4: `--run-once generate_sessions` dos veces, 14 → 14 → 14, `creadas 0` |
| US-157 Sesiones de la semana | E | B2 `f71e658`, F3 `6a82ce9`; V4 `GET /class-sessions?week=`; captura `21-sesiones-oscuro.png` |
| US-158 Cancelar futuras | E | B3 `96f763c`; V4 `cancelled_count = 2` |
| US-159 Check-in | E | C1 `0ac0b2f`, F4 `ed1de65`, C4 `73134a7`; V5 `checkin.spec.ts` 2 corridas verdes; V8 en vivo (abajo) |
| US-160 Descontar y devolver | E | C2 `c76de5c`, C2b `cf18704`; V8 en vivo: 10 → 9 → 10 y tiquetera de 1 agotada |
| US-161 Quitar asistencia | E | C3 `840a7e1`; V8: borrado lógico con motivo y devolución de la clase |
| US-162 Reportes | E | R1 `1ef992a`, F5 `bf1117f`; V8: `GET /attendance/summary` y captura `22-asistencia-oscuro.png` |
| US-163 Última asistencia | E | R2 `5d8eb8f`; V8: `GET /members?last_attendance=7d` y `=never` responden 200; perf 19 ms con 1.000 socios |
| US-164 KPI en Inicio | E | R3 `51ce41e`, F6 `77a821c`; V8: `GET /dashboard` y captura `23-inicio-oscuro.png` |

**Demos (5 de 5 E)**

1. Horario: V4 (horas de lunes a viernes, `default_capacity = 15`, franja con coach).
2. Sesiones: V4 (job idempotente, cancelar una y las futuras de una franja).
3. Check-in en tablet: V8 en vivo y V5. Al día: 201 sin banderas. Vencido: `flags = {expired}` sin 409. Asistente 16: `{no_membership,over_capacity}`. `other_day` y `out_of_window` solo los cubre el E2E de V5 (`checkin.spec.ts`), no se repitieron en V8.
4. Tiqueteras: V8 en vivo (10 → 9, quitar → 10, agotar una de 1 recorta `end_date` y guarda `original_end_date`).
5. Reportes y filtros: V8 (resumen, asistencia del socio, filtro, `attendance_week`). La pestaña Asistencia de la ficha se verificó por la API y por E2E/vitest de F5, no con captura.

**Condiciones C1 a C6 (5 E, 1 P)**

- C1 numeración: E (W0-1 `5e4595c`; ids de 32 caracteres o menos, `test_todos_los_ids_de_revision_caben_en_varchar_32`).
- C2 `0025` con consultas previas: E (W0-2 `6481d43`; V2: las tres consultas dan 0).
- C3 sin migración de CHECK: E (C2, `test_0029::test_checks_de_0008_siguen`).
- C4 grants y triggers: E (V2: `dbsetup` «25 tablas clasificadas»; 13 guardas con `tgenabled = A`; V3 prod-smoke 233 y 252 ok).
- C5 lista blanca G-03 antes de US-163 y tablero api y web juntos: E (R2 `5d8eb8f`, R3 `51ce41e`).
- C6 reconstruir y regenerar: **P**. `openapi.json`, `types.ts` y la imagen `apex-web:local` (revisión `d1fa18b9e36c`, web sin cambios posteriores) están al día. La etiqueta `apex-api:local` apunta a una imagen creada a las 08:02 UTC con `org.opencontainers.image.revision = v99.0.0` y del proyecto `apex-smoke` (rastro de V3/prod-smoke), no al SHA del árbol; el worker usa otro id de imagen. En desarrollo el api y el worker ejecutan el código por el montaje de `api/src` (último cambio en `a157e9e`, anterior al arranque del worker a las 07:59 UTC), así que el comportamiento verificado es el del árbol, pero el artefacto-imagen del api no está reconstruido con el SHA.

**Hallazgos de la revisión de seguridad (16 de 16 E)**

- H-1 llave de firma fuera del api: E (S7-D23, W0-3 `0d65e8b` y `4297a26`; V3 prod-smoke «el api no ve `sign/`»).
- H-2 modo tablet: E (S7-D24, F4 `ed1de65`, F4b `0d48047`, C4 `73134a7`; V8: 0 enlaces en la pantalla y 0 llamadas a `/reveal`).
- H-3 membresía futura no descuenta: E (S7-D25, C2; `test_class_consumption.py`; V8 con tiquetera que empezó ayer).
- M-1 interbloqueo al cancelar futuras: E (B3 `96f763c`, `test_checkin_concurrency.py`).
- M-2 límites de día: E (C1, C3; V5).
- M-3 guardas de sesiones y franjas: E (A2, B1; V2 `tgenabled`).
- M-4 `with_signing` en falso por omisión: E (W0-3; prueba AST).
- M-5 resumen agregado en SQL: E (R1 `1ef992a`, R1b `1057451`, perf de 26 semanas verde).
- M-6 `0025` y `FOR NO KEY UPDATE`: E (W0-2 `6481d43`; residual S7-D36).
- L-1 a L-7: E (S7-D32; destinos en B2, C1, C2, W0-2 y F4).

**Decisiones S7-D23 a S7-D42 (20 de 20 E)**

D23 W0-3; D24 F4 (la inactividad de 10 min solo tiene prueba unitaria de `GymShell`; el token de dispositivo queda para v0.5 por la propia decisión); D25 C2 y V8; D26 B3; D27 C1 y C3 (V5); D28 ADR-006 en `4297a26`; D29 C2 y V8; D30 V2 (conteo 0); D31 V2 y V3; D32 LOW; D33 `5d62ece`; D34 W0-3; D35 proceso; D36 `d6e84bc`; D37 B1b `05f8602`; D38 B2b `0578e5a`; D39 C1; D40 C2, C2b y C3b; D41 C4, C4b y C4d; D42 C4b `e5716da`.

### Desviaciones honestas

- Las migraciones llegaron a `0031_refresh_kiosk_path` (el plan decía `0029`); el modo quiosco del servidor (S7-D41, S7-D42) no estaba en el plan inicial y lo exigió la revisión de F4.
- El plan de V8 dice `end_date = max(start_date, hoy)`; la regla vigente es S7-D29, `min(end_date, max(start_date, hoy))`. Es la que se verificó.
- `apex-api:local` no lleva el SHA del árbol (C6, parcial).
- Una tiquetera agotada queda `expired` el mismo día (fin = hoy, 0 clases) y la renovación empieza al día siguiente: es la regla de S7-D40 (12), no un defecto.
- `attendance_week` del tablero cuenta todas las asistencias vivas de la semana (30 en desarrollo, con residuo de E2E y de esta corrida); `GET /attendance/summary` solo cuenta sesiones programadas que ya empezaron. Cada una es consistente con su diseño; no se contrastan entre sí.
- Residuo en la base de desarrollo: decenas de sesiones `E2E …` canceladas hoy y los datos «Prueba S7 V8 …» de abajo.

### Pilar 2 · en vivo (desarrollo, interfaz real en 8180, coach de prueba, tema oscuro)

Datos ficticios «Prueba S7 V8 …»: coach `prueba-s7-v8-coach@ejemplo.local` (contraseña en `C:\Users\PC\Desktop\apex-claves\desarrollo-coach-v8.txt`), tres planes, 3 socios con membresía y 16 socios «Cupo NN», dos sesiones extra de hoy (04:26 y 04:29 de Bogotá). Todo se manejó con un script de Playwright temporal fuera de `web/tests` (no se versiona).

1. **Check-in en modo tablet de un socio con tiquetera de 10 (9).** Antes: `classes_remaining 10, end 2026-12-14, original_end NULL, active`. Tras tocar «Llegó» en la pantalla: `9, 2026-12-14, NULL, active`; fila de `classes.attendance` con `flags {}`, `membership_status_at_checkin active`, `removed_at NULL`, `membership_id` de la tiquetera. La pantalla mostró 0 enlaces y no hubo llamadas a `/reveal`.
2. **Quitarla (10).** Diálogo «¿Quitar a … de esta clase?» con motivo: `classes_remaining 10, active`; la fila queda con `removed_at` y `removed_reason = «Prueba S7 V8 quitar para devolver la clase»`.
3. **Agotar una tiquetera de 1.** Inicio el 2026-11-12. Antes: `1, 2026-12-12`. Después del check-in: `0, end_date 2026-11-15 (= min(2026-12-12, max(2026-11-12, hoy))), original_end_date 2026-12-12, expired`.
4. **Renovar sin `MembershipOverlap`.** `POST /members/{id}/memberships` con `renew: true`: 201, `pending_payment`, 2026-11-16 a 2026-12-16, 1 clase.
5. **Socio vencido.** Plan de 3 días iniciado hace 7: check-in 201 con `flags {expired}`, `membership_status_at_checkin expired`, chip rojo «Vencido» (captura 11).
6. **Asistente 16.** Sesión de cupo 15 con 15 asistentes sembrados por API; el 16 por la tablet queda con `{no_membership,over_capacity}` y 16 asistentes vivos (captura 14).
7. **Auditoría.** `audit.audit_log`: `insert` y `update` de `classes.attendance` por el coach (el `update` del quitar trae `removed_at` y el motivo); `update` de `memberships.memberships` con `classes_remaining 9`, luego `0` con `end_date 2026-11-15` y `original_end_date 2026-12-12`, luego `10` al devolver.
8. **Tablero.** `GET /dashboard`: `attendance_week {count 30, flagged_count 29}` y `sessions_today` con las dos sesiones (2/15 y 16/15) y `duration_min`.
9. **Artefactos.** `git rev-parse --short HEAD` = `a80ac57`; `apex-web:local` con revisión `d1fa18b9e36c` (src de web sin cambios desde entonces); `apex-api:local`, ver C6.
10. **Rendimiento (V6).** `-m perf` de las cuatro pruebas: 5 passed en 64 s. Check-in con 1.000 socios y 15 asistentes: 121, 16, 15, 15, 15 y 40 ms (< 2 s); `last_attendance=30d`: 19 ms; tablero con 20.000 asistencias: 18 ms; resumen de 26 semanas < 500 ms.

Capturas (PNG, 1,5 MB) en `docs/scratch/evidencia-s7/`: `10`, `11`, `12`, `13`, `14` (check-in en modo tablet, oscuro), `20-horario`, `21-sesiones`, `22-asistencia`, `23-inicio` (admin, oscuro) y `00-clases-hoy`.

### Defectos de producto

Ninguno nuevo. Observación de baja prioridad: Inicio lista, en «Hoy en el box», todas las sesiones canceladas del día (hoy unas 40 filas de residuo E2E), lo que empuja la tarjeta «Asistencia de la semana» fuera de la vista. Con un horario real no ocurre.
