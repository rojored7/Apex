# Sprint 7 · cuaderno del front (rama feat/sprint-07-front)

## S7-F1 · Configuración (Horario y Clases) y menú Hoy por feature (US-154, S7-D21, BRECHAS 13.17)

Rojo (antes del código): `HoursSettingsForm.test.tsx` y `ClassesSettingsForm.test.tsx` no resolvían el import
(2 archivos fallidos); `nav.test.ts` 3 failed (Por avisar hoy sin classes/wods); `ConfigPage.test.tsx` 3 failed
(siete pestañas, `?tab=horario`, `?tab=clases`). Total medido: 6 failed + 2 archivos sin importar.

Verde:
- `features/system/api.ts`: claves `hours` y `classes` (Zod, tipos, `WEEK_DAYS`).
- `features/system/schemas.ts`: `hoursSettingsSchema` (día cerrado o 1 a 2 rangos HH:MM, orden y solape) y `classesSettingsSchema`.
- `components/HoursSettingsForm.tsx` y `ClassesSettingsForm.tsx`; `pages/ConfigPage.tsx` con pestañas Horario y Clases.
- `layouts/nav.ts`: fuera `HOY_FEATURES`; cada entrada de Hoy depende de su feature.
- Fixtures `hoursSection` y `classesSection` en `src/test/settings.ts`.

DESIGN-GAP anotados en código: días hacia adelante (fijo 14, Q23); «Check-in vencido» siempre permitido y marcado (N-38);
Config.html trae tres textos libres de horario, el contrato fija siete días con rangos.

