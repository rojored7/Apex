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
