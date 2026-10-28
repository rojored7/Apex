# Brechas entre el diseño del front y el plan del backend

Fecha del análisis: 20 de octubre de 2026.
Documentos comparados: `CLAUDE.md`, `docs/PLAN.md` (plan backend por versiones) y `docs/design/` (DESIGN.md, ROUTES.md, SCREENS-INDEX.md, 37 pantallas).

Este archivo es la lista de trabajo para alinear los tres documentos. Cada punto se cierra editando el documento que corresponda; cuando el backend exporte `docs/openapi.json` (US-021), `ROUTES.md` se reescribe a partir de ese contrato.

**Estado al 21 de octubre de 2026.** Las cinco decisiones de la sección 1 se aprobaron en el gate humano (`docs/ddd/GATE.md`) y quedaron registradas en `docs/ddd/DECISIONES.md`. Los puntos cerrados llevan una línea **Resuelto** con la decisión que los cierra; el detalle vive en `docs/ddd/02_domain_model.md` y `docs/ddd/05_service_design.md`.

## 1. Decisiones que bloquean (resolver antes de codificar)

### D1. Quién construye el front
- **Resuelto (gate del 21 de octubre de 2026):** opción (b). Claude Code construye el front en `web/` dentro de este flujo. El "Alcance" de `CLAUDE.md` se reescribió.
- `CLAUDE.md` (Alcance) dice que Claude Code no crea ni rediseña el front; en este repo solo se integra.
- La entrega de diseño (`_entregas/2026-10-20-diseno-handoff/README-handoff.md`) dice lo contrario: "Abre Claude Code en el repo y pídele: construye el layout del panel y la pantalla /socios siguiendo docs/design".
- Opciones: (a) el front lo construye otro flujo y aquí solo se integra en `web/`; (b) Claude Code también construye el front en este repo. Si es (b), hay que reescribir el párrafo de Alcance de `CLAUDE.md`.
- La sección "Front: diseño aprobado" ya se agregó a `CLAUDE.md` con redacción neutra ("quien construya el front"), así sirve en ambos casos.

### D2. Convención de paginación
- **Resuelto (gate del 21 de octubre de 2026):** `limit`/`offset`, máximo 200. `DESIGN.md` y `ROUTES.md` corregidos; `Pagination` calcula `offset = (página - 1) * limit`.
- `CLAUDE.md` regla de datos 6: `limit` y `offset`, máximo 200.
- `DESIGN.md` (regla 2 y "Qué NO hacer") y `ROUTES.md`: `page` y `page_size`.
- Recomendación: mantener `limit`/`offset` en el API (es la regla del archivo que manda) y cambiar las dos menciones en `DESIGN.md` y `ROUTES.md`. El componente Pagination calcula `offset = (página - 1) * limit`. Tamaños de página del diseño: 25, 50, 100.

### D3. Carpeta del front
- `CLAUDE.md`: `web/`. Entrega de diseño: `frontend/public/brand/`.
- Resuelto: `web/`. Ya aplicado en la sección nueva de `CLAUDE.md`. Los logos van a `web/public/brand/`.

### D4. Orden de construcción
- **Resuelto (gate del 21 de octubre de 2026):** el front sigue el orden de versiones del backend; `docs/ddd/09_sprint_plan/` fija qué pantallas entran en cada sprint.
- El front propone: login, socios, planes, membresías y pagos, inicio, clases y check-in, movimientos, WODs y resultados, atleta, avisos, sistema, TV, portal.
- El backend entrega: v0.1 socios, planes, membresías, pagos, auditoría, usuarios; v0.2 avisos; v0.3 llaves con OpenBao y adjuntos; v0.4 clases; v0.5 WODs, resultados, TV; v0.6 atleta; v1.0 portal.
- Diferencia: el front pone clases antes que avisos; el backend al revés. Recomendación: el front sigue el orden de versiones del backend (ver sección 6). La pantalla Inicio se construye en v0.1 con los KPIs que existan y se completa en cada versión.

### D5. Contrato de "vender membresía"
- **Resuelto (gate del 21 de octubre de 2026):** un solo endpoint `POST /members/{id}/memberships` con `first_payment` opcional y `renew: true` para renovar (operación `sell`); el pago sigue inmutable y la activación ocurre por evento. No existe `POST /memberships/{id}/renew` (Q2).
- Front (`Membresia_Vender.html`, ROUTES): una sola llamada `POST /memberships` que crea la membresía y el primer pago.
- Backend (Tareas 6 y 7): `POST /members/{id}/memberships` crea la membresía; `POST /memberships/{id}/payments` registra el pago; la activación ocurre por el evento `PaymentRegistered` cuando los pagos cubren `agreed_price_cop`.
- Recomendación: mantener los dos endpoints del backend y agregar en el service de memberships una operación `sell(member_id, plan_id, first_payment)` que ejecute ambos en una transacción, expuesta como `POST /members/{id}/memberships` con `first_payment` opcional en el cuerpo. El front hace una llamada; el backend conserva pagos inmutables y el evento.

## 2. Pantallas que necesitan endpoints o módulos que el plan no tiene

### Módulo `settings` (pantalla `Config.html`)
- **Cierre Sprint 2:** implementado en S2-B1 (`0005_settings`, `settings.service`, rutas `gym`, `privacy` y `memberships`) y en S2-F5 (pestañas). Las demás secciones (`hours`, `payment_methods`, `channels`, `classes`, `tv`) siguen fuera y responden 404 `section_not_available` (S2-D15).
- **Resuelto (gate del 21 de octubre de 2026):** módulo `settings` en v0.1 (EP-05), secciones y rangos en Q11 y N-18; `channels` llega en v0.2 sin secretos (Q12).
- Front: `GET/PATCH /settings` por sección: gym, hours, payment_methods, channels, classes, memberships, tv, privacy.
- Plan: no existe ningún módulo de configuración.
- Impacto: el token de la TV (v0.5), los medios de pago configurables (v0.1), los canales de aviso (v0.2) y el horario del gimnasio dependen de esto.
- Propuesta: módulo `settings` en v0.1 con una tabla clave-valor por sección (JSON validado con Pydantic por sección), `__audited__ = True`, solo admin. Secciones nuevas se agregan en la versión que las necesita.

### API de llaves (pantalla `Llaves.html`)
- **Resuelto (gate del 21 de octubre de 2026):** router `core/crypto/router.py` en v0.3 (EP-18); `crypto_jobs` existe desde v0.1; CBOM adelantado a v0.3 (Q26), CycloneDX en v1.0.
- Front: `GET /crypto/keys`, `GET /crypto/ops?page`, `GET /crypto/jobs`, `POST /crypto/keys/:id/rotate {reason, confirm:"ROTAR"}`, `GET /crypto/cbom`.
- Plan: rotación y CBOM solo como comandos de `cli.py` (`rotate-key` en Tarea 2, `cbom` en v1.0). No hay router.
- Propuesta: router `core/crypto/router.py` solo admin, en v0.3 junto con OpenBao. La rotación por lotes de la Tarea 2 debe guardar su progreso en una tabla `crypto_jobs` para que `GET /crypto/jobs` tenga qué mostrar. CBOM se adelanta de v1.0 a v0.3 o la pantalla muestra el botón deshabilitado hasta entonces.

