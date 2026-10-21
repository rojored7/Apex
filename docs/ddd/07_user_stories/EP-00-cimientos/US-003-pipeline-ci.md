# US-003 · Como equipo quiero un pipeline de CI que corra lint, tipos, pruebas con PostgreSQL 16 y el build de imágenes en cada PR para que nada roto llegue a `main`

- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context:** ninguno de negocio (`.github/workflows/`)
- **Versión:** v0.1
- **Actor:** equipo
- **Tamaño:** 3
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como equipo
quiero `.github/workflows/ci.yml` con ruff, mypy, pytest contra un servicio PostgreSQL 16 y build de las imágenes
para que la protección de `main` dependa de una verificación automática y no de la memoria de quien revisa

## Contexto de dominio

- **Aggregate / entidades:** ninguno.
- **Reglas que aplica:** "Calidad y Git" de `CLAUDE.md` (CI en cada PR: lint, mypy, pruebas, licencias, build); `05_service_design.md` sección 7.
- **Eventos que emite:** ninguno
- **Eventos que consume:** ninguno
- **Funciones puras:** ninguna

## Alcance

- **Backend:** workflow con disparadores `pull_request` y `push` a `main`; job `api` (setup de uv con caché, `uv sync`, `ruff check`, `ruff format --check`, `mypy src`, `pytest --cov` con `services: postgres:16` y `DATABASE_URL` de prueba); job `web` (`npm ci`, lint, `npm test`, `npm run build`) que se activa cuando exista `web/package.json`; job `images` (`docker build` de `api` y `web` sin push); el check de licencias se agrega en US-004. Regla de protección de `main` actualizada para exigir estos jobs.
- **Front:** No aplica (solo el job de CI del front).

## Criterios de aceptación

1. Todo PR hacia `main` ejecuta los jobs `api`, `web` e `images`.
2. El job `api` usa un contenedor `postgres:16` y las pruebas se conectan a él por `DATABASE_URL`; ninguna prueba usa SQLite.
3. Un PR con un error de ruff, de mypy o una prueba fallida queda en rojo y no se puede fusionar.
4. El job `api` publica el reporte de cobertura y falla si la cobertura de `src/` baja de 80 % (umbral activo desde que exista código de negocio; en este sprint el umbral se configura pero aplica sobre lo existente).
5. El job `images` construye `api/Dockerfile` y la imagen del front sin publicarlas.
6. Ningún secreto real se usa en CI; las variables de prueba están en el workflow o en `env` de prueba.
7. El tiempo total del pipeline en un PR trivial es menor de 10 minutos.

## Escenarios BDD

```gherkin
# language: es
Característica: Integración continua en cada PR

  Escenario: PR correcto en verde
    Dado un PR que no rompe lint, tipos ni pruebas
    Cuando GitHub Actions ejecuta el workflow "ci"
    Entonces los jobs "api", "web" e "images" terminan en verde
    Y el botón de fusionar queda habilitado

  Escenario: Prueba fallida bloquea la fusión
    Dado un PR con una prueba de pytest que falla
    Cuando corre el job "api"
    Entonces el job termina en rojo
    Y la protección de "main" impide fusionar

  Escenario: Pruebas contra PostgreSQL real
    Dado el job "api" con el servicio "postgres:16"
    Cuando una prueba abre una sesión con DATABASE_URL
    Entonces la conexión es a PostgreSQL 16
    Y la prueba no usa SQLite
```

## Endpoints

- Ninguno.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no.
- **Trigger / restricciones:** checks obligatorios en la protección de rama.
- **Funciones puras a probar:** ninguna.
- **Pruebas:** PR de control con una prueba rota (debe quedar en rojo) documentado en la descripción del PR.
- **Archivos principales:** `.github/workflows/ci.yml`.

## Supuestos

- Ninguno.

## Dependencias

- US-002 · Proyecto api con uv, ruff, mypy y pytest.

## INVEST

- **Independiente:** solo requiere el proyecto `api`; los jobs `web` e `images` se activan cuando existan sus archivos.
- **Negociable:** caché, matriz y tiempos.
- **Valiosa:** convierte las reglas de calidad en un gate obligatorio.
- **Estimable:** workflow estándar.
- **Pequeña:** uno o dos días.
- **Testeable:** PR de control en rojo y PR limpio en verde.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y regla
- [x] Endpoints y roles definidos (no aplica)
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen

## Definición de terminado

- [ ] Workflow en `main` y checks obligatorios configurados
- [ ] PR de control en rojo verificado
- [ ] Revisión de PR aprobada
