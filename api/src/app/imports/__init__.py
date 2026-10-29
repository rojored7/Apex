"""Importación de socios desde Excel (`import-members`, S4B-B1; S4B-D34, D35, D64).

Capa de aplicación: solo la importa `cli_ops/import_members.py` (S4B-D76). Aquí vive todo uso de
`openpyxl` y `defusedxml` (S4B-D21); nada de `bus`, `types`, `hashlib` ni `text(...)`.
Privados: `limits` (ruta, tamaño y zip), `parse` (cabecera y fila), `persist` (altas y resumen),
`report` (CSV) y `results`; `members_xlsx` es la fachada y lee el libro.
"""
