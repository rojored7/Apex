# US-112 · Importar socios desde Excel — desglose técnico

- **Historia:** `docs/ddd/07_user_stories/EP-13-puesta-en-marcha-y-continuidad/US-112-importar-socios-desde-excel.md`
- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context / módulo:** Members (vía `members.service`), comando de aplicación en `api/src/app/cli.py` con el lector en `api/src/app/imports/members_xlsx.py`
- **Versión:** v0.1
- **Puntos de la historia:** 8

## Estado de preparación

**READY**

Q17 fija la plantilla, la cabecera exacta y la idempotencia por documento. N-02 fija la normalización. N-15 fija a nombre de quién queda la importación. Q16 permite `data_consent_at` nulo. La librería para leer `.xlsx` (`openpyxl`) tiene licencia MIT, permitida. Lo que queda (la entrada resumen en auditoría, el rollback del `--dry-run`) se resuelve dentro de la arquitectura actual, sin cambiar contratos.

## Resumen

Se agrega `import-members <archivo.xlsx> [--as <email>] [--dry-run]` a `cli.py`. El módulo `app/imports/members_xlsx.py` tiene las funciones puras `validate_header(cells)` y `parse_member_row(row_number, cells) -> MemberCreate | RowError`, y el orquestador `import_members(session, rows, actor_id, dry_run)`. El orquestador:

- lee con `openpyxl` en modo `read_only`;
- detecta documentos repetidos dentro del archivo comparando el índice ciego;
- omite los documentos que ya existen (`members.service.id_by_document`);
- crea los nuevos con `members.service.create` en lotes de 500, dentro de `core.crypto.bus.batch()` para que `crypto_ops` agrupe por `batch_id` (US-029).

Escribe un reporte CSV junto al archivo, con el documento enmascarado a los últimos 3 dígitos, y deja una entrada resumen en auditoría. Se crea también la plantilla `docs/plantillas/importar-socios.xlsx`.

## Correcciones aplicadas por DECISIONES.md

- La historia exige `--as <email>` como obligatorio → `--as` es opcional; sin él, `created_by` y `user_id` de auditoría son `SYSTEM_USER_ID`, y con él, el admin activo indicado: corregido por DECISIONES N-15. El escenario "a nombre de dueno@apex.co" se cumple pasando `--as`.
- Criterio 4: la historia normaliza solo puntos y espacios → la normalización del índice ciego es NFKD sin diacríticos, minúsculas, sin espacios, puntos ni guiones; teléfono solo dígitos sin `57`/`+57` inicial; correo en minúsculas y sin espacios. Así `1.020.304`, `1020-304` y `1 020 304` son el mismo documento: corregido por DECISIONES N-02.
- La importación no crea membresías; si una versión futura las importa, no tendrá el límite retroactivo del API: anotado según DECISIONES N-24 (no cambia esta historia).
- Socio existente por documento → se omite como `skipped_existing` y no se actualiza con los datos del archivo: aceptado como lectura de "idempotente por documento" de DECISIONES Q17.
- `data_consent_at` nulo y advertencia en el resumen: aceptado por DECISIONES Q16. `data_consent_version` vacío: aceptado por DECISIONES N-19.
- Teléfono y correo opcionales; documento, nombres y apellidos obligatorios: aceptado por DECISIONES N-19.

## Validación contra el dominio

- Aggregate Member con value objects cifrados `Document`, `Phone`, `Email`, `BirthDate` y `EmergencyContact` (2.1). La importación solo crea socios con `members.service.create`, que hace cumplir las invariantes: documento único entre no borrados por `document_idx`, nombres y apellidos no vacíos.
- RN-13: todo dato sensible queda cifrado por los tipos `Encrypted`/`BlindIndexed` de Members. El reporte y los logs nunca llevan valores completos.
- Mapeo de Q17: `sexo` F, M o X (sin importar mayúsculas) a `f`, `m` o `x`, y vacío a `null`; `contacto_emergencia_nombre` y `contacto_emergencia_telefono` a `emergency_contact` JSON `{name, phone}`, que se cifra junto (`member.emergency_contact`); `fecha_nacimiento` AAAA-MM-DD estricto (`2001-02-30` se rechaza). Una celda de tipo fecha de Excel se acepta y se convierte (la plantilla fuerza formato texto para evitarla). Un documento numérico (`1020304.0`) se convierte a texto sin decimales.
- Regla de datos 8: comando idempotente y auditado.
- Evento emitido: `MemberCreated` por socio nuevo (lo emite `members.service.create`; no tiene suscriptores en v0.1).
- Funciones puras: `validate_header(cells: Sequence[object]) -> None | HeaderError`, `parse_member_row(row_number: int, cells: Sequence[object]) -> MemberCreate | RowError` y `mask_document(doc: str) -> str` ("•••304"). Confirmado: sin discrepancias.

