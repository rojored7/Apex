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

## Sprint 2 · decisiones de implementación

Fuente: `docs/ddd/blueprints/sprint-02-plan.md` (enmiendas E1 a E9) y el cuaderno `docs/scratch/sprint-02.md`. Cada slice agrega aquí lo que decidió al implementar.

### Sprint 2 · decisiones del blueprint y de la revisión de seguridad (D1–D53)

Fuente: sección 1 de `docs/ddd/blueprints/sprint-02-plan.md`, copiada tal cual, con una línea "Estado al cierre del sprint" donde el slice se desvió. Las secciones por slice (S2-W0-1 y S2-B1 a S2-B9) no cambian.

#### Decisiones del blueprint (D1 a D34) con la opción elegida

- **S2-D1:** `UserStatus` con cinco valores. Orden: `deleted > locked > inactive > pending_activation > active`.
- **S2-D2:** la auditoría usa `table_name = 'auth.users'` y la redacción `'***'`. Se corrigen la demo y US-045/US-107.
- **S2-D3:** un router plano por módulo, con la ruta completa en cada decorador. `test_list_routes_use_page_params` recorre `effective_routes(create_app(...))`.
- **S2-D4:** `auth/service.py` queda como fachada. `auth/rules.py` (puras), `auth/tokens.py` (con sesión) y `auth/cookies.py` son privados del módulo. La regla `private_helper` en `tests/architecture/_imports.py` es obligatoria, no opcional.
- **S2-D5:** `core/validators.py` define `EmailAddress` sin `email-validator`, que tiene licencia Unlicense y queda fuera de la lista.
- **S2-D6:** se usan los nombres reales del código:
  - `dummy_verify`;
  - `normalize_for_index(value, kind)`;
  - `active_admin_id_by_email` se renombra a `active_user_id_by_email`, que exige `active` y excluye `SYSTEM_USER_ID` (L-4 del Sprint 1);
  - las excepciones de dominio no tocan `core/errors.py`.
  - Estado al cierre del sprint: `active_user_id_by_email` resuelve `--as` (S2-B2); `active_admin_id_by_email` vuelve solo para `issue-reset-link`, con cuenta `active` (S2-B4).
- **S2-D7:** las escrituras auditadas van por ORM con `SELECT ... FOR UPDATE`. Hay dos excepciones, porque ninguna de las dos se audita:
  - `revoke_all` (un UPDATE masivo);
  - el incremento de `failed_login_count` (`UPDATE ... RETURNING`, L-10).
- **S2-D8:** la auditoría del login va por el evento `LoginAttempted`, con commit explícito antes del 401. El patrón actor_scope + flush + commit vive en una sola función, `auth/tokens.commit_failure(session)`.
- **S2-D9:** la migración `0005b_auth_security` (padre `0005_settings`) reemplaza la `0008` que sugería el análisis de impacto. Contenido:
  - `auth.users.must_change_password` (bool, por defecto false);
  - `auth.users.failed_login_count` (int ≥ 0, por defecto 0);
  - `auth.users.tokens_valid_after` (timestamptz, nulo; H-3);
  - `auth.refresh_tokens.family_started_at` (timestamptz NOT NULL, `server_default now()`; L-4).
- **S2-D10:** el límite por intentos queda corregido por H-4:
  1. Solo cuentan los fallos. Se comprueba el contador antes de argon2 sin sumar y se suma al fallar.
  2. Clave `(correo normalizado, ip_bucket_key)`: 10 fallos por 900 s.
  3. Tope global por cuenta: 100 fallos por 3.600 s.
  4. Bloqueo persistente (`locked_at`) a los 20 fallos consecutivos.
  5. Al último admin activo solo le rigen el límite por IP y argon2.
  6. Settings nuevas: `LOGIN_ACCOUNT_LIMIT=10`, `LOGIN_ACCOUNT_WINDOW_S=900`, `LOGIN_ACCOUNT_GLOBAL_LIMIT=100`, `LOGIN_ACCOUNT_GLOBAL_WINDOW_S=3600`, `LOGIN_LOCK_AFTER=20`.
  7. `unlock` por API limpia los contadores en memoria de esa cuenta (`ratelimit.forget`). `cli unlock-user` corre en otro proceso; el runbook documenta que `restart api` limpia la memoria.
  - Estado al cierre del sprint: aplicada con los nombres de E5 y `Settings`; el último admin queda fuera de las capas 3 a 5 y su `failed_login_count` sí sube. Ver S2-B2 y `docs/RUNBOOK.md`, "Sesión y límites".
- **S2-D11:** `refresh_current(session)` corre dentro de `current_user` tras validar el token. Se quita la dependencia global de `main.include_module_routers` (M-3 del Sprint 1).
- **S2-D12:** `ADMIN_*` solo en `tools`. `SeedSettings` lee `.env.seed`; se crea `.env.seed.example` con valores vacíos (L-9). `seed` rechaza el literal `cambiar-esto`. `seed_admin` siembra con `must_change_password=true`; `--no-force-change` solo con `ENV=dev`, leído de `Settings`.
  - Estado al cierre del sprint: `.env.example` ya no trae `ADMIN_*` (solo un comentario); `SeedSettings` lee `.env.seed` y `ADMIN_*` están en `NON_API_ENV_VARS`. Ver S2-B2.
- **S2-D13 (reemplazada por M-9):** `COOKIE_SECURE=false` por defecto en v0.1. Con `ENV=production` se exige `COOKIE_SECURE=true`, salvo `ALLOW_INSECURE_COOKIE=true` explícito (validador de `Settings`).
  - Estado al cierre del sprint: sustituida por M-9 (validador de `Settings`); el valor por defecto sigue en `false`. Ver S2-B2.
- **S2-D14:** `GET /auth/me` consulta la base: usuario más `settings.service.gym_name`.
- **S2-D15:** las secciones habilitadas son `gym`, `privacy` y `memberships`.
  - Las demás responden 404 `section_not_available`.
  - Las rutas tipadas se declaran antes que la genérica.
  - `PATCH` reemplaza la sección completa.
  - Estado al cierre del sprint: `gym`, `privacy` y `memberships` son las únicas secciones; el resto responde 404 `section_not_available`. Config se muestra en pestañas (S2-F5). Ver S2-B1.
- **S2-D16:** sí a `document_type` (`CC`, `CE`, `TI`, `PA`; por defecto `CC`), con dos correcciones de seguridad:
  - sin columna `notes` (M-5);
  - `MemberCreate.data_consent: bool`, y el servidor fija `data_consent_at = clock.now_utc()` (M-4).
  - Estado al cierre del sprint: `data_consent` es booleano (`strict=True`, LOW-5) y el servidor fija `data_consent_at`; `document_type` está en `0006_members`; no hay `notes`. Ver S2-B7 y S2-F6.
- **S2-D17:** `auth.users` no tiene nombre. La tabla y el panel usan el correo, con `// DESIGN-GAP:`; `display_name` llega con US-110.
  - Estado al cierre del sprint: Usuarios muestra el correo y no el nombre; `display_name` llega con US-110 (Sprint 4A). Ver S2-F4a.
- **S2-D18:** activar es `POST /auth/reset`: el token lleva su `purpose`, responde 204 y no inicia sesión. Nace la ruta `/cambiar-clave` con `// DESIGN-GAP:`.
  - Estado al cierre del sprint: `activate` y `reset` responden 204 sin iniciar sesión. La ruta `/cambiar-clave` (`routeTable.ts`, acceso de sesión) usa `ChangePasswordPage`, que llama a `POST /auth/me/password` con la contraseña actual; no es el formulario de restablecer. Ver S2-B4, S2-F2 y S2-F4a.
- **S2-D19:** `proveedor_local`, `sin_llaves` y `bus_listo` suben a `tests/conftest.py`. El cliente HTTP de pruebas no corre el lifespan.
- **S2-D20:** `test_no_sensitive_in_logs.py` se implementa en B7. El caso `reveal` queda como prueba aparte saltada, con dueño S3-B10 (US-074).
- **S2-D21:** `test_audited_tables` importa `models` solo si `find_spec` lo encuentra. `audit` entra en `MODULES` con `router.py` vacío. Orden final: `("auth","settings","audit","members","plans")`.
  - Estado al cierre del sprint: `audit` está en `MODULES` con `router.py` vacío; el orden final es `("auth", "settings", "audit", "members", "plans")`. Ver S2-B6. La sección de B6 dice que el router se llena "hasta US-074 (EP-17)"; eso es un error: US-074 es "mostrar dato sensible auditado" (Sprint 3), y las rutas de consulta son US-102 (Sprint 4A).
- **S2-D22:** se agregan dos dependencias, con `npm run licenses` y `NOTICE`:
  - sí a `@hookform/resolvers` (MIT), en F3;
  - `@axe-core/playwright` (MPL-2.0 sin modificar, solo desarrollo), en F5, con su línea en `scripts/ci/licenses-exceptions.txt`.
  - Estado al cierre del sprint: no se instaló `@hookform/resolvers`; el adaptador propio es `web/src/shared/lib/zodResolver.ts` (S2-F5). `@axe-core/playwright` 4.14.0 entró en S2-F5 (MPL-2.0, solo desarrollo, con su línea en `scripts/ci/licenses-exceptions.txt`); S2-F8 se hizo antes e inyectó `axe-core` directamente.
- **S2-D23:** `web/src/config/routeTable.ts` es la única tabla de rutas. `homeFor`, `canAccessRoute` y `safeNext` viven en `core/auth/routeAccess.ts` y no comparan roles con literales: `homeFor` usa `can(role, "portal.view")`, una acción nueva que solo tiene `member` en `permissions.ts`. No se amplía el `ignores` de la regla de literales (resuelve la última parte de la condición 6).
- **S2-D24:** `StatusTag` acepta `account`, con `ACCOUNT_LABELS` y `ACCOUNT_TONES`.
- **S2-D25:** `InicioPage` mínima, con `// DESIGN-GAP:`, hasta `GET /dashboard` del Sprint 3.
  - Estado al cierre del sprint: `InicioPage` mínima en S2-F2 con `// DESIGN-GAP:`. El tablero es US-108 del Sprint 4A (`SPRINT-04A.md`, S4A-B8), no del Sprint 3 como decía esta decisión; corregido en `SPRINT-02.md` y `docs/BRECHAS.md`.
