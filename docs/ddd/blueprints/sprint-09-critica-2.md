# Crítica 2 del plan del Sprint 9 (plan-critic, 2026-11-16)

Veredicto: APROBADO CON OBSERVACIONES

Los 10 hallazgos de la crítica 1 quedaron resueltos con pasos y pruebas (1 en W0-3; 2 por S9-D42 con `translate_busy`, `core/db.py:225-258`; 3 con el orden de `wods/benchmarks.py:92-98`; 4 con `_invalidate` por ORM y `test_invalidation_audit.py`; 5 con `whatsapp_ready` y las cinco condiciones de `notifications/service.py:184-196`; 6, 7 y 10; 8 con reserva; 9 con la condición de S9-D41). Verificado además: alias 15 contra `scripts/workflow/slice-gate.sh:96-140`; `dbsetup` de V2 (`infra/db/apply.sh:43`, `core/config_non_api.py:39-41`); nombres de función de `wods/catalog.py`, `results/reads.py`, `results/leaderboard.py` y `results/rules.py:69`.

## Observaciones

1. [MEDIO] El conteo de la alerta no llega a Telegram: `core/alerts_telegram.py:144-156` manda un código sin plantilla sin contexto. Corrección: W0-3 suma `core/alerts_telegram.py` (tres entradas en `_DINAMICOS`) y su prueba de `render_message`.
2. [MEDIO] El rollback de V3 no se puede ejecutar como está: `infra/compose.yml:53,108,212,281` fijan `image: apex-api:local` y el api corre como `apex_api` sin DDL. Corrección: override en el auxiliar y `downgrade` con `run --rm migrate alembic downgrade ...`; lo mismo en §6.2 y `actualizar.md`.
3. [MEDIO] X1 no dice cómo entra `can_whatsapp`: `notifications/queries.py:54` arma `NotificationOut` con `getattr` por campo; `_whatsapp_config` vive en `service.py:218` y `queries.py` no puede importar `service`; `skip` (`service.py:237`) también devuelve `NotificationOut`. Corrección: excluir el campo en esa línea, inyectar la configuración y probar `get`, `list_for_member` y `skip`.
4. [BAJO] La prueba de «base ocupada» de B3 no dice cómo conoce el `result_id`: handler de prueba suscrito a `WodResultRecorded` (`results/record.py:203-205`) que inserta sin confirmar desde otra conexión.
5. [BAJO] S9-D41: la autorización del push debe constar en la conversación del orquestador.
