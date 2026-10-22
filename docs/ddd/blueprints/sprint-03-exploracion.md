# Exploración Sprint 3 (Fase 1 de /flow-update)

Rama `feat/sprint-03-membresias-pagos`, HEAD `d65056e` (igual a `main`), árbol limpio. Solo lectura: no se corrió pytest ni vitest (línea base del cierre del Sprint 2 en `docs/scratch/sprint-02-revision-backend.md`: 1987 pruebas ok, 4 omitidas, cobertura 96 %, ruff y mypy limpios). Se consultó la base viva sin modificarla: `alembic current` da `0007_plans (head)`, `btree_gist` instalada, esquemas `memberships`, `payments` y `worker` creados por `0001`, `pg_trgm` ausente. Rutas relativas a la raíz; `core/` = `api/src/app/core/`, `mod/` = `api/src/app/modules/`.

## 0. Resumen ejecutivo

El Sprint 2 dejó casi todos los contratos que el Sprint 3 consume. Cuatro no coinciden con el plan: `members.service.ref` se llama `get_ref` y lanza en vez de devolver `None`; `members.service.active_ids` no existe; `bus.op_context` no existe; `settings.service.payment_methods` no existe (se crea). Lo demás (`memberships_policy`, `plans.get(for_share)`, `names_for` de members, plans y auth, `search_ids`, `mask`, `reveal`, `audit.record`, `SessionDep`, `violated_constraint`, `responses_for`, `no_store`, `paginate`) está y tiene la firma que el plan espera o una muy cercana.

Lo que cambia el diseño o rompe gates (detalle en 4 y 5):

1. **Los estados `expiring`, `expired` y el regreso de `frozen` a `active` no los mueve nadie en el Sprint 3.** US-091 y US-092 leen la columna `status` guardada y US-094 (el job que la recalcula) está fuera del sprint. Congelar se entrega sin descongelar.
2. **`test_service_import_graph.py` falla en el primer slice (S3-B1), no en S3-B4.** Cuenta los imports perezosos como aristas del ciclo, y `memberships` ya importa `members`, `plans` y `settings` en B1. Hay que reescribir el control de ciclos (solo aristas de nivel de módulo) y ampliar `ALLOWED_EDGES` y `LAZY_IMPORT_WHITELIST` desde B1.
3. **`members/service.py` pasa de 800 líneas** con US-071, 073, 074, 075 y 076 (hoy 523). `test_file_and_function_size` lo bloquea: hay que partirlo en privados como `auth` (S2-R10) y registrar los privados en `PRIVATE_HELPERS`.
4. **Orden de candados socio y cadena de auditoría.** `sell` toma `pg_advisory_xact_lock(member)` y luego el flush audita (candado de la cadena). `register` hace flush del pago (candado de la cadena) y después el handler de activación quiere el candado del socio: orden inverso, interbloqueo posible.
5. **`GET /payments/methods` como arreglo suelto lo rechaza `test_list_routes_use_page_params`**, y los `GET .../{id}/memberships` y `.../payments` paginados exigen un parámetro `q`.
6. **Pruebas fuera del gate de cada slice que se rompen en silencio:** `tests/migrations/test_0007_plans.py:165` (exige que `0007` sea head), `tests/architecture/test_audit_module.py:45` (tupla exacta de `MODULES`), `tests/settings/_apoyo.py:66` (`payment_methods` en `NO_HABILITADAS`), `web/src/config/features.test.ts:11` (conjunto exacto de features).
7. **`-m slow`** del plan no existe: el marcador registrado es `perf` y `--strict-markers` falla la colección con `slow`.

## 1. Mapa de integración

### 1.1 Backend: lo que el sprint consume