- **S2-D26:** en el front `/planes` es solo para admin (`plans.view`). El API deja al coach `GET /plans?active=true` y `GET /plans/{id}` de planes activos.
- **S2-D27:** el marcador `perf` se registra en `api/pyproject.toml` (B8). La prueba de 1.000 socios corre en el gate de B8 y en `run-gates.sh`.
  - Estado al cierre del sprint (revisión de Fase 4, M4): las pruebas `perf` miden con reloj y no son gate. `run-gates.sh` y el `pytest --cov` del job `api` corren `-m "not perf"`; el job `api` tiene un paso aparte `uv run pytest -m perf -q` con `continue-on-error: true` y `timeout-minutes: 10`, que informa sin bloquear. A mano: `cd api && uv run pytest -m perf -q` (con `TEST_DATABASE_URL`), como en el gate de B8 y en V5.
- **S2-D28 (reemplazada por M-2):** gracia de 10 s en el reuso de refresh (`REFRESH_REUSE_GRACE_S=10`). Dentro de la gracia responde 401 `invalid_refresh` sin revocar la familia; fuera de ella es reuso real (N-13).
  - Estado al cierre del sprint: reemplazada por M-2; la gracia de 10 s es `REFRESH_REUSE_GRACE_S`. Ver S2-B2.
- **S2-D29 (reemplazada por M-3):**
  - `Referrer-Policy: no-referrer` en `snippets/security-headers.conf`, para todo el sitio;
  - no se crea un `location` especial para `/restablecer/`;
  - `log_format apex` sigue con `$uri`;
  - una prueba con `curl` demuestra que la línea de log de `/restablecer/<token>` no contiene el token;
  - ningún `log_format` usa `$request_uri` ni `$args`.
  - Estado al cierre del sprint: reemplazada por E4 y E9. `no-referrer` va en `location = /index.html` y en `location /`, no en el snippet común, y no hay `location` de `/restablecer/`. Ver S2-W0-1.
- **S2-D30:** `PASSWORD_MAX_LENGTH = 128` y razón `too_long` (L-5 del Sprint 1). Topes en los schemas:
  - `max_length=128` en `LoginIn`, `ChangePasswordIn` y `ResetIn.new_password`;
  - `ResetIn.token` de 20 a 200 caracteres;
  - `ForgotIn.email` hasta 254.
- **S2-D31:** `test_reveal_entry.py` usa `uuid4()` (no existe fábrica de socios en B6). En S3-B10 se cambia a la fábrica.
- **S2-D32:** sí a nombre de plan único sin distinguir mayúsculas: `uq_plans_name_alive` sobre `lower(btrim(name)) WHERE deleted_at IS NULL`, con pre-chequeo igual. Topes:
  - `price_cop` de 1 a 1.000.000.000;
  - `duration_days` de 1 a 3.650;
  - `class_count` de 1 a 1.000.
  - Estado al cierre del sprint: aplicada en `0007_plans`; el CHECK de clases se corrigió a `IS NOT NULL` (ver S2-B9).
- **S2-D33:** `session.ts` se reparte entre F2 (almacén y `restoreSession`) y F3 (refresh coordinado, logout y puente con el cliente).
- **S2-D34:** tras el 201 el alta va a `/socios` con aviso. El 409 enlaza a `/socios/{existing_id}`, que da NotFound hasta S3-B9/S3-F1. Nunca se usa `?q=<documento>`.
  - Estado al cierre del sprint: el 409 de socios enlaza a `/socios/{existing_id}` ("Ver socio existente"); esa ruta no tiene pantalla hasta S3-B9 y S3-F1 (`// DESIGN-GAP:`). Ver S2-F6.

#### Decisiones de la revisión de seguridad del diseño

- **S2-D35 (H-1):** `POST /auth/logout` se autentica por la cookie, no por el Bearer.
  - Entra en `PUBLIC_ROUTES`, que pasa a 8 rutas.
  - Lleva `rate_limit("logout")` y `require_same_origin`.
  - Revoca el refresh de la cookie si existe, siempre responde 204 y siempre borra la cookie.
  - En el front, un fallo de red o un 5xx no se presenta como éxito.
  - Estado al cierre del sprint: las ocho entradas de `PUBLIC_ROUTES` son `GET /health`, `GET /api/v1/health`, las cinco rutas de auth y `GET /api/v1/tv/today` (token de dispositivo, ya presente antes de este sprint). Ver S2-B2.
- **S2-D36 (H-2):** en v0.1, `forgot` no escribe nada.
  - Normaliza el correo y aplica `ratelimit.enforce("forgot-account", ...)` además de `rate_limit("forgot")` por IP.
  - Aplica el piso de duración de S2-D39 y deja un log sin el correo.
  - Responde siempre 204. El emisor real llega con US-131.
  - Estado al cierre del sprint: `forgot` no lee ni escribe la base en v0.1; cuenta por correo, espera el piso y responde 204. Ver S2-B4.
- **S2-D37 (H-3):** `auth.users.tokens_valid_after` corta los access ya emitidos.
  - Se fija con `date_trunc('second', now)` dentro de `revoke_all`, así lo usan cambio de contraseña, reset, cerrar sesiones, bloqueo, baja y reuso.
  - `Principal` lo recibe del cargador, y `current_user` responde 401 `unauthorized` si `iat < tokens_valid_after`.
  - Ventana residual aceptada: menos de 1 s, para tokens emitidos en el mismo segundo antes de la revocación.
  - `POST /auth/me/password` responde 200 `AccessTokenOut` (`access_token`, `token_type`, `expires_in`) con un access nuevo. El front lo reparte a las demás pestañas por `apex-auth`.
  - Estado al cierre del sprint: la ventana de menos de 1 s queda aceptada (LOW-3 de S2-B3 y LOW-1 de S2-B5). Ver esas secciones.
- **S2-D38 (M-1):** dependencia `require_same_origin` en `auth/cookies.py` para login, refresh y logout.
  - Compara `Origin` (o `Referer` si falta) con `AUTH_ALLOWED_ORIGINS`; si esa lista está vacía, usa el origen de `FRONT_BASE_URL`. También acepta `Sec-Fetch-Site: same-origin|none`.
  - Sin ninguna de las tres cabeceras responde 403 `forbidden` sin tocar la cookie.
  - Los scripts de smoke y la fixture `cabeceras` envían `Origin`.
  - Estado al cierre del sprint: `require_same_origin` solo en login, refresh y logout (las rutas con cookie); `forgot` y `reset` no la llevan. Ver S2-B4.
- **S2-D39 (M-6):** se nivela el tiempo de login y forgot.
  - Piso `LOGIN_MIN_DURATION_MS`; se mide en B2 como 1,5 veces la mediana de argon2 más commit dentro del contenedor y se fija su valor por defecto.
  - Se aplica a toda respuesta 401 de login y a todo forgot, con un `sleeper` inyectable para que las pruebas no duerman.
  - Un usuario sin hash (pendiente) usa `dummy_verify`, nunca `verify_password(None, ...)`.
  - Estado al cierre del sprint: `LOGIN_MIN_DURATION_MS=75`, medido en S2-B2 y fijado en `Settings` y `.env.example`.
- **S2-D40 (M-7):** un solo predicado `rules.account_may_authenticate(user)` y su espejo SQL `rules.AUTH_FILTER`, usados por el cargador, login y refresh.
  - `is_one_time_token_usable` reutiliza el predicado, excepto la exigencia de hash cuando el propósito es `activate`.
  - `status_filter` es el espejo SQL de `user_status`. Ambos se prueban en matriz contra los cinco estados.
- **S2-D41 (M-8):** el `q` de las listas (`/socios` y `/sistema/usuarios`) vive en estado local con debounce y nunca en la URL. En la URL quedan solo filtros, `sort`, `limit` y `offset`.
- **S2-D42:** los LOW de la revisión del diseño, todos dentro del sprint:
  - **L-1:** límite por usuario autenticado de 60 por minuto en `POST /members` (B7) y en `GET /members` con `q` (B8).
  - **L-2:** `CreateUserIn.role` es `Literal["admin","coach"]`, sin `member_id`, hasta el portal (B3).
  - **L-3:** un documento, teléfono o correo que se normaliza a vacío da 422 con `field` (B7).
  - **L-4:** tope absoluto de 30 días por familia (`REFRESH_ABSOLUTE_TTL_DAYS=30`, desde `family_started_at`) y purga oportunista en cada login de los refresh del usuario vencidos hace más de 30 días (B2).
  - **L-5:** `safeNext` rechaza `\` y caracteres de control (F2).
  - **L-6:** los mensajes de `apex-auth` llevan secuencia monótona, y un `token` se ignora tras un logout (F3).
  - **L-7:** las mutaciones con `activation_url` usan `gcTime: 0` y `reset()` al cerrar el panel o el modal (F4a, F4b).
  - **L-8:** `LoginAttempted` lleva `ip` y `user_agent` (hasta 120 caracteres) y la fila `login` los guarda en `after`, nunca el correo tecleado (B2, B6).
  - **L-9:** el ejemplo de `.env.seed` va vacío y `seed` rechaza el literal del ejemplo (W0-1, B2).
  - **L-10:** el incremento de fallos es atómico (B2).
  - **L-11:** un almacén por tipo de clave (`ip`, `account`, `account-global`, `user`), cada uno con tope propio y expulsión O(1) con `OrderedDict` (B2).
  - **L-12:** `client_max_body_size 16k` en `/api/v1/auth/` (W0-1); `rate_limit` en refresh, reset y logout (B2, B4); un 429 no limpia la sesión del front (F3).
  - **L-13:** `resend-link` responde 409 `user_not_eligible` sobre la propia cuenta del emisor y sobre otros admins activos con contraseña. Para esos casos, `cli issue-reset-link <correo> --as <correo>` (B4). `PasswordChanged` lleva `via_link_issued_by` (el `created_by` del token) y la auditoría lo registra (B6).

#### Contradicciones de contrato cerradas (exploración e impacto, condición 6)

- **S2-D43:** el login emite `LoginAttempted` y `audit` se suscribe. Se corrige US-107 T1.
  - Estado al cierre del sprint: el login emite `LoginAttempted`, `audit` se suscribe y la auditoría es fail-closed (MEDIUM-1 de S2-B6). Ver S2-B6.
- **S2-D44:** el cliente usa `credentials: "same-origin"`. Se corrigen US-042 T12 y US-044 T6.
  - Estado al cierre del sprint: el cliente usa `credentials: "same-origin"`; los desgloses de US-042 y US-044 están corregidos. Ver S2-F3.
- **S2-D45:** las funciones canónicas de settings son `settings.service.memberships_policy()`, `current_privacy_version()` y `gym_name()`. Se corrigen las referencias de US-089 y US-149.
  - Estado al cierre del sprint: `memberships_policy()`, `current_privacy_version()` y `gym_name()` existen en `settings/service.py`; `get_section` queda como lectura de la ruta genérica. Ver S2-B1.
- **S2-D46:** la ruta canónica en v0.1 es `POST /api/v1/auth/me/password`, no `/me/password`. Se anota en `docs/BRECHAS.md`.
  - Estado al cierre del sprint: `POST /api/v1/auth/me/password` responde 200 `AccessTokenOut` en `docs/openapi.json`. Ver S2-B3.
- **S2-D47:** no existe `/auth/activate`; las rutas públicas exactas son `login`, `refresh`, `logout`, `forgot` y `reset`.
  - Estado al cierre del sprint: `logout` es público y se autentica por la cookie (S2-D35, H-1), no por Bearer como decía el blueprint. Ver S2-B2 y S2-B3.
- **S2-D48:** la rama real es `feat/sprint-02-identidad-config-socios-planes`. Se corrige `SPRINT-02.md`.
  - Estado al cierre del sprint: rama real `feat/sprint-02-identidad-config-socios-planes`; `SPRINT-02.md` corregido.
- **S2-D49:** la revocación de sesiones queda auditada por `SessionsRevoked`, porque `refresh_tokens` no se audita. `last_login_at` sale de la auditoría por `__audit_exclude__`; la fila `login` la deja el evento.
  - Estado al cierre del sprint: `SessionsRevoked` también se emite con `revoked = 0` en `delete_user` y `lock`, no solo en `revoke_sessions`. Ver S2-B5.
- **S2-D50:** el login muestra "APEX", porque `gym_name` solo llega autenticado. Va con `// DESIGN-GAP:`.
- **S2-D51:** el comando de desarrollo de uvicorn sigue sin `--proxy-headers`. La IP real la resuelve `core/ratelimit.client_ip` con `TRUSTED_PROXIES`. Se documenta en el runbook.
- **S2-D52:** CI gana el job `e2e-stack`. No se renombra ningún check protegido.
- **S2-D53:** existe `tests/architecture/test_service_import_graph.py` (nace en B3). Exige un grafo acíclico entre los `service.py` (`audit → auth → settings`) y deja la lista blanca de imports perezosos vacía hasta el Sprint 3.
  - Estado al cierre del sprint: `tests/architecture/test_service_import_graph.py` existe y `LAZY_IMPORT_WHITELIST` está vacía hasta el Sprint 3.

