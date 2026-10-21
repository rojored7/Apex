# US-188 · Como socio quiero ver mis pagos y descargar sus recibos para tener constancia de que mi plata quedó registrada

- **Épica:** EP-25 · Portal del socio
- **Bounded context:** Portal (módulo `portal`), Conformist de Payments
- **Versión:** v1.0
- **Actor:** socio
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Portal_Pagos` (`/mi/pagos`)

## Historia

Como socio
quiero ver la lista de mis pagos y bajar el recibo en PDF de cada uno
para comprobar lo que pagué sin pedirlo en recepción

## Contexto de dominio

- **Aggregate / entidades:** `Payment` (lectura).
- **Reglas que aplica:** RN-01, RN-02 (los anulados se muestran marcados, nunca desaparecen), RN-15.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna nueva

## Alcance

- **Backend:** `GET /me/payments` delega en `payments.service.list(member_id=...)`; `GET /me/payments/{id}/receipt.pdf` delega en `payments.service.receipt_pdf(id, by)` (US-137) tras verificar que el pago pertenece al socio.
- **Front:** `Portal_Pagos` con lista paginada y botón "Recibo" por pago.

## Criterios de aceptación

1. `GET /api/v1/me/payments?limit&offset` con rol member devuelve solo pagos de membresías del socio de la sesión, ordenados por `paid_at` descendente, con `amount_cop` entero, `method`, `reference`, `paid_at` en UTC, plan y `voided` con `void_reason`; paginación `limit` 1 a 200 (por defecto 25), `offset` y `{ items, total, limit, offset }`.
2. `GET /api/v1/me/payments/{id}/receipt.pdf` devuelve el PDF de US-137 (anulado marcado como tal) con `Content-Type: application/pdf`.
3. Un `id` de pago de otro socio devuelve 404 (prueba anti IDOR).
4. Cada descarga de recibo deja auditoría con el usuario socio y el pago.
5. Los pagos anulados aparecen con la etiqueta "Anulado" y su motivo; nunca se ocultan.
6. Admin y coach reciben 403 en estas rutas; sin token, 401.
7. Montos como `$ 120.000` y fechas en hora de Bogotá en pantalla.

## Escenarios BDD

```gherkin
# language: es
Característica: Mis pagos y recibos

  Escenario: Descargar el recibo de un pago
    Dado que "Laura" tiene un pago Nequi de $ 120.000 del 3 de octubre
    Cuando abre "Mis pagos" y pulsa "Recibo" en ese pago
    Entonces descarga un PDF con $ 120.000, Nequi y la fecha del pago
    Y la auditoría registra la descarga

  Escenario: Recibo de un pago ajeno
    Cuando "Laura" pide el recibo de un pago de "Juan"
    Entonces el sistema responde que no existe
```

## Endpoints

- `GET /api/v1/me/payments?limit&offset` — rol(es): member — salida: página de pagos — códigos: 200, 401, 403, 422
- `GET /api/v1/me/payments/{id}/receipt.pdf` — rol(es): member — salida: PDF — códigos: 200, 401, 403, 404

## Pantalla

- `Portal_Pagos`: lista con monto, medio, fecha y estado; botón "Recibo"; estados de carga, vacío ("Aún no tienes pagos") y error.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** service; router con anti IDOR; auditoría de descarga; Vitest de la página.
- **Archivos principales:** `api/src/app/modules/portal/router.py`, `web/src/features/portal/pages/PortalPayments.tsx`.

## Supuestos

- Ninguno.

## Dependencias

- US-186 · Autorización propia en rutas me
- US-137 · Descargar recibo de pago

## INVEST

- **Independiente:** reutiliza listado y recibo.
- **Negociable:** columnas visibles.
- **Valiosa:** confianza del socio en el registro de su plata.
- **Estimable:** dos rutas delegadas y una pantalla.
- **Pequeña:** pocos días.
- **Testeable:** 404 cruzado y fila de auditoría.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, anti IDOR y envelope de error
- [ ] Front: pruebas de página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada
- [ ] Revisión de PR aprobada
