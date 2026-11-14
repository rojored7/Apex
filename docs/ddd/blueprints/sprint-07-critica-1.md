# Crítica 1 del plan del Sprint 7 (plan-critic, 2026-11-14)

Veredicto: RECHAZADO

Tres bloqueantes verificados en el código, dos altos, tres medios y cuatro bajos. Todas las HIGH y MEDIUM de la revisión de seguridad tienen paso explícito.

1. BLOQUEANTE · `prod-smoke` sin `down -v` muere en la segunda corrida (`scripts/ci/prod-smoke.sh:107-115`, `bajar()` 91-96 solo baja con `CI` o `SMOKE_DOWN=1`; el guion ya hace `docker volume rm "$PROJECT-flat-keys"` en la línea 288). En S6 se bajó `apex-smoke` con `down -v` en cada corrida (`docs/scratch/sprint-06.md:169,174,246,442`). Corrección: `SMOKE_DOWN=1` solo para `apex-smoke` y excepción del volumen `apex-smoke-flat-keys`.
2. BLOQUEANTE · `deploy.sh` de v0.3 corre sus preverificaciones antes del checkout (`infra/deploy.sh:146`, checkout 298) y exige `*/custody/*` en `CRYPTO_LOCAL_SIGNING_KEY_PATH` (188-191); el rollback del plan repone `custody/` y el `deploy.sh` de v0.4 abortaría. Corrección: la única vía que pasan las dos versiones es dejar la variable vacía (el valor por omisión de `Settings` cambia de versión); S7-D23 (3) y §6.2 c dicen «borrar la línea»; `actualizar.md` con el paso previo; RUNBOOK §12 con `--reverse` antes de volver a etiquetar; prueba con `deploy_e2e.sh` desde el árbol v0.3.
3. BLOQUEANTE · `0029_memberships_original_end_date` mide 34 caracteres y `alembic_version.version_num` es `varchar(32)` (ya pasó con 0022, `docs/scratch/sprint-06.md:277`). Corrección: id de 32 o menos y prueba de largo en `test_migrations.py`.
4. ALTO · S7-D27 (a) (409 `session_not_open` fuera de hoy o ayer) contradice N-38/N-39 (`DECISIONES.md:128`, `02_domain_model.md:81`) y `SPRINT-07.md:67`; el coach podría registrar ayer pero no quitar. `start_date <=` debe compararse con `session_date`. Corrección: bandera en vez de 409 y límite del coach alineado.
5. ALTO · con `--reload` y `MIGRATE_ON_STARTUP=true` el api de desarrollo migra en cada recarga (`compose.dev.yml:29-40`, `main.py:309-310`). Corrección: `$DC stop api worker` antes del Verde de todo slice con migración y de W0-3; arrancar en P-MIG 5.
6. MEDIO · `tests/conftest.py`: `LIMPIEZA_DE_SESION` (437) y `limpiar_tras_dos_sesiones` (837) en B1 y C1, antes de `LIMPIAR_AUTH`, `LIMPIAR_MEMBERSHIPS` y `LIMPIAR_MEMBERS`.
7. MEDIO · dependientes no nombrados: `cli_ops/keys.py:30-33` (y `test_init_keys_cli.py`, `crypto/test_init_keys.py`, `test_init_keys_layout.py`), `scripts/ci/test_env_isolation.sh:202-216`, `cli_ops/__init__.py:28` en B1.
8. MEDIO · E2E: las variables `LOGIN_*` y `USER_*` vienen del `env_file` `.env`, no de la interpolación; `up -d --no-build web` no recrea el api; `ci.yml` 423-444 y el conteo de la línea 451 pasa de 22 a 24.
9. BAJO · el validador usa `CRYPTO_LOCAL_KEK_PATH.parent`, que puede ser `None` con OpenBao (`config.py:772`); sumar `jwt/`.
10. BAJO · entre C1 y C2 `POST /attendance` daría 500 por `MembershipPortNotRegistered`.
11. BAJO · el motivo de S7-D34 es falso (una copia se borra con `rm` en tools); la decisión de mover sin copia es aceptable. El `sed` del `.env` de desarrollo va por patrón.
12. BAJO · `classes` en `PRIVATE_HELPERS` (`tests/architecture/_imports.py:30`); afirmar M-4 en `test_compose_config.sh`.

## Resolución del orquestador (con la orden del usuario «todo le toca a usted», «no pare hasta terminar»)

- Hallazgo 1: se autoriza `SMOKE_DOWN=1` solo para el proyecto desechable `apex-smoke` (el guion comprueba el nombre) y el `docker volume rm` del propio guion sobre `apex-smoke-flat-keys`, como en S6. Ningún otro proyecto.
- Hallazgo 4: se respeta la regla aprobada N-38/N-39: el check-in fuera de hoy o ayer NO da 409; registra y suma la bandera `other_day`. El coach puede quitar asistencias de sesiones de hoy o de ayer (Bogotá); el admin, cualquiera. La membresía se elige con `start_date <= session_date`.
- Hallazgos 2, 3 y 5 a 12: se incorporan como propone la crítica.