### Recuperación y activación de cuenta (pantalla `Login.html`, tarjetas 2 y 3; pantalla `Usuarios.html`)
- **Cierre Sprint 2:** API en S2-B4 (`forgot` sin escritura en v0.1, `reset`, `resend-link`) y S2-B5 (`revoke-sessions`); pantallas en S2-F4a y S2-F4b. El envío del correo sigue sin canal hasta US-131 (Sprint 5).
- **Resuelto (gate del 21 de octubre de 2026):** `auth.one_time_tokens`, `POST /auth/forgot`, `POST /auth/reset`, `POST /users/{id}/resend-link` (única ruta para el enlace, N-12) y `POST /users/{id}/revoke-sessions`, todo en v0.1; el correo llega en v0.2.
- Front: `POST /auth/forgot`, `POST /auth/reset` (sirve para "nueva contraseña" y "activar cuenta"), "reenviar enlace", "cerrar sesiones" por usuario.
- Plan (Tarea 3): login, refresh, logout, me, CRUD de usuarios. Nada de tokens de un solo uso ni de correo.
- Propuesta: tabla `auth.one_time_tokens` (hash, user_id, purpose: reset o activate, expires_at, used_at) y los dos endpoints en Tarea 3. El envío del enlace por correo necesita el `EmailChannel` de v0.2; en v0.1 el admin copia el enlace desde la pantalla de usuarios. "Cerrar sesiones" es revocar todos los refresh tokens del usuario: `POST /users/{id}/revoke-sessions`.

### Tablero de inicio (pantalla `Inicio.html`)
- **Cierre Sprint 2: parcial.** S2-F2 entrega `InicioPage` mínima con `// DESIGN-GAP:`. El tablero con `GET /dashboard` es US-108 del Sprint 4A (`SPRINT-04A.md`, S4A-B8), no del Sprint 3 como decía S2-D25.
- **Resuelto (gate del 21 de octubre de 2026):** módulo `dashboard` en v0.1 (EP-07); cada campo se llena en su versión y hasta entonces viene `null`; "últimos movimientos" sale de la auditoría (Q10).
- Front: `GET /dashboard` con socios al día, por vencer, vencidos, ingresos del mes, asistencia de la semana, sesiones de hoy, por avisar hoy, últimos movimientos.
- Plan: solo `GET /memberships/summary` (Tarea 6) y `GET /payments/report?month=` (Tarea 7).
- Propuesta: endpoint `GET /dashboard` en un módulo liviano `dashboard` que solo llame a los services de los otros módulos (regla de módulos 2). Cada campo se agrega en la versión que lo hace posible: membresías y pagos en v0.1, por avisar en v0.2, asistencia y sesiones en v0.4, WOD de hoy en v0.5. Hasta entonces el campo viene `null` y el front muestra la tarjeta vacía.

### Recibo en PDF (pantallas `Pagos.html`, `Portal_Pagos.html`)
- **Resuelto (gate del 21 de octubre de 2026):** v0.2 con `reportlab` (P4); cada descarga se audita como `download` (N-08).
- Front: `GET /payments/:id/receipt.pdf` y `GET /me/payments/:id/receipt.pdf`.
- Plan: no existe.
- Propuesta: v0.1 o v0.2. Necesita una librería de PDF con licencia permitida: `reportlab` (BSD) sirve; `fpdf2` es LGPL y está prohibida. Usa el logo `apex-logo-light-bg.png`. Cada descarga se audita.

### Exportar listas (pantallas `Socios_Lista.html`, `Pagos.html`)
- **Resuelto (gate del 21 de octubre de 2026):** v0.2, CSV con `;` y BOM, solo admin, auditado con el filtro usado (Q15, N-29).
- Front: botón "Exportar".
- Plan: no existe.
- Propuesta: `GET /members/export` y `GET /payments/export` en CSV, solo admin, con auditoría obligatoria porque descifra datos personales en masa. Si no se quiere en v0.1, quitar el botón de la pantalla.

### Detalles menores de pagos (Tarea 7)
- **Resuelto (gate del 21 de octubre de 2026):** `GET /payments/{id}`, filtros `q`, `registered_by` y `voided`, `GET /payments/summary?month=` (ese nombre) y `GET /payments/methods` (US-056).
- Front pide `GET /payments/:id` (modal de detalle), filtro `registered_by`, filtro `status` (anulado o no) y búsqueda `q`. Agregar a la Tarea 7.
- Front usa `GET /payments/summary?month`; plan usa `GET /payments/report?month=`. Elegir un nombre.

### Auditoría (pantalla `Auditoria.html`)
- **Resuelto (gate del 21 de octubre de 2026):** `POST /audit/verify` y `GET /audit/verify/last`; cada verificación se persiste en `audit.verifications` (N-30).
- Front: `POST /audit/verify`. Plan (Tarea 8): solo `cli verify-audit`.
- Propuesta: exponer la misma función como endpoint admin; sobre tablas grandes correr en segundo plano y devolver el resultado de la última verificación.

### Avisos (v0.2)
- **Resuelto (gate del 21 de octubre de 2026):** ambos endpoints precisados en `docs/PLAN.md` v0.2 y en EP-14.
- Front pide `POST /notifications/:id/skip {reason}` y que `GET /notifications/:id/wa-link` marque el aviso como enviado. Precisar ambos en la descripción de v0.2.

### Resultados y portal (v0.5 y v1.0)
- **Resuelto (gate del 21 de octubre de 2026):** `POST /results/{id}/validate` en v0.5; en el portal el socio edita teléfono, correo, contacto de emergencia, preferencias de canal y contraseña, nunca documento, nombres, sexo ni fecha de nacimiento (Q24).
- `POST /results/:id/validate` (coach valida lo que envió el socio): v1.0 menciona el estado `pending` pero no el endpoint. Agregarlo.
- Portal: `POST /me/password`, `PATCH /me` (definir qué campos puede editar el socio: teléfono, correo, contacto de emergencia; nunca documento), `PATCH /me/channels`, `GET /me/summary`. Precisar en v1.0.

## 3. Datos que el diseño muestra y el modelo no tiene

