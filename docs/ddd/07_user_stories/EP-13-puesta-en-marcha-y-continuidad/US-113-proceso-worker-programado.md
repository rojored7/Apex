# US-113 · Como administrador quiero un proceso worker que corra los trabajos diarios a las 7:00 hora de Bogotá para que vencimientos y verificaciones ocurran sin que nadie se acuerde

- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context:** ninguno propio; `api/src/app/worker/` (misma imagen que el api, comando distinto)
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero que el servicio `worker` ejecute cada día a las 7:00 America/Bogota los trabajos registrados por cada épica
para que los estados de membresías, los avisos y las verificaciones se actualicen solos

## Contexto de dominio

- **Aggregate / entidades:** ninguno propio; el worker invoca services (`memberships.service.recompute_statuses` en US-094, `backup_check` en US-115; en versiones siguientes `notify` y `sign_audit`).
- **Reglas que aplica:** Q28 (el "hoy" de todos los jobs es `today_bogota()` de `core/clock.py`), `04_architecture_decision.md` sección 5 (el worker no recibe eventos; consulta tablas), sección 8 (todo efecto obligatorio se persiste en tabla).
- **Eventos que emite:** ninguno propio (los jobs emiten los suyos dentro de su transacción).
- **Eventos que consume:** ninguno.
- **Funciones puras:** `worker.registry.register(job_name, func, hour, minute)`; `worker.schedule.next_run(now_utc, tz="America/Bogota", hour=7)`.

## Alcance

- **Backend:** `worker/main.py` con APScheduler (MIT) en zona `America/Bogota`, un registro de jobs (`worker/jobs/__init__.py`) en el que cada épica agrega el suyo, una sesión de base y transacción propia por job, log JSON por ejecución (inicio, fin, duración, resultado) sin datos personales, captura de excepciones por job (un job que falla no detiene los demás), y comando `uv run python -m app.worker.main --run-once <job>` para ejecutar un job a demanda. Servicio `worker` en `infra/compose.yml` con la misma imagen y `command` distinto, `restart: unless-stopped`.
- **Front:** No aplica.

## Criterios de aceptación

1. El servicio `worker` arranca con `docker compose up` usando la misma imagen que `api` y un comando distinto.
2. Los jobs registrados se programan a las 07:00 en `America/Bogota`; con `FrozenClock` en 2026-10-21 11:59 UTC (06:59 Bogotá) la próxima ejecución calculada es 2026-10-21 12:00 UTC.
3. Cada job recibe `today = today_bogota()` y no usa la fecha UTC; a las 20:00 de Bogotá del 21 de octubre (01:00 UTC del 22) `today_bogota()` devuelve 2026-10-21.
4. Un job que lanza una excepción queda registrado en el log con su nombre y el error, su transacción se revierte y los demás jobs del ciclo se ejecutan.
5. `--run-once expirations` ejecuta solo ese job y termina con código 0 si tuvo éxito y distinto de 0 si falló.
6. Los logs del worker son JSON a stdout e incluyen `job`, `started_at` y `finished_at` en UTC, `duration_ms` y `result`; nunca incluyen campos cifrados ni tokens.
7. Si el contenedor se reinicia después de las 07:00 sin haber corrido el ciclo del día, al arrancar ejecuta los jobs pendientes del día una sola vez (misfire con gracia) y no los ejecuta dos veces si ya corrieron.
8. Si la base no está disponible, el worker reintenta la conexión y no termina en un ciclo de reinicio rápido (espera exponencial con tope de 60 s).

## Escenarios BDD

```gherkin
# language: es
Característica: Worker programado

  Escenario: Ejecutar los jobs a las 7:00 de Bogotá
    Dado un worker con el job "expirations" registrado
    Y el reloj en "2026-10-21T11:59:00Z"
    Cuando el reloj avanza a "2026-10-21T12:00:00Z"
    Entonces el job "expirations" se ejecuta una vez con today "2026-10-21"

  Escenario: Un job que falla no detiene a los demás
    Dado los jobs "expirations" y "backup_check" registrados
    Y "expirations" lanza una excepción
    Cuando corre el ciclo de las 7:00
    Entonces "backup_check" se ejecuta
    Y el log contiene el error de "expirations" sin datos personales

  Escenario: Reinicio tardío sin doble ejecución
    Dado que el ciclo del 2026-10-21 ya corrió a las 7:00
    Cuando el worker se reinicia a las 9:00 de Bogotá del mismo día
    Entonces ningún job vuelve a ejecutarse ese día

  Escenario: Ejecutar un job a demanda con nombre inexistente
    Cuando ejecuto "app.worker.main --run-once no-existe"
    Entonces el comando termina con un código distinto de 0
    Y lista los jobs registrados
```

## Endpoints

- Ninguno. Proceso `uv run python -m app.worker.main [--run-once <job>]`.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** sí, mínima: tabla `worker.job_runs` (`id`, `job_name`, `run_date` (fecha Bogotá), `started_at`, `finished_at`, `result`, `error`, columnas comunes) con índice único (`job_name`, `run_date`) para evitar doble ejecución tras reinicio.
- **Trigger / restricciones:** índice único (`job_name`, `run_date`) en `job_runs` cuando `result = 'ok'` (índice parcial).
- **Funciones puras a probar:** `next_run` con cambios de día UTC/Bogotá; `should_run(job, run_date, previous_runs)`.
- **Pruebas:** con `FrozenClock`; job de prueba que falla; prueba de compose (smoke) que el servicio arranca.
- **Archivos principales:** `api/src/app/worker/main.py`, `api/src/app/worker/jobs/__init__.py`, `infra/compose.yml`, `api/tests/worker/test_scheduler.py`.

## Supuestos

- Supuesto: se agrega la tabla `worker.job_runs` (esquema `worker`) para recordar qué ciclo corrió; los documentos no la nombran pero la exigen la idempotencia tras reinicio y la regla "todo efecto obligatorio se persiste en tabla".

## Dependencias

- US-020 · create_app, migraciones y health (configuración y sesión compartidas).
- US-013 · Reloj y fecha de Bogotá (`today_bogota`, `FrozenClock`).
- US-005 · Dockerfile del api y Compose (servicio `worker`).

## INVEST

- **Independiente:** no depende de ningún job de negocio; se prueba con un job de prueba.
- **Negociable:** la estrategia de reintento y el formato del log se pueden ajustar.
- **Valiosa:** sin worker no hay vencimientos automáticos ni verificación de backup.
- **Estimable:** APScheduler y patrón conocidos.
- **Pequeña:** un proceso y un registro.
- **Testeable:** con `FrozenClock` y la tabla de ejecuciones.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error (no aplica)
- [ ] Front: pruebas de componente y página; sin colores literales (no aplica)
- [ ] Migración aplicada con `alembic upgrade head` y reversible
- [ ] `docs/openapi.json` regenerado (no aplica)
- [ ] Auditoría verificada para las tablas tocadas (no aplica)
- [ ] Revisión de PR aprobada
