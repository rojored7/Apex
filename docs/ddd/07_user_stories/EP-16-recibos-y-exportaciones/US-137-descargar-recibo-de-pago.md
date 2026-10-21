# US-137 · Como coach quiero descargar el recibo en PDF de un pago para entregarle al socio un comprobante de lo que pagó

- **Épica:** EP-16 · Recibos y exportaciones
- **Bounded context:** Payments (esquema `payments`)
- **Versión:** v0.2
- **Actor:** administrador, coach
- **Tamaño:** 5
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Pagos` (`/pagos`, modal de detalle) y `Socio_Ficha` (`/socios/:id`, pestaña Pagos)

## Historia

Como coach o administrador
quiero un botón "Recibo" que descargue el PDF de un pago
para entregar al socio un comprobante interno con monto, medio, referencia y fecha

## Contexto de dominio

- **Aggregate / entidades:** Payment (lectura), Membership y Member (datos de encabezado vía services).
- **Reglas que aplica:** RN-01 (monto entero mostrado como `$ 120.000`), RN-02 (el recibo de un pago anulado sale marcado como anulado con su motivo; nada se modifica), RN-15 (rol), S9 (`reportlab` BSD; `fpdf2` es LGPL y está prohibida), P4 (recibo en v0.2).
- **Eventos que emite:** ninguno de dominio; la descarga se audita como acción `export`.
- **Eventos que consume:** ninguno.
- **Funciones puras:** `payments.receipt_context(payment, membership, member, gym, tz) -> ReceiptContext` (formato de monto, fecha en Bogotá, estado anulado).

## Alcance

- **Backend:** `payments.service.receipt_pdf(id, by)` con `reportlab`, logo `apex-logo-light-bg.png` y datos de la sección `gym` de Settings; obtiene nombre del socio y plan por `members.service` y `memberships.service` (nunca `models` ajenos); no incluye documento ni teléfono del socio; texto fijo "Comprobante interno de pago. No es factura electrónica". Endpoint `GET /api/v1/payments/{id}/receipt.pdf`. Cada descarga escribe auditoría con acción `export`, tabla `payments`, `record_id` y usuario.
- **Front:** botón "Recibo" en el modal de detalle de `Pagos` y en cada fila de la pestaña Pagos de `Socio_Ficha`; descarga con nombre `recibo-<id-corto>.pdf`; estado de carga y error.

## Criterios de aceptación

1. `GET /api/v1/payments/{id}/receipt.pdf` responde 200 con `Content-Type: application/pdf` para admin y coach.
2. El PDF muestra el monto como `$ 120.000` (entero COP, sin decimales), el medio con su etiqueta de Settings, la referencia si existe, la fecha `paid_at` convertida a hora de Bogotá (`20 oct 2026, 6:30 p. m.`), el nombre y apellido del socio, el plan y el periodo de la membresía.
3. El PDF no contiene documento, teléfono, correo ni ningún campo cifrado del socio.
4. El recibo de un pago anulado muestra "ANULADO", el motivo y la fecha de anulación.
5. Cada descarga deja una fila de auditoría `export` con usuario, `payments` y el id del pago.
6. Un socio (rol `member`) recibe 403 en esta ruta (su recibo llega por `/me`, EP-25); sin sesión, 401; un id inexistente, 404.
7. El chequeo de licencias de CI acepta `reportlab` y falla si se agrega `fpdf2`.
8. Generar un recibo tarda menos de 1 s.

## Escenarios BDD

```gherkin
# language: es
Característica: Recibo de pago en PDF

  Escenario: El coach descarga el recibo de un pago
    Dado un pago de 120000 COP en "nequi" con referencia "NQ-123" del socio "Ana Pérez"
    Y una sesión de coach
    Cuando el coach pulsa "Recibo" en el detalle del pago
    Entonces descarga un PDF con "$ 120.000", "Nequi" y "NQ-123"
    Y el PDF no contiene el documento de "Ana Pérez"
    Y queda una entrada de auditoría "export" del pago

  Escenario: Recibo de un pago anulado
    Dado un pago anulado con motivo "monto equivocado"
    Cuando el administrador descarga su recibo
    Entonces el PDF muestra "ANULADO" y "monto equivocado"
```

## Endpoints

- `GET /api/v1/payments/{id}/receipt.pdf` — rol(es): admin, coach — entrada: id — salida: PDF — códigos: 200, 401, 403, 404.

## Pantalla

- `Pagos` (`/pagos`): botón "Recibo" del modal de detalle.
- `Socio_Ficha` (`/socios/:id`): botón por fila en la pestaña Pagos.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** solo lectura del pago (trigger de inmutabilidad intacto).
- **Funciones puras a probar:** `receipt_context` con pago normal, anulado y sin referencia; conversión UTC → Bogotá al cruzar medianoche.
- **Pruebas:** service (texto extraído del PDF), router (roles, 404), auditoría, licencias; front (botón y descarga).
- **Archivos principales:** `api/src/app/modules/payments/service.py`, `api/src/app/modules/payments/receipt.py`, `web/src/features/payments/components/ReceiptButton.tsx`.

## Supuestos

- Supuesto: la descarga del recibo se audita con la acción `export` (el enum de `AuditEntry.action` no tiene `download`).
- Supuesto: el recibo no lleva numeración consecutiva propia; usa el id del pago.

## Dependencias

- US-099 · Ver detalle de pago (modal donde vive el botón).
- US-016 · Hook de auditoría.

## INVEST

- **Independiente:** solo lectura de pagos.
- **Negociable:** diseño del PDF.
- **Valiosa:** el socio recibe comprobante; menos discusiones en caja.
- **Estimable:** una plantilla PDF.
- **Pequeña:** un endpoint y un botón.
- **Testeable:** texto del PDF verificable.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service, router y front en verde; cobertura de 80 % o más
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada
- [ ] Revisión de PR aprobada