### S2-W0-1 · Infraestructura
- **Subred fija `172.30.0.0/24` (M-1).** Verificada libre con `docker network inspect` de las 11 redes del host (las demás usan 172.17 a 172.25 /16); no hizo falta la alternativa `172.31.0.0/24`. `web` (Nginx) queda en `172.30.0.10`, fuera de `ip_range: 172.30.0.128/25`, para que ningún contenedor con IP dinámica pueda tomarla. `TRUSTED_PROXIES=172.30.0.10/32` en `.env.example` y en el `.env` local; `test_compose_config.sh` exige que coincida con `ipv4_address` de `web` y `compose-smoke.sh` lo comprueba contra el contenedor real. Rollback: quitar `networks` e `ipv4_address` de `infra/compose.yml`, volver `TRUSTED_PROXIES` y `down`/`up` del proyecto (sin `-v`).
- **`.env.seed` solo para `tools` (M-8, D12, L-9).** `tools.env_file: [../.env, {path: ../.env.seed, required: false}]` (Compose v5.0.2, el mínimo es 2.24); api, worker y db no lo leen. `.env.seed.example` va versionado y vacío (`!.env.seed.example` en `.gitignore`; `check-key-files.sh` lo permite y bloquea `.env.seed`). `ADMIN_EMAIL` y `ADMIN_INITIAL_PASSWORD` quedan como líneas vacías en `.env.example` solo mientras `Settings` las declare (`test_env_example`); B2 las pasa a `SeedSettings` y las quita (estado al cierre: retiradas de `.env.example` en B2, que solo deja un comentario; ver S2-D12). El smoke y el job `e2e-stack` generan un `.env.seed` efímero con contraseña aleatoria.
- **`limit_req` fijo en el borde (M-3, E5, E9).** `limit_req_zone $binary_remote_addr zone=apex_auth:10m rate=60r/m` y `limit_req zone=apex_auth burst=30 nodelay` en `location /api/v1/auth/`, con `client_max_body_size 16k` (L-12) y el 429 de Nginx en el envelope del api (`rate_limited`, `Retry-After: 60`, `no-store`). Valor fijo para todos los entornos, sin `NGINX_AUTH_RATE` por `envsubst`: parametrizarlo cambiaría el `entrypoint` de la imagen web, y el perfil E2E solo necesita subir los límites del api (por `.env`, E5). Los E2E iban a reutilizar la sesión con `storageState` y la decisión se reabriría con datos si V4 chocaba con el borde: chocó, y quedó sustituido en V4 por el perfil E2E del borde (`infra/compose.e2e.yml`) con login por prueba; ver S2-V. Las respuestas 429 del propio api pasan tal cual.
- **Referrer-Policy por location (E4, E9; reemplaza el texto de S2-D29).** Sale de `snippets/security-headers.conf`. `no-referrer` en `location = /index.html` (responde toda la SPA, incluida `/restablecer/<token>`) y en `location /`; `strict-origin-when-cross-origin` en `/assets/`, `/fonts/`, `/brand/`, `@rate_limited` y `proxy-api.conf` (todo `/api/`). No existe un location de `/restablecer/`. `test_nginx_conf.sh` exige la partición y que ningún location quede sin la cabecera.
- **Cabeceras del api y CSP (L-1).** `proxy-api.conf` agrega `Cache-Control: no-store` y `Pragma: no-cache`; la CSP del api pasa a `default-src 'none'; frame-ancestors 'none'; form-action 'none'` y la del index suma `form-action 'self'`.
- **Log sin query strings (M-3, M-8, US-048).** `log_format apex` sigue con `$uri`: la línea de `/restablecer/<token>` queda como `/index.html` y `q` nunca se escribe; lo prueban con Nginx real `test_nginx_conf.sh` (contenedor desechable) y `headers.sh` (stack). Esa prueba encontró que con `error_log ... error` un fallo del upstream escribía la línea de la petición con su query; el `error_log` pasa a `crit` y `limit_req_log_level warn` deja los rechazos fuera del log. Costo aceptado: el log de Nginx ya no detalla los fallos de conexión al api (el 502 sigue en el access log y el api registra los suyos).
- **Job `e2e-stack` (S2-D52, US-068).** Levanta `infra/compose.yml` con `--build` (sin la capa de desarrollo), corre Playwright `--project=stack` con `E2E_BASE_URL` y sube `web/test-results/captures/`. `web/playwright.config.ts` tiene los proyectos `preview` y `stack`; con `E2E_BASE_URL` no arranca `webServer`. `npm run e2e` queda en `preview` (lo usa el job `web`) y `npm run e2e:stack` en `stack`.

### S2-B1 · Configuración del gimnasio
- **El coach recibe 403 en las ocho rutas de `settings` (plan B1.3, S2-D14).** Incluye `GET /settings/gym`; el coach lee el nombre del gimnasio por `GET /auth/me`, que llamará a `settings.service.gym_name(session)` (respaldo `"APEX"`). Las ocho rutas declaran `require_role("admin")`.
- **`EmailAddress` propio en `api/src/app/core/validators.py` (blueprint, decisión 5).** Sin `email-validator` (licencia Unlicense, fuera de la lista) ni `dnspython`: `Annotated[str, StringConstraints(strip_whitespace=True, to_lower=True, max_length=254), AfterValidator(check_email_shape)]` con la forma `^[^@\s]+@[^@\s]+\.[^@\s]+$` (un `@`, sin espacios, dominio con punto). El `ValueError` no repite el valor. Pruebas puras en `api/tests/core/test_validators.py`. Lo usan `settings` (`gym.email`) desde ya y `auth` y `members` en sus slices.
- **Lectura con `SECTION_VIEWS`.** `SECTION_REGISTRY` sigue con los tres esquemas de escritura (lo exige `test_settings_no_secrets`); `SECTION_VIEWS` es el mismo mapa salvo `privacy → PrivacyView`, para que `get(session, privacy)` y `current_privacy_version` funcionen con la política aún sin publicar (versión y texto `None`).
- **Primer guardado concurrente.** El `IntegrityError` del savepoint se traduce a `VersionConflict` solo si nombra `uq_settings_sections_key`; cualquier otra violación sube como error inesperado (500 sin detalle).
- **`updated_at` con la hora del servidor.** Sale de `server_default`/`onupdate = now()` del mixin y se relee con `session.refresh(fila, ["updated_at"])` tras el flush; no se fija con el reloj de la app.

