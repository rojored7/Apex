# 00b · Análisis de impacto previo (Fase 0)

Fecha: 21 de octubre de 2026.
Alcance: `full-project` (greenfield).
Anclaje: sin repositorio git. El directorio `C:\Users\PC\Proyectos\Apex` no está inicializado; no hay HEAD al que anclar. Se declara **greenfield sin repo**.

## Veredicto: AMARILLO

Se puede avanzar a Fase 1 con `--allow-amber`. El amarillo viene de cinco decisiones de producto todavía abiertas (D1 a D5 de `docs/BRECHAS.md`) y de la ausencia de scripts de gate. Ninguna es ROJA: no hay código que romper, no hay datos que perder, no hay migraciones aplicadas.

## Gate verificado manualmente

`validate-impact-analysis.sh` no existe en `scripts/workflow/` ni en `plataforma/scripts/workflow/`. Condición verificada a mano:
- Este archivo existe en `docs/ddd/00b_impact_analysis.md` (el flujo lo nombra `outputs/00b_impact_analysis.md`; en este repo los artefactos del pipeline viven en `docs/ddd/`).
- Declara greenfield sin repo.
- Tiene veredicto (AMARILLO).

Los otros tres scripts (`slice-gate.sh`, `checkpoint-commit.sh`, `run-gates.sh`) tampoco existen. En Fase 4 se verificarán a mano: lint + mypy + pytest por slice, commit manual sin push, suite completa y cobertura al cerrar cada wave. Se crearán en la Tarea 0 del plan para que los sprints siguientes los usen.

## Inventario del terreno

### Estado del directorio destino
- `CLAUDE.md` (152 líneas): reglas no negociables del proyecto, con la sección "Front: diseño aprobado".
- `README.md`: índice del repositorio.
- `docs/PLAN.md`: plan backend por versiones (v0.1 a v1.0).
- `docs/BRECHAS.md`: 8 secciones de diferencias entre diseño y plan.
- `docs/design/`: 37 pantallas (73 HTML), `DESIGN.md`, `ROUTES.md`, `SCREENS-INDEX.md`, `tokens.css`, `tokens.json`, 3 logos, `prototipo.html`.
- `_entregas/`: zip original de la entrega de diseño.
- Sin `api/`, `web/`, `infra/`, `tests/`, `.github/`, `.env.example`, `pyproject.toml`, `package.json`.

### Convenciones instaladas (globales, `~/.claude/rules/`)
- `common/`: coding-style (inmutabilidad, KISS, DRY, YAGNI, archivos de 200 a 400 líneas, máximo 800), testing (80 % de cobertura, TDD, AAA), security (sin secretos, validación de entrada, rate limit), git-workflow (Conventional Commits, sin atribución), code-review, development-workflow (research → plan → TDD → review → verify-delivery), patterns, performance, hooks, agents, pre-modification (análisis de dependencias antes de editar).
- `python/`: PEP 8, type hints, pytest, Protocol para duck typing, gestión de secretos.
- `typescript/`: estilo, patrones, testing, seguridad.
- `web/`: diseño anti-plantilla, tokens CSS, semántica HTML, rendimiento (Core Web Vitals), testing visual con Playwright, CSP.
- `~/.claude/stacks/`: no existe.

### Convenciones del proyecto (`CLAUDE.md`)
- Stack fijo: Python 3.12, FastAPI, SQLAlchemy 2 async, Alembic, Pydantic v2, PostgreSQL 16, Docker Compose, Nginx, OpenBao desde v0.2, React 19 + Vite en `web/`.
- Módulos con `router.py`, `schemas.py`, `models.py`, `service.py`; comunicación entre módulos solo por `service.py` o por eventos en `core/events.py`.
- Bus de criptografía único en `core/crypto/`; lint que prohíbe importar `cryptography`, `oqs`, `hashlib`, `hmac`, `jwt`, `argon2` fuera de `core/crypto` y `core/security`.
- Dinero en COP entero; fechas en UTC; UUID + `created_at`/`updated_at`/`created_by` en toda tabla; borrado lógico; pagos inmutables; listas paginadas; una migración por cambio.
- Licencias: MIT, BSD, Apache 2.0, PostgreSQL; MPL-2.0 sin modificar. Prohibidas GPL, LGPL, AGPL, BSL, SSPL.
- Calidad: ruff, mypy --strict, pytest con PostgreSQL en Docker, pre-commit, CI.

### Baseline
- Tests: ninguno (0 pasan, 0 fallan).
- Type check: no aplicable (sin código).
- Build: no aplicable.
- Docker: no verificado todavía; se verifica en Wave 0 del Sprint 0 (puertos libres, Docker Engine disponible en WSL2).

### Agentes del flujo disponibles en esta máquina
El flujo nombra agentes numerados (impact-prevalidator, 01-product-discovery, …, 21-security-review) que no existen en `~/.claude/agents/`. Equivalentes que sí existen y se usarán:
- Fases 1 y 2 (descubrimiento, dominio, contextos, arquitectura, diseño de servicios): el orquestador los escribe directamente a partir de la documentación existente, con `architect` y `senior-solution-architect` como apoyo si hace falta.
- Fase 3: `ddd-epic-architect` (épicas), `ddd-backlog-architect` (historias), `tech-lead-story-planner` (desglose técnico), `sprint-planning-orchestrator` (sprints), `plan-critic` (crítica del plan).
- Fases 4 a 6: `backend-implementor`, `backend-qa-executor`, `frontend-ux-engineer`, `frontend-qa-automation`, `integration-qa-engineer`, `e2e-qa-automation-engineer`, `smoke-test-generator`, `security-reviewer`, `devops-wsl2-docker`, `sprint-release-validator`.

## Riesgos identificados antes de empezar

1. **Decisiones abiertas D1 a D5** (`docs/BRECHAS.md` sección 1). Se toman supuestos recomendados en Fase 1 y se presentan en el gate humano único.
2. **Conflicto de alcance del front**: `CLAUDE.md` dice que Claude Code no construye el front; el pipeline incluye waves de frontend. Supuesto de trabajo: el front sí se construye en `web/` dentro de este flujo (opción b de D1); el párrafo de Alcance se reescribe si el usuario lo aprueba en el gate.
3. **Sin git**: los checkpoints por slice necesitan repositorio. Se inicializa en el Sprint 0, Wave 0, antes de cualquier código.
4. **Docker en Windows/WSL2**: Compose, volúmenes y permisos 600 del archivo KEK se comportan distinto en NTFS. La KEK local debe vivir en un volumen nombrado de Docker, no en una carpeta montada desde Windows.
5. **liboqs-python** está en el stack fijo pero solo se usa en v1.0 (ML-KEM). No se instala antes; cada dependencia entra en la versión que la necesita.
6. **Dependencia de internet** para Google Fonts en el front: `DESIGN.md` ya prevé fuentes locales.
