"""El vector de `signature_payload` de ADR-006 coincide con el código (S6-A1; S6-D4, US-140).

ADR-006 lleva un bloque cercado `signature-payload-vector` con un JSON: `version`, `through_seq`,
`hash` (el de la fila de ejemplo de ADR-004), `payload` y `payload_hex`. La prueba reconstruye el
payload con `through_seq = 1` y ese hash y compara BYTE A BYTE. Como `chain-hash-vector` (ADR-004),
un cambio de un solo byte invalida todas las firmas guardadas: hay que detenerse y preguntar.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.core.audit_sign import signature_payload

RAIZ = Path(__file__).resolve().parents[3] / "docs" / "adr"
ADR_006 = RAIZ / "ADR-006-firma-de-la-cadena-de-auditoria.md"
ADR_004 = RAIZ / "ADR-004-serializacion-canonica-de-auditoria.md"
BLOQUE = re.compile(r"```signature-payload-vector[ \t]*\r?\n(.*?)```", re.DOTALL)
BLOQUE_004 = re.compile(r"```chain-hash-vector[ \t]*\r?\n(.*?)```", re.DOTALL)
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def leer_vector() -> dict[str, Any]:
    bloques = BLOQUE.findall(ADR_006.read_text(encoding="utf-8"))
    assert len(bloques) == 1, (
        f"debe haber exactamente un bloque signature-payload-vector: {len(bloques)}"
    )
    vector = json.loads(bloques[0])
    assert isinstance(vector, dict)
    return vector


def test_el_bloque_tiene_las_cinco_claves_y_un_hash_hexadecimal() -> None:
    vector = leer_vector()
    assert set(vector) == {"version", "through_seq", "hash", "payload", "payload_hex"}
    assert (vector["version"], vector["through_seq"]) == (1, 1)
    assert HEX64.match(vector["hash"])


def test_el_hash_del_vector_es_el_de_la_fila_de_adr_004() -> None:
    """La fila de ejemplo es la de ADR-004: ambos documentos citan el mismo `hash`."""
    bloque = BLOQUE_004.findall(ADR_004.read_text(encoding="utf-8"))
    assert len(bloque) == 1
    assert json.loads(bloque[0])["hash"] == leer_vector()["hash"]


def test_signature_payload_reproduce_los_bytes_del_vector() -> None:
    vector = leer_vector()

    payload = signature_payload(vector["through_seq"], vector["hash"], version=vector["version"])

    assert payload == bytes.fromhex(vector["payload_hex"])
    assert payload == vector["payload"].encode("ascii")
    assert payload == b"apex-audit-sig-v1\n1\n" + vector["hash"].encode("ascii")


def test_la_version_por_omision_es_1() -> None:
    vector = leer_vector()
    assert signature_payload(1, vector["hash"]) == bytes.fromhex(vector["payload_hex"])
