# US-090 · Como administrador quiero anular una membresía con un motivo para corregir una venta equivocada dejando rastro de por qué

- **Épica:** EP-09 · Venta y ciclo de vida de membresías
- **Bounded context:** Memberships (esquema `memberships`)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** `Membresias` (`/membresias`, modal "Anular") y pestaña Membresías de `Socio_Ficha`

## Historia

Como administrador
quiero anular una membresía escribiendo el motivo
para que deje de contar como vigente, quede cerrada para siempre y se sepa quién la anuló y por qué

## Contexto de dominio

- **Aggregate / entidades:** `Membership` (`cancel_reason`, `cancelled_by`, `cancelled_at`).
- **Reglas que aplica:** RN-06 (`cancelled` es terminal), `02_domain_model.md` 2.3 (`cancel(reason)` exige motivo no vacío; solo admin), RN-15 y `BRECHAS.md` 5 (`POST /memberships/{id}/cancel` solo admin), RN-02 (los pagos de la membresía no se tocan; se anulan aparte si hace falta), RN-14 (no hay borrado físico).
- **Eventos que emite:** `MembershipCancelled`
- **Eventos que consume:** ninguno
- **Funciones puras:** `compute_status` (devuelve `cancelled` siempre)

## Alcance

- **Backend:** `memberships.service.cancel(id, reason, by)`, endpoint `POST /memberships/{id}/cancel`.
- **Front:** acción "Anular" visible solo para admin (`useCan`), `ConfirmModal` con motivo obligatorio y aviso "Los pagos no se anulan automáticamente; anúlalos desde Pagos si corresponde".

## Criterios de aceptación

1. `POST /api/v1/memberships/{id}/cancel` con `{ reason }` no vacío (después de recortar espacios, mínimo 5 caracteres, supuesto) deja `status = cancelled`, `cancel_reason`, `cancelled_by` y `cancelled_at` (UTC) y responde 200.
2. Motivo ausente, vacío o solo espacios devuelve 422 `field = "reason"`.
3. Anular una membresía ya `cancelled` devuelve 409 `code = "membership_already_cancelled"`.
4. Se puede anular desde `pending_payment`, `active`, `expiring`, `frozen` o `expired`.
5. Después de anular, ningún cambio de estado posterior la afecta: el job de vencimientos (US-094) la ignora y los handlers de pago (US-086, US-087) no la reactivan.
6. Los pagos asociados no cambian (sin `UPDATE` en `payments`); registrar un pago nuevo contra ella devuelve 422 (lo valida `payments.service.register`, US-095).
7. Al quedar cancelada, deja de contar para Q1: el socio puede recibir una venta nueva.
8. Rol `admin`; coach recibe 403 y el botón no se le muestra; sin token 401.
9. Auditoría `update` con `status`, `cancel_reason` antes y después; se emite `MembershipCancelled`.

## Escenarios BDD

```gherkin
# language: es
Característica: Anular una membresía

  Antecedentes:
    Dado que "Juan Rodríguez" tiene una membresía "Mensual" "active" del 2026-10-01 al 2026-10-31 con un pago de 120000

  Escenario: Anular con motivo
    Dado que estoy autenticado como administrador
    Cuando anulo la membresía con motivo "Se vendió al socio equivocado"
    Entonces la respuesta es 200
    Y la membresía queda "cancelled" con mi usuario y el motivo
    Y el pago de 120000 sigue sin anular
    Y se emite "MembershipCancelled"

  Escenario: Motivo vacío
    Dado que estoy autenticado como administrador
    Cuando anulo la membresía con motivo "   "
    Entonces la respuesta es 422
    Y el error señala el campo "reason"
    Y la membresía sigue "active"

  Escenario: Ya estaba anulada
    Dado que estoy autenticado como administrador
    Y la membresía ya está "cancelled"
    Cuando anulo la membresía con motivo "Otra vez"
    Entonces la respuesta es 409

  Escenario: Coach no puede anular
    Dado que estoy autenticado como coach
    Cuando anulo la membresía con motivo "Error de venta"
    Entonces la respuesta es 403
    Y la membresía sigue "active"

  Escenario: Tras anular se puede vender de nuevo
    Dado que estoy autenticado como administrador
    Y anulé la membresía con motivo "Se vendió al socio equivocado"
    Cuando vendo el plan "Mensual" a "Juan Rodríguez"
    Entonces la respuesta es 201
```

## Endpoints

- `POST /api/v1/memberships/{id}/cancel` — rol(es): admin — entrada: `{ reason: str }` — salida: `MembershipOut` — códigos: 200, 401, 403, 404, 409, 422.

## Pantalla

- `Membresias` y pestaña Membresías de `Socio_Ficha`: `ConfirmModal` con campo de motivo obligatorio; el `StatusTag` pasa a "Cancelada".

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** `CHECK (status <> 'cancelled' OR (cancel_reason IS NOT NULL AND cancelled_at IS NOT NULL))`.
- **Funciones puras a probar:** `compute_status` con `cancelled` en cualquier fecha.
- **Pruebas:** service con base real (terminal, pagos intactos, venta posterior permitida); router (solo admin); front (botón oculto para coach).
- **Archivos principales:** `api/src/app/modules/memberships/{service,router,schemas,exceptions}.py`, `web/src/features/memberships/components/CancelModal.tsx`.

## Supuestos

- Supuesto: el motivo exige al menos 5 caracteres después de recortar espacios (el dominio solo dice "no vacío").

## Dependencias

- US-084 · Vender membresía
- US-065 · SidePanel y ConfirmModal

## INVEST

- **Independiente:** una transición terminal sobre una membresía existente.
- **Negociable:** largo mínimo del motivo y textos.
- **Valiosa:** corrige ventas erróneas con rastro.
- **Estimable:** un endpoint con reglas cerradas.
- **Pequeña:** dos días.
- **Testeable:** estado terminal y matriz de rol.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada para `memberships`
- [ ] Revisión de PR aprobada
