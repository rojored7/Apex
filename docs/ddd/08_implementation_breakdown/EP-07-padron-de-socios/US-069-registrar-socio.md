# US-069 · Registrar socio — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-07-padron-de-socios/US-069-registrar-socio.md`
- **Épica:** EP-07 · Padrón de socios
- **Bounded context / módulo:** Members (`api/src/app/modules/members/`)
- **Versión:** v0.1
- **Puntos de la historia:** 8

## Estado de preparación

**READY**

Los cuatro puntos irreversibles que la historia marcaba como riesgo ya están decididos: formato del blob (`CLAUDE.md`), normalización del índice ciego (N-02), índice único parcial sobre `document_idx` y la ausencia de columnas `*_hint` (N-01). Documento obligatorio, `warnings` en la respuesta y `data_consent_version` vacío los fija N-19. Lo que queda son dependencias de EP-01, EP-02 y EP-03, que no quitan el READY.

## Resumen

- Crea la tabla `members.members` (migración `0006_members`) con los cinco campos sensibles como blob `apx1....` y tres índices ciegos (`document_idx`, `phone_idx`, `email_idx`).
- Expone `POST /api/v1/members` para admin y coach; responde 201 con `MemberDetail` enmascarado y `warnings`.
- Fija la unicidad del documento entre socios no borrados con un índice único parcial y traduce el choque (incluida la carrera entre dos inserciones) a 409 `member_document_duplicated` con `existing_id`.
- Emite `MemberCreated` en la misma transacción y deja la fila `insert` de auditoría con los campos cifrados como blob (hook de US-016).
- Deja listo el contrato interno `members.service.get_ref(member_id)` que necesita `memberships.service.sell` (US-084).
- Front: `MemberFormPage` en modo crear, con casilla de autorización, aviso de autorización faltante y enlace "Ver socio existente".

## Correcciones aplicadas por DECISIONES.md

- La historia supone columnas `document_hint`, `phone_hint` y `email_hint` con fragmentos en claro → no se crean; la respuesta enmascarada se calcula en memoria con los valores que trae la petición (no hace falta descifrar al crear): corregido por DECISIONES N-01.
- El criterio 4 normaliza solo "minúsculas, sin espacios ni puntos" → la normalización es la de N-02 (NFKD sin diacríticos, minúsculas, sin espacios, puntos ni guiones; teléfono solo dígitos y sin `57`/`+57` inicial; correo en minúsculas y sin espacios), implementada en `core/crypto` por US-026; members solo pasa el valor crudo al bus: corregido por DECISIONES N-02.
- El supuesto "si existe la sección `privacy`, se toma su versión vigente" → `data_consent_version` queda vacío (`NULL`) en v0.1 siempre: corregido por DECISIONES N-19.
- El supuesto de documento obligatorio y la lista `warnings` → aceptados y agregados al contrato; toda respuesta de crear lleva `warnings` (lista vacía `[]` si no hay avisos): corregido por DECISIONES N-19.
- `created_by` cuando el alta viene de CLI o importación → `SYSTEM_USER_ID` o el usuario de `--as <email>` (lo usa US-111/US-112 sobre este mismo service): corregido por DECISIONES N-15.

## Validación contra el dominio

- Aggregate `Member` (raíz) con value objects cifrados `Document`, `Phone`, `Email` (con índice ciego), `BirthDate` y `EmergencyContact` (sin índice): coincide con `02_domain_model.md` 2.1 y la tabla de clases de dato de la sección 5.
- Invariantes: documento único entre no borrados (índice único parcial, RN-14); `first_name` y `last_name` no vacíos (función pura y `CHECK`); `data_consent_at` opcional con aviso en v0.1 (obligatorio desde v0.3, US-149, Q16).
- S7: `sex`, `data_consent_at` y `data_consent_version` existen desde esta migración para no migrar con datos después.
- Evento emitido: `MemberCreated(member_id)` (catálogo de eventos, sección 3). Sin suscriptores en v0.1 (bienvenida queda fuera hasta v1.0 por Q13).
- Funciones puras: `validate_member_input`, `compute_warnings`, `mask` (esta última la reutiliza US-073).
- Sin discrepancias con el dominio fuera de las correcciones listadas.

## Validación contra la arquitectura

