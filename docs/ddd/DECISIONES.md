# Registro de decisiones del pipeline

Fecha: 21 de octubre de 2026. Este archivo cierra los huecos que aparecieron al derivar épicas, historias y sprints. Cada decisión es un supuesto de trabajo tomado por el orquestador; todas se presentan en el gate humano único y se pueden revertir ahí. Cuando una decisión corrige un documento anterior, se indica qué documento y qué cambia.

## A. Pendientes del usuario (se preguntan en el gate)

- **D1 / S1:** el front se construye en este repositorio, en `web/`, dentro de este flujo. Reescribir "Alcance" de `CLAUDE.md`.
- **D2 / S2:** paginación `limit`/`offset`; corregir `DESIGN.md` y `ROUTES.md`.
- **D5 / S5:** vender y renovar pasan por la operación `sell`; un solo endpoint `POST /members/{id}/memberships`.
- **P1:** quién atiende recepción (no cambia v1.0).
- **P3:** destino del backup (S3 compatible por `.env`; si no hay, local).
- **P4:** recibo PDF en v0.2.
- **P5:** correo de login en claro en `auth.users.email`.
- **P7:** solo LAN en v0.1; TLS con Caddy en v0.3.
- **Estructura:** tres épicas de núcleo (EP-01 db y eventos, EP-02 bus de criptografía, EP-03 seguridad) en vez de una. Aceptado por el orquestador; se confirma en el gate.

## B. Decididos por el orquestador (reversibles en el gate)

### Membresías
- **Q1 Renovar antes de vencer.** Se permite una membresía futura. Invariante corregida (`02_domain_model.md` 2.3): un socio tiene como máximo una membresía *vigente* (`active`, `expiring`, `frozen`) y como máximo una *futura* (`pending_payment` o `active` con `start_date > hoy`). Al renovar, `start_date` es el día siguiente al `end_date` de la vigente. Las fechas de dos membresías del mismo socio nunca se solapan.
- **Q2 Endpoint de renovar.** No existe `POST /memberships/{id}/renew`. Renovar es `POST /members/{id}/memberships` con `renew: true` (el service calcula `start_date`). El front llega desde `/membresias/vender?socio=:id&renovar=1`. Corrige `05_service_design.md` sección 4 y `docs/PLAN.md` Tarea 6.
- **Q3 Estado `pending_payment`.** Es visible. Se agrega el chip "Pendiente de pago" a `Membresias.html` y `Socios_Lista.html` (anotar `DESIGN-GAP` al construir; el diseño se actualiza después). Etiqueta: borde `--warning`, texto `--warning`, igual que "por vencer".
- **Q4 Planes por clases antes de v0.4.** Hasta que exista check-in, un plan por clases solo vence por fecha. `classes_remaining` se crea desde v0.1 pero solo lo descuenta `MemberCheckedIn` (v0.4). Documentado en EP-09.
- **Q5 Pagos por encima del precio.** Se permiten; no generan saldo a favor ni crédito. El front muestra una advertencia ("este pago supera el saldo pendiente en $ X") y pide confirmación. No hay regla nueva de dominio.
- **Q7 Congelar.** Admin y coach. Anular sigue siendo solo admin.
- **Q9 Límites de congelación.** Configurables en `settings.memberships`: `max_freeze_days_per_membership` (por defecto 30), `max_freezes_per_membership` (por defecto 2), `max_retroactive_days` (por defecto 7). `apply_freeze` recibe los límites como parámetro (sigue siendo pura).
- **Q11 Secciones `memberships` y `classes` de Settings.** `memberships`: `expiring_days` (por defecto 7), más los tres límites de Q9. `classes`: `default_capacity` (por defecto 15), `checkin_window_min` (por defecto 30: minutos antes y después de la hora de inicio en que se permite check-in), `allow_over_capacity` (por defecto true). RN-06 se corrige: "por vencer si faltan `expiring_days` días o menos (por defecto 7)". `compute_status(membership, today, expiring_days)`.
- **Q28 "Hoy".** El `today` de `compute_status` y de todos los jobs del worker es la fecha civil en `America/Bogota`, calculada en `core/clock.py` (`today_bogota()`). Corrige `02_domain_model.md` sección 2.3 y `04_architecture_decision.md` sección 7.

