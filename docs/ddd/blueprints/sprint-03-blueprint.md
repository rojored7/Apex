# Blueprint de implementación · Sprint 3 · Núcleo comercial: membresías, pagos y ficha del socio

> Corregido por `sprint-03-plan.md`, decisiones D3, D12, D13, D17, D19, D21, D26, D27 y S3-D60 a S3-D74 (más S3-D75 a S3-D78 y las enmiendas E1 a E16). Donde este plano y el plan chocan, manda el plan; el registro con la opción final está en `docs/ddd/DECISIONES.md`, "Sprint 3 · decisiones de implementación".

- Rama: `feat/sprint-03-membresias-pagos`, desde `d65056e` (= `main`, cierre del Sprint 2). Última migración aplicada: `0007_plans`.
- Entradas: `CLAUDE.md`, `SPRINT-03.md`, el blueprint del Sprint 2, `02_domain_model.md`, `03_context_map.md`, `05_service_design.md`, `DECISIONES.md` (Q1 a Q28, N-01 a N-50, G-01 a G-10, S2-D1 a S2-D53, S2-R1 a S2-R11), `BRECHAS.md`, `docs/design/` (DESIGN, ROUTES y las pantallas `Socio_Ficha`, `Socios_Lista`, `Socios_Movil`, `Membresias`, `Membresia_Vender`, `Pagos`), los desgloses de US-056, US-071 a US-076, US-083 a US-093 y US-095 a US-101, `sprint-03-exploracion.md` y el código real de `api/src/app`, `api/tests` y `web/src`.
- Este archivo es solo un plano. No cambia código. Donde el desglose, el plan del sprint y el código chocan hay una **DECISIÓN** con la opción elegida y el motivo. Las que se acepten se copian a `docs/ddd/DECISIONES.md` (sección "Sprint 3") en el primer checkpoint, igual que hizo el Sprint 2.

## 0. Cómo leerlo

1. Sección 1: decisiones D1 a D40. Leerlas antes de escribir un Rojo.
2. Sección 2: reglas transversales (backend, front, pruebas) y estructura de archivos por módulo.
3. Sección 3: orden de ejecución y dependencias entre slices.
4. Sección 4: slice por slice del backend (W0 y S3-B1 a S3-B11).
5. Sección 5: slice por slice del front (S3-F1 a S3-F7).
6. Sección 6: flujos de datos.
7. Sección 7: pruebas de arquitectura (nuevas y cambios a las existentes).
8. Sección 8: fixtures y fábricas.
9. Sección 9: mapa endpoint a front.
10. Sección 10: riesgos y puntos abiertos.

Convención de cada slice (la del Sprint 2): Rojo (stubs que lanzan `NotImplementedError` y pruebas que fallan), Verde (implementación) y Gate (`bash scripts/workflow/slice-gate.sh <modulo> <archivos de Rojo>`, que añade `tests/architecture`). En todo slice backend que toque rutas o esquemas se regenera `docs/openapi.json` (`cd api && uv run python -m app.cli export-openapi ../docs/openapi.json`) y, en el mismo checkpoint, `cd web && npm run gen:api` (la prueba `types.contract.test.ts` falla si `types.ts` no coincide con el contrato). Los parámetros de ruta se llaman `{member_id}`, `{membership_id}` y `{payment_id}` (como `{plan_id}` y `{user_id}` en el Sprint 2); `ROUTES.md` los llama `:id`.

## 1. DECISIONES

### Puerto, grafo de services y transacciones

**D1 · Puerto `MembershipGate` (G-03): quién lo define, quién lo registra y en qué orden carga `main`.**
- Se define en `payments/service.py` (no en `memberships`): `MembershipPayability(exists: bool, cancelled: bool, member_id: UUID | None)` (dataclass congelada), `MembershipGate = Callable[[AsyncSession, UUID], Awaitable[MembershipPayability]]`, `set_membership_gate(gate: MembershipGate | None) -> None` y `membership_gate() -> MembershipGate | None`. `register` y `void` llaman al gate; sin gate lanzan `MembershipGateNotRegistered` (un `RuntimeError`, sale como 500 sin datos): falla cerrado, nunca registra un pago sin validar.
- Lo registra `memberships/service.py` (la fachada) con una línea al final del archivo: `payments_service.set_membership_gate(membership_payability)`. `membership_payability` es un adaptador de seis líneas sobre `sell.get_payment_target` (S3-B1, el nombre que usa el plan del sprint; devuelve un `PaymentTarget` local), que toma `SELECT ... FOR UPDATE` de la fila de la membresía con `populate_existing=True`. En B1 `payments` aún no existe: el adaptador y el registro llegan en B4.
- Orden en `main.py`: `MODULES = ("auth", "settings", "audit", "members", "plans", "memberships", "payments")`. `memberships.service` importa `payments.service` arriba del archivo (sentido mayoritario: `sell` registra el primer pago y `list/get` piden sumas), así `payments` ya está cargado cuando `memberships` registra el gate. `payments` nunca importa `memberships` a nivel de módulo.
- `main.load_module_services()` lo usan `create_app`, el CLI (`_load_module_services`) y `tests/conftest.py` al importarse; el worker (Sprint 4A) lo llamará igual. `test_gates_registered.py` fija que tras `create_app(...)` y tras `cli._load_module_services()` el gate es `memberships.service.membership_payability` y que `register` sin gate falla cerrado.
- El doble de pruebas (`gate_doble`) es una fixture opt-in de `tests/payments/conftest.py`: guarda el gate real, registra el doble y lo restaura al salir. No es autouse, porque la prueba de router de `POST /memberships/{id}/payments` (S3-B4) y `test_gates_registered` necesitan el gate real (riesgo 5 del sprint).

**D2 · Lista blanca de imports perezosos y forma del grafo (`test_service_import_graph.py`).**
- Hoy la prueba arma un solo grafo con aristas de nivel de módulo y perezosas y exige que sea acíclico. Con `memberships -> payments` (arriba) y `payments -> memberships` (perezosa) ese grafo tendría un ciclo, que es justo lo que G-03 permite. Se cambia: el acíclico se exige sobre las aristas de **nivel de módulo**; las perezosas se validan aparte contra `LAZY_IMPORT_WHITELIST`. Como `memberships` ya importa `members`, `plans` y `settings` en B1, el cambio entra en **S3-B1** (el plan del sprint lo ponía en B4; esta prueba corre en todos los gates y la exploración confirma que falla desde B1).
- Aristas de nivel de módulo (`ALLOWED_EDGES`, además de `audit -> auth` y `auth -> settings`): B1 trae `memberships -> members` (`get_ref`, `ensure_exists`, `search_ids`, `names_for`; B7 agrega `active_ids`), `memberships -> plans` (`get(for_share=True)`, `names_for`) y `memberships -> settings` (`memberships_policy`). B3 trae `payments -> members` (`search_ids`, `ensure_exists`), `payments -> auth` (`names_for`) y `payments -> settings` (`payment_methods`). B4 trae `memberships -> payments` (`register`, `sum_not_voided`, `sums_not_voided`, eventos, puerto y `PaymentIn`). Cada slice amplía el conjunto con su propia arista.
- Perezosas (dentro de una función, con comentario `# lazy: G-03`): `LAZY_IMPORT_WHITELIST = {("payments", "memberships"), ("members", "memberships"), ("plans", "memberships")}`. En el Sprint 3 se usan las dos primeras (`payments.queries` pide `refs_for`; `members` pide `status_for` y `member_ids_by_status`). `plans -> memberships` queda declarada porque la lista de CLAUDE.md la nombra y US-082 (Sprint 4A) la usa. Una prueba fija que la lista blanca es exactamente esa.
- `test_plans_no_agrega_aristas` (hoy exige `grafo["plans"] == set()` y que nadie importe `plans`) se reescribe: `plans` no importa ningún service y el único que importa `plans.service` es `memberships`. La aserción `frozenset() == LAZY_IMPORT_WHITELIST` se quita.
- Cada `service.py` se importa en un subproceso limpio y en los dos órdenes (`python -I -c "import app.modules.members.service, app.modules.memberships.service"`), como pide el DoD de US-071.

**D3 · `sell` en una sola unidad atómica, con savepoint y orden único de candados.**
- Orden de candados (único, para no abrir interbloqueos): (1) `pg_advisory_xact_lock(hashtextextended(member_id::text, 0))`; (2) `FOR SHARE` del plan (`plans.service.get(for_share=True)`, ya existe); (3) fila de la membresía, `FOR UPDATE` con `populate_existing=True`; (4) fila del pago, `FOR UPDATE`, solo en `void`; (5) candado de la cadena de auditoría, que toma el hook al hacer flush y no se pide a mano.
- Invariante que lo hace seguro (el riesgo que señala la exploración, punto 4 del resumen): **ningún camino pide un candado de socio o de fila después de haber hecho flush de una tabla auditada en la misma transacción**, salvo sobre una fila que la transacción acaba de crear. En `sell` con primer pago el gate toma `FOR UPDATE` de la membresía recién insertada (nadie más la ve); el handler `on_payment_registered` vuelve a pedir esa misma fila (ya suya) y jamás pide el candado de socio. `register` y `void` toman la membresía antes de insertar o actualizar el pago. `freeze` toma el candado de socio primero (extender el fin puede chocar con una futura que otra petición está vendiendo) y después la fila; `cancel` toma la fila antes de escribir.
- Todo el cuerpo de `sell` corre dentro de `async with session.begin_nested():`. En producción el resultado es el mismo (una excepción revierte la petición entera), pero así "no queda ni membresía ni pago ni auditoría" se prueba dentro de la sesión con savepoint de `tests/conftest.py`, que no se puede cerrar con rollback.
- `sell` lee `settings.service.memberships_policy(session)` por dentro; el parámetro es `enforce_retroactive_limit: bool = True` (el CLI de importación, N-24, pasa `False`). Se aparta del texto `sell(..., max_retroactive_days)` de SPRINT-03 y de `05_service_design.md` porque el router no debe llamar a `settings` (un router, un service) y los services del repo ya leen su política (S2-D45). Se corrige esa línea de `05_service_design.md` en el mismo checkpoint.
- Los services toman el actor de `get_actor()` y la hora de `current_clock()` (como `members.create`); no reciben `by` ni `clock` como pide el desglose. El id del usuario en los routers es `principal.user_id`.

**D4 · `first_payment` reutiliza `payments.schemas.PaymentIn`.** US-085 pide un `FirstPaymentIn` propio sin importar `payments.schemas`. La regla 2 de módulos sí permite importar `schemas.py` de otro módulo y `memberships` ya depende de `payments`. Se usa `PaymentIn` (monto entero estricto, medio, referencia, `paid_at` con zona): una sola fuente, sin deriva de validadores; el `field` del 422 de forma sale solo (`first_payment.amount_cop`). El 422 semántico (`paid_at` futuro) lo lanza `register` con `field="paid_at"` y `sell` lo re-lanza con `field="first_payment.paid_at"` usando la pura `prefix_field`.

**D5 · Lectura de estado derivada de la fecha (el job de US-094 es del Sprint 4A).**
- El desglose dice que las lecturas devuelven el estado guardado y que el job lo corrige con el tiempo, pero el job diario no entra hasta el Sprint 4A (la exploración lo marca como el punto 1). Sin él, una membresía `active` se quedaría "Al día" para siempre y el filtro "Por vencer" estaría vacío.
- Elegido: `compute_status` ya ignora el estado guardado salvo `cancelled` y `pending_payment` (orden RN-06: cancelada, pendiente, congelada, vencida, por vencer, al día). Toda lectura del Sprint 3 calcula el estado con `compute_status(snapshot, today, expiring_days, freezes)`: `list`, `get`, `status_for`, `summary`, `count_active_by_plan`, `classify_open`. Para filtrar en SQL (`GET /memberships?status=`, `member_ids_by_status`) existe `status_expr(today, expiring_days)` en `memberships/queries.py`: un `CASE` espejo de `compute_status` con un `EXISTS` sobre `membership_freezes`. Una prueba de paridad recorre una malla de fechas y congelaciones y exige que el `CASE` y la función pura coincidan.
- La columna `status` se sigue escribiendo en cada transición (venta, activación, reversión, congelación, anulación) con lo que da `compute_status`. En el Sprint 4A el job la refresca y emite `MembershipExpiring` y `MembershipExpired`. Hasta entonces nada lee el `status` guardado salvo para distinguir `cancelled` y `pending_payment`.
- Descartado: aceptar el desfase hasta el Sprint 4A. Daría una lista de socios incorrecta desde el primer vencimiento.

**D6 · Sin `relationship()`; congelaciones por lote.** No se declara ninguna relación entre `Membership` y `MembershipFreeze` (el desglose pedía `lazy="raise"`). Las congelaciones se cargan con `_load_freezes_for(session, ids) -> dict[UUID, list[FreezeWindow]]`, una consulta por lote: sin carga perezosa en sesión async y sin N+1. `compute_status` recibe siempre la lista (parámetro obligatorio, sin valor por defecto).

**D7 · Partición de archivos (tope de 800 líneas por archivo y 50 por función; S2-R10).**
- `memberships/` y `payments/` nacen partidos: fachada `service.py` con `__all__` y archivos privados (`rules`, `events`, `sell`, `lifecycle`, `queries` en memberships; `rules`, `events`, `queries` en payments). `PRIVATE_HELPERS` de `tests/architecture/_imports.py` gana `memberships`, `payments` y `members` con esos nombres, y `test_nadie_fuera_de_auth_importa_sus_helpers_privados` se generaliza a "nadie importa los privados de otro módulo".
- `members/service.py` (523 líneas hoy) no cabe con `get`, `reveal`, `update`, `deactivate`, `reactivate` y los filtros. Paso 0 de S3-B9, sin cambio de comportamiento: se extraen las puras y los tipos (`validate_member_input`, `compute_warnings`, `mask`, `classify_query`, `QueryPlan`, `LIKE_ESCAPE` y ayudantes) a `members/rules.py`, y `service.py` las re-exporta con `__all__` (las pruebas existentes importan todo desde `app.modules.members.service`). Los casos de uso nuevos van en `members/detail.py` (`get`, `reveal`) y `members/changes.py` (`update`, `deactivate`, `reactivate`). `PRIVATE_HELPERS["members"] = {rules, detail, changes}`.

### Memberships

**D8 · Q1, `EXCLUDE` y el día siguiente: `daterange` sobre columnas `date`.**
- `start_date` y `end_date` son fechas civiles de Bogotá (`date`), no instantes. La restricción es `EXCLUDE USING gist (member_id WITH =, daterange(start_date, end_date, '[]') WITH &&) WHERE (status <> 'cancelled')`, nombrada `ex_memberships_member_dates`. Con `'[]'` PostgreSQL normaliza a `[inicio, fin+1)`: una membresía que termina el 28 y otra que empieza el 29 son adyacentes y no se solapan; empezar el 28 sí. Con `tstzrange` habría que fijar una hora y mezclar zonas, y el día siguiente de Q1 dejaría de ser exacto. `btree_gist` ya está en `0001`.
- El código revisa antes (`classify_open`, `find_overlap`) para dar un 409 con `existing_id`; la `EXCLUDE` es la red frente a la concurrencia. Un `IntegrityError` con `violated_constraint(error) == "ex_memberships_member_dates"` (SQLSTATE 23P01) se traduce a `MembershipOverlap` en `sell` y a `OverlapsFutureMembership` en `freeze`. Una prueba inserta dos rangos solapados con SQL crudo y comprueba que `constraint_name` llega en la causa de asyncpg (la exploración pide verificarlo).
- Definiciones puras (sobre el estado efectivo de D5): *vigente* es `active`, `expiring` o `frozen` con `start_date <= hoy`; *futura* es `pending_payment` (cualquier fecha) o `active`/`expiring` con `start_date > hoy`. Vender sin `renew` con vigente o futura da 409 `membership_conflict` con `existing_id`; renovar con futura da 409 `future_membership_exists`; fechas que chocan con cualquier no cancelada (también vencidas) dan 409 `membership_overlap`.
- Riesgo asumido (Q1): una `pending_payment` vieja y sin pagar cuenta como futura y bloquea nuevas ventas hasta que un admin la anule. El 409 trae `existing_id` y la ficha ofrece Anular.

**D9 · Guardia de identidad en la base (cierra el riesgo de `payments.member_id`).** `0008_memberships` crea el trigger `memberships.guard_identity()` (`BEFORE UPDATE`): rechaza cambiar `member_id`, `plan_id` y `agreed_price_cop` (RN-04). Ningún endpoint los cambia; el trigger hace que la copia inmutable `payments.member_id` nunca se desvíe de la membresía. Error: SQLSTATE `23000` con `CONSTRAINT = 'memberships_identity'`. `register` copia `member_id` de `MembershipPayability.member_id` (el gate lo lee de la fila bloqueada); nunca viene del cuerpo (`PaymentIn` tiene `extra="forbid"`), y `0011` impide cambiarlo después.

**D10 · `pending_payment` (Q3).** Es un estado guardado y visible. `compute_status` no lo cambia por fecha. `STATUS_LABELS` del front ya trae "Pendiente de pago" con tono `warning`; en chips y tabla se deja el comentario `// DESIGN-GAP:` (el diseño HTML aún no lo dibuja). Una venta sin pago o con pago parcial nace y se queda `pending_payment`; solo `on_payment_registered` la activa (RN-03).

**D11 · Cobertura y activación.** `on_payment_registered` bloquea la membresía (`populate_existing`), pide `payments.sum_not_voided` (nunca confía en `event.amount_cop`) y, si estaba `pending_payment` y `covers(agreed, paid)`, fija `status = compute_status(replace(snapshot, status=ACTIVE), hoy, expiring_days, freezes)` con `hoy = to_bogota_date(event.occurred_at)`. Un pago sobre una `pending_payment` ya vencida la deja `expired` (pagada y vencida): caso aceptado. `register` hace `flush` antes de `emit` para que la suma vea el pago.

**D12 · Sobrepago (Q5).** El backend acepta el pago sin saldo a favor y sin regla nueva. El front calcula `saldo = agreed_price_cop - paid_cop` (ambos vienen en `MembershipOut`) y, si el monto lo supera, muestra `ConfirmModal` "Este pago supera el saldo pendiente en $ X" y solo envía al confirmar. En `sell` con primer pago la comparación es contra el precio del plan.

**D13 · Anular un pago (RN-02).**
- `void(payment_id, reason)`: lee el pago sin candado para saber `membership_id`, pide el candado de la membresía por el gate (`FOR UPDATE`), después `SELECT ... FOR UPDATE` del pago, `can_void`, asigna las cuatro columnas, `flush` y entonces `emit(PaymentVoided)`. El orden membresía, pago es el mismo de `register` y evita interbloqueos con `on_payment_voided`.
- Trigger de `0011`: `RAISE EXCEPTION 'payments_immutable: <motivo>' USING ERRCODE = 'integrity_constraint_violation', CONSTRAINT = 'payments_immutable'`. El error llega como `IntegrityError` y `violated_constraint(error) == "payments_immutable"` lo traduce a 409 `payment_already_voided`; no se busca texto en el mensaje. Los otros intentos (UPDATE de columna protegida, DELETE, TRUNCATE) nunca pasan por el service; las pruebas los hacen con SQL crudo.
- La corrección de un pago no tiene endpoint de "reemplazo": el front abre `RegisterPaymentPanel` con los datos precargados.
- Reversión: `on_payment_voided` revisa el estado **efectivo**. Si es `active`, `expiring` o `frozen` y deja de estar cubierta, pasa a `pending_payment` y conserva congelaciones y `end_date` (N-25); si es `expired` o `cancelled`, no cambia (US-087).

