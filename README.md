# APEX

Sistema web para administrar un gimnasio de CrossFit en Colombia: socios, planes, membresías, pagos, vencimientos, avisos, clases, WODs, resultados y perfil del atleta. Repositorio privado.

Estado al 20 de octubre de 2026: fase de documentación. No hay código, ni repositorio git, ni infraestructura. Todo lo que existe es el plan y el diseño.

## Qué hay en el repositorio y en qué orden leerlo

1. `CLAUDE.md`. Reglas no negociables: stack, estructura de carpetas, módulos, datos, bus de criptografía, seguridad, licencias, calidad. Incluye al final la sección "Front: diseño aprobado". Manda sobre todo lo demás.
2. `docs/PLAN.md`. Plan de implementación del backend y la infraestructura, por versiones: v0.1 (13 tareas: base, socios, planes, membresías, pagos, cifrado, auditoría, Docker, worker, docs), v0.2 avisos y OpenBao, v0.3 auditoría firmada y adjuntos, v0.4 clases, v0.5 WODs y resultados, v0.6 atleta, v1.0 portal del socio.
3. `docs/design/`. Diseño aprobado del front, fuente de verdad para quien lo construya:
   - `DESIGN.md`: guía de colores, tipografía, temas, componentes compartidos y reglas.
   - `ROUTES.md`: cada ruta de React Router con su pantalla, el rol que la ve y los endpoints que consume.
   - `SCREENS-INDEX.md`: índice de las 37 pantallas agrupadas de la A a la J.
   - `screens/`: 73 archivos HTML (36 pantallas en claro y oscuro, más la TV solo en oscuro). Los enlaces entre pantallas funcionan en el navegador.
   - `prototipo.html`: las 37 pantallas en una sola página navegable con interruptor de tema. Pesa 3,1 MB.
   - `tokens.css` y `tokens.json`: variables de diseño. El front importa `tokens.css` una vez y no usa colores literales.
   - `assets/logo/`: wordmark blanco, wordmark negro e isotipo.
4. `docs/BRECHAS.md`. Análisis cruzado entre el diseño y el plan del backend: decisiones que bloquean, módulos y endpoints que faltan, datos que el modelo no tiene, nombres de rutas distintos, permisos por declarar, trazabilidad pantalla a versión, y licencias por añadir.
5. `_entregas/`. El material original tal como llegó (zip de la entrega de diseño y sus instrucciones). Se conserva como respaldo; no se usa ni se edita.

## Cómo revisar el diseño

Abrir `docs/design/prototipo.html` en el navegador para recorrer todas las pantallas, o abrir una pantalla suelta como `docs/design/screens/Inicio.html` y navegar por los enlaces. Las fuentes se cargan de Google Fonts, así que hace falta internet para verlas con la tipografía correcta.

## Estructura destino del código

La define `CLAUDE.md`. En resumen: `api/` (FastAPI, un paquete por módulo, migraciones Alembic, worker con APScheduler), `web/` (React 19 + TypeScript + Vite, build estático servido por Nginx), `infra/` (Compose, Nginx, backup, OpenBao), `docs/` (plan, diseño, ADRs, OpenAPI).

## Próximos pasos

1. Resolver las cinco decisiones de la sección 1 de `docs/BRECHAS.md` y actualizar `CLAUDE.md`, `docs/PLAN.md` o `docs/design/` según corresponda.
2. Inicializar el repositorio git con rama `main` y un `.gitignore` (Python, Node, `.env`, `/data`).
3. Ejecutar la Tarea 0 de `docs/PLAN.md` (arranque del repositorio: `uv`, `ruff`, `mypy`, `pytest`, pre-commit, CI, `.env.example`).
