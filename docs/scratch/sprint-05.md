# Cuaderno del Sprint 5 (v0.2: OpenBao, avisos de vencimiento, recibos y exportaciones)

Rama `feat/sprint-05-openbao-avisos-recibos` desde `main` `a1ad4cb` (cierre del Sprint 4B, 2026-11-04). Mismo formato que `sprint-04b.md`: un bloque por slice (Rojo, Verde, Revisiones, Evidencia) y al final "Validación V1–V12". Sin credenciales, frases ni rutas de identidades.

## Planificación (2026-11-04)

- Fase 0: `docs/ddd/impacto/sprint-05.md`, veredicto AMARILLO con C1..C10; `validate-impact-analysis.sh --allow-amber` → 0.
- Fase 1: `docs/ddd/blueprints/sprint-05-exploracion.md` (5 bloqueantes de diseño, 18 preguntas) y `sprint-05-blueprint.md` (S5-D1..D48; W0-1..W0-4, B1..B13, F1..F5).
- Decisiones del orquestador sobre las preguntas del arquitecto (Q1..Q10): PDF mínimo propio en `core/pdf.py` (sin `reportlab`/`pillow`; `pypdf` BSD solo en dev); una sola llave Transit `apex-kek`; `apex_owner` NOSUPERUSER en W0-4; sin `data_consent_at` no se avisa por ningún canal (se listan aparte); recibo sin documento; `members_without_consent` calculado; auditoría de exportación con `has_q` y filtros estructurados; `display_name` a v0.3 salvo que quepa sin contrato nuevo; respaldo de `openbao-data` (B13) dentro del sprint; custodia de las 5 llaves de desello 2 titular / 2 operador / 1 copia sellada (paso humano).
- Fase 1.5: `docs/ddd/blueprints/sprint-05-seguridad-diseno.md` (en curso).
