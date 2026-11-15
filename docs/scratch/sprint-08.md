# Sprint 8 · cuaderno (backend y orquestador)

Rama `feat/sprint-08-wods-resultados-tv`, HEAD de partida `4859031` (sobre `8b2db15`, cierre de v0.4.0 y `main`). Head de Alembic de partida: `0031_refresh_kiosk_path`.

## Planificación

- Impacto: `docs/ddd/blueprints/sprint-08-impacto.md`
- Exploración: `docs/ddd/blueprints/sprint-08-exploracion.md`
- Blueprint: `docs/ddd/blueprints/sprint-08-blueprint.md`
- Diseño de seguridad: `docs/ddd/blueprints/sprint-08-seguridad-diseno.md`
- Plan (aprobado por la orden del usuario del 2026-11-14, S8-D43): `docs/ddd/blueprints/sprint-08-plan.md`
- Críticas del plan: `docs/ddd/blueprints/sprint-08-critica-1.md`, `sprint-08-critica-2.md`

## W0-1 · documentos y decisiones (2026-11-15)

- Decisiones S8-D1 a D43 en `docs/ddd/DECISIONES.md` (bloque «Sprint 8»); migraciones reales `0032` a `0038_kiosk_results_path` en `SPRINT-08.md`, `BREAKDOWN.md` (EP-22) y DECISIONES.
- T-DOC en US-165, US-166, US-168, US-169, US-170, US-171, US-173, US-174, US-175, US-176 y US-177; `BRECHAS.md` (§4: validar resultados a EP-25; §16 nueva con los DESIGN-GAP de S8-D5, D6, D7, D8, D19 y D20); `03_context_map.md` (aristas de S8-D4); `CLAUDE.md` (módulos `wods`, `results` y `tv`, `seed-benchmarks`, 12 rutas de quiosco, 27 cubetas y 26 variables, `TV_IP_LIMIT` y `TV_TOKEN_LIMIT`, `0038`, `nightly.yml`).
- No hay Rojo ni Verde (documentos).

### Línea base de partida (de `sprint-08-impacto.md` §5)

- Cierre del Sprint 7 (S7-D43, sobre `e38b65b`): api 10 375 pasan y 103 omitidas, cobertura 95,39 %; web 4 261 pasan, 98,19 % de líneas (2 hilos).
- `tests/architecture` en `8b2db15`: 847 passed en 113,3 s (`db_test` en 5443).

### Evidencia

- Gate `bash scripts/workflow/slice-gate.sh architecture`: exit 0, 847 passed en 110,9 s (igual que la línea base).
