# US-118 · Como administrador quiero que los servicios arranquen en orden y solo reciban tráfico cuando la base y las migraciones estén listas para que un reinicio del servidor no deje el sistema a medias

- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context:** ninguno; `infra/compose.yml` y `api/src/app/main.py`
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 2
- **Prioridad:** P1 necesaria para la versión
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero que `db` arranque primero, que `api` corra `alembic upgrade head` antes de aceptar peticiones y que `web` y `worker` esperen a `api` sano
para que después de un corte de luz el sistema vuelva solo y completo

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** regla de datos 7 (nunca `create_all` en producción), `04_architecture_decision.md` sección 4 (api corre migraciones al arrancar) y sección 8 (reinicio automático de Compose).
- **Eventos que emite:** ninguno.
- **Eventos que consume:** ninguno.
- **Funciones puras:** ninguna.

## Alcance

- **Backend:** healthchecks en `db` (`pg_isready`), `api` (`/health` con `db: "ok"` y migraciones aplicadas) y `web` (Nginx responde); `depends_on` con `condition: service_healthy` (`api` de `db`; `web` y `worker` de `api`); `restart: unless-stopped` en todos; el api no abre el puerto hasta terminar `alembic upgrade head` y abrir las DEK; si la migración falla, el api termina con código distinto de 0 y Compose lo reintenta.
- **Front:** No aplica.

## Criterios de aceptación

1. Con `docker compose up` desde cero, `worker` y `web` no arrancan hasta que `api` está `healthy`.
2. Mientras `alembic upgrade head` corre, el api no responde peticiones (la conexión es rechazada o `/health` aún no existe).
3. Si una migración falla, el contenedor `api` sale con código distinto de 0, no queda escuchando en un estado parcial y el log nombra la revisión que falló.
4. Después de `docker compose restart` o de reiniciar el host, todos los servicios vuelven a `healthy` sin intervención.
5. `/health` responde 200 solo cuando la base responde y la revisión de Alembic actual es `head`.
6. Ningún servicio usa `create_all`; una prueba de arquitectura lo verifica fuera de `tests/`.

## Escenarios BDD

```gherkin
# language: es
Característica: Arranque ordenado

  Escenario: Arranque en frío
    Dado que no hay contenedores en marcha
    Cuando ejecuto "docker compose up -d"
    Entonces "db" queda "healthy" antes que "api"
    Y "web" y "worker" arrancan después de que "api" está "healthy"

  Escenario: Migración fallida
    Dado una migración nueva con un error
    Cuando arranca "api"
    Entonces "api" termina con un código distinto de 0
    Y "web" no arranca

  Escenario: Recuperación tras reinicio del host
    Dado el sistema en marcha
    Cuando el host se reinicia
    Entonces todos los servicios vuelven a "healthy" sin intervención
```

## Endpoints

- `GET /api/v1/health` (consumido por el healthcheck).

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** no aplica.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** smoke de Compose en CI (arranque en frío y migración rota); prueba de arquitectura contra `create_all`.
- **Archivos principales:** `infra/compose.yml`, `api/src/app/main.py`, `api/tests/architecture/test_no_create_all.py`.

## Supuestos

- Ninguno.

## Dependencias

- US-005 · Dockerfile del api y Compose.
- US-020 · create_app, migraciones y health.

## INVEST

- **Independiente:** solo configuración de Compose y arranque.
- **Negociable:** tiempos de healthcheck ajustables.
- **Valiosa:** el sistema se recupera solo tras un corte.
- **Estimable:** cambio acotado.
- **Pequeña:** configuración y una prueba.
- **Testeable:** smoke en CI.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Smoke de Compose en CI en verde
- [ ] Pruebas de router de `/health`
- [ ] Front (no aplica)
- [ ] Migración (no aplica)
- [ ] `docs/openapi.json` regenerado (no aplica)
- [ ] Auditoría (no aplica)
- [ ] Revisión de PR aprobada
