# Crítica 2 del plan del Sprint 8 (plan-critic, 2026-11-15)

Veredicto: APROBADO CON OBSERVACIONES

Los 13 hallazgos de la crítica 1 quedaron resueltos. Seis observaciones (cuatro medias, dos bajas), cada una de una línea:

1. MEDIO · Gramos: C2 (línea 249) no renombra las claves de `TvBoard` del blueprint S8-D18 (`load_rx_m_kg`, `load_rx_f_kg`, `score.load_kg`) → `load_rx_m_g`, `load_rx_f_g`, `load_g` enteros; F4 suma `ScoreForm` «102,5 kg se envía como 102500»; F6 suma `TvWod` y `TvLeaderboard` con `formatScore`.
2. MEDIO · `CLAVES_SIN_RUTA_TODAVIA`: `test_env_example.py:507-508` y `test_user_limits_catalog.py:462` son afirmaciones `== frozenset()`; la línea 485 es `len(USER_LIMITS) == 25`. W0-3 → `{"wods-write","results-write"}`, A1 → `{"results-write"}`, B1 → `frozenset()`; escribirlo en P-CAT 2 (el grep `== 25|== 24` no las encuentra).
3. MEDIO · Banderas de exclusión: deben vivir en una ruta absoluta común a todas las sesiones y worktrees; todo `up`, `start` o `restart` del api o de `web` (P-REBUILD 4, W0-3, A4, B5, C2) toma `apex-migracion.flag`; bandera huérfana de más de N minutos con su dueño muerto se anota en el cuaderno y se borra.
4. BAJO · S8-D1 (i) dice «un solo cambio de `ci.yml`» y A2 lo vuelve a tocar (`seed-benchmarks`).
5. BAJO · Topes de carga distintos (CHECK 0..1.000.000 g frente a 0..999,99 kg).
6. BAJO · S8-D33 no dice el `KeyKind` de la cubeta `tv` por hash (`ratelimit.py:59`): declarar `account`.

## Resolución del orquestador

Se aplican las seis tal como propone la crítica. Las banderas viven en `C:/Users/PC/Proyectos/Apex/.git/apex-locks/` (fuera del árbol versionado y común a todos los worktrees, que comparten `.git`), con N = 90 minutos. El tope de carga único es 0..1.000.000 g (0 a 1.000 kg) en el CHECK, Pydantic y Zod. Con esas ediciones el plan queda aprobado para ejecutarse por la orden del usuario del 2026-11-14.
