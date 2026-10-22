# Plan de implementación · Sprint 3 · Núcleo comercial: membresías, pagos y ficha del socio

- Rama: `feat/sprint-03-membresias-pagos`. HEAD de partida: `fe9eab0` (= `d65056e` más los tres documentos de las Fases 0, 1 y 1.5).
- Veredicto de entrada: AMARILLO (`docs/ddd/impacto/sprint-03.md`). Este plan absorbe las 10 condiciones para VERDE; la sección 10 da el slice de cada una.
- Entradas leídas completas: `SPRINT-03.md`, `impacto/sprint-03.md`, `sprint-03-exploracion.md`, `sprint-03-blueprint.md` (D1 a D40, S3-B1 a S3-B11, S3-F1 a S3-F7), `sprint-03-seguridad-diseno.md` (H-1 a H-3, M-1 a M-10, L-1 a L-13, D-1 a D-5, S3-D41 a S3-D59), `sprint-02-plan.md` (modelo de formato), `DECISIONES.md` (Sprint 2, revisión de Fase 4, S2-R1 a S2-R11), `docs/scratch/sprint-02.md`, `docs/scratch/sprint-02-verify-delivery.md` §9.3, `scripts/workflow/README.md`, `slice-gate.sh`, `CLAUDE.md`, y el código real que el sprint toca (`core/db.py`, `core/errors.py`, `core/ratelimit.py`, `core/security.py`, `tests/conftest.py`, `tests/architecture/*`, `web/tests/lint/boundaries.test.ts`, `web/src/config/*`, `infra/*`, `.github/workflows/ci.yml`).
- Mandan este plan y su bloque de decisiones. Donde el blueprint y la revisión de seguridad chocan, manda la revisión (D3, D12, D13, D17, D19, D21, D26, D27 quedan corregidas en la sección 1). Donde este plan se aparta de algo que el orquestador no fijó, lo dice con una decisión `S3-D60` o posterior y se reporta al final.
- Doctrina: TDD por slice (Rojo sobre stubs por el agente QA, Verde por el implementador, gate, checkpoint), deuda técnica cero (todo HIGH y MEDIUM es paso del plan; ningún LOW se difiere sin dueño) y ejecución al 100 % sin pausas intermedias.

## 0. Convenciones comunes a todos los slices

Alias de Compose usado en todo el plan:
`DC="docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml"`.

Cuaderno del sprint: `docs/scratch/sprint-03.md` (backend y orquestador) y `docs/scratch/sprint-03-front.md` (worktree del front). Cada slice deja su bloque Rojo y Verde (línea base, conteo de pruebas en rojo y motivo, desviaciones, evidencia Docker y psql), como en el Sprint 2.

Reparto por slice (como en el Sprint 2): el agente QA (`backend-qa-executor` o `frontend-qa-automation`) escribe stubs y Rojo y confirma el rojo con conteo; el implementador (`backend-implementor` o `frontend-ux-engineer`) hace el Verde, docs, contrato, gates, Docker y checkpoint. Un slice no empieza hasta el checkpoint del anterior en la misma rama.

### P-MIG · Protocolo de migración nueva (B1 `0008`, B2 `0009`, B3 `0010`, B4 `0011`)

1. Volcado previo: `$DC exec db pg_dump -U apex -Fc -n memberships -n payments apex > docs/scratch/sprint-03-antes-<rev>.dump && chmod 600 docs/scratch/sprint-03-antes-<rev>.dump` (S3-D58: solo los dos esquemas que el sprint toca; el completo lleva blobs cifrados y llaves envueltas). `*.dump` ya está en `.gitignore` (línea "Volcados de base de datos"); W0-1 agrega `*.sql.gz`. Se borran al cerrar el sprint (V12).
2. Detener el api mientras se redacta: `$DC stop api`. El api monta `migrations/` por bind y corre `upgrade head` en cada arranque; un archivo a medio escribir se aplicaría o rompería el arranque.
3. Escribir `api/migrations/versions/<rev>.py` y su prueba `api/tests/migrations/test_<rev>.py`. La primera migración de cada módulo agrega `from app.modules.<modulo> import models` en `api/migrations/env.py` (B1 `memberships`, B3 `payments`).
4. Probar contra `db_test`: `cd api && uv run pytest tests/core/test_migrations.py tests/migrations/test_<rev>.py -q`, con `TEST_DATABASE_URL` apuntando a `127.0.0.1:5443`.
5. Un solo head: `cd api && uv run alembic heads` (también lo exige `test_single_head`). Obligatorio porque el front corre en un worktree.
6. `$DC start api`. Esperar `healthy` y revisar `$DC exec api alembic current`: debe dar `<rev> (head)`. `$DC logs --tail 20 api` sin errores.
7. Ciclo en `apex-db-1`: `$DC exec api alembic downgrade -1`, `$DC exec api alembic upgrade head`, `alembic current`.
8. La prueba de la migración anterior (`test_0007_plans.py` en B1, `test_0008_memberships.py` en B2, etc.) pasa de "es head" a "está en la cadena hasta head" (D40).

### P-API · Contrato (todo slice de backend que cambie rutas o esquemas)

1. `cd api && uv run python -m app.cli export-openapi ../docs/openapi.json`.
2. `cd web && npm run gen:api`.
3. `cd web && npx vitest run src/core/api/types.contract.test.ts`.
4. Correr dos veces la exportación: deben salir idénticas.
5. Los dos archivos regenerados entran en el checkpoint del slice. Solo los slices de backend tocan `types.ts`; el worktree del front hace rebase sobre la rama antes de cada slice que consuma un contrato nuevo.
6. Si una respuesta que el front valida con un esquema Zod `.strict()` gana un campo (`memberRowSchema`, D35), el mismo checkpoint agrega el campo al esquema como opcional con valor por defecto y corre `cd web && npx vitest run src/features/members/schemas.test.ts`.

### Gate y checkpoint (orden E1, heredado del Sprint 2)

- Orden obligatorio en cada slice: (1) Verde completo; (2) P-API si cambió el contrato; (3) escribir el bloque del slice en el cuaderno y cualquier doc (`DECISIONES.md`, `CLAUDE.md`, `RUNBOOK.md`, `BRECHAS.md`, `ROUTES.md`); (4) **último** `slice-gate.sh` del slice, el que sella; (5) solo pasos que no tocan el árbol (Docker, psql, curl, Playwright contra el stack); (6) `checkpoint-commit.sh`. Si (5) obliga a cambiar código, se vuelve a (1). `checkpoint-commit.sh` aborta si la huella del árbol cambió después del sello.
- Se corren todos los `slice-gate.sh` del slice seguidos, sin editar entre uno y otro. `tests/architecture` corre en cada gate (A-5): desde B1 el grafo de services y desde B4 el gate real bloquean todo checkpoint.
- `PYTEST_ADDOPTS="-m 'not perf'"` en todos los gates salvo los que listan un archivo `perf` (B7, B8, B9) y V5 (E8 y S2-D27).
- Módulos del gate: `slice-gate.sh` resuelve `<modulo>` como `api/src/app/modules/<modulo>` y `api/tests/<modulo>`, y `web/<feature>` como `web/src/features/<feature>`, sin lista fija (S3-D61): `memberships`, `payments`, `web/memberships` y `web/payments` funcionan en cuanto existen los directorios, que crea el Rojo de su primer slice. El gate falla con "módulo inexistente" si se invoca antes.
- Lista blanca de imports perezosos (D2, G-03): `LAZY_IMPORT_WHITELIST = {("payments", "memberships"), ("members", "memberships"), ("plans", "memberships")}`. Todo import perezoso va dentro de la función, con el comentario `# lazy: G-03 (<par>)`. El grafo acíclico se exige solo sobre aristas de nivel de módulo.
- Limpieza de `db_test` (D30, S3-D48): `LIMPIAR_PAYMENTS` y `LIMPIAR_MEMBERSHIPS` hacen `ALTER TABLE <t> DISABLE TRIGGER USER`, `DELETE`, `ENABLE TRIGGER USER` sobre `payments.payments`, `memberships.membership_freezes` y `memberships.memberships` (las tres tienen triggers de inmutabilidad o de borrado), con guarda `to_regclass`, en `LIMPIEZA_DE_SESION` y en el `finally` de `dos_sesiones`, antes de `LIMPIAR_MEMBERS`. Orden: pagos, congelaciones, membresías, socios, planes.
- Antes del checkpoint `git status` muestra solo cambios del slice. Checkpoint: `bash scripts/workflow/checkpoint-commit.sh "S3-<id> <resumen>"`.

### Docker

- **api:** el bind de `src` con `--reload` recoge los cambios de código (`$DC logs --tail 20 api`). Una migración nueva exige P-MIG (paso 6). Solo `pyproject.toml`, `uv.lock`, `alembic.ini` o `Dockerfile` exigen `$DC up -d --build api` (W0-1 por el digest; el sprint no agrega dependencias).
- **tools:** usa COPY. Antes de `$DC run --rm tools <cmd>` con código nuevo, `$DC build api`. Este sprint no cambia `cli.py`; `_load_module_services` carga `memberships` y `payments` por `MODULES`.
- **web:** usa COPY. `$DC build web && $DC up -d web` antes de cualquier E2E del proyecto `stack` o de una demo contra `http://localhost:8180`.
- Tras editar `.env`, siempre `$DC up -d api` (no `restart`).
- No editar `api/src` mientras corre un E2E `stack` (`--reload` reiniciaría el api).

## 1. Bloque "Sprint 3" para `docs/ddd/DECISIONES.md`

Se agrega como sección nueva `## Sprint 3 · decisiones de implementación` en el checkpoint de S3-W0-1. Las decisiones del blueprint se registran con la opción elegida; las de seguridad y las de este plan continúan la numeración.

### Decisiones del blueprint (D1 a D40) con la opción elegida

- **D1:** el puerto `MembershipGate` vive en `payments/service.py` (`MembershipPayability(exists, cancelled, member_id, agreed_price_cop)`, `set_membership_gate`, `membership_gate`); lo registra `memberships/service.py` al final del archivo (B4); sin gate `register` y `void` fallan cerrados (`MembershipGateNotRegistered`). El doble `gate_doble` es una fixture opt-in de `tests/payments/conftest.py` que restaura el real. `MembershipPayability` gana `agreed_price_cop` por S3-D41.
- **D2:** aceptada. Grafo acíclico solo sobre aristas de nivel de módulo; perezosas validadas contra la lista blanca de la sección 0; el cambio de `test_service_import_graph.py` entra en **B1**; `ALLOWED_EDGES` crece slice a slice (B1: `memberships -> members/plans/settings`; B3: `payments -> members/auth/settings`; B4: `memberships -> payments`); `test_plans_no_agrega_aristas` se reescribe; cada `service.py` se importa en subproceso limpio en los dos órdenes.
- **D3:** aceptada con las adiciones de H-3 y L-1: orden único de candados (socio, `FOR SHARE` del plan, fila de membresía, fila de pago, cadena de auditoría por el hook); `core/locks.py: lock_member(session, member_id)` (S3-D54) y `memberships/sell.py: lock_membership(session, membership_id)` (S3-D59) como únicas puertas; `sell` dentro de `begin_nested()`; `sell(..., enforce_retroactive_limit: bool = True)` en lugar de `max_retroactive_days`; services con `get_actor()` y `current_clock()`, sin `by` ni `clock`; `principal.user_id`. `tests/memberships/test_lock_order.py` prueba las combinaciones con `lock_timeout` corto. `05_service_design.md` y `SPRINT-03.md` se corrigen en W0-1.
- **D4:** `first_payment: PaymentIn | None` reutiliza `payments.schemas.PaymentIn` (incluidos `confirm_overpayment` y `confirm_duplicate`); el `field` del 422 va con `prefix_field("first_payment", ...)`.
- **D5:** aceptada. Estado derivado en lectura con `compute_status(snapshot, today, expiring_days, freezes)` y `status_expr(today, expiring_days)` en SQL, con `test_status_expr_parity.py`. La columna `status` se escribe en cada transición; nada la lee salvo para `cancelled` y `pending_payment`.
- **D6:** sin `relationship()`; congelaciones por lote con `_load_freezes_for`.
- **D7:** aceptada. `memberships` y `payments` nacen partidos (`rules`, `events`, `sell`, `lifecycle`, `queries` / `rules`, `events`, `queries`) con `service.py` como fachada; `members` se parte en B9 paso 0 (`rules.py` extraído sin cambio de comportamiento, `detail.py` y `changes.py` nuevos). `PRIVATE_HELPERS` gana las tres entradas y la prueba de helpers privados se generaliza.
- **D8:** `daterange(start_date, end_date, '[]')` sobre `date`, restricción `ex_memberships_member_dates`, `WHERE status <> 'cancelled'`; 409 por código antes y la `EXCLUDE` como red (`violated_constraint` sobre `constraint_name`, SQLSTATE 23P01); riesgo Q1 de la `pending_payment` vieja aceptado (visible y anulable).
- **D9:** trigger `memberships.guard_identity()` en `0008`, ampliado por S3-D48 (`start_date`, `classes_total`, cancelada terminal) y acompañado de `memberships.forbid_delete()`.
- **D10:** `pending_payment` guardado y visible; chip con `// DESIGN-GAP:`.
- **D11:** activación por cobertura en `on_payment_registered` con `sum_not_voided` tras el `flush`; un pago sobre una pendiente ya vencida la deja `expired`.
- **D12 (corregida por H-1):** el sobrepago y el duplicado se confirman en el servidor: sin `confirm_overpayment` el API responde 409 `payment_exceeds_balance`; sin `confirm_duplicate`, 409 `payment_possible_duplicate` (S3-D41). Q5 sigue sin saldo a favor.
- **D13 (corregida por M-6):** `void` con el orden membresía, pago; trigger de `0011` con `CONSTRAINT = payments_immutable`, traducido a 409 `payment_already_voided`; los triggers nuevos van con `ENABLE ALWAYS` (S3-D49); la reversión conserva congelaciones y `end_date`.
- **D14:** aceptada: 422 para entrada mal formada (`frozen_to`, `freeze_too_retroactive`, `freeze_outside_validity`); **409** para `membership_not_freezable`, `freeze_already_scheduled`, `freeze_limit_reached`, `freeze_days_exceeded`, `overlaps_future_membership`. Sin `reason` en `FreezeIn` (`// DESIGN-GAP:`).
- **D15:** `classes_total = classes_remaining = class_count` al vender; nada descuenta clases hasta v0.4.
- **D16:** aceptada: fin inclusivo por N-23 (`start_date + duration_days`); el front dice "hasta el <fecha>" con `// DESIGN-GAP:`; "Precio pactado" de solo lectura.
- **D17 (corregida por M-7):** `amount_cop BIGINT CHECK BETWEEN 1 AND 1000000000` y `StrictInt`; `reference` `SafeText` de 1 a 64 **y** patrón `^[A-Za-z0-9][A-Za-z0-9 ._/#-]{0,63}$` (S3-D50); `void_reason` 1 a 500 y `cancel_reason` 5 a 500, ambos `SafeText`; referencia opcional en los tres medios.
- **D18:** lista de membresías con `status` separado por comas (`Query(max_length=100)`, L-9), `paid_cop` por `payments.sums_not_voided`, `q` por `members.search_ids(include_deleted=True)` con el límite de la cubeta compartida `members-search` (S3-D45), orden `end_date, id`.
- **D19 (corregida por M-1 y L-12):** `reveal` descifra con `types.reveal(socio, campo, "reveal")` y audita con `core.audit.record(action="reveal", table_name="members.members", after={"field": campo, "ip": client_ip}, subject_member_id=id)` en la misma transacción; sin `SensitiveFieldRevealed`; sin `commit()` explícito; límites `members-reveal` 30/min, `members-reveal-hour` 200/h, `members-reveal-day` 600/día (S3-D44).
- **D20:** la ficha descifra con propósito `mask` sin lote (`bus.batch` pondría `record_id = NULL`): una fila `decrypt` por campo no vacío con el `record_id` del socio.
- **D21 (corregida por M-3 y L-1):** `MemberPatch` cerrado (`first_name`, `last_name`, `sex`, `birth_date`, `phone`, `email`, `emergency_contact`, `document`, `document_type`, `data_consent`); `ensure_can_change(set_fields, role)` por **presencia** de `document` o `document_type`; `data_consent` solo `true` y sin reescribir la fecha; `deactivate` y `reactivate` toman `lock_member` (S3-D46, S3-D54). `test_no_physical_delete.py` reemplaza a `test_no_physical_delete_users.py`.
- **D22:** filtros `membership_status` y `plan_id` en `GET /members` con conjunto de ids por import perezoso y `any_`/`all_` (nunca `IN` expandido); `MemberRowOut.membership_end_date` nuevo; `status_for` por página.
- **D23:** `parse_month` y `month_bounds_utc` con `zoneinfo`; años 2020 a 2100 y aritmética de `(year, month)` (S3-D47).
- **D24:** sección `payment_methods` con códigos fijos `("cash", "nequi", "breb")`, etiquetas `SafeText` únicas sin distinguir mayúsculas y lectura tolerante (S3-D55).
- **D25:** `GET /payments/methods` responde `PaymentMethodsOut { items }`.
- **D26 (corregida por L-2 y M-8):** filtros de pagos de D26; `PaymentRow` agrega `backdated: bool` (`created_at - paid_at > 1 día`) y `GET /payments` acepta `backdated=true` (S3-D51); `registered_by_name` y `voided_by_name` son el correo parcial (`l•••@dominio`, S3-D57) hasta US-110.
- **D27 (corregida por H-2 y M-2):** 429 por ruta, nunca por router; `CON_LIMITE` gana `post /members/{member_id}/memberships` (`memberships-write`), `post /memberships/{membership_id}/freeze` (`memberships-write`), `post /memberships/{membership_id}/payments` (`payments-write`), `post /payments/{payment_id}/void` (`admin-write`), `post /memberships/{membership_id}/cancel` (`admin-write`), `get /memberships` y `get /payments` (`members-search`, solo con `q`), `get /members/{member_id}` (`members-detail`), `patch /members/{member_id}` (`members-write`), `post /members/{member_id}/reveal` (`members-reveal`). Los topes viven en `core/ratelimit.USER_LIMITS` (S3-D59).
- **D28:** rutas anidadas por socio en los routers de `memberships` y `payments`, con `q` real (`plans.service.search_ids` para membresías; referencia exacta para pagos).
- **D29:** marcador `perf`, fuera de los gates. `SPRINT-03.md` se corrige.
- **D30:** limpieza con `DISABLE TRIGGER USER` (sección 0), ampliada a las dos tablas de `memberships` por S3-D48.
- **D31, D32, D33, D34:** aceptadas sin cambio (listas sin cifrado; `auth.service.names_for` existe; `reloj` en 2026-10-21; `exceptions.py` por módulo y códigos en `errorCodes.ts`).
- **D35:** aceptada (compatibilidad del contrato entre B9 y F2 vía P-API paso 6).
- **D36:** `ENABLED_FEATURES` gana `memberships` en F3 y `payments` en F4; `routeTable` recibe `load` por slice; sin acciones nuevas en `permissions.ts`.
- **D37:** aceptada, todas con `// DESIGN-GAP:`; "Socios con él" de `Planes.html` queda para US-082 (Sprint 4A) y `BRECHAS.md` se corrige en W0-1.
- **D38:** aceptada; además `CLAUDE.md` gana `core/locks.py` en la estructura, la línea del 503 `busy` en Seguridad y `web/src/shared/data/` en la regla 5 del front.
- **D39:** `MemberCardList` sí se construye, con `useMembersInfinite` y `maxPages: 20` (S3-D52).
- **D40:** las pruebas ajenas que fijan el estado del Sprint 2 cambian en el slice que las rompe (sección 10).

### Decisiones de la revisión de seguridad del diseño (S3-D41 a S3-D59), con la opción final

- **S3-D41 (H-1):** `PaymentIn.confirm_overpayment` y `confirm_duplicate` (`StrictBool`, por defecto `False`, no se guardan); `register` bajo el candado de la membresía calcula `saldo = agreed_price_cop - sum_not_voided` y lanza 409 `payment_exceeds_balance` (`field="amount_cop"`) o 409 `payment_possible_duplicate` (mismo `membership_id`, `registered_by`, `amount_cop`, `method` y `reference` no anulado en los últimos 120 s); `sell` con `first_payment` compara con el precio del plan y no aplica el duplicado. Slices B3, B4, F3, F4.
- **S3-D42 (H-2):** cubetas por usuario `memberships-write` (30/min: `sell`, `renew`, `freeze`), `payments-write` (30/min: `register`), `admin-write` (30/min: `cancel`, `void`); `members-write` (60/min) sigue para `POST`/`PATCH /members`; `MAX_PAYMENTS_PER_MEMBERSHIP = 60` no anulados (409 `payment_limit_reached`). Las lecturas no consumen cupo de escritura. Slices W0-2 (helper), B1, B2, B3, B5, B6.
- **S3-D43 (H-3):** `Settings.DB_LOCK_TIMEOUT_MS=10000`, `DB_STATEMENT_TIMEOUT_MS=30000`, `DB_IDLE_IN_TX_TIMEOUT_MS=60000` pasan como `server_settings` de asyncpg en `create_engine_from`; `migrations/env.py` los anula con `SET LOCAL ... = 0` dentro de la transacción de migración; SQLSTATE 55P03, 57014 y 40P01 se traducen a 503 `busy` con `Retry-After: 1` (S3-D67); `tests/memberships/test_lock_order.py` cubre `sell`/`sell`, `sell`/`register`, `register`/`void`, `freeze`/`register`, `sell`/`cancel`, `sell`/`deactivate`; regla de arquitectura "ningún handler suscrito pide candados que el emisor no tenga" en `tests/architecture/test_handlers_no_new_locks.py` (AST: en `lifecycle.py` las funciones `on_*` no llaman a `lock_member` ni abren `with_for_update` sobre otra entidad). Excepción registrada a "no tocar `core/db.py` ni `core/errors.py`" del impacto: entran en el slice propio S3-W0-2.
- **S3-D44 (M-1):** tres ventanas de `reveal` por usuario y `logger.warning("reveal volume", extra={"user_id", "count"})` al superar el 50 % del cupo horario (`ratelimit.usage`); reiniciar el api vacía los cupos (aceptado, ya documentado en RUNBOOK §1). Slice B10.
- **S3-D45 (M-2):** `members-detail` 120/min en `GET /members/{member_id}`; `PII_SEARCH_BUCKET = "members-search"` compartida por los tres `GET` con `q` (socios, membresías, pagos), 60/min en conjunto. Slices B7, B8, B9.
- **S3-D46 (M-3):** `ensure_can_change` por presencia; `MemberPatch` cerrado; `data_consent` solo `true`, fija `data_consent_at` solo si estaba nula, `false` da 422; `emergency_contact.phone` con `SafeText`; `status`, `deleted_at` y `data_consent_at` nunca en el cuerpo. Slice B10.
- **S3-D47 (M-4):** `start_date <= hoy + 366` (422 `start_date_too_far`, salvo `renew`); `PAID_AT_FLOOR = 2020-01-01` para `paid_at`, `from`, `to`, `ends_from`, `ends_to`, con techo hoy + 5 años para los rangos; `parse_month` 2020 a 2100; ningún `datetime` extremo llega a 500. Slices B1, B3, B7, B8.
- **S3-D48 (M-5):** en `0008`, `guard_identity` rechaza cambiar `member_id`, `plan_id`, `agreed_price_cop`, `start_date`, `classes_total` y cualquier cambio sobre una fila `cancelled`; `memberships.forbid_delete()` `BEFORE DELETE OR TRUNCATE`; en `0009`, `membership_freezes` append-only (`BEFORE UPDATE OR DELETE OR TRUNCATE`). Limpieza de pruebas con `DISABLE TRIGGER USER` en las dos tablas. Slices B1, B2.
- **S3-D49 (M-6):** `ALTER TABLE ... ENABLE ALWAYS TRIGGER` en todos los triggers de `0008`, `0009` y `0011`, con prueba bajo `session_replication_role = replica`; `tests/architecture/test_no_trigger_tampering.py` prohíbe `DISABLE TRIGGER`, `session_replication_role`, `ALTER TABLE ... TRIGGER` y `TRUNCATE` en `app/` (nace en B1, S3-D69); separación de roles de base diferida a S4B-W0-2 (residual aceptado: el control es el trigger más el secreto de la base). Slices B1, B4.
- **S3-D50 (M-7):** patrón de comprobante en `reference`; avisos "No escribas teléfonos, documentos ni datos de salud" bajo referencia y motivos (F3, F4, F5); la auditoría inmutable conserva el texto (residual registrado; supresión en US-119). Slices B3, F3, F4, F5.
- **S3-D51 (M-8):** aceptada la desviación de N-27 por rol: `register(..., role)`; el coach solo registra `paid_at >= ahora - max_retroactive_days` (422 `paid_at_too_retroactive`); el admin sin límite salvo el piso de S3-D47; `PaymentRow.backdated` y filtro `backdated`; `logger.warning` (solo ids) al anular un pago de un mes anterior al actual en Bogotá. Slices B3, B5, B8.
- **S3-D52 (M-9):** `onReveal` hace `mutateAsync`, aplana y `mutation.reset()` antes de devolver; prueba de que `queryClient.getMutationCache().getAll()` no conserva el valor; `useUpdateMember`, `useSellMembership`, `useRegisterPayment`, `useVoidPayment`, `useFreezeMembership` y `useCancelMembership` hacen `reset()` en `onSettled`; `useMembersInfinite` con `maxPages: 20`. Slices F1 a F5.
- **S3-D53 (M-10):** `memberships.summary` se resuelve en SQL (`DISTINCT ON (member_id)` ordenado por la prioridad de US-092 sobre `status_expr`, `count(*) FILTER` por estado; cinco enteros) y se guarda en una caché de proceso de 30 s con clave `(hoy, expiring_days)` invalidada por `MembershipSold`, `MembershipActivated`, `MembershipActivationReverted`, `MembershipFrozen`, `MembershipCancelled`, `PaymentRegistered` y `PaymentVoided`; `resolve_member_status` queda como oráculo de la prueba de paridad. Detalle de `active_ids` en S3-D60. Slice B7.
- **S3-D54 (L-1):** `core/locks.py: lock_member` (B1); `deactivate` y `reactivate` lo toman (B10); prueba `sell` frente a `deactivate` con `dos_sesiones` (B10).
- **S3-D55 (L-3):** `payment_methods`: `label` y `hint` `SafeText`, etiquetas únicas sin distinguir mayúsculas (422 `field="value.<code>.label"`), `payment_methods()` tolera JSON con claves ajenas usando defaults. Slice B3.
- **S3-D56 (L-4, L-5, L-6, L-11):** `tests/architecture/test_sql_literals_constant.py` (todo `text(...)`, `literal_column(...)` y `execute(` de `app/modules` y `app/core` recibe constantes de cadena; valores ligados; fija `AUDIT_CHAIN_LOCK_KEY`, `MIGRATION_LOCK_KEY` y que `lock_member` use `hashtextextended`); `tests/architecture/test_guarded_calls.py` (`set_membership_gate(` solo en `memberships/service.py` y `tests/`; `enforce_retroactive_limit=` solo en `cli.py`, nunca en un `router.py`; ningún `isolation_level` en `create_async_engine` ni `execution_options`). Slices B1 (L-4, L-6, L-11) y B4 (L-5).
- **S3-D57 (L-2):** correo parcial en `registered_by_name` y `voided_by_name` con la pura `payments/rules.partial_email` hasta US-110. Slice B8.
- **S3-D58 (L-8):** volcado previo a `0011` con `-n payments -n memberships`, `chmod 600`, `*.sql.gz` en `.gitignore`, borrado al cierre (V12). P-MIG lo aplica a las cuatro migraciones.
- **S3-D59 (D-1 a D-5):** `core/ratelimit.USER_LIMITS` y `enforce_user_limit(bucket, user_id)` (W0-2); `core/security.StaffDep` y `AdminDep` (W0-2); `memberships/sell.lock_membership` única puerta de `with_for_update` sobre `Membership` (B1, prueba AST en `test_guarded_calls.py`); `members/detail._decrypt_fields` única llamada a `types.reveal` fuera de `core` (B9, prueba AST); `core/pagination.ID_BATCH = 200` y `chunked()` (W0-2) para `refs_for`, `_enrich`, `status_for` y `sums_not_voided`.

