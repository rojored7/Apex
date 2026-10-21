# US-132 · Como administrador quiero ver en Inicio cuántos avisos quedan por gestionar hoy para no olvidar llamar a nadie

- **Épica:** EP-14 · Avisos de vencimiento
- **Bounded context:** Dashboard (lectura) sobre Notifications
- **Versión:** v0.2
- **Actor:** administrador, coach
- **Tamaño:** 1
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Inicio` (`/`, tarjeta Por avisar)

## Historia

Como administrador o coach
quiero que la tarjeta "Por avisar" de Inicio muestre el número de avisos pendientes o fallidos de hoy
para saber de un vistazo si hay trabajo de avisos sin abrir otra pantalla

## Contexto de dominio

- **Aggregate / entidades:** `Notification` (conteo).
- **Reglas que aplica:** contrato estable del tablero (EP-12: se llena un campo `null`, no se cambia la forma).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `notifications.service.today_count(today)`; `dashboard.service.summary` llena `notifications_today`.
- **Front:** `KpiCard` "Por avisar" con enlace a `/avisos/hoy`.

## Criterios de aceptación

1. `GET /api/v1/dashboard` devuelve `notifications_today` como entero igual al `total` de `GET /notifications/today` para el mismo día; deja de ser `null`.
2. Ningún otro campo del contrato de `/dashboard` cambia de nombre ni de tipo.
3. La tarjeta enlaza a `/avisos/hoy`; con 0 muestra "0" y el texto "Nadie por avisar".
4. Admin y coach ven la tarjeta; el rol de `/dashboard` no cambia.

## Escenarios BDD

```gherkin
# language: es
Característica: KPI por avisar

  Escenario: Ver el conteo del día
    Dado que hoy hay 4 avisos pendientes y 1 fallido
    Cuando abro Inicio como administrador
    Entonces la tarjeta "Por avisar" muestra 5

  Escenario: Contrato estable
    Cuando pido el tablero
    Entonces los campos de v0.1 conservan su nombre y tipo
```

## Endpoints

- `GET /api/v1/dashboard` — rol(es): admin, coach — cambia `notifications_today` de `null` a entero — códigos: 200, 401, 403

## Pantalla

- `Inicio`, `KpiCard` Por avisar (ya existe vacía desde US-109).

## Notas técnicas

- **Migración:** no.
- **Pruebas:** service (conteo cuadra con la lista); prueba de contrato de `/dashboard` (snapshot del esquema OpenAPI); Vitest de la tarjeta.
- **Archivos principales:** `api/src/app/modules/dashboard/service.py`, `api/src/app/modules/notifications/service.py`.

## Supuestos

- Supuesto: el nombre del campo es `notifications_today`, como lo fija US-108 (contradicciones del desglose: clave del tablero).

## Dependencias

- US-124 · Generar avisos del día
- US-109 · KPIs de membresías e ingresos (tarjeta existente)

## INVEST

- **Independiente:** un campo.
- **Negociable:** texto de la tarjeta.
- **Valiosa:** frase guía del producto.
- **Estimable:** trivial.
- **Pequeña:** 1.
- **Testeable:** conteo igual a la lista.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service y contrato en verde
- [ ] Front: prueba de la tarjeta; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
