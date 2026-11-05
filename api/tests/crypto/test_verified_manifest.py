"""`bus.verified_manifest_bytes` (S5-D178, revisión de seguridad B13: MEDIUM de doble lectura).

Lee el manifiesto UNA vez, verifica su firma sobre esos bytes y devuelve esos mismos bytes: quien
los parsea no vuelve a abrir el archivo (no hay ventana entre la firma y el uso). `None` ante
firma ausente o mala, enlace, tamaño mayor de 1 MiB o llave mal formada. `verify_signed_manifest`
sigue siendo un envoltorio booleano.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.crypto import bus, minisign
from tests.factories.minisign_signer import make_signing_key, write_signature

LLAVE = make_signing_key(41)


def _firmado(carpeta: Path, contenido: bytes = b'{"a": 1}\n') -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    manifiesto = carpeta / "latest.json"
    manifiesto.write_bytes(contenido)
    write_signature(LLAVE, manifiesto)
    return manifiesto


def test_devuelve_los_bytes_firmados(tmp_path: Path) -> None:
    manifiesto = _firmado(tmp_path)

    assert bus.verified_manifest_bytes(manifiesto, LLAVE.pubkey) == b'{"a": 1}\n'


def test_el_envoltorio_booleano_coincide(tmp_path: Path) -> None:
    manifiesto = _firmado(tmp_path)

    assert bus.verify_signed_manifest(manifiesto, LLAVE.pubkey) is True
    assert bus.verify_signed_manifest(manifiesto, make_signing_key(42).pubkey) is False


def test_firma_mala_o_llave_ajena_o_mal_formada_da_none(tmp_path: Path) -> None:
    manifiesto = _firmado(tmp_path)
    write_signature(LLAVE, manifiesto, corrupt=True)

    assert bus.verified_manifest_bytes(manifiesto, LLAVE.pubkey) is None
    assert bus.verified_manifest_bytes(manifiesto, "no-es-una-llave") is None


def test_sin_minisig_o_inexistente_da_none(tmp_path: Path) -> None:
    manifiesto = _firmado(tmp_path)
    manifiesto.with_name("latest.json.minisig").unlink()

    assert bus.verified_manifest_bytes(manifiesto, LLAVE.pubkey) is None
    assert bus.verified_manifest_bytes(tmp_path / "nada.json", LLAVE.pubkey) is None


def test_mas_de_1_mib_da_none(tmp_path: Path) -> None:
    manifiesto = _firmado(tmp_path, b" " * ((1 << 20) + 1))

    assert bus.verified_manifest_bytes(manifiesto, LLAVE.pubkey) is None


def test_el_manifiesto_se_abre_una_sola_vez(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifiesto = _firmado(tmp_path)
    abiertos: list[Path] = []
    original = minisign._read_regular

    def espia(path: Path, limit: int) -> bytes | None:
        abiertos.append(path)
        return original(path, limit)

    monkeypatch.setattr(minisign, "_read_regular", espia)

    assert bus.verified_manifest_bytes(manifiesto, LLAVE.pubkey) is not None
    assert abiertos.count(manifiesto) == 1
