# Mapa de rutas del front

Cada ruta dice: pantalla de referencia en `screens/`, quién la ve, y qué pide al API (`/api/v1`). Las carpetas de React siguen los dominios del plan: `members`, `plans`, `memberships`, `payments`, `classes`, `wods`, `results`, `athletes`, `notifications`, `system`, `portal`.

Convenciones fijadas en el gate del 21 de octubre de 2026 (`docs/ddd/DECISIONES.md`): toda lista pagina con `limit` (1 a 200, por defecto 25) y `offset`, y responde `{ items, total, limit, offset }` (D2); los errores llegan como `{ error: { code, message, field?, existing_id? } }`; los nombres definitivos de ruta los fija `docs/openapi.json` (`docs/ddd/05_service_design.md`, sección 4).

## Acceso (sin sesión)

- `/login` → `Login.html`. POST `/auth/login` (cookie `apex_refresh` HttpOnly; el access solo en memoria) y luego GET `/auth/me`. Con `must_change_password` va a `/cambiar-clave`; si no, a `next` o al inicio del rol: `/` (admin, coach) o `/mi` (socio). "Cerrar sesión" del TopBar: POST `/auth/logout`. Implementación S2-F3: [detalle](../ddd/blueprints/sprint-02-rutas-front.md).
- `/recuperar` → `Login.html` (tarjeta "Olvidé mi contraseña"; S2-F4a, `features/auth/pages/ForgotPage.tsx`). POST `/auth/forgot` y, pase lo que pase (204, 429, 5xx o red), el mismo mensaje: "Pídele al administrador tu enlace de recuperación." (`// DESIGN-GAP:`: en v0.1 forgot no envía correos, H-2 y S2-D36; el enlace lo da el admin).
- `/restablecer/:token` → `Login.html` (tarjeta "Nueva contraseña / Activar cuenta"). Activa una cuenta nueva o recupera el acceso con el mismo enlace (S2-D18): POST `/auth/reset` `{ token, new_password }`; no abre sesión. Implementación S2-F4a: [detalle](../ddd/blueprints/sprint-02-rutas-front.md).
- `/tv?token=…` → `TV.html`. GET `/tv/today` cada 30 s. Sin sesión; el token lo da Configuración.
- `/cambiar-clave` → sin pantalla propia (`// DESIGN-GAP:`; usa la tarjeta "Nueva contraseña" de `Login.html`). Con sesión, cualquier rol. POST `/auth/me/password`. Toda ruta con sesión lleva aquí mientras `must_change_password` sea verdadero (S2-D18). Implementación S2-F4a (y "Mi cuenta" del TopBar): [detalle](../ddd/blueprints/sprint-02-rutas-front.md).

## Panel (layout: TopBar + SideNav) — admin y coach

Inicio
- `/` → `Inicio.html`. GET `/dashboard` (socios al día, por vencer, vencidos, ingresos del mes, asistencia semana, sesiones de hoy, por avisar, últimos movimientos). Hasta que exista GET `/dashboard` (Sprint 4A, US-108), Inicio es mínima: saludo con el correo y accesos a Socios y, para admin, Planes, Usuarios y Configuración (`// DESIGN-GAP:`, S2-D25).

Socios (módulo 1)
- `/socios` → `Socios_Lista.html` (celular: `Socios_Movil.html`). GET `/members?q&status&plan&last_attendance&sort&limit&offset` (`last_attendance` solo desde v0.4; la lista trae `membership_status` resuelto y nunca datos cifrados). Admin y coach. Implementación S2-F6: [detalle](../ddd/blueprints/sprint-02-rutas-front.md).
  - Implementación S3-F2 (US-071, US-072; `features/members/pages/MembersListPage.tsx`). Filtros en la URL con los nombres del api: `membership_status` (un chip: `active` Al día, `expiring` Por vencer, `expired` Vencidos, `frozen` Congelados, `pending_payment` Pendiente de pago, `none` Sin membresía; D22), `status=deleted` (chip "Dados de baja", solo con `members.view`, N-20; manda sobre `membership_status` si llegan los dos), `plan_id` (UUID; filtro "Plan" con GET `/plans?active=true&limit=200`, un plan de la URL que la lista no trae queda como "Plan elegido"), `sort`, `limit` y `offset`. Un valor desconocido no viaja; cambiar chip o plan vuelve a la primera página. La búsqueda (`q`) vive en memoria y nunca llega a la URL (S2-D41).
  - Conteos de los chips (D37): GET `/memberships/summary` (cinco estados) y GET `/members?limit=1&offset=0` (total de socios vivos, chip "Todos" y encabezado); "Sin membresía" es el total menos la suma de los cinco.
  - Columnas en escritorio: Socio (enlace a la ficha), Plan vigente, Vence, Membresía y Estado. En el celular (menos de 768 px) la lista son tarjetas (nombre, "Mensual · vence 27 nov 2026", estado) con "Cargar más" (páginas de `limit` por `offset`, hasta 20 páginas, M-9) y el botón flotante "Nuevo socio" (`members.create`).