Tropiezo del entorno: en Git Bash los heredocs con barras invertidas pierden las `\`; el regex `HHMM` quedó sin ellas
y el rojo de 6 pruebas lo delató. Corregido con Edit.

Evidencia:
- `slice-gate.sh web/system` (22 pruebas nuevas): exit 0. Sello `web/layouts` con `nav.test.ts`: exit 0.
- Suite completa (214 archivos), lint, tsc y build: verdes. Dos pruebas dependientes (`PanelLayout`, `shells`) se actualizaron por la entrada «Por avisar hoy» del coach.

## S7-F2 · Horario: franjas y cancelar sesiones futuras (US-155, US-158, S7-D9, BRECHAS 15.5)

Rojo (antes del código): `SchedulePage.test.tsx`, `SlotPanel.test.tsx` y `CancelFutureModal.test.tsx` no resolvían el import
(3 archivos fallidos, 0 pruebas ejecutadas).

Verde:
- `features/classes/`: `api.ts` (`useSlots`, `useCreateSlot`, `useUpdateSlot`, `useCancelFutureSessions`, `useCoachCandidates`; Zod en cada respuesta),
  `schemas.ts` (días 0 a 6, `HH:MM`, duración 15 a 240, cupo 1 a 100; PATCH solo con lo cambiado), `classErrors.ts` (409 `slot_conflict` bajo los días,
  `coach_invalid` bajo el coach, 404/403/429/5xx).
- `components/{ClassesTabs,SlotPanel,CancelFutureModal}.tsx`, `pages/SchedulePage.tsx` (tabla paginada en el servidor, «L M X J V», «Open box · sin coach»,
  «Pausada»; el coach ve «No tienes permiso para ver el horario» y no pide nada).
- `config/features.ts` habilita `classes`; `routeTable.ts` carga `/clases/horario`; códigos de error nuevos en `errorCodes.ts`.
- Pruebas dependientes actualizadas por habilitar `classes` (aparecen «Clases de hoy» y «Clases» en el menú): `features.test`, `routes.test`,
  `routes.render.test` (la prueba de ruta deshabilitada pasa a `/mi`), `nav.test`, `shells.test`, `PanelLayout.test` (13 paradas de tabulación).

DESIGN-GAP anotados: «cuántas sesiones se cancelarán» antes de confirmar (el api solo responde el conteo al cancelar; el aviso lo da después);
aviso «Al guardar se regeneran las sesiones futuras» reemplazado por el de Q23 (BRECHAS 15.5 queda cerrada). El coach de la franja se muestra por
correo (GET /users no trae nombre).

Tropiezo: la regla de lint `no-role-literals` frenó `user.role !== "member"` en `useCoachCandidates`; ahora filtra con `can(role, "classes.view")`.
Tropiezo del entorno: los heredocs de Git Bash con comillas fallaron en bloque; los archivos se escribieron con la herramienta Write.

## S7-F3 · Sesiones: semana, sesión extra y cancelar (US-157, S7-D11)

Rojo (antes del código): `weeks.test.ts`, `SessionsPage.test.tsx`, `ExtraSessionPanel.test.tsx` y `CancelSessionModal.test.tsx` no resolvían el
import (4 archivos fallidos, 0 pruebas ejecutadas).

Verde:
- `features/classes/weeks.ts` (semana ISO `AAAA-Www` 2020 a 2100, jueves decide el año, `shiftWeek`, `weekLabel`, hora de Bogotá fija UTC-5).
- `api.ts` suma `useSessions(week)`, `useCreateSession`, `useCancelSession`; `schemas.ts` el formulario de sesión extra (fecha de Bogotá a UTC,
  cupo opcional); `classErrors.ts` los 409 `session_duplicate`, `session_finished` y `session_already_cancelled`, y el 422 `starts_at`.
- `components/{WeekGrid,SessionDetail,ExtraSessionPanel,CancelSessionModal}.tsx`, `pages/SessionsPage.tsx`; `routeTable.ts` carga `/clases`.
- La URL manda: `?semana=AAAA-Www`; sin ella, inválida o con `?dia=hoy` es la semana de hoy. El filtro de coach es local.
- El coach de la sesión extra: el admin elige (GET /users); el coach solo «Yo» o nadie y no lee la lista de usuarios.
- Encabezados de día en `h2` (axe `heading-order`).

DESIGN-GAP anotados: resultados y WOD (v0.5), editar sesión (el api no tiene endpoint), «cada noche» pasa a «cada mañana a las 7:00» (S7-D10),
cada sesión es un botón que abre su detalle (no un enlace directo al check-in) para separar abrir check-in de cancelar.

Tropiezo del entorno: dos heredocs de Git Bash con comillas y acentos fallaron enteros (sin escribir nada); se aplicaron con Edit.

## S7-F3b · correcciones de la revisión de F1-F3 (M1 a M4, L5 a L9)

Rojo medido (15 pruebas fallidas antes del código): 3 de M1 (409 `session_already_cancelled`, 409 `session_finished` y 404 no invalidaban), 2 de M2
(`?dia=hoy` mostraba la semana entera), 3 de M3 (`StatusTag slot` y `data-slot` en la tabla), 1 de L5 (una sola consulta sin `role`), 3 de L7
(`formatTime24`, una por zona), 1 de L8 (hora inicial al abrir), 1 de L8 (cancelar sesiones futuras con cambios sucios), 1 del texto de truncado.

Verde:
- M1: `CancelSessionModal` invalida `["class-sessions"]` ante 409 o 404 (un 500 no).
- M2: `?dia=hoy` filtra la vista al día de hoy («Hoy, martes 20 de octubre», sin navegación de semanas) con «Ver toda la semana».
- M3: `StatusTag slot` (`Activa` ok, `Pausada` neutral) en `shared/ui` y en la tabla del Horario.
- M4: el texto de Configuración dice que el cupo por defecto se usa en una sesión extra sin cupo (el api también lo usa si se crea una franja sin cupo, pero el panel siempre lo pide).
- L5: `useCoachCandidates` pide `role=admin` y `role=coach` con `status=active` y une sin repetir; ya no filtra en el cliente. L6: se quitó «Filtra por coach» del aviso de truncado.
- L7: `formatTime24` en `core/i18n/format.ts` sobre `toBogota`; `weeks.bogotaTime` se eliminó.
- L8: el panel de sesión extra se reinicia al abrir; «Cancelar sesiones futuras» queda deshabilitado con cambios sin guardar y lo explica.
- L9: `// DESIGN-GAP:` del coach por correo en `SlotPanel` y `ExtraSessionPanel`; nombre de prueba corregido.

## S7-F4 · Check-in en modo tablet (US-159, US-161, S7-D24, L-7, E4)

Rojo medido (antes del código): `GymLayout.test.tsx` 1 archivo sin resolver `shared/hooks/gymContext`; `CheckInPage.test.tsx`, `CheckInSearch.test.tsx`
y `AttendeeList.test.tsx` sin resolver su import (4 archivos, 0 pruebas); `MemberSearch.test.tsx` 2 failed (variante gym: `short`, `renderOption`);
`shells.test.tsx` 4 failed (marca del modo tablet, salir con contraseña, cierre por inactividad). `client.test.ts` ya pasaba: `api.delete` con cuerpo
(E4) existía; solo se agregaron 2 pruebas que lo fijan.

