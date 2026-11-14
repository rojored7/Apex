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

## W0-2 · migración `0025_s6_hardening` (2026-11-14)

### Consultas previas sobre `apex-db-1` (solo lectura, antes de escribir; api y worker parados)

- `fk_attachments_key_id` (adjuntos con `key_id` sin llave): 0
- `sign_iff_public_key` (`(purpose='sign') <> (public_key IS NOT NULL)`): 0
- `photo_not_sensitive` (foto sensible): 0
- `alembic_version` previa: `0024_crypto_rotation_from_api`. Volcado: `docs/scratch/sprint-07-antes-0025.dump` (2,1 MB, ignorado por git).

### Rojo

- `tests/migrations/test_0025_s6_hardening.py` (nueva), `tests/crypto/test_rotation_no_key_update_lock.py` (nueva), `test_0024` (cadena de head) y `tests/core/test_migrations.py` (ids <= 32).
- Rojo confirmado: 15 failed + 5 errors de 33 (28 sin contar los 5 errores de fixtures) por motivo único: no existía la revisión `0025_s6_hardening` (sin FK, sin CHECK `sign_iff_public_key`/`photo_not_sensitive`, guardas de 0024). Pasaron en rojo los dos de forma (id corto de revisiones y cadena de 0024) porque no dependen de la migración.

### Verde

- `migrations/versions/0025_s6_hardening.py`: consultas previas que abortan con regla y conteo, `SET LOCAL lock_timeout = '5s'`, FK `NOT VALID`+`VALIDATE`, dos CHECK, `guard_keys_update` (regla de `public_key` tras DELETE/TRUNCATE y AFTER) y `guard_jobs_update` (solo `rotate`); `downgrade` con los cuerpos de 0024 como constantes.
- `core/crypto/service.py`: `FOR NO KEY UPDATE` (`with_for_update(key_share=True)`) en `start_rotation`, `finish_rotation` y `_lock_key`. [DECISIÓN DE DISEÑO] `count_rows_by_key` conserva `FOR UPDATE` a propósito: el conteo previo a `retire-key` debe impedir subidas nuevas con esa llave (el `KEY SHARE` de la FK choca con `FOR UPDATE`).
- Modelos: CHECK `sign_iff_public_key` y `photo_not_sensitive` (sin FK, E2). Docstring de `0023`. RUNBOOK §12: consultas previas con su remedio (L-6).
- Regresiones por la FK/CHECK nuevos corregidas en pruebas heredadas (la FK exige llave real): `tests/attachments/_apoyo.py` (`llave_retirada`), `test_attachments_check.py`, `test_init_keys_data_class.py` (nombre y forma del CHECK), `test_0021`, `test_0022`, `test_0023` (llaves reales, FK esperada). Tras corregir: 5.232 passed en la corrida de attachments/cli/crypto/members/core/audit/migrations (11 fallos previos, todos por esto).

### Evidencia

- Gate no sellante `slice-gate.sh crypto tests/crypto/test_rotation_no_key_update_lock.py tests/crypto/test_rotate.py`: exit 0, 841 passed.
- Sello `slice-gate.sh attachments` con las cinco pruebas del plan: exit 0, 1.195 passed.
- P-MIG: `$DC start api` -> healthy, `alembic current` = `0025_s6_hardening (head)`; `$DC start worker` healthy; `downgrade -1` y `upgrade head` sin error, `current` = 0025 (head). `/health`: status ok, migrations ok, crypto ok.
- Esquema en `apex-db-1`: FK `fk_attachments_key_id` validada, `ON DELETE RESTRICT`; `ck_crypto_keys_sign_iff_public_key` y `ck_attachments_photo_not_sensitive` validados; `ck_crypto_keys_sign_public_key` ya no existe. Todos los triggers de `crypto_keys`, `crypto_jobs` y `attachments` con `tgenabled = A` (10 filas).