| Punto | Archivo:línea | Firma real | Quién lo usa |
|---|---|---|---|
| Política de membresías | `mod/settings/service.py:191` | `async memberships_policy(session) -> MembershipsPolicy` (`expiring_days`, `max_freeze_days_per_membership`, `max_freezes_per_membership`, `max_retroactive_days`; dataclass en `mod/settings/schemas.py:121`) | memberships: `sell`, `freeze`, estado efectivo por lote |
| Sección por clave | `mod/settings/service.py:125, 152, 185` | `get_section(session, key: str) -> SectionOut`; `update_section(session, key, value, version, by)`; `get(session, key: SectionKey)` | La sección `payment_methods` entra por el mismo registro |
| Registro de secciones | `mod/settings/schemas.py:35, 47, 131, 139, 146` | `SectionKey.payment_methods` ya existe en el enum; faltan `ENABLED_SECTIONS`, `SECTION_REGISTRY`, `SECTION_VIEWS`, `SECTION_DEFAULTS`, `PaymentMethodsSettings` (`extra="forbid"`, claves `cash`, `nequi`, `breb`) y las salidas y entradas tipadas | US-056 |
| Rutas tipadas de settings | `mod/settings/router.py:45-88` (tipadas), `94-105` (genéricas) | La tipada `payment_methods` se declara antes de `/settings/{section}` | US-056 |
| Socio por referencia | `mod/members/service.py:290` | `async get_ref(session, member_id) -> MemberRef` (lanza `MemberNotFound`; incluye dados de baja). `MemberRef` en `mod/members/schemas.py:101`: `id, first_name, last_name, status, is_deleted` | sell, list_for_member, gate |
| Existencia | `mod/members/service.py:307` | `async ensure_exists(session, member_id, *, include_deleted=False) -> None` | listas por socio (US-093, US-101) |
| Búsqueda | `mod/members/service.py:501` | `async search_ids(session, q, *, include_deleted=False) -> set[UUID]` | memberships.list, payments.list |
| Nombres | `mod/members/service.py:510` | `async names_for(session, ids) -> dict[UUID, MemberName]` (`first_name, last_name, sex`) | memberships.list, payments.list |
| Máscara | `mod/members/service.py:185` | `mask(field, value, *, document_type=None) -> str or None`. Acepta `date` para `birth_date` y mapeo para `emergency_contact` | ficha (US-073) |
| Alta y lista | `mod/members/service.py:273, 476` | `create(session, data)`; `list(session, filters: MemberListQuery, page)` (el nombre `list` sombrea el builtin: usar `builtins.list`) | S3-B9 la amplía |
| Fila de lista y detalle | `mod/members/schemas.py:111, 79` | `MemberRowOut` ya trae `membership_status` y `plan_name` (siempre `None`); `MemberDetailOut` trae `membership_status: str or None` pero no `plan_name` | S3-B9, B10 |
| Filtros de lista | `mod/members/schemas.py:124`, `mod/members/router.py:83` | `MemberListQuery(q, status, sort)` con `extra="forbid", frozen=True` | S3-B9 agrega `membership_status`, `plan_id` |
| Plan vigente | `mod/plans/service.py:259` | `async get(session, plan_id, *, for_share=False) -> PlanSnapshot` (`FOR SHARE` real, línea 263; lanza `PlanNotFound` 404 si no existe o está dado de baja) | sell |
| Plan con bajas | `mod/plans/service.py:270` | `get_including_deleted(session, plan_id)` | detalle de membresías antiguas |
| Nombres de plan | `mod/plans/service.py:279` | `names_for(session, plan_ids) -> dict[UUID, str]` (una consulta, incluye bajas) | lista, status_for |
| Snapshot de plan | `mod/plans/schemas.py:63` | `PlanSnapshot(id, name, price_cop, kind, duration_days, class_count, is_active, deleted_at)` | sell |
| Nombres de usuario | `mod/auth/users.py:142` (reexportada en `mod/auth/service.py:62`) | `async names_for(session, user_ids: Sequence[UUID]) -> dict[UUID, str]` (devuelve el correo: `auth.users` no tiene nombre hasta US-110). **Sí existe.** | payments (registrado por, anulado por), cancelación |
| Bus de eventos | `core/events.py:56, 72` | `subscribe(Tipo, handler)` idempotente; `emit(event, session)` con el mismo `session`, tipo exacto, profundidad 5; propaga excepciones | `PaymentRegistered`, `PaymentVoided`, `MembershipSold`, `MembershipFrozen`, `SensitiveFieldRevealed` |
| Eventos: dónde viven | `docs/ddd/DECISIONES.md`, decisión L7 | Se definen en el `service.py` de quien emite; los suscriptores importan de ahí | `payments.service` define `PaymentRegistered` y `PaymentVoided`; `memberships.service` los suscribe |
| Auditoría explícita | `core/audit.py:312` | `async record(session, *, action, table_name, record_id, before, after, user_id=None, subject_member_id=None)`; `reveal` es acción válida | reveal (US-074) |
| Hook ORM | `core/audit.py:341-502` | `__audited__`, `__audit_subject__` (atributo con el socio), `__audit_redact__`, `__audit_exclude__`; el nombre de tabla que graba es `esquema.tabla` (`members.members`) | Membership (`member_id`), Payment (`member_id`), MembershipFreeze |
| Cifrado: lectura | `core/crypto/types.py:224` | `reveal(obj, field, purpose) -> str or date or dict or None`, sincrónica; exige el atributo cargado y sellado; llama a `bus.decrypt(..., purpose=, record_id=obj.id)` | ficha (`mask`) y `reveal` |
| Bus: descifrar | `core/crypto/bus.py:75` | `decrypt(blob, aad, *, purpose=None, record_id=None) -> bytes` | indirecto |
| Propósitos válidos | `core/crypto/models.py:65` | `OP_PURPOSES = ("mask", "reveal", "notify", "auth_link", "export")` | ficha y reveal |
| Lotes de `crypto_ops` | `core/crypto/oplog.py:134` (`batch`), `104` (`aggregate_ops`) | `with bus.batch("decrypt", None)`; en un lote la fila agregada pierde el `record_id` | decisión sobre `mask` (riesgo 12) |
| Sesión | `core/db.py:180, 161, 80, 106, 46` | `SessionDep` (`scope="function"`); `violated_constraint(error) -> str or None`; `CommonColumnsMixin` (con `eager_defaults`); `SoftDeleteMixin`; `APP_SCHEMAS` ya incluye `memberships` y `payments` | todos |
| Paginación | `core/pagination.py:43, 50, 59, 89, 99` | `PageParams` (limit 1..200, offset 0..1.000.000), `Page[T]`, `SearchQuery`, `paginate(session, stmt, params)` (pagina la primera entidad con `.scalars()`; no sirve para filas de varias columnas), `to_page` | todas las listas |
| No-store | `core/http.py:21` | `no_store`, dependencia de router | los routers nuevos |
| Errores por ruta | `core/errors.py:151` | `responses_for(*codes)`; códigos válidos 400, 401, 403, 404, 409, 422, 429 | todos |
| Reloj | `core/clock.py:25, 28, 49, 78, 82` | `BOGOTA`, `to_bogota_date(instant)`, `FrozenClock`, `current_clock()`, `set_clock`. **No hay función de módulo `today_bogota()`**: es el método `current_clock().today_bogota()`, y el reloj expone `now_utc()`, no `now()` | sell, summary, pagos del mes |
| Actor | `core/context.py:53, 62` | `get_actor()`, `actor_scope(user_id)`; `current_user` lo fija. Los services de socios y planes no reciben `by` | hook de auditoría |
| Principal | `core/security.py:395, 452, 473, 501` | `Principal(user_id, role, member_id, ...)`; `require_role(*roles)`; el id es `principal.user_id` (el plan escribe `current_user.id`) | routers |
| Módulos | `main.py:50, 72, 78` | `MODULES = ("auth", "settings", "audit", "members", "plans")`; `load_module_services()` importa `service.py` de cada uno; `include_module_routers` monta `mod.router` plano | agregar `memberships`, `payments` |
| CLI | `cli.py:237, 260` | `_load_module_services()` dentro de `cli_runtime`; usa `MODULES` | sin cambios si `MODULES` crece |

### 1.2 Backend: lo que el sprint crea y dónde engancha

- `main.py:50`: `MODULES` pasa a `("auth", "settings", "audit", "members", "plans", "memberships", "payments")`. Cada módulo necesita `models.py` y `router.py` (los recorren `test_audited_tables`, `test_no_store_routes`, `test_every_route_has_role`, `test_session_scope`).
- Esquemas y extensión: ya creados en `0001`. La cadena es lineal `0001 ... 0005_settings, 0005b_auth_security, 0006_members, 0007_plans`; `0008` a `0011` cuelgan de `0007_plans`.
- El `downgrade` de `0001` hace `DROP SCHEMA ... RESTRICT` (`migrations/versions/0001_core_schemas.py:42-44`). `0011` debe borrar en su `downgrade` la función de trigger de `payments`, o el ciclo a base fallará (`tests/core/test_migrations.py:60`).
- El modelo a imitar para la inmutabilidad es `audit.forbid_mutation()` con triggers `BEFORE UPDATE OR DELETE` y `BEFORE TRUNCATE` (`migrations/versions/0002_audit_log.py:79-93`).

### 1.3 Pruebas: infraestructura que el sprint reutiliza

