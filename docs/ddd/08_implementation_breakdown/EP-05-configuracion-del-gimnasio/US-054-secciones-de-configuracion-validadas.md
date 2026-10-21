# US-054 · Secciones de configuración validadas — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-05-configuracion-del-gimnasio/US-054-secciones-de-configuracion-validadas.md`
- **Épica:** EP-05 · Configuración del gimnasio
- **Bounded context / módulo:** Settings (`api/src/app/modules/settings/`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

Los dos supuestos de la historia (bloqueo optimista con `version` y 404 `section_not_available` para secciones futuras) quedaron aceptados por DECISIONES N-17, y el contenido de las secciones está fijado por Q11, Q12, N-18 y N-38/N-39. La tabla, los endpoints y la API interna para los módulos consumidores están resueltos. Las lecturas con un rol distinto de admin (etiquetas de medios de pago para el coach y nombre del gimnasio en la barra superior) no son de esta historia: se tratan en US-056 y US-061.

## Resumen

Crea el módulo `settings`: la tabla `settings.settings_sections` (migración canónica `0005_settings`), un registro de esquemas Pydantic por sección con `extra = "forbid"`, la función pura `validate_section`, el control de concurrencia por `version` y los endpoints `GET` y `PATCH /settings/{section}`, solo para admin. Los demás módulos leen la configuración por la API interna `settings.service.get(key)`, que devuelve el modelo validado con sus valores por defecto. En v0.1 están habilitadas `gym`, `payment_methods`, `privacy` y `memberships`. Las otras cuatro claves existen en el `CHECK` de la base y en el enum, pero responden 404 hasta que su épica las habilite.

## Correcciones aplicadas por DECISIONES.md

- La historia propone como supuesto que `version` funcione como bloqueo optimista con 409 → se implementa tal cual, con código `version_conflict`: aceptado por DECISIONES N-17.
- La historia propone como supuesto que una sección futura responda 404 `section_not_available` → se implementa tal cual: aceptado por DECISIONES N-17.
- Contenido futuro de la sección `classes` (Q11 incluía `allow_over_capacity`) → el esquema `classes`, cuando lo habilite US-154, solo tiene `default_capacity` y `checkin_window_min`, y `allow_over_capacity` no existe: corregido por DECISIONES N-38 y N-39. En v0.1 `classes` no está habilitada; el dato queda anotado en el registro para que nadie lo agregue.
- Secretos en la base → ningún esquema registrado admite contraseñas, tokens de API ni llaves; la sección `channels` (EP-14) solo guardará datos no secretos: corregido por DECISIONES Q12.
- Rangos y campos de cada sección → los fijan los esquemas de US-055, US-057 y US-058, siguiendo DECISIONES N-18. Esta historia solo deja el registro y el mecanismo.

## Validación contra el dominio

- Aggregate `SettingsSection` (raíz única, `02_domain_model.md` 2.14): `key`, `value` (JSON validado por el esquema de la sección) y `version`. Se confirma.
- Invariantes: cada sección tiene un esquema propio; `tv.device_token` se genera y no se escribe (lo implementa US-175, no esta historia); la sección queda auditada. Se confirman.
- Función pura `settings.validate_section(key, value) -> None | SettingsError` (`02_domain_model.md` 4). Se agregan dos auxiliares puras: `check_version(stored, sent)` y `defaults_for(key)`.
- Eventos: no emite ni consume. Los consumidores (memberships, payments, members y, más adelante, classes, notifications y tv) leen por service, en relación Conformist (`03_context_map.md` 2).
- RN-15: solo admin. Se confirma.
- Precisión de la historia: el criterio 4 devuelve `updated_by`, pero el mixin común solo trae `created_by`. Se agrega la columna `updated_by` a la tabla (dentro de la misma migración `0005_settings`). No cambia el contrato de la historia; lo hace posible.
- Precisión de la historia: la primera vez que se guarda una sección no existe la fila. Ese guardado inserta la fila y el hook la audita como `insert`, con `after` completo. Desde el segundo guardado la auditoría es `update` con `before` y `after`, como pide el criterio 8. El escenario BDD parte de una sección en versión 3, así que se cumple literalmente.

## Validación contra la arquitectura

- El módulo dueño es `modules/settings/`, con exactamente `router.py`, `schemas.py`, `models.py`, `service.py` y `exceptions.py` (errores `SectionNotAvailable`, `VersionConflict` y `SettingsValidationError`).
- Settings no depende de ningún otro módulo. Los consumidores llaman a `settings.service`; nadie importa `settings.models`. Lo verifica el test de US-022, que esta historia amplía con un caso explícito.
- Los esquemas de valor de cada sección viven en `schemas.py` y el service los usa para validar. Es un uso legítimo: no son modelo interno del dominio, sino el contrato del JSON.
- Las escrituras pasan por el ORM (`SELECT … FOR UPDATE` y mutación del objeto) para que el hook `after_flush` de US-016 audite. Un `UPDATE` de Core se saltaría la auditoría, así que queda prohibido en este service.
- Bus de criptografía: no aplica, porque la configuración no tiene datos personales. No se importa nada de la lista `banned-api`.
- La tabla tiene `__audited__ = True`. Rol: `require_role("admin")` en ambos endpoints (US-034). No hay listas, así que no aplica paginación.
- Envelope de error de US-017 o US-018: `{ "error": { "code", "message", "field"? } }`, con `field` en la forma `value.<ruta>` construida desde el `loc` de Pydantic.
- Columnas comunes con `CommonColumnsMixin` (UUID asignado en Python, `created_at`, `updated_at` y `created_by`). La configuración no se borra, así que no lleva `deleted_at`.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- [ ] T1 · `0005_settings`: tabla `settings.settings_sections` con `id UUID PRIMARY KEY`, `key TEXT NOT NULL CHECK (key IN ('gym','hours','payment_methods','channels','classes','memberships','tv','privacy'))`, `value JSONB NOT NULL`, `version INTEGER NOT NULL DEFAULT 0 CHECK (version >= 0)`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `created_by UUID NOT NULL`, `updated_by UUID NULL`; índice único `uq_settings_sections_key` sobre `key`; sin FK entre esquemas hacia `auth.users`; downgrade con `DROP TABLE` (el esquema lo crea y lo borra `0001_core_schemas`) — 1.5 h

### Models
- [ ] T2 · `api/src/app/modules/settings/models.py`: `SettingsSection(CommonColumnsMixin, Base)` con `__table_args__ = {"schema": "settings"}`, `__audited__ = True`, `key`, `value` (`JSONB`), `version` y `updated_by` — 1 h

### Service
- [ ] T3 · Funciones puras en `service.py`: `validate_section(key: SectionKey, value: dict) -> BaseModel` (lanza `SettingsValidationError(field="value.<loc>")`), `check_version(stored: int, sent: int) -> None` (lanza `VersionConflict`), `defaults_for(key: SectionKey) -> dict` y `ensure_enabled(key) -> None` (lanza `SectionNotAvailable` si la clave no está en `ENABLED_SECTIONS`) — 1.5 h
- [ ] T4 · Casos de uso: `get_section(session, key) -> SectionOut` (fila o defaults con `version=0`), `update_section(session, key, value, version, by) -> SectionOut` (`SELECT … FOR UPDATE`, `check_version`, `validate_section`, mutación ORM, `version += 1`, `updated_by = by`; si no hay fila y `version == 0`, inserta con `version = 1`; un `IntegrityError` por la clave única se traduce a `VersionConflict`), y la API interna tipada `get(session, key) -> BaseModel`, que devuelve el modelo validado con defaults para los consumidores — 2.5 h

### Schemas
- [ ] T5 · `schemas.py`: enum `SectionKey` (8 valores), `SECTION_REGISTRY: dict[SectionKey, type[BaseModel]]`, `ENABLED_SECTIONS = frozenset({gym, payment_methods, privacy, memberships})`, clase base `SectionValue` con `model_config = ConfigDict(extra="forbid", frozen=True)`, `SectionOut { key, value, version, updated_at, updated_by }` y `SectionPatchIn { value: dict, version: int >= 0 }`. Los esquemas concretos los aportan US-055, US-056, US-057 y US-058 (en esta historia se registra un esquema de prueba) — 1 h

### Router
- [ ] T6 · `router.py`: `GET /api/v1/settings/{section}` (admin; 200, 401, 403 y 404 `section_not_available` para una clave no habilitada o desconocida) y `PATCH /api/v1/settings/{section}` (admin; 200, 401, 403, 404, 409 `version_conflict` y 422 con `field`); registro en `main.py` — 1 h

### Tests unitarios puros
- [ ] T7 · `api/tests/settings/test_settings_rules.py`: `validate_section` con un valor válido, uno inválido (el `field` sale en la forma `value.x`) y uno con campo desconocido (422); `check_version` igual y distinto; `ensure_enabled` con `tv`, `hours` y una clave inexistente; `defaults_for` sin dependencia de la base — 1 h

### Tests de service con PostgreSQL
- [ ] T8 · `api/tests/settings/test_settings_service.py`: el primer guardado inserta con versión 1 y auditoría `insert`; el segundo sube a versión 2 con auditoría `update` y `before`/`after` completos; versión vieja da `VersionConflict` sin cambiar la fila; dos inserciones concurrentes con versión 0 dejan una sola fila y la otra recibe `VersionConflict`; `get` sin fila devuelve los defaults; un valor inválido no cambia la fila ni crea auditoría — 2 h

### Tests de router
- [ ] T9 · `api/tests/settings/test_settings_router.py`: admin 200 en GET y PATCH; coach 403 y sin token 401 en ambos; `GET /settings/tv`, `/hours`, `/channels` y `/classes` dan 404 `section_not_available`; PATCH con versión vieja da 409 `version_conflict`; PATCH con un valor inválido da 422 con `field` y el envelope correcto — 1.5 h

### Tests de arquitectura
- [ ] T10 · `api/tests/architecture/test_no_cross_models.py` (US-022): agregar un caso que confirme que ningún módulo fuera de `settings` importa `app.modules.settings.models`. Nuevo `api/tests/architecture/test_settings_no_secrets.py`: recorre `SECTION_REGISTRY` y falla si un campo coincide con `password|secret|api_key|private_key|smtp_pass|vapid` (Q12), y si algún esquema no tiene `extra="forbid"`. `test_every_route_has_role.py` sigue verde — 1 h

### Front
- No aplica.

### DevOps
- [ ] T11 · Regenerar `docs/openapi.json` (US-021) con los dos endpoints y los esquemas `SectionOut` y `SectionPatchIn` — 0.5 h

### Seguridad
- [ ] T12 · Revisión: `require_role("admin")` en las dos rutas; ningún valor de sección en los logs (el logger solo registra `key` y `version`); el 422 no devuelve el valor recibido completo, solo `field` y `message`; Q12 cubierto por T10 — 0.5 h

## Orden de ejecución
1. T1 (migración)
2. T2 (model)
3. T5 (enum, registro y esquemas de entrada y salida)
4. T7 (pruebas puras, en rojo)
5. T3 (funciones puras, en verde)
6. T8 (pruebas de service, en rojo)
7. T4 (casos de uso)
8. T9 (pruebas de router, en rojo)
9. T6 (router)
10. T10 (arquitectura)
11. T11 y T12

## Dependencias técnicas
- US-012 · Acceso async, columnas comunes y Alembic multiesquema: `CommonColumnsMixin`, UUID asignado en Python y esquema `settings` creado en `0001_core_schemas`.
- US-016 · Hook de auditoría after_flush: la auditoría de `settings_sections` con `before` y `after`.
- US-017 / US-018 · Envelope de errores del núcleo: el formato de los 404, 409 y 422.
- US-034 · current_user y require_role: el rol admin y los 401/403.
- US-022 · Prueba de arquitectura de models cruzados: se amplía en T10.
- US-021 · Exportación de OpenAPI: T11.

## Endpoints
- `GET /api/v1/settings/{section}` — roles: admin
- `PATCH /api/v1/settings/{section}` — roles: admin

## Riesgos
- Las lecturas que necesitan otro rol (el coach necesita etiquetas de medios de pago y nombre del gimnasio) podrían tentar a abrir `GET /settings/{section}` al coach: se expondrían `privacy` y `memberships` completas — mitigación: lectura no admin solo por endpoints de propósito específico en el módulo consumidor (US-056 y US-061), nunca por `/settings`.
- US-154 propone sembrar valores por defecto "al migrar", y esta historia los entrega con `version: 0` sin fila: son dos comportamientos distintos — mitigación: queda fijado aquí que los defaults viven en el esquema y no se siembran filas; se reporta la contradicción para el desglose de EP-21.
- Un `UPDATE` hecho con Core en lugar del ORM saltaría la auditoría — mitigación: T8 verifica la auditoría en cada guardado; la revisión de PR busca `update(` de SQLAlchemy Core en `settings/service.py`.
- Las dos inserciones concurrentes de la primera vez producen un `IntegrityError` — mitigación: se traduce a 409 y T8 lo prueba con dos sesiones.

## Estimación
- Backend: 8.5 h
- Front: 0 h
- Pruebas: 5.5 h
- DevOps / seguridad: 1 h
- **Total: 15 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/settings/test_settings_rules.py -q`
- [ ] `cd api && uv run pytest tests/settings/test_settings_service.py -q`
- [ ] `cd api && uv run pytest tests/settings/test_settings_router.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
- [ ] `psql … -c "\d settings.settings_sections"` muestra el índice único `uq_settings_sections_key`, el `CHECK` de las 8 claves y `version >= 0`
- [ ] Tras dos `PATCH /api/v1/settings/gym` con curl, `SELECT action, before IS NOT NULL, after IS NOT NULL FROM audit.audit_log WHERE table_name = 'settings_sections' ORDER BY seq` devuelve `insert` y luego `update` con `before` y `after`
- [ ] `curl -H "Authorization: Bearer <coach>" /api/v1/settings/gym` responde 403, y `GET /api/v1/settings/tv` como admin responde 404 `section_not_available`
- [ ] `docs/openapi.json` regenerado y sin diferencias en CI
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.settings --cov-fail-under=80`
