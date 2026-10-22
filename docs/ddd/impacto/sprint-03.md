# Análisis de impacto previo · Sprint 3 (núcleo comercial: membresías, pagos y ficha del socio)

Fecha: 22 de octubre de 2026 (tarde; línea base tomada a las 11:30 hora local).
Alcance: `update` sobre un repositorio con código (`flow-update`, Fase 0).
Anclaje: rama `feat/sprint-03-membresias-pagos`, HEAD `d65056e` ("cierre del Sprint 2"),
`git status` limpio, un solo worktree. El nombre de la rama coincide con `SPRINT-03.md`.
Plan de referencia: `docs/ddd/09_sprint_plan/SPRINT-03.md` (25 historias, 22 endpoints nuevos más
dos filtros en `GET /members`, migraciones `0008_memberships` a `0011_payments_immutability`,
11 slices de backend y 7 de front).

## Veredicto: AMARILLO

Se puede avanzar a la Fase 1 con `--allow-amber`. Nada es ROJO: los contratos del Sprint 2 que
este sprint consume existen con la firma esperada, `btree_gist` y los esquemas `memberships` y
`payments` están creados desde `0001`, la suite está en verde y el stack de desarrollo está arriba
en `0007_plans (head)`. El amarillo viene de que **ocho pruebas de arquitectura que corren en
todos los gates (A-5) fallan tal cual están en cuanto el primer slice agregue `memberships` a
`MODULES`** (tuplas y conjuntos literales que fijan el estado del Sprint 2: `MODULES`,
`ALLOWED_EDGES`, `LAZY_IMPORT_WHITELIST`, `CON_LIMITE`, `PENDING_AUDITED`, listas de rutas del
front), de que **tres contratos del plan chocan con pruebas existentes** (`GET /payments/methods`
como arreglo suelto, listas por socio sin `q`, el router de socios que publica 429 en todas sus
rutas) y de **nombres de contrato en los desgloses que no son los del código** (`members.service.
ref`, `bus.op_context`, `Depends(get_session)`, `Pagination`, `member.document.change`). Todo se
absorbe con las condiciones de la sección 8; ninguna exige cambiar el alcance.

## Cómo se verificó

- Lectura completa de `SPRINT-03.md`, `CLAUDE.md`, `scripts/workflow/README.md`, `docs/ddd/impacto/
  sprint-02.md`, la sección 9 de `docs/scratch/sprint-02-verify-delivery.md`, las decisiones Q1 a
  Q28, N-01, N-20, N-23 a N-28, G-03, G-04 y las de Sprint 2 y S2-R de `DECISIONES.md`, las brechas
  de `docs/BRECHAS.md` que tocan membresías, pagos y ficha, y los desgloses de US-056, US-071,
  US-073, US-074, US-083 a US-086, US-095, US-096 completos y el resto (US-075, US-076, US-087 a
  US-093, US-097 a US-101) por sus secciones de contrato.
- Lectura del código que el sprint toca (sección 1), de las 29 pruebas de `api/tests/architecture`,
  de `api/tests/conftest.py`, `api/tests/factories/`, de las pruebas de reglas del front
  (`web/tests/lint`, `web/tests/kit-inventory.test.ts`, `web/src/routes.test.ts`,
  `web/src/layouts/nav.test.ts`) y `grep` de dependientes inversos sobre `api/src`, `api/tests`,
  `api/migrations`, `web/src`, `web/tests`, `infra` y `scripts`.
- Línea base observada (sección 5), sin correr las suites. No se modificó ningún archivo fuera de
  este.

## 1. Blast radius: módulos y archivos que el sprint toca o crea

### `api/src/app/main.py` (`MODULES`)

- Cambio: `MODULES` pasa de `("auth", "settings", "audit", "members", "plans")` a incluir
  `memberships` y `payments`. Orden recomendado: `(..., "members", "plans", "memberships",
  "payments")`. El orden no condiciona los imports (`memberships.service` importa
  `payments.service` arriba del archivo y registra el gate al importarse; `members.service`
  importa `memberships.service` de forma perezosa), pero sí el orden de los routers: las rutas
  `/members/{id}/memberships` y `/members/{id}/payments` viven en los routers de `memberships` y
  `payments` (US-084, US-101) y no chocan con `GET /members/{id}` de `members` porque FastAPI
  empareja por ruta completa.
- Lo rompe: `tests/architecture/test_audit_module.py::test_modules_de_v01_incluye_audit_despues_de_auth`
  afirma la tupla literal de cinco entradas. Falla en S3-B1. Además `load_module_services()` lo
  llaman `create_app`, `cli._load_module_services()` (existe, `cli.py:237`) y `tests/conftest.py`
  al importarse: el gate `set_membership_gate` queda registrado en los tres procesos sin trabajo
  extra, que es lo que `test_gates_registered.py` (US-085 T8) tiene que comprobar. No hay
  `worker/main.py` todavía (US-113, Sprint 4A): la prueba no puede exigirlo.
- Lo importan: `cli.py`, 15 archivos de `tests/` (ver impacto Sprint 2, sección 1). `test_audited_tables.py`
  y `test_list_routes_use_page_params.py` recorren `MODULES` e importan `models` y `router` de cada
  entrada: los dos módulos nuevos nacen con `router.py`, `schemas.py`, `service.py`, `models.py` y
  `exceptions.py` completos (regla de módulos 1).

### `api/src/app/modules/memberships/` (nuevo; S3-B1, B2, B4 a B7, B11)

