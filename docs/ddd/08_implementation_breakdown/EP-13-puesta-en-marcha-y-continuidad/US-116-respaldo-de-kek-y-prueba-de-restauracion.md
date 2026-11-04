# US-116 · Respaldo de la KEK y prueba de restauración — desglose técnico

> **Corregido en S4B-W0-1** (`docs/ddd/blueprints/sprint-04b-plan.md`, sección 1, "Contradicciones de contrato cerradas en los desgloses", y decisión S4B-D2; registro en `docs/ddd/DECISIONES.md`, "Sprint 4B"). Donde el texto de abajo choque con estas notas, mandan las notas:
> - El respaldo de la KEK usa `age -p` por `archive.py`, sin `--passphrase-file` y sin `pyrage`.
> - `restore.sh` verifica la firma y exige `--confirm-database`; la KEK se restaura con `restore-kek`; la clase del respaldo es `kek.backup`.
> - La tabla es `crypto.crypto_keys` (no `crypto_keys`).
> - Sin `0014_crypto_ops_export_verb`: la migración `0014` del sprint es `0014_audit_log_triggers_always`.
> - Pruebas y scripts en Bash puro con `bash -n`; sin `bats` ni `shellcheck`.
> - `test_banned_imports.py` se reemplaza por `test_ruff_banned_api.py` sin cambio y la nueva `test_third_party_confinement.py`.
> - Los comandos usan `docker compose run --rm tools ...`, sin `uv run`.

- **Historia:** `docs/ddd/07_user_stories/EP-13-puesta-en-marcha-y-continuidad/US-116-respaldo-de-kek-y-prueba-de-restauracion.md`
- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context / módulo:** Crypto (`api/src/app/core/crypto/kek_backup.py` y `local_provider.py`), comandos en `api/src/app/cli.py`, script `infra/backup/restore.sh` y documento `docs/operacion/respaldo-y-restauracion.md`
- **Versión:** v0.1
- **Puntos de la historia:** 3

## Estado de preparación

**READY**

N-05 acepta el verbo `export` y los comandos `cli export-kek` y `cli verify-kek-backup`, que eran el único supuesto de la historia. Toda la lógica criptográfica queda dentro de `core/crypto`, que es donde la regla `banned-api` la permite. El CLI solo llama a funciones de `core/crypto`. La restauración es manual y documentada, como pide EP-13. Depende de que `0003_crypto` incluya `export` en el CHECK del verbo de `crypto_ops`.

## Resumen

Se agregan dos comandos:

- `cli export-kek --out <ruta>` lee la KEK del `LocalFileProvider`. La cifra en memoria en formato `age` con frase de paso, con `age -p` por `subprocess` en `core/crypto/archive.py`, y la escribe con permisos 600. La frase se pide por consola sin eco, dos veces, a través de `age`; nunca por argumento.
- `cli verify-kek-backup <archivo>` descifra el respaldo en memoria y comprueba que desenvuelve todas las DEK `active` y `decrypt_only` de `crypto.crypto_keys`, sin cambiar ninguna llave.

Ambos dejan una fila en `crypto_ops` y una entrada en auditoría, sin material de llave. Se escribe `infra/backup/restore.sh`, que restaura un `apex-*.sql.age` en una base vacía. Se niega si hay tablas de APEX con datos, salvo `--i-know-this-overwrites`. Hay una prueba de punta a punta en CI: socios cifrados, backup, base nueva, restauración, arranque con la KEK respaldada y `reveal` del documento; con una KEK distinta, el api no arranca. El documento de operación explica el procedimiento paso a paso.

## Correcciones aplicadas por DECISIONES.md

- Supuesto de la historia "agregar `export` al enum de verbos de `crypto_ops` y los comandos `export-kek` y `verify-kek-backup`" → aceptado; no hace falta migración nueva si `0003_crypto` (US-024) ya incluye `export` en el CHECK: DECISIONES N-05.
- Actor de los comandos → `user_id` de `crypto_ops` y de auditoría es `SYSTEM_USER_ID`, o el admin activo de `--as <email>`: corregido por DECISIONES N-15 (la historia no lo decía).
- La restauración muestra el documento con `reveal` (auditado) y no con el enmascarado de la ficha → la prueba usa `members.service.reveal`; el enmascarado de N-01 también descifra, pero no es la acción que el criterio pide: DECISIONES N-01 y Q6.
- Backups sin firma antes de v1.0 → `restore.sh` no verifica firma: DECISIONES N-48.

## Validación contra el dominio

- CryptoKey (2.13): las DEK están envueltas en `crypto.crypto_keys` y la KEK local está en un archivo 600 fuera del repositorio (`CRYPTO_LOCAL_KEK_PATH`).
- Invariante "el material en claro nunca se persiste": la KEK solo existe en claro en memoria durante el comando; el archivo exportado está cifrado con `age` y frase de paso.
- `verify-kek-backup` "sin escribir nada" se entiende como sin cambiar llaves. Las filas de bitácora (`crypto_ops` y auditoría) del criterio 2 sí se escriben. Así se concilian los criterios 2 y 3 de la historia.
- RN-13: la prueba termina en un `reveal` auditado.
- Sin eventos de dominio. Sin funciones puras nuevas, salvo `restore.sh` que valida el estado de la base con una consulta.

