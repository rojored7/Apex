"""Los cinco ADR existen con nombre fijo y formato fijo (S4B-B4; S4B-D47, US-119; S5-D48, ADR-005).

- `docs/adr/` tiene exactamente los cinco archivos (los cuatro de S4B-D47 y ADR-005, S5-D48);
- cada uno tiene, en orden, las seis secciones (`## Estado`, `## Contexto`, `## Decisión`,
  `## Alternativas descartadas`, `## Consecuencias`, `## Cómo se verifica`), todas con contenido, y
  la frase de detenerse y preguntar antes de cambiar la decisión;
- toda ruta `tests/...py` citada en "Cómo se verifica" existe en `api/tests/` y cada ADR cita al
  menos una;
- `docs/adr/README.md` nombra los cinco archivos y la plantilla de seis secciones.
Controles con fuentes falsas al final.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

API_ROOT: Final = Path(__file__).resolve().parents[2]
ADR_DIR: Final = API_ROOT.parent / "docs" / "adr"
ARCHIVOS: Final = (
    "ADR-001-monolito-modular.md",
    "ADR-002-criptografia.md",
    "ADR-003-pagos-inmutables.md",
    "ADR-004-serializacion-canonica-de-auditoria.md",
    "ADR-005-custodia-openbao.md",
)
SECCIONES: Final = (
    "Estado",
    "Contexto",
    "Decisión",
    "Alternativas descartadas",
    "Consecuencias",
    "Cómo se verifica",
)
MIN_CARACTERES: Final = 20
FRASE: Final = re.compile(r"detener(?:se|me|nos)?\s+y\s+preguntar", re.IGNORECASE)
RUTA_DE_PRUEBA: Final = re.compile(r"(?<![\w/.-])(?:api/)?(tests/[\w./-]+\.py)")


def encabezados(texto: str) -> list[tuple[str, int, int]]:
    """`(título, inicio_del_cuerpo, fin_del_cuerpo)` de cada `## ` del documento."""
    marcas = list(re.finditer(r"^##\s+(?:\d+\.\s*)?(.+?)\s*$", texto, re.MULTILINE))
    salida: list[tuple[str, int, int]] = []
    for i, m in enumerate(marcas):
        fin = marcas[i + 1].start() if i + 1 < len(marcas) else len(texto)
        salida.append((m.group(1), m.end(), fin))
    return salida


def problemas_de_secciones(texto: str) -> list[str]:
    """Secciones ausentes, desordenadas o vacías."""
    hallados = encabezados(texto)
    titulos = [t for t, _, _ in hallados]
    problemas: list[str] = []
    for nombre in SECCIONES:
        if nombre not in titulos:
            problemas.append(f"falta la sección '{nombre}'")
    presentes = [t for t in titulos if t in SECCIONES]
    if presentes != [s for s in SECCIONES if s in presentes]:
        problemas.append(f"secciones fuera de orden: {presentes}")
    for titulo, ini, fin in hallados:
        if titulo in SECCIONES and len(texto[ini:fin].strip()) < MIN_CARACTERES:
            problemas.append(f"la sección '{titulo}' está vacía")
    return problemas


def cuerpo_de(texto: str, nombre: str) -> str:
    for titulo, ini, fin in encabezados(texto):
        if titulo == nombre:
            return texto[ini:fin]
    return ""


def rutas_citadas(texto: str) -> list[str]:
    return sorted(set(RUTA_DE_PRUEBA.findall(cuerpo_de(texto, "Cómo se verifica"))))


def rutas_inexistentes(texto: str, raiz: Path) -> list[str]:
    return [r for r in rutas_citadas(texto) if not (raiz / r).is_file()]


def test_estan_los_cinco_archivos_con_el_nombre_exacto() -> None:
    faltan = [n for n in ARCHIVOS if not (ADR_DIR / n).is_file()]
    assert faltan == []
    adr = sorted(p.name for p in ADR_DIR.glob("ADR-*.md"))
    assert adr == sorted(ARCHIVOS), adr


def test_cada_adr_tiene_las_seis_secciones_en_orden_y_con_contenido() -> None:
    problemas = {
        n: p
        for n in ARCHIVOS
        if (p := problemas_de_secciones((ADR_DIR / n).read_text(encoding="utf-8")))
    }
    assert problemas == {}


def test_cada_adr_dice_que_cambiar_la_decision_exige_detenerse_y_preguntar() -> None:
    sin_frase = [n for n in ARCHIVOS if not FRASE.search((ADR_DIR / n).read_text(encoding="utf-8"))]
    assert sin_frase == []


def test_cada_adr_cita_al_menos_una_prueba_y_todas_las_citadas_existen() -> None:
    sin_citas: list[str] = []
    inexistentes: dict[str, list[str]] = {}
    for n in ARCHIVOS:
        texto = (ADR_DIR / n).read_text(encoding="utf-8")
        if not rutas_citadas(texto):
            sin_citas.append(n)
        if faltan := rutas_inexistentes(texto, API_ROOT):
            inexistentes[n] = faltan
    assert sin_citas == []
    assert inexistentes == {}


def test_el_readme_nombra_los_cinco_adr_y_la_plantilla_de_seis_secciones() -> None:
    texto = (ADR_DIR / "README.md").read_text(encoding="utf-8")
    assert [n for n in ARCHIVOS if n not in texto] == []
    assert [s for s in SECCIONES if s not in texto] == []


# Controles con fuentes falsas ----------------------------------------------------------------

BUENO = "\n\n".join(
    [
        "# ADR-009",
        "## Estado\n\nAceptado el 2026-11-01, v0.1.",
        "## Contexto\n\nUn gimnasio pequeño.",
        "## Decisión\n\nMonolito modular con un esquema por módulo.",
        "## Alternativas descartadas\n\nMicroservicios y BaaS, por costo.",
        "## Consecuencias\n\nUn solo despliegue; cambiarlo cuesta.",
        "## Cómo se verifica\n\n`tests/architecture/test_adr_docs.py` y "
        "api/tests/core/test_health.py.\nCambiarla exige detenerse y preguntar.",
    ]
)


def test_control_un_documento_completo_pasa() -> None:
    assert problemas_de_secciones(BUENO) == []
    assert FRASE.search(BUENO)
    assert rutas_citadas(BUENO) == [
        "tests/architecture/test_adr_docs.py",
        "tests/core/test_health.py",
    ]
    assert rutas_inexistentes(BUENO, API_ROOT) == []


def test_control_una_seccion_vacia_o_ausente_se_detecta() -> None:
    vacia = BUENO.replace("Un gimnasio pequeño.", "")
    assert problemas_de_secciones(vacia) == ["la sección 'Contexto' está vacía"]
    sin_consecuencias = re.sub(
        r"## Consecuencias\n\n.*?\n\n(?=## Cómo)", "", BUENO, flags=re.DOTALL
    )
    assert problemas_de_secciones(sin_consecuencias) == ["falta la sección 'Consecuencias'"]


def test_control_una_ruta_inexistente_se_detecta() -> None:
    falso = BUENO.replace("tests/core/test_health.py", "tests/core/test_no_existe_jamas.py")
    assert rutas_inexistentes(falso, API_ROOT) == ["tests/core/test_no_existe_jamas.py"]


def test_control_las_rutas_fuera_de_como_se_verifica_no_cuentan() -> None:
    texto = BUENO.replace("Microservicios y BaaS", "tests/core/test_no_existe_jamas.py")
    assert rutas_inexistentes(texto, API_ROOT) == []
