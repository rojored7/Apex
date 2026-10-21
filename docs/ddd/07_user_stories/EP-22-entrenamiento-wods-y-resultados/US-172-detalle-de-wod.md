# US-172 · Como coach quiero ver el detalle de un WOD con sus movimientos y todos sus resultados para revisar cómo le fue al box

- **Épica:** EP-22 · Entrenamiento: movimientos, WODs y resultados
- **Bounded context:** Training (módulos `wods` y `results`)
- **Versión:** v0.5
- **Actor:** administrador, coach
- **Tamaño:** 3
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `WOD_Detalle` (`/wods/:id`)

## Historia

Como coach
quiero abrir un WOD y ver su descripción, sus movimientos con cargas RX, su leaderboard y la lista completa de resultados
para revisar el desempeño del box y detectar marcas mal registradas

## Contexto de dominio

- **Aggregate / entidades:** `Wod`, `WodMovement`, `WodResult` (lectura).
- **Reglas que aplica:** RN-11, Q18 (por defecto solo vigentes), RN-15.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna nueva

## Alcance

- **Backend:** `GET /wods/{id}` (ya en US-166) y `GET /wods/{id}/results` con filtro de vigencia.
- **Front:** `WOD_Detalle` con encabezado (fecha, título, tipo de marca, time cap, benchmark), lista de movimientos (principal marcado), leaderboard (US-171) y pestaña "Todos los resultados" con quién registró y cuándo.

## Criterios de aceptación

1. `GET /api/v1/wods/{id}/results` devuelve los resultados del WOD con socio (nombre), nivel, marca, `status`, `recorded_by`, `created_at` en UTC, paginados con `limit` (1 a 200) y `offset`.
2. Por defecto solo `is_current = true`; `include_superseded=true` incluye los reemplazados marcados como tales.
3. La respuesta no incluye campos cifrados del socio.
4. Un `id` inexistente devuelve 404.
5. Solo admin y coach; `member` recibe 403.
6. Desde cada resultado se puede ir a "Corregir" (US-170) en la tablet o a la ficha del socio.

## Escenarios BDD

```gherkin
# language: es
Característica: Detalle de WOD

  Escenario: Ver movimientos y resultados
    Dado que el WOD "Fran" tiene 2 movimientos y 12 resultados vigentes
    Cuando abro el detalle de "Fran"
    Entonces veo "Thruster" marcado como movimiento principal con 43 kg hombre y 30 kg mujer
    Y veo los 12 resultados vigentes

  Escenario: WOD inexistente
    Cuando abro el detalle de un WOD que no existe
    Entonces veo el mensaje "No encontramos este WOD"
```

## Endpoints

- `GET /api/v1/wods/{id}` — rol(es): admin, coach — salida: WOD con movimientos — códigos: 200, 401, 403, 404
- `GET /api/v1/wods/{id}/results` — rol(es): admin, coach — entrada: `include_superseded?`, `limit`, `offset` — salida: página de resultados — códigos: 200, 401, 403, 404, 422

## Pantalla

- `WOD_Detalle` en `/wods/:id`: encabezado, movimientos, leaderboard y resultados. Estados de carga, vacío y error.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** service con base real (vigentes vs. reemplazados), router, front.
- **Archivos principales:** `api/src/app/modules/results/router.py`, `web/src/features/wods/pages/WodDetailPage.tsx`.

## Supuestos

- Supuesto: el parámetro `include_superseded` no está en el contrato; se agrega para revisar correcciones.

## Dependencias

- US-171 · Leaderboard del día

## INVEST

- **Independiente:** solo lectura.
- **Negociable:** qué columnas mostrar.
- **Valiosa:** revisión diaria del coach.
- **Estimable:** un endpoint y una página.
- **Pequeña:** sin escrituras.
- **Testeable:** filtros y contrato verificables.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error
- [ ] Front: pruebas de componente y página; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