- Módulo dueño: `members`. Archivos: `models.py`, `schemas.py`, `service.py`, `router.py`, `exceptions.py`.
- Bus de criptografía: los campos usan `Encrypted(data_class)` y `BlindIndexed(data_class)` de `core/crypto/types.py` (US-028). El service no importa `cryptography`, `hmac` ni `hashlib`; para el pre-chequeo de duplicado usa `core.crypto.bus.blind_index("member.document", value)`. Lint `banned-api` en verde.
- AAD = id del socio: el `id` se asigna con `uuid4()` en Python antes del `session.add` (mixin de US-012).
- Sin llamadas a otros services ni imports de `models` ajenos.
- Rol: `require_role("admin", "coach")` en el router (US-034).
- Auditoría: `__audited__ = True`; el hook `after_flush` de US-016 escribe la fila `insert` con blobs; `created_by` lo llena `before_flush` desde `current_actor`.
- Envelope de error de US-017 con `existing_id` en el 409.
- Logs: el filtro de `core/logging.py` (US-018) debe incluir `document`, `phone`, `email`, `birth_date`, `emergency_contact` en la lista de redacción.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- [ ] T1 · `0006_members`: tabla `members.members` (el esquema lo crea `0001_core_schemas`) con `id uuid PK`, `first_name text NOT NULL`, `last_name text NOT NULL`, `sex text NULL`, `status text NOT NULL DEFAULT 'active'`, `notes text NULL`, `document text NOT NULL`, `document_idx text NOT NULL`, `phone text NULL`, `phone_idx text NULL`, `email text NULL`, `email_idx text NULL`, `birth_date text NULL`, `emergency_contact text NULL`, `data_consent_at timestamptz NULL`, `data_consent_version text NULL`, `deleted_at timestamptz NULL`, `created_at`/`updated_at timestamptz NOT NULL DEFAULT now()`, `created_by uuid NOT NULL`; `CHECK (sex IN ('f','m','x'))`, `CHECK (status IN ('active','inactive'))`, `CHECK (btrim(first_name) <> '' AND btrim(last_name) <> '')`, `CHECK (document LIKE 'apx1.%')` y lo mismo para los demás blobs cuando no son nulos, `CHECK ((phone IS NULL) = (phone_idx IS NULL))` y su par para `email`; índice único parcial `uq_members_document_idx_alive ON (document_idx) WHERE deleted_at IS NULL`; índices no únicos `ix_members_phone_idx`, `ix_members_email_idx`; sin columnas `*_hint`; downgrade `DROP TABLE members.members` — 4 h

### Models
- [ ] T2 · `members/models.py`: clase `Member(CommonColumnsMixin, Base)` con `__tablename__ = "members"`, `__table_args__ = {"schema": "members"}` más los `CheckConstraint` e índices de T1, `__audited__ = True`, columnas `document: Mapped[str] = mapped_column(Encrypted("member.document"))`, `document_idx = mapped_column(BlindIndexed("member.document", source="document"))` y equivalentes para `phone`, `email`; `birth_date` con `Encrypted("member.birth_date")` (fecha ISO) y `emergency_contact` con `Encrypted("member.emergency_contact")` (JSON) — 3 h

### Service
- [ ] T3 · Función pura `validate_member_input(data: MemberInput, today: date) -> None` que lanza `MemberValidationError(field, code)`: nombres vacíos o solo espacios, `sex` fuera de `f`/`m`/`x`/`None`, `birth_date > today` (el `today` lo pasa el caso de uso con `today_bogota()`, Q28) — 2 h
- [ ] T4 · Funciones puras `compute_warnings(data) -> list[str]` (`"data_consent_missing"` si no viene `data_consent_at`) y `mask(field: SensitiveField, value: str | date | dict | None) -> str | None` (documento `•••• 0304`, teléfono `••• ••• 4567`, correo `l•••@•••.com`, fecha `••/••/1990`, contacto `"Registrado"`); trabajan sobre el valor en memoria, nunca sobre el blob — 2 h
- [ ] T5 · Caso de uso `async def create(session, data: MemberCreate, by: Actor) -> MemberCreated` (devuelve el resultado con el `MemberDetailOut`): valida (T3), pre-chequea duplicado con `bus.blind_index("member.document", data.document)` contra `document_idx` entre no borrados, asigna `id = uuid4()`, `status = "active"`, `data_consent_version = None`, hace `flush`; captura `IntegrityError` de `uq_members_document_idx_alive` (carrera) y la convierte en `MemberDocumentDuplicated(existing_id)` buscando el existente; emite `MemberCreated(member_id)` con `core.events.emit(event, session)`; arma la respuesta enmascarada con `mask` sobre los valores de entrada — 5 h
- [ ] T6 · Contrato interno `async def get_ref(session, member_id: UUID) -> MemberRef` (dataclass congelada `id`, `first_name`, `last_name`, `status`, `is_deleted`; lanza `MemberNotFound`) para que `memberships.service.sell` (US-084) valide el socio sin tocar `models`; nunca devuelve el ORM — 1 h
- [ ] T7 · `members/exceptions.py`: `MemberError` (base), `MemberValidationError`, `MemberDocumentDuplicated(existing_id)`, `MemberNotFound`; registro de su traducción al envelope (422, 409 con `field = "document"` y `existing_id`, 404) en los handlers de `core/errors.py` por tipo base de dominio — 1 h
- [ ] T8 · Evento `MemberCreated(DomainEvent)` con `member_id: UUID`, dataclass congelada declarada en `members/service.py` (los consumidores la importan desde el service del emisor) — 0.5 h

