# US-112 · Como administrador quiero importar los socios que ya tengo en Excel para pasar del cuaderno al sistema en un día

- **Épica:** EP-13 · Puesta en marcha y continuidad operativa
- **Bounded context:** Members (vía `members.service`), comando en `api/src/app/cli.py`
- **Versión:** v0.1
- **Actor:** administrador
- **Tamaño:** 8
- **Prioridad:** P0 ruta crítica
- **Refinamiento:** Lista para sprint
- **Pantalla:** Ninguna (historia sin front)

## Historia

Como administrador
quiero ejecutar `cli import-members archivo.xlsx` con la plantilla oficial
para cargar el padrón existente cifrado, sin duplicados y con un reporte de las filas que no entraron

## Contexto de dominio

- **Aggregate / entidades:** Member (con value objects cifrados `Document`, `Phone`, `Email`, `BirthDate`, `EmergencyContact`).
- **Reglas que aplica:** RN-13 (datos sensibles cifrados, búsqueda por índice ciego), invariante de documento único entre socios no borrados, nombre y apellido no vacíos, regla de datos 8 (comando de `cli.py`, idempotente y auditado), Q17 (plantilla fija `docs/plantillas/importar-socios.xlsx` con columnas `documento`, `nombres`, `apellidos`, `telefono`, `correo`, `fecha_nacimiento` (AAAA-MM-DD), `sexo` (F, M, X o vacío), `contacto_emergencia_nombre`, `contacto_emergencia_telefono`, `notas`; cabecera validada; idempotente por documento), Q16 (`data_consent_at` puede quedar nulo).
- **Eventos que emite:** `MemberCreated` por cada socio nuevo (lo emite `members.service.create`).
- **Eventos que consume:** ninguno.
- **Funciones puras:** `imports.parse_member_row(row) -> MemberIn | RowError`, `crypto.normalize_for_index` (reutilizada vía bus).

## Alcance

- **Backend:** comando `import-members <ruta.xlsx> [--dry-run]` que lee la plantilla con `openpyxl` (MIT), valida la cabecera exacta y en orden, valida cada fila con el schema de entrada de `members`, y para cada fila válida llama a `members.service.create` (si el documento no existe por `document_idx` entre no borrados) o la omite como "ya existe" (idempotencia). Procesa por lotes de 500 con `batch_id` en `crypto_ops`. Escribe un reporte CSV `import-members-<fecha>.report.csv` con número de fila, documento enmascarado (últimos 3 dígitos), resultado (`created`, `skipped_existing`, `rejected`) y motivo. Registra en auditoría una entrada de acción `insert` por socio (hook normal) y una entrada resumen del comando. Se crea además la plantilla vacía `docs/plantillas/importar-socios.xlsx`.
- **Front:** No aplica.

## Criterios de aceptación

1. Si la cabecera del archivo no coincide exactamente (nombres y orden) con las diez columnas de Q17, el comando termina con código distinto de 0, no crea ningún socio y muestra la cabecera esperada.
2. Cada fila válida crea un socio con `document`, `phone`, `email`, `birth_date` y `emergency_contact` cifrados por el bus y con `document_idx`, `phone_idx` y `email_idx` calculados; ningún valor en claro queda en la base.
3. Una fila sin `documento`, sin `nombres` o sin `apellidos`, con `fecha_nacimiento` fuera del formato AAAA-MM-DD o con `sexo` distinto de F, M, X o vacío se rechaza con su motivo en el reporte y no detiene el resto.
4. Correr el comando dos veces con el mismo archivo no crea duplicados: la segunda vez todas las filas quedan `skipped_existing` (búsqueda por índice ciego del documento normalizado, de modo que `1.020.304` y `1020304` son el mismo).
5. Dos filas del mismo archivo con el mismo documento normalizado: la primera se crea y la segunda queda `rejected` con motivo "documento repetido en el archivo".
6. `--dry-run` valida y produce el reporte sin escribir nada en la base ni en `crypto_ops`.
7. El reporte nunca contiene documento, teléfono ni correo completos (solo los últimos 3 dígitos del documento) y los logs del comando tampoco.
8. Cada socio creado deja su fila de auditoría `insert` con `user_id` del usuario de `--as <email>` o, sin él, `SYSTEM_USER_ID` (N-15) y existe una entrada resumen con número de filas creadas, omitidas y rechazadas.
9. `data_consent_at` queda nulo en los socios importados (Q16) y el resumen del comando lo advierte.
10. Importar 1.000 filas termina en menos de 2 minutos en el servidor de referencia, con las operaciones del bus registradas por lote (`batch_id`).
11. `sexo` se mapea a `f`, `m`, `x` o nulo; `contacto_emergencia_nombre` y `contacto_emergencia_telefono` se guardan juntos en `emergency_contact` como JSON cifrado.

## Escenarios BDD

