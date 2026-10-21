# US-163 · Como administrador quiero filtrar la lista de socios por su última asistencia para encontrar a quienes dejaron de venir y llamarlos antes de que no renueven

- **Épica:** EP-21 · Clases, horario y check-in
- **Bounded context:** Members (lista) con consulta a Classes
- **Versión:** v0.4
- **Actor:** administrador, coach
- **Tamaño:** 2
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Socios_Lista` (`/socios`, filtro de última asistencia)

## Historia

Como administrador o coach
quiero filtrar los socios que no vienen hace N días y ver su última asistencia en la lista
para contactarlos a tiempo

## Contexto de dominio

- **Aggregate / entidades:** `Member` (lista), `Attendance` (consulta).
- **Reglas que aplica:** regla de módulos 2 (Members no hace join con el esquema `classes`: pide a `classes.service.last_attendance_for(member_ids)`); paginación; RN-15.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** parámetro `last_attendance` en `GET /api/v1/members` y columna `last_attendance_at` en cada fila; `classes.service.last_attendance_for(member_ids)` y `classes.service.members_absent_since(date)`.
- **Front:** selector "Última asistencia" en `FilterBar` de `Socios_Lista` (7, 14, 30 días o nunca) y columna con la fecha.

## Criterios de aceptación

1. `GET /members?last_attendance=30d` devuelve solo socios cuya última asistencia es anterior a hace 30 días en Bogotá o que nunca asistieron; `never` devuelve solo los que nunca asistieron.
2. Valores admitidos: `7d`, `14d`, `30d`, `60d`, `never`; otro valor devuelve 422 con `field: "last_attendance"`.
3. Cada fila trae `last_attendance_at` en UTC o `null`.
4. El filtro se combina con `q`, `status` y `membership_status` y mantiene la paginación `limit`/`offset` y `total` correctos.
5. Members no importa `models` de `classes` (prueba de arquitectura en verde).
6. La lista responde en menos de 500 ms con 1.000 socios y el filtro activo.

## Escenarios BDD

```gherkin
# language: es
Característica: Filtro por última asistencia

  Escenario: Socios que no vienen hace un mes
    Dado que "Pedro Díaz" asistió por última vez hace 40 días y "Juan Rojas" ayer
    Cuando el administrador filtra la lista por "más de 30 días"
    Entonces ve a "Pedro Díaz" con su última asistencia
    Y no ve a "Juan Rojas"

  Escenario: Valor de filtro no válido
    Cuando pido GET /api/v1/members?last_attendance=mucho
    Entonces recibo 422 con field "last_attendance"
```

## Endpoints

- `GET /api/v1/members?last_attendance=` — rol(es): admin, coach — códigos: 200, 401, 403, 422

## Pantalla

- `Socios_Lista`, filtro y columna nuevos (`// DESIGN-GAP:` si la columna no está en el diseño).

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** cálculo de la fecha de corte con `today_bogota()`.
- **Pruebas:** service con base real (combinación de filtros, total), router, arquitectura, rendimiento con 1.000 socios.
- **Archivos principales:** `api/src/app/modules/members/service.py`, `api/src/app/modules/classes/service.py`, `web/src/features/members/components/MembersFilterBar.tsx`.

## Supuestos

- Supuesto: los valores del filtro son `7d`, `14d`, `30d`, `60d` y `never`; `ROUTES.md` solo nombra `last_attendance` sin semántica.

## Dependencias

- US-162 · Reportes de asistencia (consultas de asistencia)
- US-070 · Buscar y listar socios

## INVEST

- **Independiente:** agrega un filtro.
- **Negociable:** valores del selector.
- **Valiosa:** retención de socios.
- **Estimable:** pequeño.
- **Pequeña:** sí.
- **Testeable:** resultados exactos por fecha.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real y de router en verde; cobertura de 80 % o más en lo tocado
- [ ] Front: prueba del filtro; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
