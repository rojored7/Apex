# US-129 · Como administrador quiero consultar el historial de avisos con filtros para saber a quién se le avisó, cuándo, por dónde y con qué resultado

- **Épica:** EP-14 · Avisos de vencimiento
- **Bounded context:** Notifications (esquema `notifications`)
- **Versión:** v0.2
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Notif_Historial` (`/avisos/historial`)

## Historia

Como administrador o coach
quiero filtrar los avisos por socio, rango de fechas, regla, canal y estado
para responder con evidencia si a un socio se le avisó antes de vencer

## Contexto de dominio

- **Aggregate / entidades:** `Notification`.
- **Reglas que aplica:** paginación (regla de datos 6); RN-13 (sin contacto en la respuesta).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `GET /notifications` y `GET /notifications/{id}`.
- **Front:** `Notif_Historial` con `FilterBar`, `DataTable`, `Pagination` y detalle con el texto enviado.

## Criterios de aceptación

1. `GET /api/v1/notifications` filtra por `member_id`, `from` y `to` (sobre `target_date`), `rule_id`, `channel` y `status`; pagina con `limit` 1 a 200 (25 por defecto) y `offset`; responde `{ items, total, limit, offset }`; orden por `target_date` descendente.
2. `from` posterior a `to` o `limit` fuera de rango responde 422.
3. Cada ítem trae nombre del socio, regla, canal, `target_date`, estado, `sent_at` (UTC), quién lo envió u omitió, `skip_reason`, `attempts`, `last_error`; nunca teléfono ni correo.
4. `GET /api/v1/notifications/{id}` agrega `rendered_body`.
5. Admin y coach acceden; un socio recibe 403 (su vista es `/me/notifications`, US-193).
6. Con 10.000 avisos y filtro por socio responde en menos de 500 ms (índices `member_id`, `target_date`).

## Escenarios BDD

```gherkin
# language: es
Característica: Historial de envíos

  Escenario: Filtrar los avisos de un socio
    Dado que inicié sesión como administrador
    Y Juan Ríos tiene 3 avisos y Laura Gómez tiene 2
    Cuando filtro el historial por Juan Ríos
    Entonces veo 3 avisos ordenados del más reciente al más antiguo
    Y ninguno muestra el teléfono de Juan

  Escenario: Rango de fechas inválido
    Dado que inicié sesión como coach
    Cuando filtro desde 2026-11-01 hasta 2026-10-01
    Entonces la respuesta es 422
```

## Endpoints

- `GET /api/v1/notifications` — rol(es): admin, coach — entrada: `member_id`, `from`, `to`, `rule_id`, `channel`, `status`, `limit`, `offset` — códigos: 200, 401, 403, 422
- `GET /api/v1/notifications/{id}` — rol(es): admin, coach — códigos: 200, 401, 403, 404

## Pantalla

- `Notif_Historial` en `/avisos/historial`: filtros en `FilterBar` sincronizados con la URL, tabla con `StatusTag`, `SidePanel` de detalle con el texto enviado, estados de carga, vacío y error.

## Notas técnicas

- **Migración:** sí, índices (`member_id`, `target_date`) y (`status`) en `notifications.notifications` si no se crearon en US-124.
- **Pruebas:** service con base real (filtros combinados, orden); router (422, 403); Vitest de la página.
- **Archivos principales:** `api/src/app/modules/notifications/router.py`, `web/src/features/notifications/pages/HistoryPage.tsx`.

## Supuestos

- Ninguno.

## Dependencias

- US-124 · Generar avisos del día
- US-063 · Tabla, paginación, filtros y chips

## INVEST

- **Independiente:** solo lectura.
- **Negociable:** columnas visibles.
- **Valiosa:** evidencia ante reclamos.
- **Estimable:** lista estándar.
- **Pequeña:** 3.
- **Testeable:** filtros verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service y router en verde; cobertura de 80 % o más en lo tocado
- [ ] Front: pruebas de página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