## Validación contra la arquitectura

- Primitivas criptográficas solo en `core/crypto`: `archive.py` contiene `export_kek_file`, `restore_kek_file` y `verify_kek_backup`. Usa el binario `age -p` (respaldo con frase de paso en formato `age`, compatible con el binario `age` que el operador usa a mano) y la operación `unwrap` del `KeyProvider` (US-023). El CLI no importa `cryptography`.
- `crypto_ops`: verbo `export` para `export-kek` y `verify` para `verify-kek-backup`, con `data_class` nula o `kek` según el registro de `core/crypto/registry.py` (N-04) y sin material de llave. La tabla es append-only (US-024).
- Auditoría: `core.audit.record(action="export", table_name="crypto_keys", record_id=<id de la fila de crypto_ops>, after={"kind": "kek_backup"})` y `action="verify"` para la verificación. Las dos acciones existen en el CHECK de `0002_audit_log`.
- Lint banned-api: `subprocess` solo se importa en `core/crypto/archive.py` (`per-file-ignores`, S4B-D21).
- Licencia: `age` es BSD-3 (binario en la imagen); no hay dependencia de Python nueva.
- Restauración: `restore.sh` corre en el contenedor `backup` (tiene `age` y `pg_restore` 16) y nunca en el api.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica, siempre que `0003_crypto` (US-024) incluya `export` en el CHECK de `crypto_ops.verb` (N-05). Si no lo incluyera, se agrega `0014_crypto_ops_export_verb` (ampliar el CHECK; el downgrade solo procede si no hay filas con `export`).

### Models
- No aplica.

### Service
- [ ] T1 · `core/crypto/kek_backup.py`: `export_kek(provider, passphrase: str) -> bytes` (exige frase de al menos 12 caracteres, N-10; cifra con `age -p`; borra las referencias a la KEK en claro al terminar) y `verify_kek_backup(blob: bytes, passphrase: str, wrapped: Sequence[WrappedDek]) -> VerifyKekResult(ok, total, failed_key_ids)`, que prueba `unwrap` de cada DEK con la KEK descifrada en un `LocalFileProvider` en memoria — 2 h
- [ ] T2 · `core/crypto/service.py`: casos de uso `async def export_kek_to(session, out_path, passphrase, actor_id)` (escribe con `os.open(..., 0o600)`, se niega a sobrescribir, registra `crypto_ops` y auditoría) y `async def verify_kek_file(session, path, passphrase, actor_id) -> VerifyKekResult` (lee las DEK `active` y `decrypt_only` de `crypto_keys`, registra `crypto_ops` y auditoría con el resultado) — 1,5 h
- [ ] T3 · `app/cli.py`: subcomandos `export-kek --out <ruta> [--as <email>]` y `verify-kek-backup <archivo> [--as <email>]`; la frase se pide con `typer.prompt(hide_input=True, confirmation_prompt=True)`; no existe opción `--passphrase`; código 0 si todo bien, 1 si alguna DEK no se desenvuelve, 2 si el archivo o la frase no sirven; nunca se imprime la KEK ni la frase — 1 h
- [ ] T4 · `infra/backup/restore.sh` con `set -euo pipefail`: recibe el archivo y la identidad `age` (`-i`), comprueba con `psql` que no existan filas en `members.members`, `payments.payments` ni `audit.audit_log` (si existen, sale con código distinto de 0 salvo `--i-know-this-overwrites`), descifra en streaming (`age -d | tar -x` en `tmpfs`), restaura con `pg_restore --clean --if-exists --no-owner`, restaura `uploads/` al volumen y avisa que el api debe arrancar con la KEK respaldada — 2 h

### Schemas
- No aplica (sin HTTP).

### Router
- No aplica.

### Tests unitarios puros
- [ ] T5 · `api/tests/crypto/test_kek_backup.py`: `export_kek` produce bytes que no contienen los 32 bytes de la KEK ni su base64; `verify_kek_backup` con la frase correcta y las DEK de la misma instalación es `ok`; con otra KEK, `failed_key_ids` lista todas; con frase equivocada falla sin excepción con contenido — 1,5 h

### Tests de service con PostgreSQL
- [ ] T6 · `api/tests/cli/test_export_kek.py`: `export-kek` escribe el archivo con permisos 600 y se niega a sobrescribirlo; deja una fila `crypto_ops` con verbo `export` y una entrada de auditoría `export` sin material; `verify-kek-backup` deja verbo `verify`; `CliRunner` con `--passphrase x` termina con error de opción desconocida; la salida y `caplog` no contienen la frase ni la KEK — 1,5 h

### Tests de router
- No aplica.

### Tests de arquitectura
- [ ] T7 · `api/tests/architecture/test_banned_imports.py` (US-031): `subprocess` solo se importa en `app/core/crypto/archive.py`; `app/cli.py` no importa `cryptography` ni `hashlib` — 0,5 h

### Front
- No aplica.