### Socios y datos personales
- **Q6 Mostrar datos en claro (`reveal`).** Admin y coach. Siempre auditado con el campo y el usuario. El socio en el portal ve sus propios datos sin enmascarar (es su información) y eso también se audita.
- **Q16 Consentimiento de socios anteriores a v0.3.** `data_consent_at` puede ser nulo. El tablero muestra "socios sin autorización registrada" desde v0.3 y la ficha lo marca. No se bloquea nada por su ausencia.
- **Q17 Formato del Excel de importación.** Plantilla fija `docs/plantillas/importar-socios.xlsx` con columnas en este orden: `documento`, `nombres`, `apellidos`, `telefono`, `correo`, `fecha_nacimiento` (AAAA-MM-DD), `sexo` (F, M, X o vacío), `contacto_emergencia_nombre`, `contacto_emergencia_telefono`, `notas`. El comando valida la cabecera y rechaza el archivo si no coincide. Idempotente por documento.
- **Q24 Campos editables en el portal.** Teléfono, correo, contacto de emergencia, preferencias de canal y contraseña. Nunca documento, nombres, apellidos, sexo ni fecha de nacimiento (eso lo corrige recepción).

### Pagos, recibos y exportaciones
- **Q15 Exportar pagos.** Sí, en v0.2 junto con exportar socios (EP-16). CSV, solo admin, auditado con el filtro usado.

### Tablero
- **Q10 "Últimos movimientos".** Las últimas 10 entradas de auditoría de las tablas `members`, `memberships` y `payments`, convertidas a frase ("Ana P. registró un pago de $ 120.000 de Juan R.", "Se vendió Plan Mensual a Laura G."). Lo arma `dashboard.service` a partir de `audit.service.recent(tables, limit)`.

### Avisos
- **Q12 Credenciales de canales.** Secretos (SMTP, token de Telegram, llaves VAPID) solo en `.env`. `settings.channels` guarda lo no secreto: canal habilitado, nombre del remitente, correo de respuesta, chat por defecto. Nunca se guarda un secreto en la base.
- **Q13 Avisos de bienvenida, activación y récord.** Fuera de v0.2. Los eventos existen pero ninguna regla los consume hasta v1.0 (push de récord al socio, EP-25). Las reglas de v0.2 solo tienen los disparadores `membership_expiring` y `membership_expired`.
- **Q14 Web push.** `WebPushChannel` y `push_subscriptions` se mueven de v0.2 a v1.0 (EP-25), que es cuando hay un navegador de socio que suscribir. En v0.2 los canales son correo, Telegram y enlace de WhatsApp. Corrige `docs/PLAN.md` v0.2 punto 5 y EP-14.

### Entrenamiento
- **Q8 Borrar una asistencia.** Admin y coach, auditado; emite `AttendanceRemoved` (devuelve la clase si el plan es por clases).
- **Q18 Unicidad de resultados con corrección.** Columna `is_current` (bool) en `wod_results`; es una de las pocas columnas con `UPDATE` permitido por el trigger (junto con las de validación). Índice único parcial sobre (`wod_id`, `member_id`) `WHERE is_current`. Corregir un resultado crea uno nuevo con `supersedes_id` y pone `is_current = false` en el anterior.
- **Q19 Movimiento principal.** `wod_movements.is_primary` (a lo sumo uno por WOD, índice único parcial). RN-12 deriva RM solo del movimiento principal y solo si `score_type = load`. Un WOD sin principal no deriva récords.
- **Q20 Récord de benchmark.** Sí: un resultado validado en un WOD `is_benchmark` que mejora la marca anterior del socio crea `PersonalRecord(kind = benchmark)` derivado. "Mejor" lo decide `leaderboard_order(score_type)`.
- **Q22 Sexo nulo en el leaderboard.** Aparece solo en el filtro "Todos"; no en "F" ni en "M".
- **Q23 Cambiar el horario con sesiones generadas.** Editar o desactivar una franja afecta solo a las sesiones que aún no se han generado. Las ya generadas se cancelan a mano una por una o con la acción "cancelar sesiones futuras de esta franja" (confirmación, motivo). Las sesiones se generan con 14 días de antelación por el job diario.
- **Q25 Grupo "Hoy" del menú.** No es una pantalla: son tres enlaces a pantallas que ya existen (`Sesiones` filtrada a hoy, `WOD_Detalle` del día, `PorAvisarHoy`). No se crea ruta nueva.

