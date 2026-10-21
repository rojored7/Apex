# US-013 · Como equipo quiero un puerto `Clock` con reloj de sistema, reloj congelado y `today_bogota()` para que "hoy" sea siempre la fecha civil de Bogotá y las reglas de fechas se prueben sin esperar días

- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context:** `core/` (`core/clock.py`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 2
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `Clock` (Protocol) con `now_utc()` y `today_bogota()`, y las implementaciones `SystemClock` y `FrozenClock`
para que el estado de una membresía no cambie de día a las 7 de la noche por usar la fecha UTC, y las pruebas fijen el tiempo

## Contexto de dominio

- **Aggregate / entidades:** ninguno (lo usan Membership, Notification, el worker).
- **Reglas que aplica:** Q28 de `DECISIONES.md` (el `today` de `compute_status` y de todos los jobs es la fecha civil en `America/Bogota`, calculada en `core/clock.py`); regla de datos 2 (UTC en base).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** `clock.to_bogota_date(instant_utc) -> date`

## Alcance

- **Backend:** `core/clock.py` con `class Clock(Protocol)`: `now_utc() -> datetime` (aware, UTC) y `today_bogota() -> date`; `SystemClock` usa `datetime.now(UTC)` y `zoneinfo.ZoneInfo("America/Bogota")`; `FrozenClock(instant)` con `advance(days=..., hours=...)`; función pura `to_bogota_date`; dependencia FastAPI `get_clock` que devuelve `SystemClock` y que las pruebas sobrescriben con `FrozenClock`.
- **Front:** No aplica.

## Criterios de aceptación

1. `now_utc()` siempre devuelve un `datetime` con `tzinfo` UTC; nunca un `datetime` ingenuo.
2. `to_bogota_date(2026-10-21T02:30:00Z)` devuelve `2026-10-20` (19:30 del 20 en Bogotá).
3. `to_bogota_date(2026-10-21T05:00:00Z)` devuelve `2026-10-21`.
4. `FrozenClock` devuelve siempre el mismo instante hasta llamar `advance`.
5. Ningún archivo de `src/` fuera de `core/clock.py` llama `datetime.now()`, `datetime.utcnow()` ni `date.today()` (prueba de arquitectura por búsqueda de texto).
6. La zona `America/Bogota` está disponible en la imagen (paquete `tzdata` instalado).

## Escenarios BDD

```gherkin
# language: es
Característica: Hoy es la fecha de Bogotá

  Escenario: Noche en Bogotá, día siguiente en UTC
    Dado el instante "2026-10-21T02:30:00Z"
    Cuando calculo today_bogota
    Entonces obtengo la fecha "2026-10-20"

  Escenario: Reloj congelado para pruebas
    Dado un FrozenClock en "2026-10-20T12:00:00Z"
    Cuando avanzo 1 día
    Entonces today_bogota es "2026-10-21"

  Escenario: Uso directo de datetime.now prohibido
    Dado un service que llama "datetime.now()"
    Cuando corre la prueba de arquitectura de reloj
    Entonces la prueba falla nombrando el archivo
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** ninguno.
- **Funciones puras a probar:** `to_bogota_date` con los bordes 04:59Z y 05:00Z (Bogotá es UTC-5 sin horario de verano).
- **Pruebas:** `tests/core/test_clock.py`, `tests/architecture/test_no_direct_now.py`.
- **Archivos principales:** `api/src/app/core/clock.py`.

## Supuestos

- Ninguno.

## Dependencias

- US-002 · Proyecto api con uv, ruff, mypy y pytest.

## INVEST

- **Independiente:** no depende de base de datos.
- **Negociable:** nombres de métodos.
- **Valiosa:** evita errores de un día en vencimientos y avisos.
- **Estimable:** acotada.
- **Pequeña:** un día.
- **Testeable:** casos de borde horario.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas puras y de arquitectura en verde
- [ ] Revisión de PR aprobada
