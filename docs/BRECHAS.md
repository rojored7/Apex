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
- v0.2: `PorAvisarHoy`, `Notif_Reglas`, `Notif_Historial`, tarjetas de recuperar y activar cuenta de `Login`, pestaña Avisos de la ficha.
- v0.3: `Llaves` (si se crea el router de crypto), foto y adjuntos en `Socio_Form` y `Socio_Ficha`.
- v0.4: `Sesiones`, `Horario`, `CheckIn`, pestaña Asistencia de la ficha, KPIs de asistencia en `Inicio`.
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

## 10. Sprint 3: brechas previstas y diferencias con el diseño

Fuente: `docs/ddd/blueprints/sprint-03-plan.md` (D37, S3-D41, S3-D50) y `docs/ddd/DECISIONES.md`, "Sprint 3". Se escribe en S3-W0-1, antes de construir las pantallas; los slices del front (S3-F1 a S3-F7) anotan aquí lo que cierren o lo que aparezca y el cierre del sprint lo confirma contra los `// DESIGN-GAP:` reales de `web/src/`.

### Diferencias deliberadas con el diseño (D37; todas llevan `// DESIGN-GAP:` en el código)

- **Chip "Pendiente de pago" (Q3, D10):** el estado `pending_payment` se guarda y se muestra; `Socios_Lista.html`, `Membresias.html` y la ficha no lo dibujan.
- **"Precio pactado" de solo lectura (D16):** `SellMembershipIn` no lleva `agreed_price_cop`; el coach no fija el precio.
- **Fin de vigencia por N-23 (D16):** el fin es inclusivo (`start_date + duration_days`): un plan de 30 días da acceso 31. El front dice "hasta el <fecha>", nunca "30 días", aunque `Membresia_Vender.html` dibuje otra cuenta.
- **Congelar sin "Motivo" (D14):** `FreezeIn` no tiene `reason` y la tabla no tiene columna; el modal del diseño lo pinta.
- **Referencia opcional en los tres medios (N-28, D17):** el asterisco de Nequi y Bre-B del diseño se ignora.
- **Filtro de estado de `Pagos` en "Todos":** para que un pago recién anulado siga visible.
- **Sin "Exportar" ni recibo PDF:** llegan con v0.2 (EP-16, sección 2 de este archivo).
- **Conteos de los chips de socios:** salen de `GET /memberships/summary`; el de "Sin membresía" es el total menos la suma de los cinco estados.
- **Tarjeta de la membresía futura en la ficha:** el diseño solo dibuja la vigente.
- **Medios de pago fijos:** la pestaña "Medios de pago" tiene tres filas fijas (Efectivo, Nequi, Bre-B) sin casillas de habilitar; agregar un medio exige una actualización (D24).
- **Ficha sin autorización de datos registrada (Q16):** aviso cuando `data_consent_at` es nulo; el diseño no lo dibuja.

### "Socios con él" de `Planes.html`

No entra en el Sprint 3: necesita la arista `plans -> memberships` y `count_active_by_plan` visible en `PlanOut`. Lo cierra US-082 (Sprint 4A). La fila de `PlansPage.tsx` de la sección 9 quedó corregida.

### Confirmación de sobrepago y de duplicado (S3-D41, S3-C22)

El diseño muestra la advertencia de Q5 como un aviso del front. Desde el Sprint 3 la confirmación vive en el servidor: sin `confirm_overpayment` el API responde 409 `payment_exceeds_balance` (`field="amount_cop"`), y sin `confirm_duplicate` responde 409 `payment_possible_duplicate` cuando hay un pago igual (misma membresía, quien registra, valor, medio y referencia) no anulado en los últimos 120 s. La pantalla muestra el `ConfirmModal` y reenvía con la confirmación. `confirm_*` no se guardan. En la venta con primer pago solo aplica el sobrepago, contra el precio del plan.

### Avisos de datos personales en textos libres (S3-D50)

Bajo los campos "Referencia" (registrar pago, primer pago de la venta) y "Motivo" (anular pago, anular membresía) el front muestra "No escribas teléfonos, documentos ni datos de salud". El diseño no lo dibuja. La referencia además solo admite el patrón de comprobante `^[A-Za-z0-9][A-Za-z0-9 ._/#-]{0,63}$`. Residual registrado: la auditoría inmutable conserva el texto escrito; la supresión llega con US-119.

### Rutas y contratos que cambian respecto del diseño o de los desgloses

- `GET /api/v1/payments/methods` responde `{ items }`, no un arreglo (S3-C7).
- Las pestañas Membresías y Pagos de la ficha son rutas hijas reales: `/socios/:id/membresias` y `/socios/:id/pagos` (S3-D65, E3, E14).
- El panel de registrar pago se abre desde cualquier pantalla con `?pago=<membership_id>` o `?pago=nuevo&socio=<member_id>` (S3-D65).