- **Resuelto:** `members.sex` entra en la migración de socios de v0.1. Detalle original: el leaderboard de `WOD_Detalle.html` filtra por sexo (v0.5). Agregar a la tabla desde la Tarea 4 para no hacer una migración con datos después. Valores: `f`, `m`, `x`, opcional.
- **Resuelto:** `data_consent_at` y `data_consent_version` desde v0.1, nulos para socios anteriores (Q16). Detalle original: foto del socio y autorización de tratamiento de datos (`Socio_Form.html`): los archivos van por `attachments` (v0.3). La autorización además necesita una bandera en `members` (`data_consent_at`, `data_consent_version`) para poder consultarla sin abrir el adjunto. La sección `privacy` de Config guarda la versión vigente del texto.
- **Resuelto:** `auth.users.member_id` nulo desde v0.1 y obligatorio con `role = member`. Detalle original: el portal (v1.0) filtra "lo mío" por el `member_id` del token, pero la tabla `users` de la Tarea 3 no tiene esa columna. Agregarla nula desde v0.1; obligatoria cuando `role = member`.
- **Resuelto:** enum fijo en v0.1 (S8), etiquetas desde Settings. Detalle original: el plan usa el enum fijo `cash | nequi | breb`; `Config.html` permite configurar medios. Decidir: enum fijo en código (más simple) o lista en `settings.payment_methods`. Recomendación: enum fijo en v0.1; si el gimnasio pide otro medio, se agrega con migración.
- **Resuelto:** `class_slots`. Detalle original: front `class-slots`, plan `schedule_templates`. Mismo concepto, unificar el nombre (recomendación: `class_slots`, es el que usa el diseño).
- **Resuelto:** `personal_records.kind` (`rm` con `movement_id`, `benchmark` con `benchmark_id`, N-46), un endpoint con filtro `kind`. Detalle original: front separa `/athletes/:id/rms` y `/athletes/:id/records`; plan solo tiene `personal_records` (manuales y derivados). Definir: un RM es un `personal_record` con `kind = rm` y `movement_id`; un récord de benchmark es `kind = benchmark` con `wod_id`. Un solo endpoint con filtro `kind`.
- **Resuelto:** `plan` en v0.1 vía `status_for` (G-04); `last_attendance` en v0.4 con import perezoso (G-10). Detalle original: ROUTES pide `plan` y `last_attendance`; Tarea 4 solo tiene búsqueda y estado. `plan` se puede en v0.1 (consulta vía service de memberships); `last_attendance` solo desde v0.4.
- **Resuelto:** `membership_status` lo calcula `memberships.service.status_for` y se expone en la lista; chips con "Pendiente de pago" (Q3) y "Dados de baja" visibles para admin y coach (N-20). Detalle original: estados derivados de socio en los chips ("Al día", "Por vencer", "Vencidos", "Congelados", "Sin membresía", "Dados de baja"): el socio no tiene estado de membresía propio. Definir en el service de members cómo se calcula (última membresía no cancelada) y exponerlo como `membership_status` en la respuesta de la lista, sin join cruzado fuera del service.

## 4. Mismo concepto, nombre de ruta distinto

Para cada par, el contrato final lo fija el backend en `docs/openapi.json`; luego se corrige `ROUTES.md`.

- **Resuelto (gate del 21 de octubre de 2026):** el contrato quedó fijado en `docs/ddd/05_service_design.md`, sección 4, y `ROUTES.md` ya usa esos nombres: recursos anidados para crear, colecciones planas con filtros para listar, `/payments/summary?month=`, `ends_from` y `ends_to`, y renovar por el mismo endpoint de vender.

- Membresías de un socio: front `GET /members/:id/memberships`; plan `GET /memberships?member=`.
- Historial de un registro: front `GET /members/:id/audit`; plan `GET /audit?record=`.
- Registrar pago: front `POST /payments` (panel lateral que elige la membresía); plan `POST /memberships/{id}/payments`.
- Resumen de pagos: front `/payments/summary?month`; plan `/payments/report?month=`.
- Vencimientos: front `ends_from` y `ends_to`; plan "vence antes de".
- Renovar: front reutiliza vender con `?renovar=1` y `POST /memberships`; plan `POST /memberships/{id}/renew`.
- Asistencia por sesión: front `GET /class-sessions/:id/attendance`; plan solo describe la tabla.

Recomendación general: recursos anidados para crear (`POST /members/{id}/memberships`, `POST /memberships/{id}/payments`) y colecciones planas con filtros para listar (`GET /memberships?member=`, `GET /payments?member=`). Es lo que ya hace el plan; el front se adapta.

## 5. Permisos que el plan debe declarar

- **Resuelto (gate del 21 de octubre de 2026):** cada endpoint declara su rol en `docs/ddd/05_service_design.md`, sección 4. `DELETE /members/{id}`, `POST /memberships/{id}/cancel` y `POST /payments/{id}/void` son solo admin; congelar y revelar son admin y coach (Q6, Q7).

- `ROUTES.md` fija: coach vende membresías y registra pagos pero no anula; no da de baja socios; no ve Planes ni Sistema. Socio solo `/mi/*`.
- En el plan: Tarea 5 ya dice "solo admin" para planes. Tareas 4, 6 y 7 no dicen quién puede `DELETE /members/{id}`, `POST /memberships/{id}/cancel` ni `POST /payments/{id}/void`. Agregar `require_role("admin")` explícito en esos tres.
- Token de dispositivo de la TV: lo emite Configuración; depende del módulo `settings` (sección 2).

## 6. Trazabilidad: qué pantalla se puede construir en cada versión del backend

- v0.1: `Login` (solo la tarjeta de acceso), `Inicio` (KPIs de membresías y pagos; el resto vacío), `Socios_Lista`, `Socios_Movil`, `Socio_Ficha` (pestañas Membresías, Pagos, Historial), `Socio_Form` (sin foto ni adjuntos), `Planes`, `Membresias`, `Membresia_Vender`, `Pagos` (sin recibo PDF si se pospone), `Usuarios` (CRUD; sin reenviar enlace si no hay correo), `Auditoria`, `Config` (si se acepta el módulo `settings` en v0.1).
  - Estado al cierre del Sprint 3 (25 de octubre de 2026): construidas `/socios`, `/socios/:id` con sus pestañas Datos, Membresías y Pagos (rutas hijas), `/socios/:id/editar`, `/membresias`, `/membresias/vender` (con `?socio=` y `?renovar=1`), `/pagos` y el panel de registrar pago (`?pago=`). Pendientes de v0.1 que no son del Sprint 3: la pestaña Historial de la ficha (US-106, Sprint 4A, S4A-F2) y los KPIs de `Inicio` (US-108, Sprint 4A). Detalle en §10.
- v0.2: `PorAvisarHoy`, `Notif_Reglas`, `Notif_Historial`, tarjetas de recuperar y activar cuenta de `Login`, pestaña Avisos de la ficha.
- v0.3: `Llaves` (si se crea el router de crypto), foto y adjuntos en `Socio_Form` y `Socio_Ficha`.
- v0.4: `Sesiones`, `Horario`, `CheckIn`, pestaña Asistencia de la ficha, KPIs de asistencia en `Inicio`. Deuda de backend con dueño (S3-D92, PM2 de Fase 4 del Sprint 3): al agotarse las clases de una tiquetera, `classes` (US-160) recorta `end_date`; hasta entonces una tiquetera agotada con fin futuro bloquea la compra siguiente (`MembershipOverlap`).
- v0.5: `Movimientos`, `WOD_Lista`, `WOD_Form`, `WOD_Detalle`, `Resultados_Registro`, `TV`, pestaña Resultados de la ficha.
- v0.6: `Atleta_Perfil`, pestaña Atleta de la ficha.
- v1.0: `Portal_Inicio`, `Portal_Pagos`, `Portal_WODs`, `Portal_Progreso`, `Portal_Datos`, `Portal_Avisos`, validación de resultados enviados por socios.
- No se implementan (son referencia): `Mapa`, `P_Lista`, `P_Ficha`, `P_Formulario`.

