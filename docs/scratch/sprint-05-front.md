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

## F5 · Cuentas por correo y aviso de custodio (US-131, US-136)

- Base: rebase de F1 a F3 sobre `a098f67` (B11); un conflicto en `docs/BRECHAS.md` (filas 13.6 y 13.7) resuelto conservando ambas. `gen:api`: `types.ts` suma la ruta `/payments/{id}/receipt.pdf` (B11); `tsc` limpio.
- La feature «users» del brief vive en `features/system` (el gate `web/users` no existe: se usa `web/system`).
- Rojo/Verde: `ForgotPage` (texto de Login.html, siempre el mismo mensaje), `system/api.ts` (`email_sent` con default false; con true el token se descarta y `url`/`activationUrl` son null), `NewUserPanel` y `LinkModal` (rama «enviado» sin enlace; rama «no salió» con enlace), `core/custody/{custodyNotice.ts,CustodyNoticeHost.tsx}` (almacén externo, se retira solo tras Retry-After), `shared/ui/CustodyNotice`, `core/api/client.ts` (503 `crypto_unavailable`: aviso, sin reintento) y montaje en `PanelShell` (ranura banner) y `PortalShell`.
- El host vive en `core/custody` porque `layouts.no-fetch.test` prohíbe importar `core/api` desde los layouts.
- E2E: `stack/users-activation.spec.ts` (recuperar sin enumeración; rama email_sent), `users-access.spec.ts` (preview, texto nuevo). Filas 13.25 y 13.26 de BRECHAS.

## F5 · Revisiones (seguridad: 0 CRITICAL, 0 HIGH, 1 MEDIUM, 2 LOW)

- MEDIUM (S5-D251): el aviso de custodio solo vive en los shells (panel y portal); las rutas de acceso no descifran columnas y en `/recuperar` romper la respuesta constante filtraría información. Aceptado, sin cambio.
- LOW 1: tiempo observable de `ForgotPage`; aceptado, la igualación la hace el api (`wait_floor`, S5-D38).
- LOW 2 (corregido): `stack/users-activation.spec.ts` leía `respuesta.json()` dos veces y usaba `test.skip` dentro del `try`; ahora lee una vez y sale con `return` (anotación) para que el `finally` limpie siempre al coach.

## F4 · Recibo y exportaciones (US-137, US-138, US-139)

- Base: rebase de F1, F2, F3 y F5 sobre `99c8246` (B11 y B12), sin conflictos. SHA nuevas de los checkpoints: F1 `33dfd8e`, F2 `9c53244`, F3 `a0cb1bb`, F5 `4a27e0d`. `npm run gen:api`: sin diferencias (el contrato de B11 y B12 ya estaba en `types.ts` desde F5); `tsc` y `types.contract.test.ts` verdes.
- `core/api/client.ts`: `api.blob(path, { query, timeoutMs, signal })` devuelve `{ blob, filename, contentType }`. Tiempo propio `BLOB_TIMEOUT_MS` (120 s, mayor que el del JSON; sirve a las exportaciones de hasta 20 000 filas y al recibo). Sin caché ni almacenamiento. El 401 y el 503 `crypto_unavailable` se tratan como en el JSON; un 503 `busy` no se reintenta (la exportación ya pudo auditarse). `request` se partió en `send` (reintentos) + `readSuccess`/`requestBlob`. `core/api/disposition.ts` lee el nombre de `Content-Disposition` (RFC 6266).
- `shared/lib/download.ts`: `downloadBlob` (ObjectURL creado y revocado en `finally`, enlace fuera del DOM), `safeFilename` (sin rutas ni caracteres raros, 100 como tope) y `saveDownload` (nombre del api o el de respaldo). `shared/lib/downloadErrors.ts`: los textos fijos del api de las exportaciones (409 `export_in_progress`, 422, 503 `crypto_unavailable`) se muestran tal cual; 403, 404, 429 y 5xx usan el texto de la pantalla. `shared/data/download.ts`: `useBlobDownload` (la descarga ocurre dentro de la mutación, que devuelve `undefined` y pasa por `useSensitiveMutation`: el archivo no toca la caché de TanStack Query).
- Permisos: nueva acción `payments.receipt` (admin y coach; el api abre el recibo a `StaffDep`); `members.export` y `payments.export` ya existían (admin).
- Pagos: `ReceiptButton` (fila `inline` y detalle `button`; aviso `role="alert"`, estado «Preparando el recibo…»), `ExportButton` (ConfirmModal con el texto fijo; `exportSchema.ts` valida con Zod el rango obligatorio de 12 meses como máximo antes de llamar, las mismas reglas que el api: `to` exclusivo no pasa de un año después de `from`, el 29 de febrero pasa al 28). Socios: `ExportButton` con q, status, membership_status y plan_id (sin orden ni paginación).
- Decisión: `GET /payments/export` no acepta el filtro `backdated` de la lista; con él activo el botón queda deshabilitado y una nota lo explica (para que el CSV nunca traiga pagos que la lista no muestra). Fila 13.4 de BRECHAS.
- Los botones Exportar viven en una fila `.tools` bajo el encabezado (no en `PageHeader.actions`: el modal de confirmación necesita su estado).
- Pruebas: `client.test.ts` (blob), `disposition.test.ts`, `download.test.ts`, `downloadErrors.test.ts`, `ReceiptButton.test.tsx`, los dos `ExportButton.test.tsx`, `exportSchema.test.ts`, y casos nuevos en `PaymentsPage`, `PaymentDetailModal` y `MembersListPage`. `test/server.ts` suma `file` a `MockReply` (respuesta binaria).
- E2E de stack (escritos, no corridos; V5): `stack/payments-receipt-export.spec.ts` y `stack/members-export.spec.ts`. El segundo necesita el custodio desellado.
- BRECHAS: §10.1 y §10.8 cerradas; filas 13.4 y 13.5 en «cerrada» (el límite del recibo pasa de 30 s a 120 s, el mismo de las exportaciones).