| Pieza | Archivo:línea | Nota |
|---|---|---|
| `session` (savepoint) | `tests/conftest.py:251` | Una conexión, transacción externa, `create_savepoint`. Todo se revierte. |
| `bus_listo`, `sin_llaves`, `proveedor_local` | `tests/conftest.py:266-292` | Ya en `tests/conftest.py` (S2-D19). Los socios con campos cifrados las necesitan. |
| `restaurar_bus` (autouse) | `tests/conftest.py:297` | Foto de `events._subscribers` por prueba. **Una suscripción hecha por un import perezoso dentro de una prueba se pierde al restaurar y no vuelve** (el módulo queda en caché). Importar `memberships.service` al nivel de módulo del archivo de prueba o en un `conftest`. |
| `reset_rate_limit` (autouse) | `tests/conftest.py:308` | Almacenes del límite vacíos por prueba. |
| `capturar_eventos` | `tests/conftest.py:321` | Para `PaymentRegistered`, `MembershipSold`. |
| `reloj` | `tests/conftest.py:372` | `FrozenClock(T0)`; `reloj.advance(days=...)`. |
| `api_prueba`, `app_http`, `usuario_real`, `cabeceras`, `cliente_desde` | `tests/conftest.py:420-572` | App real sin lifespan sobre la `session` de la prueba. |
| `dos_sesiones` | `tests/conftest.py:578-607` | Commit real; limpia settings, socios, planes, auth y la cola de auditoría. **No limpia memberships ni payments**: agregar `LIMPIAR_MEMBERSHIPS` y `LIMPIAR_PAYMENTS` (los pagos con `DISABLE TRIGGER USER` primero, como `audit_log` en `:603-607`). |
| `LIMPIEZA_DE_SESION` | `tests/conftest.py:208-222` | Igual: agregar membresías, congelaciones y pagos. |
| `tests/members/conftest.py` | `bus_confirmado` | Llaves con commit real para concurrencia. Patrón a copiar. |
| Fábricas | `tests/factories/__init__.py` (`FACTORIES`), `members.py` (`make_member`, `make_members`, `KNOWN`), `plans.py` (`make_plan`, `make_plans`), `users.py` | Faltan `make_membership` y `make_payment` (y las entradas de `FACTORIES`). Cada fábrica cierra con `session.commit()` (libera el savepoint). |
| Ayudas por módulo | `tests/members/_apoyo.py` (`cuerpo`, `entrada`, `CAMPOS_DETALLE`, `MASCARAS_KNOWN`), `tests/plans/_apoyo.py`, `tests/settings/_apoyo.py` | `CAMPOS_DETALLE` es el conjunto exacto de claves de `MemberDetailOut`: cambia con S3-B9. |

### 1.4 Front

| Punto | Archivo:línea | Estado y consecuencia |
|---|---|---|
| Lista de socios | `web/src/features/members/pages/MembersListPage.tsx:40-66, 110-196` | Chips "Todos" y "Dados de baja"; la columna Membresía ya pinta `StatusTag` si `membership_status` es un estado conocido; los filtros de la URL salen de `useListParams` con la lista `FILTERS`. Para agregar `membership_status` y `plan_id` hay que ampliar `FILTERS` y `MembersParams` (`api.ts:17-23`). |
| Fila estricta | `web/src/features/members/schemas.ts:197-208` | `memberRowSchema` es `.strict()`: cualquier campo nuevo en `MemberRowOut` (por ejemplo `plan_id` o `end_date`) invalida toda la página. Mantener las ocho claves actuales o cambiar el schema y `schemas.test.ts` en el mismo slice. |
| Detalle de alta | `web/src/features/members/schemas.ts:214-219` | `memberDetailSchema` no es estricto (solo id, nombre, avisos): la ficha necesita un schema propio. |
| Ruta de ficha | `web/src/config/routeTable.ts:51-52` | `/socios/:id` y `/socios/:id/editar` sin `load`: hasta darles `load` dan 404. `memberHref` (`memberLinks.ts:14`) ya apunta a `/socios/{id}`. |
| Rutas de membresías y pagos | `routeTable.ts:56-58` | `/membresias`, `/membresias/vender`, `/pagos` sin `load`. Además `ENABLED_FEATURES` (`web/src/config/features.ts:34`) no incluye `memberships` ni `payments`: sin eso la ruta y el menú siguen ocultos aunque tengan `load`. Actualizar `features.test.ts:11` y `layouts/nav.test.ts`. |
| Permisos | `web/src/core/auth/permissions.ts:24-49` | Ya existen `members.reveal`, `members.update`, `members.delete`, `members.reactivate`, `members.document.update`, `memberships.view`, `memberships.sell`, `memberships.freeze`, `memberships.cancel`, `payments.view`, `payments.register`, `payments.void`. No hace falta tocar la matriz. |
| `MaskedValue` | `web/src/shared/ui/MaskedValue.tsx:21-31` | `onReveal` es una función que devuelve `Promise<string>`. El `reveal` del API devuelve texto, fecha, objeto o nulo: el contacto de emergencia es un objeto y hay que aplanarlo a texto en la feature o ampliar el tipo. El claro vive solo en estado local con TTL de 60 s. |
| `StatusTag` y etiquetas | `web/src/shared/ui/statusLabel.ts:8-37` | Ya incluye `pending_payment` (etiqueta "Pendiente de pago", tono warning, Q3) y `none` ("Sin plan"). |
| `DataTable` | `web/src/shared/ui/DataTable.tsx:14-31, 185-192` | Ya cambia a tarjetas en móvil por `useMediaQuery(MOBILE_QUERY)` y soporta `Column.wide`. US-072 (lista en tarjetas a 390 px) ya está cubierta por el kit; `MemberCardList` solo se justifica si `Socios_Movil.html` pide algo que `DataTable` no hace. |
| Kit disponible | `web/src/shared/ui/index.ts` | `SidePanel`, `ConfirmModal`, `Modal`, `Tabs`, `Chips`, `KpiCard`, `HistoryAside`, `FilterBar`, `Pagination`, `PageHeader`, `Field`. No hay `Select` propio: `Field` acepta un control hijo. |
| Cliente y errores | `web/src/core/api/client.ts`, `errorCodes.ts:11-39`, `response.ts:17` | Los códigos nuevos (`membership_overlap`, `membership_conflict`, `membership_cancelled`, etc.) deben entrar a `API_ERROR_CODES`; `errorCodes.test.ts` busca cada literal en `api/src`. |
| Formato | `web/src/core/i18n/format.ts:66-162` | `formatCop`, `parseCop`, `formatDate`, `formatDateTime`, `formatMonth`, `todayBogota`. Único lugar permitido para `Intl`. |
| Claves de consulta | `web/src/features/members/api.ts:33-36` | La lista usa la clave de dos elementos con `params`; el detalle usará otra forma. La invalidación por el prefijo `members` alcanza a ambas. |
| Config del sistema | `web/src/features/system/pages/ConfigPage.tsx:26-28` | Tres pestañas (gimnasio, privacidad, membresías); agregar "Medios de pago". `web/src/features/system` existe, así que `web/system` sirve para `slice-gate.sh`. |