### S2-B2 · Sesión: login, refresh y logout
- **S2-D9 son cuatro columnas, no dos (H-3, L-4).** `0005b_auth_security` agrega `auth.users.must_change_password`, `failed_login_count` (con `ck_users_failed_login_count_non_negative`), `tokens_valid_after` y `auth.refresh_tokens.family_started_at` (`NOT NULL DEFAULT now()`; el default solo llena las filas previas: el api lo escribe siempre con su reloj y la rotación lo hereda). `0004` y `0005` no se tocan.
- **Dos granularidades de clave de red (E9, H-4).** `rate_limit` por IP usa la IPv4 exacta (`ip_bucket_key(ip, ipv4_prefix=32)`) e IPv6 por /64; el límite por cuenta usa `"{correo}|{red}"` con /24 en IPv4 y /64 en IPv6. Una IPv4 mapeada en IPv6 (`::ffff:a.b.c.d`) cuenta como su IPv4 (revisión de seguridad, LOW-3).
- **Tope global por correo `LOGIN_ACCOUNT_GLOBAL_LIMIT=100` / `LOGIN_ACCOUNT_GLOBAL_WINDOW_S=3600` (H-4.2).** No estaba en la lista de E9; son variables nuevas de `Settings` con su línea activa en `.env.example`. El límite por cuenta y el global se comprueban con `enforce(count=False)` antes de argon2 y se suman con `record` solo al fallar; el último admin activo queda fuera de ambos y del bloqueo, pero su `failed_login_count` sube.
- **Casos del blueprint reemplazados por H-1.** "Logout sin access da 401" y "un token de otro usuario no se revoca" ya no aplican: el logout se autentica por la cookie, es público (8 rutas en `PUBLIC_ROUTES`) y siempre responde 204 borrando la cookie.
- **M-9 como validador de campo.** El validador de `COOKIE_SECURE` (con `ALLOW_INSECURE_COOKIE` declarada antes, porque la lee) nombra la variable en el `ConfigError`; reemplaza el `logger.warning` del lifespan que proponía el blueprint. `tests/core/test_startup_failure.py` construía `Settings` de producción sin `COOKIE_SECURE` (llamador de E3 que el Rojo no listó): se le agregó `COOKIE_SECURE=true`.
- **`LOGIN_MIN_DURATION_MS=75` medido (S2-D39).** Mediana de `verify_password` (3 / 65536 / 4) más commit dentro del contenedor `api`: 47,8, 46,6 y 58,8 ms en tres corridas de 30; 1,5 veces unos 48 ms da 72, redondeado a 75 (`docs/RUNBOOK.md`). El piso se espera después del commit del fallo.
- **Motivo del fallo.** Contraseña errada sobre una cuenta con hash es `bad_password` (suma el contador aunque la cuenta esté bloqueada o inactiva); con la contraseña correcta el motivo es el estado (`locked`, `inactive`); sin hash es `pending` con `dummy_verify`. Inexistente, técnico y borrado no emiten evento.
- **Columnas fuera de la auditoría con `UPDATE` directo.** `failed_login_count` (`UPDATE ... RETURNING`, L-10), `last_login_at` y el reinicio del contador (`tokens.record_success`) y `tokens_valid_after` (`revoke_all`) van por sentencia, no por el ORM: están en `__audit_exclude__` y así una sesión con el `User` en memoria nunca deja de escribir un cambio. `locked_at` del bloqueo sí va por el ORM (queda auditado).
- **Purga de L-4.** Cada login borra los refresh del usuario vencidos hace más de 30 días, salvo los que un sucesor aún vigente referencia por `replaced_by_id` (la FK lo exigiría).
- **Rotado dentro de la gracia sin borrar la cookie (revisión de seguridad, MEDIUM-1).** La petición concurrente que pierde recibe 401 `invalid_refresh` sin `Set-Cookie`: la ganadora ya entregó la cookie nueva y borrarla cerraría la sesión que acaba de rotar (`InvalidRefresh.clear_cookie`). Fuera de la gracia y en todo otro 401 de refresh la cookie se borra.
- **Riesgos aceptados de la revisión.** El corte `iat < tokens_valid_after` en segundos enteros deja menos de 1 s de ventana (S2-D37, ya aceptado; las pruebas fijan que `iat` igual pasa). El último admin exento responde 401 donde otra cuenta ya daría 429 y no tiene tope por cuenta (S2-D10); lo compensan el límite por IP, la política de contraseña y `must_change_password`; una alerta por volumen de fallos queda para `core/alerts` (Sprint 4A).
- **Keyring en `current_user` (S2-D11).** `main.refresh_keyring` y su dependencia en `include_module_routers` se quitan; `current_user` llama `keyring.refresh_current(session)` solo tras validar el token y el corte. Login, refresh, logout y un token inválido no leen `crypto_keys`.
- **`--as` del CLI.** Solo cuentas en estado `active` (`active_user_id_by_email` con `AUTH_FILTER`; reemplaza a `active_admin_id_by_email`). El mensaje distingue "no está activa" de "no existe" sin repetir el correo.
- **Almacenes del límite.** Cada tipo de clave (`ip`, `account`, `account-global`, `user`) tiene su almacén con tope `RATE_LIMIT_MAX_KEYS`, fijado en `create_app` con `configure_store_limits`; `app.state.rate_limits = rate_limits_from(settings)` da los topes por IP de las rutas.
- **`scripts/ci/test_compose_config.sh`.** Pasa de "ADMIN_* vacías en `.env.example`" a "`.env.example` no trae ADMIN_*" (M-8).

### S2-B3 · Mi cuenta y usuarios
- **Desviaciones del Rojo aceptadas.** El recorrido de M-8 y la prueba de listas usan `app.core.security.effective_routes` (que ya recorre `effective_route_contexts` de FastAPI) en vez de una `effective_route_contexts()` propia de las pruebas. Helpers puros que no estaban en la lista: `rules.escape_like`, `rules.user_row`, `rules.user_out`, la constante `RESET_PATH` y `LIKE_ESCAPE`. `create_user(session, *, email, role, by, front_base_url)` arma la URL en el service y no recibe `member_id` (L-2 manda sobre el blueprint); `change_password(..., current_refresh, policy)` recibe la política para el `expires_in` del access nuevo. Los casos de `issue_one_time_token` viven en `tests/auth/test_create_user.py`.
- **`require_role` revisa el rol antes que `must_change_password`.** Un rol ajeno sigue siendo 403 `forbidden`; el 403 `password_change_required` (sin `field`) sale antes de validar el cuerpo porque FastAPI resuelve las dependencias primero. Exentas: `GET /auth/me` y `POST /auth/me/password` (`allow_pending_password=True`); `POST /auth/logout` es pública desde H-1.
- **`auth.rules.validate_password_policy(field=...)` es la única política.** `service.validate_password_policy` (B2, `field="password"` fijo, la usan `seed_admin` y el CLI) delega en ella. La regla "distinta de la actual" cuesta un argon2 y solo se evalúa si la longitud y la lista ya pasaron; corre en `anyio.to_thread`.
- **`change_password` con `SELECT ... FOR UPDATE` del usuario.** Dos cambios simultáneos se serializan y el segundo verifica la actual contra el hash ya cambiado. La cookie solo protege su sesión si el refresh es del mismo usuario (`_own_refresh_id`).
- **`active_sessions` en una consulta agregada por página** (`GROUP BY user_id` sobre los ids de la página, con el reloj de la app), no un `LEFT JOIN` dentro del `select` de `paginate` (que pagina una sola entidad).
- **`core.pagination.paginate` tipa `stmt: Select[T]`.** SQLAlchemy 2.1 tipa `select(User)` como `Select[User]` (TypeVarTuple); la firma `Select[tuple[T]]` de US-019 no admitía ninguna consulta real. Primer llamador real: `list_users`.
- **Carrera del alta.** El pre-chequeo da `EmailTaken(existing_id)`; si dos altas lo pasan, `uq_users_email_alive` decide dentro de `begin_nested()` y el `IntegrityError` se traduce a `EmailTaken` solo si nombra ese índice (su `existing_id` es el de la ganadora o nulo). `created_by` del token es el actor vigente (`get_actor`).
- **Redacción (blueprint 7.2).** `redact_text` cambia el segmento que sigue a `/restablecer/` (también `%2Frestablecer%2F`, sin distinguir mayúsculas) y el valor de `apex_refresh=` (conserva los atributos de la cookie); `SENSITIVE_KEYS` suma `activation_url`, `url` y `set-cookie`. Ningún log del service lleva el token ni la URL.
- **Revisión de seguridad del slice (`security-reviewer`, sin CRITICAL).**
  - HIGH-1 corregido: `POST /auth/me/password` no tenía límite y cada intento cuesta hasta tres argon2. Ahora lleva `rate_limit("change-password", 10)` por IP (10 por minuto, `CHANGE_PASSWORD_IP_LIMIT` en el router) y un tope por usuario de 5 fallos de la contraseña actual en 900 s (`CHANGE_PASSWORD_USER_LIMIT`, almacén `user`), comprobado antes de argon2 y sumado solo al fallar. Son constantes y no variables de `Settings`, para no abrir `.env.example` en este slice. Pruebas en `tests/auth/test_change_password_limits.py`. Riesgo aceptado: un fallo de la actual no suma `failed_login_count` ni bloquea la cuenta; quien lo intenta ya tiene un access válido, y el tope por usuario corta la adivinanza.
  - MEDIUM-2 corregido en parte (`FOR UPDATE` del usuario). Riesgo aceptado: un `refresh` de otra sesión que rota justo mientras corre `revoke_all` inserta un sucesor que el `UPDATE` no ve. Esa sesión sobrevive hasta que el usuario cierre sesiones (B5). Bloquear también al usuario en `refresh` exige un orden de locks usuario → token en todo B2, y se revisa con `revoke_sessions` en B5.
  - MEDIUM-3 aceptado: `EmailTaken.existing_id` es contrato (el `Field` del diseño enlaza a la cuenta existente) y solo lo recibe un admin. El envelope no se registra en los logs.
  - LOW-4 aceptado (ya era S2-D37): ventana de menos de 1 s por el corte en segundos enteros.
  - LOW-5 corregido: el enlace codificado `%2Frestablecer%2F<token>` también se redacta.