**D14 · Congelación (Q7, Q9, N-25).**
- `0009_membership_freezes`: una fila por congelación (`frozen_from`, `frozen_to`, `days`) con `EXCLUDE` por `membership_id` sobre `daterange(frozen_from, frozen_to, '[]')`. No hay columnas `frozen_*` en `memberships`.
- `apply_freeze(membership, freezes, frozen_from, frozen_to, limits, today, expiring_days) -> FreezeOutcome(window, new_end_date)` es pura y no muta. El fin se corre `days = (to - from) + 1` (RN-07), también si la ventana es futura. `freeze` rechaza con 409 `overlaps_future_membership` si `[start_date, new_end_date]` choca con otra no cancelada.
- Códigos HTTP (el desglose dice 422 para todo; la demo del sprint pide 409 en la tercera): 422 para entradas mal formadas (`frozen_from > frozen_to` con `field="frozen_to"`, `freeze_too_retroactive`, `freeze_outside_validity`); **409** para lo que depende del estado de la membresía (`membership_not_freezable`, `freeze_already_scheduled`, `freeze_limit_reached`, `freeze_days_exceeded`, `overlaps_future_membership`). Motivo: la misma entrada habría sido válida antes de otra congelación.
- `FreezeIn` no lleva `reason` y la tabla no tiene columna de motivo: el modal del diseño pinta "Motivo"; se omite con `// DESIGN-GAP:`.

**D15 · Clases (Q4).** `sell` copia `classes_total = classes_remaining = class_count` para planes por clases y deja ambos `NULL` para planes por días. Nada descuenta clases hasta `MemberCheckedIn` (v0.4). `compute_status` ya trata `classes_remaining == 0` como vencida y tiene prueba, aunque ningún flujo del Sprint 3 llegue ahí. `original_end_date` (US-160) no entra en `0008`.

**D16 · Fin de vigencia y precio en la pantalla de venta.** `compute_end_date = start_date + duration_days` (RN-05, N-23, fin inclusivo): 30 días dan acceso 31 días. `Membresia_Vender.html` dibuja "29 oct – 27 nov" para un plan de 30 días. Manda N-23 y el front dice "hasta el 28 nov 2026", nunca "30 días"; se anota `// DESIGN-GAP:`. Tampoco se construye "Precio pactado" editable: `SellMembershipIn` no tiene `agreed_price_cop` (un coach no puede fijarlo); el campo va de solo lectura.

**D17 · Dinero y texto.**
- `payments.amount_cop BIGINT` con `CHECK (amount_cop BETWEEN 1 AND 1000000000)` y `StrictInt` en `PaymentIn` con el mismo tope. El desglose proponía hasta `2**63-1`, que un `number` de JavaScript no representa; mil millones es el tope de `plans.price_cop` (S2-D32). `agreed_price_cop INTEGER`.
- `reference` es `SafeText` de 1 a 64. `reason` de anular pago o membresía es `SafeText` (S2-R7: un NUL llegaba a PostgreSQL como 500). `void_reason` de 1 a 500; `cancel_reason` de 5 a 500 tras recortar.
- `reference` es opcional en los tres medios (N-28); el asterisco del diseño de Nequi y Bre-B se ignora con `// DESIGN-GAP:`.

**D18 · Listas de membresías.**
- `GET /memberships?status=` acepta una lista separada por comas (`status=active,expiring`) validada por la pura `parse_status_filter` (422 `field="status"`), como pide US-091: con parámetros repetidos el `field` del 422 saldría como `status[0]`. Sin `status`, la lista excluye `cancelled`; con `status=cancelled` solo ellas. Orden `end_date, id`; la pestaña de la ficha usa `start_date DESC, id`.
- La fila trae `paid_cop` (`Membresias.html` pinta "$60.000 de $120.000 · abono"): `payments.service.sums_not_voided(session, ids) -> dict[UUID, int]`, una consulta agrupada por página. Contrato nuevo de `payments` que el desglose no tenía.
- `q` busca con `members.search_ids(q, include_deleted=True)` y filtra `member_id = ANY(:ids)`; sin ids, página vacía sin más consultas. Límite por usuario de 60 por minuto solo con `q` (L-1, igual que socios).
- `paginate` solo sirve para una entidad (`.scalars()`): la lista pagina `select(Membership)` con la condición `status_expr(...)` y completa nombres, congelaciones y sumas por lote después.

### Socios

**D19 · `reveal` (RN-13, Q6) y qué queda en cada bitácora.**
- Misma transacción: `types.reveal(socio, campo, "reveal")` (descifra con `aad = id` y deja un `decrypt` con `purpose='reveal'`, `data_class='member.<campo>'`, `record_id` del socio y `user_id` del actor en `crypto_ops`) y `core.audit.record(session, action="reveal", table_name="members.members", record_id=id, before=None, after={"field": campo}, subject_member_id=id)`. El nombre de tabla correcto es `members.members` (el desglose dice `members`; el hook y `test_reveal_entry.py` usan esquema.tabla). El valor nunca va a `after`.
- No se emite `SensitiveFieldRevealed`: el catálogo lo da a `audit` como suscriptor, pero escribir la fila desde un suscriptor obligaría a `audit -> members` y duplicaría la fila. Un campo vacío devuelve `value: null` y también se audita. Funciona sobre socios dados de baja (N-20).
- No hace falta el `commit()` explícito del desglose: `SessionDep` (`scope="function"`) confirma antes de enviar el cuerpo (S2-R8, N-1); si el rastro falla sale el envelope de error y el valor no viaja. Las filas `decrypt` de `crypto_ops` se conservan aunque haya rollback (`after_soft_rollback`).
- `POST /members/{member_id}/reveal` lleva límite por usuario de 30 por minuto (`members-reveal`): es la ruta de extracción masiva que el desglose dejó como mejora futura y cuesta una línea.

**D20 · La ficha enmascara descifrando en memoria con propósito `mask`, sin lote.** El desglose de US-073 pide `bus.op_context(...)` y un `bus.batch("decrypt")`. La primera no existe; la API real es `types.reveal(obj, campo, "mask")` (o `bus.decrypt(..., purpose="mask", record_id=...)`). Dentro de `bus.batch` el agregador pone `record_id = NULL`; se descarta el lote para conservar el socio en cada fila. Una ficha deja una fila `decrypt` con `purpose='mask'` por campo no vacío (hasta cinco) con `record_id` del socio, y ninguna fila `reveal`. El valor descifrado vive solo dentro de la función; no se guarda ni se loguea. Las listas no descifran nunca (N-01).

**D21 · Editar (N-20) y baja.**
- `PATCH /members/{member_id}`: `MemberPatch` (todos opcionales, `extra="forbid"`, `model_fields_set` distingue "no enviado" de `null`; `null` en nombres o documento da 422) y `update(session, member_id, patch, *, role)`; el router pasa `principal.role`. `ensure_can_change(fields, role)` lanza 403 `forbidden_field` con `field="document"` si no es admin. Las comparaciones usan el valor normalizado (un cambio solo de formato no cuenta ni audita). Sin cambios efectivos no hay `flush`, auditoría ni evento. Un socio dado de baja responde 409 `member_deactivated`. La carrera por documento la decide `uq_members_document_idx_alive` (409 con `existing_id`). No hay control de versión (el contrato no lo pide): gana la última escritura.
- Respuesta: `MemberDetailOut` enmascarado (descifra con `mask`) y `warnings` con `data_consent_missing` si `data_consent_at` es nulo.
- `DELETE` fija `deleted_at = ahora` y `status = 'inactive'`; no toca membresías ni pagos (N-20). `reactivate` limpia ambos y exige el documento libre (409 `member_document_duplicated` con `existing_id`) y emite `MemberUpdated(changed_fields=("deleted_at", "status"))`.
- La ficha de un dado de baja es de solo lectura. Backend: editar da 409; `sell` da 422 `member_inactive`; registrar un pago contra una membresía suya sigue permitido (la baja no anula membresías; el front oculta "Registrar pago" en esa ficha).
- `tests/architecture/test_no_physical_delete.py` reemplaza a `test_no_physical_delete_users.py` (se renombra y se amplía a `members`, `plans`, `auth`, `memberships` y `payments`).

**D22 · Filtros de `GET /members` por estado de membresía y plan (G-03, G-04).**
- `membership_status` (`active`, `expiring`, `expired`, `frozen`, `pending_payment`, `none`) y `plan_id`. `members.list` pide con import perezoso (par `members -> memberships` de la lista blanca) el conjunto de ids; no hay `JOIN`. El conjunto se aplica a la consulta externa con una sola condición `Member.id == any_(array ligado)`; para `none`, `Member.id != all_(...)` con la unión de los cinco estados. Nunca se usa `IN (...)` expandido: con miles de ids superaría el límite de 32.767 parámetros de asyncpg (una prueba usa 5.000 ids). Las ramas de `q` (subconsultas con su propia condición de baja) no se tocan, así `uq_members_document_idx_alive` sigue siendo el índice del `EXPLAIN` de `test_list_perf.py`.
- `plan_id` filtra por el plan de la membresía que determina el estado resuelto; con `none` y `plan_id` la página es vacía.
- Cada página se decora con una sola llamada `status_for(ids)` (hasta 200): `membership_status`, `plan_name` y `membership_end_date` (campo nuevo de `MemberRowOut`; la lista del diseño pinta "Vence"). Es profundidad 2 (G-04): `memberships` resuelve `plans.names_for`.
- `status_for` y `member_ids_by_status` usan el estado efectivo de D5 y `resolve_member_status` (prioridad de US-092: vigente, `pending_payment`, `expired`, futura `active`, `none`). `GET /members` sigue sin descifrar nada: cero filas `decrypt`.
- Los chips de estado se traducen con la pura `chip_to_filter` (siete chips; "Dados de baja" para admin y coach, N-20).

### Pagos y settings

**D23 · `GET /payments/summary` y el mes en Bogotá.** `parse_month("AAAA-MM")` y `month_bounds_utc` usan `zoneinfo` (`BOGOTA` de `core/clock.py`), no un desfase fijo: `2026-10` es `[2026-10-01T05:00Z, 2026-11-01T05:00Z)`. Una sola consulta con `SUM ... FILTER`. Sin `month`, el mes de `current_clock().today_bogota()` (la exploración advierte que no existe una función `today_bogota()` de módulo). La prueba de cuadre compara `total_cop` con la suma de `GET /payments` del mismo rango con `voided=false`.

**D24 · `payment_methods` como sección de settings con códigos fijos.** `PAYMENT_METHOD_CODES = ("cash", "nequi", "breb")` vive en `settings/schemas.py`; `PaymentMethodsSettings` tiene exactamente esas tres claves con `label` (1 a 30) y `hint` (hasta 120), defaults "Efectivo", "Nequi" y "Bre-B". Se agrega a `ENABLED_SECTIONS`, `SECTION_REGISTRY`, `SECTION_VIEWS` y `SECTION_DEFAULTS`, con rutas tipadas `GET/PATCH /settings/payment_methods` antes de la genérica (S2-D15). `settings.service.payment_methods(session)` devuelve los tres medios decorados en orden fijo. `test_payment_method_codes.py` compara las fuentes (settings, `Literal` de `payments.schemas`, `payments.models.PAYMENT_METHODS`, CHECK del modelo y de `0010`).

**D25 · `GET /payments/methods` no puede devolver un arreglo.** `test_list_routes_use_page_params` falla ante cualquier `GET` que responda `type: array`. La respuesta es un objeto `PaymentMethodsOut { items: [{code, label, hint}] }` (no `Page_...`, no pagina). Lo lee `usePaymentMethods()` del front.

**D26 · Filtros de pagos.** `from` y `to` (alias, `AwareDatetime`, rango `[from, to)`), `method`, `registered_by`, `voided` (tri-estado), `member_id`, `membership_id` y `q` (`lower(reference) = lower(q)` o `member_id = ANY(search_ids(q))`). Con `q` hay límite por usuario de 60 por minuto. `PaymentRow` agrega las fechas de la membresía (`membership_start_date`, `membership_end_date`; el diseño pinta "Mensual 29 oct–27 nov") pidiéndolas a `memberships.refs_for`. `registered_by_name` sale de `auth.names_for` (hoy el correo): lo ve el coach; riesgo bajo, anotado en la sección 10.

### Contrato, arquitectura y pruebas

**D27 · 429 por ruta y no por router.** `members/router.py` declara hoy `responses_for(401, 403, 429)` a nivel de router: toda ruta nueva de `members` publicaría 429 y `test_las_rutas_con_limite_declaran_429` (conjunto `CON_LIMITE`) fallaría. El 429 pasa a cada ruta que lo necesita. `CON_LIMITE` gana `get /api/v1/memberships`, `get /api/v1/payments`, `patch /api/v1/members/{member_id}` y `post /api/v1/members/{member_id}/reveal`. Las rutas con rol llevan `dependencies=[Depends(no_store)]` y `SessionDep`. Las rutas fijas se declaran antes que las de parámetro (`/memberships/summary`, `/payments/summary`, `/payments/methods`): un `{payment_id}` UUID que reciba "summary" daría 422, no 404.

**D28 · Rutas anidadas por socio.** `GET /members/{member_id}/memberships` y `GET /members/{member_id}/payments` viven en los routers de `memberships` y `payments` (con el path completo en el decorador) para que `members` no dependa de ellos. `test_list_rows_without_sensitive_fields.py` recorre todo `/api/v1/members...`: las filas de esas dos listas no declaran ningún campo de `SENSIBLES`. Las listas anidadas aceptan `q` por la prueba `test_list_routes_use_page_params` (la exploración, punto 3.1): `q` es real, no decorativa: en membresías filtra por nombre de plan (función nueva `plans.service.search_ids(session, q)`, con el mismo pliegue de tildes de `plans.list`; la arista `memberships -> plans` ya existe) y en pagos por referencia exacta sin distinguir mayúsculas.

**D29 · Marca de rendimiento.** SPRINT-03 y los desgloses dicen `-m slow`; `pyproject.toml` usa `--strict-markers` y solo registra `db` y `perf` (S2-D27). Se usa `perf`, fuera de los gates (`-m "not perf"`), con el paso informativo de CI y la corrida manual del cierre.

**D30 · Limpieza de pruebas y trigger de pagos.** `LIMPIEZA_DE_SESION` y el `finally` de `dos_sesiones` (`tests/conftest.py`) harían `DELETE FROM payments.payments`, que el trigger de `0011` rechaza. Se limpia como ya se hace con `audit.audit_log`: `ALTER TABLE payments.payments DISABLE TRIGGER USER`, `DELETE`, `ENABLE TRIGGER USER` (apaga también el de `TRUNCATE`), con guarda `to_regclass` mientras la migración no exista. Orden: pagos, congelaciones, membresías, socios, planes. `docs/scratch/*.dump` se agrega a `.gitignore` antes del volcado de S3-B4 (el volcado lleva blobs cifrados y llaves envueltas).

**D31 · Datos que salen de las listas.** Todas las listas de membresías, pagos y socios devuelven `{items,total,limit,offset}` y ningún dato cifrado. Los nombres (`first_name`, `last_name`) van en claro (RN-13). Los montos salen como enteros JSON.

**D32 · `auth.service.names_for` ya existe** (`auth/users.py`, re-exportada por `auth/service.py`; devuelve el correo). No hay trabajo. El nombre real (`display_name`) llega con US-110 (Sprint 4A).

**D33 · Reloj de las pruebas.** En las pruebas, "hoy" es 2026-10-21 (`reloj` = `T0` = 2026-10-21T15:00Z = 10:00 en Bogotá). Todos los casos de fechas de este plano se calculan con `reloj` y `FrozenClock`; ningún caso llama a `date.today()`.

**D34 · Excepciones y códigos de error.** Cada módulo tiene `exceptions.py` con una base (`MembershipError`, `PaymentError`) y códigos estables; ningún `message` repite valores del usuario. Los códigos nuevos entran a `web/src/core/api/errorCodes.ts` (`API_ERROR_CODES`) y `errorCodes.test.ts` los busca como literales en `api/src`.

**D35 · Compatibilidad del contrato entre slices.** Un slice backend que agrega campos a una respuesta regenera `docs/openapi.json` y `types.ts`; si la respuesta tiene un esquema Zod `.strict()` en el front (`memberRowSchema`, S2-F6), ese mismo checkpoint agrega el campo al esquema como opcional con valor por defecto, para que el front no quede en `invalid_response` entre S3-B9 y S3-F2. La lógica de pantalla llega en el slice de front.

**D36 · Features y rutas del front.** `ENABLED_FEATURES` gana `memberships` y `payments` (con S3-F3 y S3-F4); `features.test.ts` fija hoy el conjunto exacto de seis y `nav.test.ts` el menú. `routeTable.ts` ya declara `/socios/:id`, `/socios/:id/editar`, `/membresias`, `/membresias/vender` y `/pagos` sin `load`; cada slice les agrega su `load` y actualiza la lista de `routes.test.ts`. No hay acciones nuevas en `permissions.ts`: ya existen `members.reveal`, `members.update`, `members.delete`, `members.reactivate`, `members.document.update`, `memberships.view/sell/freeze/cancel` y `payments.view/register/void`. El desglose nombra `member.document.change` y `member.deactivate`; manda la matriz real.

**D37 · Diferencias deliberadas con el diseño** (todas con `// DESIGN-GAP:` en el código): chip "Pendiente de pago" (Q3); precio pactado de solo lectura; sin "Motivo" al congelar; referencia opcional; fin de vigencia por N-23; el filtro de estado de `Pagos` arranca en "Todos" (para que el pago recién anulado siga visible); sin "Exportar" ni recibo PDF (v0.2); conteos de los chips de socios con `GET /memberships/summary` (el de "Sin membresía" es el total menos la suma de los cinco estados); "Socios con él" de `Planes.html` no entra (necesita `plans -> memberships`, US-082).

**D38 · Documentación que el sprint corrige.** `DECISIONES.md` (sección Sprint 3 con D1 a D40), `03_context_map.md` (aristas de lectura `payments -> members`, `payments -> auth`, `payments -> settings` y la lista blanca), `05_service_design.md` (firmas reales de `sell`, `reveal`, `GET /payments/methods` como objeto), `BRECHAS.md` (sección 10: cierre del Sprint 3 y DESIGN-GAP nuevos), `RUNBOOK.md` (volcado previo a `0011`, restauración y cómo probar el trigger). La sección del puerto inyectado de ADR-001 se redacta en US-119. `CLAUDE.md` no cambia.

**D39 · `MemberCardList` sí se construye.** La exploración nota que `DataTable` ya cambia a tarjetas bajo 768 px. Pero `DataTable` pagina, y US-072 pide "Cargar más" acumulativo (`useInfiniteQuery`), chips desplazables dentro de su contenedor y botón flotante "Nuevo socio". `MembersListPage` usa `MemberCardList` bajo `MOBILE_QUERY` y `DataTable` en escritorio; las tarjetas reutilizan `StatusTag` y los tokens de `DataTable.module.css`.

**D40 · Pruebas ajenas que se rompen en silencio** (no están en el Rojo de ningún slice y fallan en el gate o en `run-gates.sh`):
- `tests/migrations/test_0007_plans.py`, prueba `..._y_es_head`: exige que `0007_plans` sea la única cabeza. Pasa a "está en la cadena hasta head", como se hizo con `0006`; cada migración nueva repite el cambio con la anterior.
- `tests/architecture/test_audit_module.py` fija la tupla exacta de `MODULES`.
- `tests/architecture/test_audited_tables.py` (`PENDING_AUDITED`), `test_settings_no_secrets.py` y `tests/settings/_apoyo.py` (`NO_HABILITADAS` y `RUTAS`: las ocho rutas de settings pasan a diez).
- `tests/members/_apoyo.py` (`CAMPOS_DETALLE`) y los esquemas de fila.
- `web/src/config/features.test.ts`, `web/src/routes.test.ts`, `web/src/layouts/nav.test.ts`, y los fixtures de fila en `web/src/test/members.tsx` y `web/tests/e2e/members.spec.ts` (el esquema de fila es estricto).

