# US-151 · Como administrador quiero ver cuántos socios no tienen autorización registrada para ir recogiéndolas sin bloquear la operación

- **Épica:** EP-19 · Adjuntos y autorización de tratamiento de datos
- **Bounded context:** Members (+ Dashboard, lectura)
- **Versión:** v0.3
- **Actor:** administrador, coach
- **Tamaño:** 2
- **Prioridad:** P2 mejora
- **Refinamiento:** Criterios completos; BDD solo de flujo principal
- **Pantalla:** `Inicio` (`/`) y `Socio_Ficha` (`/socios/:id`)

## Historia

Como administrador
quiero ver en el tablero cuántos socios no tienen autorización de datos y una marca en su ficha
para pedírsela cuando vengan, sin que nada se bloquee por su ausencia

## Contexto de dominio

- **Aggregate / entidades:** `Member` (`data_consent_at`).
- **Reglas que aplica:** Q16 (`data_consent_at` puede ser nulo en socios anteriores a v0.3; el tablero muestra "socios sin autorización registrada" y la ficha lo marca; no se bloquea nada); RN-14 (los dados de baja no cuentan).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `members.service.count_without_consent()`; campo `members_without_consent` en `GET /api/v1/dashboard`; filtro `consent=missing` en `GET /api/v1/members`; `GET /api/v1/members/{id}` ya devuelve `data_consent_at`.
- **Front:** tarjeta `KpiCard` "Sin autorización" en Inicio que enlaza a `/socios?consent=missing`; `StatusTag` "Sin autorización registrada" en el encabezado de la ficha.

## Criterios de aceptación

1. `members_without_consent` cuenta socios con `data_consent_at` nulo y `deleted_at` nulo.
2. `GET /members?consent=missing` devuelve solo esos socios, paginado con `limit`/`offset` (máximo 200).
3. Ninguna operación (vender, registrar pago, check-in, editar) falla por `data_consent_at` nulo.
4. La ficha de un socio con `data_consent_at` nulo muestra la marca con texto, no solo color.
5. El campo nuevo del tablero no cambia los demás campos del contrato (solo se agrega).
6. `GET /dashboard` sigue exigiendo admin o coach.

## Escenarios BDD

```gherkin
# language: es
Característica: Socios sin autorización registrada

  Escenario: El tablero muestra a los socios pendientes
    Dado que hay 12 socios activos sin autorización registrada y 1 dado de baja sin autorización
    Cuando el administrador abre Inicio
    Entonces la tarjeta "Sin autorización" muestra 12
    Y al pulsarla ve la lista de esos 12 socios

  Escenario: Un socio sin autorización compra una membresía
    Dado un socio sin autorización registrada
    Cuando el coach le vende una membresía
    Entonces la venta se registra sin error
```

## Endpoints

- `GET /api/v1/dashboard` — rol(es): admin, coach — salida: agrega `members_without_consent: int` — códigos: 200, 401, 403
- `GET /api/v1/members?consent=missing` — rol(es): admin, coach — códigos: 200, 401, 403, 422

## Pantalla

- `Inicio` (tarjeta nueva; `// DESIGN-GAP:` la tarjeta no está en el diseño) y `Socio_Ficha` (marca en el encabezado).

## Notas técnicas

- **Migración:** no; considerar índice parcial `members(id) WHERE data_consent_at IS NULL AND deleted_at IS NULL` si el conteo es lento (con 1.000 socios no hace falta).
- **Trigger / restricciones:** ninguna.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** service con base real (conteo excluye bajas), router del filtro, front (tarjeta y marca).
- **Archivos principales:** `api/src/app/modules/members/service.py`, `api/src/app/modules/dashboard/service.py`, `web/src/features/dashboard/pages/HomePage.tsx`.

## Supuestos

- Supuesto: el nombre del campo es `members_without_consent` y el valor del filtro `consent=missing`.

## Dependencias

- US-149 · Registrar autorización de datos
- US-108 · Contrato del tablero

## INVEST

- **Independiente:** agrega un campo y un filtro.
- **Negociable:** ubicación de la tarjeta.
- **Valiosa:** plan de recolección de consentimientos (Q16).
- **Estimable:** conteo, filtro y dos marcas.
- **Pequeña:** sí.
- **Testeable:** conteo exacto y ausencia de bloqueos.

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Front: pruebas de componente; sin colores literales
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