### Atleta
- **Q21 Qué medidas se cifran.** Todas las de `body_metrics` (peso, estatura, porcentaje de grasa y cualquier medida futura) bajo `athlete.metric`. Solo `measured_at` y `member_id` quedan en claro.

### Criptografía y auditoría
- **Q26 CBOM.** Se adelanta a v0.3 dentro de EP-18 (administración de llaves). `docs/PLAN.md` v1.0 punto 3 queda solo con la firma de backups.
- **Q27 ML-DSA no disponible.** La firma nocturna usa el verbo `sign` del bus con la `data_class` `audit.signature`; el algoritmo lo decide la llave registrada en `crypto_keys`. Si OpenBao no ofrece ML-DSA cuando llegue v0.3, la llave se crea con Ed25519 y se rota a ML-DSA-65 después; las firmas viejas siguen verificándose con su llave. No bloquea.

## C. Correcciones que estas decisiones imponen a documentos anteriores

Se aplican cuando el gate apruebe el paquete, en este orden:
1. `02_domain_model.md`: invariante de membresías (Q1), `compute_status` con `expiring_days` y fecha de Bogotá (Q11, Q28), `apply_freeze` con límites (Q9), `is_current` e `is_primary` (Q18, Q19), récord de benchmark (Q20), push a v1.0 (Q14).
2. `05_service_design.md`: quitar `renew` como endpoint (Q2), `reveal` para coach (Q6), secciones de settings (Q11).
3. `docs/PLAN.md`: Tarea 6 (renovar), v0.2 (push sale), v0.3 (CBOM entra), v1.0 (CBOM sale).
4. `docs/BRECHAS.md`: marcar como resueltas D3, D4 y las de sección 3 que estas decisiones cierran.
5. `docs/design/`: anotar chip "Pendiente de pago" y paginación `limit`/`offset`.

## D. Supuestos de las historias (N-01 a N-50): aceptados o corregidos

Cada supuesto quedó escrito en la historia que lo originó (`07_user_stories/README.md`, sección "Preguntas abiertas"). Aquí se decide. "Aceptado" significa que el supuesto de la historia vale tal cual; "Corregido" significa que la historia y el desglose técnico deben seguir lo que dice aquí.

### Criptografía y datos personales
- **N-01 Corregido.** No existen columnas `*_hint`. Ningún fragmento de un dato cifrado se guarda en claro. El enmascarado (`CC •••• 4417`) lo calcula el servidor en memoria descifrando el campo al leer la ficha; esa lectura queda en `crypto_ops` (verbo `decrypt`, propósito `mask`) pero no es un `reveal` de auditoría. Las listas nunca muestran datos cifrados, ni enmascarados; solo la ficha. `reveal` sigue siendo la única forma de ver el valor completo y se audita.
- **N-02 Corregido.** Normalización del índice ciego: NFKD sin diacríticos, minúsculas, sin espacios, puntos ni guiones. Teléfono: solo dígitos, sin el prefijo `57` o `+57` inicial. Correo: minúsculas y sin espacios. `CLAUDE.md` (bus, regla 5) se amplía en el gate con esta definición.
- **N-03 Aceptado.** La DEK se envuelve con AES-256-GCM bajo la KEK local; con OpenBao, lo que Transit devuelva.
- **N-04 Aceptado.** Registro de `data_class` como constante en `core/crypto/registry.py`. Firma: `apx1.<key_id>.<alg>.<sig_b64url>`.
- **N-05 Aceptado.** `crypto_ops.count`, verbo `export`, comandos `cli export-kek` y `cli verify-kek-backup`, `CryptoJob.kind = rewrap`.
- **N-06 Aceptado.** `core/audit.py` no importa `hashlib`: usa `core.crypto.bus.digest(data) -> str` (SHA-256). Es coherente con `CLAUDE.md`: `core/audit` llama a `core/crypto`, no al revés.
- **N-07 Aceptado.** La llave de índice solo se rota con `--index` explícito; la pantalla de Llaves solo rota llaves `encrypt`.
- **N-08 Corregido.** Se agrega la acción `download` a `AuditEntry.action`. Recibos y adjuntos se auditan como `download`; `export` queda para listas.
- **N-09 Aceptado** (v1.0). Las llaves de suscripción push se guardan en claro; se revisa si entra el bus para `member.push`.

