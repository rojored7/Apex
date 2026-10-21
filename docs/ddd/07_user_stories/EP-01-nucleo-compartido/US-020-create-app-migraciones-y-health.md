# US-020 · Como equipo quiero `create_app()` que aplique las migraciones al arrancar y exponga `/health` para que el sistema no acepte tráfico con un esquema viejo y el operador sepa en un vistazo si está sano

- **Épica:** EP-01 · Núcleo compartido de la plataforma
- **Bounded context:** `core/` (`main.py`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `main.py` con `create_app()` que registre routers, middlewares y handlers de error, corra `alembic upgrade head` antes de aceptar peticiones y exponga `GET /health`
para que cada despliegue deje el esquema al día y el healthcheck de Compose refleje el estado real de la base

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** estructura de `CLAUDE.md` (`main.py` corre migraciones al arrancar); "Calidad y Git" (healthcheck en `/health`); `04_architecture_decision.md` secciones 4 y 6 (`/health` en la lista blanca sin rol).
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `create_app()` que valida `Settings`, configura logging (US-018), registra handlers de error (US-017), monta los routers de módulos bajo `/api/v1`, y en el `lifespan` de arranque ejecuta `alembic upgrade head` con un `pg_advisory_lock` (para que `api` y `worker` no migren a la vez) y luego los pasos de arranque que registren otras historias (apertura de DEKs, US-025); `GET /health` (sin rol) que hace `SELECT 1` con timeout de 2 s y devuelve `{ "status": "ok", "db": "ok", "version": "<git sha>" }` con 200 o `{ "status": "degraded", "db": "down" }` con 503; registro extensible de comprobaciones de salud (`register_health_check(name, fn)`) para que US-136 agregue OpenBao.
- **Front:** No aplica.

## Criterios de aceptación

1. Con la base arriba, `GET /health` responde 200 con `status = ok` y `db = ok`.
2. Con la base abajo, `GET /health` responde 503 con `db = down` en menos de 3 s.
3. Al arrancar sobre una base con migraciones pendientes, el api las aplica antes de aceptar la primera petición; si una migración falla, el proceso termina con código distinto de 0.
4. Dos procesos arrancando a la vez no ejecutan la migración en paralelo (lock asesor).
5. `/health` no exige rol y no devuelve datos personales ni configuración sensible.
6. Todas las rutas de módulos quedan bajo el prefijo `/api/v1`.
7. Uvicorn arranca con `uv run uvicorn app.main:app`.

## Escenarios BDD

```gherkin
# language: es
Característica: Arranque con migraciones y salud

  Escenario: Sistema sano
    Dado el api arrancado con la base disponible
    Cuando pido "GET /health"
    Entonces el código HTTP es 200
    Y el cuerpo indica "db" igual a "ok"

  Escenario: Base caída
    Dado el api en ejecución y la base detenida
    Cuando pido "GET /health"
    Entonces el código HTTP es 503 en menos de 3 segundos
    Y el cuerpo indica "db" igual a "down"

  Escenario: Migración que falla impide arrancar
    Dado una migración pendiente que falla
    Cuando arranca el api
    Entonces el proceso termina con error
    Y no acepta peticiones
```

## Endpoints

- `GET /health` — rol(es): ninguno (lista blanca) — entrada: ninguna — salida: `{ status, db, version }` — códigos: 200, 503.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no (ejecuta las existentes).
- **Trigger / restricciones:** `pg_advisory_lock` con una clave fija durante `upgrade`.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** router (`/health` con base arriba y con engine apuntando a un puerto cerrado), service (lock), smoke en Compose.
- **Archivos principales:** `api/src/app/main.py`, `api/src/app/core/health.py`.

## Supuestos

- Supuesto: `/health` se expone en la raíz del api (`/health`) y además en `/api/v1/health` para que Nginx lo alcance por el proxy; el contrato de `05_service_design.md` sección 4 lo lista como `GET /health` bajo el prefijo.

## Dependencias

- US-012 · Base de datos y Alembic multiesquema.
- US-017 · Envelope de errores.
- US-018 · Logging JSON sin datos sensibles.

## INVEST

- **Independiente:** no depende de módulos de negocio.
- **Negociable:** forma de la respuesta de salud.
- **Valiosa:** despliegues seguros y diagnóstico inmediato.
- **Estimable:** acotada.
- **Pequeña:** dos días.
- **Testeable:** códigos 200 y 503.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de router y smoke en verde
- [ ] `docs/openapi.json` regenerado
- [ ] Revisión de PR aprobada
