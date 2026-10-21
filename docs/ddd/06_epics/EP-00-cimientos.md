# EP-00 · Cimientos del repositorio

- **Versión del plan:** v0.1 (Tarea 0; partes de la Tarea 10 y de la sección 7 de `05_service_design.md`).
- **Bounded context:** ninguno de negocio. Es el terreno donde viven todos los contextos (`api/`, `web/`, `infra/`, `scripts/`).
- **Estimación relativa:** L.

## Objetivo de negocio

Que el gimnasio tenga, desde el primer día, un proyecto que se levanta con un solo comando y que no deja entrar código defectuoso, inseguro o con licencias prohibidas. Sin este piso, cada épica siguiente se construye sobre arena y el costo de corregir crece en cada versión.

## Actores

- Equipo de desarrollo (Claude Code y quien revise los PR).
- Pipeline de CI (GitHub Actions), actor automático que aprueba o rechaza.
- Operador del servidor del gimnasio (levanta el sistema con Docker Compose).

## Capacidades incluidas

### Repositorio y calidad del backend
- Inicializar git, rama `main` protegida y convención de ramas `feat/`, `fix/`, `chore/` (riesgo 3 de `00b_impact_analysis.md`: hoy no hay repositorio).
- Estructura de carpetas de `CLAUDE.md`: `api/`, `web/`, `infra/`, `docs/adr/`, `scripts/workflow/`.
- `api/pyproject.toml` con `uv`, dependencias de runtime y de desarrollo separadas.
- `ruff` (lint y formato) con `flake8-tidy-imports` y la lista `banned-api` del bus de criptografía: `cryptography`, `oqs`, `hashlib`, `hmac`, `jwt`, `argon2` prohibidos fuera de `core/crypto` y `core/security`.
- `mypy --strict` sobre `src/`; `pytest` con `asyncio_mode=auto`; una prueba trivial en verde.
- `.pre-commit-config.yaml` con ruff y mypy.

### Integración continua
- `.github/workflows/ci.yml`: lint, mypy, pruebas con servicio PostgreSQL 16, `pip-licenses --fail-on` con la lista prohibida (GPL, LGPL, AGPL, BSL, SSPL), chequeo de licencias del front (`license-checker` o equivalente, `BRECHAS.md` sección 7) y build de imágenes.
- Lista de licencias permitidas ampliada con ISC y OFL 1.1 (iconos Lucide y fuentes), según `01_product_discovery.md` sección 6; archivo `NOTICE` inicial.

### Contenedores y proxy (esqueleto)
- `api/Dockerfile` multi-stage con `uv` y usuario no root.
- `infra/compose.yml` con `web`, `api`, `worker` y `db`, con healthchecks; `infra/compose.dev.yml` con hot reload, puertos abiertos y `db_test`.
- `infra/nginx/default.conf`: sirve `web/dist`, proxy de `/api/` a `api:8000`, `client_max_body_size 5m`. Las cabeceras de seguridad y la CSP las endurece EP-03.
- KEK local en un volumen nombrado de Docker, no en una carpeta montada desde Windows (riesgo 4 de `00b_impact_analysis.md`).

### Configuración
- `.env.example` con todas las variables de la Tarea 0: `DATABASE_URL`, `JWT_PRIVATE_KEY_PATH`, `CRYPTO_PROVIDER=local`, `CRYPTO_LOCAL_KEK_PATH`, `TZ_DISPLAY=America/Bogota`, `UPLOADS_DIR=/data/uploads`, `CORS_ORIGINS`.
- `README.md` para levantar el proyecto en 5 minutos.

### Scripts de gate del flujo (`scripts/workflow/`)
- `slice-gate.sh`: lint, mypy y pytest del módulo tocado.
- `checkpoint-commit.sh`: commit de checkpoint por slice, sin push.
- `run-gates.sh`: suite completa y cobertura al cerrar una wave.
- `validate-impact-analysis.sh`: verifica que exista el análisis de impacto con veredicto antes de empezar.
- Hoy ninguno existe (`00b_impact_analysis.md`, "Gate verificado manualmente"); a partir de esta épica dejan de verificarse a mano.

### Esqueleto del front (`web/`)
- Proyecto Vite + React 19 + TypeScript estricto, ESLint, Vitest y Testing Library; Playwright instalado, todavía sin flujos.
- `web/src/core/styles/tokens.css` copiado de `docs/design/tokens.css`, con una regla de lint o de revisión que impide colores y fuentes literales en componentes.
- Fuentes locales en `web/public/fonts/` (Michroma, Titillium Web) y logos en `web/public/brand/` (supuesto S3).
- Componentes compartidos base en `web/src/shared/ui/`: `Button`, `Field` y `StatusTag`, con estados de foco, hover y deshabilitado, controles de 44 px y prueba de componente. El resto del kit lo construye EP-06.
- `web/Dockerfile`, o build en CI copiado a la imagen de Nginx.

## Fuera de alcance

- Lógica de negocio de cualquier módulo.
- Endurecimiento de cabeceras, CSP y CORS (EP-03).
- Servicio `backup`, `deploy.sh` y datos de demostración (EP-13).
- Layouts, navegación y el resto de componentes compartidos (EP-06).
- OpenBao (EP-15) y Caddy (EP-20).

## Criterios de éxito medibles

- `uv run ruff check .`, `uv run mypy src` y `uv run pytest` en verde en una máquina limpia (criterio de salida de la Tarea 0).
- `docker compose -f infra/compose.yml -f infra/compose.dev.yml up` deja `db` sano y `api` respondiendo `/health` en menos de 5 minutos desde un clon limpio.
- Un PR de control que agrega una dependencia GPL o LGPL falla en CI.
- Un archivo fuera de `core/crypto` que importa `hashlib` falla en `ruff`.
- Los cuatro scripts de `scripts/workflow/` existen, son ejecutables y devuelven un código distinto de 0 cuando el gate falla.
- `npm run build` y `npm test` del front en verde, con `Button`, `Field` y `StatusTag` cubiertos.

## Dependencias

- Ninguna. Es la raíz del grafo.

## Riesgos

- Docker en Windows con WSL2: los permisos 600 y los volúmenes se comportan distinto en NTFS.
- El supuesto S1 (el front se construye en este repo) contradice el párrafo "Alcance" de `CLAUDE.md`. Si el gate humano no lo aprueba, la parte `web/` de esta épica sale del alcance.
- Que el chequeo de licencias del front no reconozca ISC u OFL 1.1 y produzca rechazos falsos.

## Pantallas del diseño que habilita

- Ninguna directamente. Habilita la construcción de todas.
