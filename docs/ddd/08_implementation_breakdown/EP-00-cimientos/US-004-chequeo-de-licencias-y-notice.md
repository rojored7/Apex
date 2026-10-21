# US-004 · Chequeo de licencias en CI y archivo NOTICE — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-00-cimientos/US-004-chequeo-de-licencias-y-notice.md`
- **Épica:** EP-00 · Cimientos del repositorio
- **Bounded context / módulo:** ninguno de negocio, terreno (`.github/workflows/ci.yml`, `api/`, `web/`, `NOTICE`, `CONTRIBUTING.md`)
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**NEEDS_REFINEMENT**

La lista permitida de `CLAUDE.md`, ampliada por DECISIONES N-49 con `0BSD`, `ISC` y `OFL-1.1`, no incluye la licencia de la Python Software Foundation (`PSF-2.0`). `typing_extensions`, dependencia obligatoria de Pydantic v2, FastAPI y SQLAlchemy 2, se publica con `PSF-2.0`; `greenlet` (lo trae SQLAlchemy async) declara `MIT` y `PSF-2.0`. Con un `--allow-only` estricto, que exige el criterio 6 (licencia desconocida falla), el job `api` queda en rojo desde la primera corrida. DECISIONES.md no lo resuelve y no se puede sacar la dependencia sin cambiar el stack fijo.

## Resumen

Dos pasos de licencias en CI y un `NOTICE` en la raíz. Backend: `pip-licenses` sobre el entorno de runtime del api (sin grupo `dev`), con lista blanca estricta (`--allow-only`), coincidencia parcial y una lista de excepciones MPL-2.0 explícita y comentada. Front: `license-checker` sobre dependencias de producción con `--onlyAllow` y `--excludePrivatePackages`. Un PR de control con `fpdf2` (LGPL) debe quedar en rojo. `NOTICE` lista nombre, versión y licencia de cada dependencia directa de `api` y `web`, más las fuentes OFL que no son paquetes.

## Correcciones aplicadas por DECISIONES.md

- La historia acepta `0BSD` en el front como supuesto "si el gate lo rechaza se quita" → `0BSD`, `ISC` y `OFL-1.1` quedan en la lista permitida de backend y de front, y `CLAUDE.md` se actualiza en el gate: corregido por DECISIONES N-49.
- La historia usa `--fail-on` con la lista prohibida y además `--allow-only` → se usa solo `--allow-only` (lista blanca), que ya rechaza las prohibidas y también lo desconocido (criterio 6); la lista prohibida queda como comentario y como prueba de control. No es corrección de DECISIONES; es la forma de cumplir el criterio 6 sin ambigüedad.

## Validación contra el dominio

- No hay aggregates, entidades, value objects, invariantes RN-xx ni eventos.

## Validación contra la arquitectura

- Sección "Licencias" de `CLAUDE.md`: MIT, BSD, Apache 2.0, PostgreSQL; MPL-2.0 solo sin modificar; prohibidas GPL, LGPL, AGPL, BSL, SSPL. Con N-49: más `0BSD`, `ISC`, `OFL-1.1`.
- MPL-2.0 sin modificar en v0.1, ya presente de forma transitiva: `certifi` (lo trae `httpx`). Entra a la lista de excepciones con comentario "sin modificar, transitiva de httpx", igual que el patrón de OpenBao y pywebpush. En el front, `axe-core` (MPL-2.0) llega con US-010 como dependencia de desarrollo; no la toca el chequeo de producción, pero va en `NOTICE` como herramienta.
- El chequeo de backend corre sobre el entorno de runtime (lo que va en la imagen), no sobre el de desarrollo: herramientas como `pip-licenses` o `pre-commit` no se distribuyen. Se corre además un informe del entorno de desarrollo sin `--allow-only`, solo para el `NOTICE`.
- ShellCheck (GPL-3.0) no se usa en CI para los scripts de US-008, aunque sea solo herramienta: evita abrir la discusión de licencias.

## Preguntas abiertas

- Pregunta: ¿se agrega `PSF-2.0` (Python Software Foundation License) a la lista de licencias permitidas de `CLAUDE.md`, igual que N-49 agregó `0BSD`, `ISC` y `OFL-1.1`? Es permisiva y la usan `typing_extensions` (obligatoria para Pydantic v2 y FastAPI) y `greenlet` (SQLAlchemy async). Alternativa por defecto propuesta: **sí**, se agrega `PSF-2.0` (y su variante de nombre `Python Software Foundation License`) a la lista blanca del backend y se registra junto a N-49 en el gate. La alternativa contraria (excepción por paquete para `typing_extensions` y `greenlet`) también funciona, pero obliga a mantener la lista cada vez que otro paquete PSF entre de forma transitiva.

## Tareas

### Migración Alembic
- No aplica.

### Models
- No aplica.

### Service
- No aplica.

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- No aplica.

### Tests de service con PostgreSQL
- No aplica.

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T1 · `scripts/ci/tests/test_licenses.sh`: crea un entorno temporal con `uv venv`, instala `fpdf2` y corre `scripts/ci/check-licenses-api.sh` contra él; exige código distinto de 0 y que la salida nombre `fpdf2` y `LGPL`. Repite con un paquete local sin metadatos de licencia (`scripts/ci/tests/fixtures/sin-licencia/`) y exige falla (criterio 6). Lo corre el job `api` en un paso aparte — 2 h