### Identidad, sesiones y plataforma
- **N-10 Aceptado.** Contraseña mínima de 12 caracteres, sin otras reglas de composición; se valida contra una lista corta de contraseñas comunes.
- **N-11 Aceptado.** Activación 72 h, recuperación 1 h, 400 `invalid_token`, `FRONT_BASE_URL`.
- **N-12 Corregido.** Una sola ruta: `POST /users/{id}/resend-link` (genera token nuevo e invalida el anterior; devuelve el enlace). `GET /users/{id}/activation-link` no existe.
- **N-13 Corregido en un punto.** Refresh en cookie HttpOnly y access en memoria: aceptado. Cambiar contraseña revoca las demás sesiones: aceptado. **Reusar un refresh ya rotado revoca todas las sesiones del usuario** (es señal de robo), no solo responde 401.
- **N-14 Aceptado.** Tolerancia 30 s, `/docs` apagado en producción, `TRUSTED_PROXIES`, nonce de CSP con `$request_id`.
- **N-15 Corregido (unificado).** Existe un único usuario técnico `system@apex.local`, rol `admin`, `is_active = false` (no puede iniciar sesión), creado por la migración inicial con UUID fijo `00000000-0000-0000-0000-000000000001` y expuesto como `SYSTEM_USER_ID`. Worker, seed, importación y migraciones de proveedor lo usan como `created_by` y `user_id`. Todo comando de CLI acepta `--as <email>` para atribuir la acción a una persona cuando la ejecuta una persona. No existen usuarios `seed` ni `SYSTEM_ACTOR_ID` por variable.
- **N-16 Aceptado.** `/health` en raíz y en `/api/v1/health`; backup informativo; 503 `crypto_unavailable` con OpenBao sellado.
- **N-17 Aceptado.** `version` como control de concurrencia (409 `version_conflict`); sección futura 404 `section_not_available`.
- **N-18 Definido.** Campos: `gym` (name, nit, address, city, phone, whatsapp, email); `hours` (por día de la semana, lista de rangos `open`/`close` en hora local); `privacy` (policy_version, policy_text, retention_years por defecto 5, consent_required_from fecha o null); rangos: `expiring_days` 1 a 30, `max_freeze_days_per_membership` 0 a 180, `max_freezes_per_membership` 0 a 12, `max_retroactive_days` 0 a 30, `default_capacity` 1 a 100, `checkin_window_min` 0 a 240.

### Socios
- **N-19 Aceptado.** Documento obligatorio; teléfono y correo opcionales; `data_consent_version` vacío en v0.1; las respuestas de crear y editar llevan `warnings: []` (lista de avisos no bloqueantes). Se agrega al contrato.
- **N-20 Corregido.** Admin y coach ven socios dados de baja en la lista (chip "Dados de baja") y en la ficha en modo solo lectura; no 404. Solo admin cambia el documento (es identidad); coach edita el resto. Existe `POST /members/{id}/reactivate` (admin) desde v0.1. La baja no anula membresías.
- **N-21 Aceptado.** Propósitos `notify`, `auth_link` y `mask`; el propósito va en `after` de la auditoría.

### Planes y membresías
- **N-22 Corregido en un punto.** `DELETE /plans/{id}` es borrado lógico y falla con 409 si hay membresías en `pending_payment`, `active`, `expiring` o `frozen` (esa es la definición de "activa" para RN-08): aceptado. **El nombre del plan es único entre no borrados** (índice único parcial).
- **N-23 Aceptado.** Fin inclusivo; desfase 0 cuenta como "por vencer".
- **N-24 Corregido en un punto.** `renew: true` ignora `start_date`: aceptado. `GET /members/{id}/memberships/renewal-preview`: aceptado. **`start_date` por el API como máximo `max_retroactive_days` atrás** (por defecto 7, de Settings); el CLI de importación no tiene límite.
- **N-25 Corregido.** Las congelaciones son una entidad interna `MembershipFreeze` (tabla `membership_freezes`: `frozen_from`, `frozen_to`, `days`, `created_by`), una fila por congelación, para poder aplicar `max_freezes_per_membership`. `compute_status` recibe la lista. Si se anula el pago que cubría una membresía `frozen`, pasa a `pending_payment` y conserva sus congelaciones. Si extender el fin choca con una membresía futura, 409 `overlaps_future_membership`.
- **N-26 Aceptado.** El resumen y el tablero cuentan socios por estado resuelto.

