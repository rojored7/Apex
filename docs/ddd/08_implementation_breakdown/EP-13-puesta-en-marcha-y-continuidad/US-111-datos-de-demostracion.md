# US-111 · Datos de demostración — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-13-puesta-en-marcha-y-continuidad/US-111-datos-de-demostracion.md`
- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context / módulo:** ninguno propio; comando de aplicación que usa los services de Plans, Members, Memberships, Payments y Auth (`api/src/app/cli.py`, `api/src/app/seed/demo.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 5

## Estado de preparación

**READY**

DECISIONES.md cierra el único supuesto que cambiaba comportamiento: no existe usuario `seed`; el seed usa `SYSTEM_USER_ID` o `--as <email>` (N-15). El resto (Q1, Q9, N-24, N-25, N-27) está decidido. La historia depende de que `memberships.service.sell` acepte fechas de inicio en el pasado cuando lo llama un CLI. Eso es un contrato a coordinar con EP-09, no una duda abierta.

## Resumen

Se agrega el comando `seed --demo [--force-demo-on-non-empty] [--as <email>]` a `cli.py` (typer). Se apoya en `app/seed/demo.py`, que tiene la función pura `demo_dataset(today) -> DemoSpec` y el orquestador `apply_demo(session, today, actor_id)`. El orquestador crea, solo a través de services: 3 planes, 30 socios ficticios con documentos `999…` cifrados por el bus, membresías en los seis estados (incluida una futura de renovación) y pagos en los tres medios, con un pago anulado. Al final llama a `memberships.service.recompute_statuses(today)` para que los estados guardados coincidan con `compute_status` del día. Es idempotente: si los documentos de demo ya existen, termina con código 0 y no hace nada. Si hay socios que no son de demo, se niega.

## Correcciones aplicadas por DECISIONES.md

- La historia crea y usa un usuario de sistema `seed` (rol admin, inactivo) → no se crea ningún usuario. `created_by` y `user_id` de auditoría son `SYSTEM_USER_ID` (`00000000-0000-0000-0000-000000000001`, creado por `0004_auth`), o el admin activo indicado con `--as <email>`: corregido por DECISIONES N-15.
- Criterio 6 ("`user_id` del usuario de sistema `seed`") → `user_id = SYSTEM_USER_ID` o el de `--as`: corregido por DECISIONES N-15.
- Fechas de inicio en el pasado para membresías vencidas y por vencer → el CLI no tiene el límite de `max_retroactive_days`, que es solo del API: corregido por DECISIONES N-24 (el texto nombra la importación; se aplica igual a todo CLI, porque el límite es "por el API").
- Membresía congelada → se crea con `memberships.service.freeze`, que inserta una fila en `membership_freezes` y respeta los límites de Settings: corregido por DECISIONES N-25 y Q9 (la ventana de demo queda dentro de `max_retroactive_days` y `max_freeze_days_per_membership`).
- Membresía futura de renovación → `sell(..., renew=True)`, que calcula `start_date` al día siguiente del fin de la vigente: aceptado por DECISIONES Q1 y Q2.
- Pagos con `paid_at` en el pasado → permitidos sin límite hacia atrás: aceptado por DECISIONES N-27.

## Validación contra el dominio

- Aggregates tocados por sus services: Plan (`plans.service.create`), Member (`members.service.create`), Membership (`memberships.service.sell`, `freeze`, `cancel`, `recompute_statuses`) y Payment (`payments.service.register`, `void`).
- RN-01: precios y montos enteros en COP (mensual 120.000, trimestral 320.000, tiquetera de 12 clases en 60 días 150.000).
- RN-03: la activación ocurre por el handler `on_payment_registered` de Memberships; el seed nunca cambia un estado a mano.
- RN-04: `agreed_price_cop` lo copia `sell`.
- RN-05, RN-06 con Q11 y Q28: las fechas se calculan relativas a `today_bogota()`; `demo_dataset` usa `expiring_days` de Settings para ubicar las "por vencer".
- RN-07 y N-25: la congelación extiende `end_date` y deja una fila en `membership_freezes`.
- Q1: una socia queda con vigente `expiring` y futura `pending_payment`, sin solape de fechas.
- Q4: la tiquetera solo vence por fecha en v0.1.
- Regla de datos 8: el comando es idempotente y auditado (cada inserción pasa por el hook de US-016).
- Eventos: los emiten los services (`MemberCreated`, `PlanCreated`, `MembershipSold`, `PaymentRegistered`, `MembershipActivated`, `PaymentVoided`, `MembershipFrozen`, `MembershipCancelled`, `MembershipExpiring`, `MembershipExpired`). El seed no consume eventos.
- Función pura propia: `demo_dataset(today: date, expiring_days: int) -> DemoSpec`. Confirmado: sin discrepancias.

## Validación contra la arquitectura

- `cli.py` y `app/seed/` son capa de aplicación, igual que el worker: no son módulos, no tienen `models.py` y solo llaman a `service.py`. Una prueba de arquitectura lo verifica: no se importa `app.modules.*.models` desde `cli.py` ni desde `app/seed`.
- No hay SQL directo. El "sin límite retroactivo" se pide a `memberships.service.sell` con un parámetro explícito (`max_retroactive_days: int | None`, donde `None` significa sin límite; el router de EP-09 pasa el valor de Settings). Es un contrato a coordinar con US-084.
- Cifrado: los datos personales los cifra `members.service.create` con los tipos `Encrypted` y `BlindIndexed` (US-028). El seed no llama al bus para cifrar. Para detectar el seed ya aplicado usa `members.service.id_by_document(document)`, que calcula el índice ciego dentro de Members.
- Actor: el comando abre la sesión con el contexto de actor de procesos sin petición HTTP que define US-016 (actor = `SYSTEM_USER_ID` o el de `--as`). `--as` se resuelve con `auth.service.active_admin_id_by_email(email)` (contrato pedido a EP-04).
- Lint banned-api: sin primitivas.
- Rol: no hay HTTP. Quien corre el CLI tiene acceso al servidor; `--as` exige un admin activo.
- Auditoría: todas las tablas tocadas tienen `__audited__ = True`; la cadena sigue válida (se verifica con `audit.service.verify` de US-104/US-105).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · `app/seed/demo.py`: función pura `demo_dataset(today: date, expiring_days: int) -> DemoSpec` (dataclasses congeladas) con 3 planes, 30 socios (`documento = "999" + 7 dígitos`, nombres ficticios, sexo variado, teléfonos `300 000 00xx`, correos `demo+NN@apex.local`) y la especificación de membresías y pagos: al menos 2 `active`, 2 `expiring` (con `end_date = today + 4`), 2 `expired` (con `end_date = today - 11`), 1 `frozen` (ventana de `today - 2` a `today + 5`), 2 `pending_payment`, 1 `cancelled`, 1 vigente con futura de renovación y 1 pago anulado; pagos en `cash`, `nequi` y `breb` — 3 h
- [ ] T2 · `app/seed/demo.py`: `async def apply_demo(session, today, actor_id, *, force_on_non_empty: bool) -> DemoResult` que comprueba idempotencia (`members.service.id_by_document` del primer y del último documento de demo), cuenta socios no de demo (`members.service.count(include_deleted=True)` menos los de demo hallados) y se niega si hay alguno sin `force_on_non_empty`; crea planes, socios, ventas (`sell(..., max_retroactive_days=None)`), pagos (`payments.service.register`), anulación (`payments.service.void`), congelación, cancelación, renovación (`sell(..., renew=True)`) y al final `memberships.service.recompute_statuses(today)`; todo en una sola transacción — 4 h
- [ ] T3 · `app/cli.py`: subcomando `seed --demo` (typer) que lee `today_bogota()`, resuelve el actor (`--as <email>` con `auth.service.active_admin_id_by_email`, o `SYSTEM_USER_ID`), abre la sesión con el contexto de actor de US-016, llama a `apply_demo` y sale con 0 ("seed de demo aplicado" o "seed de demo ya aplicado") o con 2 (base con socios reales, sin cambios); el `seed` sin `--demo` sigue siendo el del admin inicial de US-041 — 1,5 h
- [ ] T4 · Contratos pedidos a otros módulos, coordinados con sus dueños: `memberships.service.sell(..., max_retroactive_days: int | None)` (EP-09, US-084), `members.service.id_by_document(document) -> UUID | None` y `members.service.count(include_deleted)` (EP-07, US-069/US-070), `auth.service.active_admin_id_by_email(email)` (EP-04) — 1 h

### Schemas
- No aplica (usa los schemas de entrada de cada módulo: `MemberCreate`, `PlanCreate`, `PaymentIn`).

### Router
- No aplica.

### Tests unitarios puros
- [ ] T5 · `api/tests/cli/test_demo_dataset.py`: con `today = 2026-10-21` y `expiring_days = 7` hay un `expiring` con `end_date = 2026-10-25` y un `expired` con `end_date = 2026-10-10`; todos los documentos empiezan por `999` y son únicos; los montos son `int` positivos; hay al menos un caso por estado y por medio; la ventana de congelación cumple los límites por defecto de Q9 — 1,5 h

### Tests de service con PostgreSQL
- [ ] T6 · `api/tests/cli/test_seed_demo.py`: sobre base migrada, `apply_demo` crea exactamente 3 planes y 30 socios, al menos una membresía por estado, pagos en los tres medios y un pago anulado con `void_reason`; los estados guardados son iguales a `compute_status(m, today, expiring_days)` — 2 h
- [ ] T7 · `api/tests/cli/test_seed_demo.py`: `SELECT document, phone, email, birth_date, emergency_contact FROM members.members` solo devuelve valores que empiezan por `apx1.`; cada inserción tiene entrada en `audit.audit_log` con `user_id = SYSTEM_USER_ID` (o el de `--as`); `audit.service.verify()` da `ok` después del seed — 1,5 h
- [ ] T8 · `api/tests/cli/test_seed_demo.py`: segunda corrida no cambia conteos ni agrega auditoría; con un socio real (documento `1020304`) se niega con código 2 sin crear nada; con `--force-demo-on-non-empty` siembra — 1,5 h
- [ ] T9 · `api/tests/cli/test_seed_cli.py`: el comando por `typer.testing.CliRunner`: códigos de salida 0 y 2, mensaje "seed de demo ya aplicado", `--as` con un correo que no es admin activo termina con código distinto de 0 — 1 h

### Tests de router
- No aplica (sin HTTP).

### Tests de arquitectura
- [ ] T10 · `api/tests/architecture/test_no_cross_models.py` (US-022) se amplía para revisar también `app/cli.py`, `app/seed/` y `app/imports/`: ninguno importa `app.modules.*.models` ni ejecuta `text("INSERT|UPDATE|DELETE ...")` — 0,5 h

### Front
- No aplica.

### DevOps
- [ ] T11 · Documentar en el README (US-007) el paso "`docker compose run --rm api uv run python -m app.cli seed --demo`" para el ambiente de capacitación, y agregar el seed de demo al smoke de Compose de US-118 — 0,5 h

### Seguridad
- [ ] T12 · Revisión: los documentos ficticios no coinciden con cédulas asignables (prefijo `999`); la salida del comando no imprime datos de socios; el seed nunca corre automáticamente en producción (solo a mano) — 0,5 h

## Orden de ejecución

1. T4 (acordar contratos con EP-04, EP-07 y EP-09).
2. T5 (en rojo), luego T1.
3. T6, T7 y T8 (en rojo), luego T2.
4. T9 (en rojo), luego T3.
5. T10.
6. T11 y T12.

## Dependencias técnicas

- US-078 · Crear plan: `plans.service.create`.
- US-069 · Registrar socio: `members.service.create` con cifrado e índice ciego; `id_by_document` y `count`.
- US-084 · Vender membresía: `sell` con `max_retroactive_days=None` para el CLI y `renew=True`.
- US-086 · Activar por cobertura: el handler que activa al registrar el pago.
- US-089 · Congelar membresía (`membership_freezes`, N-25) y US-090 · Anular membresía.
- US-094 · Job de vencimientos: `memberships.service.recompute_statuses(today)`.
- US-095 · Registrar pago y US-097 · Anular pago.
- US-041 · Cuentas de usuario: `SYSTEM_USER_ID` en `0004_auth` y `auth.service.active_admin_id_by_email`.
- US-016 · Hook de auditoría: contexto de actor para procesos sin HTTP.
- US-054 / US-058 · Settings de membresías (`expiring_days`, límites de Q9).
- US-104 / US-105 · Verificación de la cadena de auditoría.
- US-023 · `cli init-keys`: las DEK deben existir antes del seed.

## Endpoints

- Ninguno.

## Riesgos

- Que `sell` aplique el límite retroactivo dentro del service sin parámetro: el seed no podría crear membresías vencidas — mitigación: T4 acuerda `max_retroactive_days: int | None` con EP-09 antes de empezar; se lista como contrato cruzado.
- Fechas relativas que caen en un borde (por ejemplo `expiring_days` cambiado en Settings): los estados no saldrían como se espera — mitigación: `demo_dataset` recibe `expiring_days` y T6 compara contra `compute_status`.
- Correr el seed de demo en la base real del gimnasio: mezcla datos ficticios con reales — mitigación: el comando se niega si hay socios que no son de demo, y el prefijo `999` permite encontrarlos y darlos de baja.
- Una transacción grande que falla a la mitad: no queda seed parcial porque todo va en una transacción.

## Estimación

- Backend: 10 h
- Front: 0 h
- Pruebas: 8 h
- DevOps / seguridad: 1 h
- **Total: 19 h**

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/cli/test_demo_dataset.py tests/cli/test_seed_demo.py tests/cli/test_seed_cli.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] Base limpia: `uv run alembic upgrade head && uv run python -m app.cli init-keys && uv run python -m app.cli seed --demo` termina con código 0
- [ ] `psql -c "SELECT count(*) FROM members.members"` devuelve 30 y `psql -c "SELECT status, count(*) FROM memberships.memberships GROUP BY status"` muestra los seis estados
- [ ] `psql -c "SELECT count(*) FROM members.members WHERE document NOT LIKE 'apx1.%'"` devuelve 0
- [ ] `uv run python -m app.cli verify-audit` termina con código 0 después del seed
- [ ] Segunda corrida de `seed --demo` imprime "seed de demo ya aplicado" y no cambia los conteos
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.seed --cov=app.cli --cov-fail-under=80`