## 7. Licencias que faltan en la lista de `CLAUDE.md`

- **Resuelto (gate del 21 de octubre de 2026):** `CLAUDE.md` acepta ahora ISC, OFL-1.1, 0BSD y PSF-2.0, y MPL-2.0 sin modificar también para `certifi` y `axe-core`; la CI corre `license-checker` en `web/` (US-004).

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

## 9. Sprint 2: cierre de brechas y diferencias con el diseño

Estado al cierre del sprint (`docs/ddd/09_sprint_plan/SPRINT-02.md`, sección "Estado al cierre"). Las pantallas del Sprint 2 son Login (tarjeta de acceso), Inicio mínima, Usuarios, Configuración en pestañas, Socios (alta y lista) y Planes (alta y lista, S2-F7: checkpoint `e662449`, fusionado en `981836a`). `/planes` carga `PlansPage` (`load` en `routeTable.ts`) y es solo para admin en el front (S2-D26).

### Rutas y contratos

- **`/cambiar-clave`:** no tiene pantalla en `docs/design/`. La ruta del front exige sesión (`web/src/config/routeTable.ts`) y usa `ChangePasswordPage`, un formulario con la contraseña actual que llama a `POST /api/v1/auth/me/password`. No es el formulario de restablecer, que usa el enlace de un solo uso. Lo usa quien tiene `must_change_password` verdadero. `// DESIGN-GAP:` (S2-D18, S2-F2, S2-F4a).
- **`POST /api/v1/auth/me/password`:** ruta canónica en v0.1 (S2-D46). Responde 200 con `AccessTokenOut` y un access nuevo; revoca las demás sesiones (S2-B3).
- **Inicio (`/`):** `InicioPage` mínima hasta `GET /api/v1/dashboard` (S2-D25). Ver la nota de la sección anterior sobre el Sprint 4A.
- **Activación y restablecimiento:** responden 204 y no inician sesión. El botón dice "Guardar contraseña", no "Guardar y entrar" (S2-D18).
- **Login:** muestra "APEX" en lugar de "[NOMBRE DEL GIMNASIO]", porque `gym_name` solo llega con sesión (S2-D50).
- **Cerrar sesión:** `POST /api/v1/auth/logout` es público y se autentica por la cookie, no por el Bearer (S2-D35).

### Datos

- **Socio, consentimiento:** `data_consent` es booleano. El cliente no envía `data_consent_at`; el servidor fija la fecha con su reloj (M-4, S2-D16).
- **Socio, notas:** no existe `notes` (M-5). Foto, firma y documento firmado llegan con v0.3.
- **Socio, tipo de documento:** `document_type` (`CC`, `CE`, `TI`, `PA`; por defecto `CC`) en `0006_members`, sin cifrar (S2-D16).
- **Socio, nombre:** `first_name` y `last_name` en dos campos (S2-D16).
- **Usuario, nombre:** `auth.users` no tiene nombre; Usuarios muestra el correo (S2-D17). `display_name` no existe en el código. Ver la contradicción abierta más abajo.

### Pantallas

- **Configuración:** tres pestañas (Gimnasio, Privacidad, Membresías) con `?tab=`, en lugar de las ocho cajas con índice (S2-D15, S2-F5).
- **Usuarios:** las acciones del ciclo de vida van en cada fila (editar, bloquear, desbloquear, cerrar sesiones, reenviar enlace, dar de baja), no en un panel de `Usuarios.html` (S2-F4b).
- **Socios, búsqueda:** el término `q` vive en el estado local y nunca en la URL (S2-D41).
- **Socios, 409:** "Ver socio existente" enlaza a `/socios/{existing_id}`, que no tiene pantalla hasta S3-B9 y S3-F1 (S2-D34).

### Brechas que el sprint cerró

- `settings` (`Config.html`): cerrada en S2-B1 y S2-F5.
- Recuperación y activación de cuenta: cerrada en la API (S2-B4) y en el front (S2-F4a, S2-F4b). El correo sigue pendiente de US-131.
- Ruta de cambio de contraseña: cerrada (`POST /api/v1/auth/me/password`, S2-D46).
- `data_consent`, `notes` y `document_type`: cerradas en el contrato (S2-D16).
- Tablero de inicio: parcial (ver arriba).
- Planes (`Planes.html`): alta y lista cerradas en S2-B9 y S2-F7; edición y baja llegan con el Sprint 4A.

### DESIGN-GAP por pantalla

Cada fila es un `// DESIGN-GAP:` de `web/src/` (listado en `docs/scratch/sprint-02-front.md`). Donde el plan no fija sprint, se dice así.

