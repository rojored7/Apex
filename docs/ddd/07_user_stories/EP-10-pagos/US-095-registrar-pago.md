# US-095 · Como coach o administrador quiero registrar un pago contra una membresía para que cada peso recibido quede anotado una sola vez y active la membresía cuando cubra el precio

- **Épica:** EP-10 · Registro inmutable de pagos
- **Bounded context:** Payments (esquema `payments`)
- **Versión:** v0.1
- **Actor:** administrador, coach
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Pagos` (`/pagos`, `SidePanel` "Registrar pago")

## Historia

Como coach o administrador
quiero registrar un pago en efectivo, Nequi o Bre-B contra una membresía
para que el dinero recibido quede registrado una sola vez y la membresía se active sola cuando los pagos cubran el precio pactado

## Contexto de dominio

- **Aggregate / entidades:** `Payment` (raíz): `membership_id`, `amount_cop`, `method`, `reference`, `paid_at`, `registered_by`, `voided`, `void_reason`, `voided_by`, `voided_at`. Value object `Money`.
- **Reglas que aplica:** RN-01 (dinero entero en COP, mayor que 0), RN-02 (el pago nace inmutable; la protección en base la cierra US-096), RN-03 (la activación la decide Memberships por evento, no Payments), S8 (medios fijos `cash`, `nequi`, `breb`), Q5 (un pago que supera el saldo se permite, no genera saldo a favor; el front advierte y pide confirmación). Mapa de contextos sección 5: Payments nunca cambia el estado de una membresía.
- **Eventos que emite:** `PaymentRegistered(membership_id, amount_cop)`.
- **Eventos que consume:** ninguno.
- **Funciones puras:** ninguna nueva (la validación de `Money` vive en `schemas.py` y en `service.py`).

## Alcance

- **Backend:** modelo `Payment` y migración del esquema `payments`; `payments.service.register(membership_id, amount_cop, method, reference, paid_at, by)` que pide a `memberships.service.get(membership_id)` que la membresía exista y no esté `cancelled`, guarda el pago y emite `PaymentRegistered` en la misma transacción; router `POST /memberships/{id}/payments`. Es también la función que llama `sell` con `first_payment` (US-085).
- **Front:** botón "Registrar pago" en `Pagos` que abre `SidePanel` con búsqueda de socio, selección de su membresía no cancelada, monto, medio (etiquetas de `settings.payment_methods`), referencia y fecha de pago; advertencia de excedente (Q5) con confirmación; al guardar, refresca la lista y el resumen.

## Criterios de aceptación

1. `POST /api/v1/memberships/{id}/payments` con `amount_cop` entero mayor que 0, `method` en `cash`, `nequi` o `breb`, devuelve 201 con el pago creado, `registered_by` y `created_by` iguales al usuario autenticado.
2. `amount_cop` con decimales, cero, negativo o no numérico devuelve 422 con `field = "amount_cop"` (RN-01); el monto se guarda y se devuelve como entero, nunca como decimal ni texto.
3. `method` fuera de `cash`, `nequi`, `breb` devuelve 422 con `field = "method"` (S8).
4. `reference` es opcional, se recorta y acepta como máximo 64 caracteres; más largo devuelve 422 con `field = "reference"`.
5. `paid_at` es opcional; si no viene se usa la hora actual del servidor en UTC; si viene, debe traer zona horaria y se guarda en UTC (`TIMESTAMPTZ`); un `paid_at` en el futuro (más de 5 minutos por delante del reloj) devuelve 422 con `field = "paid_at"`.
6. Si la membresía no existe devuelve 404; si está `cancelled` devuelve 409 con `code = "membership_cancelled"` y no se crea ninguna fila.
7. En la misma transacción se emite `PaymentRegistered(membership_id, amount_cop)`; si un handler suscrito falla, el pago no queda guardado (prueba con handler que lanza excepción).
8. Payments no escribe ninguna columna de `memberships`; el cambio a `active` ocurre solo por el handler de US-086 (prueba de arquitectura: `payments` no importa `memberships.models`).
9. La tabla `payments.payments` tiene `__audited__ = True`: cada registro deja una fila de auditoría `insert` con usuario y fecha.
10. Rol: el endpoint declara `require_role("admin", "coach")`; un usuario `member` recibe 403 y una petición sin token 401.
11. El front muestra la advertencia "este pago supera el saldo pendiente en $ X" cuando `amount_cop` es mayor que el saldo y solo envía tras confirmar (Q5); el servidor acepta el pago igual.
12. El front muestra montos con `$ 120.000` y fechas en hora de Bogotá; el dato enviado es entero y UTC.

## Escenarios BDD

```gherkin
# language: es
Característica: Registrar un pago contra una membresía

  Antecedentes:
    Dado que existe la socia "Laura Gómez" con una membresía "Plan Mensual" en estado "pending_payment" y precio pactado 120000
    Y que estoy autenticado como "coach"

  Escenario: Registro un pago Nequi con referencia
    Cuando registro un pago de 120000 por "nequi" con referencia "NQ-778812" en esa membresía
    Entonces la respuesta es 201
    Y el pago queda con "registered_by" igual a mi usuario
    Y se emite "PaymentRegistered" con monto 120000
    Y la auditoría tiene una entrada "insert" en la tabla "payments" con mi usuario

  Escenario: Registro un pago sin fecha y se usa la hora actual
    Cuando registro un pago de 50000 por "cash" sin indicar "paid_at"
    Entonces la respuesta es 201
    Y "paid_at" es la hora actual en UTC

  Escenario: Monto con decimales es rechazado
    Cuando registro un pago de 120000.50 por "cash"
    Entonces la respuesta es 422 con "field" igual a "amount_cop"
    Y no se crea ningún pago

  Escenario: Medio de pago no permitido
    Cuando registro un pago de 120000 por "tarjeta"
    Entonces la respuesta es 422 con "field" igual a "method"

  Escenario: Fecha de pago en el futuro
    Cuando registro un pago de 120000 por "cash" con "paid_at" de mañana
    Entonces la respuesta es 422 con "field" igual a "paid_at"

  Escenario: Membresía cancelada no recibe pagos
    Dado que la membresía de "Laura Gómez" está "cancelled"
    Cuando registro un pago de 120000 por "cash"
    Entonces la respuesta es 409 con "code" igual a "membership_cancelled"

  Escenario: Pago que supera el saldo pendiente
    Dado que la membresía ya tiene pagos no anulados por 100000
    Cuando en el formulario escribo 50000
    Entonces veo la advertencia "este pago supera el saldo pendiente en $ 30.000"
    Y el pago solo se envía cuando confirmo

  Escenario: Un socio no puede registrar pagos
    Dado que estoy autenticado como "member"
    Cuando registro un pago de 120000 por "cash" en esa membresía
    Entonces la respuesta es 403