## Validación contra la arquitectura

- `cli.py` y `app/imports/` son capa de aplicación: no son módulos ni tienen `models.py`, y llaman solo a `members.service` y `auth.service`. Usan el schema `MemberCreate` de `members/schemas.py` para validar. Importar schemas desde la capa de aplicación no viola la regla de models cruzados; T13 lo verifica.
- Bus de criptografía:
  - el cifrado lo hacen los tipos de columna de Members;
  - para detectar repetidos en el archivo se usa `core.crypto.bus.blind_index("member.document", doc)`, que normaliza por N-02;
  - el lote usa `core.crypto.bus.batch()` (US-029);
  - el hash del archivo para la entrada resumen usa `core.crypto.bus.digest(data)` (N-06).

  Nada importa `hashlib` ni `hmac` fuera de `core/crypto`.
- Lint banned-api: sin primitivas fuera de `core/crypto`.
- Licencias: `openpyxl` 3.1 (MIT) y su dependencia `et_xmlfile` (MIT) entran en la lista permitida y pasan `pip-licenses` (US-004). `defusedxml` (licencia PSF) **no** se agrega porque la PSF no está en la lista de `CLAUDE.md`. La protección contra XML malicioso se reemplaza por límites de tamaño (10 MB) y de filas (5.000), porque el archivo lo aporta el mismo administrador en el servidor.
- Auditoría: cada socio deja su `insert` por el hook de US-016. La entrada resumen se escribe con `core.audit.record(action="insert", table_name="members_import", record_id=<uuid de la corrida>, after={file_name, file_sha256, rows, created, skipped_existing, rejected, consent_missing})`. `table_name` es libre y no colisiona con `members`, así que no aparece en "Últimos movimientos" (US-110) ni en el historial de la ficha. La acción `insert` ya está en el CHECK de `0002_audit_log`.
- `--dry-run`: toda la corrida va en una transacción que termina en `ROLLBACK`. Así no queda nada en `members`, `audit_log` ni `crypto_ops`, siempre que el bus registre `crypto_ops` en la sesión del llamador (US-029). Si US-029 usara otra sesión, `--dry-run` pasaría al bus un modo `no_log` documentado.
- Rol: no hay HTTP. `--as` exige un admin activo.

## Preguntas abiertas

Ninguna.

## Tareas

### Migración Alembic
- No aplica (usa `members.members` de `0006_members` y `audit.audit_log` de `0002_audit_log`).

### Models
- No aplica.

### Service
- [ ] T1 · `app/imports/members_xlsx.py`: constante `TEMPLATE_HEADER` con las diez columnas de Q17 en orden; `validate_header(cells)` que compara exacto (sin espacios sobrantes, minúsculas) y devuelve la cabecera esperada en el error — 1 h
- [ ] T2 · `app/imports/members_xlsx.py`: `parse_member_row(row_number, cells)` con los casos del dominio (obligatorios, fecha estricta o celda de fecha, sexo, documento numérico, correo inválido con la validación de `MemberCreate`, contacto de emergencia como par) y `mask_document`; devuelve `RowError(row_number, reason)` con motivos en español ("apellidos obligatorio", "fecha_nacimiento inválida", "sexo inválido", "correo inválido") — 3 h
- [ ] T3 · `app/imports/members_xlsx.py`: `read_rows(path) -> Iterator[tuple[int, list[object]]]` con `openpyxl.load_workbook(path, read_only=True, data_only=True)`, solo la primera hoja, límite de 10 MB y 5.000 filas, filas totalmente vacías ignoradas — 1,5 h
- [ ] T4 · `app/imports/members_xlsx.py`: `async def import_members(session, path, actor_id, *, dry_run) -> ImportResult` que valida la cabecera (aborta sin escribir), parsea, detecta repetidos del archivo por `bus.blind_index`, consulta `members.service.id_by_document`, crea con `members.service.create(data, by=actor_id)` en lotes de 500 dentro de `bus.batch()`, atrapa el error de duplicado del service como `skipped_existing` (red de seguridad del índice único), escribe la entrada resumen y hace `ROLLBACK` si `dry_run` — 4 h
- [ ] T5 · `app/imports/report.py`: `write_report(path, results)` que escribe `import-members-<AAAAMMDD-HHMMSS>.report.csv` junto al archivo, con separador `;` y BOM UTF-8 (igual que N-29), columnas `fila;documento;resultado;motivo`, documento enmascarado — 1 h
- [ ] T6 · `app/cli.py`: subcomando `import-members <archivo> [--as <email>] [--dry-run]` que resuelve el actor (`auth.service.active_admin_id_by_email` o `SYSTEM_USER_ID`), abre la sesión con el contexto de actor de US-016, imprime el resumen (creados, omitidos, rechazados, advertencia de autorización faltante por Q16) y sale con 0 si la cabecera es válida aunque haya filas rechazadas, o con 2 si la cabecera no coincide o el archivo no se puede leer — 1,5 h
- [ ] T7 · Contrato pedido a EP-07: `members.service.id_by_document(document) -> UUID | None` (busca por `document_idx` entre no borrados) y que `members.service.create` levante un error tipado `DuplicateDocument(existing_id)` — 0,5 h