| Pantalla o archivo | Brecha | Se resuelve en |
|---|---|---|
| Panel · `SideNav.tsx` | Cajón y modo plegado no dibujados | Sin sprint en el plan |
| Panel · `SideNav.module.css` | Velo sin token; usa `--black` al 45 % como `SidePanel` | Sin sprint en el plan |
| Panel · `nav.ts` | "Pantalla · Abrir pantalla TV" no entra; la TV se abre con token | Sprint 8 / EP-23 (US-175) |
| Portal · `PortalLayout.tsx` y `.module.css` | Contador de avisos; sin token de 600 px ni del alto del menú inferior | Sprint 10 / EP-25 |
| Tablet · `GymLayout.module.css`, `ZoneShells.tsx` | Sin token de texto ampliado; la salida de la tablet va a `/` | Sin sprint en el plan |
| Rutas · `routeTable.ts`, `routes.reference.ts`, `ChangePasswordPage` | `/cambiar-clave` sin pantalla en el diseño | Sin sprint; resuelto en código (S2-F2, S2-F4a) |
| Rutas · `NoPermissionPage.tsx`, `MessagePage.tsx` | El diseño no tiene pantallas de error ni de permiso | Sin sprint en el plan |
| Rutas · `PendingPage.tsx` | Estado intermedio para `/planes` | Cerrada: F7 dejó `/planes` en `load` y la revisión de Fase 4 (L1) retira `PendingPage.tsx` y la rama `pending` de `routeTable.ts` y `routes.tsx` |
| Inicio · `InicioPage.tsx` | Tablero de `Inicio.html` hasta `GET /dashboard` | Sprint 4A / US-108 |
| Kit · `StatusTag.module.css` | Relleno de peligro constante entre temas | Sin sprint en el plan |
| Kit · `Catalog.tsx` | Estados de cuenta de `StatusTag` | Resuelto en S2-F4a |
| Login · `LoginCard.tsx` | "[NOMBRE DEL GIMNASIO]" se muestra como "APEX" (S2-D50); avisos de cierre no confirmado y del 429 sin dibujar | Sin sprint en el plan |
| Configuración · `ConfigPage.tsx` | Pestañas en vez de ocho cajas (S2-D15) | Decisión tomada; las secciones `hours`, `payment_methods`, `channels`, `classes` y `tv` llegan con sus sprints |
| Configuración · `GymSettingsForm.tsx` | Sin cuadro de logo; "Zona horaria" como nota fija; NIT, ciudad y correo no están en `Config.html` | Logo: v0.3. Lo demás, sin sprint en el plan |
| Configuración · `PrivacySettingsForm.tsx` | Sección propia en lugar de la caja "TV · Datos personales" | Decisión tomada; sin sprint |
| Configuración · `MembershipsSettingsForm.tsx` | "Días de gracia", "Check-in vencido" y unidad de carga no están en el contrato de US-058; las clases llegan con US-154 | Clases: Sprint 7 / US-154. Lo demás, sin sprint en el plan |
| Usuarios · `UsersPage.tsx` | Sin columna de nombre (S2-D17); rol como texto; filtro "Equipo" | Nombre: Sprint 4A / US-110. Filtro "Equipo": sin sprint. La columna de acciones se resolvió en S2-F4b |
| Usuarios · `NewUserPanel.tsx` | Reutiliza el panel de edición sin nombre; muestra el enlace que la pantalla no dibuja | Sin sprint en el plan |
| Usuarios · `ChangePasswordPanel.tsx` | Sin pantalla "Mi cuenta" en el diseño | Sin sprint en el plan |
| Activación · `ResetPage.tsx` | "Guardar contraseña" en lugar de "Guardar y entrar" (S2-D18) | Decisión tomada |
| Recuperación · `ForgotPage.tsx` | Mensaje fijo de v0.1 (H-2) | Sprint 5 / US-131 (correo) |
| Usuarios · `UserRowActions.tsx`, `UsersPage.tsx` | Acciones en la fila en lugar del panel del diseño; `DESIGN.md` pide filas sin editar ni borrar | Decisión tomada (S2-F4b); sin sprint |
| Usuarios · `EditUserPanel.tsx` | Sin nombre (S2-D17); sin tabla de permisos por rol | Nombre: Sprint 4A / US-110. Tabla de permisos: sin sprint |
| Usuarios · `LinkModal.tsx` | La pantalla no dibuja dónde se ve el enlace reenviado | Sin sprint en el plan |
| Kit · `shared/ui/Modal.tsx` | `DESIGN.md` solo nombra `ConfirmModal` | Sin sprint en el plan |
| Socios · `MemberFormFields.tsx` | Sin foto, firma ni documento firmado; sin "Acceso al portal", unidad de cargas ni observaciones de salud; nombre en dos campos; sexo y teléfono opcionales | Foto, firma y autorización: Sprint 6 / US-148 y US-149. Acceso al portal: Sprint 10 / EP-25. Unidad de cargas: sin historia verificada (atleta, EP-24). Observaciones de salud: sin historia en el plan. Nombre y opcionales: S2-D16 y N-19 |
| Socios · `MemberFormPage.tsx` | Sin "Guardar y vender membresía"; tras guardar vuelve a la lista con aviso | Venta: Sprint 3 / S3-B1 (US-083 y US-084). El aviso es decisión tomada |
| Planes · `PlansPage.tsx` | Sin "Socios con él"; sin "Editar" en la fila; total sin partir en activos e inactivos; duración y clases en columnas propias; filtro "Estado" en vez de "Mostrar" (que ya nombra el tamaño de página) | "Socios con él": Sprint 4A / US-082 (corregido en S3-W0-1, D37: necesita `plans -> memberships`). "Editar": Sprint 4A. Lo demás, decisión tomada en S2-F7 |
| Planes · `PlanForm.tsx` | Sin descripción ni casilla "Activo": `PlanCreate` no los tiene; el panel solo crea | Edición y activación: Sprint 4A. Descripción: sin historia en el plan |
| Planes · `PlanDetailPanel.tsx` | `Planes.html` no dibuja un detalle de solo lectura | Edición: Sprint 4A. El detalle de solo lectura es decisión tomada en S2-F7 |
| Socios · `MembersListPage.tsx` | Sin teléfono, plan, vence, asistencia ni columna de acción; sin documento enmascarado (N-01); sin chips ni conteos por estado de membresía; sin filtros de plan y asistencia; sin "Exportar" | Membresía, plan, filtros, chips y conteos: Sprint 3 / US-071. Asistencia: Sprint 7 / EP-21. Exportar: Sprint 5 / EP-16. Documento enmascarado: N-01 (la lista no devuelve datos cifrados) |

### Contradicción abierta

- `docs/ddd/09_sprint_plan/SPRINT-01.md` (refinamientos de US-110) planea `display_name` en `0004`. El código no lo tiene, `0004_auth` tampoco, y S2-D17 lo deja para US-110 del Sprint 4A. No se cambió ninguno de los dos documentos; hay que decidir cuál manda.

## 10. Sprint 3: brechas con el diseño (cierre de V1)

Estado al 25 de octubre de 2026, después de los slices S3-F1 a S3-F7. Fuentes: `docs/scratch/sprint-03-front.md` (cuaderno del front), los `// DESIGN-GAP:` de `web/src/`, `docs/ddd/blueprints/sprint-03-plan.md` (D10, D14, D16, D17, D24, D37, D39) y `docs/ddd/DECISIONES.md` (Q3, N-20, N-23, N-26, N-27, N-28, S3-D41, S3-D46, S3-D50, S3-D51, S3-D57, S3-D65 y S3-D98).

Cada brecha dice qué pide el diseño, qué se construyó y por qué, y su estado. Los estados son:
- Aceptada para v0.1: lo construido es el comportamiento de v0.1.
- Pendiente de diseño: el diseño no fija la solución y el front usa una provisional.
- Depende de versión futura: el dato o la acción llega con el módulo dueño (versión o sprint indicado).
- Pendiente de código: la pantalla existe, pero el diseño o una historia piden algo que el código todavía no hace.

### 10.1 Socios: lista y vista móvil (S3-F2)

Pantallas `Socios_Lista.html` y `Socios_Movil.html`. Ruta `/socios`.