## 2. Reglas transversales

### Backend
1. Routers: validan, declaran rol con `require_role`, llaman a **un** service y devuelven; cero `select` en routers. Todo con `SessionDep`, `dependencies=[Depends(no_store)]` y `responses_for(...)` por ruta (D27). Listas con `Annotated[PageParams, Depends()]`, `q: SearchQuery = None` y `Page[T]`.
2. Un módulo solo llama a otro por su `service.py` (más `schemas.py` y `exceptions.py`); nunca `models`, `router` ni privados. Las aristas están en D2.
3. Eventos: dataclasses congeladas con `kw_only` que heredan `DomainEvent`, declaradas en el archivo privado `events.py` del emisor y re-exportadas por su `service.py` (L7). Los suscriptores importan de `service.py`; `subscribe` se llama al final del `service.py` del suscriptor.
4. Todo caso de uso async recibe `session` primero; actor con `get_actor()`; hora con `current_clock()`; "hoy" con `current_clock().today_bogota()`.
5. Las tablas auditadas se escriben por ORM (el hook las ve), con `begin_nested()` y `violated_constraint` para traducir carreras. Las lecturas pesadas (`sum`, `summary`) pueden usar Core.
6. Cada migración se prueba con `tests/migrations/test_<revision>.py` (columnas, CHECKs, índices, restricciones con SQLSTATE) y entra en el ciclo `alembic upgrade head`, `downgrade -1`, `upgrade head`. Cada `downgrade` es simétrico: borra triggers y funciones antes que la tabla y nunca el esquema (`0001` lo gestiona; su `downgrade` usa `DROP SCHEMA ... RESTRICT`).
7. Ningún `message` ni log lleva documento, teléfono, correo, referencia de pago ni motivo. `logger.info` con ids solamente.
8. Dinero siempre `int` COP. Fechas: `date` para vigencias, `TIMESTAMPTZ` para instantes, "hoy" de Bogotá.

### Front
1. TanStack Query para todo dato del servidor; React Hook Form y Zod para todo formulario; toda lista pagina en el servidor con `useListParams` (el texto `q` vive en memoria, nunca en la URL, S2-D41).
2. Por feature: `api.ts` (hooks), `schemas.ts` (Zod), `*Errors.ts` (traducción de `ApiError`), `*Links.ts`, `components/`, `pages/`. Los tipos salen de `core/api/types.ts` generado.
3. Sin rol comparado con literal fuera de `permissions.ts` y `session.ts`: `useCan`, `can`, `<Can>`. Sin `console`, `fetch` directo ni `Intl` fuera de `core/api` y `core/i18n`.
4. Mutaciones con datos sensibles o motivo: `gcTime: 0`. El valor revelado vive solo en el estado local de `MaskedValue`.
5. Componentes compartidos nuevos en `shared/ui/` con su prueba; todo faltante del diseño lleva `// DESIGN-GAP:`.

### Pruebas
1. TDD por slice: Rojo con stubs, Verde y gate. Puras sin base; de service con `session`; de router con `app_http`, `usuario_real` y `cabeceras`.
2. Importar los services al nivel del archivo de prueba o en `conftest`: `restaurar_bus` (autouse) restaura el bus al terminar cada prueba, y una suscripción hecha por un import perezoso dentro de una prueba se pierde.
3. Rendimiento con `@pytest.mark.perf` (D29).

### Estructura de archivos nueva

```
api/src/app/modules/
  memberships/
    __init__.py
    models.py        Membership, MembershipFreeze (S3-B1, S3-B2)
    rules.py         privado: tipos y funciones puras (D7)
    events.py        privado: MembershipSold, MembershipActivated, MembershipActivationReverted,
                     MembershipFrozen, MembershipCancelled
    sell.py          privado: sell, renewal_preview, get_payment_target, membership_payability
    lifecycle.py     privado: freeze, cancel, on_payment_registered, on_payment_voided
    queries.py       privado: list, get, list_for_member, summary, status_for,
                     member_ids_by_status, count_active_by_plan, refs_for, status_expr,
                     _load_freezes_for
    exceptions.py    schemas.py    router.py
    service.py       fachada con __all__; al final registra el gate y las dos suscripciones
  payments/
    __init__.py  models.py  exceptions.py  schemas.py  router.py
    rules.py         privado: validate_paid_at, normalize_reference, can_void,
                     normalize_void_reason, parse_month, month_bounds_utc, build_filters
    events.py        privado: PaymentRegistered, PaymentVoided
    queries.py       privado: list, get, list_for_member, summary, sum(s)_not_voided, _enrich
    service.py       fachada: register, void, methods, puerto MembershipGate, re-exportaciones
  members/           + rules.py (extraído), detail.py, changes.py
  settings/          + PaymentMethodsSettings y payment_methods() (sin archivos nuevos)
api/migrations/versions/
  0008_memberships.py   0009_membership_freezes.py   0010_payments.py   0011_payments_immutability.py
api/tests/
  memberships/  payments/  (carpetas nuevas, con _apoyo.py y, en payments, conftest.py)
  factories/memberships.py   factories/payments.py   factories/__init__.py (FACTORIES)
  architecture/ test_payment_method_codes.py  test_payments_immutability_code.py
                test_gates_registered.py  test_no_cross_schema_sql.py  test_no_physical_delete.py
web/src/features/
  memberships/  payments/  (nuevas)   members/ y system/ crecen
```

### Tipos puros de `memberships/rules.py` (firma que fijan las pruebas de B1)

- `MembershipStatus(StrEnum)`: `pending_payment`, `active`, `expiring`, `expired`, `frozen`, `cancelled`. `ResolvedStatus` = esos cinco sin `cancelled` más `none` (`Literal`).
- `PlanTerms(kind, duration_days, class_count)`, `FreezeWindow(frozen_from, frozen_to)` con `days` y `contains(day)`, `PaymentLine(amount_cop, voided)` y `MembershipSnapshot(id, status, start_date, end_date, classes_remaining)`; todos `@dataclass(frozen=True, slots=True)` con validación en `__post_init__` (`start <= end`).
- `compute_end_date(start_date, plan) -> date`; `compute_status(m, today, expiring_days, freezes) -> MembershipStatus` (`ValueError` si `expiring_days < 0`); `effective(m, today, expiring_days, freezes) -> MembershipSnapshot` (mismo snapshot con el estado calculado); `paid_total`, `covers(agreed_price_cop, paid_cop)`, `is_covered`.
- `next_start_for_renewal(current, today) -> date`; `plan_renewal(current, plan, price_cop, today) -> RenewalPlan(start_date, end_date, agreed_price_cop)`.
- `classify_open(items, today) -> OpenMemberships(current, future)` y `find_overlap(start, end, others) -> UUID | None`, ambas sobre snapshots con estado efectivo (rangos cerrados; las canceladas las filtra el llamador).
- `resolve_member_status(items, today) -> ResolvedStatus` y `resolve_member_membership(...)` (devuelve además el snapshot que decide).
- `apply_freeze(...) -> FreezeOutcome`, `FreezeLimits(max_days, max_count, max_retroactive_days)`, `should_revert(effective_status, agreed_price_cop, paid_cop)`, `normalize_cancel_reason(reason) -> str`, `parse_status_filter(raw) -> frozenset[MembershipStatus] | None` y `prefix_field(prefix, field) -> str | None`.

## 3. Orden de ejecución y dependencias

Orden del plan: W0, B1 a B11, F1 a F7. Un checkpoint por slice (`scripts/workflow/checkpoint-commit.sh`); `run-gates.sh` al cerrar cada wave.

Dependencias duras:
- B1 trae también el cambio de `test_service_import_graph.py` (D2) y la primera ampliación de `MODULES` (`memberships`). Hasta B3 no existe `payments`: `sell` deja la rama `first_payment` con `NotImplementedError`.
- B2 necesita la tabla de B1. B3 no depende de memberships (doble en `tests/payments/conftest.py`). B4 cruza los dos módulos: gate real, activación y el primer `PaymentRegistered` real; desde aquí el grafo es completo.
- B5 necesita B4 (el trigger y el gate). B6 necesita B4 (renovar con primer pago) y B2 (renovar con congelada). B7 necesita B3 (`sums_not_voided`) y los métodos de `members` (`active_ids`). B8 necesita `memberships.refs_for` (B1). B9 necesita B7 (`status_for`, `member_ids_by_status`). B10 no depende de memberships. B11 necesita B7 (`list_for_member`) y B8 (`list` de pagos).
- Front: F1 necesita B9 y B10; F2 necesita B7 y B9; F3 necesita B4 y B6; F4 necesita B3, B4 y B5; F5 necesita B6 y B7; F6 necesita B8; F7 necesita B11 y los componentes de F3 a F5.
- Archivos compartidos que más de un slice toca: `main.py` (`MODULES`: B1 y B3), `tests/conftest.py` (limpiezas: B1, B3 y B4), `tests/architecture/_imports.py` y `test_service_import_graph.py` (B1, B3, B4, B9), `tests/architecture/test_error_codes_per_route.py` (`CON_LIMITE`: B7, B8, B10), `web/src/config/routeTable.ts` y `routes.test.ts` (F1, F3, F4, F5), `web/src/features/members/api.ts` y `schemas.ts` (B9 en compatibilidad, F1, F2).

## 4. Backend, slice por slice

### S3-W0 · Línea base (sin infraestructura nueva)

- `docker compose --env-file .env -f infra/compose.yml -f infra/compose.dev.yml up -d --build`; `docker compose exec api alembic current` debe dar `0007_plans`; `bash scripts/workflow/run-gates.sh` en verde sobre `main`. El resultado se anota en `docs/scratch/sprint-03.md` (cuaderno del sprint, guardarraíl 5 de las reglas del agente).
- `.gitignore`: agregar `docs/scratch/*.dump` (D30) en este primer checkpoint, no en B4.
- Pendientes heredados del Sprint 2 con dueño "Sprint 3" que el plan no menciona (sección 10): fijar por digest las imágenes base (L3 de la revisión de Fase 4) y actualizar vitest y stylelint (N-5). Se decide en W0 si entran o pasan a S4B-W0-2; no bloquean ningún slice.

### S3-B1 · Reglas puras y vender (US-083, US-084)

Crear `api/migrations/versions/0008_memberships.py` (`down_revision = "0007_plans"`):
- Tabla `memberships.memberships`: columnas comunes del mixin más `member_id uuid NOT NULL`, `plan_id uuid NOT NULL`, `agreed_price_cop integer NOT NULL`, `start_date date NOT NULL`, `end_date date NOT NULL`, `classes_total integer NULL`, `classes_remaining integer NULL`, `status text NOT NULL`, `cancel_reason text NULL`, `cancelled_by uuid NULL`, `cancelled_at timestamptz NULL`. Sin FK a otros esquemas. Sin columnas `frozen_*`.
- CHECKs (con `name=` corto; la convención les antepone `ck_memberships_`): `agreed_price_positive`, `dates_ordered` (`start_date <= end_date`), `status` (los seis valores), `classes_total_positive`, `classes_remaining_non_negative`, `classes_pair` (`(classes_total IS NULL) = (classes_remaining IS NULL)`), `classes_remaining_le_total`, `cancelled_has_reason` (`status <> 'cancelled' OR (cancel_reason, cancelled_by y cancelled_at no nulos)`) y `cancel_reason_length` (5 a 500).
- `ExcludeConstraint(("member_id", "="), (literal_column("daterange(start_date, end_date, '[]')"), "&&"), name="ex_memberships_member_dates", using="gist", where="status <> 'cancelled'")`.
- Índices: `ix_memberships_status_end_date (status, end_date)`, `ix_memberships_member_status_start (member_id, status, start_date)` y `ix_memberships_plan_id (plan_id)` (el filtro por plan y `count_active_by_plan`).
- Trigger `memberships.guard_identity()` (D9), `BEFORE UPDATE` por fila: rechaza `member_id`, `plan_id` o `agreed_price_cop` distintos, con `ERRCODE = integrity_constraint_violation` y `CONSTRAINT = memberships_identity`.
- `downgrade`: trigger, función, índices y tabla (la `EXCLUDE` cae con la tabla); no toca `btree_gist` ni el esquema.

Crear en `api/src/app/modules/memberships/`:
- `models.py`: `class Membership(CommonColumnsMixin, Base)` con `__tablename__ = "memberships"`, las mismas restricciones en `__table_args__` (para que `Base.metadata` coincida con la migración), `__audited__ = True` y `__audit_subject__ = "member_id"`. Constantes `STATUSES` y `EXCLUDE_NAME`. Sin `relationship()` (D6) y sin columnas diferidas (el hook lee `history.deleted`).
- `rules.py`: lo de la sección 2 ("Tipos puros"), salvo `apply_freeze`, `should_revert` y `parse_status_filter` (B2, B5 y B7).
- `events.py`: `MembershipSold(membership_id, member_id, plan_id, agreed_price_cop, start_date, end_date, renewal: bool)`.
- `exceptions.py`: base `MembershipError`; `MemberInactive` (422 `member_inactive`), `PlanInvalid` (422 `plan_invalid`, `field="plan_id"`), `PlanInactive` (422 `plan_inactive`, `field="plan_id"`), `StartDateTooRetroactive` (422 `start_date_too_retroactive`, `field="start_date"`), `MembershipConflict` (409 `membership_conflict`, con `existing_id`), `MembershipOverlap` (409 `membership_overlap`) y `MembershipNotFound` (404 `membership_not_found`). El 404 del socio es el `MemberNotFound` de `members.exceptions`.
- `schemas.py`: `SellMembershipIn(plan_id: UUID, start_date: date | None = None, renew: StrictBool = False, first_payment: None = None)` con `extra="forbid"` (B4 abre `first_payment` a `PaymentIn`; así B1 no importa `payments`); `FreezeOut`; `MembershipOut` (`id`, `member_id`, `member_name`, `plan_id`, `plan_name`, `agreed_price_cop`, `paid_cop`, `start_date`, `end_date`, `classes_total`, `classes_remaining`, `status`, `freezes: list[FreezeOut]`, `cancel_reason`, `cancelled_at`, `created_at`); `SellMembershipOut(MembershipOut)` con `first_payment_id: UUID | None`; dataclasses `MembershipRef(member_id, member_first_name, member_last_name, plan_name, start_date, end_date)` y `PaymentTarget(exists, cancelled, member_id)`.
- `sell.py`: `sell(session, *, member_id, plan_id, start_date, renew=False, first_payment=None, enforce_retroactive_limit=True) -> SellMembershipOut`. Pasos, todos dentro de `begin_nested()`: candado de socio (D3); `members.get_ref` y `MemberInactive` si `is_deleted` o `status != "active"`; `plans.get(for_share=True)` con `PlanNotFound` convertido en `PlanInvalid`, y `PlanInactive`; política y "hoy"; límite retroactivo (N-24); carga de las no canceladas del socio con sus congelaciones, `effective` y `classify_open`; `find_overlap`; insertar (el `id` ya lo asignó el mixin) y `flush` con traducción de la `EXCLUDE`; `emit(MembershipSold)`. `renew=True` o `first_payment` no nulo lanzan `NotImplementedError` hasta B6 y B4. También `get_payment_target(session, membership_id) -> PaymentTarget` (`FOR UPDATE`, `populate_existing`).
- `queries.py` (versión B1): `refs_for(session, membership_ids) -> dict[UUID, MembershipRef]` por lote con `members.names_for` y `plans.names_for`; sin ids no consulta.
- `router.py`: `POST /members/{member_id}/memberships`, 201 `SellMembershipOut`, rol admin o coach, `responses_for(404, 409)`.
- `service.py`: fachada con `__all__`.

Crear en pruebas: `api/tests/memberships/{__init__,_apoyo}.py`, `api/tests/factories/memberships.py` (sección 8) y `api/tests/migrations/test_0008_memberships.py`.

Modificar:
- `main.py`: `MODULES` suma `"memberships"` al final.
- `tests/conftest.py`: `LIMPIAR_MEMBERSHIPS` (con `to_regclass`) en `LIMPIEZA_DE_SESION` y en el `finally` de `dos_sesiones`.
- `tests/architecture/_imports.py` (`PRIVATE_HELPERS["memberships"]`), `test_service_import_graph.py` (D2), `test_audit_module.py` (`MODULES`), `test_audited_tables.py` (`memberships.memberships` pasa a requerida y se comprueba su sujeto `member_id`) y `tests/migrations/test_0007_plans.py` (D40).
- `docs/openapi.json` y `web/src/core/api/types.ts`.

Rojo (casos clave):
- `test_rules.py`: matriz de `compute_end_date` (2026-10-01 más 30 días da 2026-10-31; clases con 60 días da 2026-11-30; febrero bisiesto 2028-02-01 más 30 da 2028-03-02); `compute_status` con `expiring_days` 7 y fin 2026-10-31 (el 23 es `active`, el 24 y el 31 `expiring`, el 1 de noviembre `expired`), `pending_payment` en fecha pasada, `cancelled` siempre, `classes_remaining = 0`, ventana que contiene hoy, dos ventanas y solo la segunda contiene hoy, `expiring_days` negativo; `covers` e `is_covered` (igual, menor, mayor por Q5, todos anulados, lista vacía); `next_start_for_renewal` (vigente hasta el 2026-10-28 da el 29, vencida da hoy, sin membresía da hoy, `today == end_date` da `end_date + 1`); `classify_open` (vigente, vigente congelada, futura pendiente, futura activa, solo vencidas o canceladas) y `find_overlap` (adyacentes no chocan, el mismo día sí); valores inmutables (`FrozenInstanceError`, fechas invertidas).
- `test_sell_service.py`: venta por días con `reloj` (fin 2026-11-20, `pending_payment`, precio copiado); tiquetera de 12 clases (12 de 12); cambiar el precio del plan después no cambia `agreed_price_cop`; socio inexistente (404), dado de baja e inactivo (422); plan inexistente e inactivo; `membership_conflict` con `existing_id` (vigente y también solo futura pendiente); `membership_overlap` y violación directa de la `EXCLUDE` por SQL crudo; venta permitida con previa `expired` o `cancelled`; `start_date` de hoy menos 7 permitido y menos 8 rechazado; `enforce_retroactive_limit=False` sin tope; una fila `insert` en `audit.audit_log` con `subject_member_id`; `MembershipSold` una vez con `capturar_eventos`; un handler que lanza deja cero filas de membresía y de auditoría (savepoint de D3); dos ventas simultáneas del mismo socio con `dos_sesiones`: una gana y la otra recibe 409.
- `test_sell_router.py`: 201 con el cuerpo de `SellMembershipOut` (montos enteros); 401; 403 `member`; 404; 409 con envelope y `existing_id`; 422 por `plan_id` ausente o no UUID, `start_date` mal formada, campo desconocido (incluido `agreed_price_cop`) y `first_payment` presente (hasta B4).
- `test_refs_for.py`: nombres y fechas por lote, sin ids no consulta, incluye socios y planes dados de baja.
- `test_0008_memberships.py`: columnas y nulabilidad; cada CHECK con `INSERT` crudo (SQLSTATE 23514); `EXCLUDE` (23P01 con rangos solapados; adyacentes aceptados; canceladas ignoradas; otro socio ignorado); trigger de identidad (23000); la revisión cuelga de `0007_plans`; ciclo de downgrade.