- `/socios/nuevo` → `Socio_Form.html`. POST `/members` (+ POST `/members/:id/attachments` para foto y autorización). Admin y coach con `members.create`. Implementación S2-F6: [detalle](../ddd/blueprints/sprint-02-rutas-front.md).
- `/socios/:id` → `Socio_Ficha.html`. GET `/members/:id` con pestañas: `/memberships`, `/payments`, `/attendance`, `/results`, `/athlete`, `/notifications`, `/attachments`, `/audit`.
- `/socios/:id/editar` → `Socio_Form.html`. PATCH `/members/:id`.
- Dar de baja: modal en la ficha. DELETE `/members/:id` (borrado lógico). Solo admin. Reactivar: POST `/members/:id/reactivate` (solo admin). Mostrar un dato cifrado: POST `/members/:id/reveal` `{ field }` (admin y coach, auditado).

Planes (módulo 2) — solo admin
- `/planes` → `Planes.html`. GET `/plans`. Crear y editar en panel lateral: POST / PATCH `/plans/:id`. Activar/desactivar: PATCH `active`. En el front la ruta es solo admin (`plans.view`); el API además deja al coach `GET /plans?active=true` y `GET /plans/{id}` de planes activos, que el front todavía no ofrece (S2-D26). Implementación S2-F7: [detalle](../ddd/blueprints/sprint-02-rutas-front.md).

Membresías (módulo 3)
- `/membresias` → `Membresias.html`. GET `/memberships?status&q&plan_id&ends_from&ends_to&limit&offset`.
  - Implementación S3-F5 (US-089 a US-092; `features/memberships/pages/MembershipsPage.tsx`). Admin y coach (`memberships.view`). Filtros en la URL: `status` (uno o varios estados separados por comas, igual hacia el api, D18: `active`, `expiring`, `expired`, `frozen`, `pending_payment`, `cancelled`; sin `status` el api excluye las anuladas), `plan_id` (UUID), `ends_from` y `ends_to` ("Vence entre", `AAAA-MM-DD`), `limit` (25, 50 o 100) y `offset`. Un estado desconocido, un plan que no es UUID, una fecha que no existe o un rango invertido no viajan (el rango invertido se explica en la pantalla). La búsqueda por nombre o documento (`q`) vive en memoria y nunca llega a la URL (S2-D41).
  - Pide además GET `/memberships/summary` (cinco tarjetas de socios por estado, `useMembershipSummary`) y GET `/plans` para el filtro de plan (`limit=200`; el coach con `active=true`, S2-D26).
  - Acciones de la fila: Renovar (`memberships.sell`) a `/membresias/vender?socio=:id&renovar=1` con el nombre en el estado de la navegación; Registrar saldo (`payments.register`, solo si la membresía recibe pagos y le falta plata) abre el panel de pagos sobre la lista con `?pago=<membership_id>` (S3-D65); Congelar (`memberships.freeze`, solo al día o por vencer); Anular (`memberships.cancel`, solo admin, toda membresía no anulada).