### Front
- [ ] T2 · `web/package.json`: script `"licenses": "license-checker --production --excludePrivatePackages --onlyAllow \"MIT;BSD-2-Clause;BSD-3-Clause;Apache-2.0;ISC;0BSD;OFL-1.1\" --summary"` y `license-checker` (BSD-3-Clause) en `devDependencies`; documentar en `CONTRIBUTING.md` que una licencia desconocida (`UNKNOWN`, `UNLICENSED`) falla — 1 h

### DevOps
- [ ] T3 · `scripts/ci/check-licenses-api.sh`: `uv sync --frozen --no-dev` en un entorno aparte (`UV_PROJECT_ENVIRONMENT=.venv-runtime`) y `uvx --from pip-licenses pip-licenses --python .venv-runtime/bin/python --from=mixed --partial-match --allow-only="MIT;BSD;Apache;PostgreSQL;ISC;0BSD;PSF;Python Software Foundation" --ignore-packages <lista de excepciones MPL-2.0>`; la lista de excepciones vive en `scripts/ci/licenses-exceptions.txt` con una línea por paquete y su comentario (`certifi  # MPL-2.0 sin modificar, transitiva de httpx`); el `PSF` queda condicionado a la respuesta de la pregunta abierta — 2,5 h
- [ ] T4 · Paso `licencias-api` en el job `api` de `.github/workflows/ci.yml` que corre T3 y luego T1 — 0,5 h
- [ ] T5 · Paso `licencias-web` en el job `web` que corre `npm run licenses` (activo cuando exista `web/package.json`, igual que el job) — 0,5 h
- [ ] T6 · `scripts/ci/notice.sh`: genera la sección de dependencias directas de `NOTICE` (api: `pip-licenses --from=mixed --format=plain-vertical --packages <directas de pyproject>`; web: `license-checker --production --direct --csv`), más un bloque fijo para Michroma y Titillium Web (OFL-1.1, archivos en `web/public/fonts/`) y para `axe-core` (MPL-2.0, solo desarrollo); paso de CI que regenera y falla con `git diff --exit-code NOTICE` si quedó desactualizado — 2 h
- [ ] T7 · `NOTICE` inicial en la raíz generado con T6 y `CONTRIBUTING.md` con la regla "toda dependencia nueva actualiza `NOTICE` (`bash scripts/ci/notice.sh`) y, si es MPL-2.0, se agrega a `scripts/ci/licenses-exceptions.txt` con su justificación" — 1 h
- [ ] T8 · PR de control `chore/licencias-control` que agrega `fpdf2` a `[project.dependencies]`; verificar el rojo del paso `licencias-api` con el nombre del paquete en el log; cerrar sin fusionar — 0,5 h

### Seguridad
- [ ] T9 · Revisión de la lista de excepciones: cada entrada MPL-2.0 tiene comentario, no hay comodines, y ninguna excepción cubre un paquete GPL/LGPL/AGPL/BSL/SSPL; revisar que el chequeo corre sobre runtime y no sobre `dev` — 1 h

## Orden de ejecución
1. T3 (script del backend; primero en local contra el lock actual para ver qué paquetes no pasan)
2. T1 (prueba de control en rojo y en verde)
3. T4 (paso en CI)
4. T2, T5 (front, cuando exista `web/package.json`)
5. T6, T7 (NOTICE generado y regla documentada)
6. T9 (revisión)
7. T8 (PR de control)

## Dependencias técnicas
- US-003 · Pipeline CI: los jobs `api` y `web` donde viven los pasos.
- US-002 · Proyecto api: `uv.lock` sobre el que corre `pip-licenses`.
- US-009 · Esqueleto del front: `web/package.json` para T2 y T5 (el paso del backend no lo espera).

## Endpoints
- Ninguno.

## Riesgos
- Nombres de licencia inconsistentes en metadatos de PyPI (clasificadores "BSD License", "Apache Software License", expresiones SPDX `Apache-2.0 OR BSD-3-Clause`): con coincidencia exacta habría falsos rechazos — mitigación: `--partial-match` con raíces cortas (`BSD`, `Apache`) y prueba T1 que confirme que un paquete LGPL igual falla (la raíz `GPL` no está en la lista, y `LGPL` no contiene ninguna raíz permitida).
- `--partial-match` con la raíz `BSD` aceptaría "BSL" si un metadato escribiera mal el nombre: no coincide como subcadena, pero el riesgo de un clasificador raro existe — mitigación: T9 revisa la salida completa una vez y la lista prohibida queda como prueba explícita en T1.
- Pregunta abierta PSF-2.0: si el gate decide excepción por paquete, T3 cambia la lista blanca por dos entradas en `licenses-exceptions.txt` — mitigación: el script lee ambas listas de archivos, el cambio es de datos.
- `license-checker` está sin mantenimiento activo — mitigación: es BSD-3-Clause y estable; si falla con npm 11, se reemplaza por `license-checker-rseidelsohn` (BSD-3-Clause) con los mismos parámetros.
- Front condicionado a D1: si el gate no aprueba el front en este repositorio, T2 y T5 salen del alcance.

## Estimación
- Backend: 0 h
- Front: 1 h
- Pruebas: 2,5 h
- DevOps / seguridad: 7,5 h
- **Total: 11 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `bash scripts/ci/check-licenses-api.sh` termina con código 0 sobre el `uv.lock` de `main`
- [ ] `bash scripts/ci/tests/test_licenses.sh` termina con código 0 (las dos verificaciones de rechazo pasan)
- [ ] `cd web && npm run lint && npx tsc --noEmit && npm run licenses` (si hay front)
- [ ] `bash scripts/ci/notice.sh && git diff --exit-code NOTICE` sin cambios
- [ ] El PR de control con `fpdf2` queda en rojo en el paso `licencias-api` (enlace en el PR)
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app --cov-fail-under=80`