Verde:
- `shared/hooks/gymContext.ts` (`useGym`, `useGymHeader`) y `useIdleTimeout.ts`; `layouts/GymLayout.tsx` con `tablet` (sin enlaces, salida con
  contraseña, 10 min), `counter` y `LeaveTabletDialog.tsx`; `layouts/tabletMode.ts` (en memoria); `GymShell` entra al modo en
  `/clases/:id/checkin`, verifica con `core/auth/confirmPassword.ts` (POST /auth/login sin tocar la sesión) y cierra por inactividad con `logout()`.
- `shared/ui`: `MemberSearch` (size gym, estado `short`, `renderOption`, `placeholder`), `StatusTag flag` + `FLAG_LABELS` (siete banderas).
- `shared/data/members.ts`: `photo_attachment_id`, `useMemberSearch(text, delay, minChars)` y `error`.
- `features/classes`: `api.ts` (`useClassSession`, `useCheckIn`, `useRemoveAttendance`; invalidan `["class-session"]` y `["class-sessions"]`),
  `classErrors.ts`, `flags.ts`, `components/{CheckInSearch,AttendeeList,RemoveAttendanceModal}`, `pages/CheckInPage` (default export).
- `docs/operacion/clases.md`, BRECHAS 15.6 y 15.7 resueltas, ROUTES.md; E2E `web/tests/e2e/stack/checkin.spec.ts` (sin correr, V5).

DESIGN-GAP anotados: búsqueda por «últimos 4 del documento» (N-02), WOD del encabezado (v0.5), «Ver asistencia completa» y «registrar resultados»
(no hay enlaces al panel en modo tablet), «saldo pendiente / vence hoy» junto a la hora (AttendeeOut solo trae banderas).
Desviación: la marca del modo vive en memoria del módulo, no en sessionStorage (la regla de lint S4B-D51 lo reserva a RouteError.tsx; no se tocó la configuración). Un F5 en el check-in la restablece por la ruta.
Decisiones: «Vender» (sin plan) sale del modo con la contraseña; etiquetas de bandera «Vencido» y «Congelado» (igual que el estado de membresía).
Tropiezos del entorno: los heredocs de Git Bash con comillas fallaron en bloque otra vez (se usó Write); no hay Python en el PATH.

## S7-F4b · Modo quiosco del servidor en el front (S7-D41 punto 6) y correcciones de la revisión de F4

Merge previo: el backend de C4 (hasta 1057451) con un conflicto en `docs/operacion/clases.md`; se fundieron las dos guías (manda el backend en lo del quiosco).

Rojo medido (pruebas escritas antes del código): 6 archivos, 106 failed / 49 passed (kiosk.test.ts sin módulo, shells.test.tsx sin `registerOnKioskMode` ni marca por sesión,
RequireAuth.test.tsx, client.test.ts, useIdleTimeout.test.tsx, CheckInPage.test.tsx foco).

Verde:
- `core/auth/kiosk.ts` (`enterKiosk`, `exitKiosk`, `logoutDevice` con 3 intentos) reemplaza a `confirmPassword.ts` (borrado, ya no usa `/auth/login`); `exitKiosk` renueva el access si venció y repite una vez.
- `session.ts`: `SessionUser.kioskPath` (de `/auth/me`, `kiosk_path`), `applyKioskAccess` (access nuevo + marca + canal entre pestañas), el puente registra `registerOnKioskMode` (403 `kiosk_mode` relee me).
- `RequireAuth` redirige a `kioskPath` desde cualquier otra ruta (recarga, barra de direcciones). `tabletMode.ts` ya no guarda estado: solo `CHECKIN_PATH` e `isTabletSession`.
- `GymShell`: entra con POST /auth/kiosk (con error y Reintentar), `useBlocker` abre el diálogo de salida para «atrás» y toda navegación fuera; `GymLayout` suma `blockedTo`/`onCancelLeave`.
- LOW a foco al buscador tras «Llegó»; b `useIdleTimeout` con instante límite y `visibilitychange`; c reintento del cierre por inactividad; d `MemberSearch` vuelve al formato original (solo líneas del slice); e `onSelect` muerto fuera de `CheckInSearch` (opcional en `MemberSearch`).
- MEDIUM-3: `web/tests/e2e/stack/checkin.spec.ts` reescrito con cuenta coach (siete banderas, 409 por api, atrás/recarga/barra, salida con contraseña, tiquetera 10-9-10, sin /reveal). Sin correr (V5).
Nota: el quiosco confina a UNA sesión de clase; otra sesión exige salir con la contraseña (las banderas de ayer y +7 días se prueban por el api).

## S7-F4c · Correcciones de la revisión de F4b (HIGH-1, MEDIUM-1 a 3, LOW-1 a 3) y selector «Clases de hoy» (S7-D42, front)

