# Brechas entre el diseño del front y el plan del backend

Fecha del análisis: 20 de octubre de 2026.
Documentos comparados: `CLAUDE.md`, `docs/PLAN.md` (plan backend por versiones) y `docs/design/` (DESIGN.md, ROUTES.md, SCREENS-INDEX.md, 37 pantallas).

Este archivo es la lista de trabajo para alinear los tres documentos. Cada punto se cierra editando el documento que corresponda; cuando el backend exporte `docs/openapi.json` (Tarea 12), `ROUTES.md` se reescribe a partir de ese contrato.

## 1. Decisiones que bloquean (resolver antes de codificar)

### D1. Quién construye el front
- `CLAUDE.md` (Alcance) dice que Claude Code no crea ni rediseña el front; en este repo solo se integra.
- La entrega de diseño (`_entregas/2026-10-20-diseno-handoff/README-handoff.md`) dice lo contrario: "Abre Claude Code en el repo y pídele: construye el layout del panel y la pantalla /socios siguiendo docs/design".
- Opciones: (a) el front lo construye otro flujo y aquí solo se integra en `web/`; (b) Claude Code también construye el front en este repo. Si es (b), hay que reescribir el párrafo de Alcance de `CLAUDE.md`.
- La sección "Front: diseño aprobado" ya se agregó a `CLAUDE.md` con redacción neutra ("quien construya el front"), así sirve en ambos casos.

### D2. Convención de paginación
- `CLAUDE.md` regla de datos 6: `limit` y `offset`, máximo 200.
- `DESIGN.md` (regla 2 y "Qué NO hacer") y `ROUTES.md`: `page` y `page_size`.
- Recomendación: mantener `limit`/`offset` en el API (es la regla del archivo que manda) y cambiar las dos menciones en `DESIGN.md` y `ROUTES.md`. El componente Pagination calcula `offset = (página - 1) * limit`. Tamaños de página del diseño: 25, 50, 100.

### D3. Carpeta del front
- `CLAUDE.md`: `web/`. Entrega de diseño: `frontend/public/brand/`.
- Resuelto: `web/`. Ya aplicado en la sección nueva de `CLAUDE.md`. Los logos van a `web/public/brand/`.

### D4. Orden de construcción
- El front propone: login, socios, planes, membresías y pagos, inicio, clases y check-in, movimientos, WODs y resultados, atleta, avisos, sistema, TV, portal.
- El backend entrega: v0.1 socios, planes, membresías, pagos, auditoría, usuarios; v0.2 avisos; v0.3 llaves con OpenBao y adjuntos; v0.4 clases; v0.5 WODs, resultados, TV; v0.6 atleta; v1.0 portal.
- Diferencia: el front pone clases antes que avisos; el backend al revés. Recomendación: el front sigue el orden de versiones del backend (ver sección 6). La pantalla Inicio se construye en v0.1 con los KPIs que existan y se completa en cada versión.

### D5. Contrato de "vender membresía"
- Front (`Membresia_Vender.html`, ROUTES): una sola llamada `POST /memberships` que crea la membresía y el primer pago.
- Backend (Tareas 6 y 7): `POST /members/{id}/memberships` crea la membresía; `POST /memberships/{id}/payments` registra el pago; la activación ocurre por el evento `PaymentRegistered` cuando los pagos cubren `agreed_price_cop`.
- Recomendación: mantener los dos endpoints del backend y agregar en el service de memberships una operación `sell(member_id, plan_id, first_payment)` que ejecute ambos en una transacción, expuesta como `POST /members/{id}/memberships` con `first_payment` opcional en el cuerpo. El front hace una llamada; el backend conserva pagos inmutables y el evento.

## 2. Pantallas que necesitan endpoints o módulos que el plan no tiene

### Módulo `settings` (pantalla `Config.html`)
- Front: `GET/PATCH /settings` por sección: gym, hours, payment_methods, channels, classes, memberships, tv, privacy.
- Plan: no existe ningún módulo de configuración.
- Impacto: el token de la TV (v0.5), los medios de pago configurables (v0.1), los canales de aviso (v0.2) y el horario del gimnasio dependen de esto.
- Propuesta: módulo `settings` en v0.1 con una tabla clave-valor por sección (JSON validado con Pydantic por sección), `__audited__ = True`, solo admin. Secciones nuevas se agregan en la versión que las necesita.