Gate: `bash scripts/workflow/slice-gate.sh memberships tests/memberships/test_rules.py tests/memberships/test_sell_service.py tests/memberships/test_sell_router.py tests/memberships/test_refs_for.py tests/migrations/test_0008_memberships.py`, más `cd api && uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head`.

### S3-B2 · Congelar (US-089)

Crear `api/migrations/versions/0009_membership_freezes.py` (`down_revision = "0008_memberships"`):
- Tabla `memberships.membership_freezes`: comunes más `membership_id uuid NOT NULL REFERENCES memberships.memberships(id)` (mismo esquema), `frozen_from date NOT NULL`, `frozen_to date NOT NULL`, `days integer NOT NULL`.
- CHECKs: `dates_ordered` (`frozen_from <= frozen_to`) y `days_match` (`days = (frozen_to - frozen_from) + 1`).
- `ExcludeConstraint(("membership_id", "="), (literal_column("daterange(frozen_from, frozen_to, '[]')"), "&&"), name="ex_membership_freezes_dates", using="gist")`; índice `ix_membership_freezes_membership (membership_id)`.
- `downgrade`: índice y tabla.

Modificar o crear:
- `models.py`: `MembershipFreeze(CommonColumnsMixin, Base)` con `__audited__ = True`. No declara `__audit_subject__`: la tabla no tiene `member_id`; la fila `update` de `memberships` (cambio de `end_date` y `status`) sí lleva el sujeto. Se anota para US-106 (Sprint 4A), que decide cómo mostrar las congelaciones en el historial.
- `rules.py`: `FreezeLimits(max_days, max_count, max_retroactive_days)`, `FreezeOutcome(window, new_end_date)`, `FreezeError(code, field, status)` y `apply_freeze`. Orden de validación: estado efectivo `active` o `expiring` (`membership_not_freezable`, 409); `frozen_from > frozen_to` (`validation_error`, `field="frozen_to"`, 422); `frozen_from < today - max_retroactive_days` (`freeze_too_retroactive`, 422); `frozen_from` fuera de `[start_date, end_date]` (`freeze_outside_validity`, 422); alguna ventana con `frozen_to >= today` (`freeze_already_scheduled`, 409); `len(freezes) >= max_count` (`freeze_limit_reached`, 409); `sum(days) + days_nuevos > max_days` (`freeze_days_exceeded`, 409, con los días disponibles en el mensaje).
- `events.py`: `MembershipFrozen(membership_id, member_id, frozen_from, frozen_to, days, end_date)`.
- `exceptions.py`: `FreezeRejected` (el `FreezeError` convertido: lleva `code`, `field` y `status`) y `OverlapsFutureMembership` (409 `overlaps_future_membership`).
- `queries.py`: `_load_freezes_for(session, ids) -> dict[UUID, list[FreezeWindow]]` (una consulta, orden `frozen_from`); `sell` y el resto de B1 dejan de pasar listas vacías.
- `lifecycle.py`: `freeze(session, *, membership_id, frozen_from, frozen_to) -> MembershipOut`. Pasos: leer la membresía sin candado para saber el socio; candado de socio (D3); `FOR UPDATE` de la fila con `populate_existing`; `MembershipNotFound` si no existe; política; congelaciones; `apply_freeze` (se traduce a `FreezeRejected`); `find_overlap` del nuevo rango contra las otras no canceladas del socio (`OverlapsFutureMembership`); insertar la `MembershipFreeze`, actualizar `end_date` y `status = compute_status(...)` con la lista nueva; `flush` con traducción de `ex_memberships_member_dates` a `OverlapsFutureMembership`; `emit(MembershipFrozen)`.
- `schemas.py`: `FreezeIn(frozen_from: date, frozen_to: date)` con `extra="forbid"`; `FreezeOut(id, frozen_from, frozen_to, days, created_at)`.
- `router.py`: `POST /memberships/{membership_id}/freeze`, 200 `MembershipOut`, admin y coach (Q7), `responses_for(404, 409)`.
- `tests/conftest.py`: `LIMPIAR_MEMBERSHIPS` borra primero las congelaciones. `tests/factories/memberships.py`: `make_freeze`. `test_0008_memberships.py` pasa a "está en la cadena".

Rojo:
- `test_freeze_rules.py`: 10 días desde hoy con fin 2026-10-31 da fin 2026-11-10; ventana de un día suma 1; ventana futura (2026-10-20 a 2026-10-24) corre a 2026-11-05 y sigue `active`; cada límite de Q9 en sus fronteras (hoy menos 7 permitido y menos 8 rechazado; 30 días exactos permitidos y 31 rechazados; segunda permitida y tercera rechazada); fechas invertidas; fuera de vigencia; ya programada; estados no congelables (`pending_payment`, `frozen`, `expired`, `cancelled`); la entrada no se muta.
- `test_freeze_service.py`: congelar desde hoy deja `frozen` y `end_date` extendido; congelación futura deja `active`; límites leídos de `settings` guardado y por defecto si la sección no existe; choque con una futura da 409 `overlaps_future_membership` sin filas nuevas ni cambios; una congelada y extendida junto a una futura contigua; segunda congelación tras terminar la primera y tercera 409 `freeze_limit_reached`; auditoría con `insert` en `membership_freezes` y `update` en `memberships` (`end_date` y `status`, con `subject_member_id`); `MembershipFrozen` una vez; violación directa de la `EXCLUDE` de congelaciones; dos congelaciones concurrentes de la misma membresía con `dos_sesiones` (una gana).
- `test_freeze_router.py`: 200 coach y admin; 403 `member`; 401; 404; 422 con `field="frozen_to"` y con cada código de 422; 409 con cada código de 409.
- `test_0009_membership_freezes.py`: columnas, CHECKs, `EXCLUDE` (rangos solapados 23P01; adyacentes aceptados), FK, ciclo.

Gate: `bash scripts/workflow/slice-gate.sh memberships tests/memberships/test_freeze_rules.py tests/memberships/test_freeze_service.py tests/memberships/test_freeze_router.py tests/migrations/test_0009_membership_freezes.py`, más el ciclo de Alembic.

### S3-B3 · Registrar pago y medios de pago (US-095, US-056)

Crear `api/migrations/versions/0010_payments.py` (`down_revision = "0009_membership_freezes"`):
- Tabla `payments.payments`: comunes más `membership_id uuid NOT NULL`, `member_id uuid NOT NULL` (copia inmutable, D2/D9), `amount_cop bigint NOT NULL`, `method text NOT NULL`, `reference text NULL`, `paid_at timestamptz NOT NULL`, `registered_by uuid NOT NULL`, `voided boolean NOT NULL DEFAULT false`, `void_reason text NULL`, `voided_by uuid NULL`, `voided_at timestamptz NULL`. Sin FK entre esquemas.
- CHECKs: `amount_range` (`amount_cop BETWEEN 1 AND 1000000000`, D17), `method` (`IN ('cash','nequi','breb')`), `reference_length` (`reference IS NULL OR char_length(reference) BETWEEN 1 AND 64`), `void_reason_length` (`<= 500`), `void_coherent` (`(voided = false AND void_reason IS NULL AND voided_by IS NULL AND voided_at IS NULL) OR (voided = true AND btrim(void_reason) <> '' AND voided_by IS NOT NULL AND voided_at IS NOT NULL)`).
- Índices: `ix_payments_paid_at (paid_at DESC)`, `ix_payments_membership_id (membership_id)`, `ix_payments_member_paid (member_id, paid_at DESC)`. El índice de `registered_by` solo si la prueba `perf` de B8 lo pide (migración propia entonces).
- `downgrade`: índices y tabla.

Crear en `payments/`:
- `models.py`: `Payment(CommonColumnsMixin, Base)` con `__audited__ = True`, `__audit_subject__ = "member_id"` y las constantes `PAYMENT_METHODS = ("cash", "nequi", "breb")`, `MAX_AMOUNT_COP`.
- `schemas.py`: `PaymentMethod = Literal["cash", "nequi", "breb"]`; `PaymentIn(amount_cop: StrictInt (1..1.000.000.000), method, reference: SafeText | None (máx. 64, recortada; vacía pasa a `None`), paid_at: AwareDatetime | None)` con `extra="forbid"`; `PaymentOut` (`id`, `membership_id`, `member_id`, `amount_cop`, `method`, `reference`, `paid_at`, `registered_by`, `voided`, `void_reason`, `voided_by`, `voided_at`, `created_at`); `PaymentMethodOut(code, label, hint)` y `PaymentMethodsOut(items)` (D25).
- `rules.py`: `validate_paid_at(paid_at, now)` (exige zona; `PAID_AT_FUTURE_TOLERANCE = timedelta(minutes=5)`; sin límite hacia atrás, N-27) y `normalize_reference(value)`.
- `events.py`: `PaymentRegistered(membership_id, payment_id, amount_cop)` y `PaymentVoided(membership_id, payment_id)` (el segundo se emite desde B5).
- `exceptions.py`: base `PaymentError`; `PaymentMembershipNotFound` (404 `membership_not_found`), `MembershipCancelled` (409 `membership_cancelled`), `PaidAtInFuture` (422 `validation_error`, `field="paid_at"`), `PaymentNotFound` (404 `payment_not_found`), y `MembershipGateNotRegistered(RuntimeError)`.
- `service.py` (B3): puerto del gate (D1) y `register(session, *, membership_id, amount_cop, method, reference, paid_at) -> PaymentOut`. Pasos: gate (`exists` falso da 404; `cancelled` da 409; sin gate, falla cerrado); `paid_at = paid_at o current_clock().now_utc()` y `validate_paid_at`; crear `Payment(member_id=gate.member_id, registered_by=get_actor())`; `flush` (el hook audita; `eager_defaults` trae las fechas) y solo entonces `emit(PaymentRegistered)`. También `sum_not_voided(session, membership_id) -> int`, `sums_not_voided(session, membership_ids) -> dict[UUID, int]` (`COALESCE(SUM) ... WHERE voided = false GROUP BY membership_id`) y `methods(session) -> PaymentMethodsOut`.
- `router.py`: rutas fijas primero. `GET /payments/methods` (admin y coach, `responses_for()` sin extras) y `POST /memberships/{membership_id}/payments` (201 `PaymentOut`, `responses_for(404, 409)`).

Settings (sin archivos nuevos): en `schemas.py`, `PAYMENT_METHOD_CODES`, `MethodLabel`, `PaymentMethodsSettings`, `PaymentMethodsSectionOut`, `PaymentMethodsPatchIn`, y el registro en `ENABLED_SECTIONS`, `SECTION_REGISTRY`, `SECTION_VIEWS` y `SECTION_DEFAULTS`. En `service.py`, la pura `decorate_methods(codes, labels)` y `payment_methods(session)`. En `router.py`, las dos rutas tipadas antes de la genérica.

Modificar: `main.py` (`MODULES` suma `"payments"`), `test_audit_module.py`, `test_audited_tables.py` (`payments.payments` requerida, sujeto `member_id`), `PRIVATE_HELPERS["payments"]`, `test_service_import_graph.py` (aristas de payments, D2), `tests/conftest.py` (`LIMPIAR_PAYMENTS`, D30: ahora el trigger aún no existe, pero la forma con `DISABLE TRIGGER USER` ya va), `tests/settings/_apoyo.py` y los tests de settings (D40), `docs/openapi.json` y tipos.

Rojo (casos clave):
- `tests/payments/test_rules.py`: `validate_paid_at` (ahora; ahora más 4 min 59 s; más 5 min 1 s; sin zona; un año atrás aceptado); `normalize_reference` (espacios, vacío, 64 y 65 caracteres); `PaymentIn` con montos 0, -1, 1, 120000, 120000.5, "120000", `true` y 1.000.000.001; medio "tarjeta".
- `tests/payments/test_register.py` (con `gate_doble`): registro feliz (fila, `registered_by` y `created_by` del actor, `member_id` copiado del gate, `paid_at` por defecto con `reloj`); membresía inexistente; membresía cancelada sin fila creada; expiradas y congeladas aceptadas (N-28); `PaymentRegistered` una vez con el monto; un handler que lanza revierte el pago; auditoría `insert` en `payments.payments` con `subject_member_id`; `sum_not_voided` y `sums_not_voided` con pagos vigentes y anulados insertados por SQL (el trigger aún no existe); sin gate, `MembershipGateNotRegistered` y cero filas; autoflush (la suma ve el pago antes del evento).
- `tests/settings/test_payment_methods_rules.py`, `..._service.py`, `..._router.py`: `decorate_methods` con etiquetas por defecto y personalizadas y orden fijo aunque el JSON venga en otro orden; `validate_section` con clave extra `tarjeta` (`field: "value.tarjeta"`), sin `nequi`, con `label` vacía (`value.cash.label`) y `hint` de 121 caracteres; coach 403 en `GET` y `PATCH`; guardar etiquetas no cambia ninguna fila de `payments.payments`.
- `tests/payments/test_payment_methods_router.py`: 200 a coach y admin con tres elementos en orden, 403 al socio, 401 sin token, forma de objeto (D25).
- `tests/architecture/test_payment_method_codes.py` (D24).
- `tests/migrations/test_0010_payments.py`: columnas, CHECKs con SQL crudo, índices, ciclo.

La prueba de router de `POST /memberships/{id}/payments` (`tests/payments/test_router_register.py`) pasa a B4 (necesita el gate real, M-1).

Gate: `bash scripts/workflow/slice-gate.sh payments tests/payments/test_rules.py tests/payments/test_register.py tests/payments/test_payment_methods_router.py tests/migrations/test_0010_payments.py` y `bash scripts/workflow/slice-gate.sh settings tests/settings/test_payment_methods_rules.py tests/settings/test_payment_methods_service.py tests/settings/test_payment_methods_router.py tests/architecture/test_payment_method_codes.py`, más el ciclo de Alembic.

### S3-B4 · Inmutabilidad, venta con primer pago y activación (US-096, US-085, US-086)

Paso previo (antes de aplicar `0011`): `docker compose exec db pg_dump -U <usuario> -Fc apex > docs/scratch/sprint-03-antes-0011.dump`. El archivo queda fuera de git por la regla de W0. `RUNBOOK.md` documenta la restauración (`pg_restore`) y que `downgrade -1` borra triggers y funciones sin tocar datos.

Crear `api/migrations/versions/0011_payments_immutability.py` (`down_revision = "0010_payments"`):
- Función `payments.forbid_mutation()` (`plpgsql`, `SECURITY INVOKER`, sin `EXCEPTION WHEN OTHERS`): con `DELETE` o `TRUNCATE` lanza `payments_immutable: delete`; con `UPDATE`: si `OLD.voided` lanza `payments_immutable: already_voided`; si cambia alguna de `id`, `membership_id`, `member_id`, `amount_cop`, `method`, `reference`, `paid_at`, `registered_by`, `created_at` o `created_by` lanza `payments_immutable: column`; exige `NEW.voided AND btrim(coalesce(NEW.void_reason, '')) <> '' AND NEW.voided_by IS NOT NULL AND NEW.voided_at IS NOT NULL`, si no lanza `payments_immutable: incomplete_void`. `updated_at` queda libre. Cada `RAISE` usa `ERRCODE = integrity_constraint_violation` y `CONSTRAINT = payments_immutable` (D13).
- Triggers `payments_forbid_mutation BEFORE UPDATE OR DELETE ... FOR EACH ROW` y `payments_forbid_truncate BEFORE TRUNCATE ... FOR EACH STATEMENT` (la misma función, como `audit.forbid_mutation`).
- `downgrade`: los dos triggers y la función; no toca datos.

Cambios en `payments/`: `rules.py` agrega `can_void(payment) -> bool` (`not payment.voided`). `service.py` exporta la constante `IMMUTABLE_CONSTRAINT = "payments_immutable"`.

Cambios en `memberships/`:
- `schemas.py`: `SellMembershipIn.first_payment: PaymentIn | None` (D4).
- `sell.py`: `membership_payability(session, membership_id) -> payments_service.MembershipPayability` (adaptador de `get_payment_target`); la rama `first_payment`: después del `flush` de la membresía y de `emit(MembershipSold)`, `payments_service.register(...)` dentro del mismo `begin_nested()`; `PaymentError` de validación se re-lanza con `prefix_field`; la respuesta se arma al final con el estado que dejó el handler (misma instancia de la sesión, `populate_existing`) y `first_payment_id`.
- `lifecycle.py`: `on_payment_registered(event, session)` (D11) y `MembershipActivated(membership_id, member_id, status)` en `events.py`; `snapshot(row)`.
- `service.py`: al final, `payments_service.set_membership_gate(membership_payability)` y `events.subscribe(PaymentRegistered, on_payment_registered)`.
- `tests/payments/conftest.py`: `gate_doble` (sección 8).
- `.gitignore` y `RUNBOOK.md` (volcado y restauración).

Rojo (casos clave):
- `tests/payments/test_can_void.py`: pago vigente `True`, anulado `False`.
- `tests/payments/test_immutability.py` (SQL crudo con `SAVEPOINT` por caso y relectura de la fila): `DELETE` y `TRUNCATE` rechazados; `UPDATE` de cada columna protegida rechazado (parametrizado), también si la misma sentencia llena las de anulación; anulación completa aceptada con `updated_at` cambiado y monto intacto; sin motivo, con motivo de espacios, sin `voided_by` o sin `voided_at` rechazada; segunda anulación rechazada; `voided` de `true` a `false` rechazado; `UPDATE` sin cambios sobre un anulado rechazado. Cada rechazo es `IntegrityError` con `violated_constraint == "payments_immutable"` y el motivo en el mensaje.
- `tests/payments/test_router_register.py` (gate real): 201 coach y admin; 403 `member`; 401; 422 con `field` de `amount_cop`, `method`, `reference` y `paid_at`; 404 y 409 con envelope; monto entero en JSON.
- `tests/memberships/test_sell_with_payment_service.py`: pago igual al precio da `active` en la misma respuesta; parcial da `pending_payment`; mayor (Q5) da `active` sin filas extra; `paid_at` por defecto; atomicidad (un handler de `PaymentRegistered` que lanza, o un gate que lanza, deja cero filas en `memberships`, `payments` y `audit.audit_log`); dos filas `insert` con el mismo `user_id` y `subject_member_id`; `registered_by` es el actor; 422 con `field="first_payment.amount_cop"` y `first_payment.paid_at` futuro.
- `tests/memberships/test_activation_service.py` (por el bus real): 60.000 y luego 60.000 sobre 120.000 da `active` y un solo `MembershipActivated`; el mismo caso el 2026-10-27 da `expiring`; 20.000 deja `pending_payment` sin eventos; un pago anulado no suma; pago sobre `active`, `expiring` y `frozen` no emite; membresía con congelación que contiene hoy y un pago que cubre queda `frozen`; handler que lanza revierte pago y estado; auditoría `update` con `before.status = pending_payment` y `after.status = active` del usuario que pagó; dos pagos concurrentes de 60.000 con `dos_sesiones` terminan `active` (candado de la membresía).
- Arquitectura: `test_payments_immutability_code.py`, `test_gates_registered.py`, `test_service_import_graph.py` (aristas de memberships hacia payments, `payments` no importa `memberships` a nivel de módulo, pares perezosos, importación limpia en los dos órdenes).
- `tests/migrations/test_0011_payments_immutability.py`: existencia de función y triggers, ciclo `upgrade/downgrade` sin tocar filas, la revisión cuelga de `0010_payments`.

