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

## W0-2 · Nginx, redacción del log y job nocturno (2026-11-15)

### Rojo

- `tests/core/test_logging_redact.py` (en el archivo existente): `test_redacta_x_device_token_en_cualquier_mayuscula` y `test_redact_text_recorta_x_device_token_en_texto_libre` (4 casos): 5 failed (la clave no estaba en `SENSITIVE_KEYS` y el texto libre dejaba el valor).
- `scripts/ci/test_nightly_workflow.sh` (nuevo): exit 1, `nightly.yml` no existía.
- `scripts/ci/test_nginx_conf.sh` (bloque «Rojo S8-W0-2»): 1 falla, falta el comentario junto a `location /` que diga que `/tv` pasa por ahí. Las comprobaciones funcionales de `/tv` (200, `no-store`, `no-referrer`, CSP con nonce, log sin consulta) ya pasaban con la configuración vigente (hallazgo 12: no hace falta `location` nuevo) y quedan como guarda.

### Verde

- `infra/nginx/default.conf`: solo el comentario junto a `location /` (sin `location` nuevo).
- `api/src/app/core/logging.py`: `x-device-token` en `SENSITIVE_KEYS` y en la expresión de cabecera de texto libre (`x-(vault|device)-token`).
- `.github/workflows/nightly.yml` (nuevo): `schedule` (07:17 UTC) y `workflow_dispatch`, permisos de lectura, acciones por SHA, job `tv-soak` con un paso que pasa (la spec real llega en F6). `ci.yml` (job `scripts`), `run-gates.sh` y `wave0-gate.sh` corren `test_nightly_workflow.sh`.
- Resultado: `test_logging_redact.py` 49 passed; `test_nginx_conf.sh` 0 fallas; `test_nightly_workflow.sh` 0 fallas; `test_images_pinned.sh` 0 fallas.

### Evidencia

- P-REBUILD 3: `docker buildx build --load --network host --allow network.host -t apex-web:local -f web/Dockerfile .` y `$DC up -d --no-build --force-recreate web` (con `apex-migracion.flag` tomada y soltada); `nginx -t` ok.
- `curl -s -D - -o /dev/null 'http://127.0.0.1:8180/tv?token=prueba-sin-valor'`: 200, `Cache-Control: no-store`, `Referrer-Policy: no-referrer` y CSP con `nonce-` por petición. `$DC logs web --tail 20 | grep -c 'token='`: 0.
- Gate: `wave0-gate.sh S8-W0-2` quedó colgado ~20 min en `test_infra_scripts.sh` (`test_restore_guard.sh`: fallos de `fork` de Cygwin en Windows, `Win32 error 299`), ajeno al slice; se cortó y no se cuenta. Corridos aparte, en verde: `test_nginx_conf.sh` 0 fallas, `test_nightly_workflow.sh` 0 fallas, `test_images_pinned.sh` 0 fallas, `bash -n` de `run-gates.sh` y `wave0-gate.sh`. Sello con `slice-gate.sh core/logging tests/core/test_logging_redact.py` (ruff, mypy y pruebas del módulo).