### API de llaves (pantalla `Llaves.html`)
- Front: `GET /crypto/keys`, `GET /crypto/ops?page`, `GET /crypto/jobs`, `POST /crypto/keys/:id/rotate {reason, confirm:"ROTAR"}`, `GET /crypto/cbom`.
- Plan: rotación y CBOM solo como comandos de `cli.py` (`rotate-key` en Tarea 2, `cbom` en v1.0). No hay router.
- Propuesta: router `core/crypto/router.py` solo admin, en v0.3 junto con OpenBao. La rotación por lotes de la Tarea 2 debe guardar su progreso en una tabla `crypto_jobs` para que `GET /crypto/jobs` tenga qué mostrar. CBOM se adelanta de v1.0 a v0.3 o la pantalla muestra el botón deshabilitado hasta entonces.

### Recuperación y activación de cuenta (pantalla `Login.html`, tarjetas 2 y 3; pantalla `Usuarios.html`)
- Front: `POST /auth/forgot`, `POST /auth/reset` (sirve para "nueva contraseña" y "activar cuenta"), "reenviar enlace", "cerrar sesiones" por usuario.
- Plan (Tarea 3): login, refresh, logout, me, CRUD de usuarios. Nada de tokens de un solo uso ni de correo.
- Propuesta: tabla `auth.one_time_tokens` (hash, user_id, purpose: reset o activate, expires_at, used_at) y los dos endpoints en Tarea 3. El envío del enlace por correo necesita el `EmailChannel` de v0.2; en v0.1 el admin copia el enlace desde la pantalla de usuarios. "Cerrar sesiones" es revocar todos los refresh tokens del usuario: `POST /users/{id}/revoke-sessions`.

### Tablero de inicio (pantalla `Inicio.html`)
- Front: `GET /dashboard` con socios al día, por vencer, vencidos, ingresos del mes, asistencia de la semana, sesiones de hoy, por avisar hoy, últimos movimientos.
- Plan: solo `GET /memberships/summary` (Tarea 6) y `GET /payments/report?month=` (Tarea 7).
- Propuesta: endpoint `GET /dashboard` en un módulo liviano `dashboard` que solo llame a los services de los otros módulos (regla de módulos 2). Cada campo se agrega en la versión que lo hace posible: membresías y pagos en v0.1, por avisar en v0.2, asistencia y sesiones en v0.4, WOD de hoy en v0.5. Hasta entonces el campo viene `null` y el front muestra la tarjeta vacía.

### Recibo en PDF (pantallas `Pagos.html`, `Portal_Pagos.html`)
- Front: `GET /payments/:id/receipt.pdf` y `GET /me/payments/:id/receipt.pdf`.
- Plan: no existe.
- Propuesta: v0.1 o v0.2. Necesita una librería de PDF con licencia permitida: `reportlab` (BSD) sirve; `fpdf2` es LGPL y está prohibida. Usa el logo `apex-logo-light-bg.png`. Cada descarga se audita.

### Exportar listas (pantallas `Socios_Lista.html`, `Pagos.html`)
- Front: botón "Exportar".
- Plan: no existe.
- Propuesta: `GET /members/export` y `GET /payments/export` en CSV, solo admin, con auditoría obligatoria porque descifra datos personales en masa. Si no se quiere en v0.1, quitar el botón de la pantalla.

### Detalles menores de pagos (Tarea 7)
- Front pide `GET /payments/:id` (modal de detalle), filtro `registered_by`, filtro `status` (anulado o no) y búsqueda `q`. Agregar a la Tarea 7.
- Front usa `GET /payments/summary?month`; plan usa `GET /payments/report?month=`. Elegir un nombre.

### Auditoría (pantalla `Auditoria.html`)
- Front: `POST /audit/verify`. Plan (Tarea 8): solo `cli verify-audit`.
- Propuesta: exponer la misma función como endpoint admin; sobre tablas grandes correr en segundo plano y devolver el resultado de la última verificación.