### Decisiones de este plan (lo que el orquestador no fijó; S3-D60 en adelante)

- **S3-D60 · `members.service.active_ids`.** Se crea en B7 como `active_ids(session) -> frozenset[UUID]` (una consulta de ids con `deleted_at IS NULL`, sin descifrar); `summary` la consume en lotes de `SUMMARY_ID_BATCH = 1000` con `member_id = ANY(:lote)` y suma los contadores de cada lote, así `memberships` nunca liga una lista sin tope en una sola sentencia y el conjunto está acotado por el padrón (1.000 socios, `01_product_discovery.md`). La caché de S3-D53 vive en `memberships/queries.py` (`SummaryCache`, TTL medido con `current_clock().now_utc()` para que `reloj.advance` la controle; `reset_summary_cache()` y `configure_summary_cache(ttl_s)`); la fixture autouse `sin_cache_de_resumen` de `tests/memberships/conftest.py` pone TTL 0 y restaura; `test_summary_cache.py` la prueba con TTL 30.
- **S3-D61 · `slice-gate.sh` no cambia.** El mapeo `<modulo>` y `web/<feature>` es genérico; `scripts/workflow/README.md` solo gana los ejemplos `memberships`, `payments`, `web/memberships` y `web/payments`, y la nota de que el Rojo crea los directorios antes del primer gate.
- **S3-D62 · Imágenes base por digest en W0-1.** `python:3.12-slim` (dos `FROM` de `api/Dockerfile`), `node:22-alpine` y `nginx:stable-alpine` (`web/Dockerfile`), `postgres:16` (`infra/compose.yml` y `compose.dev.yml`) y `nginx:stable-alpine` de `scripts/ci/test_nginx_conf.sh` van `imagen:tag@sha256:...` con la fecha y el comando de renovación en comentario (`docker buildx imagetools inspect <imagen:tag> --format '{{json .Manifest.Digest}}'`). Renovación manual al abrir cada sprint (sin Dependabot para Docker en este repo). `scripts/ci/test_images_pinned.sh` (grep puro, sin Docker) lo vigila en `run-gates.sh` y en el job `scripts` de CI. Digests de `postgres`, `nginx` y `node` del 22 de octubre ya están en DECISIONES (revisión de Fase 4, L3); el de `python:3.12-slim` se consulta al ejecutar W0-1.
- **S3-D63 · `npm audit` de desarrollo.** W0-1 actualiza `vitest`, `@vitest/coverage-v8`, `stylelint` y `stylelint-config-standard` (mayor permitida si el gate del front sigue verde) hasta `npm audit --audit-level=high` (todas las dependencias) en cero; el job `web` de CI gana un paso informativo `npm audit --audit-level=high` con `continue-on-error: true` (el gate sigue siendo el de producción, N-5), y `scripts/workflow/README.md` lo documenta. Si una mayor rompe la configuración y no se arregla dentro del slice, es un gate fallido: se detiene con opciones (regla de ejecución).
- **S3-D64 · `.env.seed` se borra.** W0-1 exporta `E2E_ADMIN_EMAIL` y `E2E_ADMIN_PASSWORD` a la shell de la sesión y borra el `.env.seed` local (CLAUDE.md: "se borra tras el primer seed"); el admin queda en el gestor de contraseñas del operador. Si la contraseña se pierde, `tools issue-reset-link <admin> --as <admin>` (RUNBOOK §2) emite un enlace de restablecimiento sin necesitarla. V3 toma las credenciales de la shell, nunca del archivo.
- **S3-D65 · Front sin cruces entre features (condición 8).** Tres mecanismos, y `boundaries.test.ts` no cambia: (1) los hooks y esquemas que comparten dos features viven en `web/src/shared/data/` (`members.ts`: `useMembersSearch`; `plans.ts`: `usePlans` se mueve desde `features/plans/api.ts`, que lo reexporta; `paymentMethods.ts`: `usePaymentMethods`; `memberships.ts`: `useMembershipSummary`, `useMemberMemberships`; `schemas/` con sus Zod); (2) las pestañas Membresías y Pagos de la ficha son rutas hijas (`/socios/:id/membresias`, `/socios/:id/pagos`) cuyo `load` apunta a `features/memberships/components/MemberMembershipsTab` y `features/payments/components/MemberPaymentsTab` y se montan por `<Outlet>` desde `MemberDetailPage` (`config/routeTable.ts` es quien cruza, no una feature); (3) `RegisterPaymentPanel` se monta una sola vez como `RegisterPaymentPanelHost` en `layouts/PanelLayout.tsx` (lazy, solo si `payments` está habilitada) y cualquier pantalla lo abre con la URL `?pago=<membership_id>` o `?pago=nuevo&socio=<member_id>` (`shared/lib/paymentPanel.ts`: `paymentPanelHref`, `readPaymentPanel`); `VoidPaymentModal` solo se usa dentro de `features/payments`. `MemberPaymentsTab` se mueve de `features/members` (blueprint) a `features/payments`.
- **S3-D66 · Orden de lanzamiento del front.** Conservan sus nombres, pero se ejecutan por disponibilidad del backend y dependencia entre sí: F3 (tras B6), F4 (tras B7), F5 (tras B7), F6 (tras B8), F2 (tras B9), F1 (tras B10), F7 (tras B11). `RegisterPaymentPanel` (F4) lista las membresías no canceladas del socio con `GET /memberships?member_id=&status=active,expiring,frozen,pending_payment` (B7, trae `paid_cop`), no con `GET /members/{id}/memberships` (B11), para no esperar al último slice.
- **S3-D67 · 503 `busy`.** `core/db.py` define `DatabaseBusy(DomainError)` (status 503, code `busy`, `Retry-After: 1`), `BUSY_SQLSTATES = {"55P03", "57014", "40P01"}`, `sqlstate_of(error)` y `translate_busy(error)`; `get_session` envuelve el `yield` en `except DBAPIError` y re-lanza `DatabaseBusy` cuando aplica, así `_handler_dominio` responde sin que `core/errors.py` importe SQLAlchemy. `_publicar_error_response` agrega `503` (con `ErrorResponse`) a toda operación con sesión, igual que hace con `500`; `responses_for` y su catálogo no cambian; `test_error_responses_in_openapi.py` exige `503` junto a `500`. `core/locks.py` también traduce a `DatabaseBusy` la espera agotada de `pg_advisory_xact_lock`.
- **S3-D68 · Sin `CHECK voided_at >= created_at` (L-10 parcial).** Se descarta: en pruebas `created_at` es `now()` del servidor y `voided_at` sale del `FrozenClock` (2026-10-21), y en producción `paid_at` admite +5 minutos, así que una anulación legítima podría fallar. Entran el resto de L-10: `SECURITY INVOKER` y `SET search_path = pg_catalog` en las cuatro funciones de trigger.
- **S3-D69 · Pruebas de arquitectura adelantadas.** `test_no_trigger_tampering.py` nace en B1 (el primer trigger es el de `0008`), no en B4; `tests/architecture/test_user_limits_catalog.py` (W0-2) exige que todo literal de `enforce_user_limit("...")` en un router sea clave de `USER_LIMITS`, que toda clave tenga al menos una ruta, y que el conjunto de rutas que llaman a `enforce_user_limit` sea exactamente `CON_LIMITE` menos las rutas de `auth` (que usan `rate_limit`).
- **S3-D70 · Nombres (L-7).** La excepción 409 `member_deactivated` se llama `MemberIsDeactivated`; el evento se llama `MemberDeactivated`. `tests/architecture/test_events_without_pii.py` (B10) exige que ningún `DomainEvent` declare campos `reference`, `reason`, `document`, `phone`, `email`, `name`, `value`, `first_name`, `last_name`.
- **S3-D71 · Rendimiento.** No se siembra con 10.000 socios: el volumen del producto es 1.000 (`01_product_discovery.md`) y el límite de parámetros de asyncpg se cubre con el caso de 5.000 ids de B9. Casos `perf`: B7 (1.000 socios y 3.000 membresías: `status=expiring` < 500 ms, `summary` < 300 ms), B8 (10.000 pagos, `limit=25` < 500 ms), B9 (5.000 ids en `any_` y el `EXPLAIN` de `test_list_perf.py` intacto). Se corren en su gate (sin `PYTEST_ADDOPTS`) y en V5.
- **S3-D72 · E2E.** Proyecto `stack` (`web/tests/e2e/stack/`, lo corre el job `e2e-stack`): `sell-with-payment.spec.ts` (F3), `payment-void.spec.ts` (F4), `member-detail.spec.ts` (F1: ficha, reveal, PATCH, baja y reactivación) y `members-mobile.spec.ts` (F2, a 390 px contra el stack). Proyecto `preview` (API simulada con `page.route`): `members-mobile.spec.ts` (F2, 60 socios, 390 × 844 y 320 × 640, axe) y `sell-with-payment.spec.ts` (F3). Idempotencia: documento aleatorio de 10 dígitos por corrida; cada spec limpia lo que crea solo por API de baja lógica.
- **S3-D73 · S3-B9 con dos checkpoints.** El paso 0 (extraer `members/rules.py` sin cambio de comportamiento) sella y confirma solo (`S3-B9a`), para que un fallo de la partición no se mezcle con los filtros y la ficha (`S3-B9b`).
- **S3-D74 · `register(..., role)` y el gate.** El rol llega al service como argumento del router (igual que `update` en D21); `GateDoble` de pruebas devuelve también `agreed_price_cop`.

### Contradicciones de contrato cerradas (condición 4; se corrigen en los desgloses en W0-1)

- **S3-C1:** `members.service.ref(member_id) -> MemberRef | None` no existe: es `get_ref(session, member_id) -> MemberRef`, lanza `MemberNotFound` y expone `is_deleted` (US-084, US-093).
- **S3-C2:** `members.service.active_ids()` no existía: nace en B7 como `frozenset[UUID]` (S3-D60) (US-092 T5).
- **S3-C3:** `bus.op_context(...)` no existe: la puerta es `core.crypto.types.reveal(obj, field, purpose)`; la ficha no usa `bus.batch` (D20) (US-073 T1, US-074 T1, US-077).
- **S3-C4:** `audit.record(table_name="members")` → `"members.members"` (US-074 T1).
- **S3-C5:** `Depends(get_session)`, `Depends(get_clock)`, `current_user.id` → `SessionDep`, `current_clock()`, `principal.user_id` (US-084 T8, US-095 T8 y otros).
- **S3-C6:** `Pagination`/`page: Pagination` → `PageParams`; `search_ids` devuelve `set[UUID]`, no `list` (US-091, US-093).
- **S3-C7:** `GET /payments/methods` como arreglo → objeto `{ items }` (US-056 T3/T4, README del desglose).
- **S3-C8:** `member.document.change` → `members.document.update`; `member.deactivate` → `members.delete` (US-075 T11, US-076).
- **S3-C9:** `test_service_import_cycles.py`, `test_payments_does_not_import_memberships.py` y `test_payments_dependencies.py` viven en `test_service_import_graph.py` (US-071, US-085, US-098).
- **S3-C10:** `MemberNotFound` no se duplica en `memberships/exceptions.py`: se importa de `members.exceptions` (US-084 T4).
- **S3-C11:** el router de `reveal` no hace `commit()` explícito: `SessionDep` confirma antes de enviar (US-074 T4).
- **S3-C12:** `compute_status(membership, today, expiring_days)` → cuatro argumentos, con `freezes` obligatorio (`SPRINT-03.md` S3-B1).
- **S3-C13:** `sell(..., max_retroactive_days)` → `sell(..., enforce_retroactive_limit=True)`; el service lee `memberships_policy` (`SPRINT-03.md` S3-B1, `05_service_design.md` línea de `sell`).
- **S3-C14:** `-m slow` → `-m perf` (`SPRINT-03.md` S3-B7 y "Validación del sprint", US-091 T8, US-098 T7).
- **S3-C15:** `Clock.now()` y `today_bogota()` de módulo no existen: `current_clock().now_utc()` y `current_clock().today_bogota()` (US-095).
- **S3-C16:** `SensitiveFieldRevealed` no existe ni se crea (D19); US-107 criterios 1 y 2 se cumplen con `audit.record` directo.
- **S3-C17:** `settings.service.payment_methods(session)` no existía: se crea en B3 con el estilo de `memberships_policy` (US-056, US-095).
- **S3-C18:** "notas" en la ficha (US-073 resumen): `notes` no existe desde M-5 del Sprint 2.
- **S3-C19:** `test_service_import_graph.py` falla desde B1, no desde B4 (`SPRINT-03.md` S3-B4).
- **S3-C20:** Wave 0 "sin infraestructura nueva" (`SPRINT-03.md`): tiene dos slices, W0-1 (digests, dependencias de desarrollo, `.env.seed`, docs) y W0-2 (tiempos de espera de la base, 503 `busy`, helpers de `core`).
- **S3-C21:** `MembershipPayability` lleva `agreed_price_cop` (US-095 T12).
- **S3-C22:** la demo del sprint (punto 2) dice "la pantalla pide confirmación": el API responde 409 `payment_exceeds_balance` sin `confirm_overpayment` y la pantalla reenvía con la confirmación.

## 2. Fixtures y utilidades de prueba compartidas

Cada una entra en el primer slice que la necesita (condición 5).

- **W0-2 (`tests/core`):** `motor_con_tiempos(settings)` en `tests/core/test_db_timeouts.py` (engine construido con `create_engine_from` sobre `TEST_DATABASE_URL` para leer `SHOW lock_timeout`); `app_rota` ya existe (`tests/core/_app_rota.py`) para el handler 503.
- **B1:**
  - `api/tests/factories/memberships.py`: `make_membership(session, member, plan, *, status="pending_payment", start=None, end=None, price=None, classes_remaining=None, **cambios) -> Membership` (calcula `start` con `reloj`, `end` con `compute_end_date`, inserta por ORM bajo `actor_scope(SYSTEM_USER_ID)` y confirma el savepoint como `make_plan`), `make_memberships(session, n, ...)` para `perf`; entrada en `FACTORIES`.
  - `tests/conftest.py`: `LIMPIAR_MEMBERSHIPS` (sección 0) en `LIMPIEZA_DE_SESION` y en el `finally` de `dos_sesiones`.
  - `tests/memberships/__init__.py`, `_apoyo.py` (`MEMBERSHIPS = "/api/v1/memberships"`, `cuerpo_venta(plan_id, **cambios)`, `CAMPOS_MEMBERSHIP` y `CAMPOS_SELL` como conjuntos exactos de claves, `leer_membresia(session, id)` y `leer_auditoria(session, table_name, record_id)` con SQL crudo, `contar_decrypt(session, record_id)`), `conftest.py` (`bus_confirmado` copiado de `tests/members/conftest.py`; `memberships_service` importado al nivel del módulo para que `restaurar_bus` conserve las suscripciones).
  - `tests/core/test_locks.py` usa `dos_sesiones` y `SET LOCAL lock_timeout = '200ms'` como `tests/plans/test_service_list.py:305`.
- **B2:** `make_freeze(session, membership, frozen_from, frozen_to) -> MembershipFreeze` (calcula `days`; no mueve `end_date`); `LIMPIAR_MEMBERSHIPS` borra primero las congelaciones.
- **B3:**
  - `api/tests/factories/payments.py`: `make_payment(session, membership, *, amount=None, method="cash", paid_at=None, voided=False, void_reason=None, reference=None, registered_by=None) -> Payment` (toma `member_id` de la membresía; inserta por ORM sin emitir eventos; `voided=True` es un `INSERT` legal para el trigger de B4); entrada en `FACTORIES`.
  - `tests/payments/__init__.py`, `_apoyo.py` (`PAYMENTS`, `cuerpo_pago(**cambios)`, `cuerpo_anulacion(reason)`, `CAMPOS_PAYMENT`, `CAMPOS_ROW`, `CAMPOS_DETAIL`, `leer_pago`), `conftest.py` (`GateDoble`: `dict[UUID, MembershipPayability]` con `__call__` async; fixture opt-in `gate_doble` que guarda `membership_gate()`, registra el doble y restaura al salir; `payments_service` importado al nivel del módulo).
  - `tests/conftest.py`: `LIMPIAR_PAYMENTS` (con `DISABLE TRIGGER USER` desde ya, aunque el trigger llegue en B4) antes de `LIMPIAR_MEMBERSHIPS`.
  - `tests/settings/_apoyo.py`: `payment_methods` sale de `NO_HABILITADAS` y entra en `RUTAS` (10 rutas tipadas).
- **B4:** nada nuevo; `gate_doble` deja de usarse en `test_router_register.py` y `test_gates_registered.py`.
- **B7:** `sin_cache_de_resumen` (autouse en `tests/memberships/conftest.py`, S3-D60); `contador_de_consultas(engine)` en `tests/conftest.py` (`before_cursor_execute` sobre la conexión síncrona; cuenta sentencias por tabla) para las aserciones "una consulta por servicio vecino por página" de B7, B8, B9 y B11.
- **B9:** `tests/members/_apoyo.py`: `CAMPOS_DETALLE` gana `plan_name` y `membership_end_date`; `CAMPOS_FILA` gana `membership_end_date`.
- **B10:** `tests/audit/test_reveal_entry.py` pasa a `make_member` (S2-D31).
- **Front:** `web/src/test/memberships.tsx` (fixtures `membershipRow`, `membershipOut`, `summary`) y `web/src/test/payments.tsx` (`paymentRow`, `paymentDetail`, `paymentMethods`) en F3 y F4; `web/tests/e2e/helpers/stack.ts` gana `crearSocio(page, admin) -> { id, documento }` y `venderMembresia(page, socioId, planId, pago?)` por API en F3; `documentoAleatorio()` para la idempotencia (S3-D72).

## 3. Paralelismo: cuándo lanzar cada slice de front

El backend corre en serie en la rama del sprint (W0-1, W0-2, B1 a B11). Un agente de front corre los siete slices en un worktree bajo `.claude/worktrees/`, con `SLICE_BASE` fijado a la base del worktree, en el orden de S3-D66. Antes de cada slice hace `git rebase feat/sprint-03-membresias-pagos` para traer `docs/openapi.json` y `web/src/core/api/types.ts`; nunca los regenera. El front no edita `docs/scratch/sprint-03.md`, `DECISIONES.md`, `CLAUDE.md` ni `BRECHAS.md` (usa `docs/scratch/sprint-03-front.md`); `docs/design/ROUTES.md` solo lo edita el front. Al cierre se fusiona en V1.

- **F3 (vender, primer pago y renovar):** tras el checkpoint de B6. Primer slice del worktree: crea `shared/data/`, `features/memberships/`, `features/payments/{api,schemas}.ts` mínimos, habilita `memberships`.
- **F4 (registrar y anular pagos, medios de pago):** tras B7 (necesita B3, B4, B5 y la lista de membresías por socio de B7). Habilita `payments`.
- **F5 (pantalla de membresías):** tras B7 (necesita B2, B6, B7). Puede ir antes que F4 si B7 cierra mientras F4 está en curso; el orden entre F4 y F5 es indiferente salvo por `?pago=`, que F5 solo enlaza.
- **F6 (pantalla de pagos):** tras B8.
- **F2 (filtros de la lista y vista móvil):** tras B9 (necesita B7 y B9).
- **F1 (ficha del socio):** tras B10 (necesita B9 y B10).
- **F7 (pestañas de la ficha):** tras B11 y F1.
- **E2E `stack`:** se corren en el slice si el backend ya existe en la rama fusionada del worktree; si no, en V4. Los `preview` se corren siempre en su slice.

## 4. Wave 0

### S3-W0-1 · Línea base, imágenes por digest, dependencias de desarrollo, `.env.seed` y documentación

- **Historias:** tareas DevOps de la deuda heredada (DECISIONES revisión de Fase 4 L3 y N-5; `sprint-02-verify-delivery.md` §9.3) y T-DOC de las condiciones 3, 4 y 10.
- **Cierra:** condición 4 (contradicciones), condición 10 (decisión sobre digests y dependencias), condición 3 (contratos fijados en los documentos), S3-D61 a S3-D64, L-8 (`.gitignore`), la deuda 9.3 de digests y de `npm audit`.
- **Depende de:** nada.
- **Migración:** ninguna.

**W0-1.1 · Línea base**
1. `$DC up -d --build`; esperar los cuatro servicios `healthy`; `$DC exec api alembic current` debe dar `0007_plans (head)`; `git status` limpio; `git worktree list` solo el principal.
2. `bash scripts/workflow/run-gates.sh` sobre `fe9eab0`: api `-m "not perf"` 1.987 ok y 4 saltadas esperadas, cobertura ≥ 95 %; web lint, tsc, pruebas con cobertura y build.
3. Crear `docs/scratch/sprint-03.md` con la línea base (conteos reales, HEAD, imágenes `apex-api:local` y `apex-web:local` con su id, puertos de `.env` solo por nombre).

**W0-1.2 · Documentación de contrato (T-DOC)**
- `docs/ddd/DECISIONES.md`: sección "Sprint 3" con el bloque de la sección 1 completo (D1 a D40 con opción, S3-D41 a S3-D74, S3-C1 a S3-C22).
- `docs/ddd/09_sprint_plan/SPRINT-03.md`: `-m perf` (dos sitios), `sell(..., enforce_retroactive_limit)`, `compute_status` con cuatro argumentos, `test_service_import_graph.py` desde S3-B1, Wave 0 con S3-W0-1 y S3-W0-2, 503 `busy` en Seguridad, `GET /payments/methods` como objeto, E2E en `tests/e2e/stack/` y `tests/e2e/`, demo con el texto corregido (S3-C22, 409 en la tercera congelación, `payments_immutable`), "Socios con él" fuera (US-082).
- `docs/ddd/05_service_design.md`: línea de `sell` (firma real, `enforce_retroactive_limit`, sin `by` ni `max_retroactive_days` desde el router), `reveal` con `types.reveal` + `audit.record`, `GET /payments/methods` objeto, `register(..., role)`, `MembershipPayability` con `agreed_price_cop`.
- `docs/ddd/03_context_map.md`: aristas de lectura `payments -> members`, `payments -> auth`, `payments -> settings`, `memberships -> payments` y la lista blanca de la sección 0.
- Desgloses en `docs/ddd/08_implementation_breakdown/`: US-084, US-093 (`get_ref`, `is_deleted`), US-092 (`active_ids`), US-073, US-074 (`types.reveal`, `members.members`, sin commit), US-091, US-093 (`PageParams`, `set[UUID]`), US-056 (`{items}`), US-075, US-076 (`members.document.update`, `members.delete`), US-095 (`now_utc`, `SessionDep`, `agreed_price_cop`, `role`, `confirm_*`), US-096 (sin `CHECK voided_at >= created_at`), US-071, US-085, US-098 (pruebas consolidadas), US-083 (`compute_status` 4 argumentos).
- `docs/BRECHAS.md`: sección 10 "Sprint 3": DESIGN-GAP previstos (D37), "Socios con él" a US-082, 409 de confirmación de sobrepago y duplicado, avisos de datos personales en motivos.
- `docs/RUNBOOK.md`: sección 7 "Imágenes base por digest y su renovación" (comando de S3-D62), sección 8 "Primer admin sin `.env.seed`" (S3-D64), y los esqueletos de las secciones 9 (tiempos de espera, W0-2), 10 (membresías y pagos: volcado previo a `0011`, restauración, cómo probar los triggers; se completan en B1 a B5).
- `scripts/workflow/README.md`: ejemplos `memberships`, `payments`, `web/memberships`, `web/payments` (S3-D61); `test_images_pinned.sh` en `run-gates.sh`; paso informativo de `npm audit` (S3-D63).
- Nota al inicio de `sprint-03-blueprint.md`: "corregido por `sprint-03-plan.md`, decisiones D3, D12, D13, D17, D19, D21, D26, D27 y S3-D60 a S3-D74".
- `CLAUDE.md`: `core/locks.py` en la estructura (B1 lo crea; se anota aquí para no tocar CLAUDE.md dos veces), línea "503 `busy` con `Retry-After: 1` cuando la base agota `lock_timeout`, `statement_timeout` o detecta un interbloqueo" en Seguridad, y en la regla 5 del front "los hooks y esquemas que comparten dos features viven en `web/src/shared/data/`".

**W0-1.3 · Rojo de infraestructura**
- Crear `scripts/ci/test_images_pinned.sh` (Bash, sin Docker): falla si algún `FROM` de `api/Dockerfile` o `web/Dockerfile`, algún `image:` de `infra/compose.yml` o `compose.dev.yml` distinto de `apex-*:local`, o la imagen de `scripts/ci/test_nginx_conf.sh` no lleva `@sha256:[0-9a-f]{64}`; y si el digest no va acompañado de un comentario con la fecha.
- `scripts/ci/test_compose_config.sh`: caso "postgres fijado por digest en los dos compose".
- `bash -n` de los scripts nuevos. Correr `test_images_pinned.sh`: debe fallar en cinco sitios.

**W0-1.4 · Verde de infraestructura (S3-D62)**
- `docker buildx imagetools inspect python:3.12-slim --format '{{json .Manifest.Digest}}'` y anotar; usar los digests de DECISIONES (L3) para `postgres:16`, `nginx:stable-alpine` y `node:22-alpine` (reconfirmarlos con el mismo comando).
- `api/Dockerfile` (dos `FROM`), `web/Dockerfile` (dos `FROM`), `infra/compose.yml`, `infra/compose.dev.yml`, `scripts/ci/test_nginx_conf.sh`: `imagen:tag@sha256:...` con comentario `# <fecha>; renovar: docker buildx imagetools inspect ...`.
- `scripts/workflow/run-gates.sh`: `test_images_pinned.sh` en la lista de scripts de infraestructura; `.github/workflows/ci.yml`, job `scripts`: ejecutarlo.
- `scripts/workflow/tests/run.sh` sigue verde (el gate de workflow no conoce `scripts/ci`).

**W0-1.5 · Dependencias de desarrollo del front (S3-D63)**
1. `cd web && npm audit --audit-level=high` (sin `--omit=dev`): anotar los 11 hallazgos de partida.
2. `npm install -D vitest@latest @vitest/coverage-v8@latest stylelint@latest stylelint-config-standard@latest`; si queda alguna transitiva (`tinypool`, `braces`, `micromatch`, `fast-glob`), `npm audit fix` sin `--force`; si persiste, `npm update <paquete>` con la versión mínima corregida.
3. `npm audit --audit-level=high` en cero; `npm run lint && npx tsc --noEmit && npm test -- --run --coverage && npm run build`; `npm run licenses`; `bash scripts/ci/notice.sh` si cambió la lista.
4. Ajustes de configuración que exija una mayor de vitest (`vitest.config.ts`, `web/src/test/setup.ts`, `tests/lint/stylelint.test.ts`): se hacen aquí, con sus pruebas verdes.
5. `.github/workflows/ci.yml`, job `web`: paso "auditoría de dependencias de desarrollo (informativo, S3-D63)" con `npm audit --audit-level=high` y `continue-on-error: true`, después del gate de producción.