```

## Endpoints

- `POST /api/v1/memberships/{id}/payments` — rol(es): admin, coach — entrada: `{ amount_cop: int > 0, method: "cash" | "nequi" | "breb", reference?: str (máx. 64), paid_at?: datetime ISO 8601 con zona }` — salida: `PaymentOut { id, membership_id, amount_cop, method, reference, paid_at, registered_by, voided, created_at }` — códigos: 201, 401, 403, 404, 409, 422.

## Pantalla

- `Pagos` en `/pagos`: botón "Registrar pago" y `SidePanel` con `Field` de socio (búsqueda contra `GET /members?q=`), selector de membresía del socio, monto, medio, referencia y fecha. Estados de carga en el envío, error con el envelope en el `Field` indicado por `field`.
- `// DESIGN-GAP:` la advertencia de excedente (Q5) no está dibujada; se usa `ConfirmModal`.

## Notas técnicas

- **Migración:** sí. Esquema `payments`, tabla `payments` con `id` UUID, `membership_id` UUID (sin FK cruzada entre esquemas: la integridad la valida el service), `amount_cop BIGINT CHECK (amount_cop > 0)`, `method TEXT CHECK (method IN ('cash','nequi','breb'))`, `reference TEXT NULL`, `paid_at TIMESTAMPTZ NOT NULL`, `registered_by UUID NOT NULL`, `voided BOOLEAN NOT NULL DEFAULT false`, `void_reason TEXT NULL`, `voided_by UUID NULL`, `voided_at TIMESTAMPTZ NULL`, columnas comunes; índices por `membership_id` y `paid_at`.
- **Trigger / restricciones:** los `CHECK` anteriores; el trigger de inmutabilidad lo agrega US-096.
- **Funciones puras a probar:** validación de monto (0, -1, 1, 120000, 120000.5) en el schema.
- **Pruebas:** service con base real (registro, membresía cancelada, rollback si falla el handler); router (rol, 422 por campo, envelope); arquitectura (sin imports de `memberships.models`); front (Vitest del `SidePanel`, advertencia Q5); E2E: registrar pago Nequi con referencia y verlo en el resumen del mes (junto con US-100).
- **Archivos principales:** `api/src/app/modules/payments/{models,schemas,service,router,exceptions}.py`, `api/migrations/versions/*_payments.py`, `web/src/features/payments/{api.ts,schemas.ts,components/RegisterPaymentPanel.tsx}`.

## Supuestos

- Supuesto: `paid_at` no puede estar en el futuro (tolerancia de 5 minutos) y no tiene límite hacia atrás, para permitir registrar tarde un pago recibido días antes.
- Supuesto: `reference` es opcional para los tres medios y tiene un máximo de 64 caracteres; no es obligatoria para Nequi ni Bre-B.
- Supuesto: se pueden registrar pagos en membresías `pending_payment`, `active`, `expiring`, `frozen` y `expired` (cobro de deuda); solo `cancelled` se rechaza.
- Supuesto: el saldo pendiente para la advertencia Q5 lo calcula el front con `agreed_price_cop` y `paid_cop` que expone `GET /memberships/{id}` (US-091 debe incluir `paid_cop`).

## Dependencias

- US-084 · Vender membresía (el pago siempre es contra una membresía).
- US-016 · Hook de auditoría (tabla auditada).
- US-014 · Bus de eventos transaccional (`PaymentRegistered`).
- US-056 · Etiquetas de medios de pago (etiquetas del selector).
- US-065 · Panel lateral y modal de confirmación.
- US-091 · GET /memberships/{id} debe exponer paid_cop para la advertencia de excedente de Q5 (agregado en consolidación)

## INVEST

- **Independiente:** solo necesita una membresía existente; la activación (US-086) se construye aparte y reacciona al evento.
- **Negociable:** el diseño del panel y la tolerancia de `paid_at` se pueden ajustar sin cambiar el valor.
- **Valiosa:** es la entrada de toda la caja del gimnasio.
- **Estimable:** un modelo, una migración, un endpoint y un panel.
- **Pequeña:** cabe en un sprint; inmutabilidad y anulación van en US-096 y US-097.
- **Testeable:** cada criterio tiene prueba de router, service o componente.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `payments.payments`
- [ ] Revisión de PR aprobada
