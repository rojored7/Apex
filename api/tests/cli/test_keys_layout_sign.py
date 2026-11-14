"""Layout del volumen `keys` con `sign/` y `--reverse` (S7-D4, S7-D23 (4), S7-D34).

La llave de firma pasa de `custody/` a `sign/` (el api monta solo `custody/` y `jwt/`). El cambio
es un `rename` atómico dentro del mismo volumen: idempotente, sin pisar y reversible.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from app.cli import app
from app.cli_ops.keys_layout import migrate_layout, reverse_layout
from tests.cli._apoyo import correr

SOLO_POSIX = pytest.mark.skipif(os.name == "nt", reason="NTFS no conserva el modo POSIX")
SEMILLA = b"firma-de-prueba-" + b"s" * 16  # nunca material real
KEK = b"kek-de-prueba-" + b"k" * 18
PEM = b"jwt-privada-de-prueba"
PUB = b"jwt-publica-de-prueba"

ARBOL_NUEVO = {
    "custody/kek.bin": KEK,
    "sign/sign-ed25519.key": SEMILLA,
    "jwt/jwt_ed25519.pem": PEM,
    "jwt/jwt_ed25519.pub": PUB,
}


def _escribir(raiz: Path, relativos: dict[str, bytes]) -> Path:
    for rel, datos in relativos.items():
        destino = raiz / rel
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(datos)
        destino.chmod(0o600)
    return raiz


def _arbol(raiz: Path) -> dict[str, bytes]:
    return {
        p.relative_to(raiz).as_posix(): p.read_bytes()
        for p in sorted(raiz.rglob("*"))
        if p.is_file()
    }


def test_plano_viejo_a_layout_nuevo(tmp_path: Path) -> None:
    raiz = _escribir(
        tmp_path / "keys",
        {
            "kek.bin": KEK,
            "sign-ed25519.key": SEMILLA,
            "jwt_ed25519.pem": PEM,
            "jwt_ed25519.pub": PUB,
        },
    )

    informe = migrate_layout(raiz)

    assert set(informe.moved) == {
        "kek.bin",
        "sign-ed25519.key",
        "jwt_ed25519.pem",
        "jwt_ed25519.pub",
    }
    assert _arbol(raiz) == ARBOL_NUEVO


def test_layout_s6_a_layout_nuevo(tmp_path: Path) -> None:
    raiz = _escribir(
        tmp_path / "keys",
        {
            "custody/kek.bin": KEK,
            "custody/sign-ed25519.key": SEMILLA,
            "jwt/jwt_ed25519.pem": PEM,
            "jwt/jwt_ed25519.pub": PUB,
        },
    )

    informe = migrate_layout(raiz)

    assert informe.moved == ("sign-ed25519.key",)
    assert _arbol(raiz) == ARBOL_NUEVO
    assert not (raiz / "custody" / "sign-ed25519.key").exists()


def test_idempotente(tmp_path: Path) -> None:
    raiz = _escribir(tmp_path / "keys", {"custody/sign-ed25519.key": SEMILLA})
    assert migrate_layout(raiz).moved == ("sign-ed25519.key",)

    segunda = migrate_layout(raiz)

    assert segunda.nothing_to_migrate
    assert (raiz / "sign" / "sign-ed25519.key").read_bytes() == SEMILLA


def test_idempotente_por_cli_la_segunda_dice_nada_que_migrar(tmp_path: Path) -> None:
    raiz = _escribir(tmp_path / "keys", {"custody/sign-ed25519.key": SEMILLA})

    primera = correr(app, ["init-keys", "--migrate-layout", "--dir", str(raiz)])
    segunda = correr(app, ["init-keys", "--migrate-layout", "--dir", str(raiz)])

    assert primera.exit_code == 0 and "movido sign-ed25519.key" in primera.output
    assert segunda.exit_code == 0 and "nada que migrar" in segunda.output


def test_conflicto_no_pisa(tmp_path: Path) -> None:
    raiz = _escribir(
        tmp_path / "keys",
        {"custody/sign-ed25519.key": SEMILLA, "sign/sign-ed25519.key": b"otra-semilla"},
    )
    antes = _arbol(raiz)

    informe = migrate_layout(raiz)

    assert informe.conflicts == ("sign-ed25519.key",) and informe.moved == ()
    assert _arbol(raiz) == antes


def test_dos_origenes_son_conflicto(tmp_path: Path) -> None:
    raiz = _escribir(
        tmp_path / "keys", {"sign-ed25519.key": SEMILLA, "custody/sign-ed25519.key": b"otra"}
    )
    antes = _arbol(raiz)

    informe = migrate_layout(raiz)

    assert informe.conflicts == ("sign-ed25519.key",)
    assert _arbol(raiz) == antes


def test_conflicto_por_cli_sale_con_2(tmp_path: Path) -> None:
    raiz = _escribir(
        tmp_path / "keys",
        {"custody/sign-ed25519.key": SEMILLA, "sign/sign-ed25519.key": b"otra-semilla"},
    )

    resultado = correr(app, ["init-keys", "--migrate-layout", "--dir", str(raiz)])

    assert resultado.exit_code == 2


def test_reverse_devuelve_la_llave_a_custody(tmp_path: Path) -> None:
    raiz = _escribir(tmp_path / "keys", ARBOL_NUEVO)

    informe = reverse_layout(raiz)

    assert informe.moved == ("sign-ed25519.key",)
    assert (raiz / "custody" / "sign-ed25519.key").read_bytes() == SEMILLA
    assert not (raiz / "sign" / "sign-ed25519.key").exists()


def test_reverse_es_idempotente_y_no_pisa(tmp_path: Path) -> None:
    raiz = _escribir(tmp_path / "keys", ARBOL_NUEVO)
    assert reverse_layout(raiz).moved == ("sign-ed25519.key",)
    assert reverse_layout(raiz).nothing_to_migrate

    _escribir(raiz, {"sign/sign-ed25519.key": b"otra"})
    antes = _arbol(raiz)

    assert reverse_layout(raiz).conflicts == ("sign-ed25519.key",)
    assert _arbol(raiz) == antes


def test_reverse_por_cli_y_ida_y_vuelta(tmp_path: Path) -> None:
    raiz = _escribir(tmp_path / "keys", ARBOL_NUEVO)

    vuelta = correr(app, ["init-keys", "--migrate-layout", "--reverse", "--dir", str(raiz)])
    ida = correr(app, ["init-keys", "--migrate-layout", "--dir", str(raiz)])

    assert vuelta.exit_code == 0 and ida.exit_code == 0
    assert _arbol(raiz) == ARBOL_NUEVO


def test_reverse_sin_migrate_layout_se_rechaza(tmp_path: Path) -> None:
    resultado = correr(app, ["init-keys", "--reverse", "--dir", str(tmp_path / "keys")])

    assert resultado.exit_code != 0


@SOLO_POSIX
def test_sign_queda_en_700_y_la_llave_en_600(tmp_path: Path) -> None:
    raiz = _escribir(tmp_path / "keys", {"custody/sign-ed25519.key": SEMILLA})

    migrate_layout(raiz)

    assert stat.S_IMODE((raiz / "sign").stat().st_mode) == 0o700
    assert stat.S_IMODE((raiz / "sign" / "sign-ed25519.key").stat().st_mode) == 0o600


# S7-W0-3b (L-1): la comprobación y el movimiento son una sola operación ----------------------


def test_un_destino_que_aparece_tras_la_comprobacion_no_se_pisa(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Carrera entre dos `tools`: el conflicto se decidió antes y el destino aparece después."""
    from app.cli_ops import keys_layout

    raiz = _escribir(
        tmp_path / "keys",
        {"custody/sign-ed25519.key": SEMILLA, "sign/sign-ed25519.key": b"otra-semilla"},
    )
    monkeypatch.setattr(keys_layout, "_es_conflicto", lambda *_a: False)

    informe = migrate_layout(raiz)

    assert (raiz / "sign" / "sign-ed25519.key").read_bytes() == b"otra-semilla"
    assert (raiz / "custody" / "sign-ed25519.key").read_bytes() == SEMILLA
    assert informe.conflicts == ("sign-ed25519.key",)