- Congelar: modal (admin y coach, con los límites de Configuración). POST `/memberships/:id/freeze` `{ frozen_from, frozen_to }`, sin motivo (D14, `// DESIGN-GAP:`); vista previa "Son N días; la membresía terminará el …"; los 409 de límites se explican en el modal (`freeze_days_exceeded` con los días que quedan). Anular: modal con motivo de 5 a 500 caracteres y el aviso de no escribir datos personales. POST `/memberships/:id/cancel` `{ reason }` (solo admin); los pagos no se tocan. Implementación S3-F5: `features/memberships/components/{FreezeModal,CancelMembershipModal}.tsx`.
- `/membresias/vender` y `/membresias/vender?socio=:id&renovar=1` → `Membresia_Vender.html`. POST `/members/:id/memberships` con `first_payment` opcional (crea membresía y primer pago en una sola llamada, D5); con `?renovar=1` el cuerpo lleva `renew: true` y la fecha de inicio la calcula el servidor (Q2); vista previa: GET `/members/:id/memberships/renewal-preview`. Estado "Pendiente de pago" visible en la lista (Q3).
  - Implementación S3-F3 (US-084, US-085, US-088; `features/memberships/pages/SellPage.tsx`). Admin y coach (`memberships.sell`). Parámetros: `socio` (UUID; fija el socio, uno inválido se ignora) y `renovar=1` (solo con `socio`). El nombre del socio viaja en el estado de la navegación (`{ memberName }`); sin él la tarjeta dice "Socio elegido" hasta que exista GET `/members/:id` (S3-F1). La búsqueda del socio nunca llega a la URL (S2-D41).
  - Pide GET `/members?q=&limit=10&offset=0` (buscar socio, `shared/data/members.ts`), GET `/plans?active=true&limit=100&offset=0` (planes activos, `shared/data/plans.ts`; el coach los ve aunque no vea `/planes`, S2-D26), GET `/payments/methods` (etiquetas de los medios, `shared/data/paymentMethods.ts`) y, al renovar con plan elegido, GET `/members/:id/memberships/renewal-preview?plan_id=`. Envía POST `/members/:id/memberships` con `plan_id`, `renew`, `start_date` (no al renovar) y `first_payment` (`amount_cop`, `method`, `reference` solo Nequi y Bre-B, `paid_at` en UTC, `confirm_overpayment`, `confirm_duplicate: false`).
  - Un valor mayor al precio abre la confirmación "¿Registrar un pago mayor al precio?" y solo entonces viaja `confirm_overpayment: true` (S3-D41); un 409 `payment_exceeds_balance` también la abre. 409 `membership_conflict` avisa con "Renovar" (`?socio=:id&renovar=1`); 409 `future_membership_exists` enlaza a `/socios/:id`. Tras el 201 la venta registrada se queda en la página con su estado ("Al día" o "Pendiente de pago").

Pagos (módulo 4)
- `/pagos` → `Pagos.html`. GET `/payments?q&from&to&method&registered_by&voided&member&limit&offset`. Resumen del mes: GET `/payments/summary?month`.
  - Implementación S3-F6 (US-098, US-099, US-100; `features/payments/pages/PaymentsPage.tsx`). Admin y coach (`payments.view`). Filtros en la URL: `from` y `to` ("Fecha del pago", días civiles de Bogotá `AAAA-MM-DD`; hacia el api van en UTC: `from` es ese día a las 00:00 de Bogotá y `to` es exclusivo, el día siguiente al "Hasta" a las 00:00 de Bogotá, rango `[from, to)` de D26), `method` (`cash`, `nequi`, `breb`), `registered_by` (UUID; opciones "Yo" y quienes aparecen en la página), `voided` (Estado: sin él es Todos, D37; `false` Válidos, `true` Anulados), `backdated` (`true` solo retroactivos, `false` sin ellos; S3-D51), `limit` (25, 50 o 100) y `offset`. Un valor desconocido, un usuario que no es UUID, una fecha que no existe o un rango invertido no viajan (el rango invertido se explica). La búsqueda por socio o referencia (`q`) vive en memoria y nunca llega a la URL (S2-D41).
  - Resumen del mes: `?mes=AAAA-MM` (por defecto el mes actual de Bogotá; uno mal formado se ignora; cambiarlo conserva los demás parámetros y Limpiar no lo quita). Pide siempre GET `/payments/summary?month=AAAA-MM`; tarjetas de total (con los pagos válidos), una por medio con la etiqueta de Configuración (GET `/payments/methods`) y anulados; 422 `month` (fuera de 2020 a 2100) se explica.
  - Columnas: socio (enlace a la ficha), fecha y hora de Bogotá, membresía ("Mensual 29 oct–28 nov"), valor, medio, referencia, registró (correo parcial tal cual, S3-D57), estado ("Válido" o "Anulado" y la marca "Retroactivo") y "Ver". "Registrar pago" (`payments.register`) abre el panel con `?pago=nuevo`. "Ver" abre el detalle (GET `/payments/:id`, `components/PaymentDetailModal.tsx`) con la anulación (motivo, quién y cuándo) si la hay; "Anular pago" solo con `payments.void` y en un pago no anulado, cambia el detalle por `VoidPaymentModal` y al cerrarlo vuelve el detalle releído. Sin editar ni borrar.
