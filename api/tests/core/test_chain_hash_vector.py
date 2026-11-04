"""El vector de `chain_hash` documentado en ADR-004 coincide con el código (S4B-B4; S4B-D47).

`docs/adr/ADR-004-serializacion-canonica-de-auditoria.md` lleva un bloque cercado con la etiqueta
`chain-hash-vector` que contiene un JSON con tres claves:

    {"prev_hash": "<64 ceros>", "row": {<HASHED_KEYS de una fila de ejemplo>}, "hash": "<64 hex>"}

Dentro de `row`: `id` y `user_id` son UUID en texto, `at` es ISO 8601 UTC con `Z` y 6 decimales,
`seq` es entero y `before`/`after` son `null` u objetos. La prueba lo lee con una expresión
regular y exige `chain_hash(prev_hash, fila) == hash` con `prev_hash == ZERO_HASH`. La fila no
lleva datos personales reales (sin correos, teléfonos, documentos ni blobs `apx1.`).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from app.core.audit import HASHED_KEYS, ZERO_HASH, canonical, chain_hash

ADR = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "adr"
    / "ADR-004-serializacion-canonica-de-auditoria.md"
)
BLOQUE = re.compile(r"```chain-hash-vector[ \t]*\r?\n(.*?)```", re.DOTALL)
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def leer_vector(texto: str) -> dict[str, Any]:
    """El JSON del bloque `chain-hash-vector`; falla con un motivo claro si falta o está vacío."""
    bloques = BLOQUE.findall(texto)
    assert len(bloques) == 1, f"debe haber exactamente un bloque chain-hash-vector: {len(bloques)}"
    assert bloques[0].strip(), "el bloque chain-hash-vector está vacío"
    vector = json.loads(bloques[0])
    assert isinstance(vector, dict)
    return vector


def fila_para_hash(fila: dict[str, Any]) -> dict[str, Any]:
    """Los tipos que la cadena recibe de la base: UUID y datetime con zona."""
    salida = dict(fila)
    for clave in ("id", "user_id", "record_id"):
        if isinstance(salida.get(clave), str):
            salida[clave] = UUID(salida[clave])
    if isinstance(salida.get("at"), str):
        salida["at"] = datetime.fromisoformat(salida["at"])
    return salida


def test_el_bloque_existe_y_tiene_las_tres_claves() -> None:
    vector = leer_vector(ADR.read_text(encoding="utf-8"))
    assert set(vector) == {"prev_hash", "row", "hash"}
    assert vector["prev_hash"] == ZERO_HASH
    assert HEX64.match(vector["hash"])
    assert set(HASHED_KEYS) <= set(vector["row"])


def test_el_hash_del_adr_es_el_que_calcula_chain_hash() -> None:
    vector = leer_vector(ADR.read_text(encoding="utf-8"))
    fila = fila_para_hash(vector["row"])
    assert chain_hash(vector["prev_hash"], fila) == vector["hash"]


def test_la_fila_del_ejemplo_no_lleva_datos_personales() -> None:
    vector = leer_vector(ADR.read_text(encoding="utf-8"))
    texto = json.dumps(vector["row"], ensure_ascii=False)
    assert "@" not in texto
    assert "apx1." not in texto


def test_la_fecha_del_ejemplo_esta_en_el_formato_canonico() -> None:
    vector = leer_vector(ADR.read_text(encoding="utf-8"))
    fila = fila_para_hash(vector["row"])
    assert re.search(rb'"at":"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}Z"', canonical(fila))


def test_control_un_hash_alterado_no_coincide() -> None:
    texto = (
        "```chain-hash-vector\n"
        + json.dumps(
            {
                "prev_hash": ZERO_HASH,
                "row": {"id": "00000000-0000-0000-0000-0000000000aa", "seq": 1, "at": None},
                "hash": "f" * 64,
            }
        )
        + "\n```\n"
    )
    vector = leer_vector(texto)
    assert chain_hash(vector["prev_hash"], fila_para_hash(vector["row"])) != vector["hash"]


def test_control_sin_bloque_o_bloque_vacio_se_rechaza() -> None:
    for texto in ("sin bloque", "```chain-hash-vector\n```\n"):
        try:
            leer_vector(texto)
        except AssertionError:
            continue
        raise AssertionError("debía rechazarse")