### Schemas
- [ ] T9 · `members/schemas.py`: `EmergencyContactIn {name, phone}`, `MemberCreate` (`model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)`, `document` obligatorio, `phone?`, `email?` como `EmailStr`, `birth_date?` `date`, `sex?` `Literal["f","m","x"] | None`, `notes?` con máximo 2.000 caracteres, `data_consent_at?` `AwareDatetime`), `MemberDetailOut` (nombres, `sex`, `status`, `notes`, campos sensibles enmascarados como `str | None`, `data_consent_at`, `deleted_at`, `membership_status: str | None`, `created_at`, `updated_at`, `warnings: list[str]`) — 2 h

### Router
- [ ] T10 · `members/router.py`: `POST /api/v1/members` con `Depends(require_role("admin", "coach"))`, `status_code=201`, `response_model=MemberDetailOut`; códigos 201, 401, 403, 409, 422; registra el router en `main.py` — 1 h

### Tests unitarios puros
- [ ] T11 · `api/tests/members/test_member_rules.py`: `validate_member_input` (nombre `"   "`, apellido vacío, sexo `"z"`, fecha futura, fecha de hoy válida con `FrozenClock`), `compute_warnings` (con y sin autorización), `mask` por cada campo y con `None` — 2 h

### Tests de service con PostgreSQL
- [ ] T12 · `api/tests/members/test_service_create.py`: alta completa (blob empieza por `apx1.` y descifra al valor con `aad = id`); `"1.020.304"` y `"1020304"` dan el mismo `document_idx`; duplicado entre vivos → `MemberDocumentDuplicated` con `existing_id`; duplicado contra un socio con `deleted_at` → se crea; carrera de dos sesiones que insertan el mismo documento → una gana y la otra recibe el error de dominio; fila `insert` en `audit.audit_log` con blobs y sin claro; `MemberCreated` emitido y un handler que falla revierte el alta; `created_by` = actor — 5 h

### Tests de router
- [ ] T13 · `api/tests/members/test_router_create.py`: 201 con admin y coach, 403 con `member`, 401 sin token, 422 con `field` (`first_name`, `sex`, `birth_date`, `document` ausente), 409 con `existing_id` en el envelope, `warnings == ["data_consent_missing"]` y `warnings == []`; captura de logs (`caplog`) sin documento, teléfono, correo ni token — 3 h

### Tests de arquitectura
- [ ] T14 · `api/tests/architecture/test_members_encrypted_at_rest.py`: crea socios y verifica con SQL crudo que `SELECT document, phone, email, birth_date, emergency_contact FROM members.members` no contiene ningún valor sembrado y que cada blob empieza por `apx1.<key_id>.A256GCM.`; siguen en verde `test_no_cross_models.py` (US-022), `test_every_route_has_role.py` (US-035) y `test_banned_imports.py` (US-031) — 1.5 h

### Front
- [ ] T15 · `web/src/features/members/schemas.ts` (Zod `memberCreateSchema` con las mismas reglas del API) y `web/src/features/members/api.ts` (`useCreateMember` con TanStack Query; mapea el envelope a errores de campo) — 2 h
- [ ] T16 · `web/src/features/members/pages/MemberFormPage.tsx` en modo crear y `components/MemberFormFields.tsx` (React Hook Form, `Field` del kit): campos de `Socio_Form` sin foto ni adjuntos, casilla "El socio autorizó el tratamiento de datos" que envía `data_consent_at = ahora`, aviso "Falta la autorización de tratamiento de datos" cuando la respuesta trae `data_consent_missing`, enlace "Ver socio existente" a `/socios/{existing_id}` ante 409, redirección a la ficha; `// DESIGN-GAP:` del aviso y la casilla; solo tokens de color — 5 h
- [ ] T17 · Vitest + Testing Library en `web/src/features/members/pages/MemberFormPage.test.tsx`: validación en cliente, error de campo devuelto por el API, enlace del 409, aviso de autorización — 2.5 h
- [ ] T18 · Playwright `web/tests/e2e/members.spec.ts`: "crear socio, buscarlo por teléfono y abrir su ficha" (se completa con US-070 y US-073) — 1 h