**W0-1.6 · Entorno local y repositorio (S3-D58, S3-D64)**
- `.gitignore`: confirmar `*.dump` y agregar `*.sql.gz` bajo "Volcados de base de datos".
- `.env.seed` local: `export E2E_ADMIN_EMAIL=... E2E_ADMIN_PASSWORD=...` en la shell de la sesión (nunca al cuaderno) y `rm .env.seed`; anotar en el cuaderno que el admin vive en el gestor de contraseñas del operador y el camino de recuperación (RUNBOOK §8).
- `bash scripts/workflow/slice-gate.sh memberships` debe fallar con "módulo inexistente: api/src/app/modules/memberships" (prueba negativa de S3-D61; se anota).

**W0-1.7 · Docker**
1. `$DC build api web` (cambiaron los `Dockerfile`) y `$DC up -d`; los cuatro servicios `healthy`.
2. `$DC exec api alembic current` = `0007_plans (head)`.
3. `bash scripts/smoke/headers.sh` y `bash scripts/ci/web-smoke.sh` contra `http://localhost:8180`: 0 fallas.
4. `docker image inspect apex-api:local apex-web:local --format '{{.Id}} {{.Created}}'` al cuaderno.

**W0-1.8 · Gate**
1. `bash -n scripts/ci/*.sh scripts/smoke/*.sh scripts/workflow/*.sh`.
2. `bash scripts/ci/test_images_pinned.sh`; `bash scripts/ci/test_compose_config.sh`; `bash scripts/ci/test_nginx_conf.sh`.
3. `bash scripts/workflow/tests/run.sh`.
4. `cd web && npm run lint && npx tsc --noEmit && npm test -- --run --coverage && npm run build` (la actualización de vitest se valida con la suite completa, no con un gate parcial).
5. Al final, para sellar: `bash scripts/workflow/slice-gate.sh web/app tests/unit/playwright-config.test.ts tests/unit/dev-proxy.test.ts tests/unit/index-html.test.ts tests/lint/boundaries.test.ts`.

**W0-1.9 · Checkpoint**
`checkpoint-commit.sh "S3-W0-1 línea base, imágenes por digest, dependencias de desarrollo del front y decisiones del sprint"`. Incluye el bloque de `DECISIONES.md` y las correcciones de T-DOC.

### S3-W0-2 · Tiempos de espera de la base, 503 `busy` y helpers comunes de `core`

- **Historias:** H-3 (S3-D43, S3-D67), D-1, D-2, D-5 (S3-D59), parte de M-1 (`ratelimit.usage`, S3-D44).
- **Cierra:** H-3 (puntos 1 y 2), S3-D59 (helpers), S3-D69 (`test_user_limits_catalog`), condición 2 (helper de límite y alias de rol que todo router nuevo usa).
- **Depende de:** W0-1.
- **Migración:** ninguna. Toca `core/db.py`, `core/errors.py` (solo el gancho de OpenAPI), `core/config.py`, `core/ratelimit.py`, `core/security.py`, `core/pagination.py` y `migrations/env.py`: excepción a la lista "no tocar" del impacto, justificada en S3-D43 (una transacción detenida congela todas las escrituras auditadas; el sprint introduce la primera doble espera) y registrada en DECISIONES.

**W0-2.1 · Stubs**
- `core/config.py`: `DB_LOCK_TIMEOUT_MS: int = 10000`, `DB_STATEMENT_TIMEOUT_MS: int = 30000`, `DB_IDLE_IN_TX_TIMEOUT_MS: int = 60000` (`gt=0`).
- `core/db.py`: `BUSY_SQLSTATES`, `server_settings_from(settings) -> dict[str, str]`, `sqlstate_of(error) -> str | None` (lee `error.orig.sqlstate` de asyncpg), `class DatabaseBusy(DomainError)` (status 503, code `busy`, mensaje fijo "La base de datos está ocupada; intenta de nuevo en un momento.", `headers={"Retry-After": "1"}`), `translate_busy(error) -> DatabaseBusy | None`.
- `core/ratelimit.py`: `USER_LIMITS: Final[dict[str, tuple[int, int]]]` (`members-write` 60/60, `members-search` 60/60, `members-detail` 120/60, `members-reveal` 30/60, `members-reveal-hour` 200/3600, `members-reveal-day` 600/86400, `memberships-write` 30/60, `payments-write` 30/60, `admin-write` 30/60), `PII_SEARCH_BUCKET = "members-search"`, `async enforce_user_limit(bucket: str, user_id: UUID) -> None`, `async usage(bucket, key, *, window_s, kind="user") -> int`.
- `core/security.py`: `StaffDep = Annotated[Principal, Depends(require_role("admin", "coach"))]` y `AdminDep = Annotated[Principal, Depends(require_role("admin"))]`.
- `core/pagination.py`: `ID_BATCH: Final = 200` y `chunked(items: Sequence[T], size: int = ID_BATCH) -> Iterator[Sequence[T]]`.

**W0-2.2 · Rojo**
- `tests/core/test_db_timeouts.py`: `server_settings_from(settings)` da `{"lock_timeout": "10000ms", "statement_timeout": "30000ms", "idle_in_transaction_session_timeout": "60000ms"}`; un engine de `create_engine_from(settings con TEST_DATABASE_URL)` responde `SHOW lock_timeout` = `10s`; con `dos_sesiones` y `SET LOCAL lock_timeout = '200ms'`, un `SELECT ... FOR UPDATE` sobre una fila de `plans.plans` bloqueada por la otra sesión lanza `DBAPIError` con `sqlstate_of == "55P03"` y `translate_busy` devuelve `DatabaseBusy` con `Retry-After: 1`; `SELECT pg_sleep(1)` bajo `SET LOCAL statement_timeout = '100ms'` da `57014`; un `IntegrityError` cualquiera da `translate_busy is None`; `get_session` convierte el 55P03 en `DatabaseBusy` (sesión real contra `db_test`).
- `tests/core/test_errors_busy.py` (con `app_http` y `app_rota`): una ruta cuyo service lanza `DatabaseBusy` responde 503 con `{"error": {"code": "busy"}}`, `Retry-After: 1`, `Cache-Control: no-store`, sin traza en `caplog` a nivel `ERROR`; un `DBAPIError` con otro SQLSTATE sigue dando 500 `internal_error`.
- `tests/core/test_config.py`: las tres variables, defaults y `gt=0`; `tests/core/test_env_example.py`: las tres activas con sus valores.
- `tests/core/test_migrations.py`: nuevo caso `test_las_migraciones_anulan_los_tiempos_de_espera`: con `DB_STATEMENT_TIMEOUT_MS=1` en el entorno de `migrated_database`, `upgrade head` termina igual (el `SET LOCAL` de `env.py`).
- `tests/core/test_ratelimit.py`: `enforce_user_limit` usa `kind="user"` y el tope de `USER_LIMITS` (la llamada 31 de `memberships-write` da `TooManyRequestsError` con `retry_after`); un bucket desconocido lanza `KeyError` al importar (se valida en una prueba de `USER_LIMITS` cerrado); `usage` devuelve el conteo dentro de la ventana y 0 fuera; `PII_SEARCH_BUCKET == "members-search"`.
- `tests/core/test_require_role.py`: `StaffDep` deja pasar admin y coach y da 403 a `member`; `AdminDep` solo admin; `test_every_route_has_role` sigue viendo `require_role` en el árbol.
- `tests/core/test_pagination_chunks.py`: `chunked` con 0, 1, 200, 201 y 450 elementos; conserva el orden; `ID_BATCH == 200`.
- `tests/architecture/test_error_responses_in_openapi.py`: toda operación con rol declara `503` además de `500`; las públicas y `/health` no cambian.
- `tests/architecture/test_user_limits_catalog.py` (S3-D69): hoy solo `members/router.py` usa `enforce`; la prueba exige que ningún router llame a `ratelimit.enforce` directo con `kind="user"` (solo `enforce_user_limit`), que cada literal sea clave de `USER_LIMITS` y que el conjunto de rutas con `enforce_user_limit` sea `CON_LIMITE` menos las de `auth`. Falla porque `members/router.py` aún usa `enforce`.
- Confirmar el rojo con conteo.

**W0-2.3 · Verde**
- `core/db.py`: `create_engine_from` pasa `connect_args={"timeout": CONNECT_TIMEOUT_S, "server_settings": server_settings_from(settings)}`; `get_session` envuelve el `yield` en `try/except DBAPIError as error: busy = translate_busy(error); if busy: raise busy from error; raise`.
- `core/errors.py`: `_publicar_error_response` agrega `503` a toda operación que ya recibe `500` y tenga seguridad declarada; `MENSAJE_503` fijo. Sin otro cambio.
- `core/ratelimit.py`, `core/security.py`, `core/pagination.py`, `core/config.py`, `.env.example` (tres líneas activas con comentario "0 solo en migraciones e importación; el CLI de importación de US-112 los anula con `SET LOCAL`").
- `migrations/env.py`: en `run_migrations_online`, tras abrir la conexión y antes de `context.run_migrations()`, `connection.execute(text("SET LOCAL lock_timeout = 0")); ... statement_timeout = 0; ... idle_in_transaction_session_timeout = 0` dentro de la transacción (constantes; cumple L-4).
- `members/router.py`: las dos llamadas a `ratelimit.enforce` pasan a `enforce_user_limit("members-write", principal.user_id)` y `enforce_user_limit(PII_SEARCH_BUCKET, principal.user_id)`; `Staff` local se reemplaza por `StaffDep`; `plans/router.py` igual con `StaffDep` y `AdminDep`. Sin cambio de comportamiento (mismos topes).
- `tests/members/test_router_create.py` y `test_router_list.py` siguen verdes (regresión del 429).

**W0-2.4 · Documentación**
- `docs/RUNBOOK.md` sección 9: qué hace cada tiempo de espera, cómo ver un 503 `busy` en los logs (`code=busy`, sin traza), qué hacer si se repite (`pg_stat_activity` con `wait_event_type = 'Lock'`, `pg_terminate_backend` de la sesión de soporte), y que una importación larga va con `SET LOCAL ... = 0`.
- `DECISIONES.md`: ya anotado en W0-1 (S3-D43, S3-D67).

**W0-2.5 · Contrato**
P-API (el `503` entra en todas las operaciones con rol; `types.ts` cambia).

**W0-2.6 · Gate**
1. `slice-gate.sh core/config tests/core/test_config.py tests/core/test_env_example.py`.
2. `slice-gate.sh core/ratelimit tests/core/test_ratelimit.py`.
3. `slice-gate.sh core/security tests/core/test_require_role.py`.
4. `slice-gate.sh core/pagination tests/core/test_pagination_chunks.py tests/core/test_pagination_db.py`.
5. `slice-gate.sh core/errors tests/core/test_errors_busy.py tests/core/test_errors_router.py tests/core/test_errors_field.py`.
6. `slice-gate.sh members tests/members/test_router_create.py tests/members/test_router_list.py`; `slice-gate.sh plans tests/plans/test_router_create.py tests/plans/test_router_list.py`.
7. `slice-gate.sh architecture tests/core/test_migrations.py tests/architecture/test_error_responses_in_openapi.py tests/architecture/test_user_limits_catalog.py`.
8. Al final, para sellar: `slice-gate.sh core/db tests/core/test_db_timeouts.py tests/core/test_db.py tests/core/test_session_dependency.py`.

**W0-2.7 · Docker y evidencia**
1. `$DC up -d api` (lee `.env`; las variables tienen default, así que `.env` local no cambia). `$DC logs --tail 20 api` sin errores; `/api/v1/health` 200.
2. Demostración de H-3 por 8180: en una `psql` contra `apex-db-1`, `BEGIN; SELECT pg_advisory_xact_lock(4270002);` (el candado de la cadena de auditoría) y dejarla abierta; `POST /api/v1/members` con el admin debe responder **503 `busy`** con `Retry-After: 1` a los ~10 s; `ROLLBACK` en psql y repetir: 201. Anotar tiempos.
3. `$DC exec api alembic current` sigue en `0007_plans` (las migraciones corrieron con el `SET LOCAL`).

**W0-2.8 · Checkpoint**
`"S3-W0-2 tiempos de espera de la base, 503 busy y helpers de límite, rol y lotes"`.

## 5. Backend

Orden estricto: B1 → B2 → B3 → B4 → B5 → B6 → B7 → B8 → B9a → B9b → B10 → B11. El checkpoint de cada slice es la base del siguiente. Todo router nuevo: `APIRouter(tags=[...], dependencies=[Depends(no_store)], responses=responses_for(401, 403))`, rutas fijas antes que las de parámetro, `SessionDep`, `StaffDep`/`AdminDep`, `responses_for(...)` por ruta con 429 solo donde hay `enforce_user_limit`.

### S3-B1 · Reglas puras, vender, candados y la base de `memberships`

- **Historias:** US-083 y US-084.
- **Depende de:** W0-2.
- **Migración:** `0008_memberships` (`down_revision = "0007_plans"`).
- **Cierra:** condiciones 1 (pruebas de arquitectura del Sprint 2 y `env.py`), 5 (fábrica y limpieza de membresías), 6 (`memberships` nace partido), 9 (P-MIG y P-API); riesgos 3 (parcial), 4, 17, 20 y 21 de la exploración; H-2 (`memberships-write` en `sell`), H-3 punto 3 (primer caso de `test_lock_order`), M-4 (`start_date_too_far`), M-5 (`0008`), M-6 (`ENABLE ALWAYS` y `test_no_trigger_tampering`, S3-D69), L-1 (helper), L-4, L-6, L-10 (funciones), L-11, D-3 (`lock_membership`); S3-D2, S3-D8, S3-D9, S3-D47, S3-D48, S3-D54, S3-D56.

**B1.1 · Fábrica, limpieza y apoyos (sección 2, B1)**
`tests/factories/memberships.py`, `FACTORIES`, `LIMPIAR_MEMBERSHIPS` en `tests/conftest.py`, `tests/memberships/{__init__,_apoyo,conftest}.py`, `from app.modules.memberships import models` en `migrations/env.py`. Verificar que nada se rompió con `cd api && uv run pytest tests/members tests/plans -q`.

**B1.2 · Stubs**
- `api/src/app/modules/memberships/{__init__,models,rules,events,sell,lifecycle,queries,exceptions,schemas,router,service}.py` con firmas tipadas y `NotImplementedError`; `lifecycle.py` vacío salvo docstring; `service.py` fachada con `__all__`.
- `core/locks.py`: `MEMBER_LOCK_NAMESPACE: Final = 0` y `async lock_member(session, member_id) -> None` (`text("SELECT pg_advisory_xact_lock(hashtextextended(:m, 0))")` con `m=str(member_id)`; traduce 55P03 a `DatabaseBusy`).
- `memberships/sell.py`: `async lock_membership(session, membership_id) -> Membership | None` (`select(Membership).where(...).with_for_update().execution_options(populate_existing=True)`), única puerta de `with_for_update` sobre `Membership`.
- `main.py`: `MODULES = (..., "plans", "memberships")`.
- `tests/architecture/_imports.py`: `PRIVATE_HELPERS["memberships"] = frozenset({"rules", "events", "sell", "lifecycle", "queries"})`.

**B1.3 · Rojo de arquitectura (condición 1, D2, D40, S3-D56, S3-D69)**
- `tests/architecture/test_service_import_graph.py` reescrita (D2): `_grafo_real` separa aristas de nivel de módulo y perezosas; acíclico solo sobre las primeras; `ALLOWED_EDGES = {("audit","auth"), ("auth","settings"), ("memberships","members"), ("memberships","plans"), ("memberships","settings")}`; `LAZY_IMPORT_WHITELIST` igual a los tres pares de la sección 0 y una prueba de que toda perezosa real está en la lista (hoy ninguna); `test_plans_no_importa_services_y_solo_memberships_lo_importa`; importación en subproceso limpio (`python -I -c`) en los dos órdenes para cada par de `ALLOWED_EDGES`.
- `tests/architecture/test_audit_module.py`: `MODULES == ("auth","settings","audit","members","plans","memberships")` (B3 agrega `payments`).
- `tests/architecture/test_audited_tables.py`: `memberships.memberships` pasa de `PENDING_AUDITED` a `REQUIRED_AUDITED_TABLES_V01`; nueva prueba `test_membership_y_payment_declaran_sujeto` (por ahora solo `Membership.__audit_subject__ == "member_id"`); `PENDING_AUDITED` conserva `payments.payments`, `memberships.membership_freezes` (hasta B2), `classes.class_sessions` y `notifications.notifications`.
- `tests/architecture/test_no_cross_models.py`: la prueba de helpers privados se generaliza a todos los módulos de `PRIVATE_HELPERS`; caso nuevo: `memberships` no importa `members.models`, `plans.models` ni `settings.models`.
- `tests/migrations/test_0007_plans.py`: de "es head" a "está en la cadena hasta head".
- Nuevas: `tests/architecture/test_no_trigger_tampering.py` (ninguna cadena en `app/` contiene `DISABLE TRIGGER`, `session_replication_role`, `ALTER TABLE` seguido de `TRIGGER`, ni `TRUNCATE`; control con una fuente falsa que debe fallar); `tests/architecture/test_sql_literals_constant.py` (L-4: todo argumento de `text(`, `literal_column(` y `execute(` en `app/modules` y `app/core` es `ast.Constant`; `AUDIT_CHAIN_LOCK_KEY == 4_270_002`, `MIGRATION_LOCK_KEY == 4_270_001`; `core/locks.py` contiene `hashtextextended`); `tests/architecture/test_guarded_calls.py` (L-6: `enforce_retroactive_limit=` solo en `cli.py` y nunca en un `router.py`; L-11: ningún `isolation_level` en `create_async_engine` ni en `execution_options`; D-3: `with_for_update` sobre `Membership` solo en `memberships/sell.py::lock_membership`); `tests/architecture/test_handlers_no_new_locks.py` (S3-D43 punto 4: las funciones `on_*` de `memberships/lifecycle.py` no llaman a `lock_member` ni a `lock_membership` con un id distinto de `event.membership_id`; hoy no hay handlers y pasa vacía con `pytest.skip` prohibido: afirma la lista exacta de handlers, vacía en B1).

**B1.4 · Rojo de `memberships`**
- `tests/memberships/test_rules.py`: la matriz del blueprint B1 (`compute_end_date`, `compute_status` con `freezes` obligatorio, `covers`, `is_covered`, `next_start_for_renewal`, `classify_open`, `find_overlap`, inmutabilidad), más M-4: `validate_start_date(start, today, *, max_retroactive_days, max_ahead_days=366)` acepta hoy + 366 y rechaza hoy + 367 (`StartDateTooFar`) y hoy − 8 (`StartDateTooRetroactive`); `date(9999, 12, 31)` da `StartDateTooFar` y no `OverflowError`.
- `tests/memberships/test_sell_service.py`: los casos del blueprint B1 (venta por días con `reloj`, tiquetera, precio copiado, 404/422 de socio y plan, `membership_conflict` con `existing_id`, `membership_overlap` y 23P01 por SQL crudo, venta tras `expired`/`cancelled`, retroactividad, `enforce_retroactive_limit=False`, auditoría `insert` con `subject_member_id`, `MembershipSold` una vez, savepoint de D3, dos ventas simultáneas con `dos_sesiones`), más `start_date = hoy + 367` da 422 `start_date_too_far` y `hoy + 366` pasa; `first_payment` o `renew=True` lanzan `NotImplementedError` (hasta B4 y B6).
- `tests/memberships/test_sell_router.py`: casos del blueprint, más la venta 31 en un minuto del mismo usuario da 429 con `Retry-After` (`memberships-write`) y la 31 de otro usuario pasa; `responses` de la ruta incluyen 404, 409, 422, 429 y 503.
- `tests/memberships/test_refs_for.py`: por lote con `chunked`; sin ids no consulta; incluye dados de baja.
- `tests/memberships/test_lock_order.py` (H-3): `sell` frente a `sell` del mismo socio con `dos_sesiones` y `SET LOCAL lock_timeout = '2s'`: ninguna termina con 55P03 ni 40P01 (una gana, la otra 409); se parametriza por combinación y las demás llegan en B3 a B6 y B10.
- `tests/core/test_locks.py`: dos sesiones, la segunda espera; con `lock_timeout = '200ms'` la segunda recibe `DatabaseBusy`; la llave es la misma para el mismo UUID y distinta para otro.
- `tests/migrations/test_0008_memberships.py`: columnas y nulabilidad; cada CHECK con `INSERT` crudo (23514); `EXCLUDE` (23P01 solapados, adyacentes aceptados, canceladas ignoradas, otro socio ignorado); `guard_identity` (23000 con `CONSTRAINT = memberships_identity`) al cambiar `member_id`, `plan_id`, `agreed_price_cop`, `start_date`, `classes_total`, y al tocar `status`, `cancel_reason`, `cancelled_by` o `cancelled_at` de una `cancelled`; `forbid_delete` (`DELETE` y `TRUNCATE` rechazados con `CONSTRAINT = memberships_no_delete`); bajo `SET session_replication_role = replica` el `UPDATE` sigue rechazado (M-6); `pg_get_functiondef` de las dos funciones contiene `SECURITY INVOKER` y `search_path`; cuelga de `0007_plans`; ciclo.
- Confirmar el rojo con conteo y motivos.

**B1.5 · Migración**
`0008_memberships` por P-MIG: tabla, CHECKs e índices del blueprint B1; `ExcludeConstraint` `ex_memberships_member_dates`; funciones `memberships.guard_identity()` (D9 + S3-D48) y `memberships.forbid_delete()` (`plpgsql`, `SECURITY INVOKER`, `SET search_path = pg_catalog`, `RAISE ... USING ERRCODE = 'integrity_constraint_violation', CONSTRAINT = ...`); triggers `memberships_guard_identity BEFORE UPDATE FOR EACH ROW`, `memberships_forbid_delete BEFORE DELETE FOR EACH ROW`, `memberships_forbid_truncate BEFORE TRUNCATE FOR EACH STATEMENT`, cada uno con `ALTER TABLE memberships.memberships ENABLE ALWAYS TRIGGER <nombre>`; `downgrade`: tres triggers, dos funciones, índices, tabla (la `EXCLUDE` cae con la tabla); nunca el esquema ni `btree_gist`. SQL literal sin f-strings (S608).

**B1.6 · Verde**
- `models.py`, `rules.py` (incluye `validate_start_date`, `MAX_START_AHEAD_DAYS = 366`, `StartDateTooFar` como código `start_date_too_far`), `events.py` (`MembershipSold`), `exceptions.py` (del blueprint más `StartDateTooFar`), `schemas.py` (`SellMembershipIn` con `first_payment: None = None`), `sell.py` (`sell` con `begin_nested()`, `lock_member`, `get_ref`, `plans.get(for_share=True)`, política, `validate_start_date`, `effective` + `classify_open` + `find_overlap`, insert y `flush` con traducción de la `EXCLUDE`, `emit(MembershipSold)`; `get_payment_target`), `queries.py` (`refs_for`, `_load_freezes_for` devolviendo listas vacías hasta B2), `router.py` (`POST /members/{member_id}/memberships`, 201, `StaffDep`, `enforce_user_limit("memberships-write", principal.user_id)`, `responses_for(404, 409, 429)`), `service.py` fachada.
- `core/locks.py` real; `CLAUDE.md` ya lo lista (W0-1).

**B1.7 · Documentación**
`docs/RUNBOOK.md` sección 10: cómo comprobar la `EXCLUDE` y los triggers de `0008` con psql.

**B1.8 · Contrato**
P-API.

**B1.9 · Gate**
1. `slice-gate.sh core/locks tests/core/test_locks.py`.
2. `slice-gate.sh architecture tests/core/test_migrations.py tests/migrations/test_0008_memberships.py tests/migrations/test_0007_plans.py`.
3. Al final, para sellar: `slice-gate.sh memberships tests/memberships/test_rules.py tests/memberships/test_sell_service.py tests/memberships/test_sell_router.py tests/memberships/test_refs_for.py tests/memberships/test_lock_order.py` (arquitectura va incluida).

**B1.10 · Docker y evidencia**
1. Pasos 6 y 7 de P-MIG; `alembic current` = `0008_memberships (head)`.
2. Vender por 8180 (admin, el plan "Mensual" del Sprint 2, el socio de CC `1.020.304.417`): 201 `pending_payment`, `agreed_price_cop = 120000`.
3. psql: `SELECT status, start_date, end_date FROM memberships.memberships`; `SELECT action, subject_member_id FROM audit.audit_log WHERE table_name='memberships.memberships'` (una fila `insert`); `INSERT` crudo solapado → `23P01 ex_memberships_member_dates`; `UPDATE ... SET agreed_price_cop = 1` → `23000 memberships_identity`; `DELETE` → `memberships_no_delete`.

**B1.11 · Checkpoint**
`"S3-B1 reglas puras, vender, candados y migración 0008"`.

### S3-B2 · Congelar

- **Historias:** US-089.
- **Depende de:** B1.
- **Migración:** `0009_membership_freezes` (`down_revision = "0008_memberships"`).
- **Cierra:** riesgos 3 (congelada y extendida) y 17 de la exploración; H-2 (`memberships-write` en `freeze`); M-5 (`0009` append-only); L-10 (función); S3-D14, S3-D48.

**B2.1 · Fábrica y limpieza**
`make_freeze`; `LIMPIAR_MEMBERSHIPS` borra primero `membership_freezes` (con `DISABLE TRIGGER USER`); `test_0008_memberships.py` pasa a "está en la cadena".

**B2.2 · Stubs**
`MembershipFreeze` en `models.py`; `FreezeLimits`, `FreezeOutcome`, `FreezeError`, `apply_freeze` en `rules.py`; `MembershipFrozen` en `events.py`; `FreezeRejected`, `OverlapsFutureMembership` en `exceptions.py`; `FreezeIn`, `FreezeOut` en `schemas.py`; `freeze` en `lifecycle.py`; `_load_freezes_for` real en `queries.py`; ruta en `router.py`.

**B2.3 · Rojo**
- `tests/memberships/test_freeze_rules.py`: los casos del blueprint B2 (fin 2026-10-31 congelado 10 días desde hoy da 2026-11-10; ventana futura 2026-10-20 a 2026-10-24 corre a 2026-11-05 y sigue `active`; fronteras de Q9 en `max_retroactive_days` 7, `max_days` 30 y `max_count` 2; fechas invertidas; fuera de vigencia; ya programada; estados no congelables; sin mutación), más `frozen_to = 9999-12-31` da `freeze_days_exceeded` y no desborda.
- `tests/memberships/test_freeze_service.py`: casos del blueprint (estado `frozen` y fin extendido; futura deja `active`; límites de `settings` y por defecto; 409 `overlaps_future_membership` sin filas ni cambios; congelada y extendida junto a una futura contigua; segunda y tercera congelación; auditoría `insert` en `membership_freezes` y `update` en `memberships` con `subject_member_id`; `MembershipFrozen` una vez; 23P01 de la `EXCLUDE` de congelaciones por SQL crudo; dos congelaciones concurrentes con `dos_sesiones`).
- `tests/memberships/test_freeze_router.py`: 200 coach y admin; 403 `member`; 401; 404; 422 con `field="frozen_to"` y con cada código 422; 409 con cada código 409; la congelación 31 en un minuto da 429 (`memberships-write`, compartido con `sell`: 20 ventas más 11 congelaciones dan 429 en la 31).
- `tests/memberships/test_lock_order.py`: `freeze` frente a `sell` del mismo socio (la futura que la congelación podría solapar): sin 55P03 ni 40P01.
- `tests/migrations/test_0009_membership_freezes.py`: columnas, CHECKs (`dates_ordered`, `days_match`), `EXCLUDE` `ex_membership_freezes_dates`, FK a `memberships.memberships`, trigger `membership_freezes_append_only` (`UPDATE`, `DELETE` y `TRUNCATE` rechazados con `CONSTRAINT = membership_freezes_append_only`, también bajo `replica`), `pg_get_functiondef` con `SECURITY INVOKER`, ciclo.
- `tests/architecture/test_audited_tables.py`: `memberships.membership_freezes` pasa a requerida (sin `__audit_subject__`: anotado para US-106).
- `tests/architecture/test_handlers_no_new_locks.py`: la lista exacta de handlers sigue vacía.
- Confirmar el rojo.