- Chip "Pendiente de pago" (Q3): el diseño no lo dibuja. Se muestra con el tono de "Por vencer" (borde y texto `--warning`). Aceptada para v0.1.
- Chips de estado: el celular usa los ocho del escritorio ("Todos" y siete estados) en una fila desplazable, no los cuatro de `Socios_Movil.html` ("Al día", "Por vencer", "Vencidos", "Inactivos"). La barra de filtros se apila. Aceptada para v0.1.
- Plegado "Filtros": no se construye. El plegado del portal llega con v1.0. Depende de versión futura (v1.0).
- Chip "Dados de baja": solo lo ven admin y coach (N-20), en lugar de un 404. Aceptada.
- Conteos de los chips: salen de `GET /memberships/summary` (D37, N-26). "Todos" cuenta los socios vivos y "Sin membresía" es el total menos la suma de los cinco estados, que nunca es negativo. Aceptada para v0.1.
- Paginación en celular: "Cargar más" acumula tarjetas (US-072, D39) en vez de "Anterior" y "Siguiente". La lista se corta en 20 páginas y muestra "Se muestran los primeros N socios". US-072 pide "Cargar más" hasta el total; el tope es una desviación que ya fijó D39, no la regla de la historia. Aceptada para v0.1.
- Botón "+ Nuevo": en celular es un botón flotante (blueprint F2); el diseño lo pone junto al título. Aceptada.
- Círculo de la foto en la tarjeta: llega con los adjuntos (v0.3). Depende de versión futura (v0.3).
- "12 clases · quedan 2" en la tarjeta: `GET /members` no trae las clases restantes. Depende de versión futura (clases, v0.4).
- Columnas de escritorio: el diseño pide teléfono, última asistencia y una columna "Acción" (Ver, Renovar, Vender). La lista no devuelve datos cifrados (N-01) y la asistencia llega con v0.4; las acciones están en la ficha y en Membresías. Teléfono: aceptada para v0.1 (N-01). Asistencia: depende de v0.4. Acción: aceptada.
- Documento enmascarado bajo el nombre: la lista no lo trae (N-01); se ve en la ficha. Aceptada para v0.1.
- Columna "Vence": fecha con año. No lleva "Vencido · 5 días" ni "reanuda 1 nov", porque la fila no trae días restantes ni fecha de reanudación. Aceptada para v0.1.
- Filtro por última asistencia: v0.4 (EP-21). Depende de versión futura.
- "Exportar": v0.2 (Q15, N-29, EP-16, US-139). Depende de versión futura (v0.2). El comentario de `MembersListPage.tsx` ya lo atribuye a EP-16 (Fase 4 del front).
- Encabezado sin "· 269 con membresía": el número ya está en los chips. Aceptada.
- Nota de búsqueda por valor exacto: el diseño no la pone; va como ayuda corta bajo la lista. Aceptada.
- "Ordenar por: Vencimiento más próximo": `GET /members` solo ordena por apellido, nombre y fecha de alta (`members/service.py`, `_ORDEN`). Ordenar por fin de membresía cruza `members` con `memberships` dentro de la consulta de socios, algo que la regla 2 de `CLAUDE.md` no permite sin un puerto. Decisión S3-D98: no entra en v0.1.

### 10.2 Ficha del socio (S3-F1 y S3-F7)

Pantalla `Socio_Ficha.html`. Ruta `/socios/:id`.

- Foto y cuatro tarjetas de resumen (Membresía, Asistencia, Último WOD, Avisos): la foto llega con los adjuntos (v0.3). La tarjeta Membresía es la de la vigente, dentro de la pestaña Membresías. Las otras tres llegan con sus versiones (Avisos v0.2, Asistencia v0.4, Último WOD v0.5). Depende de versión futura.
- Acciones del encabezado: el diseño pone "Renovar" y "Registrar pago" arriba. Aquí van en las pestañas: Membresías (Renovar, Registrar saldo) y Pagos (Registrar pago). "Vender membresía" siempre lleva a la venta; si el socio ya tiene una vigente, el 409 de la venta ofrece "Renovar" (S3-D65). Aceptada para v0.1.
- Menú "Más": no existe. Traería WhatsApp (v0.2) y el enlace al portal (v1.0). "Dar de baja" va como botón del encabezado. El menú depende de versión futura; el botón, aceptada.
- Aviso "Sin autorización de datos registrada" (Q16): aparece cuando `data_consent_at` es nulo. El diseño no lo dibuja. Aceptada.
- Socio dado de baja: el diseño no dibuja el estado. La ficha muestra la etiqueta "Dado de baja" con la fecha y queda en solo lectura (editar responde 409 `member_deactivated`). "Mostrar" sigue disponible (N-20). Aceptada.
- "Reactivar": el diseño no tiene la acción. Solo la ve el admin; reemplaza a "Dar de baja" en el menú de un socio dado de baja (`POST /members/{id}/reactivate`, N-20). Si el documento ya lo usa otro socio vivo, el 409 `member_document_duplicated` enlaza a ese socio. Aceptada.
- Pestañas: Asistencia (v0.4), Resultados (v0.5), Atleta (v0.6), Avisos (v0.2) y Adjuntos (v0.3) se muestran deshabilitadas hasta su versión. Historial también se muestra deshabilitada, con la nota "Disponible en v0.1 · Sprint 4A": su pestaña es de US-106 (Sprint 4A, S4A-F2). Depende de versión futura.
- Pestañas Membresías y Pagos: existen como rutas hijas (S3-D65). Aceptada.

### 10.3 Pestaña Datos y edición del socio (S3-F1)

Pantallas `Socio_Ficha.html` (pestaña Datos) y `Socio_Form.html` en modo editar. Rutas `/socios/:id` (pestaña índice) y `/socios/:id/editar`.

- Contacto de emergencia: el diseño muestra nombre y parentesco en claro y enmascara solo el teléfono. El api cifra y enmascara el contacto completo ("Registrado"); `members.emergency_contact` es un campo cifrado en v0.1 (`CLAUDE.md`, reglas de datos). Aceptada para v0.1.
- Campos cifrados: "Mostrar" revela un dato con una llamada auditada (US-074) y el claro dura 60 s. El diseño no dibuja el botón ni la auditoría. Aceptada.
- Edición por rol: `Socio_Form.html` no distingue roles. El coach ve el documento y su tipo de solo lectura; si los envía, aunque sean iguales, el api responde 403 `forbidden_field`. El admin los edita. Aceptada (S3-D46).
- Campos sensibles al editar: el diseño no dice cómo se cambia un dato cifrado. Aquí van "Cambiar", "Quitar" y "Deshacer" sobre la máscara. Dejar el campo vacío no lo envía; `null` solo se envía con "Quitar". El documento no se quita. Aceptada.
- Autorización de datos: se puede marcar, nunca retirar (`data_consent: false` da 422). "Registrar autorización" aparece solo si falta. El diseño no lo dice. Aceptada (S3-D46).
- Sexo: suma "Sin indicar" (no se envía) y "Otro" (`x`), según §3. Aceptada.
- Sexo y teléfono: el diseño los marca con asterisco (obligatorios); el alta los deja opcionales, como fija N-19. Aceptada.
- Caja "Historial reciente" de la pestaña Datos: llega con la pestaña Historial (US-106, Sprint 4A). Depende de versión futura (Sprint 4A).
- Foto, firma, documento firmado y archivo: llegan con los adjuntos (v0.3, EP-19). Depende de versión futura.
- "Acceso al portal": v1.0. "Unidad para cargas": v0.6 (atleta). "Observaciones de salud": no existen en el modelo (M-5). Depende de versión futura; las observaciones no tienen modelo.
- Guardar: el alta vuelve a la lista con aviso (decisión de S2-F6); la edición vuelve a la ficha con "Cambios guardados". El diseño pide "Guardar y vender membresía" y el front no lo ofrece; la venta se alcanza desde la ficha. Pendiente de diseño.
- Baja y reactivación: la confirmación usa `ConfirmModal` de DESIGN.md; el diseño no la dibuja. Aceptada.

### 10.4 Pestañas Membresías y Pagos de la ficha (S3-F7)

El diseño de la ficha solo enlaza a `Membresias.html` y `Pagos.html`; no dibuja el contenido de las pestañas.

