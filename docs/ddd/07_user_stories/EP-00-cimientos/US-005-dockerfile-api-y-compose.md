# US-005 · Como equipo quiero la imagen del api y los archivos de Compose de producción y desarrollo con healthchecks para que el sistema se levante con un solo comando en el servidor del gimnasio y en cualquier máquina de desarrollo

- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context:** ninguno de negocio (`api/Dockerfile`, `infra/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 5
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `api/Dockerfile` multi-stage con `uv` y usuario no root, `infra/compose.yml` con `web`, `api`, `worker` y `db`, e `infra/compose.dev.yml` con hot reload, puertos abiertos y `db_test`
para que `docker compose up` deje el sistema arriba y sano en minutos, igual en el servidor y en desarrollo

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** stack fijo de `CLAUDE.md` (Docker Engine en Linux, Compose, PostgreSQL 16); "Seguridad" (nada de secretos en imágenes); riesgo 4 de `00b_impact_analysis.md` (KEK en volumen nombrado, no en carpeta montada de Windows); `04_architecture_decision.md` sección 4.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** `api/Dockerfile` en dos etapas (builder con `uv sync --frozen --no-dev`, runtime `python:3.12-slim` con usuario `apex` UID fijo, sin compiladores); comando por defecto Uvicorn y comando alterno `python -m app.worker.main` para el worker (misma imagen). `infra/compose.yml`: servicios `db` (postgres:16 con volumen `pgdata` y healthcheck `pg_isready`), `api` (healthcheck HTTP a `/health`, `env_file: .env`, volumen nombrado `keys` montado en solo lectura en la ruta de `CRYPTO_LOCAL_KEK_PATH`, volumen `uploads` en `/data/uploads`), `worker` (misma imagen, comando worker), `web` (Nginx, lo completa US-006); `restart: unless-stopped`. `infra/compose.dev.yml`: monta `api/src` con `--reload`, publica puertos 8000 y 5432, servicio `db_test` (postgres:16, sin volumen persistente) para pytest.
- **Front:** No aplica.

## Criterios de aceptación

1. `docker build -f api/Dockerfile api` produce una imagen que corre como usuario no root (`docker run --rm <img> id -u` distinto de 0).
2. La imagen final no contiene `.env`, archivos de llave ni el grupo de dependencias de desarrollo (verificado listando `/app` y `pip list`).
3. `docker compose -f infra/compose.yml -f infra/compose.dev.yml up` desde un clon limpio deja `db` en estado `healthy` y `api` respondiendo `/health` con 200 en menos de 5 minutos (cuando exista US-020; antes, el contenedor arranca).
4. La KEK local vive en el volumen nombrado `keys`, no en una carpeta del host; el volumen se monta en modo solo lectura en `api` y `worker`.
5. `worker` usa la misma imagen que `api` con un comando distinto.
6. `db_test` existe solo en `compose.dev.yml` y no persiste datos entre reinicios.
7. Los volúmenes `pgdata`, `uploads`, `keys` (y `backups`, que usa US-114) están declarados con nombre.
8. Ningún servicio de `compose.yml` publica el puerto de PostgreSQL al host.

## Escenarios BDD

```gherkin
# language: es
Característica: Sistema levantado con Docker Compose

  Escenario: Arranque en desarrollo desde cero
    Dado un clon limpio con Docker instalado y un ".env" copiado de ".env.example"
    Cuando ejecuto "docker compose -f infra/compose.yml -f infra/compose.dev.yml up -d"
    Entonces el servicio "db" queda "healthy"
    Y el servicio "api" queda en ejecución con usuario no root

  Escenario: Imagen sin secretos
    Dado la imagen construida desde "api/Dockerfile"
    Cuando busco archivos ".env" o "*.key" dentro de la imagen
    Entonces no encuentro ninguno

  Escenario: Base de producción no expuesta
    Dado solo el archivo "infra/compose.yml"
    Cuando inspecciono los puertos publicados
    Entonces el servicio "db" no publica el puerto 5432 al host
```

## Endpoints

- Ninguno (el healthcheck usa `GET /api/v1/health` o `/health` de US-020).

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** permisos del volumen `keys`: el archivo de KEK queda con modo 600 y dueño UID de `apex` (lo crea `cli init-keys`, US-023).
- **Funciones puras a probar:** ninguna.
- **Pruebas:** job `images` de CI construye la imagen; smoke en CI con `docker compose up` y espera de `healthy` (cuando exista `/health`).
- **Archivos principales:** `api/Dockerfile`, `api/.dockerignore`, `infra/compose.yml`, `infra/compose.dev.yml`.

## Supuestos

- Supuesto: el healthcheck de `api` apunta a `/health` sin prefijo `/api/v1` (el contrato de `05_service_design.md` sección 4 lo lista como público); US-020 confirma la ruta exacta.

## Dependencias

- US-002 · Proyecto api con uv, ruff, mypy y pytest (lo que se empaqueta).

## INVEST

- **Independiente:** solo requiere el proyecto `api`.
- **Negociable:** imagen base, nombres de volúmenes.
- **Valiosa:** el operador levanta el sistema sin conocimientos técnicos.
- **Estimable:** patrón Docker conocido.
- **Pequeña:** tres a cuatro días, con las particularidades de WSL2.
- **Testeable:** comandos y estado `healthy`.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (supuesto declarado)

## Definición de terminado

- [ ] Imagen construida en CI
- [ ] Arranque desde cero verificado en Linux y en Windows con WSL2
- [ ] Revisión de PR aprobada
