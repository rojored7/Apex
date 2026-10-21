# Mapa de rutas del front

Cada ruta dice: pantalla de referencia en `screens/`, quién la ve, y qué pide al API (`/api/v1`). Las carpetas de React siguen los dominios del plan: `members`, `plans`, `memberships`, `payments`, `classes`, `wods`, `results`, `athletes`, `notifications`, `system`, `portal`.

## Acceso (sin sesión)

- `/login` → `Login.html`. POST `/auth/login`. Según el rol redirige a `/` (admin, coach) o `/mi` (socio).
- `/recuperar` → `Login.html` (tarjeta "Olvidé mi contraseña"). POST `/auth/forgot`.
- `/restablecer/:token` → `Login.html` (tarjeta "Nueva contraseña / Activar cuenta"). POST `/auth/reset`.
- `/tv?token=…` → `TV.html`. GET `/tv/today` cada 30 s. Sin sesión; el token lo da Configuración.

## Panel (layout: TopBar + SideNav) — admin y coach

Inicio
- `/` → `Inicio.html`. GET `/dashboard` (socios al día, por vencer, vencidos, ingresos del mes, asistencia semana, sesiones de hoy, por avisar, últimos movimientos).

Socios (módulo 1)
- `/socios` → `Socios_Lista.html` (celular: `Socios_Movil.html`). GET `/members?q&status&plan&last_attendance&sort&page&page_size`.
- `/socios/nuevo` → `Socio_Form.html`. POST `/members` (+ POST `/members/:id/attachments` para foto y autorización).
- `/socios/:id` → `Socio_Ficha.html`. GET `/members/:id` con pestañas: `/memberships`, `/payments`, `/attendance`, `/results`, `/athlete`, `/notifications`, `/attachments`, `/audit`.
- `/socios/:id/editar` → `Socio_Form.html`. PATCH `/members/:id`.
- Dar de baja: modal en la ficha. DELETE `/members/:id` (borrado lógico). Solo admin.

Planes (módulo 2) — solo admin
- `/planes` → `Planes.html`. GET `/plans`. Crear y editar en panel lateral: POST / PATCH `/plans/:id`. Activar/desactivar: PATCH `active`.

Membresías (módulo 3)
- `/membresias` → `Membresias.html`. GET `/memberships?status&q&plan&ends_from&ends_to&page`.
- `/membresias/vender` y `/membresias/vender?socio=:id&renovar=1` → `Membresia_Vender.html`. POST `/memberships` (crea membresía y primer pago en una sola llamada).
- Congelar: modal. POST `/memberships/:id/freeze`. Anular: modal con motivo. POST `/memberships/:id/cancel` (solo admin).

Pagos (módulo 4)
- `/pagos` → `Pagos.html`. GET `/payments?q&from&to&method&registered_by&status&page`. Resumen del mes: GET `/payments/summary?month`.
- Registrar: panel lateral. POST `/payments`. Detalle: modal, GET `/payments/:id`. Anular: modal con motivo, POST `/payments/:id/void` (solo admin). Recibo: GET `/payments/:id/receipt.pdf`.

Clases (módulo 5)
- `/clases` → `Sesiones.html`. GET `/class-sessions?week`. Sesión extra: POST. Cancelar: POST `/class-sessions/:id/cancel`.
- `/clases/horario` → `Horario.html`. GET/POST/PATCH `/class-slots`. Solo admin.
- `/clases/:id/checkin` → `CheckIn.html` (tema oscuro, tablet). GET `/class-sessions/:id`, GET `/members?q` (búsqueda rápida), POST `/attendance` {session, member}, DELETE `/attendance/:id`.
- `/clases/asistencia` → pestaña de `Sesiones.html`. GET `/attendance?member&from&to`.

Movimientos (módulo 6)
- `/movimientos` → `Movimientos.html`. GET `/movements?q&category&active`. Panel lateral: POST / PATCH.