### Pagos y exportaciones
- **N-27 Aceptado.** `paid_at` opcional (por defecto ahora), no futuro con 5 minutos de tolerancia, sin límite hacia atrás; mes por `paid_at` en Bogotá; sin cierre de caja en v1.0 (anotar como mejora v1.1: "cierre de mes").
- **N-28 Aceptado.** Se aceptan pagos sobre `expired` y `frozen`; `reference` opcional.
- **N-29 Definido.** CSV con `;` y BOM UTF-8. Socios: `nombres, apellidos, documento, telefono, correo, estado_membresia, plan, vence, creado`. Pagos: `fecha, socio, plan, monto, medio, referencia, registrado_por, anulado, motivo_anulacion`. Solo admin, auditado como `export` con el filtro usado.

### Auditoría
- **N-30 Corregido en un punto.** `GET /audit/{seq}` y `GET /audit/verify/last`: aceptados. Salto en `seq` es ruptura: aceptado. **El resultado de cada verificación se persiste en `audit.verifications`** (started_at, finished_at, through_seq, ok, broken_at_seq, triggered_by) para que un reinicio no lo pierda.
- **N-31 Corregido en un punto.** **El historial de la ficha muestra auditoría de `members`, `memberships` y `payments` del socio** (por `record_id` de sus membresías y pagos), no solo `members`. Login fallido de correo inexistente: solo log y rate limit, no auditoría.
- **N-32 Aceptado.** Firma a las 07:00 con el worker; 3 reintentos; atrasada a las 48 h.

### Avisos
- **N-33 Corregido.** Ley 1581: sin preferencia guardada, el socio solo recibe `whatsapp_link` (lo envía una persona desde "por avisar hoy") y correo únicamente si tiene `data_consent_at`. Canales automáticos requieren opt-in explícito en la ficha (v0.2) o en el portal (v1.0).
- **N-34 Corregido.** `telegram` deja de ser canal al socio: es canal **interno al equipo** (chat del gimnasio) que recibe el resumen diario de "por avisar hoy" y las alertas del worker (backup fallido, firma atrasada, OpenBao sellado). Canales al socio: `email`, `whatsapp_link`, `push` (v1.0). `NotificationRule.channel` solo admite canales al socio; las alertas internas salen de `core/alerts.py` → `TelegramChannel`.
- **N-35 Aceptado.** 3 intentos, recuperación de hasta 15 días, no avisar "vencido" a quien ya renovó.
- **N-36 Aceptado.** Correos de activación y recuperación salen directo con texto fijo.
- **N-37 Corregido.** Nada se crea "después del commit". El handler de `PersonalRecordSet` inserta la fila `Notification` en `pending` dentro de la misma transacción; el envío lo hace el job `notify` del worker. `Notification.membership_id` pasa a opcional.

### Clases y entrenamiento
- **N-38 y N-39 Corregidos.** RN-09 manda: el check-in **nunca** responde 409 ni 422 por cupo, hora ni membresía. Siempre registra y devuelve `flags: ["expired" | "no_membership" | "frozen" | "over_capacity" | "out_of_window"]`; `flagged = len(flags) > 0`. La tablet muestra la advertencia en rojo. `allow_over_capacity` se elimina de Settings; `default_capacity` y `checkin_window_min` son umbrales de advertencia.
- **N-40 Corregido en un punto.** `start_time` de la franja en hora local: aceptado (es una plantilla semanal). Devolver una clase reactiva una tiquetera `expired` si su fecha no pasó: aceptado. **Borrar una asistencia es borrado lógico** (`removed_at`, `removed_by`, `removed_reason`); unicidad por índice parcial sobre (`session_id`, `member_id`) `WHERE removed_at IS NULL`.
- **N-41 Aceptado.** Unicidad de `date` para el WOD principal; `score_type` inmutable con resultados; `PATCH /class-sessions/{id}` entra al contrato.
- **N-42 Aceptado.** Resultado registrado por coach o admin nace `validated` y emite `WodResultValidated`.
- **N-43 Aceptado.** Time cap: `seconds = time_cap_s` y `capped = true`, ordenados después de los que terminaron; `rx` y `rx_plus` comparten grupo.
- **N-44 Corregido en un punto.** Hash del token, rate limit 12 por minuto, nombre e inicial del apellido: aceptados. **El token viaja en la cabecera `X-Device-Token`**; la URL `/tv?token=…` lo recibe una sola vez, el front lo guarda en `localStorage` y limpia la query. Nginx no registra query strings de `/api/v1/tv/`.