**B2.4 · Migración**
`0009_membership_freezes` por P-MIG: tabla, CHECKs, `EXCLUDE`, índice `ix_membership_freezes_membership`, función `memberships.forbid_freeze_mutation()` y triggers `membership_freezes_append_only BEFORE UPDATE OR DELETE FOR EACH ROW` y `membership_freezes_forbid_truncate BEFORE TRUNCATE`, con `ENABLE ALWAYS`; `downgrade`: triggers, función, índice, tabla.

**B2.5 · Verde**
Según el blueprint B2: `apply_freeze` puro con el orden de validación de D14; `freeze(session, *, membership_id, frozen_from, frozen_to)`: leer sin candado para saber el socio, `lock_member`, `lock_membership`, 404, política, congelaciones, `apply_freeze` → `FreezeRejected`, `find_overlap` → `OverlapsFutureMembership`, insertar `MembershipFreeze`, `end_date` y `status = compute_status(...)`, `flush` con traducción de `ex_memberships_member_dates`, `emit(MembershipFrozen)`. `POST /memberships/{membership_id}/freeze` (200 `MembershipOut`, `StaffDep`, `enforce_user_limit("memberships-write", ...)`, `responses_for(404, 409, 422, 429)`). `sell` y `refs_for` pasan a usar `_load_freezes_for` real.

**B2.6 · Documentación**
RUNBOOK §10: congelaciones append-only.

**B2.7 · Contrato**
P-API.

**B2.8 · Gate**
1. `slice-gate.sh architecture tests/core/test_migrations.py tests/migrations/test_0009_membership_freezes.py tests/migrations/test_0008_memberships.py tests/architecture/test_audited_tables.py`.
2. Al final, para sellar: `slice-gate.sh memberships tests/memberships/test_freeze_rules.py tests/memberships/test_freeze_service.py tests/memberships/test_freeze_router.py tests/memberships/test_lock_order.py`.

**B2.9 · Docker y evidencia**
Pasos 6 y 7 de P-MIG; `alembic current` = `0009_membership_freezes (head)`. Por 8180: congelar 10 días la membresía de B1 (está `pending_payment`: 409 `membership_not_freezable`; se anota como evidencia de D14) y psql: `UPDATE memberships.membership_freezes SET days = 1` rechazado.

**B2.10 · Checkpoint**
`"S3-B2 congelar membresías y migración 0009"`.

### S3-B3 · Registrar pago, medios de pago y la base de `payments`

- **Historias:** US-095 y US-056.
- **Depende de:** B2 (orden de la cadena de migraciones). No depende del gate real (doble en `tests/payments/conftest.py`).
- **Migración:** `0010_payments` (`down_revision = "0009_membership_freezes"`).
- **Cierra:** condiciones 1 (`MODULES` final), 3 (`GET /payments/methods` objeto), 5 (fábrica y limpieza de pagos, doble del gate), 6 (`payments` partido), 7 (`NO_HABILITADAS`); riesgos 7, 8, 18 de la exploración; H-1 (regla en `register`), H-2 (`payments-write`, `MAX_PAYMENTS_PER_MEMBERSHIP`), M-4 (`PAID_AT_FLOOR`), M-7 (patrón de referencia), M-8 (`paid_at` por rol), L-3; S3-D1 (puerto), S3-D24, S3-D25, S3-D41, S3-D42, S3-D47, S3-D50, S3-D51, S3-D55, S3-D74.

**B3.1 · Fábrica, limpieza, apoyos y settings de prueba (sección 2, B3)**
`tests/factories/payments.py`, `FACTORIES`, `LIMPIAR_PAYMENTS`, `tests/payments/{__init__,_apoyo,conftest}.py`, `tests/settings/_apoyo.py` (`NO_HABILITADAS` sin `payment_methods`; `RUTAS` con las dos tipadas nuevas), `from app.modules.payments import models` en `migrations/env.py`. `pytest tests/settings -q` queda en rojo solo por `payment_methods` (lo cierra el Verde).

**B3.2 · Stubs**
- `api/src/app/modules/payments/{__init__,models,rules,events,queries,exceptions,schemas,router,service}.py`.
- `service.py`: `MembershipPayability(exists, cancelled, member_id, agreed_price_cop)`, `MembershipGate`, `set_membership_gate`, `membership_gate`, `MembershipGateNotRegistered`, `register(session, *, membership_id, amount_cop, method, reference, paid_at, confirm_overpayment=False, confirm_duplicate=False, role) -> PaymentOut`, `sum_not_voided`, `sums_not_voided`, `methods`.
- `rules.py`: `PAID_AT_FLOOR = datetime(2020, 1, 1, tzinfo=UTC)`, `PAID_AT_FUTURE_TOLERANCE = timedelta(minutes=5)`, `DUPLICATE_WINDOW = timedelta(seconds=120)`, `MAX_PAYMENTS_PER_MEMBERSHIP = 60`, `REFERENCE_PATTERN`, `validate_paid_at(paid_at, now, *, role, max_retroactive_days)`, `normalize_reference`, `check_balance(agreed_price_cop, paid_cop, amount_cop, *, confirmed) -> None`, `is_possible_duplicate(recent: Sequence[PaymentFingerprint], candidate: PaymentFingerprint, now) -> bool`, `check_payment_count(count, *, limit=MAX_PAYMENTS_PER_MEMBERSHIP)`.
- `settings/schemas.py`: `PAYMENT_METHOD_CODES`, `MethodLabel(label: SafeText 1..30, hint: SafeText 0..120)`, `PaymentMethodsSettings` (`extra="forbid"`, validador de etiquetas únicas sin mayúsculas), `PaymentMethodsSectionOut`, `PaymentMethodsPatchIn`, registro en `ENABLED_SECTIONS`, `SECTION_REGISTRY`, `SECTION_VIEWS`, `SECTION_DEFAULTS`; `settings/service.py`: `decorate_methods(codes, labels)` pura y `payment_methods(session)`; `settings/router.py`: `GET`/`PATCH /settings/payment_methods` tipadas antes de la genérica.
- `main.py`: `MODULES = (..., "memberships", "payments")`. `PRIVATE_HELPERS["payments"] = {"rules", "events", "queries"}`.

**B3.3 · Rojo**
- `tests/payments/test_rules.py`: `validate_paid_at` (ahora; +4 min 59 s; +5 min 1 s rechazado; sin zona; coach con `paid_at = ahora − 7 días` aceptado y `− 8 días` da `PaidAtTooRetroactive`; admin con `− 400 días` aceptado; `2019-12-31T23:59:59Z` rechazado para ambos; `0001-01-01T00:00:00+05:00` da 422 y no `OverflowError`); `normalize_reference` (espacios, vacío a `None`, 64 y 65); `REFERENCE_PATTERN` (`NEQ-00123`, `12/10 #4`, `A` pasan; `mi correo a@b.co`, `3001234567 mamá`, `ñ` y U+200B no); `check_balance` (igual, menor, mayor sin confirmar → `PaymentExceedsBalance`, mayor confirmado pasa, saldo cero y monto positivo sin confirmar → 409); `is_possible_duplicate` (igual en 119 s sí; 121 s no; distinto `reference` no; anulado no; otro `registered_by` no); `check_payment_count` (59 pasa, 60 lanza `PaymentLimitReached`); `PaymentIn` con montos 0, −1, 1, 120000, 120000.5, "120000", `true`, 1.000.000.001; medio `tarjeta`; `confirm_overpayment: "yes"` da 422; campo desconocido 422.
- `tests/payments/test_register.py` (con `gate_doble`): registro feliz (fila, `registered_by` y `created_by` del actor, `member_id` copiado del gate, `paid_at` por defecto con `reloj`, `confirm_*` no se guardan); membresía inexistente 404; cancelada 409 sin fila; expiradas y congeladas aceptadas (N-28); `PaymentRegistered` una vez con el monto; un handler que lanza revierte el pago; auditoría `insert` en `payments.payments` con `subject_member_id` y sin `confirm_*`; `sum_not_voided` y `sums_not_voided` con pagos vigentes y anulados de la fábrica; sin gate `MembershipGateNotRegistered` y cero filas (`set_membership_gate(None)` y restauración); autoflush (la suma ve el pago antes del evento); H-1: 60.000 sobre saldo 60.000 pasa, 60.001 da 409 `payment_exceeds_balance` con `field="amount_cop"` y con `confirm_overpayment=True` 201; dos registros iguales seguidos: el segundo 409 `payment_possible_duplicate`, con `confirm_duplicate=True` pasa, tras anular el primero (fábrica `voided=True`) no cuenta; con `dos_sesiones` dos pagos idénticos simultáneos: el candado del doble (`SELECT ... FOR UPDATE` del doble sobre una fila real de `memberships`) serializa y el segundo ve el primero; el pago 61 no anulado da 409 `payment_limit_reached` y uno anulado no cuenta; `role="coach"` con `paid_at` de hace 8 días da 422 `paid_at_too_retroactive` y `role="admin"` pasa.
- `tests/settings/test_payment_methods_rules.py`, `..._service.py`, `..._router.py`: `decorate_methods` con etiquetas por defecto y personalizadas en orden fijo aunque el JSON venga en otro orden; `validate_section` con `tarjeta` (`field: "value.tarjeta"`), sin `nequi`, `label` vacía (`value.cash.label`), `hint` de 121, `label` con U+200B (SafeText), dos etiquetas "Nequi"/"nequi" (`value.nequi.label`); `payment_methods(session)` con un JSON guardado a mano con clave `tarjeta` devuelve los tres con defaults y nunca `tarjeta`; coach 403 en `GET` y `PATCH`; `version_conflict` 409; guardar no cambia `payments.payments`.
- `tests/payments/test_payment_methods_router.py`: 200 a coach y admin con `items` de tres en orden, 403 `member`, 401, `Cache-Control: no-store`, forma de objeto.
- `tests/architecture/test_payment_method_codes.py` (D24): `settings.schemas.PAYMENT_METHOD_CODES`, el `Literal` de `payments.schemas`, `payments.models.PAYMENT_METHODS`, el CHECK del modelo y el texto de `0010_payments.py` coinciden.
- `tests/architecture/test_service_import_graph.py`: `ALLOWED_EDGES` gana `("payments","members")`, `("payments","auth")`, `("payments","settings")`; `payments` no importa `memberships` a ningún nivel todavía.
- `tests/architecture/test_audit_module.py` (tupla final) y `test_audited_tables.py` (`payments.payments` requerida con sujeto `member_id`).
- `tests/settings/test_settings_router.py` y `test_settings_rules.py`: la parametrización de `NO_HABILITADAS` ya no incluye `payment_methods` (cuatro secciones) y `test_settings_no_secrets.py` ve la sección nueva.
- `tests/migrations/test_0010_payments.py`: columnas, CHECKs (`amount_range`, `method`, `reference_length`, `void_reason_length`, `void_coherent`) con SQL crudo, tres índices, cuelga de `0009`, ciclo.
- `tests/memberships/test_lock_order.py`: `sell` frente a `register` sobre otra membresía del mismo socio (con `gate_doble` sobre filas reales): sin 55P03 ni 40P01.
- La prueba de router de `POST /memberships/{id}/payments` (`test_router_register.py`) va en B4 (gate real).
- Confirmar el rojo.

**B3.4 · Migración**
`0010_payments` por P-MIG: tabla con `member_id NOT NULL`, CHECKs, índices `ix_payments_paid_at (paid_at DESC)`, `ix_payments_membership_id`, `ix_payments_member_paid (member_id, paid_at DESC)`; sin FK entre esquemas; sin triggers (llegan en `0011`); `downgrade`: índices y tabla.

**B3.5 · Verde**
- `payments/`: `models.py` (`Payment` auditado con sujeto `member_id`, `PAYMENT_METHODS`, `MAX_AMOUNT_COP`), `schemas.py` (`PaymentIn` con `confirm_overpayment`, `confirm_duplicate`, `reference: SafeText | None` con `pattern`, `extra="forbid"`; `PaymentOut`; `PaymentMethodOut`; `PaymentMethodsOut`), `rules.py`, `events.py` (`PaymentRegistered(membership_id, payment_id, amount_cop)`, `PaymentVoided(membership_id, payment_id)`), `exceptions.py` (`PaymentError`, `PaymentMembershipNotFound` 404, `MembershipCancelled` 409, `PaidAtInFuture` 422 `field="paid_at"`, `PaidAtTooRetroactive` 422 `paid_at_too_retroactive`, `PaymentExceedsBalance` 409 `payment_exceeds_balance`, `PossibleDuplicatePayment` 409 `payment_possible_duplicate`, `PaymentLimitReached` 409 `payment_limit_reached`, `PaymentNotFound` 404, `MembershipGateNotRegistered(RuntimeError)`), `service.py` (`register`: gate → 404/409; `paid_at` por defecto `current_clock().now_utc()`; `validate_paid_at(..., role, max_retroactive_days=memberships_policy(session).max_retroactive_days)`; bajo el candado que tomó el gate: `sum_not_voided`, `check_balance`, conteo y `check_payment_count`, huellas de los últimos 120 s e `is_possible_duplicate`; crear `Payment(member_id=gate.member_id, registered_by=get_actor())`; `flush`; `emit(PaymentRegistered)`), `queries.py` (`sum_not_voided`, `sums_not_voided` con `chunked`, `_recent_fingerprints(session, membership_id, since)`, `count_not_voided`), `router.py` (`GET /payments/methods` con `StaffDep` y `responses_for()`; `POST /memberships/{membership_id}/payments` 201, `StaffDep`, `enforce_user_limit("payments-write", ...)`, `role=principal.role`, `responses_for(404, 409, 422, 429)`).
- Settings según B3.2 (`payment_methods()` tolerante: valida con `PaymentMethodsSettings.model_validate` y, si falla, cae a defaults con `logger.warning` de solo la clave).
- `main.py` con `MODULES` final.

**B3.6 · Documentación**
RUNBOOK §10: reglas del servidor para sobrepago, duplicado, tope de 60 y retroactividad por rol; `05_service_design.md` ya corregido en W0-1.

**B3.7 · Contrato**
P-API.

**B3.8 · Gate**
1. `slice-gate.sh settings tests/settings/test_payment_methods_rules.py tests/settings/test_payment_methods_service.py tests/settings/test_payment_methods_router.py tests/settings/test_settings_router.py tests/settings/test_settings_rules.py tests/architecture/test_payment_method_codes.py tests/architecture/test_settings_no_secrets.py`.
2. `slice-gate.sh architecture tests/core/test_migrations.py tests/migrations/test_0010_payments.py tests/migrations/test_0009_membership_freezes.py tests/architecture/test_audited_tables.py tests/architecture/test_audit_module.py`.
3. `slice-gate.sh memberships tests/memberships/test_lock_order.py`.
4. Al final, para sellar: `slice-gate.sh payments tests/payments/test_rules.py tests/payments/test_register.py tests/payments/test_payment_methods_router.py`.

**B3.9 · Docker y evidencia**
Pasos 6 y 7 de P-MIG; `alembic current` = `0010_payments (head)`. Por 8180: `GET /api/v1/payments/methods` con el coach → `{items: [cash, nequi, breb]}`; `PATCH /settings/payment_methods` con el admin cambia la etiqueta de `breb` a "Bre-B (Bancolombia)" y `GET /payments/methods` la refleja. `POST /memberships/{id}/payments` todavía no (sin gate real hasta B4): se anota.

**B3.10 · Checkpoint**
`"S3-B3 registrar pago, medios de pago y migración 0010"`.

### S3-B4 · Inmutabilidad, venta con primer pago y activación

- **Historias:** US-096, US-085 y US-086.
- **Depende de:** B3.
- **Migración:** `0011_payments_immutability` (`down_revision = "0010_payments"`), con volcado previo (P-MIG paso 1, S3-D58).
- **Cierra:** condiciones 5 (gate real y doble restaurable), 9 (`pg_dump` antes de `0011`); riesgos 1, 2, 5, 6 y 7 de la exploración; riesgos 1, 2 y 5 de `SPRINT-03.md`; H-1 (`sell` con `first_payment`), H-3 punto 3 (`register` frente a `void` llega en B5; aquí `sell` con pago frente a `register`), M-6 (`ENABLE ALWAYS` en `0011` y prueba de réplica), L-5 (AST de `set_membership_gate`), L-8 (volcado parcial), L-10 (función de `0011`); S3-D1, S3-D11, S3-D13, S3-D41 (`sell`), S3-D49, S3-D56 (L-5), S3-D58.

**B4.1 · Volcado y RUNBOOK**
P-MIG paso 1 con `-n payments -n memberships` a `docs/scratch/sprint-03-antes-0011_payments_immutability.dump`, `chmod 600`; RUNBOOK §10: restauración (`pg_restore --clean -n payments -n memberships`), `downgrade -1` no toca datos, cómo probar el trigger.

**B4.2 · Stubs**
- `payments/rules.py`: `can_void(payment) -> bool`; `payments/service.py`: `IMMUTABLE_CONSTRAINT = "payments_immutable"`.
- `memberships/schemas.py`: `SellMembershipIn.first_payment: PaymentIn | None = None` (D4).
- `memberships/sell.py`: `membership_payability(session, membership_id) -> MembershipPayability` (adaptador de `get_payment_target` + `agreed_price_cop`); rama `first_payment` de `sell`.
- `memberships/lifecycle.py`: `snapshot(row)`, `on_payment_registered(event, session)`; `events.py`: `MembershipActivated(membership_id, member_id, status)`.
- `memberships/service.py`: al final, `payments_service.set_membership_gate(membership_payability)` y `events.subscribe(PaymentRegistered, on_payment_registered)`.

**B4.3 · Rojo**
- `tests/payments/test_can_void.py`: vigente `True`, anulado `False`.
- `tests/payments/test_immutability.py` (SQL crudo con `SAVEPOINT` por caso y relectura): `DELETE` y `TRUNCATE` rechazados; `UPDATE` de cada columna protegida (`id`, `membership_id`, `member_id`, `amount_cop`, `method`, `reference`, `paid_at`, `registered_by`, `created_at`, `created_by`) rechazado, también si la misma sentencia llena las de anulación; anulación completa aceptada con `updated_at` cambiado y monto intacto; sin motivo, motivo de espacios, sin `voided_by` o sin `voided_at` rechazada (`incomplete_void`); segunda anulación rechazada (`already_voided`); `voided` de `true` a `false` rechazado; `UPDATE` sin cambios sobre un anulado rechazado; bajo `session_replication_role = replica` el `UPDATE` sigue rechazado (M-6); comparación con `information_schema.columns`: el conjunto de columnas de `payments.payments` es exactamente las 10 protegidas, las 4 de anulación y `updated_at` (US-096 T4); `pg_get_functiondef` con `SECURITY INVOKER` y `search_path`. Cada rechazo es `IntegrityError` con `violated_constraint == "payments_immutable"` y el motivo en el mensaje.
- `tests/payments/test_router_register.py` (gate real, sin `gate_doble`): 201 coach y admin; 403 `member`; 401; 422 con `field` de `amount_cop`, `method`, `reference` (patrón), `paid_at`; 404 y 409 (`membership_cancelled` llega en B6: aquí 409 `payment_exceeds_balance` y `payment_possible_duplicate` con envelope); montos enteros; el pago 31 en un minuto 429 (`payments-write`); `Cache-Control: no-store`.
- `tests/memberships/test_sell_with_payment_service.py`: casos del blueprint B4 (igual al precio → `active` en la respuesta; parcial → `pending_payment`; `paid_at` por defecto; atomicidad con handler o gate que lanza: cero filas en las tres tablas; dos `insert` con el mismo `user_id` y `subject_member_id`; `registered_by` del actor; 422 con `field="first_payment.amount_cop"` y `first_payment.paid_at`), más H-1: mayor al precio sin `confirm_overpayment` da 409 `payment_exceeds_balance` con `field="first_payment.amount_cop"` y cero filas; con `confirm_overpayment=True` da `active` sin filas extra; `confirm_duplicate` no aplica (dos ventas con pago a dos socios no chocan).
- `tests/memberships/test_activation_service.py` (bus real): casos del blueprint (60.000 + 60.000 → `active` y un solo `MembershipActivated`; el 2026-10-27 → `expiring`; 20.000 → `pending_payment` sin eventos; anulado no suma; pago sobre `active`/`expiring`/`frozen` no emite; congelación que contiene hoy → `frozen`; handler que lanza revierte pago y estado; auditoría `update` con `before.status`/`after.status` del usuario que pagó; dos pagos concurrentes de 60.000 con `dos_sesiones` terminan `active`).
- `tests/memberships/test_lock_order.py`: `sell` con `first_payment` frente a `register` sobre otra membresía del mismo socio: sin 55P03 ni 40P01.
- Arquitectura: `test_payments_immutability_code.py` (AST: en `app/modules/payments` no hay `session.delete(`, `delete(Payment)`, `update(Payment)` ni `TRUNCATE`; `voided`, `void_reason`, `voided_by`, `voided_at` solo se asignan dentro de `void`, que aún no existe: la prueba afirma "cero asignaciones fuera de `void`"), `test_gates_registered.py` (tras `create_app(settings_prueba, run_migrations_on_startup=False)` y tras `cli._load_module_services()`, `membership_gate() is memberships.service.membership_payability`; `register` sin gate falla cerrado y restaura), `test_service_import_graph.py` (`("memberships","payments")` en `ALLOWED_EDGES`; `payments` no importa `memberships` a nivel de módulo; importación limpia en los dos órdenes `memberships, payments` y `payments, memberships`), `test_guarded_calls.py` (L-5: `set_membership_gate(` solo en `memberships/service.py` y `tests/`), `test_handlers_no_new_locks.py` (lista exacta `["on_payment_registered"]`; el handler solo llama a `lock_membership(session, event.membership_id)`).
- `tests/migrations/test_0011_payments_immutability.py`: función y dos triggers existen con `tgenabled = 'A'` (ENABLE ALWAYS); ciclo `upgrade/downgrade` sin tocar filas (se cuentan antes y después); cuelga de `0010`.
- Confirmar el rojo.

**B4.4 · Migración**
`0011_payments_immutability` por P-MIG: función `payments.forbid_mutation()` (`plpgsql`, `SECURITY INVOKER`, `SET search_path = pg_catalog`, sin `EXCEPTION WHEN OTHERS`; ramas `delete`/`truncate` antes de leer `OLD`; `already_voided`; `column` con `IS DISTINCT FROM` sobre las 10 columnas; `incomplete_void`; `updated_at` libre; `RAISE ... USING ERRCODE = 'integrity_constraint_violation', CONSTRAINT = 'payments_immutable'`), triggers `payments_forbid_mutation BEFORE UPDATE OR DELETE FOR EACH ROW` y `payments_forbid_truncate BEFORE TRUNCATE FOR EACH STATEMENT`, `ENABLE ALWAYS` en ambos; `downgrade`: dos triggers y `DROP FUNCTION payments.forbid_mutation()`.

**B4.5 · Verde**
Según el blueprint B4 y S3-D41: `membership_payability` devuelve `MembershipPayability(exists, cancelled, member_id, agreed_price_cop)` de la fila bloqueada; `sell` con `first_payment` llama a `payments_service.register(...)` dentro del mismo `begin_nested()` después del `flush` y de `emit(MembershipSold)`, pasando `confirm_overpayment` y `role` del llamador (`sell(..., role)`), y re-lanza `PaymentError` con `prefix_field("first_payment", ...)`; la respuesta se arma con la fila tras el handler (`populate_existing`) y `first_payment_id`; `on_payment_registered` (D11) con `lock_membership(session, event.membership_id)` y `sums_not_voided`; `service.py` registra el gate y la suscripción; `router.py` de membresías pasa `role=principal.role`.

**B4.6 · Documentación**
RUNBOOK §10 completo (trigger, volcado, restauración); `.gitignore` ya cubre el volcado.

**B4.7 · Contrato**
P-API (`first_payment` en `SellMembershipIn`).

**B4.8 · Gate**
1. `slice-gate.sh architecture tests/core/test_migrations.py tests/migrations/test_0011_payments_immutability.py tests/migrations/test_0010_payments.py tests/architecture/test_gates_registered.py tests/architecture/test_payments_immutability_code.py`.
2. `slice-gate.sh payments tests/payments/test_can_void.py tests/payments/test_immutability.py tests/payments/test_router_register.py tests/payments/test_register.py`.
3. Al final, para sellar: `slice-gate.sh memberships tests/memberships/test_sell_with_payment_service.py tests/memberships/test_activation_service.py tests/memberships/test_sell_service.py tests/memberships/test_lock_order.py`.

**B4.9 · Docker y evidencia (demo 1 y 2)**
1. Pasos 6 y 7 de P-MIG; `alembic current` = `0011_payments_immutability (head)`.
2. Por 8180 con el admin: anular por psql la membresía de B1 no es posible (sin endpoint hasta B6): crear un socio nuevo y vender "Mensual" con `first_payment` de 120.000 en efectivo → 201 `active`, `paid_cop = 120000`, `first_payment_id`. psql: fila de `memberships`, fila de `payments` con `member_id` copiado, dos `insert` y un `update` en `audit.audit_log` con el mismo `subject_member_id`.
3. Otro socio: venta con 60.000 → `pending_payment`; `POST /memberships/{id}/payments` de 60.000 → `active`; un tercer pago de 1.000 sin `confirm_overpayment` → 409 `payment_exceeds_balance`; con `confirm_overpayment: true` → 201. Repetir el mismo pago en menos de 2 min → 409 `payment_possible_duplicate`.
4. psql: `UPDATE payments.payments SET amount_cop = 1` → `payments_immutable: column`; `DELETE` → `payments_immutable: delete`; `SET session_replication_role = replica; UPDATE ...` → rechazado.

**B4.10 · Checkpoint**
`"S3-B4 inmutabilidad de pagos (0011), venta con primer pago y activación por cobertura"`.

### S3-B5 · Anular pago y revertir la activación

- **Historias:** US-097 y US-087.
- **Depende de:** B4.
- **Migración:** ninguna.
- **Cierra:** demo 3; H-2 (`admin-write` en `void`), H-3 punto 3 (`register` frente a `void`), M-8 punto 3 (aviso de mes anterior), L-5 (anular un pago de una cancelada); S3-D13, S3-D42, S3-D51 (aviso).

**B5.1 · Stubs**
`payments/rules.py`: `normalize_void_reason`, `VOID_REASON_MAX = 500`, `is_previous_month(paid_at, today) -> bool`; `payments/exceptions.py`: `PaymentAlreadyVoided` (409), `InvalidVoidReason` (422, `field="reason"`); `payments/schemas.py`: `VoidPaymentIn(reason: SafeText)`; `payments/service.py`: `void(session, *, payment_id, reason) -> PaymentOut`; `memberships/rules.py`: `should_revert`; `memberships/lifecycle.py`: `on_payment_voided`; `memberships/events.py`: `MembershipActivationReverted(membership_id, member_id, previous_status)`; `memberships/service.py`: `events.subscribe(PaymentVoided, on_payment_voided)`; `payments/router.py`: `POST /payments/{payment_id}/void`.