### S2-B4 · Activación, recuperación y reenvío
- **Desviaciones del Rojo aceptadas.** `forgot(session, email, *, ip, policy)` en vez de un `sleeper` por parámetro: la espera usa el sleeper de `configure_sleeper` (el mismo de login, que `sleeper_nulo` ya anula) y el piso sale de `policy.min_duration_ms`. `service.issue_link` es nuevo: el CLI necesita emitir sin L-13 y solo puede llamar al `service.py` (regla `private_helper`). `RESET_IP_LIMIT=10` (E5): el 429 de `reset` llega en el undécimo por IP, no en el sexto. `FORGOT_ACCOUNT_WINDOW_S=3600` (el encargo no fijaba la ventana). El parámetro de la ruta es `{user_id}` (`{id}` sombrea el builtin, A002). `forgot` y `reset` no llevan `require_same_origin`: no usan la cookie (S2-D38 cubre login, refresh y logout). Las públicas de auth son cinco con logout (S2-D47 manda sobre el blueprint).
- **`forgot` no lee la base.** Sin emisor (US-131) no hay nada que hacer con la cuenta; no consultarla quita de raíz la diferencia de tiempo entre un correo existente y uno inexistente. Normaliza, cuenta en `forgot-account` (todo intento, 5 por 3600 s, desde cualquier IP), espera el piso y deja el log "forgot recibido" sin el correo. El 429 por cuenta sale antes del piso: no distingue cuentas porque cuenta igual exista o no.
- **Elegibilidad del enlace por estado.** `resend_link` e `issue_link` solo emiten para `active` o `pending_activation`; bloqueado, borrado e **inactivo** dan `UserNotEligible` (el blueprint nombraba solo bloqueado y borrado; un inactivo no podría usar el enlace). L-13 se aplica después: la propia cuenta y otro admin `active` (con hash) dan 409; un admin pendiente recibe `activate`.
- **CLI `issue-reset-link`.** `--as` es obligatorio y debe ser un admin activo (`service.active_admin_id_by_email`, nombre que B2 había retirado y vuelve con este único uso); el correo objetivo se resuelve con `ids_by_email` (sin borrados), así inexistente, borrado, bloqueado e inactivo salen con 2 y el mismo mensaje, sin repetir el correo. Imprime una línea de propósito y vencimiento y la URL una sola vez.
- **`activate` sobre una cuenta con hash sigue siendo usable (decisión del Rojo, S2-D40).** Con el cierre de enlaces de MEDIUM-1 ya no queda vía para que un `activate` abierto conviva con una contraseña fijada por otra ruta.
- **Revisión de seguridad del slice (`security-reviewer`, sin CRITICAL ni HIGH).**
  - MEDIUM-1 corregido: fijar la contraseña por enlace (`reset`, cualquier propósito) o cambiarla en "Mi cuenta" cierra por ORM (auditado) todos los enlaces abiertos del usuario, de cualquier propósito (`tokens.close_open_one_time_tokens`). Un bloqueo no los cierra: un bloqueado no puede usarlos (`is_one_time_token_usable`) y el desbloqueo de S2-B5 debe cerrarlos (queda anotado para B5). Pruebas en `tests/auth/test_one_time_token_closure.py`.
  - LOW-1 corregido: `reset` bloquea en el orden usuario → token (lee el `user_id` del token sin candado, bloquea el usuario y luego el token con `populate_existing`), el mismo de `resend_link`, `issue_link` y `change_password`. Prueba de `reset` y reenvío concurrentes sin interbloqueo.
  - LOW-2 aceptado (ver el punto de `activate`).
  - LOW-3 aceptado (ya era S2-D37): ventana de menos de 1 s por el corte en segundos enteros.
  - LOW-4 aceptado y anotado para US-131: el tope por cuenta de `forgot` permite gastar la cuota de un correo ajeno; hoy no tiene efecto porque `forgot` no envía nada. Cuando haya emisor, el tope debe contar emisiones reales o no frenar el envío legítimo.
  - INFO: un admin bloqueado no se recupera con `issue-reset-link` hasta desbloquearlo; documentado en `docs/RUNBOOK.md`.

### S2-B5 · Ciclo de vida del usuario
- **Desviaciones del Rojo aceptadas.** La segunda baja (`DELETE` sobre una cuenta ya borrada) da 404 `user_not_found`, no es idempotente: coherente con `update_user`, que da 404 sobre una borrada. `SessionsRevoked` se emite también con `revoked = 0` en `delete_user` y `lock` (el plan solo lo pedía para `revoke_sessions`): toda revocación administrativa queda auditada (S2-D49), como el bloqueo automático de B2. `unlock` cierra los enlaces de un solo uso abiertos (S2-B4, MEDIUM-1). El CLI `unlock-user` da un solo mensaje para cuenta no bloqueada, inexistente y borrada, sin repetir el correo (como `issue-reset-link`). Las pruebas de "un handler falla" usan `HandlerRoto` (con `RuntimeError` pasaban sobre los stubs). Ayuda de pruebas nueva `tests/auth/_ciclo.py`.
- **Candados del último admin.** `update_user` (con `role`), `delete_user` y `lock` toman primero `tokens.lock_active_admins` (`ORDER BY id FOR UPDATE` de los admins activos) y luego la cuenta objetivo (`get_alive_or_404(for_update=True)`). En READ COMMITTED la segunda transacción reevalúa el filtro tras el commit de la primera y ve el conjunto ya reducido: dos bajas de los dos únicos admins dejan exactamente uno. Bloquear al objetivo antes que el conjunto daría un interbloqueo entre dos bajas cruzadas.
- **`refresh` bloquea el usuario antes que el token (cierra el riesgo diferido de B3 MEDIUM-2).** `_locked_refresh_and_owner` lee el `user_id` del token sin candado, toma `FOR UPDATE` del usuario y luego del token con `populate_existing`, el orden de `reset`. Toda revocación (`revoke_sessions`, `lock`, `delete_user`, `change_password`, `reset`) toma el usuario antes que sus refresh, así que rotación y revocación se serializan en el usuario y un sucesor creado durante la revocación no sobrevive (prueba de seis rondas en `test_revoke_sessions.py`). `logout` sigue bloqueando solo su token: revoca esa fila y nada más.
- **`update_user`.** `None` y un valor igual al actual (el correo comparado ya normalizado) no cambian nada: un `PATCH {}` responde 200 sin fila de auditoría. Con cambio de rol, `validate_user_role` con el `member_id` actual y luego `LastAdmin`; después el pre-chequeo del correo (`EmailTaken` con `existing_id`) y la escritura dentro de `begin_nested()`, donde `uq_users_email_alive` decide la carrera.
- **`unlock` y los contadores en memoria.** `ratelimit.forget` sobre `login-account` (todas las subclaves `correo|red`) y `login-account-global` (`kind="account-global"`) corre al final del service, tras escribir en la base. El CLI corre en otro proceso y no alcanza la memoria del api: documentado en `docs/RUNBOOK.md` (`up -d api`).
- **Corrección objetiva de una prueba del Rojo.** `test_revoke_sessions.py::test_revocar_y_refrescar_a_la_vez_no_deja_ninguna_sesion_viva` pedía `argon2_rapido` en vez de `seguridad`: su `login` firma un access y, corrida sola, daba `StartupError` (llaves JWT sin configurar); en la suite pasaba solo por el orden. Ahora pide `seguridad` (que ya incluye `argon2_rapido`); la aserción no cambia.
- **Revisión de seguridad del slice (`security-reviewer`, sin CRITICAL ni HIGH).**
  - MEDIUM-1 corregido: el bloqueo automático por fallos (B2) no participaba del candado del último admin; dos fallos simultáneos sobre los dos únicos admins, cada uno con `lock_after - 1` fallos, los bloqueaban a ambos (cada login veía dos admins y ninguno quedaba exento). `_register_failure` toma ahora `tokens.lock_active_admins` antes del `UPDATE` de `increment_failures` cuando la cuenta es un admin activo (orden admins → usuario, el de `lock` y `delete_user`; tomarlo después daría un interbloqueo) y recalcula la exención con `would_remove_last_admin`. Prueba en `tests/auth/test_auto_lock_last_admin.py` (roja antes del arreglo: los dos quedaban bloqueados).
  - LOW-3 corregido: cambiar el correo (`update_user`) cierra por ORM, auditado, los enlaces abiertos de la cuenta: uno entregado al correo anterior deja de servir. Un cambio solo de rol no los toca. Las sesiones no se revocan (quien corrige un correo no presume una cuenta comprometida; para eso está "Cerrar sesiones"). Pruebas en `tests/auth/test_update_user_email_links.py`.
  - LOW-1 aceptado (ya era S2-D37): un access emitido en el mismo segundo del corte de `revoke_sessions` sobrevive hasta su vencimiento (15 min); `lock` y `delete` no tienen esa ventana porque el cargador ya rechaza la cuenta. Cambiar la comparación a `<=` rompería el access nuevo que `change_password` emite en el mismo segundo.
  - LOW-2 aceptado: un login concurrente con `revoke_sessions` puede crear un refresh posterior al corte; exige conocer la contraseña, con la que se podría entrar igual justo después. `lock` y `delete` no tienen la ventana (`is_refresh_usable` y `AUTH_FILTER`).
  - LOW-4 aceptado (informativo): `lock` y `delete_user` de un coach o socio también toman el candado de los admins; solo es contención, sin interbloqueo, y leer el rol antes sin candado para evitarlo obligaría a revalidar.

