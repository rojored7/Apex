# US-174 · Como coach quiero ver el WOD de hoy en el tablero de inicio para saber qué se entrena sin abrir otra pantalla

- **Épica:** EP-22 · Entrenamiento: movimientos, WODs y resultados
- **Bounded context:** Dashboard (módulo `dashboard`, sin esquema), Conformist de Training
- **Versión:** v0.5
- **Actor:** administrador, coach
- **Tamaño:** 1
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Inicio` (`/`, tarjeta WOD de hoy)

## Historia

Como coach
quiero ver en Inicio el título y el tipo de marca del WOD de hoy con un enlace a su detalle
para saber qué se entrena hoy apenas entro al sistema

## Contexto de dominio

- **Aggregate / entidades:** `Wod` (lectura).
- **Reglas que aplica:** contrato estable del tablero (EP-12: los campos futuros llegan `null` y cada épica solo los llena); Q28 (`today_bogota()`).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `dashboard.service.summary` llena el campo `wod_today` con `wods.service.today()` (`{ id, title, score_type, is_benchmark }` o `null`).
- **Front:** `KpiCard` "WOD de hoy" en `Inicio`, con enlace a `/wods/:id`; estado "Sin WOD publicado" con enlace a `/wods/nuevo`.

## Criterios de aceptación

1. `GET /api/v1/dashboard` devuelve `wod_today` con `id`, `title`, `score_type` e `is_benchmark` del WOD con fecha `today_bogota()`, o `null` si no hay.
2. Ningún otro campo del contrato del tablero cambia de nombre ni de tipo (prueba de contrato contra el `openapi.json` anterior).
3. A las 20:00 de Bogotá (01:00 UTC del día siguiente) el WOD mostrado sigue siendo el de la fecha de Bogotá.
4. Rol: admin y coach, como el resto del tablero; `member` recibe 403.
5. El módulo `dashboard` no importa `models` de `wods` (prueba de arquitectura).

## Escenarios BDD

```gherkin
# language: es
Característica: WOD de hoy en Inicio

  Escenario: Hay WOD publicado hoy
    Dado que el WOD de hoy es "Fran"
    Cuando abro Inicio
    Entonces la tarjeta "WOD de hoy" muestra "Fran" con enlace a su detalle

  Escenario: No hay WOD publicado
    Dado que hoy no hay WOD publicado
    Cuando abro Inicio
    Entonces la tarjeta "WOD de hoy" muestra "Sin WOD publicado"
```

## Endpoints

- `GET /api/v1/dashboard` — rol(es): admin, coach — salida: contrato del tablero con `wod_today` lleno — códigos: 200, 401, 403

## Pantalla

- `Inicio` en `/`: tarjeta WOD de hoy (`KpiCard`), estado vacío.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** service con `FrozenClock` a las 01:00 UTC, prueba de contrato, front.
- **Archivos principales:** `api/src/app/modules/dashboard/service.py`, `web/src/features/dashboard/pages/HomePage.tsx`.

## Supuestos

- Ninguno.

## Dependencias

- US-168 · WOD del día
- US-108 · Contrato del tablero

## INVEST

- **Independiente:** solo llena un campo existente.
- **Negociable:** contenido de la tarjeta.
- **Valiosa:** contexto del día en un vistazo.
- **Estimable:** trivial.
- **Pequeña:** 1 punto.
- **Testeable:** valor y `null` verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol
- [ ] Front: prueba de la tarjeta; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