**B5.2 · Rojo**
- `tests/payments/test_void_rules.py`: `normalize_void_reason` con "  Monto mal digitado  ", "", "   ", 500 y 501, NUL y U+200B (rechazados por `SafeText`); `is_previous_month` con `paid_at = 2026-09-30T23:30-05:00` y hoy 2026-10-21 (sí), `2026-10-01T04:59Z` (no: es el 30 de septiembre en Bogotá, sí), `2026-10-01T05:00Z` (no).
- `tests/payments/test_void.py`: casos del blueprint B5 (las cuatro columnas; monto, medio, referencia y `paid_at` intactos; doble anulación 409 sin cambios; inexistente 404; `PaymentVoided` una vez; handler que falla deja el pago sin anular; anular y registrar deja dos filas y `sum_not_voided` solo suma el nuevo; auditoría `update` con `before.voided`/`after.voided`, usuario y sujeto; `dos_sesiones` anulando el mismo pago: 200 y 409; un `UPDATE` hecho por SQL crudo antes también acaba en 409 por `IMMUTABLE_CONSTRAINT`), más: anular un pago cuya membresía está `cancelled` (fila de la fábrica con `status="cancelled"`) da 200 y no la reactiva (L-5); anular un pago de septiembre con `reloj` en octubre deja `logger.warning("void of previous month")` con solo ids en `caplog` (S3-D51), uno de octubre no.
- `tests/payments/test_router_void.py`: 200 admin; 403 coach y `member`; 401; 422 `field="reason"` (ausente, vacío, espacios, 501); 404; 409 con envelope; la anulación 31 en un minuto da 429 (`admin-write`); `no-store`.
- `tests/memberships/test_revert_activation_service.py` (bus real, con `payments.service.void`): casos del blueprint (único pago anulado → `pending_payment` y un `MembershipActivationReverted`; 120.000 + 20.000 anulando el de 20.000 sigue `active`; `expiring` → `pending_payment`; `frozen` → `pending_payment` con su congelación y `end_date` intactos y vuelve a `frozen` con un pago nuevo; `expired` efectivo y `cancelled` sin cambio; handler que lanza deja el pago sin anular; auditoría `update` del admin).
- `tests/memberships/test_lock_order.py`: `register` frente a `void` sobre la misma membresía: sin 55P03 ni 40P01.
- Arquitectura: `test_payments_immutability_code.py` (las cuatro columnas solo dentro de `void`), `test_handlers_no_new_locks.py` (lista exacta `["on_payment_registered", "on_payment_voided"]`), `test_error_codes_per_route.py` (`CON_LIMITE` gana `post /api/v1/payments/{payment_id}/void`, `post /api/v1/memberships/{membership_id}/payments`, `post /api/v1/members/{member_id}/memberships`, `post /api/v1/memberships/{membership_id}/freeze`; si B1 a B4 ya los agregaron, aquí solo el de `void`).
- Confirmar el rojo.

**B5.3 · Verde**
`void` con el orden de D13: leer sin candado (404), gate sobre `membership_id` (candado de la membresía por `membership_payability`), `select ... with_for_update()` del pago, `can_void` → 409, asignar las cuatro columnas (`voided_by = get_actor()`, `voided_at = current_clock().now_utc()`), `flush` con traducción de `IMMUTABLE_CONSTRAINT` a `PaymentAlreadyVoided`, `logger.warning` si `is_previous_month`, `emit(PaymentVoided)`. `on_payment_voided` (D13): `lock_membership`, estado efectivo, `should_revert` → `pending_payment` conservando congelaciones y `end_date`; `expired`/`cancelled` sin cambio. Ruta `POST /payments/{payment_id}/void` (200 `PaymentOut`, `AdminDep`, `enforce_user_limit("admin-write", ...)`, `responses_for(404, 409, 422, 429)`).

**B5.4 · Contrato**
P-API.

**B5.5 · Gate**
1. `slice-gate.sh memberships tests/memberships/test_revert_activation_service.py tests/memberships/test_lock_order.py`.
2. Al final, para sellar: `slice-gate.sh payments tests/payments/test_void_rules.py tests/payments/test_void.py tests/payments/test_router_void.py tests/payments/test_immutability.py`.

**B5.6 · Docker y evidencia (demo 3)**
Por 8180, admin: anular el segundo pago del socio de B4.9 punto 3 con motivo "Monto mal digitado" → 200 `voided = true`; `GET /memberships/{id}` (llega en B7: hasta entonces psql) muestra `pending_payment`; anular de nuevo → 409 `payment_already_voided`; psql: `UPDATE payments.payments SET amount_cop = 1 WHERE id = <anulado>` → `payments_immutable: already_voided`.

**B5.7 · Checkpoint**
`"S3-B5 anular pago y revertir la activación"`.

### S3-B6 · Renovar y anular membresía

- **Historias:** US-088 y US-090.
- **Depende de:** B4 (renovar con primer pago) y B2 (renovar con congelada).
- **Migración:** ninguna.
- **Cierra:** demo 4 y 5; riesgo 3 de `SPRINT-03.md` (renovación anticipada frente a la `EXCLUDE`); H-2 (`memberships-write` en `renew`, `admin-write` en `cancel`), H-3 punto 3 (`sell` frente a `cancel`); S3-D8 (renovación), S3-D42.

**B6.1 · Stubs**
`memberships/sell.py`: rama `renew=True` y `renewal_preview(session, *, member_id, plan_id) -> RenewalPreviewOut`; `memberships/lifecycle.py`: `cancel(session, *, membership_id, reason) -> MembershipOut`; `memberships/rules.py`: `normalize_cancel_reason`, `plan_renewal`; `memberships/schemas.py`: `CancelMembershipIn(reason: SafeText)`, `RenewalPreviewOut(start_date, end_date, agreed_price_cop, current_end_date)`; `memberships/exceptions.py`: `FutureMembershipExists` (409, `existing_id`), `MembershipAlreadyCancelled` (409), `CancelReasonInvalid` (422, `field="reason"`); `memberships/events.py`: `MembershipCancelled(membership_id, member_id, reason_len)`; rutas `GET /members/{member_id}/memberships/renewal-preview?plan_id=` y `POST /memberships/{membership_id}/cancel`.

**B6.2 · Rojo**
- `tests/memberships/test_renew_service.py` (`reloj` 2026-10-21): casos del blueprint B6 (vigente hasta 2026-10-28 → inicio 2026-10-29 y fin 2026-11-28 `pending_payment`, la vigente intacta y sin auditoría nueva; vencida → inicio hoy; renovar con pago completo → futura `active` con `start_date > hoy`; futura existente → 409 `future_membership_exists` con `existing_id`; `start_date` enviado se ignora; plan distinto e inactivo; vigente congelada (fin extendido); cancelada entre las dos; vista previa igual a lo que crea `sell` y sin filas; carrera de dos renovaciones con `dos_sesiones`), más: `renew=True` no aplica `start_date_too_far` ni el límite retroactivo; el primer pago de la renovación mayor al precio sin confirmación → 409 `payment_exceeds_balance`.
- `tests/memberships/test_renew_router.py`: 201; 409 `future_membership_exists`; 403 `member`; 401; 429 en la escritura 31 (`memberships-write`); vista previa 200, 404, 409, 422 por `plan_id` ausente o no UUID, sin límite (lectura).
- `tests/memberships/test_cancel_service.py`: casos del blueprint (anular desde cada estado; pagos intactos por SQL crudo y sin auditoría de `payments`; segunda anulación 409; motivo corto 422 sin cambios; tras anular, `sell` con las mismas fechas da 201; registrar un pago contra la cancelada da 409 `membership_cancelled` por el gate real; un `PaymentVoided` posterior no la reactiva; auditoría `update` con sujeto; `MembershipCancelled` una vez con `reason_len` y sin el texto), más: `guard_identity` impide que un `UPDATE` crudo reviva la cancelada (23000, S3-D48) y `cancel` sobre una `frozen` conserva la fila de `membership_freezes`.
- `tests/memberships/test_cancel_router.py`: 200 admin; 403 coach y `member`; 401; 404; 409; 422 `field="reason"` (4 caracteres, 501, NUL); 429 en la 31 (`admin-write`, compartido con `void`).
- `tests/memberships/test_lock_order.py`: `sell` frente a `cancel` del mismo socio: sin 55P03 ni 40P01.
- Arquitectura: `test_error_codes_per_route.py` (`CON_LIMITE` gana `post /api/v1/memberships/{membership_id}/cancel`), `test_events_without_pii.py` nace aquí si no lo hizo B5 (ningún evento con `reason`, `reference`, ...; `MembershipCancelled.reason_len` pasa).
- Confirmar el rojo.

**B6.3 · Verde**
Según el blueprint B6: `renew=True` bajo `lock_member`, `FutureMembershipExists`, `plan_renewal(vigente_o_None, plan, price_cop, hoy)`, mismas validaciones y mismo primer pago, `MembershipSold(renewal=True)`; `renewal_preview` comparte validaciones, no escribe y no toma candado; `cancel` con `lock_membership`, 404, `MembershipAlreadyCancelled`, `normalize_cancel_reason`, `status = "cancelled"` y los tres campos, `emit(MembershipCancelled)`, sin tocar pagos ni congelaciones. Rutas: vista previa (`StaffDep`, `responses_for(404, 409, 422)`), `cancel` (`AdminDep`, `enforce_user_limit("admin-write", ...)`, `responses_for(404, 409, 422, 429)`).

**B6.4 · Contrato**
P-API.

**B6.5 · Gate**
Para sellar: `slice-gate.sh memberships tests/memberships/test_renew_service.py tests/memberships/test_renew_router.py tests/memberships/test_cancel_service.py tests/memberships/test_cancel_router.py tests/memberships/test_lock_order.py tests/memberships/test_sell_service.py`.

**B6.6 · Docker y evidencia (demo 4 y 5)**
Por 8180: vista previa de renovación del socio `active` de B4.9 → inicio = fin + 1; renovar con `renew: true` → 201 `pending_payment` futura; intentar vender otra sin `renew` con `start_date` dentro de la vigente → 409 `membership_overlap`; psql `INSERT` crudo solapado → 23P01. Anular por el admin la membresía `pending_payment` de B1 con motivo → 200; `POST /memberships/{id}/payments` sobre ella → 409 `membership_cancelled`; psql `UPDATE ... SET status='active' WHERE status='cancelled'` → `memberships_identity`.

**B6.7 · Checkpoint**
`"S3-B6 renovar y anular membresía"`.

### S3-B7 · Listar membresías, resumen y consultas de estado

- **Historias:** US-091 y US-092.
- **Depende de:** B3 (`sums_not_voided`) y B6 (estados de origen completos).
- **Migración:** ninguna.
- **Cierra:** condición 3 (`perf`), condición 4 (`active_ids`); riesgos 1 (estado efectivo), 10 (parcial: `member_ids_by_status`) y 22 de la exploración; riesgo 4 del blueprint; M-2 (cubeta compartida en membresías), M-4 (`ends_*`), M-10, L-9; S3-D5, S3-D18, S3-D45, S3-D47, S3-D53, S3-D60, S3-D71 (`perf` de membresías).

**B7.1 · Fixtures**
`sin_cache_de_resumen` (autouse en `tests/memberships/conftest.py`) y `contador_de_consultas` en `tests/conftest.py` (sección 2).

**B7.2 · Stubs**
`members/service.py`: `active_ids(session) -> frozenset[UUID]` (antes de la partición de B9; va en `__all__`); `memberships/rules.py`: `parse_status_filter`, `resolve_member_status`, `resolve_member_membership`, `MEMBER_STATUS_PRIORITY`; `memberships/queries.py`: `status_expr(today, expiring_days)`, `member_status_rank_expr(...)` (el `CASE` de prioridad para `DISTINCT ON`), `list(...)`, `get(...)`, `summary(session, *, today=None)`, `SummaryCache`, `reset_summary_cache`, `configure_summary_cache`, `SUMMARY_ID_BATCH = 1000`, `status_for`, `member_ids_by_status`, `count_active_by_plan`; `memberships/schemas.py`: `MembershipRow`, `MembershipSummaryOut`, `MemberMembership`, `MembershipListQuery` (`status: str | None` con `max_length=100`, `q`, `plan_id: UUID | None`, `ends_from`, `ends_to`, `member_id: UUID | None`); `memberships/exceptions.py`: `StatusFilterInvalid` (422, `field="status"`), `DateRangeInvalid` (422, `field="ends_to"`); rutas `GET /memberships/summary`, `GET /memberships`, `GET /memberships/{membership_id}`; suscripciones de invalidación de la caché al final de `service.py`.

**B7.3 · Rojo**
- `tests/memberships/test_rules.py` (ampliado): `parse_status_filter` (coma, sin repetidos, desconocido → `StatusFilterInvalid`, cadena vacía → `None`); `resolve_member_status` con los nueve casos de US-092.
- `tests/memberships/test_status_expr_parity.py`: malla de fechas (fin − 9 a fin + 2), `expiring_days` 0, 3 y 7, con y sin congelación que contiene hoy, `classes_remaining` 0, `pending_payment`, `cancelled`: el `CASE` ejecutado en PostgreSQL y `compute_status` coinciden en cada punto; y la prioridad `DISTINCT ON` coincide con `resolve_member_status` sobre los nueve casos de US-092 sembrados con la fábrica (S3-D53).
- `tests/memberships/test_list_service.py`: casos del blueprint B7 (filtro `expiring` y rango de fin; `pending_payment`; `plan_id` y `member_id`; `q` por apellido y documento con socios reales; `q` sin coincidencias; dados de baja incluidos; nombres, congelaciones y sumas por lote con `contador_de_consultas`: una consulta por servicio vecino por página; `total` con `offset`; `paid_cop` ignora anulados; cero `decrypt`), más M-4: `ends_from = 2019-12-31` da 422 `field="ends_from"`, `ends_to = hoy + 6 años` da 422 `field="ends_to"`, rango invertido 422; `status` de 101 caracteres da 422.
- `tests/memberships/test_list_perf.py` (`@pytest.mark.perf`): 1.000 socios y 3.000 membresías con `make_memberships`; `status=expiring` en menos de 500 ms; `summary` sin caché en menos de 300 ms.
- `tests/memberships/test_list_router.py`: 200 `{items,total,limit,offset}`; `limit` 0 y 201 → 422; `status=vigente` → 422 `field="status"`; rango invertido 422; detalle 404 y 422 por UUID; 403 `member`; 401; con `q`, la búsqueda 61 en un minuto da 429 y 40 búsquedas aquí más 21 en `GET /members?q=` del mismo usuario dan 429 en la 61 (M-2, cubeta compartida); sin `q` no consume.
- `tests/memberships/test_status_queries_service.py`: casos del blueprint (10/4/4/1/2 socios por estado; `status_for` con uno sin membresías; `status_for` de 200 ids emite una sola consulta; `member_ids_by_status({"expiring"}, plan_id)`; `count_active_by_plan` = 3; un dado de baja no entra al resumen; una `active` guardada vencida cuenta `expired` sin job), más: `active_ids` devuelve `frozenset` y excluye dados de baja; `summary` con 2.500 socios vivos emite tres sentencias (lotes de 1.000) y suma igual que una sola.
- `tests/memberships/test_summary_cache.py` (TTL 30 con `reloj`): dos llamadas seguidas dan una sola consulta; `reloj.advance(seconds=31)` vuelve a consultar; cada uno de los siete eventos (emitidos con `events.emit` sobre la sesión) invalida; la clave cambia con `expiring_days`; `reset_summary_cache()` limpia.
- `tests/memberships/test_summary_router.py`: 200 con cinco enteros; 403 `member`; 401; `/memberships/summary` no cae en `{membership_id}`.
- Arquitectura: `tests/architecture/test_no_cross_schema_sql.py` (por `ast`, en `app/modules/*` salvo `audit` ninguna cadena de `text(...)` ni literal con `FROM`/`JOIN` nombra `members.`, `plans.`, `memberships.`, `payments.`, `auth.`, `settings.` de otro módulo; control con fuente falsa), `test_error_codes_per_route.py` (`CON_LIMITE` gana `get /api/v1/memberships`), `test_list_routes_use_page_params.py` (conjunto esperado gana `GET /api/v1/memberships`), `test_handlers_no_new_locks.py` (los handlers de invalidación de caché no tocan la sesión: lista exacta ampliada).
- Confirmar el rojo.

**B7.4 · Verde**
Según el blueprint B7 y S3-D53/S3-D60: `status_expr` con `case(...)`, `literal(today, Date)` y `exists()` sobre `membership_freezes`; `list` pagina `select(Membership)` con `status_expr(...).in_(statuses)`, excluye `cancelled` sin filtro, `q` con `members.search_ids(include_deleted=True)` y `any_`, orden `end_date, id`, enriquecimiento con `chunked`; `summary` con `DISTINCT ON (member_id)` ordenado por `member_status_rank_expr` y `count(*) FILTER` por estado, por lotes de `active_ids`, y `SummaryCache` (TTL 30 s, reloj de la app) invalidada por los siete eventos (suscripciones `_invalidate_summary(event, session)` sin tocar la sesión); `status_for`, `member_ids_by_status`, `count_active_by_plan` con el estado efectivo; rutas con `StaffDep`, `GET /memberships` con `enforce_user_limit(PII_SEARCH_BUCKET, ...)` solo con `q` y `responses_for(422, 429)`.

**B7.5 · Contrato**
P-API.

**B7.6 · Gate** (sin `PYTEST_ADDOPTS` en el que lista `test_list_perf.py`)
1. `slice-gate.sh members tests/members/test_service_list.py tests/members/test_router_list.py` (regresión de `active_ids` y de la cubeta compartida).
2. Al final, para sellar: `slice-gate.sh memberships tests/memberships/test_rules.py tests/memberships/test_status_expr_parity.py tests/memberships/test_list_service.py tests/memberships/test_list_perf.py tests/memberships/test_list_router.py tests/memberships/test_status_queries_service.py tests/memberships/test_summary_cache.py tests/memberships/test_summary_router.py tests/architecture/test_no_cross_schema_sql.py`.

**B7.7 · Docker y evidencia**
Por 8180: `GET /memberships?status=active,pending_payment` lista las de B4 a B6 con `paid_cop`; `GET /memberships/summary` cuadra con el conteo por socio hecho en psql con la misma regla; `GET /memberships/{id}` del socio anulado en B5 muestra `pending_payment` (cierra la evidencia pendiente de B5.6).

**B7.8 · Checkpoint**
`"S3-B7 listar membresías, resumen en SQL con caché y consultas de estado"`.

### S3-B8 · Listas, detalle y resumen de pagos

- **Historias:** US-098, US-099 y US-100.
- **Depende de:** B5 (anulaciones en los datos) y B1 (`refs_for`).
- **Migración:** ninguna (la condicional `0014_payments_registered_by_idx` solo si `perf` falla; se anota).
- **Cierra:** demo 7 (cuadre del resumen); riesgo 22 de la exploración; M-2 (cubeta en pagos), M-4 (`parse_month`, `from`/`to`), M-8 (`backdated`), L-2, L-13; S3-D23, S3-D26, S3-D45, S3-D47, S3-D51, S3-D57, S3-D71 (`perf` de pagos). Primer uso real del par perezoso `("payments", "memberships")`.

**B8.1 · Stubs**
`payments/rules.py`: `PaymentFilters`, `build_filters`, `parse_month`, `month_bounds_utc`, `InvalidMonth`, `partial_email`, `is_backdated(paid_at, created_at) -> bool`, `MONTH_MIN = 2020`, `MONTH_MAX = 2100`, `DATE_FLOOR`, `date_ceiling(today)`; `payments/queries.py`: `list`, `get`, `summary`, `_enrich`; `payments/schemas.py`: `PaymentRow` (con `backdated`), `PaymentDetail`, `PaymentsSummary`, `PaymentListQuery` (alias `from`, `backdated: bool | None`); rutas `GET /payments/summary`, `GET /payments`, `GET /payments/{payment_id}`.

**B8.2 · Rojo**
- `tests/payments/test_month_bounds.py`: `month_bounds_utc("2026-10")` da `2026-10-01T05:00Z` a `2026-11-01T05:00Z`; diciembre cruza de año; `2026-13`, `2026-1`, `26-10`, `abcd-ef`, `9999-12`, `0000-01`, `2019-12`, `2101-01` dan `InvalidMonth` (sin `ValueError` ni `OverflowError`); `2100-12` pasa.
- `tests/payments/test_list_filters.py` (puras): cada filtro aislado; `voided` tri-estado; `backdated` tri-estado; `q` sin coincidencias; rango excluye `to`; `from = 2019-12-31` y `to = hoy + 6 años` rechazados con `field`; `partial_email("laura@box.co") == "l•••@box.co"`, un correo de una letra y uno sin `@`; `is_backdated` con 23 h (no) y 25 h (sí).
- `tests/payments/test_list.py`: 40 pagos de octubre (3 anulados, 2 `backdated`): primera página de 25 descendente y `total = 40`; cada filtro; `q` por referencia en minúsculas; `q` por apellido parcial y documento; `member_id` y `membership_id`; sin datos cifrados; nombres y fechas de la membresía por los services reales; `contador_de_consultas`: una consulta por servicio vecino por página; `decrypt` solo con `q`; `registered_by_name` es correo parcial.
- `tests/payments/test_router_list.py`: 200 admin y coach; 403 `member`; 401; 422 con `field` para `limit` 0 y 201, `offset` negativo, `method="tarjeta"`, `from` inválido; enteros; con `q` la 61 da 429 y comparte cubeta con `/members?q=` (M-2); `backdated=true` filtra.
- `tests/payments/test_get.py` y `test_router_get.py`: vigente; anulado con `voided_by_name` parcial; 404; 422 con "no-es-uuid"; `/payments/summary` y `/payments/methods` no caen en `{payment_id}`; 403; 401.
- `tests/payments/test_summary.py`: escenario del blueprint (660.000 por medio; `voided_count = 1`; `payments_count = 3`); `2026-11-01T03:00Z` cuenta en octubre y `T05:00Z` en noviembre; mes vacío da ceros; sin `month` usa Bogotá con `FrozenClock` en `2026-10-31T23:30-05:00`; `total_cop` igual a la suma de `list(voided=false)` del rango; L-13: un pago de septiembre anulado en octubre no cambia octubre y sí baja septiembre.
- `tests/payments/test_router_summary.py`: 200; 422 `field="month"` con `2026-13` y `9999-12`; 403; 401; enteros.
- `tests/payments/test_list_perf.py` (`perf`): 10.000 pagos, `limit=25` en menos de 500 ms; `summary` del mes en menos de 300 ms.
- Arquitectura: `test_service_import_graph.py` (par perezoso `("payments","memberships")` presente y permitido; `payments` sigue sin importarlo a nivel de módulo), `test_error_codes_per_route.py` (`get /api/v1/payments`), `test_list_routes_use_page_params.py` (`GET /api/v1/payments`).
- Confirmar el rojo.

**B8.3 · Verde**
Según el blueprint B8 con S3-D47, S3-D51 y S3-D57: `list` pagina `select(Payment)` con `ORDER BY paid_at DESC, id DESC`, enriquece con `memberships.service.refs_for` (import perezoso, `# lazy: G-03 (payments -> memberships)`), `auth.service.names_for` + `partial_email`, `members.search_ids` solo con `q`; `summary` en una consulta con `SUM ... FILTER` y `COUNT ... FILTER`; `month_bounds_utc` con aritmética de `(year, month)`; rutas `StaffDep`, `GET /payments` con `enforce_user_limit(PII_SEARCH_BUCKET, ...)` solo con `q`, orden fijo (`summary`, `methods`, lista, `{payment_id}`).

**B8.4 · Contrato**
P-API.

**B8.5 · Gate** (sin `PYTEST_ADDOPTS`)
1. `slice-gate.sh members tests/members/test_router_list.py` (cubeta compartida).
2. Al final, para sellar: `slice-gate.sh payments tests/payments/test_month_bounds.py tests/payments/test_list_filters.py tests/payments/test_list.py tests/payments/test_router_list.py tests/payments/test_get.py tests/payments/test_router_get.py tests/payments/test_summary.py tests/payments/test_router_summary.py tests/payments/test_list_perf.py`.

**B8.6 · Docker y evidencia**
Por 8180: `GET /payments?from=2026-10-01T05:00:00Z&to=2026-11-01T05:00:00Z&voided=false` y `GET /payments/summary?month=2026-10`: `total_cop` igual a la suma de `amount_cop` de la lista; `GET /payments/{id}` del anulado de B5 con `void_reason` y `voided_by_name` parcial.

**B8.7 · Checkpoint**
`"S3-B8 listas, detalle y resumen de pagos"`.

### S3-B9a · Partición de `members/service.py` (sin cambio de comportamiento)

- **Historias:** tarea técnica de US-071 y US-073 (D7, condición 6, riesgo 3 de la exploración).
- **Depende de:** B8.
- **Migración:** ninguna.
- **Cierra:** condición 6 (`members`), S3-D73.

**B9a.1 · Extracción**
Mover a `members/rules.py` las puras y los tipos: `validate_member_input`, `compute_warnings`, `mask`, `classify_query`, `QueryPlan`, `LIKE_ESCAPE` y sus ayudantes; `service.py` los re-exporta con `__all__` (las pruebas de `tests/members` importan todo desde `app.modules.members.service` y no se tocan). Crear `members/detail.py` y `members/changes.py` vacíos con docstring. `PRIVATE_HELPERS["members"] = frozenset({"rules", "detail", "changes"})`.

**B9a.2 · Rojo de arquitectura**
`tests/architecture/test_no_cross_models.py`: ningún módulo distinto de `members` importa `app.modules.members.rules`, `detail` ni `changes`; `tests/architecture/test_file_and_function_size.py` sigue verde (`service.py` < 800).

**B9a.3 · Gate**
Para sellar: `slice-gate.sh members` (toda la carpeta `tests/members`, sin lista).

**B9a.4 · Checkpoint**
`"S3-B9a partición de members/service.py en rules, detail y changes"`.

### S3-B9b · Filtros de socios y ficha

- **Historias:** US-071 y US-073.
- **Depende de:** B9a y B7 (`status_for`, `member_ids_by_status`).
- **Migración:** ninguna.
- **Cierra:** condición 1 (lista blanca perezosa `("members","memberships")` en uso), condición 2 (429 por ruta en `members`), demo 6 (máscaras) y 7 (filtros); riesgos 10, 11, 12 de la exploración; riesgo 8 del blueprint (D35); M-2 (`members-detail`), D-4 (`_decrypt_fields`); S3-D20, S3-D22, S3-D27, S3-D35, S3-D45, S3-D59, S3-D71 (5.000 ids).

**B9b.1 · Stubs**
`members/schemas.py`: `MembershipFilterStatus`, `MemberListQuery` con `membership_status` y `plan_id`, `MemberRowOut.membership_end_date`, `MemberDetailOut.plan_name` y `membership_end_date`; `members/rules.py`: `chip_to_filter(chip) -> MemberChipFilter`; `members/detail.py`: `_decrypt_fields(socio, campos, purpose) -> dict[str, object]` y `get(session, member_id) -> MemberDetailOut`; `members/service.py` (`list` con el conjunto de ids); `members/router.py`: `GET /members/{member_id}`; `tests/members/_apoyo.py` (`CAMPOS_DETALLE`, `CAMPOS_FILA`).