- Registrar: panel lateral que elige la membresía. POST `/memberships/:id/payments` (409 `membership_cancelled` si está anulada). Medios de pago con etiqueta: GET `/payments/methods`. Detalle: modal, GET `/payments/:id`. Anular: modal con motivo, POST `/payments/:id/void` (solo admin). Recibo: GET `/payments/:id/receipt.pdf`.
  - Implementación S3-F4 (US-095, US-097; S3-D65, E10). El panel "Registrar pago" no es una ruta: se abre sobre cualquier pantalla del panel con el parámetro `?pago=` y lo monta una sola vez `layouts/PanelShell.tsx` (descarga perezosa, solo con la feature `payments`). `?pago=<membership_id>` abre el panel con esa membresía elegida (GET `/memberships/:id`); `?pago=nuevo&socio=<member_id>` lo abre para ese socio; `?pago=nuevo` pide buscarlo (GET `/members?q=&limit=10&offset=0`; el texto nunca llega a la URL, S2-D41). Un valor que no es un UUID se ignora. Los enlaces los arma `shared/lib/paymentPanel.ts` (`paymentPanelHref`, `readPaymentPanel`, `closePaymentPanelHref`), conservando los demás parámetros; cerrar quita `pago` (y el `socio` de un pago nuevo) reemplazando la entrada del historial. Admin y coach (`payments.register`).
  - Las membresías que se ofrecen salen de GET `/memberships?member_id=&status=active,expiring,frozen,pending_payment&limit=20&offset=0` (S3-D66), cada una con su saldo ("Mensual 25 oct–24 nov · saldo $ 60.000"); con una sola se elige sola y el valor se precarga con su saldo. Envía `amount_cop`, `method`, `reference` (solo Nequi y Bre-B), `paid_at` en UTC, `confirm_overpayment` y `confirm_duplicate`. Un valor mayor al saldo (o un 409 `payment_exceeds_balance`) abre "¿Registrar un pago mayor al saldo?" y solo entonces viaja `confirm_overpayment: true`; un 409 `payment_possible_duplicate` abre "¿Registrar otro pago igual?" y solo al confirmar viaja `confirm_duplicate: true` (S3-D41). 409 `payment_limit_reached` se explica sin reintentar; 422 `paid_at_too_retroactive` (coach) va bajo la fecha.
  - Anular (`features/payments/components/VoidPaymentModal.tsx`, solo admin con `payments.void`; la montan la pantalla de pagos, S3-F6, y la pestaña Pagos de la ficha, S3-F7): motivo de 1 a 500 caracteres; tras anular, "Registrar pago nuevo" abre `?pago=<membership_id>` sobre la misma pantalla con el valor y el medio del pago anulado en el estado de la navegación (nunca en la URL).

Clases (módulo 5)
- `/clases` → `Sesiones.html`. GET `/class-sessions?week`. Sesión extra: POST. Cancelar: POST `/class-sessions/:id/cancel`.
- `/clases/horario` → `Horario.html`. GET/POST/PATCH `/class-slots`. Solo admin.
- `/clases/:id/checkin` → `CheckIn.html` (tema oscuro, tablet). GET `/class-sessions/:id`, GET `/members?q` (búsqueda rápida), POST `/attendance` {session, member}, DELETE `/attendance/:id`.
- `/clases/asistencia` → pestaña de `Sesiones.html`. GET `/attendance?member&from&to`.

Movimientos (módulo 6)
- `/movimientos` → `Movimientos.html`. GET `/movements?q&category&active`. Panel lateral: POST / PATCH.

WODs (módulo 7)
- `/wods` → `WOD_Lista.html`. GET `/wods?week` o `/wods?q&benchmark&limit&offset`.
- `/wods/nuevo`, `/wods/:id/editar` → `WOD_Form.html`. POST / PATCH `/wods` (con sus `movements`).
- `/wods/:id` → `WOD_Detalle.html`. GET `/wods/:id`, GET `/wods/:id/leaderboard?level&sex`, GET `/wods/:id/results`.

Resultados (módulo 8)
- `/clases/:id/resultados` → `Resultados_Registro.html` (tema oscuro, tablet). GET `/class-sessions/:id/attendance`, GET/PUT `/results` {wod, member, …}. Validar los enviados por socios: POST `/results/:id/validate`.

Atleta (módulo 9)
- `/socios/:id/atleta` → `Atleta_Perfil.html` (pestaña Atleta de la ficha, con subpestañas Resumen · Medidas · RMs · Récords · Benchmarks). GET `/athletes/:id/metrics`, `/rms`, `/records`, `/benchmarks?wod`. POST `/athletes/:id/metrics`, POST `/athletes/:id/records` (manual).