def test_una_subcarpeta_enlace_es_conflicto_y_no_se_mueve_nada(tmp_path: Path) -> None:
    raiz = _escribir(tmp_path / "keys", {"custody/sign-ed25519.key": SEMILLA})
    fuera = tmp_path / "fuera"
    fuera.mkdir()
    try:
        (raiz / "sign").symlink_to(fuera, target_is_directory=True)
    except OSError:
        pytest.skip("sin permiso para crear enlaces simbólicos")

    informe = migrate_layout(raiz)

    assert informe.conflicts and not informe.moved
    assert list(fuera.iterdir()) == []
    assert (raiz / "custody" / "sign-ed25519.key").read_bytes() == SEMILLA


def test_las_subcarpetas_existentes_se_reponen_en_700(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`mkdir(exist_ok=True)` no cambia el modo de una carpeta que ya existía."""
    raiz = _escribir(tmp_path / "keys", {"custody/sign-ed25519.key": SEMILLA})
    (raiz / "sign").mkdir()
    llamadas: list[tuple[str, int]] = []
    real = os.chmod

    def espia(ruta: object, modo: int, *a: object, **k: object) -> None:
        llamadas.append((Path(str(ruta)).name, modo))
        real(ruta, modo, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "chmod", espia)

    migrate_layout(raiz)

    assert ("sign", 0o700) in llamadas