### Schemas
- [ ] T8 · `app/imports/members_xlsx.py`: dataclasses congeladas `RowError`, `RowResult(row, masked_document, outcome: Literal["created", "skipped_existing", "rejected"], reason)` e `ImportResult`; la validación de campos reutiliza `members.schemas.MemberCreate` (no se duplican reglas) — 1 h

### Router
- No aplica.

### Tests unitarios puros
- [ ] T9 · `api/tests/cli/test_members_xlsx_parse.py`: cabecera correcta e incorrecta (segunda columna "nombre"), orden cambiado, `2001-02-30` rechazada, celda de fecha aceptada, sexo `f` en minúscula aceptado, sexo `Z` rechazado, documento `1020304.0` → `"1020304"`, correo inválido rechazado, contacto de emergencia con solo nombre aceptado como `{name, phone: null}`, `mask_document("1020304") == "•••304"` — 2,5 h

### Tests de service con PostgreSQL
- [ ] T10 · `api/tests/cli/test_import_members.py`: archivo con 3 filas válidas crea 3 socios con todos los campos sensibles empezando por `apx1.` y `*_idx` calculados; reimportar deja 3 `skipped_existing`; socio existente `1020304` y fila `1.020.304` (y `1020-304`, por N-02) queda `skipped_existing`; dos filas con el mismo documento normalizado: la primera `created` y la segunda `rejected` ("documento repetido en el archivo"); fila sin apellidos `rejected` y el resto se crea — 3 h
- [ ] T11 · `api/tests/cli/test_import_members.py`: auditoría con un `insert` por socio a nombre de `--as` (o `SYSTEM_USER_ID` sin `--as`) y una entrada `members_import` con los conteos; `--dry-run` deja cero filas nuevas en `members.members`, `audit.audit_log` y `crypto.crypto_ops`; las operaciones del bus de 1.000 filas quedan agrupadas por `batch_id` — 2 h
- [ ] T12 · `api/tests/cli/test_import_members_perf.py` (marcado `slow`): 1.000 filas en menos de 2 minutos; el reporte y la salida capturada (`caplog`, `capsys`) no contienen ningún documento completo, teléfono ni correo de las filas — 1,5 h

### Tests de router
- No aplica (sin HTTP).

### Tests de arquitectura
- [ ] T13 · `api/tests/architecture/test_no_cross_models.py` revisa `app/imports/` (ampliado en US-111): sin `app.modules.*.models` y sin `openpyxl` fuera de `app/imports/`; `test_banned_imports.py` sigue verde — 0,5 h

### Front
- No aplica.

### DevOps
- [ ] T14 · `docs/plantillas/importar-socios.xlsx`: plantilla vacía generada por un script reproducible `scripts/plantillas/generar_importar_socios.py` (openpyxl, cabecera de Q17 en negrita, columnas `documento`, `telefono` y `fecha_nacimiento` con formato texto `@`, una hoja "Instrucciones" en español) — 1,5 h
- [ ] T15 · Agregar `openpyxl` a `pyproject.toml` y confirmar que `pip-licenses` de US-004 lo acepta (MIT) junto con `et_xmlfile` (MIT); registrar ambos en `NOTICE` — 0,5 h
- [ ] T16 · `docs/operacion/importar-socios.md`: pasos en lenguaje simple (copiar el archivo al servidor, `--dry-run`, revisar el reporte, correr de verdad, borrar el archivo y el reporte del servidor) — 1 h

