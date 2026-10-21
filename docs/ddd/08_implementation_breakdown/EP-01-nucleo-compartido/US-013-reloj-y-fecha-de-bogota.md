# US-013 · Reloj `Clock` y `today_bogota()` — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-01-nucleo-compartido/US-013-reloj-y-fecha-de-bogota.md`
- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context / módulo:** core (`api/src/app/core/clock.py`)
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

Q28 fija el comportamiento: "hoy" es la fecha civil de `America/Bogota`, calculada en `core/clock.py`. La historia ya lo recoge. No hay supuestos abiertos, y los bordes horarios son verificables porque Bogotá es UTC-5 sin horario de verano.

## Resumen

Se crea `core/clock.py` con lo siguiente:
- el Protocol `Clock` (`now_utc`, `today_bogota`);
- `SystemClock` y `FrozenClock`;
- la función pura `to_bogota_date`;
- un accesor de proceso `current_clock()`/`set_clock()`.

El accesor lo usan el bus de eventos (`occurred_at`), la auditoría (`at`) y el worker, que no reciben dependencias de FastAPI. También existe la dependencia `get_clock` para los routers. Una prueba de arquitectura prohíbe `datetime.now()`, `datetime.utcnow()`, `datetime.today()` y `date.today()` fuera de este archivo.

## Correcciones aplicadas por DECISIONES.md

- Ninguna; la historia ya es coherente con DECISIONES.md (Q28).

## Validación contra el dominio

- La usan `memberships.compute_status(membership, today, expiring_days)` (Q11, Q28), `notifications.target_dates` y todos los jobs del worker. El `today` siempre viene de `today_bogota()`.
- Función pura: `to_bogota_date(instant_utc: datetime) -> date`. Rechaza un `datetime` ingenuo con `ValueError`.
- Sin aggregates, sin eventos.

## Validación contra la arquitectura

- `Clock` es uno de los cuatro puertos de `05_service_design.md` sección 1.
- `core/clock.py` solo importa la biblioteca estándar (`datetime`, `zoneinfo`, `typing`). Ningún otro archivo de `core/` crea ciclos con él.
- La zona `America/Bogota` es una constante del módulo (`BOGOTA = ZoneInfo("America/Bogota")`). `Settings.TZ_DISPLAY` no altera el "hoy" de negocio (Q28).
- Rol, paginación, bus de criptografía y auditoría: no aplican.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `to_bogota_date(instant_utc: datetime) -> date` en `core/clock.py`. Exige `tzinfo` (si no lo tiene, `ValueError`) y devuelve `instant_utc.astimezone(BOGOTA).date()` — 0,5 h
- [ ] T2 · Clases del reloj:
  - `class Clock(Protocol)` con `now_utc() -> datetime` y `today_bogota() -> date`;
  - `SystemClock`, que usa `datetime.now(UTC)`;
  - `FrozenClock(instant: datetime)`, que exige un instante aware, lo normaliza a UTC y ofrece `advance(*, days=0, hours=0, minutes=0) -> None` y `set(instant) -> None`.
  
  `today_bogota()` delega en `to_bogota_date(self.now_utc())` — 1,5 h
- [ ] T3 · Accesores:
  - `current_clock() -> Clock` y `set_clock(clock: Clock) -> Token`, sobre un `ContextVar` con `SystemClock` como valor por defecto. Con `ContextVar`, las pruebas en paralelo no se pisan;
  - dependencia FastAPI `get_clock() -> Clock`, que devuelve `current_clock()`; las pruebas usan `app.dependency_overrides[get_clock]` o `set_clock(FrozenClock(...))`;
  - docstring: el bus de eventos (US-014), la auditoría (US-015) y el worker toman la hora de `current_clock()`.
  
  — 1,5 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T4 · `tests/core/test_clock.py`:
  - `now_utc()` siempre aware con `UTC` (criterio 1);
  - `to_bogota_date(2026-10-21T02:30:00Z) == 2026-10-20` (criterio 2);
  - `to_bogota_date(2026-10-21T05:00:00Z) == 2026-10-21` (criterio 3);
  - bordes `04:59:59Z` (día anterior) y `05:00:00Z` (mismo día);
  - un instante ingenuo da `ValueError`;
  - `FrozenClock` fijo hasta `advance` (criterio 4);
  - escenario BDD: `FrozenClock(2026-10-20T12:00Z).advance(days=1)` da `today_bogota() == 2026-10-21`;
  - `set_clock` dentro de un contexto no se filtra a otro.
  
  — 1,5 h

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica. La sobrescritura de `get_clock` se ejercita en las pruebas de router de los módulos que la usan (EP-09, EP-12).

### Tests de arquitectura
- [ ] T5 · `api/tests/architecture/test_no_direct_now.py`:
  - recorre `src/app/**` con `ast` y falla, nombrando archivo y línea, ante `datetime.now`, `datetime.utcnow`, `datetime.today` o `date.today` fuera de `core/clock.py` (criterio 5);
  - cubre también los alias (`from datetime import datetime as dt`; `dt.now()`).
  
  — 1,5 h

### Front
- No aplica.

### DevOps
- [ ] T6 · Agregar `tzdata` (Apache-2.0) como dependencia de `api/pyproject.toml`, para no depender del sistema operativo de la imagen, y un paso de smoke en el Dockerfile o en CI: `python -c "import zoneinfo; zoneinfo.ZoneInfo('America/Bogota')"` (criterio 6) — 0,5 h

### Seguridad
- No aplica (no maneja datos sensibles ni entradas externas).

## Orden de ejecución
1. T4 y T5 (en rojo)
2. T1
3. T2
4. T3
5. T6

## Dependencias técnicas
- US-002 · Proyecto api con uv, ruff, mypy y pytest: entorno y mypy estricto.
- US-005 · Dockerfile del api: smoke de `tzdata` en la imagen (T6).

## Endpoints
- Ninguno.

## Riesgos
- Un `FrozenClock` global que se filtra entre pruebas paralelas — mitigación: `ContextVar` en `set_clock` (T3), con su prueba.
- Uso indirecto del reloj del sistema (`func.now()` en SQL) para calcular "hoy" — mitigación: `func.now()` solo para `created_at` y `updated_at` técnicos; el "hoy" de negocio siempre sale de `today_bogota()`. La regla se documenta en el docstring y se revisa en las historias de EP-09 y del worker.
- Si Colombia adoptara horario de verano, cambiaría la regla — mitigación: `zoneinfo` con `tzdata` actualizado lo absorbe sin cambiar código.

## Estimación
- Backend: 3,5 h
- Front: 0 h
- Pruebas: 3 h
- DevOps / seguridad: 0,5 h
- **Total: 7 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_clock.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `docker compose -f infra/compose.yml run --rm api python -c "import zoneinfo; print(zoneinfo.ZoneInfo('America/Bogota'))"` imprime la zona sin error
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.clock --cov-fail-under=80`