```gherkin
# language: es
Característica: Importar socios desde Excel

  Antecedentes:
    Dado un administrador con correo "dueno@apex.co"
    Y la plantilla oficial "importar-socios.xlsx"

  Escenario: Importar un archivo válido
    Dado un archivo con 3 filas válidas
    Cuando ejecuto "cli import-members socios.xlsx --as dueno@apex.co"
    Entonces se crean 3 socios con sus datos cifrados
    Y el reporte lista 3 filas "created"
    Y hay 3 entradas de auditoría "insert" a nombre de "dueno@apex.co"

  Escenario: Reimportar el mismo archivo no duplica
    Dado que ya importé "socios.xlsx" con 3 filas
    Cuando ejecuto el mismo comando otra vez
    Entonces no se crea ningún socio
    Y el reporte lista 3 filas "skipped_existing"

  Escenario: Documento con puntos se reconoce como existente
    Dado un socio existente con documento "1020304"
    Y un archivo con una fila de documento "1.020.304"
    Cuando ejecuto la importación
    Entonces la fila queda "skipped_existing"

  Escenario: Cabecera incorrecta
    Dado un archivo cuya segunda columna se llama "nombre"
    Cuando ejecuto la importación
    Entonces el comando termina con un código distinto de 0
    Y no se crea ningún socio

  Escenario: Fila inválida no detiene la importación
    Dado un archivo con una fila sin "apellidos" y dos filas válidas
    Cuando ejecuto la importación
    Entonces se crean 2 socios
    Y el reporte marca la fila sin apellidos como "rejected" con motivo "apellidos obligatorio"
```

## Endpoints

- Ninguno. Comando `uv run python -m app.cli import-members <archivo.xlsx> [--as <email>] [--dry-run]`.

## Pantalla

- Ninguna.

## Notas técnicas

- **Migración:** no (usa las tablas de US-069).
- **Trigger / restricciones:** índice único parcial sobre `document_idx WHERE deleted_at IS NULL` (de US-069) como red de seguridad.
- **Funciones puras a probar:** `validate_header(cells)`, `parse_member_row(row)` con casos: fecha `2001-02-30` rechazada, sexo `f` en minúscula aceptado, documento con espacios normalizado, correo inválido rechazado.
- **Pruebas:** puras de parseo; service con base real (idempotencia, duplicado en archivo, cifrado, auditoría, dry-run sin escrituras); prueba de rendimiento marcada `slow` con 1.000 filas; prueba de que el reporte y los logs no contienen datos completos.
- **Archivos principales:** `api/src/app/cli.py`, `api/src/app/imports/members_xlsx.py`, `docs/plantillas/importar-socios.xlsx`, `api/tests/cli/test_import_members.py`.
- **Licencias:** `openpyxl` es MIT (verificar en el chequeo de US-004).

## Supuestos

- Supuesto: el comando acepta `--as <email>` de un usuario admin activo para atribuir `created_by` y la auditoría; sin él, usa `SYSTEM_USER_ID` (N-15). Q17 no dice a nombre de quién se importa.
- Supuesto: el reporte se escribe junto al archivo de entrada y enmascara el documento a los últimos 3 dígitos.
- Supuesto: un socio existente por documento no se actualiza con los datos del archivo (solo se omite); Q17 dice "idempotente por documento" sin precisar si actualiza.

## Dependencias

- US-069 · Registrar socio (`members.service.create`, cifrado, duplicado).
- US-029 · Bitácora `crypto_ops` por lote (`batch_id`).

## INVEST

- **Independiente:** solo usa el service de socios.
- **Negociable:** formato del reporte y tamaño de lote ajustables.
- **Valiosa:** es el paso que permite el arranque real del gimnasio.
- **Estimable:** plantilla y reglas fijadas por Q17.
- **Pequeña:** un comando; tamaño 8 por validaciones, idempotencia y rendimiento.
- **Testeable:** archivos de prueba con resultados esperados por fila.

## Definición de listo

- [x] Criterios de aceptación verificables
- [x] Escenarios BDD con camino feliz, error y rol
- [x] Endpoints y roles definidos
- [x] Dependencias identificadas
- [x] Sin preguntas abiertas que bloqueen (o supuesto declarado)

## Definición de terminado

- [ ] `ruff check`, `ruff format` y `mypy --strict` en verde
- [ ] Pruebas de reglas puras y de service con PostgreSQL real en verde; cobertura de 80 % o más en lo tocado
- [ ] Pruebas de router: rol, validación y envelope de error (no aplica: sin HTTP)
- [ ] Front: pruebas de componente y página; sin colores literales (no aplica)
- [ ] Migración aplicada con `alembic upgrade head` y reversible (no aplica)
- [ ] `docs/openapi.json` regenerado (no aplica)
- [ ] Auditoría verificada para las tablas tocadas
- [ ] Revisión de PR aprobada