- Contratos del Sprint 2 que consume, verificados en HEAD:
  - `members.service.get_ref(session, member_id) -> MemberRef` (`service.py:277`): lanza
    `MemberNotFound` si no existe; `MemberRef(id, first_name, last_name, status, is_deleted)`.
    **Los desgloses de US-084 y US-093 lo llaman `ref(member_id) -> MemberRef | None` con
    `deleted_at`**: el nombre canónico es `get_ref`, no devuelve `None` y expone `is_deleted`.
  - `members.service.ensure_exists(session, member_id, *, include_deleted=False)` (`:293`),
    `search_ids(session, q, *, include_deleted=False) -> set[UUID]` (`:501`; US-091 lo anota como
    `list[UUID]`, es `set`), `names_for(session, ids) -> dict[UUID, MemberName]` (`:510`;
    `MemberName(id, first_name, last_name, sex)`), `id_by_document`, `count`.
    **`members.service.active_ids()` que pide US-092 T5 para `summary()` no existe**: se agrega a
    `members.service` en S3-B7 (una consulta de ids vivos) o `summary` usa `count` más
    `member_ids_by_status`; decidirlo en el plan.
  - `plans.service.get(session, plan_id, *, for_share=False) -> PlanSnapshot` (`plans/service.py:264`):
    `FOR SHARE` real; `PlanNotFound` si no existe o está dado de baja. `get_including_deleted`
    (`:274`) y `names_for(session, plan_ids) -> dict[UUID, str]` (`:284`). `PlanSnapshot` trae
    `price_cop`, `kind`, `duration_days`, `class_count`, `is_active`, `deleted_at`.
  - `settings.service.memberships_policy(session) -> MembershipsPolicy` (`settings/service.py:190`):
    dataclass congelada en `settings/schemas.py` con `expiring_days`,
    `max_freeze_days_per_membership`, `max_freezes_per_membership`, `max_retroactive_days`
    (S2-D45). Importar `settings.schemas` desde otro módulo está permitido (`_imports.FOREIGN_ALLOWED`).
  - `auth.service.names_for(session, user_ids) -> dict[UUID, str]` (`auth/users.py:142`,
    reexportada en `auth/service.py:62` y `__all__`): lo usan US-098 y US-099 para
    `registered_by_name` y `voided_by`.
  - `core.clock`: `current_clock()`, `today_bogota()` en el `Clock`, `to_bogota_date(instant)`
    (`clock.py:28`) para los handlers (US-086). Existe `get_clock()` (`:90`) pero ninguna ruta lo
    inyecta como dependencia: el patrón del repo es `current_clock()` dentro del service.
  - `core.events`: `DomainEvent` (kw_only, `occurred_at` del reloj), `subscribe` (idempotente),
    `emit(event, session)` con `MAX_EVENT_DEPTH = 5` (la cadena más larga del sprint es
    `sell → register → PaymentRegistered → on_payment_registered → MembershipActivated`,
    profundidad 3). Los eventos nuevos (`MembershipSold`, `MembershipActivated`,
    `MembershipActivationReverted`, `MembershipFrozen`, `MembershipCancelled`,
    `PaymentRegistered`, `PaymentVoided`, `SensitiveFieldRevealed`, `MemberUpdated`,
    `MemberDeactivated`) se declaran en el `service.py` del emisor, como `MemberCreated` hoy;
    `core/events.py` no cambia.
  - `core.db`: `SessionDep` (único alias, S2-R8), `CommonColumnsMixin` con `id` asignado al
    construir, `violated_constraint(error)` para traducir el `23P01` del `EXCLUDE` (asyncpg expone
    `constraint_name`, así que `MembershipOverlap` se detecta por nombre de restricción, no por
    SQLSTATE), `SoftDeleteMixin` solo para socios, planes y usuarios (no para membresías).
  - `core.errors.responses_for(*codes)` (catálogo 400/401/403/404/409/422/429/500) y
    `DomainError` con `field` y `existing_id` como kwargs.
  - `core.pagination`: `PageParams`, `Page[T]`, `SearchQuery` (patrón sin controles, 100
    caracteres), `paginate`, `to_page`. **Los desgloses de US-091 y US-093 hablan de
    `Pagination`/`page: Pagination`: el tipo es `PageParams`.**
  - `core.ratelimit.enforce(bucket, key, *, limit, window_s, kind="user")` si se decide limitar
    `reveal` por usuario (ver `members/router.py` abajo).
