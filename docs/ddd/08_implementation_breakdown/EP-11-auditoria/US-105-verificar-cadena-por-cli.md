# US-105 · Verificar cadena por CLI — desglose técnico

> **Corregido en S4A-W0-1** (`docs/ddd/blueprints/sprint-04a-plan.md`, sección 1 y enmiendas E1 a E10; registro en `docs/ddd/DECISIONES.md`, "Sprint 4A"). Donde el texto de abajo choque con estas notas, mandan las notas:
> - El correo de `--as` se resuelve con `cli.resolve_actor(session, email)`, no con `auth.service.get_by_email` (no existe); el comando usa `cli_runtime(settings, runtime_options(ctx))` y fija el actor con `unit_of_work(actor)` durante el commit (S4A-D15, S4A-D41).
> - `--wait-timeout` (300 s por defecto) espera con `pg_try_advisory_lock` en un bucle de 2 s, no con `pg_advisory_lock` bloqueante (el `lock_timeout` de 10 s lo cortaría); agotado, sale 2 (S4A-D15).
> - Con `ENV=production`, `--as` es obligatorio (salida 2 si falta) y `--db-timeouts off` se rechaza (salida 2); con `ENV=dev` `--as` sigue opcional (S4A-D53).
> - `run_verification` y `format_verify_message` viven en `core/audit_verify.py`, no en `core/audit.py`, y `run_verification` recibe una sesión (`run_verification(session, source="cli", by=actor)`) (S4A-D12, S4A-D15).
> - La conexión del candado es `AUTOCOMMIT` y se invalida en el `finally` tras `pg_advisory_unlock`, con `VERIFY_MAX_SECONDS = 900`, igual que en el API; los lotes son de `VERIFY_BATCH_SIZE = 1000` y la verificación compara contra el ancla de la última verificación `ok` (`through_hash`) (S4A-D44, S4A-D47, S4A-D43).
> - En la imagen no hay `uv`: el comando del runbook es `docker compose exec api python -m app.cli verify-audit --as <correo>` (CLAUDE.md, "Comandos"); `cli.py` se parte en `app/cli_ops.py` solo si pasa de 760 líneas (S4A-D72).

- **Historia:** `docs/ddd/07_user_stories/EP-11-auditoria/US-105-verificar-cadena-por-cli.md`
- **Épica:** EP-11 · Auditoría y trazabilidad
- **Bounded context / módulo:** Audit (`api/src/app/core/audit.py`), comando en `api/src/app/cli.py`
- **Versión:** v0.1
- **Puntos de la historia:** 2

## Estado de preparación

**READY**

El comando, sus códigos de salida y su salida están definidos. Los dos supuestos que chocaban con decisiones ya tomadas (`user_id` nulo en la entrada `verify` y "no hay tabla de resultados") quedan corregidos por DECISIONES N-15 y N-30. La lógica de verificación se comparte con US-104 (`core.audit.run_verification`).

## Resumen

Agrega el comando `uv run python -m app.cli verify-audit [--as <email>]` (typer), que fija el actor, recorre la cadena completa por lotes con `core.audit.run_verification(source="cli")`, imprime "Cadena íntegra: N filas verificadas" (código 0) o "Cadena rota en el registro seq X" (código 1), y sale con código 2 si la base no está disponible. Cada ejecución deja una fila en `audit.verifications` y una entrada `verify` en la cadena con `after.source = "cli"`.

## Correcciones aplicadas por DECISIONES.md

- La historia registra la entrada `verify` con `user_id` nulo → `user_id = SYSTEM_USER_ID` (`00000000-0000-0000-0000-000000000001`) por defecto, o el usuario indicado con `--as <email>` cuando lo ejecuta una persona: corregido por DECISIONES N-15. `after.source = "cli"` se conserva.
- La historia no persiste el resultado fuera de la cadena → cada ejecución inserta una fila en `audit.verifications` con `source = 'cli'` y `triggered_by` igual al actor, para que `GET /audit/verify/last` (US-104) también muestre las verificaciones hechas por CLI: corregido por DECISIONES N-30.
- El nombre del comando es `verify-audit`, igual que en `05_service_design.md` sección 2.

## Validación contra el dominio

- Aggregate `AuditEntry`; RN-16. Regla de datos 8: los comandos de mantenimiento viven en `cli.py` y quedan auditados.
- Funciones puras: `verify_chain` (US-104) y la nueva `format_verify_message(result) -> tuple[str, int]` (texto y código de salida), probada sin base.
- Eventos: ninguno.

## Validación contra la arquitectura

