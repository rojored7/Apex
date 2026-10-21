# US-158 · Como administrador quiero cancelar de una vez las sesiones futuras de una franja para aplicar un cambio de horario sin cancelar clase por clase

- **Épica:** EP-21 · Clases, horario y check-in
- **Bounded context:** Classes (esquema `classes`)
- **Versión:** v0.4
- **Actor:** administrador
- **Tamaño:** 2
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Horario` (`/clases/horario`, acción de la franja)

## Historia

Como administrador
quiero cancelar con un solo paso todas las sesiones futuras ya generadas de una franja, con confirmación y motivo
para que un cambio de horario se refleje de inmediato en las dos semanas ya generadas

## Contexto de dominio

- **Aggregate / entidades:** `ClassSlot`, `ClassSession`.
- **Reglas que aplica:** Q23 (editar o desactivar una franja afecta solo a las no generadas; las generadas se cancelan una por una o con "cancelar sesiones futuras de esta franja", con confirmación y motivo); RN-15 (solo admin).
- **Eventos que emite:** `SessionCancelled` por cada sesión cancelada.
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `POST /api/v1/class-slots/{id}/cancel-future-sessions` con `reason`; cancela en una transacción las sesiones `scheduled` de la franja con `starts_at` posterior a ahora.
- **Front:** acción "Cancelar sesiones futuras" en el `SidePanel` de la franja, con `ConfirmModal` que muestra cuántas sesiones se cancelarán y pide motivo.

## Criterios de aceptación

1. Solo admin; coach recibe 403.
2. Sin `reason` devuelve 422.
3. Se cancelan solo las sesiones `scheduled` de esa franja con `starts_at > ahora`; las pasadas, las ya canceladas y las sesiones extra no cambian.
4. La respuesta trae `cancelled_count`; si no hay sesiones futuras responde 200 con `cancelled_count: 0`.
5. Cada sesión cancelada guarda el motivo, emite `SessionCancelled` y queda auditada; si alguna falla, no se cancela ninguna.
6. La acción no desactiva la franja (eso es US-155) y el modal lo dice.

## Escenarios BDD

```gherkin
# language: es
Característica: Cancelar sesiones futuras de una franja

  Escenario: Cambio de horario de la clase de las 6:00
    Dado que inicié sesión como administrador
    Y la franja del lunes a las 06:00 tiene 2 sesiones futuras generadas
    Cuando cancelo sus sesiones futuras con el motivo "la clase pasa a las 06:30"
    Entonces las 2 sesiones quedan canceladas con ese motivo
    Y las sesiones pasadas de esa franja no cambian

  Escenario: Sin motivo
    Dado que inicié sesión como administrador
    Cuando intento cancelar las sesiones futuras de una franja sin motivo
    Entonces recibo 422 con field "reason"
```

## Endpoints

- `POST /api/v1/class-slots/{id}/cancel-future-sessions` — rol(es): admin — entrada: `{ reason }` — salida: `{ cancelled_count }` — códigos: 200, 401, 403, 404, 422

## Pantalla

- `Horario`, acción en el `SidePanel` de la franja con `ConfirmModal`.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** service con base real (filtros de estado y fecha, atomicidad), router (rol, 422).
- **Archivos principales:** `api/src/app/modules/classes/service.py`, `web/src/features/classes/components/SlotPanel.tsx`.

## Supuestos

- Supuesto: la ruta es `POST /class-slots/{id}/cancel-future-sessions`; ningún documento la nombra.
- Supuesto: si una sesión futura ya tiene asistencias (check-in anticipado dentro de la ventana), igual se cancela y las asistencias se conservan.

## Dependencias

- US-157 · Sesiones de la semana (cancelación unitaria y evento)

## INVEST

- **Independiente:** acción masiva sobre lo existente.
- **Negociable:** alcance temporal.
- **Valiosa:** evita cancelar clase por clase.
- **Estimable:** un endpoint y un modal.
- **Pequeña:** sí.
- **Testeable:** conteo y filtros verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real y de router en verde; cobertura de 80 % o más en lo tocado
- [ ] Front: prueba del modal; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
