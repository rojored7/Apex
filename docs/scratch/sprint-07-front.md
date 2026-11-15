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