## 2. Patrones del módulo a replicar (members y plans)

**Archivos.** `models.py`, `schemas.py`, `exceptions.py`, `service.py`, `router.py`, `__init__.py` con docstring del contrato. Si el service crece, fachada con `__all__` y privados (S2-R10).

**Modelo auditado** (`mod/members/models.py:42-74`, `mod/plans/models.py`):

```python
class Membership(CommonColumnsMixin, Base):
    __tablename__ = "memberships"
    __table_args__ = (CheckConstraint(...), ExcludeConstraint(...), {"schema": "memberships"})
    __audited__: ClassVar[bool] = True
    __audit_subject__: ClassVar[str] = "member_id"  # llena audit_log.subject_member_id (G-05)
```

Sin columnas `deferred` (el hook lee `history.deleted`). Dinero `Mapped[int]`, fechas `date` o `datetime` con zona. Un `float`, `Decimal` o `bytes` aborta el flush (`CanonicalError`).

**Excepciones.** Subclases de `DomainError` con `status`, `code` y `default_message` de clase (`mod/members/exceptions.py:30-47`); `field` y `existing_id` por constructor. El mensaje nunca repite el valor recibido.

**Service: alta con carrera** (`mod/members/service.py:260-270`, `mod/plans/service.py:190-200`). Pre-chequeo, luego insertar dentro de `begin_nested()` y traducir solo la restricción conocida:

```python
try:
    async with session.begin_nested():
        session.add(fila)
        await session.flush()
except IntegrityError as error:
    if violated_constraint(error) != NOMBRE_DE_LA_RESTRICCION:
        raise
    raise MembershipOverlap(...) from None
```

Con `eager_defaults` no hace falta `session.refresh`. Para el `EXCLUDE` el SQLSTATE es `23P01`; `violated_constraint` lee `constraint_name` de la causa de asyncpg: verificarlo con una prueba que inserte directo dos rangos solapados.

**Contratos para otros módulos.** Dataclasses congeladas en `schemas.py` (`MemberRef`, `PlanSnapshot`), nunca el ORM; consultas por lote (`names_for` con lista vacía no consulta).

**Router plano** (`mod/members/router.py:37-63`):

```python
router = APIRouter(tags=["memberships"], dependencies=[Depends(no_store)], responses=responses_for(401, 403))
Staff = Annotated[Principal, Depends(require_role("admin", "coach"))]
Admin = Annotated[Principal, Depends(require_role("admin"))]
Session = SessionDep

@router.post("/members/{member_id}/memberships", status_code=201,
             response_model=SellMembershipOut, responses=responses_for(404, 409))
```

Ruta completa en el decorador; las fijas (`/memberships/summary`, `/payments/summary`, `/payments/methods`) antes de las que llevan parámetro; parámetros de ruta con nombre propio (`member_id`, `membership_id`, `payment_id`). Límite por usuario con `ratelimit.enforce(bucket, str(principal.user_id), limit=..., window_s=..., kind="user")` dentro de la ruta (`mod/members/router.py:56-62`).

**Listas.** `response_model=Page[Fila]`, `page: Annotated[PageParams, Depends()]`, `q: SearchQuery = None`. Enriquecimiento por lote con `names_for` (members, plans, auth); `paginate` pagina una sola entidad, así que las filas con varias columnas se arman con el ORM de la entidad propia y se completan después.

**Eventos y suscripciones.** Evento como `@dataclass(frozen=True, kw_only=True)` que hereda `DomainEvent` (`mod/members/service.py:118-120`); `events.subscribe(Tipo, handler)` al final del `service.py` (patrón de `mod/audit/service.py:104-107`).

**Pruebas por módulo.** `tests/<mod>/_apoyo.py` (constantes, `cuerpo()`, lecturas con SQL crudo), `conftest.py` solo si hay fixtures propias, pruebas puras `test_*_rules.py`, de service con `session`, de router con `app_http`, `usuario_real("coach")` y `cabeceras(usuario)`; concurrencia con `dos_sesiones` y `bus_confirmado`; reloj con `reloj`; eventos con `capturar_eventos`.

**Front.** Un directorio por feature con `api.ts` (hooks de TanStack Query con `parseResponse(schema, await api.get(...))`), `schemas.ts` (Zod; formularios con React Hook Form y el `zodResolver` propio de `shared/lib/zodResolver.ts`), `*Errors.ts` (traducción de `ApiError` a mensaje), `*Links.ts`, `components/` y `pages/` con `*.module.css` y pruebas junto al archivo. Mutaciones con datos sensibles: `gcTime: 0` (`useCreateMember`, `web/src/features/members/api.ts:50-62`).

## 3. Pruebas de arquitectura existentes: qué hacen y qué hay que tocar