### DevOps
- [ ] T8 · `infra/tests/restore_e2e.sh` en CI (Compose de prueba): crear socio "Ana Pérez" con documento cifrado → `export-kek` con la frase por `age -p` → `run.sh` de US-114 → base nueva vacía → `restore.sh` → descifrar el respaldo de la KEK con `core.crypto.kek_backup` en un paso de prueba y montarlo como `CRYPTO_LOCAL_KEK_PATH` → arrancar el api → `members.service.reveal` devuelve el documento; segundo caso con una KEK distinta: el api sale con código distinto de 0 y el log dice "no se pudo desenvolver la DEK" sin la llave — 3 h
- [ ] T9 · `infra/backup/tests/test_restore_guard.sh`: `restore.sh` sobre una base con socios se niega y la base queda igual (conteo antes y después); con `--i-know-this-overwrites` procede — 1 h
- [ ] T10 · `docs/operacion/respaldo-y-restauracion.md`: pasos numerados en lenguaje simple: dónde está la KEK, cómo exportarla, dos copias fuera del servidor (por ejemplo, una USB en la caja fuerte y un gestor de contraseñas del dueño), dónde guardar la identidad privada `age` y la frase de paso por separado, cómo verificar el respaldo cada mes con `verify-kek-backup`, cómo restaurar (abrir la KEK con `age -d`, `restore.sh`, arrancar) y qué hacer si se perdió alguna pieza; registro en el PR de que otra persona lo siguió — 2 h
- [ ] T11 · `NOTICE` con `age` (sin dependencia nueva de Python) — 0,5 h

### Seguridad
- [ ] T12 · Revisión: la frase no pasa por argumentos ni por variables de entorno en los logs; el archivo exportado nunca se escribe dentro del volumen `backups` (se rechaza esa ruta, para no guardar la KEK junto al backup); `restore.sh` no imprime la identidad; la KEK descifrada en la prueba vive en `tmpfs` y se borra — 1 h

## Orden de ejecución

1. Confirmar que `0003_crypto` tiene `export` en el CHECK (si no, crear `0014_crypto_ops_export_verb`).
2. T11 (dependencia y licencia).
3. T5 (en rojo), luego T1.
4. T7.
5. T6 (en rojo), luego T2 y T3.
6. T9 (en rojo), luego T4.
7. T8.
8. T10 y T12.

## Dependencias técnicas

- US-023 · KeyProvider y proveedor local: lectura de la KEK y `unwrap`.
- US-024 · Tablas `crypto_keys`, `crypto_ops` y `crypto_jobs`: verbo `export` en el CHECK (N-05).
- US-025 · Apertura de DEK al arrancar: el api no arranca con una KEK equivocada.
- US-029 · Bitácora `crypto_ops`.
- US-015 · `core.audit.record` y acciones `export` y `verify`.
- US-074 · Mostrar dato sensible auditado (`reveal`) para cerrar la prueba (agregado en consolidación).
- US-114 · Backup nocturno cifrado: `run.sh`, formato del archivo y manifiesto.
- US-041 · `SYSTEM_USER_ID` y `--as`.
- US-004 · Licencias.

## Endpoints

- Ninguno.

## Riesgos

- Respaldar el backup sin la KEK es como no respaldar — mitigación: el documento lo pone como primer paso y `verify-kek-backup` permite comprobarlo cada mes.
- Guardar la KEK exportada y la identidad `age` en el mismo lugar que los backups: quien tenga el respaldo lo abre todo — mitigación: el comando rechaza rutas dentro del volumen `backups` y el documento separa las tres piezas (KEK, frase e identidad).
- Que `age -p` por `subprocess` filtre la frase — mitigación: la frase solo viaja por el TTY de `age`, nunca por argumento.
- Con OpenBao (v0.2) la KEK sale del servidor y este comando cambia — mitigación: `export-kek` solo funciona con el proveedor `local` y responde con un mensaje claro con otro proveedor; EP-15 define su respaldo.
- El criterio 6 (otra persona siguió el documento) es manual — mitigación: casilla obligatoria en la plantilla del PR.
- Estimación por encima del rango de 3 puntos (10 a 15 h): la suma da 18 h porque la prueba de punta a punta en CI (T8) y el documento de operación probado (T10) pesan más que el código — mitigación: T8 reutiliza el Compose de prueba de US-114.

## Estimación

- Backend: 7 h
- Front: 0 h
- Pruebas: 4 h
- DevOps / seguridad: 7 h
- **Total: 18 h**

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/crypto/test_kek_backup.py tests/cli/test_export_kek.py -q`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `bash -n infra/backup/restore.sh infra/tests/restore_e2e.sh` y `bash infra/backup/tests/test_restore_guard.sh`
- [ ] `bash infra/tests/restore_e2e.sh` en CI termina con 0 (restaura y hace `reveal`; con otra KEK el api no arranca)
- [ ] `psql -c "SELECT verb, count(*) FROM crypto.crypto_ops WHERE verb IN ('export','verify') GROUP BY verb"` muestra las dos operaciones
- [ ] `docs/operacion/respaldo-y-restauracion.md` existe y el PR registra quién lo siguió
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.core.crypto.kek_backup --cov-fail-under=80`
