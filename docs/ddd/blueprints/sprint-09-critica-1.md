# Crítica 1 del plan del Sprint 9 (plan-critic, 2026-11-16)

Veredicto: RECHAZADO

Motivo: los dos HIGH y los seis MEDIUM están como pasos explícitos (sección 8 del plan), pero H-2 y M-5 se apoyan en dos supuestos falsos sobre el código real.

## Hallazgos críticos (bloquean)

1. [CRÍTICO] `alert()` rechaza las claves que el plan le pasa (H-2, M-5, M-6). `api/src/app/core/alerts.py:23-41` (`ALERT_CONTEXT_KEYS` sin `user_id`, `count` ni ids) y `:85-87` (`ValueError` antes de los sinks); `tests/core/test_alerts.py:78` fija el conjunto. Efecto: el `reveal` 101 da 500 y, en el fallo blando, el `ValueError` revierte `PUT /results`. Corrección: W0-3 suma `core/alerts.py` y su prueba con claves enteras nuevas en `COUNT_KEYS`; la alerta de derivación va sin ids (solo `error_type`; los ids al log, regla de `alerts.py:7`); `alert` en su propio `try`; Rojo en B3: una alerta que falla no revierte el resultado.
2. [CRÍTICO] `DatabaseBusy` nunca se lanza dentro de un service (S9-D30): la crea `get_session` al salir con `translate_busy` (`core/db.py:253-258`); dentro llega un `DBAPIError` con SQLSTATE de `BUSY_SQLSTATES` (`db.py:182`). Corrección: si `translate_busy(error) is not None`, se relanza el original; el Rojo de B3 y B5 fuerza un `lock_timeout` real dentro del savepoint y espera 503; `derive-records` (B6) define su propio trato.
3. [ALTO] El patrón del savepoint no está escrito como paso (`wods/benchmarks.py:92-98`: `begin_nested()` vacía lo pendiente antes de abrir). Corrección en B3 y B5: `_invalidate` hace `flush` antes del `begin_nested` (falla cerrado); `add` y `flush` del récord derivado o repuesto dentro del bloque; Rojo: tras el fallo blando la sesión sigue usable, la auditoría del resultado persiste y `verify-audit` pasa.
4. [ALTO] La invalidación de un récord derivado puede quedar sin auditoría: un `UPDATE` de Core no pasa por `after_flush` (`core/audit.py:503`). Corrección: `_invalidate` por ORM o auditoría explícita; Rojo: fila `update` de `athletes.personal_records` con el actor, por corrección y por anulación.

## Observaciones (no bloquean)

5. [MEDIO] X1 afirma una condición que `wa_link` no tiene (`notifications/service.py:184-196`, `members/contact.py:109`): el Rojo enumera las cinco condiciones reales (estado no `skipped`, canal `whatsapp_link`, `channels.whatsapp.enabled`, autorización y teléfono).
6. [MEDIO] A1: la fábrica pone `voided_*` al nacer y la guarda lo prohíbe; la fábrica hace INSERT y luego UPDATE por SQL, y necesita una fila real de llave `athlete.metric`.
7. [MEDIO] `tests/core/crypto/` no existe: `test_boot_data_classes.py` va en `tests/crypto/`.
8. [MEDIO] Rollback 6.2 promete en V3 una comprobación que no está (`core/crypto/keyring.py:156` carga todas las filas): paso explícito en V3 con la imagen v0.5.0 tras el `downgrade`, o declararlo no probado.
9. [BAJO] S9-D38: `git credential fill` con `GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never`; el push de V5 y V9 contradice `CLAUDE.md` («el push lo hace una persona»): decisión S9 y corrección de `CLAUDE.md` en W0-1.
10. [BAJO] Ciclo de slice: P-MIG 1 a 4 antes del gate; 5 a 7 en el paso 7.

## Supuestos verificados

`MODULES` (`main.py:66-81`); `CONSENT_MISSING_CONDITION` en `members/rules.py:394`; `emit` propaga (`core/events.py:72`); `lock_member` antes de emitir (`results/void.py:53`, `record.py:105`); `SELECT` de `apex_api`/`apex_worker` sobre `crypto.crypto_keys` (`grants.sql:181,211`); limpieza con `ENABLE ALWAYS` (`tests/conftest.py:324`); `PENDING_AUDITED` (`test_audited_tables.py:84,176`); `nightly.yml:18` con `workflow_dispatch`; scripts y pruebas citados existen. No revisado: argumentos de `slice-gate.sh`, `dbsetup` de V2, nombres de función en `wods/catalog.py` y `results/reads.py`.
