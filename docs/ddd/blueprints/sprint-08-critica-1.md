# Crítica 1 del plan del Sprint 8 (plan-critic, 2026-11-15)

Veredicto: RECHAZADO

Dos bloqueantes, tres altos, cinco medios y tres bajos, verificados contra `8b2db15`.

1. BLOQUEANTE · Las cargas en `Decimal` rompen la auditoría: `core/audit.py:179-196` rechaza cualquier `Decimal` (ADR-004; `tests/core/test_audit_serialize.py:68`, `test_audit_chain.py:95`); `wods.wod_movements` (`load_rx_m_kg`, `load_rx_f_kg` numeric) y `results.wod_results` (`load_kg`) son tablas auditadas. Ninguna tabla del repo tiene hoy columnas `numeric`.
2. BLOQUEANTE · «La prueba con un coach real» queda como pendiente humano (S8-D40, §7 punto 3, V9, riesgo 14), contra la orden del usuario.
3. ALTO · S8-D33 (M-3) se contradice: con `tv-fail` comprobado antes de leer la cabecera, 12 fallos de un socio dejan en 429 a la TV válida de la misma IP.
4. ALTO · Los E2E de los slices F (`$DCE2E up -d --force-recreate api web`, P-REBUILD 3) pueden arrancar el api durante el paso 0 de un slice de backend con migración (riesgo de S7-D43).
5. ALTO · Faltan catálogos y conteos fijos: `CON_LIMITE` (`test_error_codes_per_route.py:26-161`), excepción de `/tv/today` en `test_user_limits_catalog.py:274-276`, `CLAVES_SIN_RUTA_TODAVIA` (W0-3 mete `wods-write` y `results-write`; A1 y B1 las sacan), conteos de `test_env_example.py:194-196, 474, 485, 507-508` y `test_ratelimit.py:520, 530`, `MODULES` en `test_audit_module.py:55-67`, `"results.results"` en `test_audited_tables.py:169`.
6. MEDIO · P-ROL: `grants.sql:93-95` y `98-99` (REVOKE por esquema de PUBLIC y de los tres roles) deben nombrar `wods` y `results`; `ESQUEMAS` de `test_db_grants.py:42`; `revoke.sql` no necesita cambios (solo `DROP OWNED`).
7. MEDIO · La parada 1 choca con los curl de evidencia de B1 y C2, los smokes de cierre de wave y los E2E de F: sumarlos como excepciones.
8. MEDIO · `TV_IP_LIMIT` y `TV_TOKEN_LIMIT` tienen cota 1-120; el `sed` de `ci.yml:424` (`=1000`) tumbaría el api: fijar 120 explícito y probarlo en `test_env_example`.
9. MEDIO · El E2E de F1 espera «Fran» tras `seed-benchmarks`, que la CI no siembra (`ci.yml:513-516`).
10. MEDIO · B3: `auth/models.py:80-82` (CHECK `.../checkin$`) no está en la lista; `0038` conserva el nombre `ck_refresh_tokens_kiosk_path_shape` (`test_0031:17,57`).
11. BAJO · Ranking de la TV: posiciones calculadas después de excluir bajas y sin autorización (si no, los huecos delatan), con prueba.
12. BAJO · `location = /tv` con `rewrite ... last` no aplica sus `add_header` (rige `location = /index.html`, `default.conf:137`): probar cabeceras con curl.
13. BAJO · `test_logging_redaction.py` duplicaría `test_logging_redact.py`; orden de limpieza dentro de `wods`; `core/db.APP_SCHEMAS` (:50) sin `classes`, `wods`, `results`; otras conftest con limpieza (`cli/`, `worker/`, `audit/`, `notifications/`, `attachments/`).

## Resolución del orquestador (orden del usuario «no pare hasta terminar»)

- 1: las cargas se guardan como ENTERO en gramos (`*_load_g int`, CHECK ≥ 0), como el dinero en COP; el api las expone en gramos y el front las muestra en kg con hasta dos decimales; ADR-004 no se toca. Prueba de auditoría de un WOD y de un resultado con carga.
- 2: S8-D40 se cierra con evidencia automática y en vivo: E2E de F4 (15 resultados con tiempo medido) y, en V8 Pilar 2, una clase completa por la interfaz real en quiosco (check-in, 15 resultados, corrección, leaderboard en la TV y conteos en la base). Ningún paso humano.
- 3: se valida primero el token (SHA-256 + `compare_digest`, 401 uniforme); si es válido aplica solo `tv` por hash; si no, comprueba y suma `tv-fail` por IP. Prueba «misma IP».
- 4: exclusión explícita entre P-E2E/P-REBUILD de los slices F y el tramo paso 0 → checkpoint de cualquier slice de backend con migración (un archivo de bandera en el scratchpad, como en el Sprint 7).
- 5 a 13: se incorporan tal como propone la crítica.
