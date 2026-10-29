"""Validador mínimo de manifest.schema.json para las pruebas de shell (S4B-D80).

Implementa solo el subconjunto de JSON Schema que usa el esquema (type, const, enum,
pattern, minLength, maxLength, minimum, minItems, required, properties,
additionalProperties, items). Sin dependencias: se ejecuta con cualquier Python 3.
Uso: python validate_manifest.py <schema.json> <manifiesto.json>; sale con 0 si es válido.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

TIPOS: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "array": (list,),
    "object": (dict,),
    "null": (type(None),),
    "boolean": (bool,),
}


def _tipo_ok(valor: Any, tipo: str) -> bool:
    if tipo == "integer" and isinstance(valor, bool):
        return False
    return isinstance(valor, TIPOS[tipo])


def validar(valor: Any, esquema: dict[str, Any], ruta: str = "$") -> list[str]:
    errores: list[str] = []
    tipo = esquema.get("type")
    if tipo is not None:
        tipos = tipo if isinstance(tipo, list) else [tipo]
        if not any(_tipo_ok(valor, t) for t in tipos):
            return [f"{ruta}: tipo {type(valor).__name__} no está en {tipos}"]
    if "const" in esquema and valor != esquema["const"]:
        errores.append(f"{ruta}: debe ser {esquema['const']!r}")
    if "enum" in esquema and valor not in esquema["enum"]:
        errores.append(f"{ruta}: {valor!r} no está en {esquema['enum']}")
    if isinstance(valor, str):
        if "pattern" in esquema and re.search(esquema["pattern"], valor) is None:
            errores.append(f"{ruta}: no cumple {esquema['pattern']}")
        if "minLength" in esquema and len(valor) < esquema["minLength"]:
            errores.append(f"{ruta}: más corto que {esquema['minLength']}")
        if "maxLength" in esquema and len(valor) > esquema["maxLength"]:
            errores.append(f"{ruta}: más largo que {esquema['maxLength']}")
    if isinstance(valor, int) and not isinstance(valor, bool):
        if "minimum" in esquema and valor < esquema["minimum"]:
            errores.append(f"{ruta}: menor que {esquema['minimum']}")
    if isinstance(valor, list):
        if "minItems" in esquema and len(valor) < esquema["minItems"]:
            errores.append(f"{ruta}: menos de {esquema['minItems']} elementos")
        if "items" in esquema:
            for i, item in enumerate(valor):
                errores += validar(item, esquema["items"], f"{ruta}[{i}]")
    if isinstance(valor, dict):
        for requerido in esquema.get("required", []):
            if requerido not in valor:
                errores.append(f"{ruta}: falta {requerido}")
        props = esquema.get("properties", {})
        for clave, sub in valor.items():
            if clave in props:
                errores += validar(sub, props[clave], f"{ruta}.{clave}")
            elif esquema.get("additionalProperties") is False:
                errores.append(f"{ruta}: propiedad no permitida {clave}")
    return errores


def main(argv: list[str]) -> int:
    with open(argv[1], encoding="utf-8") as f:
        esquema = json.load(f)
    with open(argv[2], encoding="utf-8") as f:
        manifiesto = json.load(f)
    errores = validar(manifiesto, esquema)
    for e in errores:
        print(e, file=sys.stderr)
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