### Avisos (v0.2)
- Front pide `POST /notifications/:id/skip {reason}` y que `GET /notifications/:id/wa-link` marque el aviso como enviado. Precisar ambos en la descripción de v0.2.

### Resultados y portal (v0.5 y v1.0)
- `POST /results/:id/validate` (coach valida lo que envió el socio): v1.0 menciona el estado `pending` pero no el endpoint. Agregarlo.
- Portal: `POST /me/password`, `PATCH /me` (definir qué campos puede editar el socio: teléfono, correo, contacto de emergencia; nunca documento), `PATCH /me/channels`, `GET /me/summary`. Precisar en v1.0.

## 3. Datos que el diseño muestra y el modelo no tiene

- `members.sex`: el leaderboard de `WOD_Detalle.html` filtra por sexo (v0.5). Agregar a la tabla desde la Tarea 4 para no hacer una migración con datos después. Valores: `f`, `m`, `x`, opcional.
- Foto del socio y autorización de tratamiento de datos (`Socio_Form.html`): los archivos van por `attachments` (v0.3). La autorización además necesita una bandera en `members` (`data_consent_at`, `data_consent_version`) para poder consultarla sin abrir el adjunto. La sección `privacy` de Config guarda la versión vigente del texto.
- `auth.users.member_id`: el portal (v1.0) filtra "lo mío" por el `member_id` del token, pero la tabla `users` de la Tarea 3 no tiene esa columna. Agregarla nula desde v0.1; obligatoria cuando `role = member`.
- Medios de pago: el plan usa el enum fijo `cash | nequi | breb`; `Config.html` permite configurar medios. Decidir: enum fijo en código (más simple) o lista en `settings.payment_methods`. Recomendación: enum fijo en v0.1; si el gimnasio pide otro medio, se agrega con migración.
- Horario semanal: front `class-slots`, plan `schedule_templates`. Mismo concepto, unificar el nombre (recomendación: `class_slots`, es el que usa el diseño).
- RMs y récords: front separa `/athletes/:id/rms` y `/athletes/:id/records`; plan solo tiene `personal_records` (manuales y derivados). Definir: un RM es un `personal_record` con `kind = rm` y `movement_id`; un récord de benchmark es `kind = benchmark` con `wod_id`. Un solo endpoint con filtro `kind`.
- Filtros de la lista de socios: ROUTES pide `plan` y `last_attendance`; Tarea 4 solo tiene búsqueda y estado. `plan` se puede en v0.1 (consulta vía service de memberships); `last_attendance` solo desde v0.4.
- Estados derivados de socio en los chips ("Al día", "Por vencer", "Vencidos", "Congelados", "Sin membresía", "Dados de baja"): el socio no tiene estado de membresía propio. Definir en el service de members cómo se calcula (última membresía no cancelada) y exponerlo como `membership_status` en la respuesta de la lista, sin join cruzado fuera del service.

## 4. Mismo concepto, nombre de ruta distinto

Para cada par, el contrato final lo fija el backend en `docs/openapi.json`; luego se corrige `ROUTES.md`.

- Membresías de un socio: front `GET /members/:id/memberships`; plan `GET /memberships?member=`.
- Historial de un registro: front `GET /members/:id/audit`; plan `GET /audit?record=`.
- Registrar pago: front `POST /payments` (panel lateral que elige la membresía); plan `POST /memberships/{id}/payments`.
- Resumen de pagos: front `/payments/summary?month`; plan `/payments/report?month=`.
- Vencimientos: front `ends_from` y `ends_to`; plan "vence antes de".
- Renovar: front reutiliza vender con `?renovar=1` y `POST /memberships`; plan `POST /memberships/{id}/renew`.
- Asistencia por sesión: front `GET /class-sessions/:id/attendance`; plan solo describe la tabla.

Recomendación general: recursos anidados para crear (`POST /members/{id}/memberships`, `POST /memberships/{id}/payments`) y colecciones planas con filtros para listar (`GET /memberships?member=`, `GET /payments?member=`). Es lo que ya hace el plan; el front se adapta.

## 5. Permisos que el plan debe declarar

