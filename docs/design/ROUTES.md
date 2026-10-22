# Mapa de rutas del front

Cada ruta dice: pantalla de referencia en `screens/`, quién la ve, y qué pide al API (`/api/v1`). Las carpetas de React siguen los dominios del plan: `members`, `plans`, `memberships`, `payments`, `classes`, `wods`, `results`, `athletes`, `notifications`, `system`, `portal`.

Convenciones fijadas en el gate del 21 de octubre de 2026 (`docs/ddd/DECISIONES.md`): toda lista pagina con `limit` (1 a 200, por defecto 25) y `offset`, y responde `{ items, total, limit, offset }` (D2); los errores llegan como `{ error: { code, message, field?, existing_id? } }`; los nombres definitivos de ruta los fija `docs/openapi.json` (`docs/ddd/05_service_design.md`, sección 4).

## Acceso (sin sesión)

- `/login` → `Login.html` (S2-F3, `features/auth/pages/LoginPage.tsx`). POST `/auth/login` (cookie `apex_refresh` HttpOnly, `Path=/api/v1/auth`; el access queda solo en memoria); luego GET `/auth/me` para el nombre del gimnasio. Con `must_change_password` va a `/cambiar-clave`; si no, a `next` cuando `safeNext` lo acepta para el rol, o al inicio del rol: `/` (admin, coach) o `/mi` (socio). Errores: 401 siempre "Correo o contraseña incorrectos"; 429 con la cuenta atrás de `Retry-After` y el botón bloqueado; 403 de `Origin`, red y 5xx con mensaje genérico. Avisa al llegar si el cierre anterior no lo confirmó el servidor (H-1) o si la sesión venció. Bajo el logo dice "APEX" (`// DESIGN-GAP:`, S2-D50: `gym_name` solo llega con sesión). "Cerrar sesión" del TopBar: POST `/auth/logout` (por la cookie) y, pase lo que pase, limpia la sesión de todas las pestañas (`apex-auth`) y vuelve aquí.
- `/recuperar` → `Login.html` (tarjeta "Olvidé mi contraseña"; S2-F4a, `features/auth/pages/ForgotPage.tsx`). POST `/auth/forgot` y, pase lo que pase (204, 429, 5xx o red), el mismo mensaje: "Pídele al administrador tu enlace de recuperación." (`// DESIGN-GAP:`: en v0.1 forgot no envía correos, H-2 y S2-D36; el enlace lo da el admin).
- `/restablecer/:token` → `Login.html` (tarjeta "Nueva contraseña / Activar cuenta"; S2-F4a, `features/auth/pages/ResetPage.tsx`). Activa una cuenta nueva o recupera el acceso con el mismo enlace (S2-D18). Al llegar, `history.replaceState` deja la barra en `/restablecer` (recargar ya no tiene el token: hay que abrir el enlace otra vez). Contraseña de 12 a 128 caracteres con repetición. POST `/auth/reset` `{ token, new_password }`: 204 va a `/login` con el aviso "Tu contraseña quedó guardada. Inicia sesión con ella." (estado de la navegación, nunca la URL); 400 `invalid_token` o un token mal formado: "El enlace ya no es válido. Pide uno nuevo al administrador."; 422 `new_password` bajo el campo. El botón dice "Guardar contraseña" y no "Guardar y entrar" (`// DESIGN-GAP:`: el reset no abre sesión).
- `/tv?token=…` → `TV.html`. GET `/tv/today` cada 30 s. Sin sesión; el token lo da Configuración.
- `/cambiar-clave` → sin pantalla propia (`// DESIGN-GAP:`; usa la tarjeta "Nueva contraseña" de `Login.html`). Con sesión, cualquier rol. POST `/auth/me/password`. Toda ruta con sesión lleva aquí mientras `must_change_password` sea verdadero (S2-D18). Desde S2-F4a (`features/auth/pages/ChangePasswordPage.tsx`): contraseña actual, nueva (12 a 128) y repetición; el 200 `AccessTokenOut` deja el access nuevo en la sesión y lo reparte a las demás pestañas por `apex-auth` (S2-D37), y la página va al inicio del rol (`homeFor`). Tiene "Cerrar sesión". "Mi cuenta" del TopBar del panel abre el mismo cambio en un `SidePanel` con los datos de GET `/auth/me` (correo, rol, gimnasio) y al terminar avisa "Contraseña actualizada".

## Panel (layout: TopBar + SideNav) — admin y coach

Inicio
- `/` → `Inicio.html`. GET `/dashboard` (socios al día, por vencer, vencidos, ingresos del mes, asistencia semana, sesiones de hoy, por avisar, últimos movimientos). Hasta que exista GET `/dashboard` (Sprint 3), Inicio es mínima: saludo con el correo y accesos a Socios y, para admin, Planes, Usuarios y Configuración (`// DESIGN-GAP:`, S2-D25).