| Prueba | Hoy | Impacto del sprint |
|---|---|---|
| `test_service_import_graph.py` | `ALLOWED_EDGES = {(audit, auth), (auth, settings)}` (`:28-30`); `LAZY_IMPORT_WHITELIST` vacía y la aserción `frozenset() == LAZY_IMPORT_WHITELIST` (`:31, 168`); `_grafo_real` suma aristas de nivel de módulo y perezosas (`:125`) y el ciclo se calcula sobre ambas; `test_plans_no_agrega_aristas` (`:143`) | Reescribir: (a) ciclo solo sobre aristas de nivel de módulo; (b) `ALLOWED_EDGES` con `memberships` hacia `members`, `plans`, `settings`, `payments` (y `auth` si usa `names_for`), y `payments` hacia `members`, `auth`, `settings`; (c) lista blanca con `(members, memberships)` y `(payments, memberships)`, más `(plans, memberships)` si se deja preparada; (d) quitar `test_plans_no_agrega_aristas` y la aserción de vacío. Consolida además `test_service_import_cycles`, `test_payments_does_not_import_memberships` y `test_payments_dependencies`, que no existen todavía. |
| `test_audited_tables.py` | `PENDING_AUDITED` con `memberships.memberships` y `payments.payments` (`:43-46`) | Al crear las tablas pasan a `REQUIRED_AUDITED_TABLES_V01`; falta `memberships.membership_freezes` (tabla nueva de `0009`): auditarla o excluirla con motivo. |
| `test_audit_module.py:45` | `assert MODULES == ("auth", "settings", "audit", "members", "plans")` | Actualizar la tupla en el slice que cambia `MODULES`. |
| `test_no_cross_models.py` | Recorre todos los módulos con `find_forbidden_imports` | Cubre los nuevos sin cambios. `PRIVATE_HELPERS` de `tests/architecture/_imports.py:33` solo conoce `auth`: agregar los privados de `members`, `memberships`, `payments` si se parten. |
| `test_no_plaintext_at_rest.py` | Exige fábrica solo para tablas con columnas cifradas | Memberships y payments no cifran nada: no hace falta. |
| `test_list_rows_without_sensitive_fields.py` | Recorre los `GET` bajo `/api/v1/members` con respuesta `Page_...` | Verá `GET /members/{id}/memberships` y `/payments`; sus filas no deben declarar `email`, `phone`, `document`, `birth_date`, `emergency_contact`, `*_idx` ni `*_hint`. |
| `test_list_routes_use_page_params.py` | Toda `Page_...` exige `PageParams`, parámetro `q` y `limit` con máximo 200; ningún `GET` 200 puede ser un arreglo (`:65-67`) | `GET /payments/methods` no puede devolver un arreglo; las listas anidadas por socio necesitan `q`. |
| `test_no_store_routes.py` | Toda ruta con rol lleva `no_store` en el árbol de dependencias | Los dos routers nuevos con `dependencies=[Depends(no_store)]`. |
| `test_error_codes_per_route.py` | `CON_LIMITE` (`:26-35`) es la lista exacta de rutas con 429; 401 en toda ruta con sesión; 422 solo con parámetros o cuerpo | El router de socios declara 429 a nivel de router (`mod/members/router.py:38`): al sumar `GET /members/{id}` y demás, todas heredarían 429 y la prueba falla. Pasar el 429 a las rutas que lo tienen o ampliar `CON_LIMITE`. Toda ruta nueva con límite se agrega a la lista. |
| `test_session_scope.py` | Cada nodo `get_session` con `scope="function"` | Usar siempre `SessionDep` (varios desgloses escriben `Depends(get_session)`: no copiarlo). |
| `test_file_and_function_size.py` | 800 líneas por archivo, 50 por función | Ver riesgo 3. |
| `test_no_sensitive_in_logs.py` | La pata `reveal` está saltada (`:66-68`, "US-074, S3-B10") | Implementar en S3-B10 con un `reveal` real y buscar el claro en stdout y `caplog`. |
| `test_settings_no_secrets.py` | `set(SECTION_REGISTRY) == set(ENABLED_SECTIONS)`; ningún campo con nombre de secreto; `extra="forbid"` anidado | La sección `payment_methods` debe cumplirlo. |
| Nuevas del plan | `test_gates_registered`, `test_payment_method_codes`, `test_payments_immutability_code`, `test_no_cross_schema_sql`, `test_no_physical_delete` | `test_no_physical_delete_users.py` vigila solo `auth`: la nueva debe cubrir members, plans, memberships y payments (CLAUDE.md, datos 4). |

## 4. Riesgos de integración

Ordenados por gravedad. Cada uno trae su mitigación.

1. **[ALTO] Nadie recalcula `status` en el Sprint 3.** US-091 lista por el estado guardado ("tal como están guardados; el job de US-094 y las escrituras los mantienen al día"), US-092 `resolve_member_status` también se apoya en la columna, y SPRINT-03 deja fuera US-094. Consecuencias: una membresía vence por fecha y sigue `active`; "Por vencer" nunca aparece; una congelación termina y la membresía queda `frozen`; el chip "Vencidos" y el resumen mienten. La función pura `compute_status` sí existe (US-083). Mitigación recomendada, a decidir en el blueprint y registrar en DECISIONES.md: (a) las lecturas (`status_for`, `member_ids_by_status`, `summary`, `GET /memberships/{id}`) calculan el estado efectivo en Python con `compute_status(membership, today, expiring_days, freezes)` sobre filas cargadas por lote; (b) el filtro `status` de `GET /memberships` se resuelve en SQL con el mismo criterio (CASE con `today` y `expiring_days`), o se adelanta la parte de servicio de US-094 (`recompute_statuses(session, today)`, sin worker) a S3-B7 y se invoca antes de listar. Sin esto, la demo "Congelar 10 días" no se puede cerrar de punta a punta.

2. **[ALTO] Interbloqueo entre venta y pago.** El hook de auditoría toma `pg_advisory_xact_lock(AUDIT_CHAIN_LOCK_KEY)` en cada fila auditada (`core/audit.py:279`). `sell` (US-084 T5) toma el candado del socio y después flushea (cadena). `register` flushea el pago (cadena) y el handler de activación (US-086) pide el candado del socio: orden inverso. Dos transacciones sobre el mismo socio se cruzan, PostgreSQL aborta una con `40P01` y el usuario ve un 500. Mitigación: el candado del socio se toma siempre antes de cualquier flush auditado. En `register` y `void`: resolver `member_id` por el puerto (`payability`), tomar el candado, y solo entonces insertar. Prueba con `dos_sesiones` que ejecute `sell` y `register` simultáneos sobre el mismo socio.

3. **[ALTO] `members/service.py` y `memberships/service.py` superan 800 líneas.** `members/service.py` ya tiene 523; ficha, reveal, update, deactivate y reactivate, y filtros suman unas 400. La partición sigue S2-R10: fachada `service.py` con `__all__` y privados (`rules.py` puras, lecturas, escrituras), añadidos a `PRIVATE_HELPERS`. Para memberships, nacer partido: `rules.py` (US-083, `classify_open`, `find_overlap`, `apply_freeze`), ventas y renovación, ciclo de vida (congelar, anular, handlers), consultas (lista, detalle, resumen, `status_for`). El análisis de aristas lee todos los archivos del módulo, y los privados de un módulo no los puede importar otro. Funciones de más de 50 líneas: `sell` con primer pago, la lista de membresías y `reveal` pasan fácil; partirlas desde el diseño.

4. **[ALTO] `test_service_import_graph.py` falla desde B1.** Ver sección 3. La lista blanca de imports perezosos y las aristas permitidas deben entrar con el primer slice de `memberships`, no en B4 como dice SPRINT-03. El ciclo `memberships` y `payments` es real: `memberships` importa `payments.service` a nivel de módulo (registra el gate, llama a `register` y `sum_not_voided`) y `payments` solo lo toca de forma perezosa para enriquecer listas (`refs_for`, US-098). Registrar ambos sentidos con su comentario en la lista blanca.