**B9b.2 · Rojo**
- `tests/members/test_chip_to_filter.py`: los siete chips y uno desconocido (`ValueError`).
- `tests/members/test_service_list_membership_filters.py` (`reloj`, `expiring_days` 7): casos del blueprint B9 ("por vencer" frente a "al día"; `pending_payment`; `none` como complemento; vigente más futura muestra la vigente; filtro por plan de la vigente; plan inexistente vacío; `none` con `plan_id` vacío; dado de baja con `status=deleted` y su estado; la rama de documento sigue usando `uq_members_document_idx_alive` con `EXPLAIN`; cero `decrypt`; una sola llamada a `status_for` por página con `contador_de_consultas`); `test_list_perf.py` gana el caso `perf` de 5.000 ids en `any_` (S3-D71) sin tocar el límite de parámetros.
- `tests/members/test_router_list_filters.py`: 422 con `membership_status="moroso"` (`field="membership_status"`) y `plan_id` no UUID; coach con `status=deleted` 200 (N-20); `plan_name` y `membership_end_date` en las filas con membresía; `responses` de `POST /members` y `GET /members` siguen con 429 y las demás rutas de `members` no (D27).
- `tests/members/test_service_get.py`: casos del blueprint (cinco máscaras de `KNOWN`; cinco filas `decrypt` con `purpose='mask'`, `record_id` y `user_id`; ninguna `reveal`; dado de baja devuelve `deleted_at`; `membership_status`, `plan_name`, `membership_end_date` de `status_for`; campos nulos sin fila; `warnings == []`).
- `tests/members/test_router_get.py`: 200 admin y coach; 200 sobre un dado de baja; 403 `member`; 401; 404; 422 por UUID; `no-store`; sin documento en claro; `caplog` limpio; la ficha 121 en un minuto da 429 (`members-detail`, M-2) y la 121 de otro usuario pasa.
- Arquitectura: `test_service_import_graph.py` (la aserción de lista blanca vacía ya se quitó en B1; aquí el par `("members","memberships")` aparece como perezoso real y está permitido), `test_error_codes_per_route.py` (`CON_LIMITE` gana `get /api/v1/members/{member_id}`; el 429 del router de `members` baja a `POST /members` y `GET /members`), `tests/architecture/test_reveal_single_door.py` (D-4: fuera de `core/`, `types.reveal(` solo se llama en `members/detail.py::_decrypt_fields`), `test_list_rows_without_sensitive_fields.py` (verde con los campos nuevos).
- Front (D35): `web/src/features/members/schemas.ts` agrega `membership_end_date: z.string().nullable().optional().default(null)` a `memberRowSchema` y `memberDetailSchema` acepta `plan_name` y `membership_end_date`; `web/src/test/members.tsx` y `web/tests/e2e/members.spec.ts` al día; `schemas.test.ts` verde.
- Confirmar el rojo.

**B9b.3 · Verde**
Según el blueprint B9 con D-4 y M-2: `members.list` pide con import perezoso (`# lazy: G-03 (members -> memberships)`) `member_ids_by_status` y aplica `Member.id == any_(array)` o `!= all_(...)` en la consulta externa; con `none` y `plan_id` página vacía sin consultar; decora con `status_for(ids)` (hasta 200). `detail.get` carga el socio con dados de baja, `_decrypt_fields(socio, CAMPOS_CIFRADOS, "mask")` y `mask(...)`; `status_for([id])` perezoso; nunca audita. Router: `responses_for(401, 403)` en el `APIRouter`; 429 declarado en `POST /members`, `GET /members` y `GET /members/{member_id}` (`enforce_user_limit("members-detail", ...)`, `responses_for(404, 422, 429)`).

**B9b.4 · Documentación**
`docs/design/ROUTES.md` no cambia aquí (lo edita el front en F1). RUNBOOK §4 (Socios): máscaras y `crypto_ops` por ficha.

**B9b.5 · Contrato**
P-API con el paso 6 (D35): `cd web && npx vitest run src/features/members/schemas.test.ts`.

**B9b.6 · Gate** (sin `PYTEST_ADDOPTS` por el caso `perf` de 5.000 ids)
Para sellar: `slice-gate.sh members tests/members/test_chip_to_filter.py tests/members/test_service_list_membership_filters.py tests/members/test_router_list_filters.py tests/members/test_service_get.py tests/members/test_router_get.py tests/members/test_service_list.py tests/members/test_router_list.py tests/members/test_list_perf.py tests/architecture/test_reveal_single_door.py`.

**B9b.7 · Docker y evidencia (demo 6 y 7)**
Por 8180: `GET /members/{id}` del socio de CC `1.020.304.417` → `document: "CC •••• 4417"`; psql: `SELECT verb, purpose, count(*) FROM crypto.crypto_ops WHERE record_id = <id> GROUP BY 1, 2` → `decrypt | mask | 5` y cero `reveal` en `audit.audit_log`; `GET /members?membership_status=active&plan_id=<Mensual>` devuelve el socio de B4; `GET /members?membership_status=none` no lo devuelve.

**B9b.8 · Checkpoint**
`"S3-B9b filtros de socios por membresía y ficha enmascarada"`.

### S3-B10 · Revelar, editar, dar de baja y reactivar

- **Historias:** US-074, US-075 y US-076.
- **Depende de:** B9b.
- **Migración:** ninguna.
- **Cierra:** la deuda del Sprint 2 (`test_no_sensitive_in_logs` `reveal`, `test_reveal_entry` con fábrica, T8 de US-018 en `test_logging_redact`), demo 6; riesgos 13, 14, 15, 16 de la exploración; H-3 punto 3 (`sell` frente a `deactivate`); M-1, M-3, L-1 (uso), L-7, L-12; S3-D19, S3-D21, S3-D44, S3-D46, S3-D54, S3-D70.

**B10.1 · Stubs**
`members/rules.py`: `diff_fields(before, patch) -> frozenset[str]`, `ensure_can_change(set_fields, role)`, `ADMIN_ONLY_FIELDS = frozenset({"document", "document_type"})`; `members/schemas.py`: `RevealIn`, `RevealOut`, `MemberPatch` (los diez campos de S3-D46, `extra="forbid"`, `emergency_contact.phone: SafeText`), `EmergencyContactOut`; `members/exceptions.py`: `MemberIsDeactivated` (409 `member_deactivated`), `MemberFieldForbidden` (403 `forbidden_field`, `field`), `MemberAlreadyDeactivated` (409), `MemberNotDeactivated` (409), `ConsentCannotBeWithdrawn` (422 `field="data_consent"`); `members/detail.py`: `reveal(session, member_id, field, *, ip) -> RevealOut`; `members/changes.py`: `update(session, member_id, patch, *, role) -> MemberDetailOut`, `deactivate(session, member_id) -> None`, `reactivate(session, member_id) -> MemberDetailOut`; eventos `MemberUpdated(member_id, changed_fields)` y `MemberDeactivated(member_id)` en `members/service.py` (el módulo no tiene `events.py`; se re-exportan); rutas `POST /members/{member_id}/reveal`, `PATCH /members/{member_id}`, `DELETE /members/{member_id}`, `POST /members/{member_id}/reactivate`; `tests/audit/test_reveal_entry.py` sin `uuid4()`.

**B10.2 · Rojo**
- `tests/members/test_service_reveal.py`: casos del blueprint B10 (valor igual al sembrado en los cinco campos; exactamente una fila `reveal` con `user_id`, `record_id`, `subject_member_id` y `after == {"field": ..., "ip": ...}` sin el valor (L-12); exactamente una `decrypt` con `purpose='reveal'`, `data_class='member.<campo>'`, `record_id`; si `audit.record` lanza (`monkeypatch`) no hay `reveal` ni valor pero sí `decrypt`; campo vacío → `None` y audita; ningún suscriptor agrega otra fila; sobre un dado de baja funciona).
- `tests/members/test_router_reveal.py`: 200 admin y coach con `{field, value}`; 422 `field="field"` con `first_name`; 403 `member` sin fila `reveal`; 401; 404; `no-store`; fallo simulado del commit → 500 sin el valor en el cuerpo; límites: la 31 en un minuto 429, la 201 en una hora 429 (`members-reveal-hour`, con `reloj.advance`), la 601 en un día 429; al pasar de 100 en la hora aparece `logger.warning("reveal volume")` con `user_id` y `count` y sin valores (M-1); `caplog` y stdout sin el valor.
- `tests/audit/test_reveal_entry.py`: con `make_member` y `members.service.reveal`, una fila `reveal`, `verify_chain` en verde, el valor no está en `before` ni `after`.
- `tests/members/test_member_patch_rules.py`: `diff_fields` (sin cambios; un cambio; solo de formato `"300 123 4567"` frente a `"3001234567"`; `null` en opcional); `ensure_can_change` por presencia (M-3): coach con `document` presente, aunque igual, da `MemberFieldForbidden`; coach con `document_type` igual; admin pasa; coach sin ninguno pasa.
- `tests/members/test_service_update.py`: casos del blueprint (cambio de teléfono recifra, nuevo nonce, `phone_idx` recalculado y la búsqueda vieja no encuentra; documento repetido → `MemberDocumentDuplicated` sin cambios parciales; dado de baja → `MemberIsDeactivated`; auditoría `update` solo con columnas cambiadas; PATCH sin cambios sin auditoría ni evento; `MemberUpdated.changed_fields` sin valores; `*_idx` como `***`), más M-3: `data_consent=true` sobre consentimiento nulo fija `data_consent_at = reloj` y sobre uno existente no la cambia; `data_consent=false` → 422; el documento solo cambia por admin y reindexa.
- `tests/members/test_router_update.py`: 200 admin y coach; 403 `member`; 403 coach con `document` igual y con distinto (`field="document"`) y con `document_type`; 401; 404; 409 (`member_document_duplicated` con `existing_id`, `member_deactivated`); 422 (`last_name` vacío, `sex` inválido, `birth_date` futura, `document: null`, `status`, `deleted_at`, `data_consent_at` en el cuerpo, `emergency_contact.phone` con NUL); `warnings` presente; el PATCH 61 en un minuto 429 (`members-write`, compartido con `POST /members`).
- `tests/members/test_service_deactivate.py` (con `reloj`): casos del blueprint (`deleted_at` en UTC y `status='inactive'`; auditoría `update`; `MemberDeactivated`; sale de lista y búsquedas; un socio nuevo con el mismo documento se crea; `memberships` y `payments` intactos con las fábricas; baja repetida 409; reactivar vuelve a `active`; reactivar con documento tomado 409 con `existing_id`; reactivar un vivo 409), más L-1: `sell` frente a `deactivate` con `dos_sesiones` y `bus_confirmado`: la venta que entra después de la baja recibe 422 `member_inactive`, nunca 201 sobre un dado de baja; sin 55P03 ni 40P01.
- `tests/members/test_router_deactivate.py`: 204 admin; 403 coach y `member`; 401; 404; 409; `reactivate` 200 admin, 403 coach, 409 de ambos tipos.
- `tests/memberships/test_lock_order.py`: `sell` frente a `deactivate` (misma combinación, vista desde membresías).
- `tests/architecture/test_no_physical_delete.py` (reemplaza a `test_no_physical_delete_users.py`): sin `session.delete(`, `delete(Member|Plan|User|Membership|Payment)` ni `DELETE FROM` sobre esas tablas en `app/`; `tests/architecture/test_no_sensitive_in_logs.py`: la prueba `reveal` deja de saltarse (login de coach, alta, `GET /members/{id}`, `reveal` de documento y teléfono, `PATCH`; ni stdout ni `caplog` contienen `KNOWN_NORMALIZED`, tokens ni `apx1.`); `tests/core/test_logging_redact.py`: un `reveal` real (T8 de US-018); `tests/architecture/test_events_without_pii.py` (S3-D70; `MemberUpdated.changed_fields` son nombres de campo, no valores); `test_error_codes_per_route.py` (`patch /api/v1/members/{member_id}` y `post /api/v1/members/{member_id}/reveal`).
- Confirmar el rojo.

**B10.3 · Verde**
Según el blueprint B10 con D19 corregida, S3-D44, S3-D46, S3-D54: `reveal` con `_decrypt_fields(socio, [field], "reveal")` y `audit.record(..., after={"field": field, "ip": ip})`; el router pasa `ip=client_ip(request, settings.TRUSTED_PROXIES)` y aplica las tres ventanas con `enforce_user_limit` más `usage("members-reveal-hour", ...)` para el aviso; `update` con `lock_member`, `ensure_can_change(patch.model_fields_set, role)`, comparación por `_decrypt_fields(..., "mask")`, `Secret.from_plain` solo en los campos que cambian, pre-chequeo `id_by_document` y traducción de `uq_members_document_idx_alive`, `data_consent`; `deactivate` y `reactivate` con `lock_member` y la traducción del índice único; rutas `POST .../reveal` (`StaffDep`, `responses_for(404, 422, 429)`), `PATCH` (`StaffDep`, `enforce_user_limit("members-write", ...)`, `responses_for(403, 404, 409, 422, 429)`), `DELETE` (204, `AdminDep`, `responses_for(404, 409, 422)`), `POST .../reactivate` (`AdminDep`, `responses_for(404, 409, 422)`).

**B10.4 · Documentación**
RUNBOOK §4: `reveal` y sus tres cupos; qué significa `reveal volume` en el log; recuperación de un socio dado de baja. `BRECHAS.md` §10: "Dado de baja", "Reactivar" y campos sensibles en edición con `// DESIGN-GAP:`.

**B10.5 · Contrato**
P-API.

**B10.6 · Gate**
1. `slice-gate.sh audit tests/audit/test_reveal_entry.py`.
2. `slice-gate.sh core/logging tests/core/test_logging_redact.py`.
3. `slice-gate.sh memberships tests/memberships/test_lock_order.py`.
4. Al final, para sellar: `slice-gate.sh members tests/members/test_service_reveal.py tests/members/test_router_reveal.py tests/members/test_member_patch_rules.py tests/members/test_service_update.py tests/members/test_router_update.py tests/members/test_service_deactivate.py tests/members/test_router_deactivate.py tests/architecture/test_no_physical_delete.py tests/architecture/test_no_sensitive_in_logs.py tests/architecture/test_events_without_pii.py`.

**B10.7 · Docker y evidencia (demo 6)**
Por 8180: `POST /members/{id}/reveal` `{field: "document"}` con el admin → `1020304417`; psql: una fila `reveal` en `audit.audit_log` (`after` con `field` e `ip`, sin el valor) y una `decrypt` con `purpose='reveal'`; `PATCH` con el coach cambiando `phone` → 200 y `phone_idx` distinto; `PATCH` con el coach enviando `document` igual → 403 `forbidden_field`; `DELETE` con el admin → 204 y `GET /members/{id}` con `deleted_at`; `POST /members/{id}/memberships` sobre él → 422 `member_inactive`; `POST .../reactivate` → 200. `$DC logs api` sin el documento ni el teléfono.

**B10.8 · Checkpoint**
`"S3-B10 revelar auditado, editar, dar de baja y reactivar socios"`.

### S3-B11 · Pestañas de la ficha

- **Historias:** US-093 y US-101 (backend).
- **Depende de:** B7 (`list` de membresías) y B8 (`list` de pagos).
- **Migración:** ninguna.
- **Cierra:** condición 3 (`q` en las listas anidadas), D28, el contrato definitivo del sprint.

**B11.1 · Stubs**
`plans/service.py`: `search_ids(session, q) -> set[UUID]` (en `__all__`); `memberships/queries.py`: `list_for_member(session, member_id, page, *, q=None) -> Page[MembershipOut]`; `payments/queries.py`: `list_for_member(session, member_id, voided, page, *, q=None) -> Page[PaymentRow]`; rutas `GET /members/{member_id}/memberships` y `GET /members/{member_id}/payments`.

**B11.2 · Rojo**
- `tests/plans/test_search_ids.py`: por nombre con tildes plegadas, incluye dados de baja, sin `q` vacío, sin `decrypt`.
- `tests/memberships/test_member_memberships_service.py`: orden `start_date DESC, id`; incluye canceladas; dado de baja devuelve las suyas; inexistente → `MemberNotFound`; congelaciones sin N+1 (`contador_de_consultas`); `q` por nombre de plan; estado efectivo; `paid_cop` por lote.
- `tests/memberships/test_member_memberships_router.py`: 200 paginado; `limit=0` 422; 404; 403 `member`; 401; sin 429 (no hay límite: `q` no usa `members.search_ids`).
- `tests/payments/test_list_for_member.py`: tres pagos en dos membresías (uno anulado) descendente; `voided=false` devuelve dos; dado de baja devuelve sus pagos; inexistente 404; `q` por referencia exacta; `backdated` presente.
- `tests/payments/test_router_member_payments.py`: 200 coach y admin; 404; 422 con `limit=0` y 201; 403 `member`; 401.
- Arquitectura: `test_list_routes_use_page_params.py` (las dos rutas anidadas con `PageParams` y `q`), `test_list_rows_without_sensitive_fields.py` (sin cambios; verde), `test_service_import_graph.py` (`memberships -> plans` ya existe; nada nuevo).
- Confirmar el rojo.

**B11.3 · Verde**
Según el blueprint B11: `members.ensure_exists(include_deleted=True)` → 404 en ambas; `plans.search_ids` con el mismo pliegue de `core/search`; rutas `StaffDep`, `responses_for(404, 422)`, `q: SearchQuery = None`, `Annotated[PageParams, Depends()]`, declaradas en los routers de `memberships` y `payments` con el path completo.

**B11.4 · Contrato**
P-API. Con este slice el contrato queda definitivo: 22 endpoints nuevos más los filtros de `GET /members`; `docs/openapi.json` sin diferencias al exportar dos veces.

**B11.5 · Gate**
1. `slice-gate.sh plans tests/plans/test_search_ids.py tests/plans/test_service_list.py`.
2. `slice-gate.sh payments tests/payments/test_list_for_member.py tests/payments/test_router_member_payments.py`.
3. Al final, para sellar: `slice-gate.sh memberships tests/memberships/test_member_memberships_service.py tests/memberships/test_member_memberships_router.py`.

**B11.6 · Cierre del backend (wave 3)**
1. `bash scripts/workflow/run-gates.sh`: cobertura global de `app` ≥ 80 % (esperado ≥ 93 %); `cd api && uv run pytest tests/architecture -q` (0 saltadas: la de `reveal` ya corre).
2. `cd api && uv run pytest -m perf -q` (membresías, pagos, socios) con `TEST_DATABASE_URL`: tiempos al cuaderno.
3. Ciclo de Alembic completo en `apex-db-1`: `downgrade 0007_plans` → `upgrade head` → `alembic current` = `0011_payments_immutability (head)`; `uv run alembic heads` = una.
4. `uvx pre-commit run --all-files`.

**B11.7 · Docker y evidencia**
Por 8180: `GET /members/{id}/memberships` y `GET /members/{id}/payments` del socio de B4 con `q` vacío y con `q=Mensual` / `q=<referencia>`; `Cache-Control: no-store`.

**B11.8 · Checkpoint**
`"S3-B11 pestañas de membresías y pagos de la ficha; cierre del backend"`.

## 6. Front (worktree, en paralelo; orden de ejecución F3, F4, F5, F6, F2, F1, F7 según S3-D66)

En todos los slices de front:
- rebase sobre la rama del sprint antes de empezar (trae `docs/openapi.json` y `types.ts`); nunca se regeneran en el worktree;
- el gate acota lint y tsc a los archivos del slice (A-01) y vitest a la lista;
- `$DC build web && $DC up -d web` antes de cualquier E2E del proyecto `stack` o de una demo en 8180;
- mecanismo de cruce entre features (S3-D65): hooks y esquemas compartidos en `web/src/shared/data/`; pestañas de la ficha por rutas hijas; `RegisterPaymentPanel` como host en `layouts/PanelLayout.tsx` abierto por `?pago=`; `boundaries.test.ts` no se toca y corre en cada gate `web/app`;
- toda mutación con monto, motivo o valor sensible: `gcTime: 0` y `reset()` en `onSettled` (S3-D52);
- los códigos nuevos entran a `web/src/core/api/errorCodes.ts` en el primer slice que los usa; `errorCodes.test.ts` los busca en `api/src` (el worktree ve el backend por el rebase);
- cada faltante del diseño lleva `// DESIGN-GAP:` y se anota en `docs/scratch/sprint-03-front.md` para que el orquestador lo pase a `BRECHAS.md` en V1.

### S3-F3 · Vender, primer pago y renovar

- **Historias:** US-084, US-085 y US-088 (front).
- **Depende de:** B6 (checkpoint) y W0-1 (vitest actualizado).
- **Cierra:** condición 8 (nace `shared/data/`), condición 7 (`features.test.ts`, `nav.test.ts`, `routes.test.ts` por `memberships`), H-1 (front: confirmación de sobrepago en la venta), M-7 (aviso en referencia), M-9 (`reset()`); S3-D16, S3-D36, S3-D41, S3-D50, S3-D52, S3-D65, S3-D72.

**F3.1 · Rebase, datos compartidos y códigos**
- `git rebase feat/sprint-03-membresias-pagos`; `npm ci`.
- Crear `web/src/shared/data/`: `members.ts` (`useMembersSearch(q)` sobre `GET /members?q=&limit=10`, `membersSearchSchema`), `plans.ts` (mover `usePlans` y `planRowSchema` desde `features/plans/api.ts` y `schemas.ts`; `features/plans/api.ts` los reexporta para no tocar `PlansPage`), `paymentMethods.ts` (`usePaymentMethods()` con `staleTime` 5 min, lee `items`; `paymentMethodsSchema`), `memberships.ts` (`useMembershipSummary()`, `membershipSummarySchema`; `useMemberMemberships` llega en F7), `schemas/money.ts` (`copInt = z.number().int().min(1).max(1_000_000_000)`).
- `web/src/core/api/errorCodes.ts`: `busy`, `member_inactive`, `plan_invalid`, `plan_inactive`, `start_date_too_retroactive`, `start_date_too_far`, `membership_conflict`, `membership_overlap`, `future_membership_exists`, `membership_not_found`, `payment_exceeds_balance`, `payment_possible_duplicate`, `payment_limit_reached`, `paid_at_too_retroactive`. `core/api/client.ts`: un 503 `busy` se reintenta una vez tras `Retry-After` segundos en lecturas (`GET`), nunca en escrituras; el mensaje genérico "El sistema está ocupado; intenta de nuevo" en `errorCodes`.
- `web/src/test/memberships.tsx` y `web/src/test/payments.tsx` (fixtures de la sección 2).

**F3.2 · Stubs**
`features/memberships/{api,schemas,membershipErrors,membershipLinks}.ts`, `lib/rules.ts`, `pages/SellPage.tsx`, `pages/SellPage.renew` (mismo componente, `?renovar=1`), `components/FirstPaymentSection.tsx`; `features/payments/{api,schemas}.ts` mínimos (solo lo que F3 necesita; F4 los amplía); `config/features.ts` con `memberships`; `routeTable.ts` con `load` en `/membresias/vender`.

**F3.3 · Rojo**
- `src/features/memberships/schemas.test.ts`: `sellMembershipSchema(today)` (monto entero positivo, `first_payment` opcional, referencia hasta 64 con el patrón de S3-D50, `renew` descarta `start_date` en `toSellBody`), `membershipOutSchema` y `sellMembershipOutSchema` estrictos con enteros.
- `src/features/memberships/lib/rules.test.ts`: `computeEndDate` (N-23: 2026-10-29 + 30 → "hasta el 28 nov 2026"), `saldo`, `exceedsBalance`.
- `src/features/memberships/pages/SellPage.test.tsx`: resumen con moneda y fecha por `core/i18n/format`; 409 `membership_conflict` con enlace "Renovar" a `?socio=:id&renovar=1`; sin planes activos; error por campo con foco; un solo envío por doble clic; `confirm_overpayment` no se envía si no hubo modal; tras el 201 el `MutationCache` no conserva `variables` (S3-D52); 503 `busy` muestra el mensaje y no limpia el formulario.
- `src/features/memberships/pages/SellPage.renew.test.tsx`: fecha calculada visible y no editable ("Empieza el 29 oct 2026, al día siguiente de que termine la actual"); cambio de plan refresca `useRenewalPreview`; 409 `future_membership_exists` con enlace a la ficha.
- `src/features/memberships/components/FirstPaymentSection.test.tsx`: referencia visible para Nequi y Bre-B y opcional (`// DESIGN-GAP:`); el aviso "No escribas teléfonos, documentos ni datos de salud" bajo referencia (M-7); monto mayor al precio abre `ConfirmModal` "Este pago supera el precio del plan en $ X" y solo envía con `confirm_overpayment: true` al confirmar; un 409 `payment_exceeds_balance` inesperado (carrera) también abre el modal y reenvía; error `first_payment.*` bajo su campo; fecha enviada en UTC.
- `src/shared/data/*.test.ts`: `usePaymentMethods` parsea `items` en orden; `useMembersSearch` no guarda `q` en la URL; `usePlans` reexportado sigue funcionando (`features/plans` verde).
- `src/config/features.test.ts` (siete habilitadas), `src/layouts/nav.test.ts` ("Membresías" en el menú), `src/routes.test.ts` (`/membresias/vender` con `load`).
- `tests/e2e/sell-with-payment.spec.ts` (preview, `page.route` simulando el API): vender con pago completo y ver "Al día" en el resumen; `tests/e2e/stack/sell-with-payment.spec.ts`: crear socio por API (`crearSocio`), vender por la pantalla con pago completo, comprobar "Al día" en `/socios` y el 409 al vender de nuevo; documento aleatorio por corrida.
- Confirmar el rojo.

**F3.4 · Verde**
Según el blueprint F3 con D16, D37 y S3-D41: `SellPage` en `/membresias/vender` y `?socio=:id&renovar=1` (tres pasos en una página; socio por `useMembersSearch` o fijo; `usePlans({active: true})`; inicio por defecto hoy en Bogotá; "Precio pactado" de solo lectura; resumen con vigencia, precio, pago y saldo); `FirstPaymentSection` con `usePaymentMethods`; `useSellMembership(memberId)` (`gcTime: 0`, `reset()` en `onSettled`, invalida `["memberships"]`, `["members"]`, `["payments"]`, `["memberships-summary"]`); `useRenewalPreview`; `membershipErrors.ts`; `// DESIGN-GAP:` por fin de vigencia, precio pactado y referencia opcional.

**F3.5 · Documentación**
`docs/design/ROUTES.md`: `/membresias/vender` con sus parámetros y endpoints; `docs/scratch/sprint-03-front.md` con el bloque del slice y los DESIGN-GAP.

**F3.6 · Gate**
1. `slice-gate.sh web/core src/core/api/errorCodes.test.ts src/core/api/client.test.ts`.
2. `slice-gate.sh web/shared src/shared/data/members.test.ts src/shared/data/plans.test.ts src/shared/data/paymentMethods.test.ts src/shared/data/memberships.test.ts`.
3. `slice-gate.sh web/plans src/features/plans/pages/PlansPage.test.tsx` (regresión del movimiento de `usePlans`).
4. `slice-gate.sh web/app src/config/features.test.ts src/layouts/nav.test.ts src/routes.test.ts tests/lint/boundaries.test.ts`.
5. `cd web && npx playwright test --project=preview tests/e2e/sell-with-payment.spec.ts`.
6. Al final, para sellar: `slice-gate.sh web/memberships src/features/memberships/schemas.test.ts src/features/memberships/lib/rules.test.ts src/features/memberships/pages/SellPage.test.tsx src/features/memberships/pages/SellPage.renew.test.tsx src/features/memberships/components/FirstPaymentSection.test.tsx`.