- Pestaña Membresías: tarjetas de la vigente y de la futura, e historial con las columnas de `Membresias.html`, sin "Socio" y sin acciones por fila (las acciones van en las tarjetas). Aceptada.
- Tarjeta de la futura: el diseño solo dibuja la vigente. Pendiente de diseño (el front la muestra con el mismo formato).
- "Pendiente de pago" (Q3) en la tarjeta: tono "Por vencer" y su texto. Aceptada.
- Vigencia con año ("29 sept 2026 – 28 oct 2026", DESIGN.md regla 7). Aceptada.
- Pestaña Pagos: tabla de `Pagos.html` sin columna "Socio" (es la del socio) y con "Anular" en la fila en vez de "Ver". Aceptada.
- "Ocultar anulados" (`voided=false` en la URL): no dibujado. Pendiente de diseño.
- Fechas con año y hora en 12 h (DESIGN.md regla 7). Aceptada.
- "Registrar pago" oculto para un socio dado de baja. Aceptada (N-20).

### 10.5 Membresías (S3-F5, `/membresias`)

Pantalla `Membresias.html`.

- Chip "Pendiente de pago" (Q3): no dibujado; tono "Por vencer" y su texto. Aceptada.
- Conteos: el diseño los pone en los chips ("Activas 210"). Aquí van en cinco tarjetas "Socios por estado de su membresía", porque cuentan socios según la membresía que decide su estado (N-26) y no filas de la lista. Un chip con ese número no coincidiría con el listado al pulsarlo. Aceptada para v0.1.
- "Exportar": v0.2 (EP-16, US-139). Depende de versión futura. El comentario de `MembershipsPage.tsx` ya lo atribuye a EP-16 (Fase 4 del front).
- Chip "Historial completo": no se construye. Sin estado, la lista ya trae todas menos las anuladas (D18), y marcar todos los chips da el historial completo. Aceptada.
- Estado "Anulada" (`cancelled`): el diseño no define su estilo; el `StatusTag` usa el de "Congelado" (neutro). Pendiente de diseño.
- Fechas con año ("29 sept 2026"; el diseño escribe "29 sep"). Aceptada (DESIGN.md regla 7).
- Estado de la fila: la etiqueta común de `StatusTag` ("Por vencer"), no "Vence en 8 días". Aceptada.
- Pagada completa: "$ 120.000 · pagado" en lugar de la marca "✓" (el significado va en texto). Aceptada.
- Filtro de plan: el admin ve todos los planes y el coach solo los activos (S2-D26). Un plan inactivo que llega por la URL se muestra como "Plan elegido". Aceptada.
- Congelar: el modal del diseño tiene un campo "Motivo"; `FreezeIn` no lo recibe y la tabla no tiene columna (D14). Aceptada para v0.1. Si el gimnasio lo pide, es cambio de API y de tabla.
- Acciones por estado: "Registrar saldo" solo en estados que reciben pagos (N-28) y con saldo; "Congelar" solo para al día o por vencer (el api responde 409 `membership_not_freezable` en las demás). Aceptada (reglas del api).

### 10.6 Vender y renovar (S3-F3, `/membresias/vender`)

Pantalla `Membresia_Vender.html`. Rutas `/membresias/vender`, con `?socio=` y `?renovar=1`.

- Fin de vigencia: el diseño dibuja "29 oct – 27 nov" para un plan de 30 días. El fin es inclusivo (`inicio + duración`, N-23), así que el front dice "hasta el 28 nov 2026". Aceptada (D16, N-23).
- "Precio pactado": el diseño lo deja ajustar como descuento. `SellMembershipIn` no recibe precio y el servidor copia el del plan. Aceptada para v0.1 (D16). Si el gimnasio pide descuentos, cambia el contrato de venta.
- Referencia del primer pago: opcional en los tres medios (N-28, D17); el asterisco de Nequi y Bre-B del diseño se ignora. El patrón de comprobante aplica a todos (S3-D50). Aceptada.
- Fecha y hora del pago: el diseño pide solo la fecha. `paid_at` es un instante (N-27), así que se pide fecha y hora. Aceptada.
- "Recibo por correo si el socio tiene correo": no aparece; los recibos llegan con v0.2 (P4). Depende de versión futura (v0.2).
- Tarjeta del socio: el diseño muestra "vigente hasta … · la nueva empieza el …". Desde la Fase 4 del front, el resultado de la búsqueda y la tarjeta del socio elegido dicen plan, estado y fin ("Mensual · Por vencer · hasta el 2 nov 2026", `membership_end_date` de S3-B9b). El inicio de la nueva está en el paso "2 · Plan y fechas". Resuelto.
- Nombre del socio: si se llega sin el nombre en la navegación (un enlace directo o recargar), la tarjeta dice "Socio elegido" hasta que `GET /members/{id}` lo entrega (S3-F7). Resuelto.
- "Registra": el resumen muestra el correo de la sesión; el nombre de usuario llega con US-110 (Sprint 4A). Depende de versión futura (Sprint 4A).
- Botón: "Vender y cobrar" (con pago) o "Vender" (sin pago), en lugar de "Confirmar venta y pago" del diseño. Pendiente de diseño: el diseño debe adoptar el nombre.
- Sobrepago: el aviso "¿Registrar un pago mayor al precio?" es de la pantalla. El api responde 409 `payment_exceeds_balance`, y solo entonces viaja `confirm_overpayment: true` (S3-D41). Aceptada.
- Migas, "Cancelar" y estado tras vender: las migas enlazan "Membresías" a `/membresias`. "Cancelar" y el enlace de "Venta registrada" llevan a la ficha del socio si se llegó con `?socio=`, y a `/membresias` si no. La venta registrada se queda en la página para que se lea el resultado (S3-D103). Resuelto en la Fase 4 del front.

### 10.7 Registrar pago y anular (S3-F4, panel `?pago=`)

Pantalla `Pagos.html` (panel lateral). Se abre sobre cualquier pantalla con `?pago=<membresía>` o `?pago=nuevo&socio=<socio>` (S3-D65).

