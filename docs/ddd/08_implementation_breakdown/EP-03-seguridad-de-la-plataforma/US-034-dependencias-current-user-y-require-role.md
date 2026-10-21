# US-034 · Dependencias current_user y require_role — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-03-seguridad-de-la-plataforma/US-034-dependencias-current-user-y-require-role.md`
- **Épica:** EP-03 · Seguridad de la plataforma
- **Bounded context / módulo:** core/security, transversal (`api/src/app/core/security.py`), con un adaptador en Auth (`api/src/app/modules/auth/service.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**ARCHITECTURAL_GAP_DETECTED**

La historia pide que `current_user`, que vive en `core/security`, "cargue el usuario por `auth.service`" para rechazar usuarios inactivos, bloqueados o dados de baja en cada petición (criterios 3 y 4). Eso hace que `core/` dependa de un módulo, lo que la arquitectura prohíbe, y crea un ciclo de imports: `auth.service` importa `core.security` (hash, tokens) y `core.security` importaría `auth.service`. Además, importar `modules/auth/models` desde core está prohibido. La arquitectura no documenta ningún puerto para esto. Abajo va la propuesta concreta para cerrarlo; con ella aprobada, la historia queda lista sin cambiar su alcance.

## Resumen

`current_user` lee `Authorization: Bearer`, decodifica con US-033 y pide el estado vigente del usuario a un puerto `PrincipalLoader` que define `core/security` y que implementa y registra Auth al importarse, igual que los handlers del bus de eventos. Devuelve un `Principal` (id, rol vigente, `member_id`) y fija el `current_actor` de US-016 para auditoría y para la bitácora de criptografía. `require_role(*roles)` exige `current_user` y el rol, y deja una marca que lee la prueba de US-035. Los errores usan el envelope de US-017: 401 y 403.

## Correcciones aplicadas por DECISIONES.md

- La historia trata al actor como "el usuario autenticado" sin decir nada del usuario técnico → el usuario técnico `SYSTEM_USER_ID` (`00000000-0000-0000-0000-000000000001`, `is_active = false`) nunca autentica por HTTP. El cargador lo devuelve como no válido por estar inactivo, y `current_user` además lo rechaza de forma explícita por su UUID (defensa en profundidad): corregido por DECISIONES N-15.
- La historia (y US-016) nombran `SYSTEM_ACTOR_ID` como actor de procesos sin petición → no existe esa variable; el `current_actor` sin petición HTTP lo fija el CLI o el worker con `SYSTEM_USER_ID` o con el usuario de `--as <email>`. `current_user` solo lo fija en peticiones: corregido por DECISIONES N-15.

## Validación contra el dominio

- Aggregate `User`: se leen `is_active`, `locked_at`, `deleted_at`, `role` y `member_id`. Coincide con `02_domain_model.md` 2.11 (bloquear impide el acceso; revocar sesiones revoca refresh tokens, y el access token muere solo por estado o por vencimiento).
- RN-15 (rol por endpoint; coach no anula ni borra; socio solo lo suyo): `require_role` es el mecanismo. El "solo lo suyo" del socio se apoya en `Principal.member_id` (portal, v1.0).
- Eventos: ninguno emitido ni consumido.
- Función pura: `role_allowed(user_role: Role, allowed: frozenset[Role]) -> bool`.
- Decisión de comportamiento: el rol que vale es el **vigente en la base** (lo devuelve el cargador), no el del claim. Si un admin pasa a coach, pierde los permisos de admin en la siguiente petición y no 15 minutos después. Es más restrictivo y no cambia el contrato.

## Validación contra la arquitectura

- Regla rota por la historia literal: `core/security` → `modules/auth/service`. La arquitectura (`03_context_map.md` y `05_service_design.md`) solo prevé dependencias de módulos hacia core, y `core/` no puede depender de un módulo. Importar `modules/auth/models` desde core es además un caso de models cruzados.
- Ciclo: `modules/auth/service.py` importa `core.security` (US-032, US-033); si `core.security` importara `auth.service`, el ciclo solo se rompería con imports diferidos, que ocultan el acoplamiento.
- Puertos documentados hoy: `KeyProvider`, `NotificationChannel`, `StorageProvider`, `Clock`. `PrincipalLoader` no está; hay que agregarlo a la tabla de puertos de `05_service_design.md` sección 1.
- Con la propuesta: core define el `Protocol` y el registro; Auth lo implementa en su `service.py` usando sus propios models (permitido). Ningún otro módulo toca `auth`. `current_actor` vive en core (US-016), así que fijarlo es core → core.
- La sesión de base que usa el cargador es la misma de la petición (`Depends(get_session)` de `core/db.py`), así que la lectura no abre otra conexión.
- banned-api: `current_user` no usa primitivas directamente; delega en `decode_access_token` (US-033) dentro de `core/security`.
- Paginación, bus de criptografía y `__audited__`: no aplican (solo lectura).

## Preguntas abiertas

- **Brecha 1 (core no puede depender de Auth).** Propuesta: en `core/security.py` se define `Principal` (dataclass congelada: `user_id: UUID`, `role: Role`, `member_id: UUID | None`), el puerto `PrincipalLoader(Protocol)` con `async def __call__(self, session: AsyncSession, user_id: UUID) -> Principal | None` y `register_principal_loader(loader)`. `modules/auth/service.py` define `load_active_principal(session, user_id)`, que devuelve `None` si el usuario no existe, tiene `is_active = false`, `locked_at` no nulo o `deleted_at` no nulo, y lo registra al importarse (`core.security.register_principal_loader(load_active_principal)`), igual que `core/events.subscribe`. El lifespan de `create_app()` verifica que hay un cargador registrado y, si no lo hay, el arranque falla: cerrado por defecto. En pruebas se registra un doble (esto también cumple la dependencia suave US-034 → US-041). Una prueba de arquitectura nueva impide que `app.core` importe `app.modules`. Pide aprobar el puerto y anotarlo en `05_service_design.md` sección 1. La alternativa descartada es validar solo los claims en core y que cada router consulte a `auth.service`: obliga a que todos los módulos dependan del router de Auth y no cumple los criterios 3 y 4 si un router lo olvida.
- **Contradicción con US-043 (EP-04), sin resolver en DECISIONES.md.** Esta historia dice 401 `unauthorized` para todo fallo y "sin revelar por qué falló el token" (criterio 7). US-043 (criterio 5) exige 401 `token_expired` para un access vencido, porque el cliente del front (`core/api/client.ts`) solo intenta el refresh con ese código. US-043 además usa `invalid_token` para los demás casos, un código que N-11 ya usa para el 400 de tokens de un solo uso. Pregunta cerrada: ¿`current_user` responde 401 `token_expired` solo para un access vencido con firma válida, y 401 `unauthorized` para todo lo demás (sin cabecera, firma inválida, claims malos, usuario inexistente, inactivo, bloqueado o dado de baja)? Alternativa por defecto propuesta: sí. Saber que un token propio venció no revela nada sobre la existencia de otros usuarios, y se evita reutilizar `invalid_token`. US-043 debe ajustar su criterio 5.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica (los models de `auth.users` son de US-041; core no los importa).

### Service
- [ ] T1 · En `api/src/app/core/security.py`: `Role = Literal["admin", "coach", "member"]`, `Principal`, el `Protocol` `PrincipalLoader`, `register_principal_loader(loader)`, `get_principal_loader()` (lanza `RuntimeError` si no hay) y `_reset_principal_loader_for_tests()` — 1,5 h
- [ ] T2 · Función pura `role_allowed(user_role: Role, allowed: frozenset[Role]) -> bool` — 0,5 h
- [ ] T3 · Dependencia `async def current_user(request: Request, session: AsyncSession = Depends(get_session)) -> AsyncIterator[Principal]`: parsea `Authorization` (esquema `Bearer` sin distinguir mayúsculas, exactamente un token); `decode_access_token` (US-033); rechaza `sub == SYSTEM_USER_ID`; llama al cargador; si `None` → `UnauthorizedError("unauthorized")`; `TokenExpired` → `UnauthorizedError("token_expired")` según la pregunta abierta; fija `current_actor` (US-016) con `token = current_actor.set(principal.user_id)`, hace `yield principal` y en `finally` `current_actor.reset(token)`; todas las 401 llevan `WWW-Authenticate: Bearer` y el mismo mensaje genérico ("Sesión no válida") — 2 h
- [ ] T4 · Fábrica `require_role(*roles: Role) -> Callable[..., Awaitable[Principal]]`: valida al definir la ruta que `roles` no está vacío y que cada rol existe (si no, `ValueError` al importar el router); la dependencia devuelta recibe `principal = Depends(current_user)` y lanza `ForbiddenError("forbidden")` si `role_allowed` es falso; la función lleva el atributo `__apex_roles__ = frozenset(roles)`, que lee US-035 — 1,5 h
- [ ] T5 · En `api/src/app/modules/auth/service.py` (adaptador; se completa cuando exista US-041): `async def load_active_principal(session, user_id) -> Principal | None` con un `SELECT` sobre `auth.users` por id y el filtro de estado, y el registro al importarse — 1 h
- [ ] T6 · En el lifespan de `api/src/app/main.py`: verificar `get_principal_loader()` después de registrar los routers y fallar el arranque con "no hay PrincipalLoader registrado (módulo auth)" — 0,5 h

### Schemas
- No aplica (el envelope `ErrorResponse` es de US-017).

### Router
- [ ] T7 · Router de prueba solo en tests (`api/tests/core/_routes.py`): `GET /_t/admin` con `require_role("admin")`, `GET /_t/staff` con `require_role("admin", "coach")` y `GET /_t/actor`, que devuelve el `current_actor` leído dentro del handler — 0,5 h

### Tests unitarios puros
- [ ] T8 · `api/tests/core/test_require_role.py::test_role_allowed`: tabla completa de 3 roles por 7 subconjuntos no vacíos; `require_role()` sin roles y `require_role("root")` lanzan `ValueError` — 1 h

### Tests de service con PostgreSQL
- [ ] T9 · `api/tests/auth/test_principal_loader.py` (con US-041): `load_active_principal` devuelve `Principal` para un usuario activo y `None` para inactivo, bloqueado, dado de baja, inexistente y `SYSTEM_USER_ID` — 1 h

### Tests de router
- [ ] T10 · `api/tests/core/test_require_role.py` con `httpx.AsyncClient` y un `PrincipalLoader` doble: admin en `/_t/admin` → 200; coach → 403 `forbidden`; sin cabecera → 401 `unauthorized` con `WWW-Authenticate`; `Basic xxx` → 401; token vencido → 401 `token_expired`; token firmado con otra llave → 401 `unauthorized`; usuario que el doble marca como bloqueado después de emitir el token → 401; usuario dado de baja → 401; token con `sub = SYSTEM_USER_ID` → 401; member en `/_t/staff` → 403 y coach → 200; `/_t/actor` devuelve el `user_id` del token y el `contextvar` queda vacío después de la petición; los cuerpos 401 de "inexistente" y "bloqueado" son idénticos byte a byte — 3 h

### Tests de arquitectura
- [ ] T11 · Nuevo `api/tests/architecture/test_core_does_not_import_modules.py`: recorre con `ast` todos los archivos de `app/core/**` y falla si alguno importa `app.modules` (directo, relativo o con `importlib`); `test_no_cross_models.py` (US-022) sigue verde — 1 h

### Front
- No aplica.

### DevOps
- No aplica.

### Seguridad
- [ ] T12 · Revisión: no hay ruta que lea `request.headers["Authorization"]` fuera de `current_user`; el `contextvar` no se filtra entre peticiones concurrentes (prueba con `asyncio.gather` de dos clientes con usuarios distintos dentro de T10); los mensajes 401 y 403 son genéricos; el estado del usuario se lee en cada petición — 0,5 h

## Orden de ejecución
1. Aprobación de la brecha (puerto `PrincipalLoader`) y de la pregunta del código `token_expired`
2. T8 (pruebas puras en rojo)
3. T11
4. T1
5. T2
6. T7
7. T10 (en rojo, con doble)
8. T3
9. T4
10. T6
11. T5 y T9 (cuando exista US-041)
12. T12

## Dependencias técnicas
- US-033 · JWT Ed25519: `decode_access_token`, `TokenExpired` y `TokenInvalid`.
- US-017 · Envelope de errores: `UnauthorizedError`, `ForbiddenError` y el formato `{ "error": { "code", "message" } }`.
- US-016 · Hook de auditoría after_flush: define `current_actor`; esta historia lo fija.
- US-012 · Base de datos: `get_session` y la sesión por petición.
- US-020 · create_app: lifespan donde se verifica el cargador.
- US-041 · Cuentas de usuario (suave): implementación real de `load_active_principal`; mientras tanto, doble.
- US-043 · Renovar sesión: depende del código `token_expired` (pregunta abierta).

## Endpoints
- Ninguno.

## Riesgos
- Si un módulo se olvida de usar `require_role`, el endpoint queda abierto — mitigación: la prueba de arquitectura de US-035.
- Consulta a `auth.users` en cada petición — impacto: menos de 10 usuarios concurrentes, despreciable; mitigación: búsqueda por clave primaria, sin caché (una caché retrasaría el bloqueo).
- `contextvar` sin `reset` deja el actor de una petición en otra — mitigación: `finally` en la dependencia con `yield` y la prueba de concurrencia de T12.
- Si la brecha no se aprueba y se implementa la historia literal, queda un ciclo de imports y core acoplado a Auth — mitigación: la prueba T11 lo bloquea en CI.

## Estimación
- Backend: 7,5 h
- Front: 0 h
- Pruebas: 6 h
- DevOps / seguridad: 0,5 h
- **Total: 14 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_require_role.py -q`
- [ ] `cd api && uv run pytest tests/auth/test_principal_loader.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/api/v1/auth/me` responde `401` sin cabecera y el cuerpo trae `"code":"unauthorized"`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.security --cov-fail-under=80`
