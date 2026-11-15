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