5. **[ALTO] Trigger de `0011` y el `updated_at` del mixin.** `CommonColumnsMixin.updated_at` tiene `onupdate=func.now()`: al anular, el `UPDATE` toca `voided`, `void_reason`, `voided_by`, `voided_at` y `updated_at`. El trigger debe permitir esas cinco columnas y nada más, comparando `OLD` y `NEW` columna por columna (`IS DISTINCT FROM`), rechazar la segunda anulación (`OLD.voided = true`), `DELETE` y `TRUNCATE`. SQLAlchemy solo envía las columnas modificadas, lo que ayuda. Pruebas: una por columna permitida y una por cada prohibida (`id`, `created_at`, `created_by`, `member_id`, `membership_id`, `amount_cop`, `method`, `reference`, `paid_at`, `registered_by`), con SQL crudo. El `downgrade` borra triggers y función antes de la tabla (ver 1.2).

6. **[ALTO] Limpieza de pruebas ante el trigger de pagos.** `LIMPIEZA_DE_SESION` y `dos_sesiones` borran con `DELETE`. Sobre `payments.payments` fallarán por su propio trigger: usar `ALTER TABLE payments.payments DISABLE TRIGGER USER` y `ENABLE`, como con `audit_log` (`tests/conftest.py:215-217, 603-607`). Memberships no tiene trigger, pero necesita su `DELETE` de limpieza.

7. **[MEDIO] `PaymentRegistered` y el autoflush.** El handler suma `sum_not_voided` en la misma sesión; si `register` no hace `flush` antes de `emit` la suma no ve el pago (US-095, riesgo 4). En la venta con primer pago el orden es: insertar membresía, flush, `register` (flush), `emit`, handler.

8. **[MEDIO] Códigos de error duplicados.** US-084 T4 crea `MemberNotFound` propio en memberships; `members.exceptions.MemberNotFound` ya existe (404 `member_not_found`) y el front lo conoce (`errorCodes.ts`). Importarlo de `members.exceptions` (permitido por la regla 2 de módulos). Igual con el plan: `plans.get` lanza `PlanNotFound` (404), pero el contrato de venta pide 422 `plan_id` y `plan_inactive`; traducir en `sell`.

9. **[MEDIO] `GET /payments/methods` y las listas anidadas contra las pruebas de listas.** Ver sección 3. Respuesta como objeto con una lista `items`, y `q` en `GET /members/{id}/memberships` y `/payments` (aunque `q` no filtre nada, documentarlo).

10. **[MEDIO] Filtros de lista de socios.** El `UNION` de ramas (`mod/members/service.py:409-436`) repite la condición de baja en cada rama para que la de documento use el único parcial. Los filtros por membresía se agregan como una condición más sobre `Member.id` en la consulta externa (`:496`), no dentro de las ramas: el parcial queda intacto. `Member.id.in_(lista)` expande un parámetro por id (tope de asyncpg 32.767); usar `any_(array)` con un solo parámetro y, para `none`, el complemento con `all_`. A 1.000 socios no importa, pero no dejarlo en `IN` expandido. Hoy `MemberRowOut.membership_status` y `plan_name` salen `None` (`:470-471`); se llenan con `status_for` por página.

11. **[MEDIO] `memberRowSchema` estricto.** Ver 1.4. Si el API agrega cualquier campo a `MemberRowOut`, el front invalida la lista completa. Mantener las claves actuales y que `membership_status` y `plan_name` sigan siendo texto o nulo; regenerar `types.ts` y correr `types.contract.test.ts` en el mismo slice.

12. **[MEDIO] Máscaras de la ficha y bitácora.** `bus.batch` agrega las filas y descarta el `record_id` (`core/crypto/oplog.py:129`). N-01 y el demo esperan una fila `decrypt` por vista; con el lote quedan cinco filas con `batch_id` común y sin socio. Si importa saber qué ficha se abrió, no usar el lote para `mask`: `reveal(obj, campo, "mask")` suelto deja una fila por campo con el `record_id` del socio. Decidir y fijarlo con prueba. Cada apertura de ficha escribe en `crypto_ops` (en `before_commit`), así que un `GET` abre una escritura.

13. **[MEDIO] Reveal: ruta de la auditoría.** US-107 (criterios 1 y 2) y el catálogo de eventos piden `SensitiveFieldRevealed` con un suscriptor de `audit`; US-074 y SPRINT-03 piden `audit.record` directo en el service y prohíben el suscriptor duplicado. El evento no existe en el código. Camino consistente con el resto: `members.service.reveal` llama a `core.audit.record(action="reveal", table_name="members.members", record_id=id, after={"field": campo}, subject_member_id=id)` y emite `SensitiveFieldRevealed` sin suscriptor en `audit` (evita una arista de `audit` hacia `members`). El `table_name` es `members.members` (US-074 escribe `"members"`; `test_reveal_entry.py` y el hook usan `members.members`). Cierra US-107 criterios 1 y 2.

14. **[MEDIO] Reactivar un socio y la unicidad del documento.** `uq_members_document_idx_alive` solo cubre vivos. Si otro socio tomó el documento mientras estaba de baja, `reactivate` choca: traducirlo con el mismo patrón `begin_nested` y `violated_constraint` a `MemberDocumentDuplicated`. Cambiar el documento (solo admin, N-20) igual.

15. **[MEDIO] Edición recifra y reindexa.** `PATCH /members/{id}` debe cargar el socio completo (no `load_only`), asignar `Secret.from_plain` solo a los campos que cambian y dejar que `before_flush` recalcule los `_idx`; asignar un `_idx` a mano falla (`index_manual`). El hook de auditoría necesita el valor anterior cargado para `before`.

16. **[MEDIO] `reveal` de `emergency_contact` y `birth_date`.** El service devuelve `date` o `dict`; `RevealOut.value` es texto, objeto o nulo, y `MaskedValue` espera `Promise<string>`.

17. **[MEDIO] `EXCLUDE` y las congelaciones.** Extender `end_date` al congelar es un `UPDATE` que el gist revalida; ante una futura que choque llega `23P01` y el plan quiere 409 `overlaps_future_membership`. Hacer el chequeo en código con `find_overlap` y dejar el `23P01` como red de seguridad, traducido con `violated_constraint` al nombre de la restricción. Nombrar el `EXCLUDE` explícitamente en modelo y migración (la convención de nombres solo cubre `ix`, `uq`, `ck`, `fk` y `pk`).

18. **[MEDIO] Dinero: `BIGINT` contra JavaScript.** US-095 declara `amount_cop BIGINT` con tope de 2^63-1; el front maneja `number` (2^53). `plans.price_cop` tiene tope de 1.000.000.000. Acotar `amount_cop` a un tope coherente.

19. **[BAJO] Regeneración de contrato.** Cada slice con rutas: `export-openapi`, `gen:api` y `types.contract.test.ts` (CI falla si `docs/openapi.json` queda desactualizado, `ci.yml:73-75`).

