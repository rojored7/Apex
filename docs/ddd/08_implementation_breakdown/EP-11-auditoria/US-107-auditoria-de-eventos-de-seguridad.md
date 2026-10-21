# US-107 · Auditoría de eventos de seguridad — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-11-auditoria/US-107-auditoria-de-eventos-de-seguridad.md`
- **Épica:** EP-11 · Auditoría y trazabilidad
- **Bounded context / módulo:** Audit (`api/src/app/modules/audit/service.py`, `api/src/app/core/audit.py`), suscrito a eventos de Auth (`api/src/app/modules/auth/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

El reparto está cerrado por la consolidación de historias: la fila `reveal` la escribe US-074 en su transacción y esta historia solo verifica que exista; aquí quedan el login (exitoso y fallido de correo existente), `UserLocked`, `SessionsRevoked` y la prueba de arquitectura de tablas auditadas. DECISIONES N-31 confirma que el login fallido de un correo inexistente no se audita. Los contratos de evento que se piden a Auth son campos, no comportamiento nuevo.

## Resumen

Registra en la cadena de auditoría los eventos de seguridad que no son cambios de columnas: `auth.service.login` llama a `core.audit.record(action="login", ...)` con `after = { result: "ok" | "failed" }` (el fallido se confirma aunque la petición responda 401), y `modules/audit/service.py` se suscribe a `UserLocked` y `SessionsRevoked` y escribe una entrada `update` sobre `users` con `after.event`. Agrega `tests/architecture/test_audited_tables.py`, que falla si alguna tabla de v0.1 que debe auditarse no tiene `__audited__ = True`, y una prueba que confirma que el `reveal` de US-074 deja exactamente una entrada sin el valor.

## Correcciones aplicadas por DECISIONES.md

- Login fallido de correo inexistente: solo log y rate limit, no auditoría → se implementa así: aceptado por DECISIONES N-31.
- `SessionsRevoked` no solo lo emite el admin desde `POST /users/{id}/revoke-sessions`: también cambiar la contraseña revoca las demás sesiones y reusar un refresh ya rotado revoca todas las sesiones del usuario (DECISIONES N-13). El handler audita todos los casos; cuando no hay persona que actúe (reuso detectado en `refresh`), `user_id = SYSTEM_USER_ID`: DECISIONES N-15. `after` lleva además `reason` (`admin`, `password_changed`, `refresh_reuse`).
- La historia nombra `settings.settings_sections`; coincide con la migración canónica `0005_settings`, sin cambio.

## Validación contra el dominio

- Aggregate `AuditEntry`; RN-13 (mostrar en claro se audita), RN-16 (las entradas de eventos entran a la misma cadena).
- Eventos consumidos: `UserLocked(user_id, by)` y `SessionsRevoked(user_id, by, reason)` de `auth.service` (catálogo de `02_domain_model.md` sección 3). `SensitiveFieldRevealed` lo sigue emitiendo Members, pero la fila `reveal` la escribe US-074 directamente con `core.audit.record`; aquí no hay handler de `reveal`, para no duplicar la entrada.
- El login no es un evento: `auth.service.login` llama a `core.audit.record` (está en `core`, que Auth puede usar).
- Bloquear a un usuario actualiza `auth.users.locked_at`, columna de una tabla auditada: el hook de US-016 ya deja una entrada `update` con `locked_at`. El handler de `UserLocked` agrega la entrada con `after.event = "UserLocked"`. Quedan dos entradas para un bloqueo (cambio de columna y evento); es coherente con la historia, que pide "una entrada con el evento", y se documenta.
- Funciones puras: ninguna nueva.

## Validación contra la arquitectura

- Handlers en `modules/audit/service.py`, registrados con `core.events.subscribe` al importar el módulo; corren en la sesión y transacción del emisor, así que si fallan, el bloqueo o la revocación se revierten.
- `modules/audit` importa de `auth.service` solo las clases de evento (y `names_for` en US-102); Auth no importa nada de `modules/audit`. Sin ciclos ni `models` ajenos.
- Login fallido: la petición termina en 401 y la transacción de la petición se revertiría junto con la entrada. `auth.service.login` escribe la entrada de fallo en una sesión propia de corta duración (`async with session_factory() as audit_session: record(...); commit()`) antes de levantar `InvalidCredentials`. El `seq` y `prev_hash` se toman bajo el lock de cadena de `record()`, así que la entrada se encadena bien aunque venga de otra sesión.
- Ninguna entrada contiene contraseñas, hashes de contraseña ni tokens; `after` solo lleva `result`, `event`, `reason`. Lint `banned-api` sin cambios.
- Rate limit (US-036) intacto: la escritura de auditoría ocurre después de contar el intento y no lo cuenta de nuevo.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `modules/auth/service.py` (contrato con EP-04): `login` llama a `core.audit.record(action="login", table_name="users", record_id=user.id, user_id=user.id, after={"result": "ok"})` en la transacción del login exitoso; en contraseña incorrecta, usuario bloqueado o inactivo de un correo existente escribe `{"result": "failed"}` en sesión propia confirmada antes de levantar el 401; correo inexistente no escribe nada — 2 h
- [ ] T2 · Contrato de eventos con EP-04: `UserLocked(user_id, by)` y `SessionsRevoked(user_id, by, reason)` como dataclasses congeladas en `auth/service.py`, emitidos por `lock`, `revoke_sessions`, cambio de contraseña y detección de reuso de refresh (con `by = SYSTEM_USER_ID` en el reuso) — 1 h
- [ ] T3 · `modules/audit/service.py`: handlers `on_user_locked(event, session)` y `on_sessions_revoked(event, session)` que llaman a `core.audit.record(action="update", table_name="users", record_id=event.user_id, user_id=event.by, after={"event": ..., "reason": ...})`; registro con `core.events.subscribe` al importar; `main.py`, `cli.py` y el worker importan `app.modules.audit.service` para que los handlers existan en todos los procesos — 1,5 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- No aplica (sin funciones puras nuevas).

### Tests de service con PostgreSQL
- [ ] T4 · `api/tests/audit/test_security_events.py`: login exitoso deja una entrada `login` con `result = ok`; login fallido de correo existente deja `result = failed` aunque la petición responda 401 (la fila existe tras el rollback de la petición); correo inexistente no deja entrada; ninguna entrada contiene la contraseña tecleada ni el hash (búsqueda en `before`/`after` serializados); `UserLocked` y `SessionsRevoked` dejan su entrada con el admin como `user_id` y el afectado como `record_id`; el reuso de refresh deja `SessionsRevoked` con `SYSTEM_USER_ID`; handler que falla revierte el bloqueo; la cadena sigue íntegra (`verify_chain`) tras todos los eventos — 3 h
- [ ] T5 · `api/tests/audit/test_reveal_entry.py`: el `reveal` de US-074 deja exactamente una entrada `reveal` con `table_name = "members"`, `record_id = member_id`, `after.field` y sin el valor revelado; si la escritura de auditoría falla, el endpoint responde 500 con envelope y no entrega el valor — 1,5 h
- [ ] T6 · Prueba del rate limit: cinco logins fallidos con correo existente generan cinco entradas y el sexto intento responde 429 igual que sin auditoría (la auditoría no cuenta intentos) — 0,5 h

### Tests de router
- [ ] T7 · `api/tests/auth/test_router_login_audit.py`: `POST /auth/login` fallido responde 401 con envelope y la entrada `failed` existe; exitoso responde 200 y la entrada `ok` existe — 0,5 h

### Tests de arquitectura
- [ ] T8 · `api/tests/architecture/test_audited_tables.py`: recorre `Base.metadata` y los modelos registrados; falla nombrando la tabla si alguna de `members.members`, `plans.plans`, `memberships.memberships`, `payments.payments`, `auth.users`, `settings.settings_sections` no tiene `__audited__ = True`; la lista vive en una constante `REQUIRED_AUDITED_TABLES_V01` del test (se amplía con `memberships.membership_freezes` si US-089 la declara auditada) — 1 h

### Front
- No aplica.

### DevOps
- [ ] T9 · Verificar que el log JSON de US-018 registra el login fallido de correo inexistente solo con IP y resultado, sin el correo tecleado, y que `main.py`, `cli.py` y el worker cargan los handlers (prueba de humo en `compose.dev.yml`) — 1 h

### Seguridad
- [ ] T10 · Revisión con `security-reviewer`: ningún secreto en `after`, el login fallido no permite enumerar correos por tiempos de respuesta distintos (la sesión extra se abre también en el camino de correo inexistente sin escribir, o se iguala con `argon2` falso de US-042), la sesión propia del fallo no deja conexiones abiertas — 1 h

## Orden de ejecución
1. T8 (arquitectura en rojo)
2. T4, T5, T6 (service en rojo)
3. T2
4. T1
5. T3
6. T7
7. T9
8. T10

## Dependencias técnicas
- US-015 · Tabla de auditoría y cadena de hashes: `record()` con lock de cadena, usable desde otra sesión.
- US-016 · Hook de auditoría after_flush: entrada de `locked_at` y `__audited__`.
- US-014 · Bus de eventos transaccional.
- US-042 · Iniciar sesión: punto de inserción del `record` de login.
- US-043 / US-045 · Renovar sesión y cambiar contraseña: emiten `SessionsRevoked` (N-13).
- US-050 · Bloquear y desbloquear usuario: emite `UserLocked`.
- US-051 · Cerrar sesiones de un usuario: emite `SessionsRevoked`.
- US-074 · Mostrar dato sensible auditado: escribe la fila `reveal`.
- US-036 · Rate limit de login.

## Endpoints
- Ninguno.

## Riesgos
- La entrada de login fallido en sesión propia agrega una escritura por intento y puede usarse para llenar la tabla — mitigación: el rate limit de US-036 (5 por minuto por IP) acota el volumen; solo correos existentes escriben.
- Dos entradas por bloqueo (hook y evento) pueden confundir al leer el historial — mitigación: el detalle (US-103) muestra `after.event`; la pantalla de auditoría lo distingue por la columna de acción y el contenido.
- Si EP-04 no incluye `by` y `reason` en los eventos, el handler no puede atribuir la acción — mitigación: contrato pedido explícitamente en T2 y en el resumen para el orquestador.

## Estimación
- Backend: 4,5 h (T1 a T3)
- Front: 0 h
- Pruebas: 6,5 h (T4 a T8)
- DevOps / seguridad: 2 h (T9, T10)
- **Total: 13 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/audit/test_security_events.py tests/audit/test_reveal_entry.py -q`
- [ ] `cd api && uv run pytest tests/auth/test_router_login_audit.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] Un `curl -X POST /api/v1/auth/login` con contraseña incorrecta de un correo existente responde 401 y `SELECT after FROM audit.audit_log WHERE action = 'login' ORDER BY seq DESC LIMIT 1` devuelve `{"result": "failed"}`
- [ ] `SELECT count(*) FROM audit.audit_log WHERE after::text ILIKE '%<contraseña de prueba>%'` devuelve 0
- [ ] `cd api && uv run python -m app.cli verify-audit` devuelve 0 tras generar los eventos
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.audit --cov=app.modules.auth --cov-fail-under=80`