Gate: `bash scripts/workflow/slice-gate.sh payments tests/payments/test_can_void.py tests/payments/test_immutability.py tests/payments/test_router_register.py tests/migrations/test_0011_payments_immutability.py` y `bash scripts/workflow/slice-gate.sh memberships tests/memberships/test_sell_with_payment_service.py tests/memberships/test_activation_service.py`, más el ciclo de Alembic. Desde aquí `tests/architecture` (incluido el grafo) bloquea todo checkpoint.

### S3-B5 · Anular pago y revertir la activación (US-097, US-087)

Crear o modificar:
- `payments/rules.py`: `normalize_void_reason(value) -> str` (recorta; vacío o más de 500 da `InvalidVoidReason`); `VOID_REASON_MAX = 500`.
- `payments/exceptions.py`: `PaymentAlreadyVoided` (409 `payment_already_voided`) e `InvalidVoidReason` (422, `field="reason"`).
- `payments/schemas.py`: `VoidPaymentIn(reason: SafeText)` con `extra="forbid"`; la respuesta es `PaymentOut`.
- `payments/service.py`: `void(session, *, payment_id, reason) -> PaymentOut`, con el orden de D13: leer el pago sin candado (404 `payment_not_found`); gate sobre su `membership_id` (candado de la membresía); `select ... with_for_update().execution_options(populate_existing=True)` del pago; `can_void` (409 si no); asignar `voided`, `void_reason`, `voided_by = get_actor()` y `voided_at = current_clock().now_utc()`; `flush`; si el `IntegrityError` trae `IMMUTABLE_CONSTRAINT` se traduce a `PaymentAlreadyVoided`; `emit(PaymentVoided)` solo después del flush. La función `void` es el único lugar de `payments` que asigna esas cuatro columnas (lo vigila `test_payments_immutability_code.py`).
- `payments/router.py`: `POST /payments/{payment_id}/void`, 200 `PaymentOut`, solo admin, `responses_for(404, 409)`.
- `memberships/rules.py`: `should_revert(effective_status, agreed_price_cop, paid_cop)`.
- `memberships/lifecycle.py` y `events.py`: `on_payment_voided(event, session)` (D13) y `MembershipActivationReverted(membership_id, member_id, previous_status)`; `memberships/service.py` suscribe `PaymentVoided`.
- `docs/openapi.json` y tipos.

Rojo (casos clave):
- `test_void_rules.py`: `normalize_void_reason` con "  Monto mal digitado  ", "", "   ", 500 y 501 caracteres, NUL y U+200B (rechazados por `SafeText` en el schema).
- `test_void.py`: anulación feliz (las cuatro columnas; monto, medio, referencia y `paid_at` intactos); doble anulación 409 sin cambios; pago inexistente; `PaymentVoided` una vez con `membership_id` y `payment_id`; un handler que falla deja el pago sin anular; anular y registrar uno nuevo deja dos filas y `sum_not_voided` solo suma el nuevo; auditoría `update` con `before.voided = false`, `after.voided = true`, usuario y `subject_member_id`; dos sesiones anulando el mismo pago con `dos_sesiones`: una 200 y otra 409; un `UPDATE` hecho fuera del service (SQL crudo) también acaba en 409.
- `test_router_void.py`: 200 admin; 403 coach y `member`; 401; 422 con `field="reason"` (ausente, vacío, espacios, 501 caracteres); 404; 409 con envelope.
- `tests/memberships/test_revert_activation_service.py` (por el bus, anulando con `payments.service.void`): único pago de 120.000 anulado da `pending_payment` y un `MembershipActivationReverted`; pagos de 120.000 y 20.000 y se anula el de 20.000, sigue `active` sin eventos; `expiring` pasa a `pending_payment`; `frozen` pasa a `pending_payment` con su fila de `membership_freezes` y su `end_date` intactos (N-25), y un pago nuevo que cubre la devuelve a `frozen`; `expired` (efectivo) y `cancelled` sin cambio; un handler que lanza deja el pago sin anular; auditoría `update` del admin.

Gate: `bash scripts/workflow/slice-gate.sh payments tests/payments/test_void_rules.py tests/payments/test_void.py tests/payments/test_router_void.py` y `bash scripts/workflow/slice-gate.sh memberships tests/memberships/test_revert_activation_service.py`.

### S3-B6 · Renovar y anular membresía (US-088, US-090)

Modificar o crear:
- `memberships/sell.py`: la rama `renew=True` de `sell` (el `start_date` recibido se descarta): bajo el candado de socio, si hay futura lanza `FutureMembershipExists` (409 `future_membership_exists`, con `existing_id`); `plan_renewal(vigente_o_None, plan, price_cop, hoy)`; mismas validaciones y mismo primer pago; `MembershipSold(renewal=True)`; el límite retroactivo no aplica. `renewal_preview(session, *, member_id, plan_id) -> RenewalPreviewOut(start_date, end_date, agreed_price_cop, current_end_date)` comparte las validaciones, no escribe y no toma el candado de socio (es solo lectura).
- `memberships/lifecycle.py`: `cancel(session, *, membership_id, reason) -> MembershipOut`: `FOR UPDATE` con `populate_existing`; 404; `MembershipAlreadyCancelled` (409 `membership_already_cancelled`) si ya lo está; `normalize_cancel_reason` (5 a 500 tras recortar, `field="reason"`); asigna `status = "cancelled"`, `cancel_reason`, `cancelled_by = get_actor()`, `cancelled_at = now`; `emit(MembershipCancelled(membership_id, member_id, reason_len))` (el evento no lleva el texto del motivo). No toca pagos ni congelaciones.
- `memberships/rules.py`: `normalize_cancel_reason`, `plan_renewal` (si no estaba ya).
- `memberships/schemas.py`: `CancelMembershipIn(reason: SafeText)` con `extra="forbid"`, `RenewalPreviewOut`.
- `memberships/exceptions.py`: `FutureMembershipExists`, `MembershipAlreadyCancelled`, `CancelReasonInvalid` (422, `field="reason"`).
- `memberships/router.py`: `GET /members/{member_id}/memberships/renewal-preview?plan_id=` (admin y coach, `responses_for(404, 409)`) y `POST /memberships/{membership_id}/cancel` (solo admin, `responses_for(404, 409)`).

Rojo (casos clave):
- `test_renew_service.py` (con `reloj` en 2026-10-21): vigente hasta el 2026-10-28, renovar da inicio 2026-10-29 y fin 2026-11-28, `pending_payment`, la vigente no cambia ni gana auditoría; vencida da inicio hoy; renovar antes de vencer con pago completo da una futura `active` con `start_date > hoy`; ya hay futura da 409 con `existing_id`; `start_date` enviado se ignora; plan distinto e inactivo; vigente congelada (fin ya extendido); no solapa (consulta de rangos); una membresía cancelada entre las dos; la vista previa devuelve lo mismo que crea `sell` y no escribe filas; carrera: dos renovaciones a la vez, una gana y la otra recibe 409 (candado) y, si las dos pasaran, la `EXCLUDE` rechaza.
- `test_renew_router.py`: 201, 409 `future_membership_exists`, 403 `member`, 401; vista previa 200, 404, 409, 422 por `plan_id` ausente.
- `test_cancel_service.py`: anular desde cada estado de origen; pagos intactos (SQL crudo y sin auditoría de `payments`); segunda anulación 409; motivo corto 422 sin cambios; tras anular, `sell` al mismo socio con las mismas fechas da 201 (la `EXCLUDE` ignora canceladas); registrar un pago contra la cancelada da 409 `membership_cancelled` por el gate real; un `PaymentVoided` posterior no la reactiva; auditoría `update` con `subject_member_id`; `MembershipCancelled` una vez.
- `test_cancel_router.py`: 200 admin; 403 coach y `member`; 401; 404; 409; 422 `field="reason"`.

Gate: `bash scripts/workflow/slice-gate.sh memberships tests/memberships/test_renew_service.py tests/memberships/test_renew_router.py tests/memberships/test_cancel_service.py tests/memberships/test_cancel_router.py`.

### S3-B7 · Listar membresías y consultas de estado (US-091, US-092)

Modificar o crear:
- `members/service.py`: `active_ids(session) -> builtins.list[UUID]` (socios con `deleted_at IS NULL`; una consulta; lo pide `summary`). Pequeño, va antes de la extracción de B9.
- `memberships/rules.py`: `parse_status_filter(raw)` (coma, sin repetidos; desconocido da `StatusFilterInvalid` con `field="status"`), `resolve_member_status` y `resolve_member_membership` (prioridad de US-092 sobre estados efectivos: vigente, `pending_payment`, `expired`, futura `active`, `none`).
- `memberships/queries.py`:
  - `status_expr(today, expiring_days)`: `CASE` espejo de `compute_status` (D5). El `EXISTS` de congelación usa `membership_freezes` del mismo esquema. Se arma con `case(...)` de SQLAlchemy y `literal(today, Date)`; la resta `end_date - today` es de `date`.
  - `list(session, *, statuses, q, plan_id, ends_from, ends_to, member_id, order="end_asc", page) -> Page[MembershipRow]` (D18). Valida `ends_from <= ends_to` (`field="ends_to"`). Sin `statuses`, excluye canceladas. Resuelve `q` con `members.search_ids(include_deleted=True)` y, en la lista de la ficha de B11, con `plans.search_ids`. Completa `member_name`, `plan_name`, `paid_cop` (`payments.sums_not_voided`) y el estado efectivo por lote (`_load_freezes_for`). Nunca descifra.
  - `get(session, membership_id) -> MembershipOut` con congelaciones, `member_name`, `plan_name` y `paid_cop`; 404 `membership_not_found`.
  - `summary(session, *, today=None) -> MembershipSummaryOut(active, expiring, expired, frozen, pending_payment)`: `members.active_ids`, una consulta de las no canceladas de esos socios, una de congelaciones, `resolve_member_status` en memoria y conteo por socio (N-26). Los socios sin membresía no se devuelven.
  - `status_for(session, member_ids, *, today=None) -> dict[UUID, MemberMembership]` donde `MemberMembership(status, plan_id, plan_name, end_date)` (dataclass congelada en `schemas.py`); lotes de 200; los ids sin filas no aparecen (el llamador usa `none`).
  - `member_ids_by_status(session, statuses, plan_id=None, *, today=None) -> set[UUID]`; el complemento `none` lo calcula `members`.
  - `count_active_by_plan(session, plan_id) -> int`: estado efectivo distinto de `cancelled` y de `expired` (G-04 y N-22 sobre D5).
- `memberships/schemas.py`: `MembershipRow(id, member_id, member_name, plan_id, plan_name, agreed_price_cop, paid_cop, start_date, end_date, classes_total, classes_remaining, status)`, `MembershipSummaryOut`, `MemberMembership`.
- `memberships/router.py`: `GET /memberships/summary` (primero), `GET /memberships` (con el límite `memberships-search` solo cuando hay `q`) y `GET /memberships/{membership_id}`. Roles admin y coach.
- `tests/architecture/test_error_codes_per_route.py`: `CON_LIMITE` gana `get /api/v1/memberships`.
- `tests/architecture/test_no_cross_schema_sql.py` (sección 7).
- `docs/openapi.json` y tipos.

Rojo (casos clave):
- `test_rules.py` (ampliado): `parse_status_filter`; `resolve_member_status` con los nueve casos de US-092 (solo vigente; vigente por vencer más futura pendiente da `expiring`; solo futura `active` da `active`; solo vencida; solo cancelada da `none`; congelada; pendiente más vencida da `pending_payment`; vencida más futura activa da `expired`; vacío).
- `test_status_expr_parity.py` (nueva): una malla de fechas alrededor del fin (menos 9 a más 2 días), `expiring_days` 0, 3 y 7, con y sin congelación que contiene hoy, `classes_remaining` 0, `pending_payment` y `cancelled`; el `CASE` ejecutado en PostgreSQL y `compute_status` coinciden en cada punto.
- `test_list_service.py`: filtro `expiring` y rango de fin (tres de tres, orden por fin); `pending_payment`; combinación con `plan_id` y `member_id`; `q` por apellido y por documento (índice ciego) con socios reales; `q` sin coincidencias; incluye socios dados de baja; nombres, congelaciones y sumas completados por lote (un contador de consultas con `before_cursor_execute`: una por servicio vecino por página); `total` correcto con `offset`; `paid_cop` ignora anulados; ninguna fila `decrypt` en `crypto_ops`; la parte `perf` con 1.000 socios y 3.000 membresías: `status=expiring` en menos de 500 ms.
- `test_list_router.py`: 200 con `{items,total,limit,offset}`; `limit` 0 y 201 dan 422; `status=vigente` da 422 con `field="status"`; rango invertido 422; detalle 404; 403 `member`; 401; límite de 60 por minuto con `q`.
- `test_status_queries_service.py`: escenario de 10, 4, 4, 1 y 2 socios por estado; `status_for` de tres socios con uno sin membresías; `status_for` de 200 ids emite una sola consulta de membresías; `member_ids_by_status({"expiring"}, plan_id)`; `count_active_by_plan` igual a 3 con dos activas, una pendiente y cinco vencidas; un socio dado de baja no entra al resumen; una membresía `active` guardada cuyo fin ya pasó cuenta como `expired` sin que nadie corra ningún job (D5).
- `test_summary_router.py`: 200 con cinco enteros, 403 `member`, 401. `perf`: resumen con 1.000 socios en menos de 300 ms.

Gate: `bash scripts/workflow/slice-gate.sh memberships tests/memberships/test_list_service.py tests/memberships/test_list_router.py tests/memberships/test_status_expr_parity.py tests/memberships/test_status_queries_service.py tests/memberships/test_summary_router.py tests/architecture/test_no_cross_schema_sql.py`; la parte `perf` se corre aparte con `uv run pytest -m perf tests/memberships`.

### S3-B8 · Listas, detalle y resumen de pagos (US-098, US-099, US-100)

Crear o modificar en `payments/`:
- `rules.py`: `PaymentFilters` (dataclass congelada: `q`, `from_`, `to`, `method`, `registered_by`, `voided`, `member_id`, `membership_id`); `build_filters(filters, member_ids_from_q) -> list[ColumnElement[bool]]` (rango `[from, to)`; `voided` tri-estado; `q` como `lower(reference) = lower(q) OR member_id = ANY(ids)`); `parse_month(value) -> tuple[int, int]` y `month_bounds_utc(month) -> tuple[datetime, datetime]` con `zoneinfo`; `InvalidMonth` (422, `field="month"`).
- `queries.py`: `list(session, filters, page) -> Page[PaymentRow]`, `get(session, payment_id) -> PaymentDetail` y `summary(session, month) -> PaymentsSummary`. `list` pagina `select(Payment)` con `ORDER BY paid_at DESC, id DESC`, calcula el total sobre la misma condición y enriquece por lote: `memberships.refs_for` (import perezoso, par `("payments", "memberships")`), `auth.names_for` (`registered_by` y, en el detalle, `voided_by`) y `members.search_ids` solo cuando hay `q`. Un helper `_enrich(rows)` lo comparten lista y detalle. `summary` es una sola consulta con `SUM(amount_cop) FILTER (WHERE NOT voided)` por total y por medio, `COUNT(*) FILTER (...)` de vigentes y de anulados, sobre `paid_at >= inicio AND paid_at < fin`, con `COALESCE` a cero.
- `schemas.py`: `PaymentRow(id, paid_at, amount_cop, method, reference, voided, void_reason, registered_by, registered_by_name, membership_id, member_id, member_first_name, member_last_name, plan_name, membership_start_date, membership_end_date)`; `PaymentDetail(PaymentRow)` con `voided_by`, `voided_by_name`, `voided_at` y `created_at`; `PaymentsSummary(month, total_cop, by_method{cash,nequi,breb}, voided_count, payments_count)`; `PaymentListQuery` con alias `from`.
- `router.py`, en este orden: `GET /payments/summary`, `GET /payments/methods` (ya existe), `GET /payments` (límite `payments-search` de 60 por minuto solo con `q`), `GET /payments/{payment_id}` (UUID; 422 si no lo es). Admin y coach.
- `tests/architecture/test_error_codes_per_route.py`: `CON_LIMITE` gana `get /api/v1/payments`. `docs/openapi.json` y tipos.

Rojo (casos clave):
- `test_month_bounds.py`: `month_bounds_utc("2026-10")` da `2026-10-01T05:00Z` a `2026-11-01T05:00Z`; diciembre cruza de año; `2026-13`, `2026-1`, `26-10`, `abcd-ef` dan `InvalidMonth`.
- `test_list_filters.py` (puras): cada filtro aislado, `voided` en `true`, `false` y ausente, `q` sin coincidencias de socio, el rango excluye `to`.
- `test_list.py` con 40 pagos de octubre (tres anulados): primera página de 25 en orden descendente y `total = 40`; cada filtro; `q` por referencia en minúsculas; `q` por apellido parcial y por documento; `member_id` y `membership_id`; la fila no trae datos cifrados; nombres y fechas de la membresía resueltos con los services vecinos reales; una consulta por servicio vecino por página; ningún `decrypt` salvo el de `q`.
- `test_list_filters` y `test_router_list.py`: 200 admin y coach; 403 `member`; 401; 422 con `field` para `limit` 0 y 201, `offset` negativo, `method="tarjeta"`; montos enteros en JSON; límite con `q`.
- `test_get.py` y `test_router_get.py`: vigente; anulado con `voided_by_name`; inexistente 404; 422 con "no-es-uuid"; `/payments/summary` no cae en `{payment_id}`; 403 y 401.
- `test_summary.py`: escenario de 300.000 en efectivo, 240.000 en Nequi, 120.000 en Bre-B y un anulado de 120.000 en Nequi da total 660.000 por medio exacto, `voided_count = 1` y `payments_count = 3`; un pago de `2026-11-01T03:00Z` cuenta en octubre y uno de `2026-11-01T05:00Z` en noviembre; mes sin pagos da ceros; sin `month` usa el mes de Bogotá con `FrozenClock` en `2026-10-31T23:30-05:00`; `total_cop` coincide con la suma de `list(voided=false)` del mismo rango (el cuadre de la demo).
- `test_router_summary.py`: 200 admin y coach; 422 `field="month"` con `2026-13`; 403; 401; enteros.
- `test_list_performance.py` (`perf`): 10.000 pagos, `limit=25`, menos de 500 ms en el service; si falla, se agrega el índice de `registered_by` en la migración condicional `0014_payments_registered_by_idx` del README del desglose (`0012` y `0013` son de US-113 y US-104).

Gate: `bash scripts/workflow/slice-gate.sh payments tests/payments/test_month_bounds.py tests/payments/test_list_filters.py tests/payments/test_list.py tests/payments/test_router_list.py tests/payments/test_get.py tests/payments/test_router_get.py tests/payments/test_summary.py tests/payments/test_router_summary.py`.

### S3-B9 · Filtros de socios y ficha (US-071, US-073)

Paso 0 (checkpoint propio, sin cambio de comportamiento): extraer `members/rules.py` (D7) y dejar `service.py` como fachada con `__all__`. Todas las pruebas de `tests/members` siguen verdes sin tocarse. Se agregan `PRIVATE_HELPERS["members"]` y su cambio en la prueba de helpers privados.