### S2-B6 · Auditoría de eventos de seguridad
- **`PasswordChanged` sí tiene suscriptor (L-13 manda sobre el blueprint 7.5).** El blueprint decía "sin suscriptores en v0.1"; L-13 pide que la auditoría registre `via_link_issued_by` (el `created_by` del enlace). `on_password_changed` deja un `update` sobre `auth.users` con `after = {event: "PasswordChanged", via, via_link_issued_by}` (UUID como texto, o `null` en un cambio desde "Mi cuenta"), atribuido a `by`.
- **Las filas de evento son `update` con `after.event`.** `UserLocked`, `SessionsRevoked` y `PasswordChanged` dejan una fila `update` propia, con `before = null` y un `after` cerrado (`event`, `reason`, `revoked`, `via`, `via_link_issued_by`), además del `update` que ya deja el hook ORM de las columnas auditadas (dos filas por bloqueo, a propósito). Las pruebas de B3 a B5 que contaban "los `update` de `auth.users`" esperando solo la fila del hook filtran con `es_update_del_hook` (`tests/auth/_cuentas.py`) y siguen exigiendo exactamente una.
- **Fila `login` (L-8, S2-D43).** `action = "login"`, `record_id` y `user_id` del propio usuario, `before = null`, `after = {result, reason, ip, user_agent}` (`reason = null` en el éxito; `user_agent` ya truncado a 120 por `auth`). Nunca el correo tecleado; un correo inexistente no emite evento y no deja fila (N-31). La fila del fallo sobrevive al 401 porque `auth` hace commit explícito del fallo (`tokens.commit_failure`).
- **Suscripción al importar.** Los cuatro handlers se registran con `events.subscribe` al final de `audit/service.py`; `subscribe` es idempotente, así que reimportar o volver a llamar `load_module_services()` no los duplica. `MODULES = ("auth", "settings", "audit")`: `audit` se carga después de `auth`, del que importa solo las clases de evento; `auth` no importa nada de `audit`. Hoy son los únicos suscriptores de esos eventos.
- **CLI.** `seed`, `unlock-user` e `issue-reset-link` llaman a `_load_module_services()` (import perezoso de `app.main` dentro de la función) después de instalar los listeners: sin eso, `unlock` o `issue_link` emitirían eventos sin suscriptor en el proceso del CLI. `export-openapi` e `init-keys` no escriben tablas auditadas y no lo cargan.
- **Ubicación de la prueba de `MODULES`.** La prueba de `MODULES` y de la suscripción única vive en `tests/architecture/test_audit_module.py`, junto con las de dirección de imports, no en un `test_modules_loaded.py` aparte.
- **Router vacío.** `audit/router.py` es un `APIRouter()` sin rutas hasta US-074 (EP-17), y el módulo no tiene `models.py` (la tabla vive en `core/audit.py`). El contrato `docs/openapi.json` no cambia.
- **Revisión de seguridad del slice (`security-reviewer`, sin CRITICAL ni HIGH).**
  - MEDIUM-1 aceptado como diseño y fijado con prueba: un handler de `LoginAttempted` que falla revierte el intento fallido entero (ni la fila `login` ni `failed_login_count`) y el login responde el error en vez de 401. Es fail-closed a propósito: la auditoría es parte del login (blueprint 7.5). Documentado en `docs/RUNBOOK.md`; prueba en `tests/audit/test_security_events_review.py`. El candado asesor de la cadena (`AUDIT_CHAIN_LOCK_KEY`) se toma ahora en cada login; es el mismo del hook ORM, sin orden nuevo de candados.
  - MEDIUM-2 verificado y fijado con prueba: el último admin activo, exento del límite por cuenta (S2-D10), sigue cortado por el límite por IP del router antes del service; desde una IP, cinco 401 dejan cinco filas y el sexto 429 ninguna. Riesgo residual aceptado: un atacante con muchas IP puede sumar filas `login/failed` sobre esa cuenta al ritmo de `LOGIN_IP_LIMIT` por IP y del `limit_req` de Nginx; agregar o espaciar filas repetidas quedaría para EP-17 si el volumen lo pide (ya era la compensación aceptada en S2-B2).
  - LOW-1 aceptado: el login fallido de un tercero queda con `user_id` de la cuenta atacada (L-8 y blueprint 7.5); la `ip` de `after` lo distingue.
  - LOW-2 aceptado y anotado para US-074: `user_agent` es texto del cliente (truncado a 120) dentro de una fila inmutable; la pantalla de auditoría debe mostrarlo escapado (React escapa por defecto) y nunca como HTML. h11 ya rechaza NUL en cabeceras.
  - LOW-3 informativo: los `reason` y `via` son `Literal` cerrados asignados con constantes; no hay texto libre.
  - LOW-4 informativo: tras `clear_subscribers()` un reimport no resuscribe; las pruebas no vacían el bus sin la fixture `restaurar_bus` (E7), que lo restaura.

### S2-B7 · Registrar socio y cifrado en reposo
- **Desviaciones del Rojo aceptadas.** `POST /members` no lleva `no_store`: el dependiente vive en `auth/cookies.py`, privado de `auth` (S2-D4), y Nginx ya pone `Cache-Control: no-store` en todo `/api/` (`proxy-api.conf`); moverlo a `core/` queda para cuando una ruta fuera de `/api/` lo necesite. Topes de longitud que el blueprint no fijaba: nombres 100, teléfono 30, parentesco 50 (documento de 3 a 30, como el blueprint). `test_0005b_auth_security.py::..._y_es_head` pasó a exigir que la revisión esté en la cadena hasta head (la cabeza única la sigue exigiendo `test_single_head`). El analizador `find_banned_imports` de `tests/architecture/_imports.py` se implementó en el Rojo (las pruebas del analizador son de la herramienta, no del producto) y `test_banned_imports.py` se reescribió sobre él. `test_no_plaintext_at_rest` carga los `models.py` de todos los paquetes de `app.modules`, no solo los de `MODULES`.
- **Teléfono con largo mínimo (L-3).** `normalize_for_index` deja `"+57"` en `"57"` (solo quita el prefijo con 12 dígitos), así que "no vacío" no basta: `validate_member_input` exige al menos 7 dígitos tras normalizar (`PHONE_MIN_DIGITS`, un fijo local) y responde 422 `field="phone"`. Documento y correo: 422 si se normalizan a vacío.
- **Máscaras.** Documento: tipo + `••••` + los 4 últimos del valor normalizado en mayúsculas; un documento de menos de 6 caracteres normalizados va sin cola (`CC ••••`). Teléfono: `••• ••• ` + 4 últimos dígitos. Correo: primera letra, `•••@•••.` y la última etiqueta del dominio. Fecha: `••/••/AAAA`. Contacto: `Registrado`. Se calculan desde la entrada; el alta no descifra nada (en `crypto_ops` solo `encrypt` e `index`).
- **Límite L-1.** `ratelimit.enforce("members-write", str(principal.user_id), limit=60, window_s=60, kind="user")` en el router antes del service; el almacén `user` es el de L-11. La validación de forma de Pydantic corre antes y no consume cupo (no toca base ni bus).
- **`id_by_document`** devuelve `None` para un valor que se normaliza a vacío (contrato para otros módulos, sin `CryptoError`). En la carrera, el `IntegrityError` de `uq_members_document_idx_alive` se traduce a `MemberDocumentDuplicated` con el `existing_id` que vea la sesión (puede ser `None`); cualquier otro `IntegrityError` se relanza.
- **Revisión de seguridad del slice (`security-reviewer`, sin CRITICAL ni HIGH).**
  - MEDIUM-1 corregido: los índices ciegos viajaban a `audit.audit_log.after` como HMAC; desde la auditoría se podía correlacionar socios por documento, teléfono o correo. `Member.__audit_redact__ = {document_idx, phone_idx, email_idx}` los deja como `***`; los blobs sí van (trazabilidad). Prueba en `tests/members/test_member_review.py`.
  - LOW-2 corregido: un documento de 3 a 5 caracteres normalizados se mostraba entero en la máscara; ahora va sin cola. Prueba en el mismo archivo.
  - LOW-5 corregido: `data_consent` es `Field(strict=True)`; `"true"`, `"yes"` o `1` dan 422 (una autorización legal solo vale con `true` literal). El contrato OpenAPI no cambia.
  - LOW-3 aceptado: un `IntegrityError` distinto del único (solo CHECKs que el service ya previene) llega al handler del 500, cuyo `logger.exception` lleva los parámetros del `INSERT`; los blobs salen redactados, quedan los nombres (en claro por diseño) y los HMAC. Si se quiere cerrar, `hide_parameters=True` en el engine es un cambio de `core/db` para todos los módulos (EP-17).
  - LOW-4 aceptado (ya era L-1 de la revisión del diseño): el 409 con `existing_id` es un oráculo de existencia para admin y coach, que ya pueden buscar por documento (B8); lo frena el límite de 60 por minuto.

