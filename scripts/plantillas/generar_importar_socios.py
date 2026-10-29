"""Genera `docs/plantillas/importar-socios.xlsx` (S4B-B1.6; S4B-D34, D35).

La plantilla lleva la cabecera de Q17 en negrita (la misma constante que valida
`import-members`), `documento`, `telefono`, `fecha_nacimiento` y el teléfono del contacto con
formato texto (Excel no recorta ceros ni convierte fechas) y una hoja `Instrucciones` en español.
No lleva ninguna fila de datos: nunca se versiona un archivo con personas.

Se ejecuta con `uv run` desde `api/`:

    cd api && uv run python ../scripts/plantillas/generar_importar_socios.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from openpyxl import Workbook  # type: ignore[import-untyped]
from openpyxl.styles import Alignment, Font  # type: ignore[import-untyped]

from app.imports.members_xlsx import MAX_ROWS, TEMPLATE_HEADER

TEXT_COLUMNS: Final = (
    "documento",
    "telefono",
    "fecha_nacimiento",
    "contacto_emergencia_telefono",
)
INSTRUCCIONES: Final = (
    "Cómo llenar la plantilla de socios",
    "",
    "1. No cambie los nombres, el orden ni la cantidad de columnas de la hoja «Socios»: el comando "
    "rechaza el archivo completo si la cabecera no es exactamente esta.",
    "2. Una fila por socio. documento, nombres y apellidos son obligatorios; el resto es opcional.",
    "3. documento: solo el número (se aceptan puntos, espacios y guiones: 1.020.304). "
    "El tipo de documento queda como CC; si es de otro tipo (CE, PA), corríjalo luego en la "
    "ficha del socio.",
    "4. fecha_nacimiento: AAAA-MM-DD, por ejemplo 1990-05-17 (columna en formato texto).",
    "5. sexo: F, M o X, o déjelo vacío.",
    "6. Contacto de emergencia: solo se guarda si llena el nombre Y el teléfono. Con uno solo "
    "de los dos, el socio se crea sin contacto de emergencia y el reporte lo marca.",
    "7. notas: NO se guarda en esta versión. Si la llena, el comando lo avisa y la ignora.",
    "8. Ningún campo de texto puede empezar por = + - o @ (ni el teléfono: escriba 3001234567, "
    "sin +57).",
    f"9. Máximo {MAX_ROWS} filas de datos y 10 MB por archivo. Solo se acepta .xlsx "
    "(sin macros ni vínculos externos).",
    "10. Los socios importados quedan SIN autorización de tratamiento de datos (Ley 1581): "
    "recoja la autorización firmada y regístrela en la ficha. No se les puede enviar avisos "
    "hasta entonces.",
    "11. Al terminar, borre este archivo y el reporte del servidor y no los envíe por correo: "
    "contienen datos personales.",
)


def _hoja_socios(libro: Workbook) -> None:
    hoja: Any = libro.active
    hoja.title = "Socios"
    hoja.append(list(TEMPLATE_HEADER))
    for celda in hoja[1]:
        celda.font = Font(bold=True)
    hoja.freeze_panes = "A2"
    for letra, nombre in zip("ABCDEFGHIJ", TEMPLATE_HEADER, strict=True):
        columna = hoja.column_dimensions[letra]
        columna.width = max(16, len(nombre) + 4)
        if nombre in TEXT_COLUMNS:
            columna.number_format = "@"


def _hoja_instrucciones(libro: Workbook) -> None:
    hoja: Any = libro.create_sheet("Instrucciones")
    hoja.column_dimensions["A"].width = 110
    for texto in INSTRUCCIONES:
        hoja.append([texto])
        hoja.cell(row=hoja.max_row, column=1).alignment = Alignment(wrap_text=True, vertical="top")
    hoja["A1"].font = Font(bold=True, size=14)


def generar(destino: Path) -> None:
    libro = Workbook()
    _hoja_socios(libro)
    _hoja_instrucciones(libro)
    destino.parent.mkdir(parents=True, exist_ok=True)
    libro.save(destino)


if __name__ == "__main__":
    generar(Path(__file__).resolve().parents[2] / "docs" / "plantillas" / "importar-socios.xlsx")
