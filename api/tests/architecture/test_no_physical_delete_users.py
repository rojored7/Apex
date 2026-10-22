"""Los usuarios nunca se borran físicamente (US-041 T12; RN-14)."""

from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "app"
PATRONES = (
    re.compile(r"delete\(\s*User\s*\)"),
    re.compile(r"session\.delete\(\s*\w*user\w*\s*\)", re.IGNORECASE),
    re.compile(r"DELETE\s+FROM\s+auth\.users", re.IGNORECASE),
    re.compile(r"TRUNCATE\s+auth\.users", re.IGNORECASE),
)


def _violaciones() -> list[str]:
    salida: list[str] = []
    for path in sorted(SRC.rglob("*.py")):
        texto = path.read_text(encoding="utf-8")
        for patron in PATRONES:
            for m in patron.finditer(texto):
                linea = texto.count("\n", 0, m.start()) + 1
                salida.append(f"{path.relative_to(SRC).as_posix()}:{linea}: {m.group(0)}")
    return salida


def test_sin_borrado_fisico_de_usuarios() -> None:
    assert _violaciones() == []


def test_el_patron_detecta_un_borrado(tmp_path: Path) -> None:
    fuente = "await session.delete(user)\nstmt = delete(User)\nSQL = 'DELETE FROM auth.users'\n"
    assert sum(len(p.findall(fuente)) for p in PATRONES) == 3