### S2-B8 · Buscar y listar socios
- **`by_document` exige letras y dígitos con al menos un dígito.** El blueprint decía "si `normalize_for_index(q, "generic")` no queda vacío"; con eso `"góm"` (→ `gom`) y `"+57"` gastarían un HMAC de documento. Se activa solo si el valor normalizado no está vacío, tiene al menos un dígito y es solo letras y dígitos ASCII (CC, CE, TI y PA siempre cumplen). El resultado de la búsqueda no cambia: un nombre nunca coincide con un índice de documento.
- **`"1.020.304"` activa también `by_phone`.** La caja es única y la regla de 7 dígitos del blueprint lo implica: un término de 7 o más dígitos se busca por documento y por teléfono (dos filas `index` del mismo lote).
- **Nombre sin tildes ni mayúsculas, sin migración.** `translate(lower(first_name || ' ' || last_name), 'áéíóúüñ', 'aeiouun') ILIKE translate(lower(:patrón), ...) ESCAPE '\'`, a los dos lados, como US-079 en planes (`ILIKE` solo no basta: `'Gómez' ILIKE '%gom%'` es falso en `en_US.utf8`). El índice `ix_members_alive_last_name` no la cubre: la rama de nombre es un recorrido secuencial de los socios vivos en v0.1. **Deuda conocida para el Sprint 4A** si la tabla crece: índice `pg_trgm` o columna normalizada.
- **El límite de búsqueda queda en el router.** `ratelimit.enforce("members-search", user_id, limit=60, window_s=60, kind="user")` solo con `q` no vacío (L-1); `q=""` y la lista sin `q` no cuentan. Un `q` solo de espacios no cuenta y el service lo trata como lista sin búsqueda (sin HMAC).
- **Forma de la consulta.** `select(Member)` con `load_only` de las columnas en claro (los blobs ni se cargan) y `id IN (UNION de subconsultas de ids)`: una por índice ciego presente y una por nombre; cada rama repite la condición de baja del filtro (`deleted_at IS NULL` sin `status`), así la de documento usa el único parcial `uq_members_document_idx_alive` (lo fija el `EXPLAIN` de `test_list_perf.py`). `paginate` hace dos sentencias (conteo y página); `search_ids` y `names_for`, una. Los índices se calculan con `bus.blind_index` dentro de un único `bus.batch("index", None)` (una fila agregada por clase con el mismo `batch_id`); una búsqueda solo por nombre o sin `q` no abre el lote. Nunca hay `decrypt`.
- **`service.list` conserva el nombre del contrato del blueprint** aunque sombrea al builtin dentro del módulo: las anotaciones y llamadas internas usan `builtins.list`.
- **Revisión de seguridad del slice (`security-reviewer`, sin CRITICAL ni HIGH).**
  - MEDIUM-1 corregido: un `q` con NUL (`%00`) llegaba como parámetro a PostgreSQL, que lo rechaza: 500 con traza. `classify_query` quita los caracteres de control (categoría `Cc`) antes de clasificar; `GET /members?q=an%00a` responde 200. Pruebas en `tests/members/test_list_review.py` (rojas antes del arreglo). El mismo riesgo en `auth.list_users` (`q` sobre el correo) queda anotado para la revisión de `core/pagination.SearchQuery` (rechazar controles en el contrato común cambiaría el OpenAPI de todas las listas).
  - MEDIUM-2 aceptado: cada búsqueda con índices escribe sus filas `index` agregadas en `crypto_ops` (bitácora inmutable que pide el diseño); el volumen queda acotado por el límite de 60 por minuto. Se tendrá en cuenta en la retención de `crypto_ops`.
  - LOW-4 corregido: el término se normaliza a NFC, así una tilde combinada (`"José"`) encuentra a "José". Prueba en el mismo archivo, junto con la regresión del escape `\`, `100%` y `a_b` contra PostgreSQL real.
  - LOW-1 aceptado: un admin o coach comprometido puede enumerar documentos, teléfonos o correos; es la funcionalidad misma, frenada por el límite (ya era L-4 de B7).
  - LOW-2 aceptado: el límite vive en memoria por proceso (un solo proceso en v0.1, documentado en el runbook).
  - LOW-3 aceptado: el sombreado del builtin `list` (ver arriba).

### S2-B9 · Crear y listar planes
- **CHECK de clases corregido respecto al blueprint.** El blueprint decía `(kind = 'classes' AND class_count > 0) OR (kind = 'days' AND class_count IS NULL)`; con `class_count` nulo, `NULL > 0` es NULL, `TRUE AND NULL` es NULL y un CHECK con NULL acepta la fila: un plan `classes` sin clases entraba por SQL crudo. `0007_plans` y `models.py` usan `(kind = 'classes' AND class_count IS NOT NULL AND class_count > 0) OR (kind = 'days' AND class_count IS NULL)` (`ck_plans_class_count_by_kind`); lo fija `test_0007_plans.py::test_los_checks_rechazan_por_sql_crudo[classes-sin-clases]`, que destapó el defecto en la validación del Rojo. El blueprint lleva la nota "(corregido en B9)".
- **`SearchQuery` rechaza los caracteres de control en todas las listas (cierra el pendiente de S2-B8, MEDIUM-1).** `core/pagination.SearchQuery` lleva `pattern=r"^[^\x00-\x1f\x7f-\x9f]*$"` (toda la categoría Unicode `Cc`, escrita con escapes para que el OpenAPI quede imprimible): `GET /users`, `/members` y `/plans` con un NUL u otro control en `q` dan 422 `validation_error` con `field="q"` antes de llegar al service (en `/users` daba 500). Cambia el OpenAPI de las tres listas. `members.classify_query` y el término de `plans.list` conservan su limpieza como defensa en profundidad para quien llame al service directo. `GET /members?q=an%00a` pasa de 200 (B8) a 422.
- **`service.detail(session, plan_id, *, role) -> PlanOut`** no estaba en el blueprint: `GET /plans/{plan_id}` necesita `created_at` y `updated_at`, que `PlanSnapshot` no trae. Lee el plan vivo en una sentencia; un plan dado de baja o inexistente da 404 `plan_not_found` antes que el 403 del coach sobre un inactivo.
- **`ensure_list_scope` y `ensure_read_scope` cierran también para `member`** (la ruta ya lo frena con `require_role("admin", "coach")`; la regla pura no depende de eso).
- **Coach (S2-D26):** `GET /plans` solo con `active=true`; sin parámetro, con `active=false` o solo con `q` da 403 `forbidden`. El front muestra `/planes` solo al admin.
- **Nombre único sin mayúsculas (DECISIÓN 32).** El pre-chequeo y el único comparan `lower(btrim(name))` en SQL a los dos lados (valor ligado, no `str.lower()` de Python, para que coincidan con la regla del índice). En la carrera, el `IntegrityError` de `uq_plans_name_alive` dentro de `begin_nested()` se traduce a `PlanNameDuplicated` con el `existing_id` que vea la sesión (puede ser `None`); cualquier otro `IntegrityError` se relanza. El service recorta el nombre aunque llegue sin validar.
- **Búsqueda:** `translate(lower(name), 'áéíóúüñ', 'aeiouun') ILIKE translate(lower(:patrón), ...) ESCAPE '\'`, con el término en NFC y sin controles; recorre los planes vivos (decenas en un gimnasio), sin índice.
- **`get(for_share=True)`** emite `SELECT ... FOR SHARE` real (la venta del Sprint 3 bloquea una baja concurrente); `names_for` es una sentencia, incluye dados de baja y `names_for([])` no consulta.
- **Pruebas reparadas por contrato:** `test_0006_members.py::..._y_es_head` pasó a exigir que `0006_members` esté en la cadena hasta head (la cabeza única la exige `test_single_head`); `test_audited_tables.py` mueve `plans.plans` a las requeridas y su ejemplo de tabla pendiente auditada pasa a `memberships.memberships`.
- **Base de desarrollo:** la validación del Rojo había dejado `apex-db-1` en `0007_plans` con el CHECK sin corregir (tabla vacía) y el api sin arrancar ("Can't locate revision"). Con la revisión definitiva, el ciclo `downgrade -1`/`upgrade head` de P-MIG recreó la tabla con el CHECK corregido.
- **Revisión de seguridad del slice (`security-reviewer`, sin CRITICAL ni HIGH).**
  - MEDIUM-1 corregido: `PlanCreate.name` aceptaba caracteres de control y de formato; un NUL llegaba como parámetro a PostgreSQL (500 con traza, el mismo defecto del `q` de S2-B8) y un nombre solo de U+200B pasaba el CHECK `btrim(name) <> ''`. Un `field_validator` normaliza a NFC, rechaza las categorías `Cc` y `Cf` y exige algo visible: 422 `field="name"`. Con NFC, "Promoción" compuesta y descompuesta chocan en `uq_plans_name_alive` (409); `create` también normaliza lo que llega sin validar. Pruebas en `tests/plans/test_plan_review.py` (10 rojas antes del arreglo). El CHECK de controles en la base que se proponía como defensa extra no se agregó: `0007_plans` ya estaba aplicada en `apex-db-1` y `db_test`, y el contrato lo cierra antes.
  - LOW-1 corregido: `PlanListQuery.q` (contrato del blueprint, aún sin cablear) usa `SEARCH_PATTERN`, como `SearchQuery`. Prueba en el mismo archivo.
  - LOW-2 aceptado: el 403 frente al 404 en `GET /plans/{id}` revela al coach que un plan inactivo existe; es la regla S2-D26 y los planes no son secretos.
  - LOW-3 aceptado: `existing_id` en el 409 solo lo ve el admin, que ya lista todos los planes.
  - LOW-4 aceptado: la búsqueda recorre la tabla de planes (decenas de filas), sin índice.

### S2-V · Validación del sprint (V2 a V9)

- **Se reabre con datos el `limit_req` fijo del borde (S2-W0-1, E5, E9).** En V4 la suite `stack` de Playwright recibió 429 de Nginx aun con el perfil E2E del api: todo el tráfico del host llega a Nginx con una sola IP (la puerta de enlace de la red de Compose, `172.30.0.128`) y cada carga completa de la SPA hace `POST /auth/refresh` y `GET /auth/me`; en serie, 46 peticiones a `/api/v1/auth/` en 20 s agotan la ráfaga de 30. Decisión: la zona `apex_auth` pasa a `infra/nginx/snippets/auth-zone.conf` (60r/m, la que lleva la imagen) e `infra/compose.e2e.yml` monta encima `infra/nginx/e2e/auth-zone.conf` (6000r/m, misma zona y tamaño) solo durante V4 y en el job `e2e-stack`. No hace falta `envsubst` ni cambiar el `entrypoint`: es un archivo montado. `infra/nginx/e2e/` no entra en la imagen (el `Dockerfile` copia `default.conf` y `snippets/`). Lo vigilan `test_nginx_conf.sh` (zona de producción a 60r/m solo en el snippet, `include` en el contexto http, `nginx -t` con las dos zonas, la de E2E distinta de 60r/m y fuera del `Dockerfile`) y `test_compose_config.sh` (solo `compose.e2e.yml` monta la zona, en solo lectura; producción y desarrollo no).
- **`storageState` de E5 no se adopta.** El refresh rota en cada uso y el reuso fuera de la gracia revoca todas las sesiones (N-13, M-2): una cookie guardada y compartida entre pruebas queda rotada tras la primera y su reuso revocaría la sesión de las demás. Cada prueba entra por `loginComo` con su propia sesión; el volumen lo absorbe el perfil E2E del borde.
- **Job `e2e-stack` de CI:** aplicaba el `.env.example` sin el perfil E2E del api (cinco logins por minuto) y no pasaba `E2E_ADMIN_EMAIL` ni `E2E_ADMIN_PASSWORD` (`datosDeBase()` lanza sin ellas). Ahora sube los topes con `sed` sobre la copia del `.env`, apila `compose.e2e.yml` en `DC` y exporta el admin del `.env.seed` efímero (con `add-mask`).
- **Defecto de producto corregido:** el saludo de Inicio ("Hola, <correo>") desbordaba 96 px a 320 px (el correo no tiene puntos de corte). `PageHeader` `.title` lleva `overflow-wrap: anywhere`. Lo vigila `captures.spec.ts` (sin desborde en los cuatro anchos, con sesión real).
- **Pruebas reparadas:** `captures.spec.ts` esperaba el `h1` "APEX" de la página estática de S2-W0-1, que desde S2-F3 redirige a `/login`; ahora captura el login (siempre claro: `AccessLayout` fuerza el claro) y el Inicio con sesión en claro y oscuro (el panel no sigue `prefers-color-scheme`: la elección vive en `apex.theme`). Las specs con axe esperan a que terminen las transiciones CSS (`esperarTransiciones`) antes de medir: tras un clic el hover del botón principal (120 ms) pasaba por un contraste intermedio de 4,22:1.

## Revisión de Fase 4 del Sprint 2

Fuente: los cuatro informes de la revisión posterior a la validación (general, seguridad, Python y TypeScript, sobre `482295f..981836a`), resumidos en `docs/scratch/sprint-02.md`, "Revisión de Fase 4". Tres agentes corrigen en paralelo: backend (`api/`), front (`web/`) y CI con documentación. Esta sección registra las decisiones; cada agente anota en su bloque lo que implementó.