Rojo medido: 7 failed (shells 4, kiosk 1, CheckInPage selector 2) sobre 60 pruebas de los 3 archivos tocados.
Verde: 641 passed en layouts, core/auth y features/classes.
- HIGH-1: GymShell entra al quiosco al LLEGAR a la ruta (efecto atado a pathname y a una ref de la marca), no cuando kioskPath pasa a null; la salida marca `leaving` antes de exitKiosk (se apaga si falla). Prueba: tras salir, 0 llamadas a POST /auth/kiosk.
- MEDIUM-1: el Outlet solo con `kioskPath === ruta` (o saliendo / cambiando de clase); si no, «Activando…» o error con Reintentar. `normalizeKioskPath` (minúsculas, sin barra final) antes del POST.
- LOW-1: el reintento del logout se corta si la sesión ya no es anónima. LOW-2: la salida vale solo para la ruta en que empezó (estado `leavingAt`).
- S7-D42: `switchSession` en el contexto de la tablet, `TodaySessionPicker` («Clases de hoy», `useTodaySessions`: from=to=hoy, status=scheduled).
- E2E (sin correr, V5): entra por clics para que «atrás» pase por el router y abra el diálogo; lecturas de membresías con el token del admin; prueba de la defensa real (POST /members/{id}/reveal con el access de POST /auth/kiosk da 403 kiosk_mode); congela desde hoy; limpia las asistencias de ayer y +7 días con el admin.

## S7-F5 · Asistencia, pestaña del socio, filtro «Última asistencia» y frases del historial (US-162, US-163, E5)

Merge previo: backend hasta e5716da (R2 y C4b); un conflicto en `docs/operacion/clases.md`, se fundieron las dos guías (manda el servidor en S7-D41 y S7-D42; se conservó lo del front).

Rojo medido (stubs con NotImplementedError): 7 archivos, 73 failed / 71 passed (AttendancePage, WeeklySummary, MemberAttendanceTab, LastAttendanceFilter, memberRow, historyPhrase, MembersListPage con la columna nueva).

Verde:
- `features/classes`: `attendanceApi.ts` (useAttendance, useAttendanceSummary, useMemberAttendance, useMemberAttendanceStats; clave `["attendance", ...]`, invalidada por check-in y quitar), `attendanceFilters.ts` (rango en la URL, 28 días por omisión, UTC `[from, to)`, tope 182 días), `pages/AttendancePage`, `components/{WeeklySummary,AttendanceCells}`, `tabs/MemberAttendanceTab`, errores en `classErrors.ts`; la pestaña «Asistencia por socio» ya no está deshabilitada.
- Rutas: `/clases/asistencia` con página y `/socios/:id/asistencia` hija de la ficha (feature classes); `MEMBER_TABS` sin `disabledUntil`; routes.reference, routes.test y ROUTES.md al día.
- `features/members`: filtro `last_attendance` (`LastAttendanceFilter`), columna «Última asistencia» (`lastAttendanceText`), «12 clases · quedan 2» (`planWithClasses`), `memberRowSchema` con los dos campos nuevos; la exportación no admite el filtro (se oculta «Exportar» y se explica).
- `historyPhrase.ts`: «registró una asistencia» y «quitó una asistencia»; `ENTITY_LABELS["classes.attendance"] = "Asistencia"`.
- BRECHAS 15.8 resuelta y fila 45 (asistencia) cerrada.

DESIGN-GAP: la pantalla de Asistencia no tiene diseño (se arma con FilterBar, DataTable y Pagination); «racha»; «Esta semana» y «Hace más de 10 días» del select (el api filtra 7/14/30/60 días o nunca).
Decisión: la pestaña de la ficha lee la última asistencia y el conteo de 30 días con `GET /attendance?member_id` (`limit=1`, el `total` es el conteo) porque `/members/{id}/attendance` no filtra por fecha.
Tropiezos del entorno: heredocs de Git Bash con comillas fallaron otra vez (se usó Write); sin Python en el PATH.

## S7-F6 · Inicio con clases de hoy y asistencia de la semana (US-164, BRECHAS 22, 23, 30 y 15.10)