Socios (módulo 1)
- `/socios` → `Socios_Lista.html` (celular: `Socios_Movil.html`). GET `/members?q&status&plan&last_attendance&sort&limit&offset` (`last_attendance` solo desde v0.4; la lista trae `membership_status` resuelto y nunca datos cifrados). Desde S2-F6 (`features/members/pages/MembersListPage.tsx`, admin y coach): GET `/members?limit&offset&q&status&sort` (B8). La búsqueda ("Nombre, documento o teléfono"; documento y teléfono por valor exacto con el índice ciego, el nombre por una parte) vive en memoria con 300 ms de espera y nunca en la URL (S2-D41); en la URL quedan `status`, `sort` (`last_name` por defecto, `first_name`, `created_at`, con `-` descendente), `limit` y `offset`. Cambiar la búsqueda vuelve a la primera página y cancela la petición anterior. Chips "Todos" y "Dados de baja" (`status=deleted`, también para el coach, N-20). Columnas: socio (enlace a `/socios/:id`, que da NotFound hasta US-073, S2-D34), estado del socio (`StatusTag account`: Activo, Inactivo o Dado de baja) y membresía (vacía hasta US-071). "Nuevo socio" solo con `members.create`. Vacío con búsqueda: "No hay socios que coincidan con la búsqueda" con "Limpiar filtros"; sin socios: "Registrar el primer socio". Un 429 de la búsqueda dice cuánto esperar (`Retry-After`). `// DESIGN-GAP:` sin columnas de teléfono, plan, vence, última asistencia ni "Acción", sin documento enmascarado bajo el nombre (N-01), sin chips por estado de membresía ni conteos (US-071), sin filtros de plan y asistencia y sin "Exportar" (US-076).
- `/socios/nuevo` → `Socio_Form.html`. POST `/members` (+ POST `/members/:id/attachments` para foto y autorización). Desde S2-F6 (`features/members/pages/MemberFormPage.tsx` y `components/MemberFormFields.tsx`, admin y coach con `members.create`): secciones Identificación (nombres, apellidos, tipo de documento CC, CE, TI o Pasaporte, número, sexo opcional y fecha de nacimiento), Contacto (teléfono y correo), Contacto de emergencia (nombre, parentesco y teléfono; si se llena, nombre y teléfono) y Autorización de datos (Ley 1581): la casilla "El socio autorizó el tratamiento de datos", sin marcar de entrada, envía `data_consent: true` (o `false`); el servidor fija la fecha y el cliente nunca envía `data_consent_at` (M-4). No hay campo de notas (M-5). Las reglas del cliente son las de `MemberCreate`: documento de 3 a 30, fecha no futura en hora de Bogotá, correo con forma y teléfono con al menos 7 dígitos. 422 con `field` bajo su campo (incluido L-3, un documento que se normaliza a vacío), 409 `member_document_duplicated` bajo el documento con "Ver socio existente" a `/socios/{existing_id}` (nunca `/socios?q=<documento>`), 429 con la espera. El 201 vuelve a `/socios` con "Socio registrado: <nombre>." y, si el api devolvió `data_consent_missing`, "Falta la autorización de tratamiento de datos." (aviso por el estado de la navegación, que se limpia al mostrarlo). Nada del formulario se guarda en el navegador. `// DESIGN-GAP:` sin foto, firma ni documento firmado (v0.3), sin "Acceso al portal" (v1.0), sin unidad de cargas (v0.6), sin observaciones de salud, nombre en dos campos, sexo y teléfono opcionales, y sin "Guardar y vender membresía" (Sprint 3).
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
- `/sistema/usuarios` → `Usuarios.html`. Desde S2-F4a (`features/system/pages/UsersPage.tsx`): GET `/users?q&role&status&limit&offset` (orden por correo del api; sin `sort`) con correo, rol, `StatusTag account` (Activo, Pendiente de activación, Bloqueado, Inactivo, Dado de baja), último acceso en hora de Bogotá y sesiones abiertas. La búsqueda vive en memoria con 300 ms de espera y nunca en la URL (S2-D41); en la URL quedan `role`, `status`, `limit` y `offset`. Alta en panel lateral "Nuevo usuario del equipo" (correo y rol Coach o Admin): POST `/users`; el 201 muestra el enlace de activación en solo lectura con "Copiar" y "Entrega este enlace por un medio seguro; vence en 72 horas", y al cerrar el panel el enlace se descarta (L-7); el 409 `email_taken` va bajo el correo con enlace al usuario existente (`?usuario=<id>`, donde S2-F4b abre su edición). Desde S2-F4b (`EditUserPanel`, `LinkModal`, `UserRowActions`, `useUserActions`): `?usuario=<id>` abre el panel "Editar usuario" (GET `/users/:id`, incluye bajas, que se ven pero no se editan; correo y rol Coach o Admin; PATCH `/users/:id` solo con lo que cambió; 409 `email_taken` bajo el correo con enlace al existente, 409 `last_admin` como mensaje general) y al cerrarlo se quita de la URL sin tocar los filtros. Columna "Acción" por fila: "Editar" (enlace a `?usuario=<id>`), "Cerrar sesiones (N)" (POST `/users/:id/revoke-sessions`; el aviso usa `{revoked}`; sobre la propia cuenta termina en `clearSession()` y `/login`, S2-D37), "Reenviar enlace" (`LinkModal`: POST `/users/:id/resend-link`, única forma de volver a obtener el enlace; "Activación, vence en 72 horas" o "Recuperación, vence en 1 hora" con la hora de Bogotá; `gcTime: 0` y descarte al cerrar, L-7; oculto en la propia fila, bloqueados, dados de baja y admins activos, L-13), "Bloquear" o "Desbloquear" (POST `/users/:id/lock`, `/unlock`) y "Dar de baja" (DELETE `/users/:id`), con `ConfirmModal` y los 409 explicados por código; "Dar de baja" y "Bloquear" no aparecen en la propia fila. `// DESIGN-GAP:` sin columna de nombre (S2-D17), rol como texto, sin filtro "Equipo", acciones del ciclo de vida en la fila en vez del panel (blueprint F4b) y sin la tabla de permisos por rol.
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