- `cli.py` llama a `core.audit.run_verification` (código de `core`), no a `modules/audit`, y para `--as` a `cli.resolve_actor` (lectura). No hay router ni rol HTTP; el control de acceso es el acceso al servidor.
- El actor se fija en la variable de contexto `current_actor` de US-016 antes de abrir la transacción; sin actor el hook fallaría (criterio 7 de US-016).
- Exclusión mutua con la verificación del API por el mismo advisory lock `AUDIT_VERIFY_LOCK_KEY`: si hay una verificación en curso en el API, el comando espera (`pg_advisory_lock`, bloqueante, con `--wait-timeout` por defecto 300 s) en lugar de fallar, porque la CLI no tiene modo en segundo plano.
- El comando nunca imprime `before` ni `after`. Lint `banned-api`: sin primitivas (el hash pasa por `bus.digest`, N-06).

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (usa `audit.verifications` de `0013_audit_verifications`, US-104).

### Models
- No aplica.

### Service
- [ ] T1 · Función pura `format_verify_message(result: VerifyResult) -> tuple[str, int]` en `core/audit.py` (0 íntegra, 1 rota) — 0,5 h
- [ ] T2 · `api/src/app/cli.py`: comando `verify-audit` con opciones `--as` (correo; resuelve el id con `cli.resolve_actor`, error y código 2 si no existe) y `--wait-timeout`; fija `current_actor`, abre conexión, toma `pg_advisory_lock` con timeout, llama a `run_verification(conn, source="cli", by=actor)`, confirma, imprime el mensaje y sale con su código; `OperationalError`/`OSError` de conexión imprime el error sin trazas internas y sale con 2 — 2,5 h

### Schemas
- No aplica.

### Router
- No aplica.

### Tests unitarios puros
- [ ] T3 · `api/tests/core/test_format_verify_message.py`: resultado íntegro (texto y 0), roto en seq 42 (texto y 1) — 0,5 h

### Tests de service con PostgreSQL
- [ ] T4 · `api/tests/cli/test_verify_audit.py` con `typer.testing.CliRunner` contra la base de prueba: cadena íntegra → código 0 y "Cadena íntegra"; fila con seq 42 alterada → código 1 y "Cadena rota en el registro seq 42"; entrada `verify` con `user_id = SYSTEM_USER_ID` y `after.source = "cli"`; con `--as admin@apex.co` la entrada y `audit.verifications.triggered_by` llevan ese usuario; `--as` con correo inexistente → código 2; la salida no contiene ningún valor de `before`/`after` — 2 h
- [ ] T5 · Mismo archivo: base no disponible (URL apuntando a un puerto cerrado) → código 2; el comando recorre por lotes (espía sobre la consulta: ninguna lectura de más de `VERIFY_BATCH_SIZE` filas) — 1 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T6 · `test_banned_imports.py` sigue verde para `cli.py`; prueba que `cli.py` registra `verify-audit` y que todo comando de `cli.py` acepta `--as` (N-15; si EP-13 crea esa prueba, se extiende) — 0,5 h

### Front
- No aplica.

### DevOps
- [ ] T7 · Documentar el comando en el runbook de operación (`docs/runbook.md` de EP-13): `docker compose exec api python -m app.cli verify-audit --as <correo>`, significado de los códigos 0, 1 y 2 — 0,5 h

### Seguridad
- [ ] T8 · Revisión: el comando no imprime filas ni secretos, el mensaje de error de conexión no muestra la contraseña de la URL de la base — 0,5 h

## Orden de ejecución
1. T3 (pura en rojo)
2. T1
3. T4, T5 (comando en rojo)
4. T2
5. T6
6. T7
7. T8

## Dependencias técnicas
- US-015 · Tabla de auditoría y cadena de hashes.
- US-104 · Verificar cadena desde pantalla: `verify_chain`, `run_verification`, tabla `audit.verifications` (`0013_audit_verifications`) y la clave del advisory lock. Si US-105 se implementa primero, crea esas piezas y US-104 las reutiliza.
- US-016 · `current_actor`.
- US-041 · Usuario técnico `SYSTEM_USER_ID` (migración `0004_auth`) y `cli.resolve_actor`.

## Endpoints
- Ninguno.

## Riesgos
- Si `run_verification` lo implementa primero US-105, el contrato con US-104 debe quedar igual — mitigación: una sola función en `core/audit.py` con `source` como parámetro y pruebas compartidas.
- Un `--wait-timeout` demasiado corto hace fallar el comando mientras el API verifica — mitigación: 300 s por defecto y mensaje claro "hay una verificación en curso".

## Estimación
- Backend: 3 h (T1, T2)
- Front: 0 h
- Pruebas: 4 h (T3 a T6)
- DevOps / seguridad: 1 h (T7, T8)
- **Total: 8 h**

## Definición de hecho
- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/core/test_format_verify_message.py -q`
- [ ] `cd api && uv run pytest tests/cli/test_verify_audit.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run python -m app.cli verify-audit; echo $?` imprime "Cadena íntegra: N filas verificadas" y `0`
- [ ] `SELECT user_id, after->>'source' FROM audit.audit_log WHERE action = 'verify' ORDER BY seq DESC LIMIT 1` devuelve `00000000-0000-0000-0000-000000000001 | cli`
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.cli --cov=app.core.audit --cov-fail-under=80`