Rojo medido (stubs con NotImplementedError): 2 archivos nuevos (ClassesKpis y sessionsToday), 19 failed; InicioPage 3 failed (región Clases, botón Check-in, DESIGN-GAP).
Verde:
- `features/dashboard/components/ClassesKpis.tsx`: «Hoy en el box» (hora de Bogotá, coach u «Open box», `n / cap`, «Llena», Check-in por sesión programada, «Terminó»/«Cancelada») y «Asistencia de la semana» (conteo, nota de marcadas, enlace a `/clases/asistencia`).
- `sessionsToday.ts`: `nextCheckInSession` (programada, hasta 60 min después de empezar). `InicioPage`: acción «Check-in» hacia esa sesión, oculta si no queda ninguna.
- `shared/lib/routes.ts` suma `checkInPath` (la feature classes lo reexporta como `checkInHref`). `FutureKpis` queda solo con el WOD.
DESIGN-GAP: gráfico por día, promedio por clase y socios distintos; la duración no viene en `sessions_today` (ventana fija de 60 min).

## S7-F5b · Correcciones de la revisión de F4c y F5 y búsqueda de 3 letras en quiosco

Rojo medido: 12 failed sobre 353 pruebas de 17 archivos (kiosk 3, shells 1, format 2, exportar 1, CheckInSearch 2, AttendancePage 1, CheckInPage 2). Las aserciones de L4 (invalidar `["attendance"]`) ya pasaban: el código lo hacía, solo faltaba fijarlo.
Verde:
- M: `enterKiosk` distingue 403 `kiosk_mode` («Esa clase no es de hoy. Elige otra clase.»), 429 con la espera y la conexión; `enterFailed` ya no dice «Reintentar» (el selector no tiene el botón). Prueba en shells: no navega y la marca sigue; la prueba de CheckInPage usa `KIOSK_MESSAGES.notToday`.
- L1: `TodaySessionPicker` muestra «Elige otra clase» si la actual no es de hoy y aparece con al menos una sesión distinta. L2: la marca de salida se pone en `onLeave`, justo antes de `proceed()`/`navigate()`.
- L3: `bogotaDayOf` en `core/i18n/format.ts` (lo usa `memberRow`); `MembersListPage` lee `Date.now()` una vez por tabla (`useState`, no por celda: la regla de pureza prohíbe leerlo en el render).
- L4: aserciones de `["attendance"]` en check-in y quitar; E2E suma el selector (cambiar de clase y volver) y el 403 `kiosk_mode` con la sesión de +7 días. La lista de socios y el historial se refrescan por staleTime.
- L5: `rangeErrorOf` suma `out_of_range` (años fuera de 2020 a 2100) con su mensaje. L6: ROUTES.md, BRECHAS fila 43 y `clases.md` (S7-D42 una sola vez, con la regla del servidor).
- Exportar: sin `delete filters.last_attendance` ni nota; `ExportButton` envía `last_attendance` (types.ts ya lo traía). Prueba: el filtro llega.
- Quiosco (C4c): `CHECKIN_MIN_CHARS = 3` contando sin espacios; `useMemberSearch` igual; `limit=10` (tope 20) y sin `sort`.

## S7-V7f · Correcciones de la revisión final del front (HIGH-1, M-2 a M-8, L-9 a L-11, L-13 a L-15)

Rojo medido (cambios de código revertidos con parche, pruebas nuevas en su sitio): 13 failed de 284 pruebas en 7 archivos (kiosk 401, tonos de bandera, GymLayout contador y contraseña vacía, selector con botón, classErrors, format).
Verde:
- HIGH-1, M-2, M-3 (E2E, sin correr): cada sesión con instante propio (hoy = ahora + 2 h y +2,5 h al minuto; ayer y +7 días a las 17:MM del reloj), la prueba se salta después de las 21:00 de Bogotá, las asistencias de ayer y +7 días se registran con el admin, el token del admin se renueva antes de limpiar y las cuatro sesiones se cancelan en el `finally`; el selector usa la hora real y el botón.
- M-4: un 401 que no es `invalid_password` en la salida cierra la sesión del dispositivo y dice «La sesión de esta tablet terminó…». M-5: el selector cambia con el botón «Cambiar de clase». M-6: `FLAG_TONES` alineado. M-7: «antes y después del inicio». M-8: `LeaveTabletDialog` con RHF + Zod (vacío dice «Escribe la contraseña.»; el botón ya no se deshabilita).
- L-9: `bogotaDayStartUtc`/`bogotaDayEndUtc` en `core/i18n/format.ts` (classes, audit, crypto y pagos los usan). L-10: `navigate(..., { replace: true })`. L-11: 403 → bloqueada solo con `attendance_locked`; 404 `session_not_found` habla de la sesión; un solo `tooManyReads`. L-13: contador con `role="status"`. L-14: sin `as unknown as`. L-15: BRECHAS 15.6 y 15.9.
- L-12: `types.ts` aún no trae `duration_min` en `SessionTodayOut`; queda la ventana de 60 min con su DESIGN-GAP.