### Seguridad
- [ ] T17 · Revisión: el archivo de origen y el reporte contienen datos personales en claro o enmascarados; el documento de operación indica borrarlos del servidor al terminar; los logs no imprimen filas; límites de tamaño y filas activos frente a un `.xlsx` malicioso — 1 h

## Orden de ejecución

1. T7 (contrato con EP-07) y T15 (dependencia y licencia).
2. T9 (en rojo), luego T8, T1 y T2.
3. T3.
4. T10 y T11 (en rojo), luego T4 y T5.
5. T6.
6. T12 y T13.
7. T14, T16 y T17.

## Dependencias técnicas

- US-069 · Registrar socio: `members.service.create`, `MemberCreate`, índice único parcial de `document_idx`, error tipado de duplicado.
- US-070 · Buscar socios: `members.service.id_by_document`.
- US-026 · Índice ciego HMAC con la normalización de N-02.
- US-028 · Tipos `Encrypted` y `BlindIndexed`.
- US-029 · Bitácora `crypto_ops` por lote (`bus.batch()`, `batch_id`, registro en la sesión del llamador).
- US-015 · Auditoría y `core.audit.record`; `bus.digest` de N-06.
- US-016 · Contexto de actor para procesos sin HTTP.
- US-041 · `SYSTEM_USER_ID` y `auth.service.active_admin_id_by_email`.
- US-004 · Chequeo de licencias y `NOTICE`.

## Endpoints

- Ninguno.

## Riesgos

- Archivos reales que no siguen la plantilla (columnas extra, otra hoja): el comando rechaza todo — mitigación: mensaje con la cabecera esperada, plantilla con hoja de instrucciones y `--dry-run` para probar sin riesgo.
- Excel convierte documentos y fechas a números o fechas: filas rechazadas por formato — mitigación: la plantilla fuerza texto y el parser acepta celdas numéricas y de fecha.
- Datos personales en claro en el servidor (archivo de origen y reporte) — mitigación: el reporte enmascara y el documento de operación ordena borrar ambos.
- `--dry-run` que deja rastro en `crypto_ops` si el bus registra en otra sesión — mitigación: T11 lo prueba; si falla, se usa el modo `no_log` del bus documentado en US-029.
- Rendimiento con 1.000 filas por el bloqueo de la cadena de auditoría en cada flush (US-015) — mitigación: T12 mide; un flush por lote de 500 reduce los bloqueos.
- Sin `defusedxml` (licencia PSF fuera de la lista) — mitigación: límites de tamaño y filas, y el archivo lo aporta el administrador.

## Estimación

- Backend: 14 h
- Front: 0 h
- Pruebas: 10 h
- DevOps / seguridad: 4 h
- **Total: 28 h**

## Definición de hecho

- [ ] `cd api && uv run ruff check . && uv run ruff format --check .`
- [ ] `cd api && uv run mypy src`
- [ ] `cd api && uv run pytest tests/cli/test_members_xlsx_parse.py tests/cli/test_import_members.py -q`
- [ ] `cd api && uv run pytest tests/cli/test_import_members_perf.py -q -m slow`
- [ ] `cd api && uv run pytest tests/architecture -q`
- [ ] `cd api && uv run pip-licenses --allow-only="MIT;BSD;Apache;PostgreSQL" | grep -i openpyxl` muestra MIT
- [ ] `uv run python -m app.cli import-members tests/fixtures/socios-3.xlsx --as dueno@apex.co` dos veces: la segunda imprime 0 creados y 3 omitidos
- [ ] `psql -c "SELECT count(*) FROM members.members WHERE document NOT LIKE 'apx1.%' OR phone NOT LIKE 'apx1.%'"` devuelve 0
- [ ] `docs/plantillas/importar-socios.xlsx` existe y su cabecera coincide con Q17
- [ ] Cobertura ≥ 80 % en lo tocado: `cd api && uv run pytest --cov=app.imports --cov-fail-under=80`