**F3.7 · Docker**
`$DC build web && $DC up -d web`; si B6 ya está en la base del worktree, `E2E_BASE_URL=http://localhost:8180 npx playwright test --project=stack tests/e2e/stack/sell-with-payment.spec.ts` (es la venta real de `verify-delivery`); si no, en V4.

**F3.8 · Checkpoint**
`"S3-F3 vender, primer pago y renovar; datos compartidos del front"`.

### S3-F4 · Registrar y anular pagos, y medios de pago

- **Historias:** US-056, US-095 y US-097 (front).
- **Depende de:** B7 (lista de membresías por socio con `paid_cop`), B5 (anular), B3 (medios) y F3.
- **Cierra:** condición 7 (`ConfigPage.test.tsx`), condición 8 (host del panel por URL), H-1 (front: sobrepago y duplicado en el panel), M-7 (avisos), M-9 (`reset()`); S3-D24, S3-D36 (`payments`), S3-D41, S3-D50, S3-D52, S3-D65, S3-D72.

**F4.1 · Rebase y stubs**
Rebase. `features/payments/schemas.ts` (`paymentRowSchema`, `paymentDetailSchema`, `registerPaymentSchema`, `voidPaymentSchema` con motivo 1 a 500 tras recortar), `features/payments/api.ts` (`useRegisterPayment(membershipId)`, `useVoidPayment()`, `usePayment(id)`), `paymentErrors.ts`, `components/RegisterPaymentPanel.tsx`, `components/RegisterPaymentPanelHost.tsx`, `components/VoidPaymentModal.tsx`; `shared/lib/paymentPanel.ts` (`paymentPanelHref(location, {membershipId} | {memberId})`, `readPaymentPanel(search)`, `closePaymentPanelHref`); `layouts/PanelLayout.tsx` monta `RegisterPaymentPanelHost` con `React.lazy` si `ENABLED_FEATURES.has("payments")`; `features/system/components/PaymentMethodsForm.tsx`, `system/api.ts` (`SettingsKey` con `payment_methods`), `system/schemas.ts` (`paymentMethodsSettingsSchema`); `config/features.ts` con `payments`.

**F4.2 · Rojo**
- `src/features/payments/schemas.test.ts`: montos enteros; referencia con patrón; motivo recortado 1 a 500; `paymentRowSchema` con `backdated`.
- `src/features/payments/components/RegisterPaymentPanel.test.tsx`: socio preseleccionado por `?pago=nuevo&socio=`; membresía preseleccionada por `?pago=<id>`; opciones de membresía con saldo ("Mensual 25 sep–24 oct · saldo $60.000") desde `GET /memberships?member_id=&status=active,expiring,frozen,pending_payment`; monto entero; error por campo (`membership_cancelled`, `paid_at`, `paid_at_too_retroactive` con el texto de 7 días para el coach); advertencia Q5: monto mayor al saldo abre `ConfirmModal` y reenvía con `confirm_overpayment: true`; 409 `payment_possible_duplicate` abre el segundo modal "Ya registraste un pago igual hace menos de 2 minutos" y reenvía con `confirm_duplicate: true` solo al confirmar; 409 `payment_limit_reached` muestra el mensaje y no reintenta; envío en UTC; aviso M-7 bajo referencia; al cerrar, `reset()` y el `MutationCache` sin `variables`; precarga desde una anulación (monto y medio).
- `src/features/payments/components/VoidPaymentModal.test.tsx`: oculto al coach (`payments.void`); motivo obligatorio con el texto "El pago no se borra: queda anulado con este motivo" y el aviso M-7; 409 `payment_already_voided` muestra "Otra persona lo anuló antes" y refresca; tras anular ofrece "Registrar pago nuevo" que abre `?pago=<membershipId>` con precarga; `reset()` al cerrar.
- `src/features/payments/components/RegisterPaymentPanelHost.test.tsx`: no renderiza nada sin `?pago=`; abre con `?pago=`; cerrar limpia el parámetro y conserva los demás filtros de la URL.
- `src/layouts/PanelLayout.test.tsx`: monta el host solo con `payments` habilitada; `layouts.no-fetch.test.ts` sigue verde (el host no pide nada hasta abrirse).
- `src/features/system/components/PaymentMethodsForm.test.tsx`: tres filas fijas, sin agregar ni quitar, nota "Para agregar un medio nuevo se requiere una actualización del sistema", etiqueta vacía con error bajo "Efectivo", etiqueta repetida con el error del API (`value.nequi.label`), guardar muestra "Cambios guardados", `version_conflict`; `ConfigPage.test.tsx`: cuatro pestañas `["Gimnasio", "Privacidad", "Membresías", "Medios de pago"]`.
- `src/config/features.test.ts` (ocho), `src/layouts/nav.test.ts` ("Pagos"), `tests/e2e/settings-config.spec.ts` (pestaña nueva).
- `tests/e2e/stack/payment-void.spec.ts`: vender por API con pago parcial, registrar el saldo por el panel (sin modal), intentar un tercer pago mayor (modal y confirmación), anular el tercero con motivo, comprobar "Anulado" y que un segundo clic en Anular da el mensaje de 409.
- Confirmar el rojo.

**F4.3 · Verde**
Según el blueprint F4 con S3-D41, S3-D50, S3-D52 y S3-D65: `RegisterPaymentPanel` (`SidePanel`) con `useMembersSearch` y la lista de membresías abiertas del socio por `useMemberOpenMemberships(memberId)` de `shared/data/memberships.ts` (`GET /memberships?member_id=&status=active,expiring,frozen,pending_payment`; vive en `shared/data` para no importar `features/memberships` desde `features/payments`); `useRegisterPayment` (`gcTime: 0`, `reset()`, invalida `["payments"]`, `["payments-summary"]`, `["memberships"]`, `["memberships-summary"]`, `["members"]`); `VoidPaymentModal` (`ConfirmModal`); `PaymentMethodsForm` en la pestaña "Medios de pago" (`// DESIGN-GAP:` por las casillas de habilitar); `payments` en `ENABLED_FEATURES`.

**F4.4 · Documentación**
`ROUTES.md`: el parámetro `?pago=` del panel y la pestaña "Medios de pago" de `/sistema/configuracion`.

**F4.5 · Gate**
1. `slice-gate.sh web/shared src/shared/lib/paymentPanel.test.ts src/shared/data/memberships.test.ts`.
2. `slice-gate.sh web/layouts src/layouts/PanelLayout.test.tsx src/layouts/layouts.no-fetch.test.ts`.
3. `slice-gate.sh web/system src/features/system/components/PaymentMethodsForm.test.tsx src/features/system/pages/ConfigPage.test.tsx`.
4. `slice-gate.sh web/app src/config/features.test.ts src/layouts/nav.test.ts tests/lint/boundaries.test.ts`.
5. `cd web && npx playwright test --project=preview tests/e2e/settings-config.spec.ts`.
6. Al final, para sellar: `slice-gate.sh web/payments src/features/payments/schemas.test.ts src/features/payments/components/RegisterPaymentPanel.test.tsx src/features/payments/components/RegisterPaymentPanelHost.test.tsx src/features/payments/components/VoidPaymentModal.test.tsx`.

**F4.6 · Docker**
`$DC build web && $DC up -d web`; E2E `stack/payment-void.spec.ts` si B7 ya está en la base; si no, V4.

**F4.7 · Checkpoint**
`"S3-F4 registrar y anular pagos, medios de pago y panel por URL"`.

### S3-F5 · Pantalla de membresías

- **Historias:** US-089, US-090, US-091 y US-092 (front).
- **Depende de:** B7 y F4 (`?pago=`).
- **Cierra:** condición 7 (`routes.test.ts` por `/membresias`), D14 (front), D18, M-7 (aviso en el motivo de anulación), M-9; S3-D50, S3-D52.

**F5.1 · Rebase y stubs**
`features/memberships/api.ts`: `useMemberships(params)` (`keepPreviousData`), `useMembership(id)`, `useFreezeMembership()`, `useCancelMembership()`; `pages/MembershipsPage.tsx`; `components/FreezeModal.tsx`, `components/CancelMembershipModal.tsx`; `lib/rules.ts`: `freezePreview(from, to, endDate)`; `routeTable.ts` con `load` en `/membresias`.

**F5.2 · Rojo**
- `MembershipsPage.test.tsx`: filtros en la URL (`status` separado por comas, `plan_id`, `ends_from`, `ends_to`), chip "Pendiente de pago" con texto (`// DESIGN-GAP:`), conteos de `useMembershipSummary`, búsqueda en memoria (`localQuery`), columnas (socio con enlace a la ficha, plan y precio, inicio, fin, clases restantes, pagado "$60.000 de $120.000 · abono", `StatusTag`), acciones por fila (Renovar a `/membresias/vender?socio=&renovar=1`; "Registrar saldo" enlaza a `?pago=<id>` solo con `payments.register`; Congelar con `memberships.freeze`; Anular oculto al coach); vacío "No hay membresías con estos filtros"; error con reintento; `limit` 25/50/100.
- `FreezeModal.test.tsx` y `lib/rules.test.ts`: `freezePreview` ("Son 10 días; la membresía terminará el 10 nov 2026"); fechas invertidas bloquean el envío; sin campo de motivo (`// DESIGN-GAP:`); mensajes por código 409 (`freeze_limit_reached`, `freeze_days_exceeded` con los días disponibles del mensaje del API, `overlaps_future_membership`) y 422; `reset()` al cerrar.
- `CancelMembershipModal.test.tsx`: motivo 5 a 500 con el texto "Los pagos asociados no se tocan: si hay que devolver dinero, se anula el pago aparte." y el aviso M-7; doble clic un solo envío; 409 `membership_already_cancelled`; `reset()`.
- `api.summary.test.ts` ya vive en `shared/data` (F3); aquí `api.test.ts` cubre `useMemberships` (clave con los filtros) y las invalidaciones.
- `src/routes.test.ts`: `/membresias` con `load`.
- Confirmar el rojo.

**F5.3 · Verde**
Según el blueprint F5 con S3-D52 y S3-D65 (sin importar `features/payments`: el botón "Registrar saldo" es un `Link` a `paymentPanelHref`).

**F5.4 · Documentación**
`ROUTES.md`: `/membresias` con filtros.

**F5.5 · Gate**
1. `slice-gate.sh web/app src/routes.test.ts tests/lint/boundaries.test.ts`.
2. Al final, para sellar: `slice-gate.sh web/memberships src/features/memberships/pages/MembershipsPage.test.tsx src/features/memberships/components/FreezeModal.test.tsx src/features/memberships/components/CancelMembershipModal.test.tsx src/features/memberships/lib/rules.test.ts src/features/memberships/api.test.ts`.

**F5.6 · Docker**
`$DC build web && $DC up -d web`; congelar 10 días y anular desde `/membresias` contra el stack (demo 5) y anotar.

**F5.7 · Checkpoint**
`"S3-F5 pantalla de membresías con congelar y anular"`.

### S3-F6 · Pantalla de pagos

- **Historias:** US-098, US-099 y US-100 (front).
- **Depende de:** B8 y F4.
- **Cierra:** condición 7 (`/pagos`), D23 y D26 (front), S3-D57 (correo parcial mostrado tal cual).

**F6.1 · Rebase y stubs**
`features/payments/api.ts`: `usePayments(params)`, `usePaymentsSummary(month)`; `pages/PaymentsPage.tsx`; `components/MonthSummary.tsx`, `components/PaymentDetailModal.tsx`; `routeTable.ts` con `load` en `/pagos`.

**F6.2 · Rojo**
- `PaymentsPage.test.tsx`: filtros en la URL (rango de fechas con el día de Bogotá convertido a UTC y `to` exclusivo, `method`, `registered_by`, estado Todos/Válidos/Anulados que arranca en Todos por D37, `backdated`); búsqueda en memoria; columnas (fecha y hora de Bogotá, socio, membresía "Mensual 29 oct–27 nov", valor, medio, referencia, registró con el correo parcial, `StatusTag` "Anulado" y marca "Retroactivo" si `backdated`); sin editar ni borrar; paginación; vacío; "Registrar pago" abre `?pago=nuevo`.
- `PaymentDetailModal.test.tsx`: anulado muestra motivo, autor parcial y fecha; sin editar ni borrar; "Anular" solo con `payments.void` y abre `VoidPaymentModal`.
- `MonthSummary.test.tsx`: mes por defecto en Bogotá; cambio de mes en `?mes=AAAA-MM`; `$ 0` en ceros; 422 `month` fuera de 2020 a 2100 muestra el error; `KpiCard` por medio y contador de anulados.
- `src/routes.test.ts`: `/pagos` con `load`.
- Confirmar el rojo.

**F6.3 · Verde**
Según el blueprint F6.

**F6.4 · Documentación**
`ROUTES.md`: `/pagos` con filtros y `?mes=`.

**F6.5 · Gate**
1. `slice-gate.sh web/app src/routes.test.ts tests/lint/boundaries.test.ts`.
2. Al final, para sellar: `slice-gate.sh web/payments src/features/payments/pages/PaymentsPage.test.tsx src/features/payments/components/PaymentDetailModal.test.tsx src/features/payments/components/MonthSummary.test.tsx`.

**F6.6 · Docker**
`$DC build web && $DC up -d web`; comprobar en 8180 que el total del mes cuadra con la lista filtrada (demo 7).

**F6.7 · Checkpoint**
`"S3-F6 pantalla de pagos con detalle y resumen del mes"`.

### S3-F2 · Filtros de la lista de socios y vista móvil

- **Historias:** US-071 y US-072.
- **Depende de:** B9b (filtros, `membership_end_date`) y B7 (resumen); F3 (`shared/data`).
- **Cierra:** D22 y D39 (front), D37 (conteos de chips), M-9 punto 4 (`maxPages`), riesgo 11 de la exploración (`memberRowSchema`); S3-D52, S3-D72 (`members-mobile`).

**F2.1 · Rebase y stubs**
`features/members/schemas.ts`: `MEMBERSHIP_CHIPS` (siete) y `chipToFilter`; `memberRowSchema` ya trae `membership_end_date` desde B9b (D35); `MembersParams` y `membersQueryKey` con `membership_status` y `plan_id`; `components/MemberStatusChips.tsx`, `components/PlanFilter.tsx`, `components/MemberCardList.tsx`; `api.ts`: `useMembersInfinite(params)` con `maxPages: 20`; `pages/MembersListPage.tsx` con columnas Plan vigente y Vence.

**F2.2 · Rojo**
- `MemberStatusChips.test.tsx`: Todos, Al día, Por vencer, Vencidos, Congelados, Pendiente de pago (`// DESIGN-GAP:` Q3), Sin membresía (total menos la suma de los cinco), Dados de baja (admin y coach, N-20); valor en la URL; cambiar reinicia `offset`; `aria-pressed`; conteos de `useMembershipSummary`.
- `PlanFilter.test.tsx`: `<select>` dentro de `Field` con `usePlans({active: true})` de `shared/data`; `plan_id` en la URL.
- `MemberCardList.test.tsx` (`matchMedia` simulado): tarjetas en móvil con nombre, `StatusTag`, plan y "vence"; tarjeta entera como enlace de al menos 44 px; etiqueta "Dado de baja"; "Cargar más" acumulativo y desaparece al llegar al total; error en la segunda página conserva las tarjetas y muestra "Reintentar"; tope `maxPages` 20 (la página 21 no se pide); botón flotante "Nuevo socio" con `members.create`; chips con `overflow-x: auto`; nada enmascarado ni sensible.
- `MembersListPage.test.tsx` ampliado: columnas Plan y Vence; `plan_id` y `membership_status` en la petición; `q` sigue fuera de la URL.
- `src/features/members/schemas.test.ts`: `memberRowSchema` sigue estricto con las nueve claves (ocho más `membership_end_date`).
- `tests/e2e/members-mobile.spec.ts` (preview, `page.route` con 60 socios) a 390 × 844 y 320 × 640: buscar "laura" y abrir la ficha (404 hasta F1: la spec solo comprueba la navegación a `/socios/:id`), "Cargar más" dos veces, `scrollWidth <= innerWidth`, axe en claro y oscuro, capturas; `tests/e2e/stack/members-mobile.spec.ts`: a 390 px contra el stack, la lista se muestra en tarjetas y "Cargar más" trae la segunda página (requiere ≥ 26 socios: `crearSocio` en bucle hasta 26, una sola vez por base).
- Confirmar el rojo.

**F2.3 · Verde**
Según el blueprint F2 con D39 y S3-D52: `MembersListPage` usa `MemberCardList` bajo `MOBILE_QUERY` y `DataTable` en escritorio; las tarjetas reutilizan `StatusTag` y los tokens de `DataTable.module.css`.

**F2.4 · Documentación**
`ROUTES.md`: filtros nuevos de `/socios`.

**F2.5 · Gate**
1. `cd web && npx playwright test --project=preview tests/e2e/members-mobile.spec.ts`.
2. Al final, para sellar: `slice-gate.sh web/members src/features/members/components/MemberStatusChips.test.tsx src/features/members/components/PlanFilter.test.tsx src/features/members/components/MemberCardList.test.tsx src/features/members/pages/MembersListPage.test.tsx src/features/members/schemas.test.ts`.

**F2.6 · Docker**
`$DC build web && $DC up -d web`; E2E `stack/members-mobile.spec.ts`; captura a 390 px al cuaderno del front (demo 7).

**F2.7 · Checkpoint**
`"S3-F2 filtros de socios por membresía, chips con conteos y vista móvil"`.

### S3-F1 · Ficha del socio

- **Historias:** US-073, US-074, US-075 y US-076 (front).
- **Depende de:** B9b, B10 y F2.
- **Cierra:** el criterio diferido de US-066 (`MaskedValue.onReveal`), S2-D34 (el enlace del 409 cobra vida), condición 7 (`/socios/:id` registrada), M-9 (S3-D52), S3-D21 y S3-D46 (front), S3-D65 (`<Outlet>` para las pestañas).

**F1.1 · Rebase y stubs**
`features/members/schemas.ts`: `memberDetailViewSchema` (todos los campos de `MemberDetailOut`; cinco sensibles como `string | null` enmascarados; `plan_name`, `membership_end_date`), `revealOutSchema`, `MemberPatchBody`, `memberEditSchema(today)`, `toMemberPatch(values, dirtyFields)`, `flattenRevealed(field, value)`; `api.ts`: `useMember(id)`, `useRevealField(id)`, `useUpdateMember(id)`, `useDeactivateMember()`, `useReactivateMember()`; `memberErrors.ts` (`forbidden_field`, `member_deactivated`, `member_already_deactivated`, `member_not_deactivated`, `member_document_duplicated` con enlace a `/socios/{existing_id}`, `data_consent`); `pages/MemberDetailPage.tsx` (+ css) con `<Outlet>` para las pestañas; `components/MemberDataTab.tsx` (pestaña índice "Datos"), `components/DeactivateMemberModal.tsx`; `pages/MemberFormPage.tsx` en modo edición; `routeTable.ts`: `load` en `/socios/:id` (con ruta índice Datos) y `/socios/:id/editar`; `errorCodes.ts` con los códigos de socios.

**F1.2 · Rojo**
- `MemberDetailPage.test.tsx`: `PageHeader` con nombre y `StatusTag` de membresía; acciones por rol con `useCan` (coach sin Dar de baja ni Reactivar; Editar y Vender con `members.update` y `memberships.sell`; Vender enlaza a `/membresias/vender?socio=`); migas; `Tabs` con Datos, Membresías, Pagos (enlaces a las rutas hijas; hasta F7 las rutas no existen y la pestaña se muestra deshabilitada con `disabledUntil`), Historial deshabilitada (US-106) y las demás por versión; aviso "Sin autorización de datos registrada" (`// DESIGN-GAP:` Q16); modo solo lectura del dado de baja con etiqueta "Dado de baja" y "Reactivar" solo con `members.reactivate`; 404 "Socio no encontrado"; error con reintento; `plan_name` y "vence" del API; los cinco campos enmascarados con el texto del API.
- `src/shared/ui/MaskedValue.reveal.test.tsx` (`fakeTimers`): una sola llamada por clic; re-enmascarado a los 60 s, al ocultar y al desmontar; 403 y 500 sin valor en pantalla; 429 muestra "Demasiadas consultas; espera un momento"; el claro nunca llega a `localStorage`, `sessionStorage` ni a la caché de TanStack Query: tras el re-enmascarado `queryClient.getMutationCache().getAll()` no contiene el valor ni `data` con él (S3-D52); un `ErrorBoundary` que lanza después de revelar no deja el valor en `document.body.innerHTML`.
- `MemberFormPage.edit.test.tsx`: campos no sensibles precargados; sensibles vacíos con su máscara como ayuda y botón "Cambiar" (el de documento solo con `members.document.update`; el coach no lo ve, y si lo enviara el 403 `forbidden_field` se muestra bajo el campo); solo envía `dirtyFields`; nunca muestra el claro; 409 con enlace a la ficha del duplicado; `data_consent` solo como casilla "Registrar autorización" visible si falta; `reset()` tras guardar.
- `DeactivateMemberModal.test.tsx`: texto "El socio deja de aparecer en la lista; sus membresías, pagos e historial se conservan"; errores del API; Reactivar con `ConfirmModal` y 409 `member_document_duplicated` con enlace.
- `src/routes.test.ts`: `/socios/:id` y `/socios/:id/editar` con `load`; la aserción "`/socios/:id` no se registra" se invierte; `src/config/routes.reference.ts` sin cambios (las rutas ya estaban).
- `tests/e2e/stack/member-detail.spec.ts`: crear socio por API, abrir la ficha, "Mostrar" documento (aparece y se re-enmascara al ocultar), editar el teléfono por la pantalla, dar de baja (solo lectura) y reactivar; coach en otra sesión no ve "Dar de baja".
- Confirmar el rojo.

**F1.3 · Verde**
Según el blueprint F1 con S3-D52 (`onReveal`: `const out = await mutation.mutateAsync(field); const plain = flattenRevealed(field, out); mutation.reset(); return plain;`), S3-D46 (campos del PATCH) y S3-D65 (`<Outlet>`; `MemberDataTab` es la ruta índice). `MaskedValue.tsx` sin cambios de comportamiento.

**F1.4 · Documentación**
`ROUTES.md`: `/socios/:id` (con `datos`, `membresias`, `pagos` como rutas hijas: las dos últimas llegan en F7) y `/socios/:id/editar`.

**F1.5 · Gate**
1. `slice-gate.sh web/shared src/shared/ui/MaskedValue.reveal.test.tsx src/shared/ui/MaskedValue.test.tsx`.
2. `slice-gate.sh web/app src/routes.test.ts tests/lint/boundaries.test.ts tests/lint/no-reveal-cache.test.ts`.
3. Al final, para sellar: `slice-gate.sh web/members src/features/members/pages/MemberDetailPage.test.tsx src/features/members/pages/MemberFormPage.edit.test.tsx src/features/members/components/DeactivateMemberModal.test.tsx src/features/members/schemas.test.ts`.

**F1.6 · Docker**
`$DC build web && $DC up -d web`; E2E `stack/member-detail.spec.ts` (demo 6 por la pantalla).

**F1.7 · Checkpoint**
`"S3-F1 ficha del socio con reveal auditado, edición, baja y reactivación"`.

### S3-F7 · Pestañas Membresías y Pagos de la ficha

- **Historias:** US-093 y US-101 (front).
- **Depende de:** B11, F1, F4 y F5.
- **Cierra:** condición 8 (rutas hijas), demo 6 (botones de la ficha), S3-D65.

**F7.1 · Rebase y stubs**
`shared/data/memberships.ts`: `useMemberMemberships(memberId, page, q?)`; `shared/data/payments.ts`: `useMemberPayments(memberId, {voided, limit, offset})`; `features/memberships/lib/rules.ts`: `membershipActions(memberships, role, today, memberDeleted)`; `features/memberships/components/MemberMembershipsTab.tsx`; `features/payments/components/MemberPaymentsTab.tsx` (S3-D65: vive en `payments`, no en `members`); `routeTable.ts` y `config/routes.reference.ts`: rutas hijas `/socios/:id/membresias` y `/socios/:id/pagos` con `load` y `feature` `memberships` y `payments`.

**F7.2 · Rojo**
- `MemberMembershipsTab.test.tsx`: tarjeta de la vigente (plan, fechas, días restantes, clases, precio, pagado y saldo, `StatusTag`, congelaciones) "Por vencer"; tarjeta de la futura "Pendiente de pago" (`// DESIGN-GAP:`); historial paginado; botones de `membershipActions` (Renovar a `/membresias/vender?socio=&renovar=1`, Vender, Congelar abre `FreezeModal`, Anular abre `CancelMembershipModal` solo admin; "Registrar saldo" enlaza a `?pago=`); nada para un dado de baja; vacío "Este socio no tiene membresías. Vender".
- `lib/rules.test.ts`: `membershipActions` en todas las ramas (vigente, vencida sin futura, con futura, dado de baja, coach/admin).
- `MemberPaymentsTab.test.tsx`: orden descendente; "Anulado" con motivo; "Retroactivo"; conmutador "Ocultar anulados"; "Registrar pago" enlaza a `?pago=nuevo&socio=` y se oculta si el socio está dado de baja; "Anular" solo con `payments.void` y abre `VoidPaymentModal`; vacío "Este socio no tiene pagos".
- `src/routes.test.ts`: las dos rutas hijas con `load`; `MemberDetailPage.test.tsx`: las pestañas Membresías y Pagos navegan y montan el `<Outlet>`.
- Confirmar el rojo.

**F7.3 · Verde**
Según el blueprint F7 con S3-D65.

**F7.4 · Documentación**
`ROUTES.md`: rutas hijas de la ficha.

**F7.5 · Gate**
1. `slice-gate.sh web/shared src/shared/data/memberships.test.ts src/shared/data/payments.test.ts`.
2. `slice-gate.sh web/app src/routes.test.ts tests/lint/boundaries.test.ts`.
3. `slice-gate.sh web/payments src/features/payments/components/MemberPaymentsTab.test.tsx`.
4. `slice-gate.sh web/members src/features/members/pages/MemberDetailPage.test.tsx`.
5. Al final, para sellar: `slice-gate.sh web/memberships src/features/memberships/components/MemberMembershipsTab.test.tsx src/features/memberships/lib/rules.test.ts`.

**F7.6 · Cierre del front (wave 5)**
`cd web && npm run lint && npx tsc --noEmit && npm test -- --run --coverage && npm run build && npm run licenses`; `npx playwright test --project=preview` completo; `$DC build web && $DC up -d web` y `npm run e2e:stack` completo contra 8180 (las nueve specs del Sprint 2 más las cuatro nuevas); `git diff --exit-code src/core/api/types.ts` tras `npm run gen:api` (sin deriva).

**F7.7 · Checkpoint**
`"S3-F7 pestañas de membresías y pagos de la ficha; cierre del front"`.

## 7. Validación del sprint

**V1 · Fusión**
Fusionar la rama del worktree del front en la rama del sprint (como `6511f47` del Sprint 1). Resolver `docs/openapi.json` y `types.ts` a favor del backend; volver a correr `npm run gen:api` y `types.contract.test.ts`. Pasar a `docs/BRECHAS.md` §10 los DESIGN-GAP de `docs/scratch/sprint-03-front.md`. `git worktree remove` del worktree del front.

