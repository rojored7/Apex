# Sprint 7 · cuaderno (backend y orquestador)

Rama `feat/sprint-07-clases-horario-checkin`, HEAD de partida `8e751eb` (sobre `a2f38ad`, cierre de v0.3.0).

## Planificación

- Impacto: `docs/ddd/blueprints/sprint-07-impacto.md`
- Exploración: `docs/ddd/blueprints/sprint-07-exploracion.md`
- Blueprint: `docs/ddd/blueprints/sprint-07-blueprint.md`
- Diseño de seguridad: `docs/ddd/blueprints/sprint-07-seguridad-diseno.md`
- Plan (aprobado por la orden del usuario del 2026-11-14, S7-D35): `docs/ddd/blueprints/sprint-07-plan.md`
- Críticas del plan: `docs/ddd/blueprints/sprint-07-critica-1.md`, `sprint-07-critica-2.md`

## W0-1 · documentos y decisiones (2026-11-14)

- Decisiones S7-D1 a D35 en `docs/ddd/DECISIONES.md` (bloque «Sprint 7»); migraciones reales `0025` a `0029_memberships_orig_end_date` en `SPRINT-07.md`, `BREAKDOWN.md` y DECISIONES.
- T-DOC en US-154, US-155, US-159, US-160, US-161, US-163 y US-164; `BRECHAS.md` §15; `03_context_map.md` (aristas de S7-D6); `CLAUDE.md` (módulo `classes`, job y CLI de generación, layout `sign/`, 25 cubetas y 24 variables, aristas).
- No hay Rojo ni Verde (documentos).

### Línea base (de `sprint-07-impacto.md` §5)

- Cierre del Sprint 6 (S6-D141, sobre `af23e51`): api 9544 pasan y 100 saltadas; web 3930 de 3930 (2 hilos, 98,37 % de líneas).
- `tests/architecture` en `a2f38ad`: 806 passed en 93,8 s (`db_test` respondió en 5443). Suite completa no corrida (poca memoria); mypy y web se toman del cierre de S6. La línea base completa se toma en W0-4.

### Evidencia

- Gate `bash scripts/workflow/slice-gate.sh architecture`: exit 0, 806 passed en 88,3 s (igual que la línea base; el primer intento sin `TEST_DATABASE_URL` dio 84 errores de entorno, no de documentos).