20. **[BAJO] `tests/migrations/test_0007_plans.py:165`** exige que la cabeza única sea `0007_plans`. Al crear `0008` falla; ajustarla como se hizo con `0006` (la revisión está en la cadena hasta head; `test_single_head` ya exige cabeza única). No la atrapa el gate de `memberships` (corre `tests/memberships` y `tests/architecture`); sí `run-gates.sh`.

21. **[BAJO] `ruff` selecciona `S`.** SQL con f-strings en `op.execute` dispara S608; para el trigger usar SQL literal sin interpolar valores. `PLC0415` no está seleccionada: los imports perezosos no necesitan `noqa`, pero sí un comentario que cite la regla 2 bis.

22. **[BAJO] Búsqueda de pagos.** US-098 busca `lower(reference) = lower(q)`; sin índice sobre esa expresión. A escala de un gimnasio es irrelevante, pero `test_list_performance` (500 ms) debería correr con `perf`.

## 5. Discrepancias entre SPRINT-03 y los desgloses, y el código real

| El plan dice | El código real | Acción |
|---|---|---|
| `members.service.ref(member_id)` devuelve `MemberRef` o `None`, con `deleted_at` (US-084, US-093) | `get_ref(session, id) -> MemberRef`, lanza `MemberNotFound`; el campo es `is_deleted: bool` | Usar `get_ref` y `is_deleted`; no crear `ref` |
| `members.service.active_ids()` (US-092 T5, supuesto) | No existe | Crearlo en un slice previo a B7 y exportarlo, o resolver `summary` con otro camino. Es una arista de lectura nueva de memberships hacia members |
| `bus.op_context(user_id, record_id, purpose)` (US-073 T1, US-074 T1, US-077) | No existe. Hay `bus.batch(verb, data_class)`, los argumentos `purpose=` y `record_id=` de `decrypt`, y `types.reveal(obj, field, purpose)` | Usar `reveal(obj, campo, "mask")` o `"reveal"` |
| `settings.service.payment_methods()` (US-056, US-095, EP-16) | No existe; el patrón vigente es `memberships_policy(session)` y `gym_name(session)` | Crear `payment_methods(session)` con ese estilo; `decorate_methods` puro |
| `compute_status(membership, today, expiring_days)` (SPRINT-03, S3-B1) | US-083 corrige a cuatro argumentos, con `freezes` (N-25) | Corregir SPRINT-03 |
| `Clock.now()` (US-095) y `today_bogota()` como función de `core/clock` | `now_utc()` y el método `today_bogota()` del reloj actual | Usar `current_clock()`; las funciones puras reciben `today` o `now` |
| `Depends(get_session)` y `current_user.id` (US-084, US-095 y otros) | `SessionDep` y `principal.user_id`; `test_session_scope` falla con `Depends(get_session)` | Usar `SessionDep` (S2-R8) |
| `sell` y `freeze` reciben `by: UUID` y `clock: Clock` | Los services de socios y planes usan `get_actor()` y `current_clock()` | Dejar `by` solo donde el CLI de importación (US-112) lo necesite; si no, seguir el patrón vigente |
| El router de reveal hace `await session.commit()` explícito (US-074 T4) | `SessionDep` ya confirma antes de enviar la respuesta (S2-R8) | No agregar commit manual |
| `table_name="members"` en la fila `reveal` (US-074 T1) | El hook y `test_reveal_entry.py` usan `members.members` | Usar `members.members` |
| La ficha incluye "notas" (US-073 resumen) | `notes` se eliminó (M-5) | Quitar de la historia |
| `GET /payments/methods` devuelve un arreglo (US-056, README) | `test_list_routes_use_page_params.py:65-67` prohíbe el arreglo suelto | Objeto con lista `items` |
| Pagos "nunca importa memberships en ningún nivel" (US-095 T12; SPRINT-03 absorbe esa prueba) | US-098 hace que `payments.list` llame a `memberships.service.refs_for` | Aceptar el import perezoso de `payments` a `memberships` como segundo sentido de la lista blanca; el nivel de módulo sigue prohibido |
| `-m slow` (S3-B7, validación del sprint, US-091 T8) | Marcador registrado: `perf` (`api/pyproject.toml:78-81`), fuera del gate (S2-D27) | Usar `perf` o registrar `slow` y decidir si entra al gate |
| Wave 0: "no hay infraestructura nueva" | DECISIONES (revisión de Fase 4, L3) asigna al primer slice de infraestructura del Sprint 3 las imágenes base por digest (`api/Dockerfile`, `web/Dockerfile`, Compose, `scripts/ci/test_nginx_conf.sh`); N-5 asigna al front del Sprint 3 la actualización de vitest y stylelint | Agregar un slice S3-W0 o diferirlas con decisión explícita |
| `test_service_import_graph` entra en S3-B4 | Falla desde B1 (riesgo 4) | Moverlo a B1 |
| US-071 y la lista: siete chips; `Socios_Lista.html` | El diseño trae "Dados de baja" y "Sin membresía"; no trae "Pendiente de pago". La ficha no trae "Dado de baja", "Reactivar", "Congelar" ni "Anular" | `// DESIGN-GAP:` en cada uno (Q3, N-20) y anotarlos en `docs/BRECHAS.md` |
| US-072 pide `MemberCardList` | `DataTable` ya renderiza tarjetas en móvil | Decidir si hace falta el componente o basta la prueba E2E `members-mobile` sobre el kit |
| `test_service_list_membership_filters` usa un doble hasta que exista US-092 | En S3-B9 el service real ya existe (B7) | Probar con el real |
| Ficha: "sin `warnings` en lectura" (US-073 T2) | `MemberDetailOut.warnings` es obligatorio | Devolver lista vacía |
| La ficha solo muestra `membership_status` | `MemberDetailOut` no tiene `plan_name` y `CAMPOS_DETALLE` es un conjunto exacto (`tests/members/_apoyo.py`) | Ampliar schema y conjunto en el mismo paso |
| `0009_membership_freezes` con FK a `memberships.memberships` | Mismo esquema: válido. `payments.membership_id` y `member_id` sin FK, correcto | Sin acción |
| SPRINT-03 Wave 0: `alembic current` en `0007_plans` | Verificado en `apex-db-1`: `0007_plans (head)` | Cumple |

## 6. Lo que `slice-gate.sh` necesita para los módulos nuevos

Lectura de `scripts/workflow/slice-gate.sh` (226 líneas):

