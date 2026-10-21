# EP-16 · Recibos y exportaciones

- **Versión del plan:** v0.2 (supuesto S9; pregunta P4; `BRECHAS.md` sección 2, "Recibo en PDF" y "Exportar listas").
- **Bounded context:** Payments (recibo) y Members (exportación).
- **Estimación relativa:** M.

## Objetivo de negocio

Darle al socio un comprobante del pago que hizo y al dueño una forma de sacar su información para contabilidad o para un respaldo propio, sin que esa salida masiva de datos personales quede sin rastro.

## Actores

- Administrador y coach: descargan el recibo de un pago.
- Administrador: único que exporta listas.
- Socio: descarga sus recibos desde el portal (lo habilita EP-25 sobre esta capacidad).

## Capacidades incluidas

### Backend
- `payments.service.receipt_pdf(id, by)` con `reportlab` (BSD; `fpdf2` es LGPL y está prohibida), con el logo `apex-logo-light-bg.png`; cada descarga se audita.
- Endpoint `GET /payments/{id}/receipt.pdf`.
- `members.service.export(filters, by)` en CSV, solo admin, auditado con acción `export`, porque descifra datos personales en masa.
- Endpoint `GET /members/export`.
- Un recibo de un pago anulado sale marcado como anulado con su motivo.

### Front
- Botón "Recibo" en el detalle de pago y en la pestaña Pagos de la ficha.
- Botón "Exportar" en la lista de socios, visible solo para admin, con confirmación que advierte que la descarga queda auditada.

## Fuera de alcance

- Factura electrónica DIAN (fuera de alcance del producto).
- Exportación de pagos en CSV (está en `BRECHAS.md` pero no en el contrato de `05_service_design.md`; ver preguntas abiertas).
- Envío del recibo por correo.

## Criterios de éxito medibles

- El recibo muestra monto como `$ 120.000`, medio, referencia, fecha en hora de Bogotá, socio y membresía.
- Cada descarga de recibo y cada exportación dejan una fila de auditoría con usuario, filtros y número de filas.
- Un coach recibe 403 en `GET /members/export`.
- Exportar 1.000 socios termina en menos de 10 segundos.
- El chequeo de licencias de CI acepta `reportlab` y rechaza `fpdf2`.

## Dependencias

- EP-10 Registro inmutable de pagos.
- EP-07 Padrón de socios.
- EP-11 Auditoría y trazabilidad.
- EP-02 Bus de criptografía (descifrado masivo por lote en la exportación).

## Riesgos

- Una exportación CSV con datos en claro sale del sistema y queda fuera de cualquier control; la auditoría solo prueba que salió.
- El recibo puede confundirse con una factura; el texto debe dejar claro que es un comprobante interno.

## Pantallas del diseño que habilita

- Recibo en `Pagos` y en la pestaña Pagos de `Socio_Ficha`; botón Exportar de `Socios_Lista`. Base del recibo de `Portal_Pagos` (EP-25).