**V2 · Stack desde cero de código**
1. `$DC build api web && $DC up -d` (los `Dockerfile` cambiaron en W0-1: las imágenes se reconstruyen de verdad, no de caché del Sprint 2); anotar los ids de imagen.
2. `$DC run --rm tools init-keys` (idempotente).
3. Esperar `healthy`; `$DC exec api alembic current` = `0011_payments_immutability (head)`.
4. Ciclo completo en `apex-db-1`: `downgrade 0007_plans` → `upgrade head` → `current`; `uv run alembic heads` una sola. Los datos de desarrollo de B1 a B11 se pierden con el `downgrade`: V3 los vuelve a crear por la pantalla y por API.
5. `$DC logs --tail 50 api`: migraciones aplicadas con el `SET LOCAL` de W0-2 y sin errores.

**V3 · Datos reales antes de navegar**
- Credenciales: `E2E_ADMIN_EMAIL` y `E2E_ADMIN_PASSWORD` desde la shell del operador (S3-D64); si faltan, `$DC run --rm tools issue-reset-link <admin> --as <admin>` y restablecer por `/restablecer/<token>`.
- psql (`-h 127.0.0.1 -p 5442 -U apex`): `SELECT id, email, role FROM auth.users WHERE deleted_at IS NULL`; `SELECT key, version FROM settings.settings_sections` (incluida `payment_methods` si se guardó); `SELECT name, price_cop, duration_days FROM plans.plans WHERE deleted_at IS NULL` (debe existir "Mensual" 120.000/30; si no, crearlo por API).
- Crear por API los socios de la demo: `demo-venta`, `demo-parcial`, `demo-renovar`, `demo-congelar`, `demo-ficha` (documentos aleatorios), y guardar sus ids en la shell.

**V4 · E2E contra el stack**
- Apilar `infra/compose.e2e.yml` y el bloque de topes altos en `.env` (E5 del Sprint 2: `LOGIN_IP_LIMIT=1000` y demás) solo durante V4; `$DC -f infra/compose.e2e.yml up -d api web`.
- `cd web && E2E_BASE_URL=http://localhost:8180 npm run e2e:stack`: las nueve specs del Sprint 2 más `sell-with-payment`, `payment-void`, `member-detail` y `members-mobile`. Dos corridas seguidas, idempotentes (documentos aleatorios; 0 fallos, 0 flaky).
- `npx playwright test --project=preview`: todas, con las capturas a 320, 768, 1024 y 1440 px en claro y oscuro, y `members-mobile` a 390 y 320.
- Restaurar `.env` (comparar con `cmp` contra la copia) y `$DC up -d api web` sin `compose.e2e.yml`; seis fallidos de login dan `401 ×5, 429`.

**V5 · Rendimiento**
`cd api && uv run pytest -m perf -q` (con `TEST_DATABASE_URL`), dos corridas: `tests/members/test_list_perf.py` (1.000 socios, documento < 500 ms, `EXPLAIN` con `uq_members_document_idx_alive`, 5.000 ids en `any_`, latencia del login fallido), `tests/memberships/test_list_perf.py` (`status=expiring` < 500 ms, `summary` < 300 ms con 1.000 socios y 3.000 membresías), `tests/payments/test_list_perf.py` (10.000 pagos, `limit=25` < 500 ms, `summary` < 300 ms). Tiempos al cuaderno. Si `payments` falla, se crea `0014_payments_registered_by_idx` por P-MIG y se repite.

**V6 · Smoke con evidencia SQL**
Se guarda en el cuaderno:
- activación atómica: tras la venta con pago de V7 punto 1, `SELECT m.status, p.member_id = m.member_id FROM memberships.memberships m JOIN payments.payments p ON p.membership_id = m.id WHERE m.id = <id>` → `active | t`, y `SELECT action, table_name, subject_member_id FROM audit.audit_log WHERE subject_member_id = <socio> ORDER BY seq` → `insert memberships.memberships`, `insert payments.payments`, `update memberships.memberships`;
- reversión: tras la anulación de V7 punto 3, la membresía `pending_payment` con sus congelaciones y `end_date` intactos;
- `EXCLUDE`: `INSERT` crudo solapado → `23P01 ex_memberships_member_dates`;
- triggers: `UPDATE payments.payments SET amount_cop = 1` → `payments_immutable: column`; segunda anulación por SQL → `already_voided`; `DELETE`/`TRUNCATE` → rechazados; `UPDATE memberships.memberships SET status='active' WHERE status='cancelled'` → `memberships_identity`; `DELETE FROM memberships.memberships` → `memberships_no_delete`; `UPDATE memberships.membership_freezes SET days=1` → `membership_freezes_append_only`; `SET session_replication_role = replica; UPDATE payments.payments ...` → rechazado;
- ficha y reveal: `SELECT verb, purpose, count(*) FROM crypto.crypto_ops WHERE record_id = <socio> GROUP BY 1, 2` → `decrypt | mask | 5` y `decrypt | reveal | 1`; `SELECT action, after FROM audit.audit_log WHERE action='reveal'` → `{"field": "document", "ip": ...}` sin el valor; cero `decrypt` atribuidos a las listas (`SELECT count(*) FROM crypto.crypto_ops WHERE verb='decrypt' AND purpose IS NULL` = 0);
- `verify_chain` en verde sobre toda `audit.audit_log`;
- 503 `busy`: la demostración de W0-2.7 repetida sobre el stack final;
- `$DC logs api` sin documentos, teléfonos, referencias ni motivos (grep de los valores de V3).

**V7 · Demo (los 7 puntos de `SPRINT-03.md` con el texto corregido, por la pantalla en 8180)**
1. Vender "Mensual" a `demo-venta` con primer pago de $ 120.000 en efectivo desde `/membresias/vender?socio=`: queda "Al día"; en la base, la fila de `memberships`, la de `payments` con `member_id` copiado y las entradas de auditoría de V6.
2. `demo-parcial`: venta con $ 60.000 → "Pendiente de pago"; registrar $ 60.000 por el panel → "Al día"; un tercer pago de $ 1.000: la pantalla muestra "Este pago supera el saldo pendiente" y pide confirmación; sin confirmar, el API responde 409 `payment_exceeds_balance` (S3-C22); al confirmar, 201. Repetirlo en menos de 2 minutos: segundo modal de posible duplicado.
3. El admin anula el segundo pago de `demo-parcial` con motivo: vuelve a "Pendiente de pago"; `UPDATE payments.payments SET amount_cop = 1` falla por el trigger; anular dos veces da 409 `payment_already_voided` ("Otra persona lo anuló antes").
4. `demo-renovar` (vendida y pagada): "Renovar" muestra inicio = fin + 1 (Q1) y crea la futura; vender otra que se solape responde 409 `membership_overlap` y el `INSERT` crudo lo rechaza la `EXCLUDE`.
5. `demo-congelar` (al día): congelar 10 días extiende el fin; la segunda solo tras terminar la primera; la tercera responde 409 `freeze_limit_reached`; anular la membresía (admin, con motivo) y luego registrar un pago responde 409 `membership_cancelled`.
6. `demo-ficha`: el documento aparece como `CC •••• <4 dígitos>`; "Mostrar" deja una fila `reveal` y una `decrypt` con `purpose='reveal'`; el coach edita el teléfono pero no puede cambiar el documento (403 `forbidden_field`, también si lo envía igual, M-3); dar de baja deja la ficha en solo lectura con "Dado de baja"; reactivar la devuelve.
7. `/socios` filtra por estado y plan con conteos en los chips; a 390 px se muestra en tarjetas con "Cargar más"; `GET /payments/summary?month=<mes>` cuadra con `/pagos` filtrado por el mes y "Válidos".

**V8 · Repetición**
- `tools seed` dos veces: "omitido". `init-keys` dos veces. `export-openapi` dos veces: idénticas e iguales a `docs/openapi.json`.
- Las specs `stack` dos veces (V4). Anular el mismo pago dos veces por API: 200 y 409. Congelar la misma ventana dos veces: 200 y 409. `POST /members/{id}/memberships` con `renew: true` dos veces: 201 y 409 `future_membership_exists`.
- `SMOKE_KEEP=1 bash scripts/ci/compose-smoke.sh` en verde (genera su `.env.seed` efímero).

**V9 · Gates completos**
1. `bash scripts/workflow/run-gates.sh`: api `-m "not perf"` con cobertura global de `app` ≥ 80 % (esperado ≥ 93 %; `cli.py` y `worker/` siguen en `omit`), scripts de infraestructura incluido `test_images_pinned.sh`, web lint, tsc, pruebas con cobertura y build. Si la máquina se queda sin memoria en las pruebas del front (como en el Sprint 2), repetir solo la sección web con `npm test -- --run --coverage` y `npm run build` y anotarlo.
2. `cd api && uv run pytest tests/architecture -q`: 0 saltadas.
3. `uvx pre-commit run --all-files`.
4. `bash scripts/workflow/tests/run.sh`.
5. `bash scripts/ci/check-licenses-api.sh` y `cd web && npm run licenses`; `NOTICE` al día.
6. `npm audit --omit=dev --audit-level=high` (gate) y `npm audit --audit-level=high` (informativo, debe seguir en cero tras W0-1); `pip-audit` sobre `uv export --frozen --no-dev --no-emit-project`.
7. gitleaks sobre el historial (imagen por digest de `ci.yml`).
8. `bash scripts/ci/check-image-secrets.sh apex-api:local` y `bash scripts/ci/test_api_image.sh apex-api:local`.
9. `cd web && npm run gen:api && git diff --exit-code src/core/api/types.ts`.

**V10 · Revisión de seguridad posterior (`security-reviewer`, Fase 4)**
Verifica contra el código fusionado: la definición de hecho del sprint (pagos inmutables por API y por SQL; anular y cancelar solo admin; todo `reveal` auditado con `ip`; listas sin datos cifrados; montos `int`); H-1 a H-3, M-1 a M-10 y L-1 a L-13 con su slice de la sección 10; los riesgos aceptados registrados (S3-D44 reinicio del api, S3-D49 roles de base, S3-D50 texto en auditoría, S3-D68 sin CHECK de fechas de anulación); que ningún handler toma candados nuevos; que `USER_LIMITS` cubre todas las escrituras. Todo CRITICAL o HIGH se corrige dentro del sprint antes de cerrar, con el mismo esquema de tres agentes de la Fase 4 del Sprint 2.

**V11 · `verify-delivery`**
- Pilar 1: matriz N/M de las 25 historias, los 22 endpoints más los dos filtros, las 4 migraciones, las 10 condiciones para VERDE, H-1 a H-3, M-1 a M-10, L-1 a L-13, D-1 a D-5, la deuda heredada de §9.3 del Sprint 2 y las 22 contradicciones de contrato, cada fila con su evidencia (archivo de prueba, línea del cuaderno o consulta de V6).
- Desviaciones declaradas: W0 con dos slices; `core/db.py` y `core/errors.py` tocados (S3-D43); 503 `busy`; confirmación de sobrepago y duplicado en el servidor; `paid_at` por rol; B9 en dos checkpoints; orden del front por disponibilidad; `MemberPaymentsTab` en `features/payments`; sin CHECK `voided_at >= created_at`; sin 10.000 socios.
- Pilar 2: V2 a V8 contra el stack con las imágenes reconstruidas de api y web, una venta y una anulación reales hechas por la pantalla (V7 puntos 1 y 3), las specs `stack` dos veces, y la evidencia SQL de V6.

**V12 · Cierre y paso humano**
- Higiene: borrar `docs/scratch/sprint-03-antes-*.dump`; `git worktree list` solo el principal; `.env` idéntico a la copia previa; stack arriba sin `compose.e2e.yml`.
- `SPRINT-03.md`: sección "Estado al cierre" con conteos, cobertura, tiempos `perf` y desviaciones; `DECISIONES.md`: "Estado al cierre" por decisión que cambió.
- Push de la rama, PR con CI en verde (`api`, `web`, `images`, `scripts`, `secrets-scan`, `e2e-stack`) y merge: lo hace una persona.

## 8. Riesgos y mitigación

1. **[HIGH] Nudo de dependencias (bus transaccional, puerto G-03, handler de cobertura, trigger).** Slices pequeños en orden estricto; `test_service_import_graph.py` con D2 desde B1; `test_gates_registered` y el gate real desde B4; `test_handlers_no_new_locks` desde B1; `run-gates.sh` al cerrar cada wave; el doble del gate es opt-in y restaura.
2. **[HIGH] Trigger de `0011` demasiado estricto o laxo.** Una prueba por columna protegida y por columna de anulación, `incomplete_void`, doble anulación, `DELETE`, `TRUNCATE`, `UPDATE` sin cambios, comparación con `information_schema.columns` y `replica`; revisión por `database-reviewer` antes del Verde de B4; volcado previo y `downgrade` que no toca datos; limpieza con `DISABLE TRIGGER USER`.
3. **[HIGH] `EXCLUDE` frente a renovación anticipada, congelación que extiende y cancelación.** Pruebas con vigente más futura, congelada y extendida, cancelada; el código responde 409 antes y la restricción es la red; `lock_member` serializa por socio; `guard_identity` impide revivir una cancelada.
4. **[HIGH] Estado desfasado sin el job de vencimientos.** D5 con `status_expr` y la prueba de paridad en cada cambio de regla; el resumen en SQL usa el mismo `CASE`.
5. **[HIGH] Interbloqueo entre candado de socio, filas y cadena de auditoría; esperas sin tope.** Orden único de D3 con `lock_member` y `lock_membership` como únicas puertas (AST), `test_lock_order.py` con seis combinaciones y `lock_timeout` corto, tiempos de espera de la base y 503 `busy` (W0-2), regla de handlers sin candados nuevos.
6. **[MEDIUM] El doble del gate oculta un error del real.** `gate_doble` opt-in; `test_router_register.py`, `test_gates_registered.py` y toda prueba de activación usan el real.
7. **[MEDIUM] `status_expr` y `compute_status` divergen.** Prueba de paridad con malla; ambos en `memberships`; `resolve_member_status` como oráculo del `DISTINCT ON`.
8. **[MEDIUM] Contrato entre B9b y F2 con `memberRowSchema` estricto.** D35 en P-API paso 6: el campo entra al esquema del front en el mismo checkpoint del backend.
9. **[MEDIUM] Cruces de features en el front.** S3-D65 (`shared/data`, rutas hijas, host por `?pago=`); `boundaries.test.ts` corre en cada gate `web/app` de cada slice.
10. **[MEDIUM] Carrera vender frente a baja de plan y vender frente a baja de socio.** `get(for_share=True)` desde B1; `lock_member` en `deactivate`/`reactivate` (B10) con prueba concurrente; US-082 cierra el plan en el Sprint 4A.
11. **[MEDIUM] La caché del resumen devuelve datos viejos.** Invalidación por los siete eventos, TTL 30 s con el reloj de la app, fixture autouse de TTL 0 en pruebas, y `test_summary_cache.py`.
12. **[MEDIUM] La actualización mayor de vitest rompe la suite del front en W0-1.** Se arregla dentro del slice con la suite completa como gate; si no se puede, es un gate fallido con opciones (no se degrada a "informativo").
13. **[MEDIUM] `--reload` aplica migraciones a medias.** P-MIG detiene el api mientras se redacta; cada migración se prueba primero contra `db_test`.
14. **[MEDIUM] Divergencia de `types.ts` entre el worktree y la rama.** Solo el backend lo regenera; rebase antes de cada slice; V1 lo verifica.
15. **[MEDIUM] El `.env.seed` borrado deja al operador sin credenciales para V3.** Exportadas a la shell en W0-1; recuperación por `issue-reset-link` documentada (S3-D64).
16. **[LOW] `pending_payment` vieja bloquea ventas (D8).** Visible, anulable, acotada por `start_date_too_far`.
17. **[LOW] Última escritura gana en `PATCH /members`.** Sin control de versión en el contrato; `lock_member` evita cruces con la baja.
18. **[LOW] Reiniciar el api vacía los cupos de `reveal` (S3-D44) y el resumen cacheado.** Aceptado y documentado.
19. **[LOW] Texto libre inmutable en la auditoría (S3-D50).** Patrón de referencia y avisos; supresión en US-119.
20. **[LOW] Las tres pruebas saltadas por NTFS se verifican en el job `api` de CI (Linux), como en el Sprint 2.**

## 9. Rollback por migración

Regla general (como el Sprint 2):
1. Bajar la migración primero: `$DC exec api alembic downgrade <revisión anterior>`.
2. Después revertir el checkpoint del slice con `git revert <sha>`.
3. Después `$DC restart api`.

Si se revierte primero el código, el archivo de migración desaparece y el arranque falla con "Can't locate revision". Antes de cada migración se guarda `docs/scratch/sprint-03-antes-<rev>.dump` (P-MIG paso 1, solo esquemas `memberships` y `payments`); restaurar es `pg_restore --clean -n memberships -n payments` sobre `apex-db-1` con el api detenido. Orden de bajada en cadena: `0011 → 0010 → 0009 → 0008 → 0007_plans`.

- **`0011_payments_immutability`:** `downgrade 0010_payments` ejecuta `DROP TRIGGER payments_forbid_mutation ON payments.payments`, `DROP TRIGGER payments_forbid_truncate ON payments.payments` y `DROP FUNCTION payments.forbid_mutation()`; no toca filas. Se revierten B4 y posteriores (B5 a B11 y el front que los usa). Sin el trigger, `void` seguiría funcionando pero la inmutabilidad quedaría solo en el código (`test_payments_immutability_code`): no se opera así más que el tiempo del revert.
- **`0010_payments`:** `downgrade 0009_membership_freezes` borra los tres índices y `payments.payments` (solo datos de desarrollo). Se revierten B3 y posteriores; `MODULES` vuelve a seis entradas.
- **`0009_membership_freezes`:** `downgrade 0008_memberships` ejecuta `DROP TRIGGER membership_freezes_append_only`, `DROP TRIGGER membership_freezes_forbid_truncate`, `DROP FUNCTION memberships.forbid_freeze_mutation()`, el índice y la tabla. Se revierten B2 y posteriores (las congelaciones registradas se pierden; `end_date` extendido queda en `memberships`).
- **`0008_memberships`:** `downgrade 0007_plans` ejecuta `DROP TRIGGER memberships_guard_identity`, `DROP TRIGGER memberships_forbid_delete`, `DROP TRIGGER memberships_forbid_truncate`, `DROP FUNCTION memberships.guard_identity()`, `DROP FUNCTION memberships.forbid_delete()`, los tres índices y la tabla (la `EXCLUDE` cae con ella); nunca el esquema (`0001`) ni `btree_gist`. Se revierten B1 y posteriores; `MODULES` vuelve a cinco.
- En CI y `db_test` no hace falta rollback: `migrated_database` migra desde cero y `test_downgrade_a_base_vacia_y_vuelta_a_head` ejercita los cuatro `downgrade` en cada corrida.
- W0-2 no tiene migración: su rollback es `git revert` del checkpoint y `$DC up -d api`; las variables `DB_*_TIMEOUT_MS` tienen default y pueden quedar en `.env`.

## 10. Trazabilidad

### Condiciones para VERDE del impacto (10)

1. Pruebas de arquitectura del Sprint 2 y `env.py`: B1.1, B1.3 (`test_audit_module`, `test_service_import_graph`, `test_audited_tables`, `test_0007_plans`), B2.3 (`membership_freezes`), B3.1 y B3.3 (`payments`), B9b.2 (par perezoso `members -> memberships` en uso; la aserción de lista vacía se quitó en B1).
2. Routers con `no_store`, `responses_for`, `SessionDep`, `current_clock()`, 429 solo con límite y en `CON_LIMITE`: W0-2 (`enforce_user_limit`, `StaffDep`/`AdminDep`, `test_user_limits_catalog`), B1 a B11 (cada ruta), B9b (el 429 del router de `members` baja a sus rutas).
3. Contratos que chocan con pruebas: B3 (`{items}`), B11 (`q` en las anidadas), W0-1 y B7 (`perf`).
4. T-DOC de nombres: W0-1.2 (S3-C1 a S3-C22); `active_ids` en B7 (S3-D60).
5. Limpieza y dobles: B1.1 (`LIMPIAR_MEMBERSHIPS`), B3.1 (`LIMPIAR_PAYMENTS`, `gate_doble`), B1.1 y B3.1 (fábricas), B10.2 (`test_no_physical_delete` solo `src/`).
6. Partición de services: B1.2 (`memberships` partido), B3.2 (`payments` partido), B9a (`members`).
7. Pruebas ajenas del front y de settings: B3.1 (`NO_HABILITADAS`), F4 (`ConfigPage.test.tsx`), F1 (`routes.test.ts` `/socios/:id`), F3/F4/F5/F6 (`features.test.ts`, `nav.test.ts`, `routes.test.ts`).
8. Front sin cruces: S3-D65, fijado antes de F3 (primer slice del worktree) y vigilado por `boundaries.test.ts` en todos los gates `web/app`.
9. P-API y P-MIG en cada slice; `alembic heads` en P-MIG paso 5; ciclo en `apex-db-1` en B1, B2, B3, B4 y V2; `pg_dump` antes de `0011` (y de las otras tres).
10. `build web` antes de E2E y demos (sección 0 y cada F); `build api` solo en W0-1 (Dockerfile) y V2; digests y `npm audit` de desarrollo decididos en S3-D62 y S3-D63 y hechos en W0-1.

### Revisión de seguridad del diseño

- **H-1:** B3 (regla y esquema), B4 (`sell`), F3 y F4 (modales y reenvío).
- **H-2:** W0-2 (helper y catálogo), B1 (`sell`), B2 (`freeze`), B3 (`register`, tope de 60), B5 (`void`), B6 (`renew`, `cancel`).
- **H-3:** W0-2 (puntos 1 y 2), B1 a B6 y B10 (`test_lock_order`), B1 (`test_handlers_no_new_locks`), nota para US-082 en DECISIONES.
- **M-1:** B10. **M-2:** W0-2 (`PII_SEARCH_BUCKET`), B7, B8, B9b. **M-3:** B10. **M-4:** B1, B3, B7, B8. **M-5:** B1, B2. **M-6:** B1 (`ENABLE ALWAYS` en `0008`, `test_no_trigger_tampering`), B2, B4; roles de base a S4B-W0-2 (registrado). **M-7:** B3, F3, F4, F5. **M-8:** B3, B5, B8, F4 (mensaje). **M-9:** F1, F2, F3, F4, F5. **M-10:** B7.
- **LOW:** L-1 en B1 y B10; L-2 en B8; L-3 en B3; L-4 en B1; L-5 en B4 y B5; L-6 en B1; L-7 en B10; L-8 en W0-1 y B4 (P-MIG); L-9 en B7; L-10 en B1, B2, B4 (sin el CHECK, S3-D68); L-11 en B1; L-12 en B10; L-13 en B8. Ninguno se difiere.
- **Duplicación D-1 a D-5:** W0-2 (D-1, D-2, D-5), B1 (D-3), B9b (D-4).

### Riesgos de integración de la exploración (sección 4)

1 → B7 (D5, `status_expr`); 2 → B1 (`lock_member`, D3), W0-2 (tiempos), B1 a B6 (`test_lock_order`); 3 → B1, B3 (partidos), B9a; 4 → B1 (D2); 5 → B4; 6 → B1, B3 (limpieza); 7 → B3, B4 (`flush` antes de `emit`); 8 → B1 (`MemberNotFound` reutilizado, `PlanInvalid`/`PlanInactive`); 9 → B3, B11; 10 → B9b (`any_`/`all_`); 11 → B9b (D35) y F2; 12 → B9b (D20); 13 → B10 (D19); 14 → B10 (`reactivate` y documento); 15 → B10 (`update` recifra); 16 → F1 (`flattenRevealed`); 17 → B2; 18 → B3 (D17); 19 → P-API en todos; 20 → B1 (`test_0007_plans`); 21 → B1 y B4 (SQL literal); 22 → B8 (`perf`).

### Riesgos de `SPRINT-03.md`

1 → sección 8 punto 1; 2 → B4 y sección 8 punto 2; 3 → B6 y B2; 4 → B1 (`for_share`) y B10 (`lock_member`); 5 → B3 y B4 (`gate_doble` opt-in).

### Deuda heredada del Sprint 2 (`sprint-02-verify-delivery.md` §9.3 y revisión de Fase 4)

- Caso `reveal` de `test_no_sensitive_in_logs` y `test_reveal_entry` a la fábrica: B10.
- Enlace del 409 a `/socios/{id}`: B9b y F1.
- Imágenes base por digest y su renovación: W0-1 (S3-D62).
- Dependencias de desarrollo del front con hallazgos de `npm audit`: W0-1 (S3-D63).
- `.env.seed` que seguía en disco (bug 1 del impacto): W0-1 (S3-D64).
- `payment_methods` (US-056): B3.
- T8 de US-018 (`test_logging_redact` con `reveal` real): B10.
- Higiene de volcados y worktrees: V1 y V12.

### Lo único que pasa al Sprint 4A o 4B (con dueño)

- "Socios con él" de `Planes.html` y `count_active_by_plan` visible en `PlanOut`: US-082 (Sprint 4A); `BRECHAS.md` corregido en W0-1.
- Job diario de vencimientos y los eventos `MembershipExpiring`/`MembershipExpired`: US-094 (Sprint 4A). D5 cubre las lecturas mientras tanto.
- Historial de la ficha y las congelaciones sin `subject_member_id`: US-106 (Sprint 4A).
- `display_name` de usuarios (reemplaza el correo parcial): US-110 (Sprint 4A).
- Separación de roles de base de datos (rol de aplicación sin `DELETE`/`TRUNCATE` sobre `payments`, `audit` y `crypto_ops`): S4B-W0-2 (S3-D49).
- `remote_addr` real y p99 del login en el servidor del gimnasio: S4B-W0-2 (sin cambio).
- `pg_trgm` o columna normalizada para la búsqueda por nombre: Sprint 4A (sin cambio).
- `omit` de `cli.py` y `worker/` en la cobertura: US-113 (Sprint 4A).
- `plans.update` sin bloquear filas de `memberships` (nota de H-3 punto 5): US-082.
- Proceso de supresión de datos en la auditoría inmutable (S3-D50): US-119.

### Conteo

- **Slices:** 20. W0-1, W0-2; B1, B2, B3, B4, B5, B6, B7, B8, B9a, B9b, B10, B11; F1, F2, F3, F4, F5, F6, F7.
- **Pasos:** 150.
  - Wave 0: W0-1 9, W0-2 8.
  - Backend: B1 11, B2 10, B3 10, B4 10, B5 7, B6 7, B7 8, B8 7, B9a 4, B9b 8, B10 8, B11 8.
  - Front: F3 8, F4 7, F5 7, F6 7, F2 7, F1 7, F7 7.
- **Validación:** 12 pasos (V1 a V12).
- **Checkpoints:** 20.
- **Migraciones:** 4 (`0008` a `0011`), más la condicional `0014_payments_registered_by_idx` solo si V5 la exige.
- **Endpoints:** 22 nuevos más los filtros `membership_status`, `plan_id` de `GET /members`; `503` declarado en toda operación con rol.
- **Pruebas de arquitectura nuevas:** 13 (`test_user_limits_catalog`, `test_no_trigger_tampering`, `test_sql_literals_constant`, `test_guarded_calls`, `test_handlers_no_new_locks`, `test_payment_method_codes`, `test_gates_registered`, `test_payments_immutability_code`, `test_no_cross_schema_sql`, `test_reveal_single_door`, `test_no_physical_delete`, `test_events_without_pii`, más la consolidada `test_service_import_graph` reescrita).
- **Decisiones del bloque "Sprint 3":** D1 a D40 con opción elegida, S3-D41 a S3-D59 de seguridad, S3-D60 a S3-D74 de este plan y S3-C1 a S3-C22 de contrato.