- Pruebas de arquitectura que lo vigilan y hoy fallan al crearlo:
  - `test_service_import_graph.py`: `ALLOWED_EDGES = {("audit","auth"), ("auth","settings")}` y
    `test_plans_no_agrega_aristas` (nadie importa `plans.service`). Aristas nuevas del sprint:
    `memberships → members`, `memberships → plans`, `memberships → settings`,
    `memberships → payments`, `payments → settings` (US-056 `methods`), `payments → members`
    (`search_ids`, `ensure_exists`), `payments → auth` (`names_for`); perezosas:
    `members → memberships` (S3-B9). `LAZY_IMPORT_WHITELIST` está vacía y la prueba afirma
    literalmente `frozenset() == LAZY_IMPORT_WHITELIST` ("vacía hasta el Sprint 3"): esa
    aserción se quita en S3-B9 con el par `("members", "memberships")`. La prueba ya absorbe
    `test_service_import_cycles.py`, `test_payments_does_not_import_memberships.py` y
    `test_payments_dependencies.py` que nombran US-071, US-085 y US-098: no se crean aparte
    (`SPRINT-03.md`, "Tests de arquitectura"). El analizador recorre todos los `*.py` del módulo,
    así que partir `service.py` en archivos privados no esconde aristas.
  - `test_audited_tables.py`: `PENDING_AUDITED` tiene `memberships.memberships` y
    `payments.payments`; **`memberships.membership_freezes` no está en ninguna lista y
    `test_toda_tabla_no_excluida_esta_auditada` exige `__audited__ = True` en toda tabla no
    excluida**: `MembershipFreeze` nace auditada (US-089 T2 ya lo dice) y las tres tablas pasan a
    `REQUIRED_AUDITED_TABLES_V01` en su slice. `__audit_subject__ = "member_id"` en `Membership` y
    `Payment` (lo documenta `core/audit.py`), y en `MembershipFreeze` no aplica salvo que lleve
    `member_id` (no lo lleva: el sujeto se pierde en esas filas; aceptable, anotarlo).
  - `test_file_and_function_size.py`: 800 líneas por archivo y 50 por función. `memberships/
    service.py` con reglas puras, `sell` (renovar y primer pago), `freeze`, `cancel`, `list`,
    `get`, `summary`, `status_for`, `member_ids_by_status`, `count_active_by_plan`, `refs_for`,
    `payability` y dos handlers no cabe en 800 líneas: partirlo desde S3-B1 (por ejemplo
    `rules.py` puro, `sales.py`, `freezes.py`, `queries.py` y `service.py` como fachada que
    reexporta, patrón S2-R10 de `auth`), y registrar los privados en
    `tests/architecture/_imports.PRIVATE_HELPERS` si se quiere que nadie fuera del módulo los
    importe. `sell` con sus nueve pasos (US-084 T5) supera las 50 líneas si se escribe de corrido.
  - `test_no_store_routes.py`: toda ruta con rol lleva `core.http.no_store`; ponerlo en
    `dependencies=[Depends(no_store)]` del `APIRouter` de cada módulo nuevo, como `members`.
  - `test_session_scope.py`: solo `SessionDep`; **los desgloses de US-084 T8 y US-095 T8 escriben
    `Depends(get_session)` y `Depends(get_clock)`**: ambos están prohibidos por S2-R8 y esta
    prueba (`get_session` sin `scope="function"` confirma después de enviar la respuesta).
  - `test_list_routes_use_page_params.py`: todo `GET` con respuesta `Page_*` exige `PageParams`,
    un parámetro `q` y `limit` con máximo 200; y **ningún `GET` responde un arreglo suelto**.
    Afecta a `GET /members/{id}/memberships` (US-093 no declara `q`) y `GET /members/{id}/payments`
    (US-101 solo declara `voided`): las dos necesitan `q: SearchQuery = None` (cableado a
    `search_ids` o solo aceptado). Y `GET /payments/methods` (US-056 T3/T4: "`[{ code, label,
    hint }]`") falla como "devuelve un arreglo sin paginar": responder un objeto, por ejemplo
    `PaymentMethodsOut { items: list[PaymentMethodOut] }`.
  - `test_list_rows_without_sensitive_fields.py`: revisa todo `GET` bajo `/api/v1/members` con
    `Page_*`: las filas de `/members/{id}/memberships` y `/members/{id}/payments`
    (`member_first_name`, `member_last_name`, `plan_name`) pasan; nunca agregar `phone`,
    `email`, `document` ni `*_idx` a `MembershipRow`/`PaymentRow`.
  - `test_error_codes_per_route.py`: `CON_LIMITE` es un conjunto literal de ocho rutas: una ruta
    nueva declara 429 si y solo si está ahí; toda ruta con rol declara 401; 422 solo con
    parámetros o cuerpo (todas las nuevas tienen `{id}` en el path, así que declaran 422).
  - `test_every_route_has_role.py` (`PUBLIC_ROUTES` fija en 8, no cambia), `test_no_direct_now.py`
    (nada de `date.today()`; `today` sale de `current_clock().today_bogota()`),
    `test_banned_imports.py` y `test_ruff_banned_api.py` (ninguna primitiva: el lock por socio
    es `pg_advisory_xact_lock(hashtextextended(...))` en SQL, no `hashlib`),
    `test_no_cross_models.py` (nunca `members.models`, `plans.models`, `settings.models`;
    `schemas` y `exceptions` ajenos sí: reutilizar `members.exceptions.MemberNotFound` en vez de
    duplicarlo en `memberships/exceptions.py` como propone US-084 T4, para no tener dos códigos
    `member_not_found` distintos).
- Migraciones: `0008_memberships` (`EXCLUDE USING gist (member_id WITH =, daterange(start_date,
  end_date, '[]') WITH &&) WHERE (status <> 'cancelled')`) y `0009_membership_freezes`;
  `migrations/env.py` necesita dos líneas `from app.modules.memberships import models` y
  `... payments import models` (hoy importa `auth`, `members`, `plans`, `settings`) para que
  `target_metadata` las conozca.

### `api/src/app/modules/payments/` (nuevo; S3-B3, B4, B5, B8, B11)

- Puerto G-03: `MembershipPayability(exists, cancelled, member_id)`, `MembershipGate`,
  `set_membership_gate(gate)`; `register` falla cerrado sin gate. Como `tests/conftest.py` llama
  a `load_module_services()` al importarse, el gate real queda registrado en toda la suite desde
  S3-B4: el doble de `tests/payments/conftest.py` (M-1) tiene que ser una fixture que lo
  sustituye y lo restaura, y la prueba "sin gate falla cerrado" tiene que desregistrarlo y
  restaurarlo (igual que `restaurar_bus` hace con los handlers).
- `register` hace `flush` antes de `emit(PaymentRegistered)` (US-086 depende de ello) y
  `sum_not_voided` (`COALESCE(SUM) ... voided = false`). `void` traduce el error del trigger
  (`payments_immutable`) a 409 `payment_already_voided` tras `SELECT ... FOR UPDATE`.
- `payments.service.methods(session)` delega en `settings.service.payment_methods()` (US-056):
  arista `payments → settings` nueva en `ALLOWED_EDGES`; `test_payment_method_codes.py` compara
  `settings.schemas.PAYMENT_METHOD_CODES` con el `Literal` de `payments.schemas` y el `CHECK` de
  `0010`.
- Migraciones `0010_payments` (con `member_id NOT NULL` copiado, índices `paid_at DESC`,
  `membership_id`, `(member_id, paid_at DESC)`, `CHECK payments_void_coherent`) y
  `0011_payments_immutability` (función `payments.forbid_mutation()` y `payments.forbid_truncate()`,
  mismo patrón que `audit.forbid_mutation()` de `0002_audit_log.py:79-93`).
- Consecuencia para la suite: después de `0011`, `DELETE FROM payments.payments` y `TRUNCATE`
  fallan también en `db_test`. `LIMPIEZA_DE_SESION` y la limpieza de `dos_sesiones` en
  `tests/conftest.py` tienen que agregar `memberships.membership_freezes`,
  `memberships.memberships` y `payments.payments`, esta última entre `ALTER TABLE
  payments.payments DISABLE TRIGGER USER` y `ENABLE TRIGGER USER` (como `audit.audit_log` y
  `crypto.crypto_ops`), y con `to_regclass(...)` para que el Rojo de B3 no rompa el resto.
  `test_no_physical_delete.py` (US-076) debe escanear solo `src/`, como hace hoy
  `test_no_physical_delete_users.py`, o la limpieza de pruebas lo dispararía.
- `tests/factories/__init__.py` (`FACTORIES`) solo exige fábrica por tabla con columnas
  cifradas (`test_no_plaintext_at_rest`): `memberships` y `payments` no las tienen, pero
  `make_membership` y `make_payment` en `tests/factories/` evitan repetir inserciones en más de
  veinte archivos de prueba del sprint.

### `api/src/app/modules/members/*` (ampliado; S3-B9, B10, B11)

- `service.py` tiene 523 líneas; `get` (ficha), `reveal`, `update` (con `diff_fields`,
  `ensure_can_change`), `deactivate`, `reactivate`, `chip_to_filter` y el decorado por lote de la
  lista lo pasan de 800. Partir en S3-B9 (por ejemplo `members/detail.py` y `members/edit.py`,
  con `service.py` reexportando) y registrarlos en `PRIVATE_HELPERS`.
- Descifrado con propósito: **no existe `bus.op_context`** (US-073 T1, US-074 T1). La puerta es
  `core.crypto.types.reveal(obj, field, purpose)` (`types.py:224`), que llama a
  `bus.decrypt(blob, aad_for(id), purpose=..., record_id=id)` y deja la fila `decrypt` en
  `crypto_ops`; para la ficha, cinco llamadas dentro de `with bus.batch("decrypt", None):` dan una
  fila agregada por `data_class` con el mismo `batch_id` y `purpose = 'mask'` (los propósitos
  válidos son `mask`, `reveal`, `notify`, `auth_link`, `export`, `crypto/models.py:65`). La fila
  `decrypt` sobrevive al rollback (`oplog._after_soft_rollback`), así que una prueba de "reveal
  que falla al auditar" verá igualmente la fila `decrypt`: el criterio es "sin valor en la
  respuesta", no "sin fila".
- Auditoría de `reveal`: `core.audit.record(session, *, action="reveal", table_name=...,
  record_id, before=None, after={"field": ...}, user_id=None, subject_member_id=None)`. El hook
  escribe `table_name` como `"members.members"` (`_table_name`) y `tests/audit/test_reveal_entry.py`
  ya usa ese nombre; **US-074 T1 dice `table_name="members"`**: usar `"members.members"` y
  `subject_member_id=member_id`. `record` toma el actor del contexto si no se pasa `user_id`.
  `test_reveal_entry.py` pasa a la fábrica (`S2-D31`) y `test_no_sensitive_in_logs.py::
  test_reveal_no_deja_el_valor_revelado_en_los_logs` deja de estar `skip` en S3-B10 (hoy su
  cuerpo es `raise AssertionError`).
- Commit antes de responder: US-074 T4 pide `await session.commit()` explícito en el router. Con
  `SessionDep` (`scope="function"`, N-1) el commit ya ocurre antes de enviar la respuesta y un
  fallo llega como envelope 500; el commit explícito dentro de `async with session.begin()` es
  redundante. Mantener el patrón del repo (ninguna ruta hace `commit`) y cubrir el caso con la
  prueba "si `audit.record` lanza, la respuesta es 500 sin valor".
- `router.py`: `APIRouter(..., responses=responses_for(401, 403, 429))` publica 429 en todas las
  rutas del router. **Las cinco rutas nuevas (`GET`/`PATCH`/`DELETE /members/{id}`, `POST
  .../reveal`, `POST .../reactivate`) declararían 429 sin tener límite y
  `test_las_rutas_con_limite_declaran_429_y_las_demas_no` falla.** Dos salidas: mover el 429 del
  router a `POST /members` y `GET /members` (que sí lo tienen), o dar límite por usuario a las
  nuevas (al menos a `reveal`, que US-074 T10 anota como mejora) y agregarlas a `CON_LIMITE`.
  Decidirlo en S3-B9.
- `schemas.py`: `MemberListQuery` (`extra="forbid"`, `frozen`) gana `membership_status` y
  `plan_id`; `MemberRowOut.membership_status`/`plan_name` y `MemberDetailOut.membership_status`
  ya existen como `str | None = None` (aditivo para el front, que ya los valida en
  `memberRowSchema`). `MemberPatch` nuevo (US-075 T6) con `model_fields_set`. La acción de
  permiso del front para cambiar el documento es `members.document.update`
  (`web/src/core/auth/permissions.ts`), no `member.document.change` como dice US-075 T11.
- `tests/members/_apoyo.CAMPOS_DETALLE` fija las claves exactas de `MemberDetailOut`: si la
  ficha agrega campos (por ejemplo `plan_name`), esa constante y `test_service_create.py` cambian.
- Lo importan: `tests/members/*` (10 archivos), `tests/architecture/test_no_sensitive_in_logs.py`,
  `test_members_encrypted_at_rest.py`, `test_import_analyzer.py`, `tests/factories/members.py`.
  Los services de `memberships` y `payments` pasan a importarlo.

### `api/src/app/modules/settings/*` (sección `payment_methods`; S3-B3)

- `schemas.py`: `ENABLED_SECTIONS` gana `SectionKey.payment_methods`; `PaymentMethodsSettings`
  (`cash`, `nequi`, `breb` con `label` y `hint`), entrada en `SECTION_REGISTRY`, `SECTION_VIEWS`,
  `SECTION_DEFAULTS` y `PAYMENT_METHOD_CODES`; `router.py` gana el par tipado
  `GET`/`PATCH /settings/payment_methods` **antes** de las genéricas `/settings/{section}`.
- Lo rompe: `tests/settings/_apoyo.NO_HABILITADAS = ("tv", "hours", "channels", "classes",
  "payment_methods")`, parametrizada en `test_settings_router.py:117` (404
  `section_not_available`) y `test_settings_rules.py:89`: quitar `payment_methods` en el Rojo de
  S3-B3. `tests/migrations/test_0005_settings.py` solo comprueba el `CHECK` de ocho claves: no
  cambia.
- Front: `ConfigPage.tsx` tiene tres pestañas y `ConfigPage.test.tsx:77-83` afirma exactamente
  `["Gimnasio", "Privacidad", "Membresías"]`: S3-F4 agrega "Medios de pago" y actualiza la prueba.

### `api/src/app/modules/audit/*`

- Sin cambios de código: `reveal` lo escribe `members.service` con `core.audit.record` (US-074,
  consolidación) y no hay suscriptor de `SensitiveFieldRevealed` en `audit.service` (la prueba
  "exactamente una fila" lo protege). `test_audit_module.py::test_audit_tiene_router_vacio_y_no_tiene_models`
  sigue válida.

### `api/migrations/versions/0008` a `0011` y `tests/core/test_migrations.py`

- `test_downgrade_a_base_vacia_y_vuelta_a_head` baja hasta `base` y vuelve en cada corrida:
  cada `downgrade` nuevo debe dejar limpio (`0011` quita los dos triggers y las dos funciones,
  `0010` y `0009` sus tablas e índices, `0008` el `EXCLUDE` y la tabla); `0001` hace `DROP SCHEMA
  ... RESTRICT`, así que una tabla que un `downgrade` olvide tumba la prueba. `test_single_head`
  exige una sola cabeza: si algún slice se trabaja en un worktree paralelo, correr `uv run
  alembic heads` en el ciclo de Alembic del gate.
- El `api` de desarrollo monta `../api/migrations` por bind y corre `upgrade head` en cada
  reinicio de `--reload`: un `0008_*.py` a medio escribir se aplica (o rompe el arranque) en
  `apex-db-1`. Redactar y probar cada migración contra `db_test` (`pytest
  tests/core/test_migrations.py`) antes de guardarla en `migrations/versions`, o parar `api`
  mientras se escribe (misma mitigación que el Sprint 2).

### `web/src/features/{members,memberships,payments,system}` y reglas del front

- `web/tests/lint/boundaries.test.ts`: **ninguna feature importa de otra feature** (sin lista
  blanca). El plan cruza features en cuatro puntos: `features/members/components/MemberPaymentsTab.tsx`
  abre `RegisterPaymentPanel` de `features/payments` (US-101 T7); la pestaña Membresías de la
  ficha vive en `features/memberships` pero se monta en `MemberDetailPage` de `features/members`
  (S3-F7); `MemberStatusChips` usa `usePlans` de `features/plans/api.ts` (US-071 T10);
  `SellPage` (`features/memberships`) usa la búsqueda de socios de `features/members/api.ts` y
  los planes de `features/plans` (US-084 T14); `RegisterPaymentPanel` usa `GET /members?q=` y
  `GET /members/{id}/memberships` (US-095 T14). Resolverlo antes de S3-F1: mover los hooks
  compartidos (`useMembers`, `usePlans`, `usePaymentMethods`, `useMemberMemberships`) a
  `core/api/` o `shared/`, componer las pestañas de la ficha por ruta (`routes.tsx`/`routeTable`
  con `Outlet`) o ampliar la regla con una lista blanca explícita en el mismo slice que la use.
- `web/src/config/routeTable.ts`: `/socios/:id`, `/socios/:id/editar`, `/membresias`,
  `/membresias/vender`, `/pagos` existen sin `load`; `ENABLED_FEATURES` no incluye
  `memberships` ni `payments`. `web/src/routes.test.ts:60-74` afirma la lista literal de rutas
  con `load` y `:78-87` que `/socios/:id` no se registra; `web/src/layouts/nav.test.ts:14` fija
  las cinco etiquetas del menú del Sprint 2 (`nav.ts` ya trae "Membresías" y "Pagos" por
  feature). Las tres pruebas cambian en S3-F1 (ficha) y S3-F3/F5/F6 (features nuevas).
  `routes.reference.ts` ya contiene las cinco rutas: el oráculo no cambia.
- `web/src/shared/ui/MaskedValue.tsx` ya acepta `onReveal: () => Promise<string>` y
  `tests/lint/no-reveal-cache.test.ts` prohíbe que importe TanStack Query o almacenamiento: la
  mutación `useRevealField` (US-074 T7, `gcTime: 0`, sin `setQueryData`) vive en la feature y
  solo le pasa la función. `web/tests/kit-inventory.test.ts` exige `<Nombre>.test.tsx` por
  componente del kit: `MaskedValue.reveal.test.tsx` es adicional, no sustituye a `MaskedValue.test.tsx`.
- `web/src/features/members/schemas.ts`: `memberRowSchema` es `.strict()` con
  `membership_status` y `plan_name` ya declarados; `memberDetailSchema` solo valida `id`,
  nombres y `warnings` (S3-F1 lo amplía a la ficha completa). `web/src/test/members.tsx` trae las
  dos columnas en `null`.
- `web/src/core/api/types.ts` se regenera con `npm run gen:api` tras cada slice de backend (CI,
  paso M3) y `errorCodes.ts` recibe los códigos nuevos (`membership_conflict`,
  `membership_overlap`, `membership_cancelled`, `payment_already_voided`,
  `start_date_too_retroactive`, `member_deactivated`, `member_already_deactivated`,
  `member_not_deactivated`, `overlaps_future_membership`, `freeze_*`).
- `ENABLED_FEATURES` con `memberships` y `payments` muestra las entradas del menú: los E2E
  `layouts.spec.ts` (solo revisa el portal) y `panel-layout.spec.ts` no cuentan entradas del
  panel; `settings-config.spec.ts` sí nombra pestañas de Configuración (revisarlo en S3-F4).

### Archivos que el sprint no debe tocar

`core/crypto/*` (la puerta `types.reveal` y `bus.batch` ya cubren la ficha y el reveal),
`core/db.py`, `core/context.py`, `core/errors.py` (los códigos nuevos son subclases de
`DomainError`), `core/pagination.py`, `core/events.py`, `core/audit.py` (`AuditAction` ya
incluye `reveal`), migraciones `0001` a `0007`, `tests/core/_principal_double.py`,
`infra/nginx/*`.

## 2. Capa de datos

### Lo que existe (aplicado en `apex-db-1` y `apex-db_test-1`, sin datos reales)

- `0001_core_schemas`: nueve esquemas (incluidos `memberships` y `payments`) y
  `CREATE EXTENSION IF NOT EXISTS btree_gist` (`versions/0001_core_schemas.py:41`): el `EXCLUDE
  USING gist` de `0008` tiene su extensión. `0008` a `0011` solo crean tablas, restricciones y
  triggers.
- Cadena lineal `0001 → 0002 → 0003 → 0004 → 0005_settings → 0005b_auth_security →
  0006_members → 0007_plans` (head). `alembic current` en `apex-api-1`: `0007_plans (head)`.
- `audit.forbid_mutation()` (`0002`) y los triggers de `crypto_ops` (`0003`) son el molde del
  trigger de pagos; `core/audit.py` ya documenta `__audit_subject__ = "member_id"` para
  `memberships` y `payments`.

### Lo que agrega el sprint

- `0008_memberships` (S3-B1): `memberships.memberships` con los CHECK de US-084 T1, `EXCLUDE
  USING gist` sobre `(member_id, daterange(start_date, end_date, '[]')) WHERE status <>
  'cancelled'`, índices `(status, end_date)` y `(member_id, status, start_date)`; sin FK a
  `members` ni `plans` (la integridad la valida el service con `get_ref` y `get(for_share=True)`).
  `down_revision = 0007_plans`.
- `0009_membership_freezes` (S3-B2): `frozen_from`, `frozen_to`, `days`, `membership_id` (FK
  interna del mismo esquema), columnas comunes; auditada.
- `0010_payments` (S3-B3): `payments.payments` con `member_id NOT NULL` copiado, `amount_cop
  BIGINT CHECK > 0`, `method` en `('cash','nequi','breb')`, `CHECK payments_void_coherent`, tres
  índices. `amount_cop` como `BIGINT` en la base y `int` en Python (regla de datos 1).
- `0011_payments_immutability` (S3-B4, tras `pg_dump -Fc` a `docs/scratch/sprint-03-antes-0011.dump`):
  `BEFORE UPDATE OR DELETE ... FOR EACH ROW` que solo deja pasar `voided false → true` con las
  cuatro columnas llenas y ninguna otra columna cambiada, más `BEFORE TRUNCATE`. Riesgo del
  mixin: `updated_at` lo toca `onupdate=func.now()` del `CommonColumnsMixin` en la anulación; el
  trigger debe dejar libre `updated_at` (US-096 T1 lo dice) o el `void` legítimo falla.
- Rollback: cada migración baja sola (sección 1); el volcado previo a `0011` es la red de
  seguridad de la base de desarrollo, y se borra al cerrar el sprint como en el Sprint 2.

### Riesgos de orden y de la suite

- Orden de slices igual a la cadena (B1 → B2 → B3 → B4): sin riesgo de dos cabezas si el backend
  va en serie; `alembic heads` en el gate si hay worktrees.
- Limpieza de `db_test` entre sesiones y en `dos_sesiones` (sección 1, `payments`): sin el
  `DISABLE TRIGGER USER` las pruebas con commit real de pagos dejan filas que la sesión siguiente
  no puede borrar y `0011` convierte la limpieza en error.
- `EXCLUDE` frente a Q1 y congelaciones (riesgo 3 del plan): `freeze` extiende `end_date` y puede
  solapar la futura; el service responde 409 `overlaps_future_membership` antes del `UPDATE`, y
  si no, el `EXCLUDE` lo rechaza con `23P01` (traducido por `violated_constraint`). Pruebas con
  vigente más futura, congelada y extendida, y cancelada (que el `WHERE status <> 'cancelled'`
  deja fuera del `EXCLUDE`).

## 3. Servicios Docker y estrategia de rebuild

- Estado: `apex-db-1` healthy (`127.0.0.1:5442`), `apex-db_test-1` healthy (`127.0.0.1:5443`,
  12 h arriba), `apex-api-1` healthy (`127.0.0.1:8181`, bind de `src` y `migrations` con
  `--reload`), `apex-web-1` healthy (`0.0.0.0:8180`). Imágenes `apex-api:local` y
  `apex-web:local` construidas el 2026-10-22 10:29 (-05); HEAD `d65056e` es de las 10:59 y los
  commits posteriores a las 10:29 solo tocan `docs/` y `web/src/core/auth/passwordPolicy.test.ts`
  (una prueba): las imágenes corresponden al código de HEAD.
- `api`: cambios en `src/` y `migrations/` se ven sin rebuild (bind); solo `pyproject.toml`/
  `uv.lock` (el sprint no prevé dependencias nuevas: `btree_gist` y `daterange` son de PostgreSQL,
  `zoneinfo` es de la biblioteca estándar con `tzdata` ya instalada) o `alembic.ini` exigen
  `build api`. Verificar `docker compose logs --tail 20 api` tras cada migración (el `lifespan`
  la aplica al reiniciar) y `exec api alembic current` al cerrar B1, B2, B3 y B4.
- `tools` (`entrypoint python -m app.cli`, sin bind de `src`): el sprint no cambia `cli.py`
  (`_load_module_services` ya existe), pero si la demo necesita `seed` o `export-openapi` desde el
  contenedor con código nuevo hace falta `build api` primero. El OpenAPI se exporta desde el host
  (`cd api && uv run python -m app.cli export-openapi ../docs/openapi.json`).
- `web`: sin bind; cada slice F1 a F7 que se quiera ver en `:8180` y los E2E del proyecto `stack`
  (`sell-with-payment.spec.ts`, `members-mobile.spec.ts`) exigen `build web && up -d web`.
  `infra/nginx/*` no cambia en este sprint (ya pone `no-store` en `/api/`), así que no hay
  `test_nginx_conf.sh` ni `headers.sh` que repetir salvo al cerrar.
- Imágenes base por digest (`Dockerfile`, Compose, `test_nginx_conf.sh`), diferido 9.3 "primer
  slice de infra del Sprint 3, a más tardar S4B-W0-2": `SPRINT-03.md` declara "no hay
  infraestructura nueva" en la Wave 0. No bloquea; el plan decide si entra aquí o queda en S4B-W0-2
  y lo anota en `DECISIONES.md`. Lo mismo con las dependencias de desarrollo del front con
  hallazgos de `npm audit` (vitest, tinypool, stylelint; "front, Sprint 3" en 9.3): no están en
  ningún slice de `SPRINT-03.md`.

## 4. Contratos API

### Estado de `docs/openapi.json` en HEAD

31 operaciones (auth 7, users 9, settings 8, members 2, plans 3, health 2); 44 esquemas.
`MemberRowOut` ya publica `membership_status` y `plan_name` como `string | null` opcionales y
`MemberDetailOut.membership_status` igual: los valores reales del Sprint 3 son aditivos para el
front (`memberRowSchema` los acepta; `StatusTag` ya pinta los siete estados de `statusLabel.ts`,
incluido `pending_payment` con tono `warning` por Q3).

### Los 22 endpoints nuevos frente a las pruebas que vigilan el contrato

- Orden de declaración: `/memberships/summary` antes de `/memberships/{id}`;
  `/payments/summary` y `/payments/methods` antes de `/payments/{id}`;
  `/members/{id}/memberships/renewal-preview` antes de cualquier `/{membership_id}`;
  `/settings/payment_methods` antes de `/settings/{section}`. Routers planos (S2-D3).
- Listas `Page_*`: `GET /memberships` (`status` múltiple, `q`, `plan_id`, `ends_from`,
  `ends_to`, `member_id`), `GET /payments` (`q`, `from`, `to`, `method`, `registered_by`,
  `voided`, `member_id`, `membership_id`), `GET /members/{id}/memberships`, `GET
  /members/{id}/payments`: las cuatro con `PageParams` y `q` (sección 1).
- `GET /payments/methods`: objeto con `items`, no arreglo.
- `GET /members` gana `membership_status` (`active`, `expiring`, `expired`, `frozen`,
  `pending_payment`, `none`) y `plan_id`; sigue con `status` (alias de `member_status`), `q`,
  `sort`, `PageParams` y su límite `members-search` solo con `q`.
- Roles: solo admin en `DELETE /members/{id}`, `POST /members/{id}/reactivate`, `POST
  /memberships/{id}/cancel`, `POST /payments/{id}/void`, `GET`/`PATCH /settings/payment_methods`;
  el resto admin y coach. Coincide con `permissions.ts` del front (`members.delete`,
  `members.reactivate`, `memberships.cancel`, `payments.void` en `ADMIN`; `members.reveal`,
  `memberships.sell`, `memberships.freeze`, `payments.register` en `STAFF`).
- Cada slice de backend que publica rutas regenera `docs/openapi.json` y `web/src/core/api/
  types.ts` (pasos `openapi al día` y `tipos del api al día` de CI fallan si no).

### Contradicciones entre desgloses y código que el plan cierra en T-DOC

- `members.service.ref` → `get_ref` (lanza, no devuelve `None`; `is_deleted`).
- `members.service.active_ids()` → no existe (agregar o sustituir).
- `bus.op_context(...)` → `core.crypto.types.reveal(obj, field, purpose)` dentro de
  `bus.batch("decrypt", None)`.
- `audit.record(table_name="members")` → `"members.members"`.
- `Depends(get_session)`, `Depends(get_clock)` → `SessionDep` y `current_clock()`.
- `Pagination` → `PageParams`; `search_ids` devuelve `set[UUID]`.
- `GET /payments/methods` como arreglo → objeto con `items`.
- `member.document.change` → `members.document.update`.
- `test_service_import_cycles.py`, `test_payments_does_not_import_memberships.py`,
  `test_payments_dependencies.py` → viven en `test_service_import_graph.py`.
- `MemberNotFound` duplicado en `memberships/exceptions.py` → reutilizar el de `members`.
- US-074 T4 "commit explícito en el router" → lo da `SessionDep` (N-1).

## 5. Línea base en HEAD `d65056e`

- `git log --oneline -3`: `d65056e docs(sprint-02): cierre del sprint...`, `b6650b5
  docs(sprint-02): evidencia de la revalidación final`, `2e393cd chore(sprint-02): integración
  tras la revisión de Fase 4...`. `git status` limpio; `git worktree list` solo el principal.
- api (cierre del Sprint 2, `docs/scratch/sprint-02.md`, bloque de cierre): `pytest -m "not perf"`
  **1.987 ok, 4 saltadas, 3 deseleccionadas**, cobertura de `app` **95,70 %** (`cli.py` y
  `worker/` en `omit` hasta US-113). Saltadas: `test_reveal_no_deja_el_valor_revelado_en_los_logs`
  (S3-B10) y tres de modo POSIX que NTFS no conserva.
- web (V9 sobre el árbol fusionado): **1.763 pruebas en 110 archivos, cobertura 99,68 % de
  líneas**, `npm run build` en verde (main 463,25 kB, 142,49 kB gzip).
- Stack (`docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml ps`): los
  cuatro contenedores healthy; `exec api alembic current` = `0007_plans (head)`.
- `.env` local (solo nombres): `WEB_PORT=8180`, `API_PORT=8181`, `DB_PORT=5442`,
  `DB_TEST_PORT=5443`, `ENV=dev`, `TRUSTED_PROXIES=172.30.0.10/32`,
  `FRONT_BASE_URL=http://localhost:8180`, `AUTH_ALLOWED_ORIGINS=http://localhost:8180,http://localhost:5173`,
  `COOKIE_SECURE=false`, `TEST_DATABASE_URL` hacia `127.0.0.1:5443/apex_test`. `.env` y
  `.env.seed` no están versionados.
- No se corrieron las suites en esta fase (instrucción de la Fase 0).

## 6. Bugs y desajustes de configuración visibles

1. `.env.seed` sigue en el disco del desarrollador después del primer `seed` (CLAUDE.md: "se
   borra tras el primer seed"). No afecta al sprint (solo lo lee `tools`); borrarlo o anotarlo.
2. `compose.dev.yml`: `--reload` con bind de `migrations/` aplica migraciones a medio escribir en
   `apex-db-1` (sección 2). Es el mismo comportamiento del Sprint 2, documentado, no un bug nuevo.
3. `api/pyproject.toml`: `[tool.coverage.run] omit` de `cli.py` y `worker/*` se mantiene hasta
   US-113 (Sprint 4A); `run-gates.sh` y el job `api` corren `-m "not perf"`, y `SPRINT-03.md`
   habla de pruebas `-m slow` (US-091 T8, US-098 T7): **el marcador registrado en `pyproject.toml`
   es `perf`, no `slow`** (`--strict-markers` haría fallar la colección con `@pytest.mark.slow`).
   Usar `perf` o registrar `slow` en el primer slice que lo use.
4. `alembic.ini` con rutas relativas a `api/`: sin cambio; `alembic` a mano se corre desde `api/`.
5. `.env.example`: coherente tras S2-W0-1; ninguna variable nueva en este sprint, así que
   `test_env_example.py` no exige cambios.
6. `ci.yml`: el job `e2e-stack` corre `npm run e2e:stack` sobre `web/tests/e2e/stack/**`; los dos
   E2E del sprint (`sell-with-payment.spec.ts`, `members-mobile.spec.ts`) deben vivir ahí (o en
   `tests/e2e/` como proyecto `preview` con MSW) según cómo se nombren en el plan, o CI no los
   verá.

## 7. Riesgos del plan ampliados con lo visto en el código

1. [HIGH] Nudo de dependencias (bus, puerto G-03, handler de cobertura, trigger): confirmado. Lo
   agrava que `tests/conftest.py` carga los services al importarse: desde S3-B4 todo el suite
   corre con el gate y los dos handlers reales; los dobles tienen que ser fixtures con
   restauración. Mitigación del plan (slices pequeños, `test_service_import_graph.py` en cada
   gate, `run-gates.sh` al cerrar cada slice) más las condiciones 1 y 2.
2. [HIGH] Trigger de `0011`: una columna olvidada en la lista `IS DISTINCT FROM` o `updated_at`
   bloqueado rompe la anulación legítima; la limpieza de `db_test` necesita `DISABLE TRIGGER
   USER`. Mitigación: prueba por columna permitida y prohibida, doble anulación, `DELETE`,
   `TRUNCATE`, comparación con `information_schema.columns` (US-096 T4) y volcado previo.
3. [HIGH] `EXCLUDE` y Q1 con renovación anticipada y congelación que extiende el fin: pruebas con
   vigente más futura, congelada y extendida, cancelada; 409 en código antes del `UPDATE`.
4. [MEDIUM] Carrera vender frente a baja de plan: `get(for_share=True)` ya emite `FOR SHARE`
   real (S2-B9); US-082 cierra el caso en 4A.
5. [MEDIUM] Doble del gate que oculta un error real: `test_router_register.py` contra el gate
   real y `test_gates_registered.py` en S3-B4.
6. [MEDIUM] Tamaño de archivos: `members/service.py` (523 líneas) y el futuro
   `memberships/service.py` superan las 800 líneas de `test_file_and_function_size.py` si no se
   parten desde el principio; partir después de escribir cuesta un slice.
7. [MEDIUM] Fronteras del front: cuatro cruces feature → feature previstos por los desgloses
   chocan con `boundaries.test.ts`; decidir el mecanismo antes de S3-F1 evita rehacer
   componentes.
8. [LOW] `crypto_ops`: cada apertura de ficha agrega cinco filas `decrypt` (`mask`) agregadas en
   un lote, y cada `reveal` una más; aceptado por N-01, tener en cuenta en la retención.
9. [LOW] `MembershipFreeze` sin `member_id`: sus filas de auditoría no llevan
   `subject_member_id`; el historial por socio (US-106) tendrá que resolverlo por `membership_id`.
10. [LOW] `summary()` de membresías cuenta socios vivos por estado resuelto (N-26) y necesita los
    ids vivos de `members` (contrato ausente): decidir entre `active_ids()` nuevo o `count` más
    `member_ids_by_status`.

## 8. Condiciones para VERDE

Se incorporan al plan de la Fase 1; el plan-critic las verifica.

1. S3-B1 (Rojo) actualiza las pruebas de arquitectura que fijan el estado del Sprint 2:
   `test_audit_module.py` (tupla `MODULES` con `memberships` y `payments`),
   `test_service_import_graph.py` (`ALLOWED_EDGES` con `memberships → members/plans/settings/
   payments` y `payments → settings/members/auth`; quitar `test_plans_no_agrega_aristas` o
   reescribirla como "solo memberships importa plans"), `test_audited_tables.py`
   (`memberships.memberships`, `memberships.membership_freezes` y `payments.payments` en
   `REQUIRED_AUDITED_TABLES_V01` en el slice que las crea), y `migrations/env.py` con los
   `models` nuevos. S3-B9 quita la aserción `frozenset() == LAZY_IMPORT_WHITELIST` y agrega
   `("members", "memberships")`.
2. Todo router nuevo lleva `dependencies=[Depends(no_store)]`, `responses_for(401, 403)` en el
   router y los 404/409/422 por ruta, `SessionDep` como única sesión y `current_clock()` en el
   service (nunca `Depends(get_session)`, `Depends(get_clock)`, `date.today()`); 429 solo en
   rutas con límite y registradas en `CON_LIMITE` de `test_error_codes_per_route.py`. S3-B9
   decide si el 429 del router de `members` baja a `POST`/`GET /members` o si `reveal` y las
   demás rutas nuevas reciben límite por usuario y entran en `CON_LIMITE`.
3. Contratos que chocan con pruebas existentes se fijan antes de codificar: `GET /payments/methods`
   responde un objeto (`{ items: [...] }`), `GET /members/{id}/memberships` y `GET
   /members/{id}/payments` aceptan `q: SearchQuery`, y el marcador de rendimiento es `perf`
   (no `slow`) o se registra `slow` en `pyproject.toml`.
4. T-DOC corrige en los desgloses los nombres que no son los del código (sección 4):
   `get_ref`, `is_deleted`, `types.reveal` + `bus.batch` en lugar de `bus.op_context`,
   `table_name="members.members"`, `PageParams`, `set[UUID]` de `search_ids`,
   `members.document.update`, `SessionDep`, pruebas consolidadas en
   `test_service_import_graph.py`, y decide `members.service.active_ids()` (nuevo en S3-B7) o su
   sustituto para `summary()`.
5. `tests/conftest.py` amplía `LIMPIEZA_DE_SESION` y la limpieza de `dos_sesiones` con
   `memberships.membership_freezes`, `memberships.memberships` y `payments.payments` (esta con
   `DISABLE/ENABLE TRIGGER USER` y `to_regclass`) en S3-B1 y S3-B3; `tests/payments/conftest.py`
   registra el doble del gate como fixture que restaura el real; `tests/factories/` gana
   `make_membership` y `make_payment`; `test_no_physical_delete.py` escanea solo `src/`.
6. `memberships/service.py` y `members/service.py` se parten en archivos privados del módulo
   desde el slice que los hace crecer (S3-B1 y S3-B9), con `service.py` como fachada y los
   nombres en `_imports.PRIVATE_HELPERS`, para no superar 800 líneas por archivo ni 50 por
   función (`test_file_and_function_size.py`).
7. S3-B3 quita `payment_methods` de `tests/settings/_apoyo.NO_HABILITADAS`; S3-F4 actualiza la
   lista de pestañas de `ConfigPage.test.tsx`; S3-F1 y S3-F3/F5/F6 actualizan
   `web/src/routes.test.ts` (rutas con `load`, `/socios/:id` registrada) y
   `web/src/layouts/nav.test.ts` (etiquetas del menú) al habilitar `memberships` y `payments`
   en `ENABLED_FEATURES`.
8. Antes de S3-F1 el plan fija cómo se componen las pantallas sin que una feature importe de
   otra (`boundaries.test.ts`): hooks compartidos en `core/api/` o `shared/`, composición por
   ruta, o lista blanca explícita en la prueba, en el mismo slice que la necesite.
9. Cada slice de backend que publica rutas termina con `export-openapi` y `npm run gen:api`; cada
   migración se prueba primero contra `db_test` (`test_migrations.py`) y después se deja en
   `migrations/versions`; el gate de B1 a B4 incluye `alembic heads` (una cabeza) y el ciclo
   `upgrade head → downgrade -1 → upgrade head` en `apex-db-1`; `pg_dump` antes de `0011`.
10. `build web && up -d web` antes de cualquier E2E o demo contra `:8180` tras cada slice de
    front; `build api` solo si cambian `pyproject.toml`/`uv.lock` o si la demo usa `tools` con
    código nuevo. El plan decide, y anota en `DECISIONES.md`, si las imágenes por digest y la
    actualización de dependencias de desarrollo del front (diferidos 9.3 del Sprint 2) entran
    en este sprint o pasan a S4B-W0-2.

## Riesgos residuales (no bloquean)

- `--reload` con polling puede reiniciar el api a mitad de un E2E del proyecto `stack`; no
  editar `src/` durante la corrida.
- Las tres pruebas saltadas por NTFS se verifican en el job `api` de CI (Linux), como en el
  Sprint 2.
- `apex-api:ci` del 2026-10-21 en el host es una imagen vieja sin uso local; no interfiere.
- `GET /members` con `membership_status` resuelve el conjunto de ids por `memberships` y filtra
  `id = ANY(:ids)`: con 1.000 socios es aceptable (volumen de `01_product_discovery.md`); medir
  junto con `test_list_perf.py`.