## F4 · Revisiones (seguridad: 0 CRITICAL, 0 HIGH, 1 MEDIUM, 3 LOW; S5-D259)

- MEDIUM (S5-D259): `q` sigue viajando en la URL de `GET /members/export` y `GET /payments/export` para que el CSV coincida con la lista; Nginx registra solo `$uri` y el api guarda `has_q`. Verificado, sin cambio.
- LOW 1 (corregido): `useBlobDownload` lleva un `AbortController` por descarga, abortado al desmontar el componente; `api.blob` recibe su `signal` y `saveDownload` no se ejecuta ni se muestra error. Pruebas en `ReceiptButton.test.tsx` y `ExportButton.test.tsx` de socios.
- LOW 2 (corregido): un 503 `busy` en una descarga dice la espera de `Retry-After` (`toDownloadError`), conserva `retryAfterS` y bloquea la acción ese tiempo (`blocked`; `ConfirmModal.confirmDisabled` en las exportaciones, botón deshabilitado en el recibo), sin reintento automático. Pruebas en `downloadErrors`, `ReceiptButton` y `ExportButton` de socios.
- LOW 3 (corregido): `requestBlob` rechaza un 200 cuyo `Content-Type` no empiece por `application/pdf` ni `text/csv` con `unexpected_content_type` y mensaje fijo; no se guarda nada. Pruebas en `client.test.ts` y `ReceiptButton.test.tsx`.

## V10 · Revisión TypeScript (0 CRITICAL, 0 HIGH, 3 MEDIUM, 3 LOW; S5-D260)

- MEDIUM 1 (corregido): `downloadBlob` revoca el ObjectURL en `setTimeout(..., 0)` tras el clic (Safari y Firefox truncan la descarga si se revoca en el mismo tick). `download.test.ts` usa `vi.useFakeTimers` y comprueba que no se revoca en el mismo tick y sí al avanzar el reloj.
- MEDIUM 2 (corregido, causa probable del flake 1/3522): el caso «503 busy» de `ReceiptButton.test.tsx` y el de `ExportButton.test.tsx` de socios usan `vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] })`, `fireEvent`, `vi.advanceTimersByTimeAsync(0)` para asentar y `vi.advanceTimersByTime(1000)` dentro de `act`; sin reloj real ni timeouts de 3000. (`findBy*` no sirve con `setTimeout` simulado: el `asyncWrapper` de RTL espera un `setTimeout(0)`.)
- MEDIUM 3 (corregido): las pruebas «al desmontar» ya no duermen 50 ms: se asienta la promesa de `api.blob` (`vi.spyOn(api, "blob")` + `await expect(...results[0].value).resolves`).
- LOW 4 (corregido): `types.contract.test.ts` cruza con `expectTypeOf` (mismas claves y asignabilidad) `notificationRowSchema`, `waLinkSchema` y `channelsOutSchema` con `NotificationOut`, `WaLinkOut` y `ChannelsOut` de `types.ts`.
- LOW 5 (corregido): `channelsSettingsSchema` con `.strict()` en `email`, `whatsapp` y `telegram`; prueba en `features/system/schemas.test.ts`.
- LOW 6 (documentado): comentario en `useBlobDownload` (una instancia por botón; para listas, encolar `mutateAsync`).
