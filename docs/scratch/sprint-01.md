# Cuaderno · Sprint 1 · Núcleo de auditoría, bus de criptografía y seguridad

Rama `feat/sprint-01-nucleo-cripto-seguridad`, creada desde `main` el 2026-10-21 tras el
merge local (fast-forward) de `chore/sprint-00-cimientos` (`ca8415f`). El push a GitHub
lo bloquea el clasificador de permisos de la sesión: queda como paso humano.

## Línea base (2026-10-21)

- `git status` limpio en `main` = `ca8415f`.
- api: 106 pruebas en verde, 1 saltada; cobertura 93 % (cierre del Sprint 0).
- web: 75 pruebas en verde; cobertura 100 %.
- Stack de desarrollo arriba: `apex-db-1`, `apex-db_test-1`, `apex-api-1`, `apex-web-1`
  en los puertos 8180/8181/5442/5443 (`.env` local).

## Slices

### S1-W0-1 · Cabeceras de seguridad y CSP con nonce (US-038)

- Rojo: `web/tests/unit/index-html.test.ts` (2 de 5 fallaban: sin `nonce` en `<script>` y `<link>`),
  `web/tests/e2e/csp.spec.ts`, `scripts/smoke/headers.sh`.
- Verde: `vite.config.ts` (`html.cspNonce`, `modulePreload.polyfill=false`),
  `infra/nginx/snippets/{security-headers,proxy-api}.conf`, `default.conf` con CSP exacta,
  `sub_filter` de `__CSP_NONCE__` → `$request_id`, `no-store`, `location /api/v1/tv/` (N-44),
  `web/Dockerfile` copia los snippets; `test_nginx_conf.sh` ampliado (26 comprobaciones);
  `compose-smoke.sh` llama a `headers.sh`.
- Evidencia: `headers.sh` contra Nginx real en 8180: 19 ok, 0 fallas (nonces distintos entre
  peticiones, 413 con 6 MB). Playwright `csp.spec.ts`: 2 ok sobre `vite preview` (interceptando
  como Nginx) y 1 ok + 1 saltada con `CSP_BASE_URL=http://localhost:8180/`. `web-smoke.sh` 5/5.
  `slice-gate.sh web/app tests/unit/index-html.test.ts` verde.
- Desviaciones: no hay script de tema inicial, así que T3 (`theme-init.js`) no aplica. El smoke de
  cabeceras corre dentro del job `images` (vía `compose-smoke.sh`), no en un job `smoke-headers`
  aparte: los nombres de los checks obligatorios no cambian. La prueba del HTML construido corre en
  entorno node y construye con la API de Vite a un directorio temporal.

### S1-B1 · Tabla de auditoría y cadena de hashes (US-015 + T1 de US-027)

- Paso previo: `pg_dump -Fc` de la base de desarrollo antes de `0002` en
  `docs/scratch/sprint-01-antes-0002.dump` (3,6 KB; ignorado por git por `*.dump`).
- Rojo: `tests/crypto/test_digest.py`, `tests/core/test_audit_chain.py`, `test_audit_log_db.py`,
  `test_audit_concurrency.py` sobre stubs con `NotImplementedError`: 20 fallos + 10 errores (la
  tabla no existía). `test_core_import_direction.py` (T11) ya existía desde US-014.
- Verde: `core/crypto/digest.py` (`sha256_hex`, solo `hashlib`), `core/audit.py` (`canonical`
  con la especificación irreversible en el docstring, `chain_hash`, `verify_chain`, `AuditEntry`,
  `append_entry` con `pg_advisory_xact_lock(4_270_002)` y `seq = último + 1`, `record`),
  migración `0002_audit_log` (CHECKs de acción con `download`, hex de 64, espejo; 4 índices;
  `audit.forbid_mutation()` con triggers de fila y de TRUNCATE).
- Evidencia: `slice-gate.sh core/audit` (46 ok, 1 saltada), `slice-gate.sh crypto` (23 ok);
  cobertura 100 % de `audit.py` y `digest.py`; ciclo de Alembic en la base de desarrollo
  (`upgrade head` → `downgrade -1` → `upgrade head`, `current` = `0002_audit_log (head)`);
  `TRUNCATE audit.audit_log` en psql rechazado por `audit.forbid_mutation()`; 10 transacciones
  concurrentes dejan `seq` 1..10 y cadena válida; `grep hashlib audit.py` vacío.
- Ajustes: `test_migrations.py` ahora compara con el head del `ScriptDirectory` y baja hasta
  `base` (antes asumía `0001`). `rows_checked` cuenta hasta la primera ruptura inclusive.
- Seguridad (T13): escritura solo con `insert()` de Core; trigger cubre TRUNCATE; lock `xact`;
  `digest` no toca `crypto_ops`. Los valores en claro de campos cifrados los evita US-016.