Crear o modificar en `members/`:
- `schemas.py`: `MemberListQuery` gana `membership_status: MembershipFilterStatus | None` (`active`, `expiring`, `expired`, `frozen`, `pending_payment`, `none`) y `plan_id: UUID | None`; `MemberRowOut` gana `membership_end_date: date | None = None` (D22, D35); `MemberDetailOut` gana `plan_name: str | None = None` y `membership_end_date: date | None = None`.
- `rules.py`: `chip_to_filter(chip) -> MemberChipFilter` (siete chips; desconocido da `ValueError`).
- `service.py` (`list`): si hay `membership_status` o `plan_id`, import perezoso de `memberships.service` (comentario `# lazy: G-03`), conjunto de ids (D22), condición `Member.id == any_(...)` o `!= all_(...)` en la consulta externa; siempre decora la página con `status_for` (hasta 200 ids). Con `none` y `plan_id` devuelve la página vacía sin consultar.
- `detail.py`: `get(session, member_id) -> MemberDetailOut`: carga el socio con dados de baja; `MemberNotFound` si no existe; para cada campo no nulo `types.reveal(socio, campo, "mask")` y `mask(...)` (D20; `birth_date` es `date` y `emergency_contact` un mapeo); `status_for([id])` con import perezoso; `warnings = []` (solo create y update los llevan); nunca audita.
- `router.py`: el 429 pasa a cada ruta (D27). `GET /members` gana los parámetros `membership_status` y `plan_id` (422 con `field`; un `plan_id` inexistente da lista vacía). Nueva `GET /members/{member_id}` (admin y coach, `responses_for(404)`; 422 por UUID; sin límite).
- `tests/architecture/test_error_codes_per_route.py` (D27) y `tests/members/_apoyo.py` (`CAMPOS_DETALLE`, `CAMPOS_FILA`).
- Front, compatibilidad (D35): `web/src/features/members/schemas.ts` agrega `membership_end_date` (opcional, `null` por defecto) a `memberRowSchema`; fixtures y `tests/e2e/members.spec.ts` al día.
- `docs/openapi.json` y tipos.

Rojo (casos clave):
- `test_chip_to_filter.py`: los siete chips y uno desconocido.
- `test_service_list_membership_filters.py` (`reloj` en 2026-10-21, `expiring_days` 7): "por vencer" (fin el 2026-10-25) frente a "al día" (fin el 2026-11-30); `pending_payment`; `none` como complemento; vigente más futura muestra la vigente; filtro por plan de la vigente; plan inexistente da vacío; `none` con `plan_id` da vacío; un socio dado de baja con membresía aparece con `status=deleted` y su estado; 5.000 ids en el conjunto no revientan el límite de parámetros; la rama de documento sigue usando `uq_members_document_idx_alive` (el `EXPLAIN` de `test_list_perf.py` no cambia); ninguna fila `decrypt`; las columnas decoradas salen de `status_for` en una sola llamada por página (contador de consultas).
- `test_router_list_filters.py`: 422 con `membership_status="moroso"` (`field="membership_status"`) y con `plan_id` no UUID; 200 de coach con `status=deleted` (N-20); `plan_name` presente en cada fila con membresía.
- `test_service_get.py`: los cinco campos vuelven enmascarados (`CC •••• 2046`, `••• ••• 4321`, `l•••@•••.co`, `••/••/1991`, `Registrado`, las máscaras de `KNOWN`); cinco filas `decrypt` con `purpose='mask'`, `record_id` del socio y `user_id` del actor, y ninguna `reveal` en `audit.audit_log` (`SELECT verb, purpose, count(*) FROM crypto.crypto_ops WHERE record_id = <id> GROUP BY 1, 2` da `decrypt | mask | 5`); un socio dado de baja devuelve `deleted_at`; `membership_status`, `plan_name` y `membership_end_date` de `status_for`; campos nulos no generan fila.
- `test_router_get.py`: 200 admin y coach; 200 de coach sobre un dado de baja; 403 `member`; 401; 404; 422 por id no UUID; `Cache-Control: no-store`; la respuesta no contiene el documento en claro; `caplog` sin valores.

Gate: `bash scripts/workflow/slice-gate.sh members tests/members/test_chip_to_filter.py tests/members/test_service_list_membership_filters.py tests/members/test_router_list_filters.py tests/members/test_service_get.py tests/members/test_router_get.py`, más `cd web && npx vitest run src/features/members/schemas.test.ts` por la compatibilidad de D35.

### S3-B10 · Revelar, editar, dar de baja y reactivar (US-074, US-075, US-076)

Crear o modificar en `members/`:
- `rules.py`: `diff_fields(before, patch) -> frozenset[str]` (compara los normalizados de documento, teléfono y correo; `null` sobre un opcional con valor cuenta como cambio) y `ensure_can_change(fields, role)`.
- `schemas.py`: `RevealIn(field: Literal["document","phone","email","birth_date","emergency_contact"])` con `extra="forbid"`; `RevealOut(field, value: str | EmergencyContactOut | None)` (la fecha como `AAAA-MM-DD`); `MemberPatch`.
- `exceptions.py`: `MemberDeactivated` (409 `member_deactivated`), `MemberFieldForbidden` (403 `forbidden_field`, con `field`), `MemberAlreadyDeactivated` (409 `member_already_deactivated`) y `MemberNotDeactivated` (409 `member_not_deactivated`).
- `detail.py`: `reveal(session, member_id, field) -> RevealOut` (D19).
- `changes.py`: `update(session, member_id, patch, *, role) -> MemberDetailOut` (D21; la comparación descifra los valores actuales con `mask`, la asignación usa `Secret.from_plain` y el tipo recifra y reindexa en el mismo flush; si cambia el documento, pre-chequeo por `id_by_document` y traducción de `uq_members_document_idx_alive`); `deactivate(session, member_id) -> None`; `reactivate(session, member_id) -> MemberDetailOut`. Eventos `MemberUpdated(member_id, changed_fields)` y `MemberDeactivated(member_id)`, sin valores.
- `router.py`: `POST /members/{member_id}/reveal` (200, admin y coach, límite `members-reveal` de 30 por minuto, `responses_for(404, 429)`), `PATCH /members/{member_id}` (200, límite `members-write`, `responses_for(403, 404, 409, 429)`), `DELETE /members/{member_id}` (204, solo admin, `responses_for(404, 409)`) y `POST /members/{member_id}/reactivate` (200, solo admin, `responses_for(404, 409)`).
- `tests/architecture/test_error_codes_per_route.py`: `CON_LIMITE` gana `patch /api/v1/members/{member_id}` y `post /api/v1/members/{member_id}/reveal`.
- `tests/architecture/test_no_physical_delete.py` (D21), que reemplaza a `test_no_physical_delete_users.py`.
- `tests/architecture/test_no_sensitive_in_logs.py`: la prueba de `reveal` deja de saltarse.
- `tests/audit/test_reveal_entry.py`: usa `make_member` y el service real.
- `docs/openapi.json` y tipos.

Rojo (casos clave):
- `test_service_reveal.py`: el valor descifrado coincide con el sembrado en los cinco campos; exactamente una fila `reveal` en `audit.audit_log` con `user_id`, `record_id`, `subject_member_id` y `after == {"field": ...}`, sin el valor; exactamente una fila `decrypt` en `crypto_ops` con `purpose='reveal'`, `data_class='member.<campo>'` y `record_id`; si `audit.record` lanza (`monkeypatch`) no queda `reveal` ni valor, pero sí el `decrypt` (`after_soft_rollback`); campo vacío devuelve `None` y también audita; ningún suscriptor agrega una segunda fila; funciona sobre un dado de baja.
- `test_router_reveal.py`: 200 admin y coach con `{field, value}`; 422 con `field="field"` para `"first_name"`; 403 `member` sin fila `reveal`; 401; 404; `Cache-Control: no-store`; fallo simulado del commit responde 500 y el cuerpo no contiene el valor; el límite de 30 por minuto da 429; `caplog` y stdout sin el valor.
- `tests/audit/test_reveal_entry.py`: con `make_member` y `members.service.reveal`, una fila `reveal`, la cadena verifica (`verify_chain`) y el valor no está en `before` ni `after`.
- `test_member_patch_rules.py`: `diff_fields` (sin cambios; un cambio; solo de formato `"300 123 4567"` frente a `"3001234567"`; `null` en opcional) y `ensure_can_change` (admin y coach, con y sin `document`).
- `test_service_update.py`: cambiar el teléfono cambia el blob (nonce distinto), descifra al nuevo valor, recalcula `phone_idx` y la búsqueda por el número viejo ya no encuentra; documento repetido da `MemberDocumentDuplicated` sin cambios parciales; dado de baja da `MemberDeactivated`; auditoría `update` solo con las columnas cambiadas (`before ? 'phone'` verdadero, `before ? 'first_name'` falso); PATCH sin cambios no deja auditoría ni evento; `MemberUpdated.changed_fields` sin valores; el coach con `document` distinto da `MemberFieldForbidden`, y con el mismo documento en otro formato no; los `*_idx` salen como `***` en la auditoría.
- `test_router_update.py`: 200 admin y coach; 403 `member`; 403 coach con `document` y `field="document"`; 401; 404; 409 (`member_document_duplicated` con `existing_id` y `member_deactivated`); 422 (`last_name` vacío, `sex` inválido, `birth_date` futura, `document: null`); `warnings` presente.
- `test_service_deactivate.py` (con `reloj`): la fila sigue con `deleted_at` en UTC y `status='inactive'`; auditoría `update`; `MemberDeactivated` emitido; sale de la lista por defecto y de la búsqueda por documento, teléfono, correo y nombre; un socio nuevo con el mismo documento se crea; las filas de `memberships` y `payments` no cambian (SQL crudo antes y después, con las fábricas); baja repetida da `MemberAlreadyDeactivated`; reactivar vuelve a `active`; reactivar con el documento tomado da `MemberDocumentDuplicated` con `existing_id`; reactivar un vivo da `MemberNotDeactivated`.
- `test_router_deactivate.py`: 204 admin; 403 coach y `member`; 401; 404; 409; `reactivate` 200 admin, 403 coach, 409 de ambos tipos.
- `test_no_physical_delete.py` y `tests/core/test_logging_redact.py` (un `reveal` real: ni el valor ni el blob en los logs; cierra T8 de US-018).

Gate: `bash scripts/workflow/slice-gate.sh members tests/members/test_service_reveal.py tests/members/test_router_reveal.py tests/members/test_member_patch_rules.py tests/members/test_service_update.py tests/members/test_router_update.py tests/members/test_service_deactivate.py tests/members/test_router_deactivate.py tests/architecture/test_no_physical_delete.py`, `bash scripts/workflow/slice-gate.sh audit tests/audit/test_reveal_entry.py` y `bash scripts/workflow/slice-gate.sh core/logging tests/core/test_logging_redact.py`.

### S3-B11 · Pestañas de la ficha (US-093, US-101 backend)

Crear o modificar:
- `plans/service.py`: `search_ids(session, q) -> set[UUID]` (planes vivos o no, con el mismo pliegue de tildes de `list`; sin `q` devuelve vacío). Lo usa la lista de la ficha para su `q` (D28).
- `memberships/queries.py`: `list_for_member(session, member_id, page, *, q=None) -> Page[MembershipOut]`: `members.ensure_exists(include_deleted=True)` (404), orden `start_date DESC, id`, incluye canceladas, congelaciones y `paid_cop` por lote; `q` filtra por nombre de plan.
- `memberships/router.py`: `GET /members/{member_id}/memberships` (admin y coach, paginado, `q`, `responses_for(404)`).
- `payments/queries.py` y `router.py`: `list_for_member(session, member_id, voided, page, *, q=None) -> Page[PaymentRow]` sobre `list` (`member_id` fijo; `q` es la referencia exacta; `members.ensure_exists(include_deleted=True)`) y `GET /members/{member_id}/payments` (admin y coach, `voided` opcional, `responses_for(404)`).
- `docs/openapi.json` y tipos. El ancla de `tests/architecture/test_list_rows_without_sensitive_fields.py` ya cubre las dos rutas (D28).

Rojo:
- `test_member_memberships_service.py`: orden por `start_date` descendente; incluye canceladas; un socio dado de baja devuelve sus membresías; socio inexistente da `MemberNotFound`; congelaciones sin N+1; `q` por nombre de plan; el estado mostrado es el efectivo.
- `test_member_memberships_router.py`: 200 con forma paginada; `limit=0` da 422; 404; 403 `member`; 401.
- `test_list_for_member.py`: tres pagos en dos membresías (uno anulado) en orden descendente; `voided=false` devuelve dos; dado de baja devuelve sus pagos; inexistente 404; `q` por referencia.
- `test_router_member_payments.py`: 200 coach y admin; 404; 422 con `limit=0` y `201`; 403 `member`; 401.

Gate: `bash scripts/workflow/slice-gate.sh memberships tests/memberships/test_member_memberships_service.py tests/memberships/test_member_memberships_router.py` y `bash scripts/workflow/slice-gate.sh payments tests/payments/test_list_for_member.py tests/payments/test_router_member_payments.py`. Al cerrar el backend (wave 3), `bash scripts/workflow/run-gates.sh`, cobertura global de `app` de 80 % o más, `cd api && uv run pytest tests/architecture -q`, el ciclo de Alembic completo sobre `0011` y las corridas `perf`.

## 5. Front, slice por slice

Gate de cada slice: `bash scripts/workflow/slice-gate.sh web/<feature> <archivos de Rojo>` (más `web/shared` cuando se toca el kit) y, al cerrar la wave, `cd web && npm run lint && npx tsc --noEmit && npm test && npm run build`. Las pruebas usan `mockApi` y `renderWithProviders` de `web/src/test/`, y los fixtures nuevos van en `web/src/test/memberships.tsx` y `web/src/test/payments.tsx`.

### S3-F1 · Ficha del socio (US-073, US-074, US-075, US-076 front)

Crear o modificar en `web/src/features/members/`:
- `schemas.ts`: `memberDetailViewSchema` (todos los campos de `MemberDetailOut`; los cinco sensibles como `string | null` enmascarados), `revealOutSchema` (valor `string`, objeto de contacto o `null`), `MemberPatchBody`, `memberEditSchema(today)` (las reglas de `memberFormSchema` con todo opcional salvo nombres) y `toMemberPatch(values, dirtyFields)`; `flattenRevealed(field, value) -> string` (el contacto de emergencia se aplana a "Nombre · Parentesco · Teléfono", la fecha se formatea con `formatDate`).
- `api.ts`: `useMember(id)` (clave `["members", "detail", id]`, `gcTime` normal; el detalle solo trae máscaras), `useRevealField(id)` (mutación con `gcTime: 0`, sin `setQueryData`, sin invalidar), `useUpdateMember(id)` (`gcTime: 0`; al salir invalida el detalle y la lista), `useDeactivateMember()` y `useReactivateMember()` (invalidan `["members"]`).
- `memberErrors.ts`: mensajes para `forbidden_field`, `member_deactivated`, `member_already_deactivated`, `member_not_deactivated` y el 409 de documento con enlace a `/socios/{existing_id}` (cierra S2-D34).
- `pages/MemberDetailPage.tsx` (+ css): `PageHeader` con nombre, `StatusTag` de membresía y acciones por rol con `useCan` (Editar y Vender para `members.update` y `memberships.sell`; Dar de baja con `members.delete`); migas Socios, nombre; bloque de datos con un `MaskedValue` por campo (`key={id}`, `onReveal` llama a `useRevealField(...).mutateAsync` y devuelve `flattenRevealed(...)`, `revealAction="members.reveal"`); aviso "Sin autorización de datos registrada" si `data_consent_at` es nulo (Q16, `// DESIGN-GAP:`); `Tabs` con Datos, Membresías, Pagos (contenido en F7) e Historial (deshabilitada con `disabledUntil`, llega con US-106) y las demás con su versión (Asistencia v0.4, Resultados v0.5, Atleta v0.6, Avisos v0.2, Adjuntos v0.3); si `deleted_at` no es nulo: etiqueta "Dado de baja", sin acciones de edición ni venta y "Reactivar" solo con `members.reactivate`; estados de carga, 404 ("Socio no encontrado") y error con reintento.
- `components/DeactivateMemberModal.tsx` con `ConfirmModal` (texto: "El socio deja de aparecer en la lista; sus membresías, pagos e historial se conservan"; errores del API) y la acción Reactivar con `ConfirmModal`.
- `pages/MemberFormPage.tsx`: modo edición en `/socios/:id/editar` (`useParams`): campos no sensibles precargados desde `useMember`; los sensibles vacíos con su máscara como ayuda y un botón "Cambiar" (el de documento solo con `members.document.update`); envía solo los campos modificados (`dirtyFields`); el 403 `forbidden_field` y el 409 se muestran bajo su campo. `// DESIGN-GAP:` de presentación de campos sensibles en edición.
- `config/routeTable.ts`: `load` para `/socios/:id` (MemberDetailPage) y `/socios/:id/editar` (MemberFormPage); `routes.test.ts` actualizado.
- `shared/ui/MaskedValue.tsx`: sin cambios de comportamiento; cierra el criterio diferido de US-066 con su prueba nueva.

Rojo:
- `src/features/members/pages/MemberDetailPage.test.tsx`: acciones por rol (coach sin Dar de baja ni Reactivar); modo solo lectura del dado de baja; aviso de autorización; pestañas en la URL; 404; los cinco campos enmascarados con el texto del API.
- `src/shared/ui/MaskedValue.reveal.test.tsx` (`fakeTimers`): una sola llamada por clic, re-enmascarado a los 60 s, al ocultar y al desmontar; error 403 y 500 sin valor en pantalla; el claro nunca llega a `localStorage`, `sessionStorage` ni a la caché de TanStack Query.
- `src/features/members/pages/MemberFormPage.edit.test.tsx`: solo envía los campos modificados; nunca muestra el valor en claro; "Cambiar" del documento oculto al coach; 409 con enlace.
- `DeactivateMemberModal.test.tsx` y la prueba de "Reactivar" en `MemberDetailPage.test.tsx`.

Gate: `bash scripts/workflow/slice-gate.sh web/members src/features/members/pages/MemberDetailPage.test.tsx src/features/members/pages/MemberFormPage.edit.test.tsx src/features/members/components/DeactivateMemberModal.test.tsx` y `bash scripts/workflow/slice-gate.sh web/shared src/shared/ui/MaskedValue.reveal.test.tsx`.

### S3-F2 · Filtros de la lista y vista móvil (US-071, US-072)

Crear o modificar:
- `features/memberships/api.ts` (nace aquí, F3 lo amplía): `useMembershipSummary()` con `membershipSummarySchema` (cinco enteros). Se adelanta desde F5 porque los chips de socios muestran conteos (D37).
- `features/members/schemas.ts`: `MEMBERSHIP_CHIPS` (siete, con `chipToFilter`), `memberRowSchema` ya con `membership_end_date`; `MembersParams` y `membersQueryKey` ganan `membership_status` y `plan_id`.
- `features/members/components/MemberStatusChips.tsx`: `Chips` de modo único con Todos, Al día, Por vencer, Vencidos, Congelados, Pendiente de pago (`// DESIGN-GAP:` Q3), Sin membresía y Dados de baja (visible a admin y coach, N-20), con conteos del resumen; el valor vive en la URL y cambiarlo reinicia `offset`.
- `features/members/components/PlanFilter.tsx`: `<select>` dentro de `Field` con `usePlans({ active: true })`. Como el coach no ve `/planes` pero sí `GET /plans?active=true`, el hook ya existe (S2-D26).
- `features/members/pages/MembersListPage.tsx`: columnas Plan vigente y Vence; `FILTERS` gana `membership_status` y `plan_id`; bajo `MOBILE_QUERY` usa `MemberCardList` (D39).
- `features/members/components/MemberCardList.tsx` y `useMembersInfinite(params)` (`useInfiniteQuery`; `getNextPageParam = offset + limit < total ? offset + limit : undefined`): tarjeta con nombre, `StatusTag`, plan y "vence"; la tarjeta entera es un enlace de al menos 44 px; etiqueta "Dado de baja"; "Cargar más" que acumula y desaparece al llegar al total; si la página siguiente falla conserva las tarjetas y muestra "Reintentar"; botón flotante "Nuevo socio" con `members.create`; chips en un contenedor con `overflow-x: auto` propio. Nada sensible, ni enmascarado.
- `web/tests/e2e/members-mobile.spec.ts` (proyecto `preview`, API simulada con 60 socios) a 390 × 844 y 320 × 640: buscar "laura" y abrir la ficha, "Cargar más" dos veces, `scrollWidth <= innerWidth`, axe en claro y oscuro, capturas.

