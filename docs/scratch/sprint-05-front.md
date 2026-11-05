# Cuaderno del front del Sprint 5 (worktree `.claude/worktrees/sprint-05-front`, rama `feat/sprint-05-front`)

## F1 · Por avisar hoy (US-127, US-128, US-129)

- Base: `8eff83e` (rama `feat/sprint-05-openbao-avisos-recibos`). `npm ci` hecho en `web/`.
- Rojo: `config/features.test.ts` (10 features), `features/notifications/api.test.ts`, `components/WaButton.test.tsx`, `components/SkipModal.test.tsx`, `pages/TodayPage.test.tsx` (fallaban por módulo inexistente o por el conteo).
- Verde: `features/notifications/{api,schemas,noticeErrors}.ts`, `pages/TodayPage.tsx`, `components/{TodayRow,WaButton,SkipModal}.tsx` con sus CSS, `config/features.ts` (`notifications` habilitada), `config/routeTable.ts` (`/avisos/hoy` con `load`, `notifications.view`: admin y coach).
- Decisiones:
  - `useWaLink` y `useSkip` pasan por `useSensitiveMutation` (gcTime 0 y reset al terminar; la prueba de `tests/lint/sensitive-mutations` lo exige). La URL de `wa-link` solo vive en una variable local de `WaButton`; `waLinkSchema` solo acepta `https://wa.me/<dígitos>`.
  - `SkipModal` usa `ConfirmModal` (motivo obligatorio de 3 a 500, un envío, error dentro del diálogo) en vez de un formulario nuevo.
  - Chips de canal en la URL (`canal`); filtran la página cargada. Abre en "Todos" (el api no filtra por canal).
  - Los avisos de correo no ofrecen WhatsApp (el api responde 409 `wrong_channel`).
- `types.ts`: el commit base traía `types.ts` desfasado de `docs/openapi.json` (faltaban `email_sent` de B9 y los KPI no nulos de B10; fallaba `types.contract.test.ts`). Se corrió `npm run gen:api` (solo esos cambios; `tsc` limpio). El backend debería incluirlo en su rama: el resultado es idéntico.
- Pruebas que cambian por habilitar la feature: `layouts/nav.test.ts`, `layouts/shells.test.tsx`, `layouts/PanelLayout.test.tsx` (ahora el menú trae el grupo Avisos: Reglas y plantillas, Historial de envíos) y `routes.test.ts` (`/avisos/hoy` con página).
- E2E: `web/tests/e2e/avisos.spec.ts` (preview, 6 casos verdes con axe en claro y oscuro a 390 y 1440 px) y `web/tests/e2e/stack/avisos.spec.ts` (escrito; se corre en V5 contra el ensayo, necesita avisos de WhatsApp pendientes).
- DESIGN-GAP anotados en `TodayPage.tsx` y `TodayRow.tsx`; filas 13.13 a 13.17 de `docs/BRECHAS.md`.
- Pendiente de otros slices: F2 construye `/avisos/reglas` y `/avisos/historial` (hoy dan 404 aunque el menú ya los muestra); F3 la tarjeta de Inicio que enlaza a `/avisos/hoy` (la entrada "Por avisar hoy" del menú exige classes y wods, Q25).

## F1 · Revisiones (seguridad: 0 CRITICAL, 0 HIGH, 1 MEDIUM, 2 LOW)

- MEDIUM (S5-D243): los mensajes del api que se muestran tal cual son fijos y sin datos personales; verificado, sin cambio.
- LOW 2 (S5-D244): `useWaLink` y `useSkip` solo releen la lista ante 404 o 409; 401, 403, 429 y 5xx no. Pruebas en `api.test.ts`.
- LOW 1 (S5-D244 enmendada): con `noopener`, `window.open` devuelve `null` siempre, así que no se comprueba el valor devuelto. Se conserva `window.open(url, "_blank", "noopener,noreferrer")` y `TodayPage` muestra la ayuda fija «Si no se abre WhatsApp, permite las ventanas emergentes de este sitio.» bajo el título. Sin lógica de detección; prueba en `TodayPage.test.tsx` (claro y oscuro).