- Fecha y hora del pago: el diseño no la muestra. `paid_at` es un instante (N-27), así que se pide fecha y hora. Aceptada.
- Referencia opcional (el diseño la marca con asterisco): N-28 y D17. Aceptada.
- "Nueva venta…" en el selector: el front lo cambia por el enlace "Vender una membresía" cuando el socio no tiene membresías abiertas. Pendiente de diseño.
- Buscador de socio: aparece solo si la URL no fija ni socio ni membresía. Pendiente de diseño.
- Tras registrar: el panel muestra "Pago registrado" con "Registrar otro pago". El diseño no dibuja el estado posterior. Pendiente de diseño.
- Socio dado de baja o inactivo: el panel abierto con `?pago=<membresía>` lo ofrece. Cobrar una membresía ya vendida no depende del estado del socio (INFO de S3-B4, regla de negocio). El buscador del panel muestra al inactivo con la nota "Inactivo · …" y no muestra a los dados de baja (S3-D99, Fase 4 del front). Aceptada.
- Anular pago (`VoidPaymentModal`): motivo de 1 a 500 caracteres y aviso M-7; tras anular, "Pago anulado" con "Registrar pago nuevo" y la precarga. El diseño no dibuja la anulación en el panel. Aceptada (US-097, S3-D50).
- Medios de pago (Configuración, pestaña "Medios de pago"): el diseño trae casillas para habilitar cada medio, el número de Nequi, la llave de Bre-B y "Exigir referencia en Nequi y Bre-B". El contrato (D24) trae solo nombre y ayuda, y los tres medios están siempre habilitados; las filas son fijas. Aceptada para v0.1. Si el gimnasio pide esos datos, es una decisión nueva.
- Textos de fecha y saldo con el formato común: "25 sept–24 oct" (el diseño escribe "sep") y "saldo $ 60.000" (el diseño escribe "$60.000"). Aceptada (DESIGN.md regla 7).
- Límite retroactivo: el 422 `paid_at_too_retroactive` no trae el número de días y el coach no lee Configuración. Desde la Fase 4 del front el texto no da una cifra: "Como coach solo puedes registrar pagos de los días que permite el gimnasio…". El aviso de duplicado tampoco fija la ventana del api ("hace unos minutos"). Resuelto.

### 10.8 Pantalla de pagos (S3-F6, `/pagos`)

Pantalla `Pagos.html`.

- Primera columna: el socio (DESIGN.md: la primera columna enlaza a la ficha); el diseño pone la fecha primero. Aceptada.
- Estado del filtro: arranca en "Todos" (D37, para que un pago recién anulado siga visible); el diseño pone "Válidos" primero. Aceptada.
- Filtro "Retroactivos" y marca "Retroactivo": no dibujados (S3-D51, campo `backdated`). Pendiente de diseño.
- "Registró": muestra el correo parcial (S3-D57), no el nombre hasta US-110. Las opciones son "Yo" y las personas que aparecen en la página, porque el coach no tiene lista de usuarios. Depende de versión futura (US-110, Sprint 4A).
- Fecha con año y hora en 12 h ("20 oct 2026, 2:10 p. m."; el diseño escribe "20 oct 14:10"). Aceptada (DESIGN.md regla 7).
- Valor sin nota de "abono": la fila no trae el saldo de la membresía. Aceptada para v0.1.
- "Exportar": v0.2 (EP-16, US-139). El comentario de `PaymentsPage.tsx` ya lo atribuye a EP-16 (Fase 4 del front). Depende de versión futura.
- Detalle del pago: sin "#4812" (los pagos tienen UUID, no consecutivo) y sin "Recibo · Reenviar · Imprimir" (recibo PDF: v0.2, P4). "Registró" muestra el correo parcial. Aceptada; el recibo depende de v0.2.
- Resumen del mes (`MonthSummary`): el diseño no dibuja el selector de mes ni la tarjeta "Anulados". El mes va en `?mes=AAAA-MM` (por defecto, el mes de Bogotá). El título lleva el año ("Octubre 2026 · total"). Con cinco tarjetas, "Anulados" baja a una segunda fila a 1440 px. Pendiente de diseño.

### 10.9 Resúmenes y KPIs del Sprint 3

- Chips de socios: conteos desde `GET /memberships/summary` (ver 10.1).
- Resumen de membresías: cinco tarjetas en vez de conteos en los chips (ver 10.5).
- Resumen mensual de pagos: total del mes, una tarjeta por medio y "Anulados" (ver 10.8).
- Inicio (`Inicio.html`): sigue en `InicioPage` mínima. Los KPIs llegan con `GET /dashboard` en US-108 (Sprint 4A, S4A-B8). Depende de versión futura (Sprint 4A).

### 10.10 Textos y avisos que el diseño no dibuja (transversal)

- Aviso bajo "Referencia" (registrar pago y primer pago de la venta) y "Motivo" (anular pago y anular membresía): "No escribas teléfonos, documentos ni datos de salud". Aceptada (S3-D50). Residual: la auditoría inmutable guarda el texto escrito; la supresión llega con US-119.
- Referencia con patrón de comprobante `^[A-Za-z0-9][A-Za-z0-9 ._/#-]{0,63}$` (S3-D50). Aceptada.
- Confirmaciones de sobrepago y de duplicado: el diseño las muestra como aviso del front. Desde el Sprint 3 las exige el servidor: 409 `payment_exceeds_balance` y 409 `payment_possible_duplicate` (pago igual no anulado en los últimos 120 s), S3-D41. El front muestra `ConfirmModal` y reenvía con `confirm_*`, que no se guardan. Aceptada.

### 10.11 Rutas y contratos de Sprint 3

- `GET /api/v1/payments/methods` responde `{ items }`, no un arreglo (S3-C7). Aceptada.
- Pestañas Membresías y Pagos de la ficha como rutas hijas con contexto (S3-D65, E3, E14). Aceptada.
- Panel de registrar pago con `?pago=` sobre cualquier pantalla del panel (S3-D65). Aceptada.
- Ficha con un `id` sin forma de UUID: muestra "Socio no encontrado" sin pedir nada. Aceptada.

### 10.12 Cierre de filas de la sección 9 (Sprint 3)

- Socios, 409 "Ver socio existente": cerrado en S3-F1; la ficha existe en `/socios/:id`.
- Socios, lista: membresía, plan, filtros, chips y conteos (US-071): cerrados en S3-F2. Asistencia (v0.4) y Exportar (v0.2) siguen pendientes.
- Socios, venta: la venta existe en `/membresias/vender` (S3-F3). "Guardar y vender membresía" en el alta sigue sin hacerse (ver 10.3).
- Membresías y pagos de la ficha: cerrados en S3-F7.
- "Socios con él" (`Planes.html`): no entra en el Sprint 3 (necesita la arista `plans -> memberships`). Lo cierra US-082 (Sprint 4A).

### 10.13 Pendientes de código (no de diseño)

Los cuatro puntos que V1 dejó aquí se cerraron en la Fase 4 del front (`docs/ddd/DECISIONES.md`, "Fase 4 · Sprint 3 · Front"). No queda ninguno abierto.

- `MemberStep.tsx`: pinta la fecha de fin del socio en el resultado y en la tarjeta (ver 10.6). Resuelto.
- `SellPage.tsx`: las migas, "Cancelar" y la salida tras vender (ver 10.6 y S3-D103). Resuelto.
- Comentarios con atribución errónea: `MembersListPage.tsx`, `MembershipsPage.tsx` y `PaymentsPage.tsx` ya atribuyen "Exportar" a EP-16 (US-139, v0.2). Resuelto.
- Texto de `paid_at_too_retroactive` (ver 10.7): sin cifra fija. Resuelto.

### 10.14 Decisiones de V1

- S3-D98: el orden "Vencimiento más próximo" de la lista de socios no entra en v0.1 (ver 10.1 y `docs/ddd/DECISIONES.md`).
- S3-D99 (Fase 4 del front): el buscador del panel de pagos ofrece al socio inactivo, marcado (ver 10.7).
- S3-D103 (Fase 4 del front): a dónde lleva la venta al salir (ver 10.6).