Rojo: `MemberStatusChips.test.tsx` (URL, reinicio de `offset`, `aria-pressed`, texto, conteos); `MemberCardList.test.tsx` (con `matchMedia` simulado: tarjetas en móvil, "Cargar más" acumulativo, error en la segunda página, botón según permiso); `MembersListPage.test.tsx` ampliado (columnas Plan y Vence, filtro de plan en la petición).

Gate: `bash scripts/workflow/slice-gate.sh web/members src/features/members/components/MemberStatusChips.test.tsx src/features/members/components/MemberCardList.test.tsx src/features/members/pages/MembersListPage.test.tsx` y `cd web && npx playwright test tests/e2e/members-mobile.spec.ts --project=preview`.

### S3-F3 · Vender, primer pago y renovar (US-084, US-085, US-088 front)

Crear o modificar en `web/src/features/memberships/`:
- `schemas.ts`: `membershipOutSchema` y `sellMembershipOutSchema` (montos enteros), `sellMembershipSchema(today)` (Zod; `plan_id`, `renew`, `first_payment` opcional con monto entero positivo, medio, referencia de hasta 64 y fecha), `renewalPreviewSchema` y `toSellBody(values)` (con `renew: true` no envía `start_date`).
- `api.ts`: `useSellMembership(memberId)` (mutación con `gcTime: 0`; invalida `["memberships"]`, `["members"]` y `["payments"]`), `useRenewalPreview(memberId, planId)` (se habilita con el plan elegido).
- `membershipErrors.ts`: mensajes en español por código (`membership_conflict` con enlace "Renovar" a `?socio=:id&renovar=1`, `future_membership_exists`, `membership_overlap`, `member_inactive`, `plan_inactive`, `start_date_too_retroactive`, `first_payment.*`).
- `lib/rules.ts`: `computeEndDate` (vista previa; manda el servidor), `saldo(price, paid)` y `exceedsBalance`.
- `pages/SellPage.tsx` en `/membresias/vender` y `?socio=:id&renovar=1`: los tres pasos del diseño en una página (socio, plan y fechas, pago) con React Hook Form y Zod. Socio: buscador `GET /members?q=` o fijo si viene `socio`; plan: `usePlans({ active: true })`; inicio por defecto hoy en Bogotá, de solo lectura con el texto "Empieza el 29 oct 2026, al día siguiente de que termine la actual" cuando `renovar=1`; fin calculado; "Precio pactado" de solo lectura (D16, `// DESIGN-GAP:`). Resumen a la derecha con vigencia, precio, pago y saldo.
- `components/FirstPaymentSection.tsx`: medios con las etiquetas de `usePaymentMethods()` (el hook y su esquema nacen en F3 en `features/payments/api.ts` y `schemas.ts`; F4 los reutiliza), valor precargado con el precio, referencia visible para Nequi y Bre-B (opcional, `// DESIGN-GAP:`), fecha y hora del pago (por defecto ahora, enviada en UTC). Si el valor supera el precio: `ConfirmModal` de Q5 y solo envía al confirmar. Botón "Vender y cobrar"; sin pago, "Vender".
- `config/features.ts` agrega `memberships`; `routeTable.ts` da `load` a `/membresias/vender`; `features.test.ts`, `nav.test.ts` y `routes.test.ts` al día.
- E2E: `web/tests/e2e/sell-with-payment.spec.ts` (preview, API simulada: vender con pago completo, ver el 201 y el cuerpo) y `web/tests/e2e/stack/sell-with-payment.spec.ts` (contra el stack: vender por la pantalla, comprobar "Al día" en `/socios`; es la venta real de `verify-delivery`).

Rojo: `SellPage.test.tsx` (resumen, formato de moneda y fecha, 409 con enlace, sin planes activos, error por campo con foco, un solo envío por doble clic), `SellPage.renew.test.tsx` (fecha calculada visible y no editable, cambio de plan refresca la vista previa, 409), `FirstPaymentSection.test.tsx` (referencia según medio, advertencia de excedente y confirmación, error `first_payment.*` bajo su campo), `lib/rules.test.ts`, `schemas.test.ts`.

Gate: `bash scripts/workflow/slice-gate.sh web/memberships src/features/memberships/pages/SellPage.test.tsx src/features/memberships/pages/SellPage.renew.test.tsx src/features/memberships/components/FirstPaymentSection.test.tsx src/features/memberships/lib/rules.test.ts` y el E2E de `preview`.

### S3-F4 · Registrar y anular pagos, y medios de pago (US-056, US-095, US-097 front)

Crear o modificar:
- `features/payments/schemas.ts`: `paymentRowSchema`, `paymentDetailSchema`, `paymentMethodsSchema`, `registerPaymentSchema`, `voidPaymentSchema` (motivo de 1 a 500 tras recortar).
- `features/payments/api.ts`: `usePaymentMethods()` (nace en F3; `staleTime` de 5 minutos; lee `items`), `useRegisterPayment(membershipId)` (`gcTime: 0`; invalida `["payments"]`, `["payments-summary"]`, `["memberships"]` y `["members"]`), `useVoidPayment()` (igual).
- `features/payments/components/RegisterPaymentPanel.tsx` (`SidePanel`): socio (búsqueda `GET /members?q=`) o `memberId` preseleccionado; membresías no canceladas del socio (`GET /members/{id}/memberships`, cada opción con su saldo: "Mensual 25 sep–24 oct · saldo $60.000"); monto, medio, referencia, fecha; advertencia de Q5 con `ConfirmModal`; errores del envelope bajo su campo (`membership_cancelled`, `paid_at`). Si viene precargado desde una anulación, monto y medio ya puestos.
- `features/payments/components/VoidPaymentModal.tsx` (`ConfirmModal` con motivo obligatorio y el texto "El pago no se borra: queda anulado con este motivo"); visible solo con `payments.void`; el 409 muestra "Otra persona lo anuló antes" y refresca el pago; tras anular ofrece "Registrar pago nuevo".
- `features/system/components/PaymentMethodsForm.tsx`: tres filas fijas (Efectivo, Nequi, Bre-B) con `Field` de etiqueta y de ayuda; sin agregar ni quitar; nota "Para agregar un medio nuevo se requiere una actualización del sistema"; `// DESIGN-GAP:` por las casillas de habilitar del diseño. `ConfigPage.tsx` gana la pestaña "Medios de pago"; `system/api.ts` amplía `SettingsKey` y el mapa de esquemas; `schemas.ts` agrega `paymentMethodsSchema`.
- `config/features.ts` agrega `payments`.

Rojo: `RegisterPaymentPanel.test.tsx` (monto entero, error por campo, advertencia Q5 y confirmación, envío en UTC, panel con socio preseleccionado), `VoidPaymentModal.test.tsx` (botón oculto al coach, motivo obligatorio, 409, precarga del pago nuevo), `PaymentMethodsForm.test.tsx` (sin botón de agregar, etiqueta vacía muestra el error bajo "Efectivo", guardar muestra "Cambios guardados", conflicto de versión), `api.test.ts` (los tres medios en orden).

Gate: `bash scripts/workflow/slice-gate.sh web/payments src/features/payments/components/RegisterPaymentPanel.test.tsx src/features/payments/components/VoidPaymentModal.test.tsx src/features/payments/api.test.ts` y `bash scripts/workflow/slice-gate.sh web/system src/features/system/components/PaymentMethodsForm.test.tsx src/features/system/pages/ConfigPage.test.tsx`.

### S3-F5 · Pantalla de membresías (US-089, US-090, US-091, US-092 front)

Crear o modificar en `web/src/features/memberships/`:
- `api.ts`: `useMemberships(params)` (clave `["memberships", params]`, `keepPreviousData`), `useMembership(id)`, `useFreezeMembership()` y `useCancelMembership()` (mutaciones con `gcTime: 0`; invalidan `["memberships"]`, `["members"]` y `["payments"]`); `useMembershipSummary` ya existe (F2).
- `pages/MembershipsPage.tsx` en `/membresias`: `PageHeader` con "Vender membresía"; `Chips` de estado con conteos (Activas, Por vencer, Vencidas, Congeladas, Pendiente de pago con `// DESIGN-GAP:`, Anuladas); selector de plan; rango "Vence entre" (`ends_from` y `ends_to`); búsqueda en memoria (`localQuery`, S2-D41); `DataTable` con socio (enlace a la ficha), plan y precio, inicio, fin, clases restantes, pagado ("$60.000 de $120.000 · abono"), `StatusTag` con texto y acciones de la fila (Renovar, Registrar saldo con `payments.register`, Congelar con `memberships.freeze`, Anular con `memberships.cancel`). `Pagination`, estados de carga, vacío ("No hay membresías con estos filtros") y error con reintento. Filtros en la URL; `status` viaja separado por comas.
- `components/FreezeModal.tsx`: dos `Field` de fecha, texto en vivo "Son N días; la membresía terminará el 10 nov 2026" (`freezePreview` en `lib/rules.ts`), mensajes en español por código, sin campo de motivo (D14, `// DESIGN-GAP:`), errores 409 de límites con los días disponibles.
- `components/CancelMembershipModal.tsx`: `ConfirmModal` con motivo obligatorio (5 a 500) y el texto "Los pagos asociados no se tocan: si hay que devolver dinero, se anula el pago aparte."
- `config/routeTable.ts`: `load` para `/membresias`.

Rojo: `MembershipsPage.test.tsx` (filtros en la URL, chip de pendiente con texto, Anular oculto al coach, "Registrar saldo" abre el panel de F4, vacío y error), `FreezeModal.test.tsx` y `lib/rules.test.ts` (`freezePreview`; fechas invertidas bloquean el envío; error por código), `CancelMembershipModal.test.tsx` (motivo corto, doble clic, 409), `api.summary.test.ts` (parseo de `useMembershipSummary`).

Gate: `bash scripts/workflow/slice-gate.sh web/memberships src/features/memberships/pages/MembershipsPage.test.tsx src/features/memberships/components/FreezeModal.test.tsx src/features/memberships/components/CancelMembershipModal.test.tsx src/features/memberships/lib/rules.test.ts`.

### S3-F6 · Pantalla de pagos (US-098, US-099, US-100 front)

Crear en `web/src/features/payments/`:
- `api.ts`: `usePayments(params)` (clave derivada de los filtros), `usePayment(id)` y `usePaymentsSummary(month)`.
- `pages/PaymentsPage.tsx` en `/pagos`: `PageHeader` con "Registrar pago" (abre el panel de F4); resumen del mes arriba; `FilterBar` con rango de fechas (el día de Bogotá se convierte a UTC con `core/i18n/format.ts`; `to` es exclusivo), medio, registró, estado (Todos, Válidos, Anulados; D37) y búsqueda en memoria; `DataTable` con fecha y hora de Bogotá, socio, membresía ("Mensual 29 oct–27 nov"), valor, medio, referencia, registró y `StatusTag` "Anulado" con texto; sin botones de editar ni borrar; `Pagination`; vacío "No hay pagos con estos filtros".
- `components/MonthSummary.tsx`: selector de mes (`?mes=AAAA-MM`, por defecto el mes actual de Bogotá), `KpiCard` de total y por medio con `$ 0` cuando es cero, contador de anulados, estados de carga y error.
- `components/PaymentDetailModal.tsx`: socio, membresía, valor, medio, referencia, fecha, quién registró, bloque de anulación (motivo, quién, cuándo); sin editar ni borrar; punto de montaje para `VoidPaymentModal`.
- `config/routeTable.ts`: `load` para `/pagos`.

Rojo: `PaymentsPage.test.tsx` (filtros en la URL, paginación, etiqueta "Anulado", vacío, `to` exclusivo), `PaymentDetailModal.test.tsx` (anulado muestra motivo y autor; no existe botón de editar ni borrar), `MonthSummary.test.tsx` (mes por defecto, cambio de mes en la URL, `$ 0`).

Gate: `bash scripts/workflow/slice-gate.sh web/payments src/features/payments/pages/PaymentsPage.test.tsx src/features/payments/components/PaymentDetailModal.test.tsx src/features/payments/components/MonthSummary.test.tsx`.

### S3-F7 · Pestañas Membresías y Pagos de la ficha (US-093, US-101 front)

Crear:
- `features/memberships/lib/rules.ts`: `membershipActions(memberships, role, today, memberDeleted) -> { renew, sell, freezeIds, cancelIds }` (pura): Renovar si hay vigente o la última está vencida y no hay futura; Vender si no hay vigente ni futura; ninguno si el socio está dado de baja; Congelar para admin y coach sobre `active` o `expiring`; Anular solo admin.
- `features/memberships/components/MemberMembershipsTab.tsx`: tarjeta de la vigente (plan, fechas, días restantes, clases, precio, pagado y saldo, `StatusTag`, congelaciones), tarjeta de la futura (`// DESIGN-GAP:`), tabla paginada del historial (`useMemberMemberships(memberId, page)`), botones de `membershipActions` (Renovar a `/membresias/vender?socio=:id&renovar=1`, Vender, `FreezeModal`, `CancelMembershipModal`); vacío "Este socio no tiene membresías. Vender".
- `features/members/components/MemberPaymentsTab.tsx`: `DataTable` paginada (`useMemberPayments(memberId, { voided, limit, offset })`: fecha en Bogotá, plan, monto, medio, referencia, `StatusTag` "Anulado" con motivo), conmutador "Ocultar anulados", botón "Registrar pago" con `memberId` (oculto si el socio está dado de baja) y "Anular" solo con `payments.void`; vacío "Este socio no tiene pagos".
- Hooks nuevos: `useMemberMemberships(memberId, page)` en `memberships/api.ts` y `useMemberPayments(memberId, { voided, limit, offset })` en `payments/api.ts`. Las dos pestañas se montan en `MemberDetailPage` (F1) con su contenido real.

Rojo: `MemberMembershipsTab.test.tsx` (vigente "Por vencer", futura "Pendiente de pago", historial, sin Renovar ni Anular para coach), `lib/rules.test.ts` (`membershipActions`, todas las ramas), `MemberPaymentsTab.test.tsx` (orden, "Anulado", panel con el socio preseleccionado, sin "Registrar pago" para un dado de baja).

Gate: `bash scripts/workflow/slice-gate.sh web/memberships src/features/memberships/components/MemberMembershipsTab.test.tsx src/features/memberships/lib/rules.test.ts` y `bash scripts/workflow/slice-gate.sh web/members src/features/members/components/MemberPaymentsTab.test.tsx`.

Al cerrar el front (wave 5): `cd web && npm run lint && npx tsc --noEmit && npm test && npm run build && npm run licenses`; E2E `sell-with-payment.spec.ts` y `members-mobile.spec.ts`; `docs/openapi.json` y `types.ts` regenerados y sin diferencias.

## 6. Flujos de datos

Todos los flujos corren en una sola transacción de petición (`SessionDep` confirma antes de enviar la respuesta). "Auditoría" es una fila de `audit.audit_log` escrita por el hook en el flush, con `subject_member_id` del socio.

### 6.1 Vender con primer pago (demo 1)

1. `POST /members/{member_id}/memberships` con `{plan_id, first_payment: {amount_cop: 120000, method: "cash"}}`. `current_user` fija el actor; `require_role("admin", "coach")`.
2. `memberships.sell` abre `begin_nested()` y toma el candado de socio.
3. `members.get_ref` (socio vivo y `active`); `plans.get(for_share=True)` (precio, tipo, duración, activo).
4. `settings.memberships_policy` y "hoy" de Bogotá. Se cargan las membresías no canceladas del socio y sus congelaciones, se calcula el estado efectivo y `classify_open` y `find_overlap` descartan el conflicto.
5. Se inserta `Membership(status="pending_payment", agreed_price_cop=plan.price_cop, end_date=compute_end_date(...))` y `flush`: fila en `memberships.memberships` y auditoría `insert`. `emit(MembershipSold)`.
6. `payments.register(...)` en la misma sesión: el gate toma `FOR UPDATE` de la membresía nueva y devuelve `member_id`; se valida `paid_at`; se inserta el `Payment` con `member_id` copiado; `flush` (auditoría `insert`); `emit(PaymentRegistered)`.
7. `memberships.on_payment_registered`: bloquea la fila, `sum_not_voided` ve el pago (flush previo), `covers(120000, 120000)` y fija `status = compute_status(base activa)`: `active`. Auditoría `update` con `before.status = pending_payment` y `after.status = active`; `emit(MembershipActivated)`.
8. Sale `SellMembershipOut` con `status = active`, `paid_cop = 120000` y `first_payment_id`. Si cualquier paso falla, el savepoint revierte membresía, pago y auditoría. En la base quedan la fila de `memberships`, la de `payments` con `member_id` copiado y las dos auditorías `insert`.

### 6.2 Pago parcial, cobertura y sobrepago (demo 2)

1. Venta con `first_payment` de 60.000: la activación ve 60.000 contra 120.000, no cubre y la membresía sigue `pending_payment` (chip "Pendiente de pago").
2. `POST /memberships/{membership_id}/payments` de 60.000: el gate bloquea y valida (no cancelada), se inserta el pago, `emit(PaymentRegistered)`, el handler suma 120.000, cubre y la pasa a `active`.
3. Un tercer pago o uno mayor al saldo: el servidor lo acepta (Q5). En el front el panel calcula `saldo = agreed_price_cop - paid_cop` y, si el monto lo supera, muestra el modal de confirmación antes de enviar.

### 6.3 Anular un pago (demo 3)

1. `POST /payments/{payment_id}/void` (admin) con `{reason}`.
2. `payments.void` lee el pago, toma el candado de la membresía (gate), luego `FOR UPDATE` del pago, `can_void`, asigna las cuatro columnas y `flush`. El trigger de `0011` deja pasar exactamente esa transición. Auditoría `update` con `before.voided = false` y `after.voided = true`.
3. `emit(PaymentVoided)`: `on_payment_voided` bloquea la membresía, suma sin el anulado, ve que ya no cubre y la devuelve a `pending_payment` (conserva congelaciones y `end_date`). Auditoría `update` de `memberships`; `emit(MembershipActivationReverted)`.
4. Prueba en la base: `UPDATE payments.payments SET amount_cop = 1` falla con `payments_immutable: column`; anular dos veces el mismo pago da 409 `payment_already_voided`; `DELETE` y `TRUNCATE` fallan.

### 6.4 Renovar antes de vencer (demo 4)

1. `GET /members/{member_id}/memberships/renewal-preview?plan_id=` muestra inicio (día siguiente al fin de la vigente, Q1), fin y precio, sin escribir.
2. `POST /members/{member_id}/memberships` con `renew: true` (el `start_date` se descarta). `sell` toma el candado de socio, rechaza con 409 `future_membership_exists` si ya hay una futura, calcula `plan_renewal` sobre el fin ya extendido de la vigente, inserta la futura en `pending_payment` (o `active` con `start_date > hoy` si el primer pago cubre) y no toca la vigente.
3. Si alguien intenta crear a mano una que se solape (otro `start_date` sin `renew`), el código responde 409 `membership_overlap` y, si saltara el código, la `EXCLUDE` `ex_memberships_member_dates` la rechaza en la base con SQLSTATE 23P01.