Avisos (módulo 10)
- `/avisos/hoy` → `PorAvisarHoy.html`. GET `/notifications/today`. Abrir WhatsApp: GET `/notifications/:id/wa-link` (devuelve el `wa.me` y marca como enviado). Omitir: POST `/notifications/:id/skip` {reason}.
- `/avisos/reglas` → `Notif_Reglas.html`. GET/POST/PATCH `/notification-rules`. Pestaña Plantillas: `/notification-templates`. Solo admin edita.
- `/avisos/historial` → `Notif_Historial.html`. GET `/notifications?member&from&to&rule&channel&status&limit&offset`.

Sistema (módulos 11 a 14) — solo admin
- `/sistema/usuarios` → `Usuarios.html`. GET `/users?q&role&status&limit&offset`; alta POST `/users` (devuelve el enlace de activación); edición GET y PATCH `/users/:id`; acciones por fila: POST `/users/:id/revoke-sessions`, `/resend-link`, `/lock` y `/unlock`, y DELETE `/users/:id`. Implementación S2-F4a y S2-F4b: [detalle](../ddd/blueprints/sprint-02-rutas-front.md).
- `/sistema/auditoria` → `Auditoria.html`. GET `/audit?from&to&user&entity&action&q&limit&offset`. Verificar cadena: POST `/audit/verify`; última verificación: GET `/audit/verify/last`.
- `/sistema/llaves` → `Llaves.html`. GET `/crypto/keys`, GET `/crypto/ops?limit&offset`, GET `/crypto/jobs`. Rotar: POST `/crypto/keys/:id/rotate` {reason, confirm:"ROTAR"}. Exportar CBOM: GET `/crypto/cbom`.
- `/sistema/configuracion` → `Config.html`. GET/PATCH `/settings` por sección (gym, hours, payment_methods, channels, classes, memberships, tv, privacy). Desde S2-F5, pestañas en `?tab=` para las tres secciones del Sprint 2 (S2-D15): [detalle](../ddd/blueprints/sprint-02-rutas-front.md). Desde S3-F4 (US-056, D24), cuarta pestaña "Medios de pago" en `?tab=medios`: GET y PATCH `/settings/payment_methods` con los tres medios fijos (Efectivo, Nequi, Bre-B), cada uno con su nombre (1 a 30, sin repetirse) y su ayuda (hasta 120); no se agregan ni se quitan medios. Al guardar se relee GET `/payments/methods`.

## Portal del socio (layout: una columna + menú inferior) — rol socio

- `/mi` → `Portal_Inicio.html`. GET `/me/summary`.
- `/mi/pagos` → `Portal_Pagos.html`. GET `/me/payments?limit&offset`. Recibo: GET `/me/payments/:id/receipt.pdf`.
- `/mi/wods` → `Portal_WODs.html`. GET `/me/results?limit&offset`, GET `/wods/today`. Enviar resultado: POST `/me/results` (queda "por validar").
- `/mi/progreso` → `Portal_Progreso.html`. GET `/me/records`, `/me/rms`, `/me/benchmarks`, `/me/metrics`. Registrar peso: POST `/me/metrics`.
- `/mi/datos` → `Portal_Datos.html`. GET/PATCH `/me`. Cambiar contraseña: POST `/me/password`.
- `/mi/avisos` → `Portal_Avisos.html`. GET `/me/notifications`, PATCH `/me/channels`, POST `/me/push-subscription` (web push).

## Permisos (lo que decide qué muestra el front)

- Admin: todo.
- Coach: ve y usa Inicio, Hoy, Socios (ver, crear, editar), Membresías y Pagos (vender y registrar; no anular), Clases, WODs, Movimientos, Atleta, Avisos. No ve Sistema ni Planes. El front oculta los botones; el API vuelve a verificar.
- Socio: solo `/mi/*`.
- La tabla única de rutas del front es `web/src/config/routeTable.ts` (S2-D23): ruta, feature, acceso (acción de `web/src/core/auth/permissions.ts`) y layout. `web/src/config/routes.reference.ts` es su copia escrita a mano desde este archivo y una prueba exige que coincidan: si cambia una ruta aquí, cambian los dos. `/clases/horario` usa la acción `classes.schedule` (solo admin) y el inicio por rol sale de `portal.view` (solo socio).