- `slice-gate.sh memberships` y `payments` resuelven `src/app/modules/<modulo>` y `tests/<modulo>`; **fallan con "módulo inexistente" si el directorio de código no existe**. El Rojo con stubs debe crear antes `api/src/app/modules/memberships/` y `payments/` (con `__init__.py`). Si se pasa lista de archivos, deben existir bajo `api/tests/`. Sin lista, `tests/<modulo>` debe existir.
- El gate corre `ruff check`, `ruff format --check` y `mypy` sobre el directorio del módulo, y `pytest <archivos> tests/architecture -q`. **No corre el ciclo de Alembic ni `tests/migrations`**: el ciclo del plan es manual (`alembic upgrade head`, `downgrade -1`, `upgrade head` contra `apex-db-1`). Las pruebas `tests/migrations/test_0008_...` hay que pasarlas por lista o correrlas aparte.
- `slice-gate.sh settings`, `members`, `audit` (con `tests/audit/test_reveal_entry.py`) y `core/logging` (con `tests/core/test_logging_redact.py`) existen y resuelven. `core/logging` mapea a `src/app/core/logging.py` y a `tests/core`.
- Front: `web/<feature>` exige `web/src/features/<feature>`. **`web/memberships` y `web/payments` no existen**; el primer archivo de prueba del Rojo los crea. `web/system` y `web/members` existen. `web/shared` apunta a `src/shared`. El gate lintea y tipa todo archivo `.ts` o `.tsx` modificado respecto a `git merge-base HEAD main` (HEAD es main hoy, así que son todos los de la rama) y corre `vitest run` sobre la lista o el directorio de la feature.
- `run-gates.sh`: `pytest --cov=app --cov-fail-under=80 -m "not perf"`, `scripts/ci/test_*.sh` (necesitan Docker), `npm run lint`, `tsc`, `npm test -- --run --coverage` y `npm run build`. `cli.py` y `worker/` siguen fuera de la cobertura hasta el Sprint 4A (`api/pyproject.toml:87`).
- `checkpoint-commit.sh` solo confirma con sello vigente (huella del árbol): cualquier edición posterior al gate lo invalida.

Infra y CI sin cambios obligados:

- `.env.example` no necesita variables nuevas: los límites de congelación y de retroactividad viven en `settings.memberships`, y nada de pagos se configura por entorno.
- `infra/compose*.yml` e `infra/nginx` igual.
- El bind mount de `api/src` recarga solo, pero **una migración nueva no dispara recarga**: `restart api` para que el lifespan corra `upgrade head`. `pyproject.toml` no cambia, así que no hace falta reconstruir la imagen.
- `docs/openapi.json` y `web/src/core/api/types.ts` cambian en cada slice con rutas (`ci.yml:73-75, 150`).
- El volcado previo a `0011` usa el servicio `db` (`POSTGRES_USER=apex`): `docker compose exec db pg_dump -U apex -Fc apex`.
- Puertos locales: web `8180`, api `8181`, db `5442`, db de prueba `5443`; `FRONT_BASE_URL=http://localhost:8180` (alineado, a diferencia de lo que anotó la exploración del Sprint 2).

## 7. Deuda heredada que toca al sprint

- **`reveal` pendiente:** la pata de `test_no_sensitive_in_logs` (saltada) y `tests/audit/test_reveal_entry.py` (con `uuid4()`, a repuntar a `make_member`) son de S3-B10. `SENSITIVE_KEYS` (`core/logging.py:40-62`) no cubre `value`, `reference` ni `amount_cop`: ningún log del service debe llevar el valor revelado ni la referencia del pago por `extra=`; las formas `apx1.` y JWT sí se redactan solas.
- **`pg_trgm`:** no instalada en `apex-db-1`. La búsqueda de socios por nombre recorre la tabla (deuda declarada para el Sprint 4A, S2-B8). El Sprint 3 la hereda sin cambio; la lista de pagos usa `search_ids` de socios y `lower(reference)`.
- **`cli.py` fuera de cobertura:** no cambia en el Sprint 3 (se quita en US-113, S4A-B1). El CLI llama `_load_module_services()` a partir de `MODULES`, así que `memberships` y `payments` se cargan solos.
- **`npm audit` de desarrollo:** 11 hallazgos en herramientas de prueba (vitest, tinypool, stylelint y transitivas). DECISIONES los asigna al front del Sprint 3; SPRINT-03 no los programa. El gate de CI es solo de producción.
- **Imágenes base por digest:** asignado al primer slice de infraestructura del Sprint 3; SPRINT-03 Wave 0 dice que no hay infraestructura nueva.
- **`memberRowSchema` estricto, `/socios/{existing_id}` sin pantalla (S2-D34) e `InicioPage` mínima:** el 409 del alta de socio enlaza a una ruta que cobra vida en S3-F1; `InicioPage` queda mínima hasta US-108 (Sprint 4A).
- **Controles de seguridad vigentes que el sprint no debe romper:** `SessionDep` (N-1); `SafeText` y `SafeMultilineText` para todo texto libre (los motivos de anulación y cancelación no pueden llevar NUL ni controles); `SearchQuery` con patrón sin controles; `offset` hasta 1.000.000; `extra="forbid"` en cuerpos; `no_store`; `responses_for`.
- **Volumen de auditoría:** `audit_log` recibe una fila por inserción y actualización auditada; una venta con primer pago genera al menos cuatro. El candado de la cadena serializa todas las escrituras auditadas del sistema hasta el commit: mantener las transacciones cortas.

## 8. Recomendaciones para el blueprint

1. Decidir primero el riesgo 1 (estado efectivo) y el 2 (orden de candados): cambian el contrato de `status_for`, `summary`, `list` y el diseño de `register`.
2. Mover al primer slice (S3-B1): `MODULES`, la reescritura de `test_service_import_graph.py`, `tests/migrations/test_0007_plans.py:165`, `tests/architecture/test_audit_module.py:45`, `PENDING_AUDITED`, las fábricas y la limpieza de pruebas para las dos tablas.
3. Crear `memberships` y `payments` ya partidos en privados con fachada; partir `members` antes de B9.
4. Seguir el patrón de `begin_nested` y `violated_constraint` con nombres de restricción explícitos, y probar `23P01` contra PostgreSQL real.
5. Un solo conjunto de códigos de error para el front, agregado a `errorCodes.ts` en cada slice backend para que `errorCodes.test.ts` los verifique contra `api/src`.
6. Front: ampliar `ENABLED_FEATURES` junto con las rutas que reciben `load`; usar `DataTable` y su vista de tarjetas para US-072; no tocar `memberRowSchema` salvo lo estrictamente necesario; nombrar cada brecha de diseño con `// DESIGN-GAP:` y anotarla en `docs/BRECHAS.md`.
7. El volcado previo a `0011`, el ciclo de Alembic y el `restart api` tras migrar son pasos manuales: documentarlos en el cuaderno `docs/scratch/sprint-03.md`.
