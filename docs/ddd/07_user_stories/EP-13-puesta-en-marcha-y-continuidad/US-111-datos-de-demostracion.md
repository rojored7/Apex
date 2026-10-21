# US-111 · Como administrador quiero cargar datos de demostración con un comando para capacitar al equipo sin tocar socios reales

- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context:** ninguno propio; usa los services de Plans, Members, Memberships, Payments y Auth (`api/src/app/cli.py`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero ejecutar `cli seed --demo` sobre una base limpia
para tener planes, socios, membresías en todos los estados y pagos con los que capacitar a recepción y probar el sistema

## Contexto de dominio

- **Aggregate / entidades:** Plan, Member, Membership, Payment, User.
- **Reglas que aplica:** RN-01 (montos enteros COP), RN-03 (activación por cobertura), RN-04 (precio pactado), RN-05 y RN-06 (fechas y estados), RN-07 (congelar extiende), regla de datos 8 (las migraciones de datos son comandos de `cli.py`, idempotentes y auditados), Q1 (como máximo una vigente y una futura), Q28 (`today_bogota()`).
- **Eventos que emite:** los que emiten los services usados (`MemberCreated`, `PlanCreated`, `MembershipSold`, `PaymentRegistered`, `MembershipActivated`, `MembershipFrozen`, `MembershipCancelled`).
- **Eventos que consume:** ninguno directamente.
- **Funciones puras:** ninguna propia; reutiliza `memberships.compute_end_date`, `memberships.compute_status`.

## Alcance

- **Backend:** comando `seed --demo` en `cli.py` (typer) que crea, a través de `service.py` de cada módulo (nunca SQL directo): 3 planes (mensual por días, trimestral por días, tiquetera de 12 clases en 60 días), 30 socios ficticios con documentos ficticios y datos cifrados por el bus, membresías en los estados `pending_payment`, `active`, `expiring`, `expired`, `frozen` y `cancelled`, al menos una membresía futura (renovación) y pagos en los tres medios (`cash`, `nequi`, `breb`) con al menos un pago anulado. Usa como `created_by` `SYSTEM_USER_ID` (N-15). Las fechas se calculan relativas a `today_bogota()` para que los estados sean correctos el día que se ejecute.
- **Front:** No aplica.

## Criterios de aceptación

1. Sobre una base recién migrada (`alembic upgrade head`), `uv run python -m app.cli seed --demo` termina con código 0 y crea exactamente 3 planes, 30 socios, al menos una membresía en cada uno de los estados `pending_payment`, `active`, `expiring`, `expired`, `frozen` y `cancelled`, y pagos en `cash`, `nequi` y `breb`.
2. Todo dato se crea llamando a los `service.py` de cada módulo; una prueba revisa que `cli.py` no importa ningún `models` de módulos (prueba de arquitectura existente US-022 lo cubre).
3. Todos los montos (`price_cop`, `agreed_price_cop`, `amount_cop`) son enteros positivos en COP, sin decimales.
4. Los campos `document`, `phone`, `email`, `birth_date` y `emergency_contact` de los 30 socios quedan cifrados: `SELECT document FROM members.members` no devuelve ningún valor en claro.
5. Los estados de las membresías coinciden con `compute_status(membership, today_bogota(), expiring_days)` el día de la ejecución.
6. Cada inserción queda en `audit.audit_log` con `user_id` = `SYSTEM_USER_ID` (o el de `--as`), y la verificación de la cadena (US-104/US-105) sigue válida después del seed.
7. Existe al menos un pago anulado (`voided = true`, `void_reason` no vacío) y su membresía quedó en el estado que corresponde a la cobertura restante (RN-03).
8. Ejecutar el comando una segunda vez no duplica nada: detecta que el seed de demo ya existe (por los documentos ficticios vía índice ciego) y termina con código 0 y el mensaje "seed de demo ya aplicado".
9. Si la base tiene socios que no son de demo, el comando se niega y termina con código distinto de 0, salvo que se pase `--force-demo-on-non-empty`.
10. Ningún documento ficticio coincide con el formato de una cédula real asignable (se usan prefijos reservados `999...`).

## Escenarios BDD

```gherkin
# language: es
Característica: Datos de demostración

  Antecedentes:
    Dado una base de datos migrada con "alembic upgrade head"
    Y la KEK local inicializada con "cli init-keys"

  Escenario: Cargar el seed de demo en una base limpia
    Cuando el administrador ejecuta "cli seed --demo"
    Entonces el comando termina con código 0
    Y existen 3 planes y 30 socios
    Y hay al menos una membresía en cada estado "pending_payment", "active", "expiring", "expired", "frozen" y "cancelled"
    Y la cadena de auditoría verifica sin errores

  Escenario: Ejecutar el seed dos veces no duplica datos
    Dado que el seed de demo ya fue aplicado
    Cuando el administrador ejecuta "cli seed --demo" otra vez
    Entonces el comando termina con código 0
    Y sigue habiendo exactamente 30 socios y 3 planes

  Escenario: Negarse a sembrar demo sobre datos reales
    Dado que existe un socio real con documento "1020304"
    Cuando el administrador ejecuta "cli seed --demo" sin "--force-demo-on-non-empty"
    Entonces el comando termina con un código distinto de 0
    Y no se crea ningún plan ni socio

  Escenario: Los datos personales de demo quedan cifrados
    Dado que el seed de demo fue aplicado
    Cuando se consulta directamente la columna "document" de "members.members"
    Entonces ningún valor empieza distinto de "apx1."
```

## Endpoints

- Ninguno. Comando `uv run python -m app.cli seed --demo [--force-demo-on-non-empty] [--as <email>]`.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** respeta el trigger de inmutabilidad de pagos (US-096): la anulación de demo usa `payments.service.void`.
- **Funciones puras a probar:** función auxiliar `demo_dataset(today)` que devuelve la especificación de socios y membresías con fechas relativas; probar que con `FrozenClock` en 2026-10-21 produce un `expiring` con `end_date` 2026-10-25 y un `expired` con `end_date` 2026-10-10.
- **Pruebas:** service con base real (conteos, estados, cifrado, auditoría, idempotencia); prueba de arquitectura de `cli.py`.
- **Archivos principales:** `api/src/app/cli.py`, `api/src/app/seed/demo.py`, `api/tests/cli/test_seed_demo.py`.

## Supuestos

- Supuesto: el usuario técnico es `SYSTEM_USER_ID` (`system@apex.local`, rol `admin`, `is_active = false`, fila creada por la migración `0004_auth`); sirve como `created_by` de los datos sembrados (N-15). No existe un usuario `seed`.
- Supuesto: la detección de "seed ya aplicado" se hace por los documentos ficticios con prefijo `999`; la bandera `--force-demo-on-non-empty` no está en los documentos de origen.

## Dependencias

- US-084 · Vender membresía (crea membresías por `sell`).
- US-095 · Registrar pago (pagos de demo).
- US-078 · Crear plan (planes de demo).
- US-069 · Registrar socio (socios cifrados).
- US-041 · Cuentas de usuario y admin inicial (usuario de sistema).

## INVEST

- **Independiente:** solo consume services ya existentes; no los modifica.
- **Negociable:** el número de socios y la mezcla de estados se pueden ajustar sin cambiar el valor.
- **Valiosa:** permite capacitar y probar sin exponer datos reales (Ley 1581).
- **Estimable:** volumen y reglas conocidos.
- **Pequeña:** un comando y un conjunto de datos; cabe en un sprint.
- **Testeable:** conteos, estados y cifrado verificables con consultas.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error (no aplica: sin HTTP)
- [ ] Front: pruebas de componente y página; sin colores literales (no aplica)
- [ ] Migración aplicada con `alembic upgrade head` y reversible (no aplica)
- [ ] `docs/openapi.json` regenerado (no aplica)
- [ ] Auditoría verificada para las tablas tocadas
- [ ] Revisión de PR aprobada