- **L7 · Dónde viven los eventos de dominio.** Los tipos de evento (`LoginAttempted`, `UserLocked`, `SessionsRevoked`, `PasswordChanged`…) se siguen definiendo en el módulo que los emite y se exportan desde su `service.py`, que es la fachada; tras partir `auth` (M6, ver abajo) viven en `auth/events.py`, privado, y `auth/service.py` los re-exporta. `core/events.py` es solo el bus (`subscribe`, `emit` y el despacho en la transacción): no conoce ningún evento concreto. Justificación: el evento es parte del contrato público del emisor, igual que sus `schemas.py`; ponerlo en `core/` haría que `core` cambie con cada módulo (regla 4 de módulos) y juntaría en un archivo el vocabulario de todos los contextos. El suscriptor ya puede importar el `service.py` del emisor (regla 2), así que no aparece ninguna dependencia nueva. Regla para lo que viene: `payments` define `PaymentRegistered` (y los demás) en su módulo y los exporta desde `payments/service.py`; `notifications`, `memberships` y `audit` los importan solo de `payments.service`, nunca de un archivo privado de `payments` ni de `core/events.py`. S2-D53 queda igual. `CLAUDE.md`, regla 3 de módulos, se corrige en el mismo cambio.
- **M6 (= H1 de Python) · `auth/service.py` se parte.** Pasa de 1.257 líneas a una fachada `service.py` (con `__all__` y `register_principal_loader`, lo único que importan los demás módulos) y cuatro archivos privados: `sessions.py` (login, refresh, logout), `users.py` (mi cuenta y ciclo de vida de usuarios), `links.py` (reset, forgot, emisión y reenvío de enlaces) y `events.py`. La regla `private_helper` de `tests/architecture` los cubre. Lo hace el backend en esta revisión; `CLAUDE.md` (estructura y regla 1) ya nombra la estructura final.
- **H3 de Python y M6 de Python · utilidades comunes en `core`.** `core/search.py` (limpieza de `q`, quitar tildes, escape de `LIKE`, hoy repetidos en `auth`, `members` y `plans`) y `core/http.py` (ayudas HTTP comunes a los routers, como `Cache-Control: no-store`, que hoy vive en `auth/cookies.py`). Las crea el backend; `CLAUDE.md` las lista.
- **M7 · Errores por ruta en OpenAPI.** Hoy las 31 operaciones declaran los mismos 400/401/403/404/409/422/429/500, incluido `/health`, y los códigos (`member_document_duplicated`, `last_admin`, `plan_name_duplicated`…) viven como strings sueltos en el front. Regla: cada ruta declara solo las respuestas que puede dar y los códigos de error salen del contrato. Dueño: backend, en esta revisión; el front deja de duplicar los códigos cuando `docs/openapi.json` los traiga (si no entra en esta revisión, queda para el Sprint 3 con el mismo dueño).
- **M4 · Política `perf`.** Ver S2-D27, "Estado al cierre": fuera de los gates (`-m "not perf"` en `run-gates.sh` y en el job `api`), paso informativo en CI con `continue-on-error` y 10 minutos.
- **N-5 · Auditoría de dependencias en CI.** `npm audit --omit=dev --audit-level=high` en el job `web` y `pip-audit` 2.10.1 sobre `uv export --frozen --no-dev --no-emit-project` (con hashes) en el job `api`; las dos limpias el 22 de octubre. Las dependencias de desarrollo del front tienen 11 hallazgos (vitest y `@vitest/mocker` moderate, tinypool critical, braces, micromatch, fast-glob y stylelint high), todos de herramientas de prueba que no se distribuyen: no son gate. Dueño: front, actualizar vitest y stylelint en el Sprint 3.
- **N-6 · IP real en el borde.** En Docker Desktop y con `userland-proxy` todos los clientes llegan a Nginx con la IP de la puerta de enlace y comparten los límites por IP. Se verifica en el servidor del gimnasio (Linux con Docker Engine) mirando `remote_addr` en el access log (`docs/RUNBOOK.md`, sección 1, "IP real en el borde"). Dueño: S4B-W0-2 (despliegue).
- **N-7 · Piso de login.** `LOGIN_MIN_DURATION_MS` pasa de 75 ms (1,5 veces la mediana) a **150 ms (p99)**: el piso debe cubrir el p99 de la rama de cuenta existente bajo contención del candado de auditoría, no la mediana. Dueño: backend, en esta revisión (valor por defecto en `Settings` y `.env.example`); remedir el p99 con carga en S4B-W0-2, en el hardware del servidor.
- **N-8 · L-13 en el cambio de correo.** `PATCH /users/{id}` no puede cambiar el correo de otro admin activo (409), la misma regla que `resend-link`: cuando `forgot` envíe correos (US-131) sería una toma de cuenta. Dueño: backend, en esta revisión; `docs/RUNBOOK.md`, sección 2, lo documenta.
- **L3 · Acciones e imágenes fijadas.** En `ci.yml` las seis acciones van por SHA de commit con la versión en comentario (`actions/checkout` v4.4.0, `actions/setup-node` v4.4.0, `astral-sh/setup-uv` v6.8.0, `actions/upload-artifact` v4.6.2, `docker/setup-buildx-action` v3.12.0, `docker/build-push-action` v6.19.2), cada job tiene `timeout-minutes` y el servicio `postgres:16` del job `api` va por digest. Quedan por digest, fuera del alcance de esta rama: `python:3.12-slim` (`api/Dockerfile`), `node:22-alpine` y `nginx:stable-alpine` (`web/Dockerfile`), `postgres:16` (`infra/compose.yml` y `infra/compose.dev.yml`) y `nginx:stable-alpine` (`scripts/ci/test_nginx_conf.sh`). Digests del 22 de octubre: `postgres:16@sha256:9e2cf6287f25c3151f4c9421ccce2b17f3e60061c111a29165e0d2cdd9ff0a97`, `nginx:stable-alpine@sha256:c59d1f8b1e0e42da75be973424cd72e23f7f8adfb54e982f4d1cd0216a5a5576`, `node:22-alpine@sha256:fe4f6d74e20370acb04ad889077d14d0f64a9c8ea6a42bc60cddf1e844699914`. Dueño: el primer slice de infraestructura del Sprint 3 (o, a más tardar, S4B-W0-2), junto con la decisión de cómo se renuevan (Dependabot o a mano, con el comando del comentario de `ci.yml`). También aceptado: `e2e-stack` reconstruye las imágenes sin la caché de GHA del job `images`; cuesta minutos y aísla el job, se revisa si el tiempo de CI molesta.
- **Recordatorio M-6 (cobertura).** `api/pyproject.toml` sigue con `omit = ["*/app/cli.py", "*/app/worker/*"]`. `cli.py` creció unas 215 líneas en el Sprint 2, con pruebas, pero fuera del 80 %. El `omit` se quita en el Sprint 4A (US-113, S4A-B1), como dice `scripts/workflow/README.md`.

### Decisiones del cierre backend de la revisión (S2-R1 a S2-R11)

Tomadas al corregir los hallazgos de seguridad (N-1 a N-9) y de Python (H1 a H3, M1 a M11); evidencia en `docs/scratch/sprint-02-revision-backend.md`.

- **S2-R1 (N-3).** El límite por cuenta del login usa la IPv4 exacta (`/32`, `/64` en IPv6),
  igual que `rate_limit`. Motivo: en la LAN del gimnasio (P7) todos comparten un /24 y un
  dispositivo con diez fallos negaba el login de las cuentas no exentas. La rotación dentro del
  /24 la siguen frenando el tope global por correo (100/h) y el bloqueo a 20 fallos. La prueba de
  B2 que fijaba el 429 desde otra IP del mismo /24 se actualizó por esta decisión.
- **S2-R2 (M2).** El cupo por cuenta y el global se reservan de forma atómica antes de argon2 y se
  devuelven si el login sale bien; un 429 del global devuelve la reserva de la cuenta. El efecto
  visible es el mismo (solo cuentan los fallos), sin la carrera de `peek` + `record`.
- **S2-R3 (N-8).** `PATCH /users/{id}` no cambia el correo de OTRO admin activo con contraseña
  (409 `user_not_eligible`), la regla L-13 aplicada al correo. El propio admin sí puede cambiar el
  suyo (ya conoce su contraseña; no hay toma de cuenta). Un admin pendiente de activación o
  bloqueado sí se corrige (su enlace de activación se cierra al cambiar el correo, LOW-3 de B5).
- **S2-R4 (M1).** Si otro cambio de contraseña ganó la carrera entre la verificación (sin
  candado) y el `FOR UPDATE`, se responde 422 `invalid_current_password` (la "actual" tecleada
  ya no lo es) sin sumar al tope por usuario: no es un intento de adivinar. Se prefirió a un 409
  nuevo para no agregar un código al contrato por un caso que el front trata igual.
- **S2-R5 (M11).** `refresh_current` no se cachea. Medición (500 llamadas tras 20 de
  calentamiento): desde el host contra `db_test`, mediana 0,707 ms, p95 0,788, p99 0,936
  (`SELECT 1` del mismo camino: 0,541 ms de mediana, casi todo es ida y vuelta); dentro del
  contenedor del api contra `db`, la consulta de marca (`_marca`) da mediana 0,407 ms, p95 0,567,
  p99 0,655. Por debajo de 1 ms: un TTL de 5 s solo agregaría una ventana en que una rotación de
  otro proceso no se ve.
- **S2-R6 (M5 general).** El piso de `PASSWORD_MIN_LENGTH` en producción es 12
  (`PASSWORD_MIN_LENGTH_FLOOR` en `core/config.py`, expuesto como `core.security.PASSWORD_MIN_LENGTH`)
  y el contrato publica `minLength: 12` en `new_password`. Consecuencia: una contraseña nueva de
  menos de 12 caracteres la rechaza el schema con 422 `validation_error` (`field=new_password`),
  antes de la política; `weak_password` queda para la lista de comunes y "igual a la actual". El
  front ya valida 12 con Zod.
- **S2-R7 (N-2).** Texto libre en dos tipos: `SafeText` (una línea: sin `Cc` ni `Cf`) y
  `SafeMultilineText` (la política de privacidad: admite tabulador y saltos; de `Cf` solo rechaza
  los controles bidireccionales, para no romper el pegado desde un procesador con guion suave o
  ZWJ). `offset` tiene tope de 1.000.000.
- **S2-R8 (N-1).** Toda ruta y `current_user` piden la sesión con `SessionDep`
  (`scope="function"`); el commit corre antes de enviar la respuesta. Nunca `Depends(get_session)`
  suelto (mezclar alcances abre dos sesiones); lo exige `test_session_scope.py`.
- **S2-R9 (N-4).** `cli unlock-user` exige `--as` de un admin activo. RUNBOOK §2 ya dice "de un admin activo".
- **S2-R10 (H1).** Un `service.py` que crece se parte en archivos privados del módulo y queda
  como fachada con `__all__`; otros módulos siguen importando solo `service.py`. Topes: 800
  líneas por archivo y 50 por función (`test_file_and_function_size.py`).
- **S2-R11 (M7 general).** Los errores del OpenAPI se declaran por ruta con `responses_for`; el
  gancho agrega `500` a todas y no toca códigos fuera del catálogo (`503` de `/health`).
