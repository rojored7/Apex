# Cuaderno · Sprint 4A · Front (worktree)

Worktree `.claude/worktrees/sprint-04a-front`, rama `feat/sprint-04a-front`, creada desde `feat/sprint-04a-worker-auditoria-tablero` tras el checkpoint de S4A-B4 (S4A-D62). Orden: F1 (tras B4), F2 (tras B5), F4 (tras B7), F3 (tras B8); se fusiona en V1.

Reglas del worktree:
- `SLICE_BASE` fijado a la base del worktree; `git rebase feat/sprint-04a-worker-auditoria-tablero` antes de cada slice.
- El front no edita `docs/scratch/sprint-04a.md`, `docs/ddd/DECISIONES.md`, `CLAUDE.md`, `docs/BRECHAS.md`, `docs/openapi.json` ni `web/src/core/api/types.ts`; sí edita `docs/design/ROUTES.md` y este cuaderno.
- Cada slice deja su bloque Rojo (conteo y motivo de cada prueba en rojo) y Verde (conteo en verde y desviaciones).
