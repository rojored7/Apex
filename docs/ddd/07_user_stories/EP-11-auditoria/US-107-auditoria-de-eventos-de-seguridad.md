# US-107 · Como administrador quiero que las consultas en claro, los inicios de sesión, los bloqueos y los cierres de sesión queden en la auditoría para tener rastro de los eventos de seguridad, no solo de los cambios de datos

- **Épica:** EP-11 · Auditoría y trazabilidad
- **Bounded context:** Audit (esquema `audit`), suscrito a eventos de Members y Auth
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna propia (las entradas se ven en `Auditoria` y en la pestaña Historial de `Socio_Ficha`)

## Historia

Como administrador
quiero que cada dato mostrado en claro, cada inicio de sesión, cada bloqueo de usuario y cada cierre forzado de sesiones quede en la cadena de auditoría
para poder demostrar quién accedió a datos personales y cómo se gestionaron las cuentas

## Contexto de dominio

- **Aggregate / entidades:** `AuditEntry`.
- **Reglas que aplica:** RN-13 (mostrar en claro se audita), RN-16 (las entradas de eventos entran a la misma cadena), catálogo de eventos de `02_domain_model.md` sección 3 (`SensitiveFieldRevealed`, `UserLocked`, `SessionsRevoked` → audit), acciones `reveal` y `login` de `AuditEntry`.
- **Eventos que emite:** ninguno.
- **Eventos que consume:** `SensitiveFieldRevealed(member_id, field, user_id)`, `UserLocked`, `SessionsRevoked`; además el login exitoso y fallido de `auth.service.login`.
- **Funciones puras:** ninguna nueva.

## Alcance

- **Backend:** handlers en `modules/audit/service.py` registrados con `core.events.subscribe` que llaman a `core.audit.record(...)` dentro de la misma transacción: `reveal` (`table_name = "members"`, `record_id = member_id`, `after = { field }`), `update` con `after = { event: "UserLocked" }` y `{ event: "SessionsRevoked" }` sobre `users`; `auth.service.login` llama a `core.audit.record(action="login", ...)` con resultado. Prueba de arquitectura que mantiene la lista de tablas que deben llevar `__audited__ = True` en v0.1.
- **Front:** No aplica (lo muestran US-102 y US-106).

## Criterios de aceptación

1. Cada `SensitiveFieldRevealed` deja exactamente una entrada `action = "reveal"` con `user_id`, `table_name = "members"`, `record_id = member_id` y `after.field` igual al campo; `after` nunca contiene el valor revelado.
2. Si el handler de auditoría falla, el `reveal` también falla y el valor no se entrega (misma transacción).
3. Un login exitoso deja una entrada `action = "login"` con `user_id` y `after = { result: "ok" }`; un login fallido de un correo existente deja `after = { result: "failed" }` con ese `user_id`; un correo inexistente no deja entrada. Ninguna entrada contiene contraseñas ni tokens.
4. `UserLocked` y `SessionsRevoked` dejan una entrada sobre `users` con el usuario afectado como `record_id`, el admin que actuó como `user_id` y el nombre del evento en `after.event`.
5. Todas estas entradas entran a la cadena de hashes y la verificación (US-104) sigue íntegra tras generarlas.
6. La prueba de arquitectura falla si alguna de las tablas `members.members`, `plans.plans`, `memberships.memberships`, `payments.payments`, `auth.users`, `settings.settings_sections` no tiene `__audited__ = True`.
7. Un login fallido sigue sujeto al rate limit de US-036 y su entrada de auditoría no cuenta como intento extra.

## Escenarios BDD

```gherkin
# language: es
Característica: Auditoría de eventos de seguridad

  Escenario: Mostrar un documento deja rastro sin el valor
    Dado que estoy autenticado como "coach"
    Cuando muestro en claro el documento de "Laura Gómez"
    Entonces la auditoría tiene una entrada "reveal" con mi usuario, el socio y el campo "document"
    Y la entrada no contiene el número de documento

  Escenario: Un login fallido queda registrado
    Dado el usuario "coach@apex.co"
    Cuando intento ingresar con una contraseña incorrecta
    Entonces la auditoría tiene una entrada "login" con resultado "failed" para ese usuario
    Y la entrada no contiene la contraseña

  Escenario: Bloquear un usuario queda registrado
    Dado que estoy autenticado como "admin"
    Cuando bloqueo al usuario "coach@apex.co"
    Entonces la auditoría tiene una entrada sobre "users" con evento "UserLocked" y mi usuario

  Escenario: Falla la auditoría y no se revela el dato
    Dado que la escritura de auditoría falla
    Cuando un coach muestra en claro el teléfono de "Laura Gómez"
    Entonces la respuesta es un error 500 con el envelope de error
    Y el teléfono no se entrega

  Escenario: Tabla nueva sin auditar
    Dado que la tabla "payments.payments" no tiene "__audited__"
    Cuando corre la prueba de arquitectura
    Entonces la prueba falla nombrando la tabla
```

## Endpoints

- Ninguno nuevo (los eventos provienen de `POST /members/{id}/reveal`, `POST /auth/login`, `POST /users/{id}/lock` y `POST /users/{id}/revoke-sessions`).

## Pantalla

- Ninguna propia.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** service con base real (una entrada por evento, rollback si falla el handler, cadena íntegra tras los eventos); arquitectura (`tests/architecture/test_audited_tables.py`); prueba de log/auditoría sin secretos.
- **Archivos principales:** `api/src/app/modules/audit/service.py`, `api/src/app/core/audit.py`, `api/src/app/modules/auth/service.py`, `api/tests/architecture/test_audited_tables.py`.

## Supuestos

- Supuesto: se auditan los logins exitosos y los fallidos de correos existentes; los fallidos de correos inexistentes no se registran (no hay `user_id` y no se guarda el correo tecleado).
- Supuesto: `UserLocked` y `SessionsRevoked` se registran como acción `update` sobre `users` con el nombre del evento en `after.event`, porque `AuditEntry.action` no tiene valores específicos para ellos.
- Supuesto: la tabla de settings se llama `settings.settings_sections`; se ajusta al nombre real de US-054.

## Dependencias

- US-016 · Hook de auditoría after_flush.
- US-014 · Bus de eventos transaccional.
- US-074 · Mostrar dato sensible auditado (emite `SensitiveFieldRevealed`).
- US-050 · Bloquear y desbloquear usuario (emite `UserLocked`).
- Nota de consolidación: la fila reveal ya la escribe US-074; esta historia solo verifica que exista y cubre login, UserLocked y SessionsRevoked

## INVEST

- **Independiente:** handlers aislados; cada emisor ya existe o se prueba con un evento sintético.
- **Negociable:** forma de `after` de cada evento.
- **Valiosa:** cubre la exigencia de rastrear el acceso a datos personales.
- **Estimable:** cuatro handlers y una prueba de arquitectura.
- **Pequeña:** dos a tres días.
- **Testeable:** cada evento tiene prueba de entrada única.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla de arquitectura
- [x] Endpoints y roles definidos (los de los emisores)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Prueba de arquitectura de tablas auditadas en verde
- [ ] Auditoría verificada (cadena íntegra tras los eventos)
- [ ] Revisión de PR aprobada
