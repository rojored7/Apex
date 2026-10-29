# Importar los socios del box desde Excel

Para pasar la lista actual de socios (la que hoy vive en una hoja de cálculo) a APEX, una sola vez o cada vez que llegue una tanda nueva. El comando es `import-members`. Lo corre una persona con acceso al servidor, con su cuenta de administrador (`--as`).

## Antes de empezar

1. Descargue la plantilla `docs/plantillas/importar-socios.xlsx` y llénela. **No cambie la cabecera**: si el orden o el nombre de una columna es distinto, el comando rechaza el archivo completo.
2. Una fila por socio. Máximo **5.000 filas** y **10 MB**. Solo `.xlsx` (sin macros ni vínculos a otros libros).
3. Tenga a mano el **correo de un administrador activo**: las altas quedan a su nombre en la auditoría.

## Las columnas (Q17)

| Columna | Obligatoria | Qué lleva |
|---|---|---|
| `documento` | sí | Solo el número. Se aceptan puntos, espacios y guiones (`1.020.304`). Un mismo documento escrito de varias formas dentro del archivo cuenta una sola vez. |
| `nombres` | sí | Ningún campo de texto puede empezar por `=`, `+`, `-` ni `@` (tampoco el teléfono: escriba `3001234567`, sin `+57`). |
| `apellidos` | sí | Igual que `nombres`. |
| `telefono` | no | Celular. |
| `correo` | no | Correo válido. |
| `fecha_nacimiento` | no | `AAAA-MM-DD` (por ejemplo `1990-05-17`). |
| `sexo` | no | `F`, `M` o `X`. |
| `contacto_emergencia_nombre` | no | Se guarda solo si llena también el teléfono. |
| `contacto_emergencia_telefono` | no | Se guarda solo si llena también el nombre. Con uno solo de los dos el socio se crea **sin contacto** y el reporte lo marca. |
| `notas` | no | **No se guarda en esta versión.** Si la llena, el comando avisa (`notes_ignored`) y la ignora. |

El tipo de documento queda en `CC`. Si alguien tiene cédula de extranjería o pasaporte, corríjalo luego en su ficha.

## Pasos

1. Cree una carpeta para el trabajo y copie ahí el archivo (en el servidor, dentro de la carpeta del proyecto):

   ```bash
   mkdir -p importar
   cp ~/socios.xlsx importar/socios.xlsx
   ```

2. **Primero en simulación** (`--dry-run`): lee, valida y saca el reporte sin escribir nada.

   ```bash
   docker compose --env-file .env -f infra/compose.yml run --rm \
     -v "$PWD/importar:/data/imports" tools \
     import-members /data/imports/socios.xlsx --as admin@su-box.co --dry-run --report simulacion.csv
   ```

3. Revise `importar/simulacion.csv` y corrija el Excel si hay filas `rejected`. Luego, la corrida real (el reporte lleva otro nombre):

   ```bash
   docker compose --env-file .env -f infra/compose.yml run --rm \
     -v "$PWD/importar:/data/imports" tools \
     import-members /data/imports/socios.xlsx --as admin@su-box.co --report resultado.csv
   ```

   Se puede repetir sin miedo: un documento que ya existe se salta (`skipped_existing`).

4. La salida son solo conteos:

   ```
   import-members: created=118 skipped_existing=0 rejected=2 consent_missing=118 notes_ignored=4 contacts_omitted=3
   ```

   Sale con **0** si la cabecera es válida (aunque haya filas rechazadas), **2** si el archivo no sirve (cabecera distinta, fuera de la carpeta, demasiado grande, hoja vacía, más de 5.000 filas) y **1** si falló una escritura (repita el comando: lo ya importado se omite).

## El reporte

`--report <nombre>` crea un CSV (separador `;`, abre bien en Excel) dentro de la carpeta, **solo con un nombre** (no rutas) y **sin pisar** uno existente. Columnas: `fila;documento;resultado;motivo`. El documento va enmascarado (`•••304`); el resultado es `created`, `skipped_existing` o `rejected`; el motivo es una frase fija (nunca el contenido de la celda). La fila es la de la hoja de Excel.

## Después: autorización de datos y borrado

- **Los socios importados quedan sin autorización de tratamiento de datos** (`consent_missing`). Ley 1581: recoja la autorización firmada de cada uno y regístrela en su ficha. Mientras tanto no se les envían avisos.
- **Borre el archivo y los reportes del servidor al terminar** y no los envíe por correo: tienen datos personales.

  ```bash
  rm -rf importar
  ```

- La auditoría deja un `insert` por socio a nombre del administrador y una entrada resumen (`members.import_runs`) con la huella SHA-256 del archivo y los conteos; nunca el nombre del archivo.

## Si algo sale mal

| Mensaje | Qué hacer |
|---|---|
| `el archivo debe estar dentro de IMPORT_DIR` | Monte la carpeta con `-v "$PWD/importar:/data/imports"` y use la ruta `/data/imports/...`. |
| `la cabecera no coincide con la plantilla...` | Vuelva a descargar la plantilla y pegue los datos debajo de su cabecera. |
| `--report ... ya existe` | Use otro nombre o borre el reporte anterior. |
| `--as: no existe un admin activo con ese correo` | Use el correo de un administrador activo. |