### 6.5 Congelar y anular la membresía (demo 5)

1. `POST /memberships/{membership_id}/freeze` con `{frozen_from, frozen_to}`: candado de socio, `FOR UPDATE` de la fila, `apply_freeze` valida estado y límites (`settings.memberships`), `find_overlap` contra las demás, inserta `MembershipFreeze`, corre `end_date` en `days` y recalcula `status`. Auditoría `insert` de la congelación y `update` de la membresía. Congelar 10 días desde hoy deja `frozen` y el fin 10 días más tarde. La segunda congelación solo después de terminar la primera (`freeze_already_scheduled` antes); la tercera da 409 `freeze_limit_reached`.
2. `POST /memberships/{membership_id}/cancel` (admin) con motivo: `FOR UPDATE`, `status = cancelled` con motivo, autor y fecha; los pagos no se tocan; la `EXCLUDE` la deja de contar.
3. Pagar una anulada: `POST /memberships/{membership_id}/payments` da 409 `membership_cancelled` (el gate devuelve `cancelled = true`).

### 6.6 Ficha del socio, máscaras y `reveal` (demo 6)

1. `GET /members/{member_id}`: carga el socio (también dado de baja); por cada campo cifrado no nulo, `types.reveal(socio, campo, "mask")` descifra en memoria y deja un `decrypt` con `purpose='mask'` y `record_id`; `mask(...)` arma `CC •••• 4417`. `status_for([id])` aporta estado, plan y fin. Cero filas `reveal`.
2. `POST /members/{member_id}/reveal` con `{field: "document"}`: `types.reveal(socio, "document", "reveal")` más `audit.record(action="reveal", table_name="members.members", after={"field": "document"}, subject_member_id=id)` en la misma transacción; el valor viaja solo en la respuesta con `no-store`. Quedan una fila `reveal` en la auditoría y una `decrypt` (`purpose='reveal'`) en `crypto_ops`.
3. `PATCH /members/{member_id}`: el coach cambia el teléfono (recifrado, `phone_idx` recalculado, auditoría `update` solo con `phone`/`phone_idx`) y recibe 403 `forbidden_field` si envía un documento distinto.
4. `DELETE /members/{member_id}` (admin): `deleted_at` y `status = inactive`; la ficha pasa a solo lectura con la etiqueta "Dado de baja" y `reactivate` la devuelve si el documento sigue libre.

### 6.7 Listas y resumen (demo 7)

1. `GET /members?membership_status=expiring&plan_id=...`: `members.list` pide con import perezoso a `memberships.member_ids_by_status` el conjunto de ids (estado efectivo en SQL con `status_expr`), lo aplica como `id = ANY(...)` y decora la página con `status_for`. Sin `JOIN` entre esquemas ni descifrado.
2. `GET /payments?from=&to=&voided=false` y `GET /payments/summary?month=2026-10` usan la misma condición de rango en Bogotá; `total_cop` del resumen es igual a la suma de la lista con `voided=false` del mismo mes.
3. A 390 px `MembersListPage` cambia a `MemberCardList` con "Cargar más".

## 7. Pruebas de arquitectura

Corren en cada gate de slice (A-5). Nuevas:

- `test_banned_imports.py` (US-083): sin cambios de código; ya recorre todo `src/app` y cubre los archivos nuevos de `memberships` y `payments`. Basta confirmarla verde en cada gate.
- `test_no_cross_models.py` (ampliada, US-084): la tercera prueba se generaliza a "nadie importa los helpers privados de otro módulo" con `PRIVATE_HELPERS` de `auth`, `memberships`, `payments` y `members`; se agrega que `memberships` no importa `members.models`, `plans.models` ni `settings.models`.
- `test_service_import_graph.py` (consolidada, US-085; D2): grafo acíclico sobre aristas de nivel de módulo; `ALLOWED_EDGES` ampliado slice por slice; `LAZY_IMPORT_WHITELIST` igual a los tres pares de G-03; `payments` sin import de `memberships` a nivel de módulo; cada `service.py` se importa en un subproceso limpio y en los dos órdenes; `test_plans_no_agrega_aristas` reescrita. Absorbe `test_service_import_cycles.py`, `test_payments_does_not_import_memberships.py` y `test_payments_dependencies.py`, que no se crean por separado.
- `test_gates_registered.py` (US-085): tras `create_app(settings_prueba, run_migrations_on_startup=False)` y tras `cli._load_module_services()`, `payments_service.membership_gate()` es `memberships.service.membership_payability`; `register` sin gate lanza `MembershipGateNotRegistered` y no deja filas (usa `set_membership_gate(None)` y restaura).
- `test_payment_method_codes.py` (US-056; D24): `PAYMENT_METHOD_CODES`, el `Literal` de `payments.schemas`, `payments.models.PAYMENT_METHODS`, el CHECK del modelo y el texto de `0010_payments.py` coinciden.
- `test_payments_immutability_code.py` (US-096): por `ast`, ningún archivo de `app/modules/payments` contiene `session.delete(`, `delete(Payment)`, `update(Payment)` ni `TRUNCATE`; las asignaciones a `voided`, `void_reason`, `voided_by` y `voided_at` solo ocurren dentro de la función `void`; ninguna otra columna de `Payment` se asigna después de construir el objeto.
- `test_no_cross_schema_sql.py` (US-091): por `ast`, en `app/modules/*` (salvo `audit`, que lee la cadena) ninguna cadena pasada a `text(...)` ni literal con `FROM`/`JOIN` nombra una tabla de otro esquema (`members.`, `plans.`, `memberships.`, `payments.`, `auth.`, `settings.`); control con una fuente falsa que debe fallar. La resolución de nombres entre módulos va siempre por `service`.
- `test_no_physical_delete.py` (US-076; reemplaza a `test_no_physical_delete_users.py`): sin `session.delete(`, `delete(Member|Plan|User|Membership|Payment)` ni `DELETE FROM` sobre esas tablas en `app/modules`.

Cambios a las existentes (D40):
- `test_audited_tables.py`: `memberships.memberships`, `memberships.membership_freezes` y `payments.payments` pasan de `PENDING_AUDITED` a `REQUIRED_AUDITED_TABLES_V01`; `PENDING_AUDITED` conserva el mecanismo con entradas futuras (`classes.class_sessions` para el Sprint 7 y `notifications.notifications` para el Sprint 5) para no dejar vacía la parametrización; nueva prueba de que `memberships.memberships` y `payments.payments` declaran `__audit_subject__ = "member_id"` (G-05).
- `test_audit_module.py`: `MODULES == ("auth", "settings", "audit", "members", "plans", "memberships", "payments")`, con `memberships` y `payments` entrando en B1 y B3.
- `test_list_rows_without_sensitive_fields.py`: sin cambios de código; vigila las dos listas anidadas por socio.
- `test_error_codes_per_route.py`: `CON_LIMITE` ampliado (D27); `PUBLICAS` no cambia.
- `test_list_routes_use_page_params.py`: el conjunto esperado de listas gana `GET /api/v1/memberships`, `GET /api/v1/payments`, `GET /api/v1/members/{member_id}/memberships` y `GET /api/v1/members/{member_id}/payments`.
- `test_settings_no_secrets.py`: `payment_methods` cumple `SECTION_REGISTRY == ENABLED_SECTIONS` y no tiene campos con nombre de secreto.
- `test_no_sensitive_in_logs.py`: la prueba `reveal` deja de saltarse (B10): login de coach, alta de socio, `GET /members/{id}`, `POST .../reveal` de documento y teléfono, `PATCH`; ni stdout ni `caplog` contienen `KNOWN_NORMALIZED`, el access, el refresh ni `apx1.`.
- `tests/core/test_logging_redact.py`: un `reveal` real (B10).

## 8. Fixtures y fábricas

- `tests/factories/memberships.py`: `make_membership(session, member, plan, *, status="pending_payment", start=None, end=None, price=None, classes_remaining=None, **cambios) -> Membership`. Calcula `start` desde el `reloj` si no se pasa y `end` con `compute_end_date`; inserta por ORM bajo `actor_scope(SYSTEM_USER_ID)` y confirma el savepoint (como `make_plan`). `make_freeze(session, membership, frozen_from, frozen_to) -> MembershipFreeze` (calcula `days`; no mueve `end_date`: la prueba de `freeze` usa el service). `make_memberships(session, n, ...)` para `perf`.
- `tests/factories/payments.py`: `make_payment(session, membership, *, amount=None, method="cash", paid_at=None, voided=False, void_reason=None, reference=None) -> Payment`. Toma `member_id` de la membresía, inserta por ORM (el `INSERT` con `voided=true` es legal para el trigger) y no emite eventos: sirve para listas y sumas. Las pruebas de activación y reversión pasan por `payments.service.register` y `void`.
- `tests/factories/__init__.py`: `FACTORIES` gana las dos; `tests/architecture/test_no_plaintext_at_rest.py` solo exige fábrica a tablas con columnas cifradas, no a estas.
- `tests/payments/conftest.py`: `GateDoble` (un `dict[UUID, MembershipPayability]` y un `__call__` async) y la fixture opt-in `gate_doble` (guarda `membership_gate()`, registra el doble y restaura al salir). Se usa en `test_register.py`, `test_payment_methods_router.py` y las pruebas de service de B3; no en `test_router_register.py` ni en `test_gates_registered.py`.
- `tests/conftest.py`: `LIMPIAR_PAYMENTS` (`ALTER TABLE payments.payments DISABLE TRIGGER USER`, `DELETE`, `ENABLE TRIGGER USER`, con `to_regclass`), `LIMPIAR_MEMBERSHIPS` (congelaciones y después membresías, con `to_regclass`), añadidos a `LIMPIEZA_DE_SESION` y al `finally` de `dos_sesiones`, antes de `LIMPIAR_MEMBERS`.
- `tests/memberships/_apoyo.py` y `tests/payments/_apoyo.py`: rutas (`MEMBERSHIPS`, `PAYMENTS`), `cuerpo(...)` de venta, de pago y de anulación, `CAMPOS_*` (claves exactas de cada respuesta), lecturas con SQL crudo de las tres tablas nuevas y de `crypto.crypto_ops`.
- `reloj`: sin cambios. Casos de fechas en `T0` = 2026-10-21: vigente hasta 2026-10-28 se arma con `reloj.today_bogota()` menos 23 días y `duration_days = 30` (inicio 2026-09-28); congelar "hoy menos 7" es 2026-10-14; `max_retroactive_days` por defecto es 7.
- `dos_sesiones` (commit real): para `sell` concurrente y pagos concurrentes; las llaves del bus se confirman con `bus_confirmado` de `tests/members/conftest.py` (se copia a `tests/memberships/conftest.py`, porque el flush de un socio con cifrado necesita las llaves confirmadas).
- `capturar_eventos(MembershipSold, PaymentRegistered, ...)` para los eventos; los services se importan al nivel del archivo de prueba (sección 2).

## 9. Mapa endpoint a front

Roles: A = admin, C = coach. Slice de backend entre paréntesis.

Socios:
- `GET /members` con `membership_status` y `plan_id` (B9; A, C): `MembersListPage`, `MemberStatusChips`, `PlanFilter` y `MemberCardList` (F2).
- `GET /members/{member_id}` (B9; A, C): `MemberDetailPage` y `useMember` (F1).
- `PATCH /members/{member_id}` (B10; A, C): `MemberFormPage` en edición y `useUpdateMember` (F1).
- `POST /members/{member_id}/reveal` (B10; A, C): `MaskedValue.onReveal` y `useRevealField` (F1).
- `DELETE /members/{member_id}` (B10; A): `DeactivateMemberModal` y `useDeactivateMember` (F1).
- `POST /members/{member_id}/reactivate` (B10; A): acción Reactivar de la ficha y `useReactivateMember` (F1).
- `POST /members/{member_id}/memberships` (B1, B4, B6; A, C): `SellPage`, `FirstPaymentSection` y `useSellMembership` (F3).
- `GET /members/{member_id}/memberships/renewal-preview` (B6; A, C): `SellPage` en modo renovar y `useRenewalPreview` (F3).
- `GET /members/{member_id}/memberships` (B11; A, C): `MemberMembershipsTab` y `useMemberMemberships` (F7); también las opciones de `RegisterPaymentPanel` (F4).
- `GET /members/{member_id}/payments` (B11; A, C): `MemberPaymentsTab` y `useMemberPayments` (F7).

Membresías:
- `GET /memberships/summary` (B7; A, C): `useMembershipSummary`, chips de `MembersListPage` (F2) y de `MembershipsPage` (F5).
- `GET /memberships` (B7; A, C): `MembershipsPage` y `useMemberships` (F5).
- `GET /memberships/{membership_id}` (B7; A, C): `useMembership` (F5) y el saldo de `RegisterPaymentPanel` (F4).
- `POST /memberships/{membership_id}/freeze` (B2; A, C): `FreezeModal` y `useFreezeMembership` (F5, F7).
- `POST /memberships/{membership_id}/cancel` (B6; A): `CancelMembershipModal` y `useCancelMembership` (F5, F7).
- `POST /memberships/{membership_id}/payments` (B3, B4; A, C): `RegisterPaymentPanel` y `useRegisterPayment` (F4).

Pagos:
- `GET /payments` (B8; A, C): `PaymentsPage` y `usePayments` (F6).
- `GET /payments/summary` (B8; A, C): `MonthSummary` y `usePaymentsSummary` (F6).
- `GET /payments/methods` (B3; A, C): `usePaymentMethods` (F3, F4).
- `GET /payments/{payment_id}` (B8; A, C): `PaymentDetailModal` y `usePayment` (F6).
- `POST /payments/{payment_id}/void` (B5; A): `VoidPaymentModal` y `useVoidPayment` (F4, F6, F7).

Settings (solo A):
- `GET` y `PATCH /settings/payment_methods` (B3): `PaymentMethodsForm` en la pestaña "Medios de pago" de `ConfigPage` (F4).

Son 22 endpoints nuevos (9 de socios, 6 de membresías, 5 de pagos y 2 de settings) más los filtros nuevos de `GET /members`. Ninguno devuelve un arreglo suelto; `GET /payments/methods` devuelve `{items}` (D25).

## 10. Riesgos y puntos abiertos

Riesgos con mitigación:
1. [HIGH] Nudo de dependencias (bus transaccional, puerto G-03, handler de cobertura, trigger). Mitigación: slices pequeños en orden estricto, grafo de services con el cambio de D2 desde B1, `test_gates_registered` y `test_service_import_graph` en cada gate desde B4, suite completa de `memberships` y `payments` con `run-gates.sh` al cerrar cada slice.
2. [HIGH] Trigger de `0011` demasiado estricto o demasiado laxo. Mitigación: una prueba por columna protegida y por columna de anulación, doble anulación, `DELETE`, `TRUNCATE` y `UPDATE` sin cambios; revisión por `database-reviewer`; volcado previo y `downgrade` simétrico que no toca datos; limpieza de pruebas con `DISABLE TRIGGER USER` (D30).
3. [HIGH] `EXCLUDE` frente a renovación anticipada, congelación que extiende y cancelación. Mitigación: pruebas con vigente más futura, congelada y extendida, y cancelada; la comprobación de código va antes y la restricción es la red; candado de socio (D3).
4. [HIGH] Estado desfasado sin el job de vencimientos. Mitigación: D5 (estado derivado de la fecha, con `status_expr` y prueba de paridad). Si se rechaza D5, hay que adelantar US-094 o aceptar que "Al día" no cambia solo hasta el Sprint 4A.
5. [MEDIUM] Interbloqueo entre candado de socio, filas y cadena de auditoría. Mitigación: el orden y la invariante de D3; pruebas concurrentes con `dos_sesiones` en venta, renovación, pago y anulación.
6. [MEDIUM] El doble del gate oculta un error del gate real. Mitigación: `gate_doble` opt-in; `test_router_register.py` y `test_gates_registered.py` usan el real.
7. [MEDIUM] `status_expr` y `compute_status` divergen. Mitigación: prueba de paridad en cada cambio de la regla; ambos viven en `memberships`.
8. [MEDIUM] Contrato entre B9 y F2: `memberRowSchema` es estricto y un campo nuevo sin esquema deja la lista en `invalid_response`. Mitigación: D35.
9. [MEDIUM] Carrera entre vender y dar de baja un plan: `get(for_share=True)` desde B1; US-082 la cierra en el Sprint 4A.
10. [MEDIUM] La lista de pagos expone el correo de quien registró al coach (`registered_by_name`). Es el dato que muestra `Pagos.html` ("Registró"); se acepta y se reemplaza por el nombre con US-110.
11. [LOW] `pending_payment` vieja bloquea ventas (D8): visible y anulable; sin autoexpiración.
12. [LOW] Última escritura gana en `PATCH /members` (D21): no hay control de versión en el contrato.
13. [LOW] El volcado previo a `0011` contiene blobs cifrados y llaves envueltas: queda fuera de git (D30) y se borra al cerrar el sprint.

Puntos abiertos que decide el orquestador (con la opción recomendada):
1. D5: estado derivado en lectura. Recomendado: sí.
2. D14: `freeze_limit_reached`, `freeze_days_exceeded`, `membership_not_freezable` y `freeze_already_scheduled` como 409 (el desglose decía 422). Recomendado: 409; la demo del sprint ya lo espera.
3. D16: fin de vigencia por N-23 frente al "29 oct – 27 nov" del diseño. Recomendado: N-23, avisar al diseño.
4. D2: mover el cambio del grafo de services de B4 a B1. Recomendado: B1 (falla desde ahí).
5. D3: `sell(..., enforce_retroactive_limit)` en lugar de `max_retroactive_days`; services sin `by` ni `clock`. Recomendado: sí, corregir `05_service_design.md`.
6. D19: sin evento `SensitiveFieldRevealed` y sin `commit()` explícito en el router. Recomendado: sí (el evento duplicaría la fila; N-1 ya cubre el commit).
7. D25: `GET /payments/methods` como objeto `{items}`. Recomendado: sí (la prueba de listas lo exige).
8. D37: conteos de chips con `GET /memberships/summary` y "Sin membresía" como diferencia. Recomendado: sí.
9. "Socios con él" de `Planes.html` (BRECHAS lo ubica en el Sprint 3): no entra porque necesita `plans -> memberships` y `count_active_by_plan` visible en `PlanOut`; lo cierra US-082 (Sprint 4A). Recomendado: dejarlo en 4A y corregir `BRECHAS.md`.
10. Pendientes heredados del Sprint 2 con dueño "Sprint 3": digests de imágenes (L3) y actualización de vitest y stylelint (N-5). Recomendado: decidirlo en W0.
11. Cambio de contraseña, tablero y auditoría de socio (`GET /members/{id}/audit`, US-106) siguen fuera: la pestaña Historial de la ficha queda deshabilitada hasta el Sprint 4A.
12. El plan del sprint dice `sell(..., max_retroactive_days)` y `-m slow`; ambos se corrigen en `SPRINT-03.md` al aceptar D3 y D29.

Evidencia manual de cierre (validación del sprint): en la base de desarrollo, el `EXCLUDE` rechaza un solape; el trigger rechaza un `UPDATE`; `audit.audit_log` tiene filas `insert`, `update` y `reveal`; `crypto_ops` tiene `decrypt` con `purpose` `mask` y `reveal`; una venta y una anulación reales hechas por la pantalla (`verify-delivery`, pilar 2, contra el stack con las imágenes reconstruidas de api, web y db).