### Atleta, portal y cierre
- **N-45 Aceptado.** Rangos de medidas, RM en kg, empate conserva el más antiguo, `scaled` no deriva RM.
- **N-46 Corregido.** Existe un catálogo `wods.benchmarks` (name único, description, score_type). Un WOD que repite un benchmark lleva `benchmark_id`; `is_benchmark` se deriva (`benchmark_id IS NOT NULL`). Los récords de benchmark y la comparación se agrupan por `benchmark_id`, no por título.
- **N-47 Aceptado.** Cuenta de portal la crea el admin; correo de login independiente del padrón; recurso ajeno 404; el socio envía resultados hasta 7 días atrás.
- **N-48 Aceptado.** Backups anteriores a v1.0 sin firma; liboqs como alternativa documentada con su debilidad; `rewrap` exige `confirm: "REENVOLVER"` y rol admin.

### Infraestructura
- **N-49 Aceptado.** Se agregan `0BSD`, `ISC` y `OFL-1.1` a la lista de licencias permitidas de `CLAUDE.md` (en el gate).
- **N-50 Aceptado.** Tabla `worker.job_runs`; backup a las 02:00 con 14 días de retención e incluye `uploads`; identidad `age` montada para verificar; OpenBao con Shamir 5 llaves y umbral 3.

### Requisito de infraestructura detectado
- La restricción "una vigente y una futura" (Q1) se implementa con `EXCLUDE USING gist` sobre el rango de fechas por socio; exige la extensión `btree_gist`, que se crea en la migración inicial.

## E. Brechas arquitectónicas del desglose técnico (G-01 a G-10) y refinamientos

Fuente: `08_implementation_breakdown/README.md`. Todas las propuestas del desglose se aceptan; las que tocan `CLAUDE.md` se aplican en el gate.

### Brechas aceptadas
- **G-01 `core/context.py`.** Archivo nuevo, solo biblioteca estándar: `SYSTEM_USER_ID`, `current_actor()`, `current_batch()`, `actor_scope()`, `batch_scope()` (contextvars). `core/audit` importa solo `core/crypto/digest.py`. Se agrega a la estructura de `CLAUDE.md`.
- **G-02 `PrincipalLoader`.** Puerto en `core/security` con `register_principal_loader()`; `auth.service.get_principal` lo registra en `create_app()`. El rol se lee de la base en cada petición; `SYSTEM_USER_ID` nunca autentica.
- **G-03 Ciclos entre services.** Regla nueva para `CLAUDE.md` (módulos, regla 2 bis): entre dos módulos, el sentido mayoritario llama al `service.py` del otro; el sentido minoritario, si solo valida, usa un puerto que registra el módulo dueño al arrancar (`payments.set_membership_gate(memberships.service.payability)`); si es una lectura de presentación, usa import perezoso dentro de la función, solo para los pares de una lista blanca en `tests/architecture/test_service_import_graph.py`. Pares permitidos en v0.1: memberships↔payments, members↔memberships, plans↔memberships; v0.4: members↔classes. Se documenta en ADR-001.
- **G-04 Lecturas a profundidad 2.** Una consulta de lectura puede recorrer aristas existentes del mapa de contextos hasta profundidad 2, por lote y sin escrituras ni eventos. `memberships.service.status_for(member_ids)` devuelve `{member_id: {status, plan_id, plan_name, end_date}}`. Se anota en `03_context_map.md`.
- **G-05 `audit_log.subject_member_id`.** Columna llenada por el hook según `__audit_subject__` del modelo (`members`: `id`; `memberships` y `payments`: `member_id`). Va en `0002_audit_log`. `payments.member_id` se copia al registrar (desnormalización aceptada para auditoría y exportación).
- **G-06 `core/jobs.py`.** Modelo `worker.job_runs` y helper `run_job(name, fn)`; lo importan solo el worker y el chequeo de salud.
- **G-07 `core/crypto/archive.py`.** `digest_file(path)` y `verify_age_archive(path, identity)` por subprocess sobre el binario `age` (BSD-3). Único sitio con hash de archivos.
- **G-08 `core/alerts.py`.** `AlertSink` Protocol y `register_sink()`; `TelegramAlertSink` vive en `modules/notifications/channels/telegram.py` y se registra en `main.py` y en el arranque del worker (v0.2). En v0.1 el único sink es el log.
- **G-09 Rotación de `attachment.sensitive`.** Puerto `Reencryptor` en `core/crypto/registry.py` y `attachments.key_id`; se implementa en EP-18 (v0.3). Hasta entonces, rotar esa clase responde 409 `rotation_not_supported`.
- **G-10** se cierra con G-03.