- `ROUTES.md` fija: coach vende membresías y registra pagos pero no anula; no da de baja socios; no ve Planes ni Sistema. Socio solo `/mi/*`.
- En el plan: Tarea 5 ya dice "solo admin" para planes. Tareas 4, 6 y 7 no dicen quién puede `DELETE /members/{id}`, `POST /memberships/{id}/cancel` ni `POST /payments/{id}/void`. Agregar `require_role("admin")` explícito en esos tres.
- Token de dispositivo de la TV: lo emite Configuración; depende del módulo `settings` (sección 2).

## 6. Trazabilidad: qué pantalla se puede construir en cada versión del backend

- v0.1: `Login` (solo la tarjeta de acceso), `Inicio` (KPIs de membresías y pagos; el resto vacío), `Socios_Lista`, `Socios_Movil`, `Socio_Ficha` (pestañas Membresías, Pagos, Historial), `Socio_Form` (sin foto ni adjuntos), `Planes`, `Membresias`, `Membresia_Vender`, `Pagos` (sin recibo PDF si se pospone), `Usuarios` (CRUD; sin reenviar enlace si no hay correo), `Auditoria`, `Config` (si se acepta el módulo `settings` en v0.1).
- v0.2: `PorAvisarHoy`, `Notif_Reglas`, `Notif_Historial`, tarjetas de recuperar y activar cuenta de `Login`, pestaña Avisos de la ficha.
- v0.3: `Llaves` (si se crea el router de crypto), foto y adjuntos en `Socio_Form` y `Socio_Ficha`.
- v0.4: `Sesiones`, `Horario`, `CheckIn`, pestaña Asistencia de la ficha, KPIs de asistencia en `Inicio`.
- v0.5: `Movimientos`, `WOD_Lista`, `WOD_Form`, `WOD_Detalle`, `Resultados_Registro`, `TV`, pestaña Resultados de la ficha.
- v0.6: `Atleta_Perfil`, pestaña Atleta de la ficha.
- v1.0: `Portal_Inicio`, `Portal_Pagos`, `Portal_WODs`, `Portal_Progreso`, `Portal_Datos`, `Portal_Avisos`, validación de resultados enviados por socios.
- No se implementan (son referencia): `Mapa`, `P_Lista`, `P_Ficha`, `P_Formulario`.

## 7. Licencias que faltan en la lista de `CLAUDE.md`

- Iconos Lucide: licencia ISC. Fuentes Michroma y Titillium Web: SIL Open Font License 1.1. Ninguna de las dos está en la lista permitida (MIT, BSD, Apache 2.0, PostgreSQL). Son permisivas; agregar ISC y OFL 1.1 a la lista para que la regla sea exacta.
- Dependencias del front que el diseño da por hechas: React Router, TanStack Query, React Hook Form, Zod, Vite, Tailwind o CSS modules. Todas MIT.
- `pip-licenses` solo revisa Python; el front necesita su propio chequeo (`license-checker` o similar) en CI.

## 8. Observaciones sobre los archivos de diseño

- 37 pantallas: 36 con versión clara y oscura, más `TV` solo en oscuro. Total 73 archivos HTML en `screens/`.
- Se corrigieron 4 enlaces que apuntaban a `TV.dark.html` (no existe) en `Config.dark.html`, `Inicio.dark.html`, `Mapa.dark.html` y `WOD_Detalle.dark.html`; ahora apuntan a `TV.html`. No queda ningún enlace ni imagen rota.
- Los HTML usan colores hex literales en su propio `<style>`: son wireframes de referencia, no código a copiar. En React solo se usan las variables de `tokens.css`.
- Las fuentes se cargan de Google Fonts; `DESIGN.md` ya indica el respaldo local en `public/fonts/` si el gimnasio no tiene internet estable.
- `prototipo.html` pesa 3,1 MB porque incrusta imágenes en base64. Es solo para revisar el diseño; no se incluye en `web/` ni en ninguna imagen Docker.
- `tokens.json` tiene `"fonts": []` vacío; las familias están en `families`. Es informativo, no afecta.
- Los textos de las pantallas contienen datos de ejemplo (nombres, cifras, "[NOMBRE DEL GIMNASIO]"). Ninguno es dato real.
