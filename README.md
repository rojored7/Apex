# APEX

Sistema web para administrar un gimnasio de CrossFit en Colombia: socios, planes, membresías, pagos, vencimientos, avisos, clases, WODs, resultados y perfil del atleta. Repositorio privado.

Estado al 21 de octubre de 2026: el plan de trabajo (`docs/ddd/`) está aprobado y el Sprint 0 (cimientos) está en curso en la rama `chore/sprint-00-cimientos`. El arranque en cinco minutos del stack se escribe al cerrar ese sprint (US-007).

## Qué hay en el repositorio y en qué orden leerlo

1. `CLAUDE.md`. Reglas no negociables: stack, estructura de carpetas, módulos, datos, bus de criptografía, seguridad, licencias, calidad. Incluye al final la sección "Front: diseño aprobado". Manda sobre todo lo demás, salvo donde contradiga al plan aprobado en el gate (entonces se corrige).
2. `docs/ddd/`. El plan de trabajo aprobado: análisis de impacto (`00b`), descubrimiento (`01`), modelo de dominio (`02`), mapa de contextos (`03`), arquitectura (`04`), diseño de servicios y contrato HTTP (`05`), épicas (`06_epics/`), historias (`07_user_stories/`), desglose técnico (`08_implementation_breakdown/`), sprints (`09_sprint_plan/`), decisiones (`DECISIONES.md`) y el paquete del gate (`GATE.md`).
3. `docs/PLAN.md`. Plan original del backend por versiones; referencia histórica. Donde se contradiga con `docs/ddd/`, manda `docs/ddd/`.
4. `docs/design/`. Diseño aprobado del front, fuente de verdad para quien lo construya:
   - `DESIGN.md`: guía de colores, tipografía, temas, componentes compartidos y reglas.
   - `ROUTES.md`: cada ruta de React Router con su pantalla, el rol que la ve y los endpoints que consume.
   - `SCREENS-INDEX.md`: índice de las 37 pantallas agrupadas de la A a la J.
   - `screens/`: 73 archivos HTML (36 pantallas en claro y oscuro, más la TV solo en oscuro).
   - `prototipo.html`: las 37 pantallas en una sola página navegable con interruptor de tema. Pesa 3,1 MB.
   - `tokens.css` y `tokens.json`: variables de diseño. El front importa `tokens.css` una vez y no usa colores literales.
   - `assets/logo/`: wordmark blanco, wordmark negro e isotipo.
5. `docs/BRECHAS.md`. Análisis cruzado entre el diseño y el plan del backend, con cada brecha marcada como resuelta y la decisión que la cierra.
6. `docs/scratch/`. Cuadernos de trabajo por sprint (línea base del entorno, evidencia de gates manuales, desviaciones).
7. `_entregas/`. El material original tal como llegó. Se conserva como respaldo; no se usa ni se edita.

## Estructura

- `api/`: backend FastAPI (`src/app/`), migraciones Alembic, pruebas (`tests/`, con `tests/architecture/` que corre en todos los gates). Gestionado con `uv`.
- `web/`: front React 19 + TypeScript + Vite; build estático servido por Nginx.
- `infra/`: Compose, Nginx, backup y OpenBao (desde v0.2).
- `scripts/workflow/`: gates del flujo (`slice-gate.sh`, `checkpoint-commit.sh`, `run-gates.sh`, `validate-impact-analysis.sh`). `scripts/ci/`: smoke de Compose, prueba de imagen y licencias.
- `docs/adr/`: registros de decisiones de arquitectura.

## Cómo contribuir

Ramas, commits, flujo por slice, herramientas locales y licencias: `CONTRIBUTING.md`.

```
cd api && uv sync
uv run ruff check . && uv run ruff format --check . && uv run mypy src && uv run pytest
```

## Cómo revisar el diseño

Abrir `docs/design/prototipo.html` en el navegador para recorrer todas las pantallas, o abrir una pantalla suelta como `docs/design/screens/Inicio.html` y navegar por los enlaces. Las fuentes se cargan de Google Fonts, así que hace falta internet para verlas con la tipografía correcta.
