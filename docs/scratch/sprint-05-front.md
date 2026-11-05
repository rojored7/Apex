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

## F2 · Reglas, plantillas, historial y pestaña Canales (US-120 a US-122, US-130)

- Base: `1cbd08c` (checkpoint de F1); la rama del backend sigue en `8eff83e` (sin rebase) y `gen:api` sin diff.
- Rojo: `features/system/components/ChannelsSettingsForm.test.tsx`, `features/notifications/pages/RulesPage.test.tsx`, `pages/HistoryPage.test.tsx`; `ConfigPage.test.tsx` pasa a cinco pestañas y `?tab=canales` abre Canales (antes era una pestaña desconocida).
- Verde:
  - Sistema: `features/system/{api,schemas}.ts` (sección `channels` con `credentials_present`), `components/ChannelsSettingsForm.tsx`, quinta pestaña en `ConfigPage`.
  - Avisos: `adminSchemas.ts`, `adminApi.ts`, `adminErrors.ts`, `historyFilters.ts`, `historyView.ts`, `components/{RulesTab,TemplatesTab,RuleForm,TemplateEditor,MessagePanel}.tsx`, `pages/{RulesPage,HistoryPage}.tsx`, rutas `/avisos/reglas` y `/avisos/historial` con `load`.
- Decisiones:
  - El desfase del api es negativo antes del fin (por vencer) y positivo después (vencida); el formulario lo escribe como "días antes" o "días después" y `toOffsetDays` evita el `-0`.
  - Editar envía solo lo que cambió (`dirtyFields`); el evento y los días viajan juntos.
  - El coach lee las reglas y las plantillas (GET con `staff-read`) pero no ve botones de escritura ni la vista previa: `POST /notification-templates/preview` es solo admin en el router (el brief decía `staff-read`; el código manda `AdminDep`).
  - Las escrituras releen la lista solo con 404 o 409 (`refreshIfStale`, S5-D244).
  - Historial: `from` y `to` son fechas del aviso (`target_date`, AAAA-MM-DD) y viajan tal cual; lo inválido no viaja.
- E2E: `tests/e2e/avisos.spec.ts` (reglas, plantillas, historial; axe en claro y oscuro a 390 y 1440 px) y `settings-config.spec.ts` (pestaña Canales) en preview, verdes; `stack/avisos.spec.ts` suma el caso de solo lectura (se corre en V5).
- DESIGN-GAP: filas 13.18 a 13.22 de `docs/BRECHAS.md`.
- Sigue en F3: ficha del socio (pestaña Avisos), preferencias y la tarjeta "Por avisar" de Inicio.

## F3 · Ficha del socio, preferencias e Inicio (US-123, US-130, US-132)

- Base: `33dbc57` (checkpoint de F2); la rama del backend sigue en `8eff83e` y `gen:api` sin diff.
- Rojo: `features/notifications/tabs/NotificationsTab.test.tsx`, `components/ChannelPreferences.test.tsx`, `features/dashboard/components/NotificationKpis.test.tsx`; `FutureKpis.test.tsx`, `InicioPage.test.tsx`, `MemberDetailPage.test.tsx` y `routes.test.ts` se ajustan.
- Verde:
  - Avisos: `memberSchemas.ts`, `memberApi.ts` (`useMemberChannels`, `useSetMemberChannel`, `useMemberNotifications`), `memberErrors.ts`, `components/ChannelPreferences.tsx`, `tabs/NotificationsTab.tsx`.
  - Ficha: la pestaña Avisos es una hija de la feature `notifications` (`childRoute` en `routeTable.ts`, `routes.reference.ts`, `ROUTES.md`); `MemberDetailPage` la quita de las deshabilitadas y `memberTabs` la comprueba con `isPageAvailable`.
  - Inicio: `NotificationKpis.tsx` (sección "Avisos") y `FutureKpis` sin esas dos tarjetas.
- Decisiones:
  - El interruptor sale de la preferencia explícita, no de `effective`: sin consentimiento `effective` es vacío pero la preferencia sigue siendo del socio. Correo: activo solo con fila explícita activa (opt-in); WhatsApp manual: activo salvo fila explícita inactiva (S5-D31).
  - Cada interruptor guarda al momento con un PATCH de ese canal y no cambia hasta la respuesta (un 422 `consent_required` deja el interruptor como estaba y muestra el mensaje del api).
  - Un socio dado de baja es de solo lectura: el PATCH responde 409 `member_deleted` (N-20).
  - El coach puede cambiar las preferencias (`PATCH` es `StaffDep`, cubeta `notifications-write`).
  - Las escrituras releen solo con 404 o 409 (`refreshIfStale`).
- E2E preview: `member-tabs.spec.ts` (pestaña Avisos, PATCH del correo, axe en claro y oscuro a 390 y 1440 px) y `home.spec.ts` (tarjetas de avisos), verdes.
- DESIGN-GAP: filas 13.23 y 13.24 de `docs/BRECHAS.md`; 13.2 y 13.3 cerradas.
- Sigue en F5 y F4: exportaciones, recibo, tarjetas de cuenta por correo y aviso de custodio.

## F3 · Revisiones (seguridad: 0 CRITICAL, 0 HIGH, 1 MEDIUM, 1 LOW)

- MEDIUM (S5-D245): con `has_consent` falso el interruptor de correo no se puede activar desde la ficha (queda deshabilitado) y un texto fijo explica que primero hay que registrar el consentimiento en Datos; desactivarlo sí se puede si estaba activo. El 422 `consent_required` del api sigue como respaldo. Pruebas en `ChannelPreferences.test.tsx` (sin consentimiento no activa ni llama al PATCH; con consentimiento sí; desactivar con y sin consentimiento).
- LOW: mientras guarda hay una región `aria-live="polite"` con «Guardando…». Prueba de presencia.
