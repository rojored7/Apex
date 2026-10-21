# US-139 · Como administrador quiero exportar los pagos filtrados a CSV para cuadrar la caja con contabilidad sin copiar a mano

- **Épica:** EP-16 · Recibos y exportaciones
- **Bounded context:** Payments (esquema `payments`)
- **Versión:** v0.2
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Pagos` (`/pagos`, botón Exportar)

## Historia

Como administrador
quiero un botón "Exportar" en la pantalla de pagos que descargue un CSV con los filtros activos
para entregar a contabilidad los ingresos del periodo

## Contexto de dominio

- **Aggregate / entidades:** Payment (lectura), Member (nombre por `members.service`).
- **Reglas que aplica:** Q15 (exportar pagos en v0.2 junto con socios; CSV, solo admin, auditado con el filtro usado), RN-01 (montos enteros COP), RN-02 (los anulados salen marcados, nunca se omiten si el filtro los incluye), RN-15.
- **Eventos que emite:** ninguno de dominio; auditoría `export`.
- **Eventos que consume:** ninguno.
- **Funciones puras:** `payments.csv_row(payment, member_name, labels, tz) -> list[str]`.

## Alcance

- **Backend:** `payments.service.export(filters, by)` con los mismos filtros de `GET /payments` (`from`, `to`, `method`, `registered_by`, `voided`, `member_id`, `membership_id`, `q`); CSV UTF-8 con BOM y separador `;`, columnas `fecha_pago;socio;plan;medio;referencia;monto_cop;anulado;motivo_anulacion;registrado_por`; `fecha_pago` en hora de Bogotá en formato `AAAA-MM-DD HH:MM`; `monto_cop` entero sin separador de miles. Sin campos cifrados (solo nombre y apellido del socio). Auditoría `export` con tabla `payments`, filtros y número de filas. Endpoint `GET /api/v1/payments/export`.
- **Front:** botón "Exportar" en `Pagos` visible solo para admin, con confirmación, usando los filtros activos.

## Criterios de aceptación

1. `GET /api/v1/payments/export` responde 200 `text/csv` para admin, 403 para coach y 401 sin sesión.
2. La suma de `monto_cop` de las filas no anuladas del CSV de un mes es igual a `total` de `GET /payments/summary?month=` del mismo mes.
3. `monto_cop` es un entero sin decimales ni separadores.
4. Los pagos anulados salen con `anulado = si` y su motivo cuando el filtro no los excluye.
5. El CSV no contiene documento, teléfono ni correo del socio.
6. Cada exportación deja auditoría `export` con usuario, filtros y número de filas.
7. Fechas `from` y `to` mal formadas devuelven 422 con `field`.

## Escenarios BDD

```gherkin
# language: es
Característica: Exportar pagos a CSV

  Escenario: Exportar los pagos de octubre
    Dado pagos de octubre por 1500000 COP no anulados y uno anulado de 120000 COP
    Y una sesión de administrador en "Pagos" con el rango de octubre
    Cuando pulsa "Exportar" y confirma
    Entonces el CSV suma 1500000 en las filas no anuladas
    Y la fila anulada tiene "anulado" en "si"
    Y queda una entrada de auditoría "export" con el rango usado

  Escenario: Rango de fechas inválido
    Dado una sesión de administrador
    Cuando pide "GET /api/v1/payments/export?from=2026-13-01"
    Entonces recibe 422 con "field" igual a "from"
```

## Endpoints

- `GET /api/v1/payments/export` — rol(es): admin — entrada: filtros de la lista — salida: CSV en streaming — códigos: 200, 401, 403, 422.

## Pantalla

- `Pagos` (`/pagos`): botón "Exportar" y modal de confirmación. `// DESIGN-GAP:` si el diseño de `Pagos` no muestra el botón.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** solo lectura.
- **Funciones puras a probar:** `csv_row` con pago anulado, sin referencia y en el cruce de medianoche UTC/Bogotá.
- **Pruebas:** service (cuadre con `summary`), router (roles, 422), auditoría, front.
- **Archivos principales:** `api/src/app/modules/payments/service.py`, `api/src/app/modules/payments/router.py`, `web/src/features/payments/components/ExportButton.tsx`.

## Supuestos

- Supuesto: el endpoint es `GET /payments/export` (propuesto en `BRECHAS.md`, aceptado por Q15) y las columnas del CSV no están definidas en los documentos.

## Dependencias

- US-098 · Listar y buscar pagos (filtros).
- US-102 · Consultar auditoría.

## INVEST

- **Independiente:** solo lectura de pagos.
- **Negociable:** columnas.
- **Valiosa:** cuadre contable sin trabajo manual.
- **Estimable:** igual al export de socios sin cifrado.
- **Pequeña:** un endpoint y un botón.
- **Testeable:** cuadre con el resumen mensual.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service, router y front en verde; cobertura de 80 % o más
- [ ] `docs/openapi.json` regenerado
- [ ] Auditoría verificada
- [ ] Revisión de PR aprobada
