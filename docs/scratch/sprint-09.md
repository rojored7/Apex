# Sprint 9 · cuaderno (backend y orquestador)

Rama `feat/sprint-09-perfil-atleta`, HEAD de partida `b8c9255` (sobre `cd0cc0b`, cierre de v0.5.0). Head de Alembic de partida: `0041_results_session_index`.

## Planificación

- Impacto: `docs/ddd/blueprints/sprint-09-impacto.md`
- Exploración: `docs/ddd/blueprints/sprint-09-exploracion.md`
- Blueprint: `docs/ddd/blueprints/sprint-09-blueprint.md`
- Diseño de seguridad: `docs/ddd/blueprints/sprint-09-seguridad-diseno.md`
- Plan (aprobado): `docs/ddd/blueprints/sprint-09-plan.md` (la sección 10 manda)
- Críticas del plan: `docs/ddd/blueprints/sprint-09-critica-1.md`, `sprint-09-critica-2.md`

## W0-1 · documentos y decisiones (2026-11-15)

- Decisiones S9-D1 a D42 en `docs/ddd/DECISIONES.md` (bloque «Sprint 9»), con la confirmación de S9-D41 (el usuario ordenó el 2026-11-15 el push del orquestador).
- Migraciones reales `0042_athletes_body_metrics` y `0043_athletes_personal_records` en `SPRINT-09.md`, `BREAKDOWN.md` (EP-24) y DECISIONES.
- T-DOC en US-178 a US-184; `02_domain_model.md` §2.9, tabla de eventos y de clases de dato; `03_context_map.md` (aristas de S9-D20 y puerto `RecordsProbe`); `05_service_design.md`; `BRECHAS.md` (fila de `benchmark_id` y §17 nueva); `ROUTES.md` (pestaña `/atleta` y rutas reales); `CLAUDE.md` (módulo `athletes` y privados, reglas 1 y 2 bis, bus 9, 28 cubetas y 27 variables, `derive-records`, `0042` y `0043`, frase del push de S9-D41).
- Los conteos de cubetas y variables de `CLAUDE.md` (28 y 27) los fija el código hasta W0-2.
- No hay Rojo ni Verde (documentos).

### Evidencia

- Gate `bash scripts/workflow/slice-gate.sh architecture` (con `TEST_DATABASE_URL` exportada; sin ella el gate da 90 errores de fixture, no de documentos): 885 passed en 246,9 s, exit 0.
- Desviaciones: ninguna prueba de documentos falló; la prueba de cubetas y variables sigue fijada por el código (26/27 hasta W0-2).

## W0-2 · cubeta `athletes-write`, variables y línea base (2026-11-15)

### Línea base (antes del Verde; con el Rojo del slice ya en el árbol)

- Suite completa del api, un solo `pytest -m "not perf"`: 10.999 pasan, 103 saltan, 47 deseleccionadas, **13 fallan** en 2.974,5 s. Las 13 son exactamente las del Rojo de este slice (conteos 28/27, `athletes-write`, `USER_ATHLETES_WRITE_LIMIT_PER_MIN`); ninguna otra.
- Saltos (103): 34 por `cmd.exe` sin entorno para el `age` falso (CI/Linux), 23 por OpenBao real (contenedor Linux y CI), 8 por enlaces simbólicos sin privilegios, 6 por modo POSIX en NTFS, 5 por `age` real y pty solo en Linux, resto del mismo tipo (Linux/CI).
- `mypy src`: Success, 0 errores en 279 archivos.
- Vitest (`--pool=forks --maxWorkers=2`): 261 archivos y 4.537 pruebas pasan, 0 fallan (355 s). `stack` y `preview` no se corren aquí (Playwright, P-E2E).

### Rojo

- Archivos: `tests/core/test_ratelimit.py`, `tests/core/test_env_example.py`, `tests/core/test_config.py`, `tests/architecture/test_user_limits_catalog.py` (`athletes-write` en `CLAVES_SIN_RUTA_TODAVIA`, 28 cubetas, 27 variables, `ci.yml` sube las 27).
- `grep "== 27|== 26|27 cubetas|26 variables"` en `api/tests`: migrados todos los de cubetas (los demás `== 26/25` son longitudes de listas ajenas).
- Medido: 4 archivos, **13 failed, 347 passed**; motivo: `KeyError 'athletes-write'`, `AttributeError USER_ATHLETES_WRITE_LIMIT_PER_MIN`, `27 == 28`, `.env.example` y `ci.yml` sin la variable.

### Verde

- `core/config.py` (`USER_ATHLETES_WRITE_LIMIT_PER_MIN`, 30, `gt=0`), `core/ratelimit.py` (cubeta y `user_limits_from`), `.env.example`, `infra/compose.yml` (api), `ci.yml` (`sed` y regex del conteo: 27).
- Mismos 4 archivos: 360 passed.