WODs (módulo 7)
- `/wods` → `WOD_Lista.html`. GET `/wods?week` o `/wods?q&benchmark&page`.
- `/wods/nuevo`, `/wods/:id/editar` → `WOD_Form.html`. POST / PATCH `/wods` (con sus `movements`).
- `/wods/:id` → `WOD_Detalle.html`. GET `/wods/:id`, GET `/wods/:id/leaderboard?level&sex`, GET `/wods/:id/results`.

Resultados (módulo 8)
- `/clases/:id/resultados` → `Resultados_Registro.html` (tema oscuro, tablet). GET `/class-sessions/:id/attendance`, GET/PUT `/results` {wod, member, …}. Validar los enviados por socios: POST `/results/:id/validate`.

Atleta (módulo 9)
- `/socios/:id/atleta` → `Atleta_Perfil.html` (pestaña Atleta de la ficha, con subpestañas Resumen · Medidas · RMs · Récords · Benchmarks). GET `/athletes/:id/metrics`, `/rms`, `/records`, `/benchmarks?wod`. POST `/athletes/:id/metrics`, POST `/athletes/:id/records` (manual).

Avisos (módulo 10)
- `/avisos/hoy` → `PorAvisarHoy.html`. GET `/notifications/today`. Abrir WhatsApp: GET `/notifications/:id/wa-link` (devuelve el `wa.me` y marca como enviado). Omitir: POST `/notifications/:id/skip` {reason}.
- `/avisos/reglas` → `Notif_Reglas.html`. GET/POST/PATCH `/notification-rules`. Pestaña Plantillas: `/notification-templates`. Solo admin edita.
- `/avisos/historial` → `Notif_Historial.html`. GET `/notifications?member&from&to&rule&channel&status&page`.

Sistema (módulos 11 a 14) — solo admin
- `/sistema/usuarios` → `Usuarios.html`. GET/POST/PATCH `/users`. Bloquear, reenviar enlace, cerrar sesiones.
- `/sistema/auditoria` → `Auditoria.html`. GET `/audit?from&to&user&entity&action&q&page`. Verificar cadena: POST `/audit/verify`.
- `/sistema/llaves` → `Llaves.html`. GET `/crypto/keys`, GET `/crypto/ops?page`, GET `/crypto/jobs`. Rotar: POST `/crypto/keys/:id/rotate` {reason, confirm:"ROTAR"}. Exportar CBOM: GET `/crypto/cbom`.
- `/sistema/configuracion` → `Config.html`. GET/PATCH `/settings` por sección (gym, hours, payment_methods, channels, classes, memberships, tv, privacy).

## Portal del socio (layout: una columna + menú inferior) — rol socio

- `/mi` → `Portal_Inicio.html`. GET `/me/summary`.
- `/mi/pagos` → `Portal_Pagos.html`. GET `/me/payments?page`. Recibo: GET `/me/payments/:id/receipt.pdf`.
- `/mi/wods` → `Portal_WODs.html`. GET `/me/results?page`, GET `/wods/today`. Enviar resultado: POST `/me/results` (queda "por validar").
- `/mi/progreso` → `Portal_Progreso.html`. GET `/me/records`, `/me/rms`, `/me/benchmarks`, `/me/metrics`. Registrar peso: POST `/me/metrics`.
- `/mi/datos` → `Portal_Datos.html`. GET/PATCH `/me`. Cambiar contraseña: POST `/me/password`.
- `/mi/avisos` → `Portal_Avisos.html`. GET `/me/notifications`, PATCH `/me/channels`, POST `/me/push-subscription` (web push).

## Permisos (lo que decide qué muestra el front)

- Admin: todo.
- Coach: ve y usa Inicio, Hoy, Socios (ver, crear, editar), Membresías y Pagos (vender y registrar; no anular), Clases, WODs, Movimientos, Atleta, Avisos. No ve Sistema ni Planes. El front oculta los botones; el API vuelve a verificar.
- Socio: solo `/mi/*`.