### Refinamientos aceptados (respuesta por defecto del desglose)
- **US-004:** se agregan `PSF-2.0`, `0BSD`, `ISC` y `OFL-1.1` a la lista permitida; `MPL-2.0` sin modificar vale para `certifi` y `axe-core`.
- **US-008:** `validate-impact-analysis.sh` acepta VERDE, APROBADO y APROBADO CON OBSERVACIONES; AMARILLO solo con `--allow-amber`; ROJO y RECHAZADO bloquean.
- **US-022:** un módulo puede importar `schemas.py` y `exceptions.py` de otro; se prohíben `models.py` y `router.py` ajenos.
- **US-024:** `crypto_keys.rotated_by` (UUID del usuario); `rotate_by` se renombra para no confundir con una fecha.
- **US-030:** una llave `retired` no descifra; el historial muestra "valor cifrado modificado" para blobs de auditoría cifrados con ella.
- **US-056:** `GET /payments/methods` (admin y coach) devuelve el enum con etiquetas.
- **US-057:** `policy_text` obligatorio; `retention_years` 1 a 20; "vigente desde" es `updated_at` de la sección.
- **US-061:** `gym_name` viaja en `GET /auth/me`; respaldo "APEX".
- **US-062:** el portal tiene 5 pestañas como el diseño (Inicio, Pagos, WODs, Progreso, Yo); "Yo" agrupa `/mi/datos` y `/mi/avisos`.
- **US-110:** se agrega `auth.users.display_name` (respaldo: parte local del correo); "últimos movimientos" excluye `SYSTEM_USER_ID`.
- **US-123:** sin preferencias guardadas no hay correo automático aunque haya consentimiento; solo `whatsapp_link` (coherente con N-33).
- **US-160:** una tiquetera que llega a 0 clases recorta `end_date` a la fecha del consumo y guarda `original_end_date`.
- **US-166:** CRUD mínimo `/benchmarks` (admin y coach) y `cli seed-benchmarks` con los benchmarks clásicos.
- **US-181:** corregir un resultado que generó un RM llena `personal_records.invalidated_at` (evento `WodResultSuperseded`); no se borra.
- **US-197:** CycloneDX es formato adicional del CBOM en v1.0.

### Contradicciones entre historias: cómo se resuelven
- Auditoría de `auth.users`: `__audit_redact__ = ("password_hash",)`; el hook reemplaza el valor por `"<redacted>"`.
- Códigos 401: `token_expired` cuando el JWT venció; `unauthorized` en cualquier otro caso (sin token, firma inválida, usuario bloqueado).
- Variables de entorno y admin inicial: manda US-011 (EP-00); las demás historias se ajustan en el desglose. Nombres: `ADMIN_EMAIL`, `ADMIN_INITIAL_PASSWORD` (un solo uso, se borra del `.env` tras el seed).
- Telegram: solo alertas internas (N-34). US-123 y US-193 se corrigen.
- Trigger de inmutabilidad de `crypto_keys`: se escribe desde `0003` con una función que admite las transiciones de estado válidas; EP-15 y EP-26 no lo reemplazan, lo extienden con migración nueva.
- Migraciones de v0.1 definitivas: las del README del desglose (`0001` a `0013`), con `seq` de auditoría asignado bajo lock, `crypto_ops.purpose`, `users.last_login_at` y `refresh_tokens.replaced_by_id`, `memberships` sin columnas `frozen_*`, `payments.member_id`.
