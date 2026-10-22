# Mapa de rutas del front

Cada ruta dice: pantalla de referencia en `screens/`, quién la ve, y qué pide al API (`/api/v1`). Las carpetas de React siguen los dominios del plan: `members`, `plans`, `memberships`, `payments`, `classes`, `wods`, `results`, `athletes`, `notifications`, `system`, `portal`.

Convenciones fijadas en el gate del 21 de octubre de 2026 (`docs/ddd/DECISIONES.md`): toda lista pagina con `limit` (1 a 200, por defecto 25) y `offset`, y responde `{ items, total, limit, offset }` (D2); los errores llegan como `{ error: { code, message, field?, existing_id? } }`; los nombres definitivos de ruta los fija `docs/openapi.json` (`docs/ddd/05_service_design.md`, sección 4).

## Acceso (sin sesión)

- `/login` → `Login.html` (S2-F3, `features/auth/pages/LoginPage.tsx`). POST `/auth/login` (cookie `apex_refresh` HttpOnly, `Path=/api/v1/auth`; el access queda solo en memoria); luego GET `/auth/me` para el nombre del gimnasio. Con `must_change_password` va a `/cambiar-clave`; si no, a `next` cuando `safeNext` lo acepta para el rol, o al inicio del rol: `/` (admin, coach) o `/mi` (socio). Errores: 401 siempre "Correo o contraseña incorrectos"; 429 con la cuenta atrás de `Retry-After` y el botón bloqueado; 403 de `Origin`, red y 5xx con mensaje genérico. Avisa al llegar si el cierre anterior no lo confirmó el servidor (H-1) o si la sesión venció. Bajo el logo dice "APEX" (`// DESIGN-GAP:`, S2-D50: `gym_name` solo llega con sesión). "Cerrar sesión" del TopBar: POST `/auth/logout` (por la cookie) y, pase lo que pase, limpia la sesión de todas las pestañas (`apex-auth`) y vuelve aquí.
- `/recuperar` → `Login.html` (tarjeta "Olvidé mi contraseña"). POST `/auth/forgot`.
- `/restablecer/:token` → `Login.html` (tarjeta "Nueva contraseña / Activar cuenta"). POST `/auth/reset`.
- `/tv?token=…` → `TV.html`. GET `/tv/today` cada 30 s. Sin sesión; el token lo da Configuración.
- `/cambiar-clave` → sin pantalla propia (`// DESIGN-GAP:`; usa la tarjeta "Nueva contraseña" de `Login.html`). Con sesión, cualquier rol. POST `/auth/me/password`. Toda ruta con sesión lleva aquí mientras `must_change_password` sea verdadero (S2-D18).

## Panel (layout: TopBar + SideNav) — admin y coach

Inicio
- `/` → `Inicio.html`. GET `/dashboard` (socios al día, por vencer, vencidos, ingresos del mes, asistencia semana, sesiones de hoy, por avisar, últimos movimientos). Hasta que exista GET `/dashboard` (Sprint 3), Inicio es mínima: saludo con el correo y accesos a Socios y, para admin, Planes, Usuarios y Configuración (`// DESIGN-GAP:`, S2-D25).

Socios (módulo 1)
- `/socios` → `Socios_Lista.html` (celular: `Socios_Movil.html`). GET `/members?q&status&plan&last_attendance&sort&limit&offset` (`last_attendance` solo desde v0.4; la lista trae `membership_status` resuelto y nunca datos cifrados).
- `/socios/nuevo` → `Socio_Form.html`. POST `/members` (+ POST `/members/:id/attachments` para foto y autorización).
- `/socios/:id` → `Socio_Ficha.html`. GET `/members/:id` con pestañas: `/memberships`, `/payments`, `/attendance`, `/results`, `/athlete`, `/notifications`, `/attachments`, `/audit`.
- `/socios/:id/editar` → `Socio_Form.html`. PATCH `/members/:id`.
- Dar de baja: modal en la ficha. DELETE `/members/:id` (borrado lógico). Solo admin. Reactivar: POST `/members/:id/reactivate` (solo admin). Mostrar un dato cifrado: POST `/members/:id/reveal` `{ field }` (admin y coach, auditado).

Planes (módulo 2) — solo admin
- `/planes` → `Planes.html`. GET `/plans`. Crear y editar en panel lateral: POST / PATCH `/plans/:id`. Activar/desactivar: PATCH `active`.

Membresías (módulo 3)
- `/membresias` → `Membresias.html`. GET `/memberships?status&q&plan&ends_from&ends_to&limit&offset`.
- `/membresias/vender` y `/membresias/vender?socio=:id&renovar=1` → `Membresia_Vender.html`. POST `/members/:id/memberships` con `first_payment` opcional (crea membresía y primer pago en una sola llamada, D5); con `?renovar=1` el cuerpo lleva `renew: true` y la fecha de inicio la calcula el servidor (Q2); vista previa: GET `/members/:id/memberships/renewal-preview`. Estado "Pendiente de pago" visible en la lista (Q3).
- Congelar: modal (admin y coach, con los límites de Configuración). POST `/memberships/:id/freeze`. Anular: modal con motivo. POST `/memberships/:id/cancel` (solo admin).

Pagos (módulo 4)
- `/pagos` → `Pagos.html`. GET `/payments?q&from&to&method&registered_by&voided&member&limit&offset`. Resumen del mes: GET `/payments/summary?month`.
- Registrar: panel lateral que elige la membresía. POST `/memberships/:id/payments` (409 `membership_cancelled` si está anulada). Medios de pago con etiqueta: GET `/payments/methods`. Detalle: modal, GET `/payments/:id`. Anular: modal con motivo, POST `/payments/:id/void` (solo admin). Recibo: GET `/payments/:id/receipt.pdf`.

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
- `/sistema/usuarios` → `Usuarios.html`. GET/POST/PATCH `/users`. Bloquear (POST `/users/:id/lock`, `/unlock`), reenviar enlace (POST `/users/:id/resend-link`, única forma de obtener el enlace), cerrar sesiones (POST `/users/:id/revoke-sessions`).
- `/sistema/auditoria` → `Auditoria.html`. GET `/audit?from&to&user&entity&action&q&limit&offset`. Verificar cadena: POST `/audit/verify`; última verificación: GET `/audit/verify/last`.
- `/sistema/llaves` → `Llaves.html`. GET `/crypto/keys`, GET `/crypto/ops?limit&offset`, GET `/crypto/jobs`. Rotar: POST `/crypto/keys/:id/rotate` {reason, confirm:"ROTAR"}. Exportar CBOM: GET `/crypto/cbom`.
- `/sistema/configuracion` → `Config.html`. GET/PATCH `/settings` por sección (gym, hours, payment_methods, channels, classes, memberships, tv, privacy). Desde S2-F5 la pantalla existe con pestañas en `?tab=` (`gimnasio`, `privacidad`, `membresias`) para las tres secciones del Sprint 2 (S2-D15): GET `/settings/{gym|privacy|memberships}` y PATCH con `{ value, version }` (409 `version_conflict` con "Recargar"; 422 con `field = "value.<campo>"`). Las demás secciones se muestran cuando llegue su versión (`// DESIGN-GAP:`).

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