### DevOps
- [ ] T19 · Regenerar `docs/openapi.json` (US-021) y cubrir `0006_members` con `api/tests/core/test_migrations.py::test_downgrade_a_base_vacia_y_vuelta_a_head` y `test_single_head`, que ya corren en el job `api`; no hay paso nuevo de CI — 0.5 h (corregido en Sprint 2, ver `docs/ddd/blueprints/sprint-02-plan.md`, P-MIG)

### Seguridad
- [ ] T20 · Revisión: lista de redacción de `core/logging.py` con los cinco campos sensibles; que el mensaje de `IntegrityError` no se propague al cliente ni al log; que `existing_id` solo sale para roles admin y coach; que `notes` no se use para datos sensibles (texto de ayuda en el formulario) — 1 h

## Orden de ejecución

1. T1 (migración) y T2 (modelo), con US-012, US-028 y US-016 ya integradas.
2. T11 (pruebas puras en rojo) y luego T3 y T4.
3. T7 y T8 (excepciones y evento).
4. T12 (pruebas de service en rojo), luego T5 y T6.
5. T9 y T10 (schemas y router), luego T13 y T14.
6. T19 y T20.
7. T15, T16, T17 (front) y al final T18 (E2E, cuando existan US-070 y US-073).

## Dependencias técnicas

- US-012 · Base de datos y Alembic multiesquema: mixin `CommonColumnsMixin` con `id` asignado en Python y `0001_core_schemas` con el esquema `members`.
- US-028 · Tipos de columna Encrypted y BlindIndexed: columnas cifradas e índice ciego en el mismo flush.
- US-026 · Índice ciego HMAC: normalización de N-02 por `data_class`.
- US-029 · Bitácora crypto_ops por lote: cada `encrypt` e `index` queda registrado.
- US-016 · Hook de auditoría after_flush: fila `insert` con blobs y `created_by`.
- US-014 · Bus de eventos transaccional: `emit` en la misma sesión.
- US-017 · Envelope de errores: `existing_id` en el 409.
- US-018 · Logging JSON sin datos sensibles: lista de redacción.
- US-034 · Dependencias current_user y require_role.
- US-061 · Panel layout y US-060 · Formato de dinero y fechas (front).

## Endpoints

- `POST /api/v1/members` — roles: admin, coach

## Riesgos

- Normalización del índice ciego mal implementada en US-026: deja duplicados invisibles y obliga a reindexar todo el padrón — mitigación: T12 prueba las variantes con puntos, guiones, tildes y prefijo `+57` contra el bus real antes de cargar datos (US-111/US-112).
- Carrera entre dos altas con el mismo documento: el pre-chequeo no basta — mitigación: el índice único parcial es la garantía final y T5 traduce la `IntegrityError` a 409 (probado en T12).
- Coste de cinco `encrypt` más tres `index` por alta: aceptable a escala del gimnasio (menos de 10 usuarios concurrentes) — mitigación: medir en T12; el registro en `crypto_ops` agrupa por lote cuando aplica (US-029).
- Front condicionado a D1: si el gate no aprueba construir el front en `web/`, T15 a T18 salen de este repositorio — mitigación: el contrato queda en `docs/openapi.json`.

## Estimación

- Backend: 21.5 h
- Front: 10.5 h
- Pruebas: 11.5 h
- DevOps / seguridad: 1.5 h
- **Total: 45 h**

La suma supera la referencia de 8 puntos (28 a 42 h) porque incluye el formulario completo del front y la carrera de inserciones; se mantiene sin partir, como pide la historia, para no dejar un socio sin cifrar.

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/members/test_member_rules.py -q`
- [ ] `cd api && uv run pytest tests/members/test_service_create.py -q`
- [ ] `cd api && uv run pytest tests/members/test_router_create.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm test -- src/features/members`
- [ ] `psql -c "SELECT count(*) FROM members.members WHERE document NOT LIKE 'apx1.%'"` devuelve 0 tras sembrar socios de prueba.
- [ ] `curl -X POST /api/v1/members` dos veces con `"1.020.304"` y `"1020304"`: la segunda responde 409 con `existing_id` igual al `id` de la primera.
- [ ] `psql -c "\d members.members"` no muestra ninguna columna `*_hint`.
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.modules.members --cov-fail-under=80`
