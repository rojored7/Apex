"""Los `details` del job `notify` y su resumen son solo enteros y claves cerradas (S5-B8; S5-D35,
S5-D86, S3-D70). # Rojo B8

Por `ast` sobre `worker/jobs/notify.py`:
- toda clave de un diccionario `details=` / `JobResult(...)` es de `DETAIL_KEYS`, y ningún valor es
  una cadena (ni f-string): solo conteos;
- cada `alert("notify_summary", ...)` pasa solo los conteos del resumen como argumentos con nombre
  y ningún valor es una cadena;
- el job usa de verdad `generate_today`, `send_pending`, `try_load` y emite el resumen (si el job
  no hiciera nada, las reglas anteriores serían vacuas);
- ninguna clave de `DETAIL_KEYS` nombra a una persona o un dato de contacto.
Controles con fuentes falsas.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

from app.core.jobs import DETAIL_KEYS

SRC: Final = Path(__file__).resolve().parents[2] / "src" / "app"
JOB: Final = SRC / "worker" / "jobs" / "notify.py"
CONTEOS_RESUMEN: Final = frozenset({"generados", "pendientes", "enviados", "fallidos", "omitidos"})
CLAVES_DE_NOTIFY: Final = frozenset(
    {
        "generados",
        "ya_renovaron",
        "sin_consentimiento",
        "sin_reglas",
        "enviados",
        "fallidos",
        "omitidos",
        "pendientes",
        "sellado",
    }
)
PALABRAS_DE_PERSONA: Final = ("nombre", "name", "correo", "email", "telefono", "phone", "documento")


def _es_cadena(nodo: ast.expr) -> bool:
    return (isinstance(nodo, ast.Constant) and isinstance(nodo.value, str)) or isinstance(
        nodo, ast.JoinedStr
    )


def diccionarios_de_details(fuente: str) -> list[ast.Dict]:
    """Los literales `{...}` que son `details=` de una llamada o el `details` de una asignación."""
    arbol = ast.parse(fuente)
    salida: list[ast.Dict] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call):
            for kw in nodo.keywords:
                if kw.arg == "details" and isinstance(kw.value, ast.Dict):
                    salida.append(kw.value)
        elif isinstance(nodo, ast.Assign) and isinstance(nodo.value, ast.Dict):
            nombres = [t.id for t in nodo.targets if isinstance(t, ast.Name)]
            if any("detail" in n for n in nombres):
                salida.append(nodo.value)
    return salida


def problemas_de_details(fuente: str) -> list[str]:
    problemas: list[str] = []
    for dic in diccionarios_de_details(fuente):
        for clave, valor in zip(dic.keys, dic.values, strict=True):
            if not (isinstance(clave, ast.Constant) and clave.value in DETAIL_KEYS):
                problemas.append(f"clave fuera de DETAIL_KEYS en la línea {dic.lineno}")
            if _es_cadena(valor):
                problemas.append(f"valor de texto en details (línea {valor.lineno})")
    return problemas


def llamadas_a_alert(fuente: str, codigo: str) -> list[ast.Call]:
    salida: list[ast.Call] = []
    for nodo in ast.walk(ast.parse(fuente)):
        if (
            isinstance(nodo, ast.Call)
            and isinstance(nodo.func, ast.Name)
            and nodo.func.id == "alert"
            and nodo.args
            and isinstance(nodo.args[0], ast.Constant)
            and nodo.args[0].value == codigo
        ):
            salida.append(nodo)
    return salida


def problemas_de_resumen(fuente: str) -> list[str]:
    problemas: list[str] = []
    for llamada in llamadas_a_alert(fuente, "notify_summary"):
        if len(llamada.args) != 1 or any(kw.arg is None for kw in llamada.keywords):
            problemas.append("el resumen solo admite argumentos con nombre")
        for kw in llamada.keywords:
            if kw.arg not in CONTEOS_RESUMEN:
                problemas.append(f"argumento fuera del resumen: {kw.arg}")
            if _es_cadena(kw.value):
                problemas.append(f"valor de texto en el resumen: {kw.arg}")
    return problemas


def nombres_usados(fuente: str) -> set[str]:
    usados: set[str] = set()
    for nodo in ast.walk(ast.parse(fuente)):
        if isinstance(nodo, ast.Name):
            usados.add(nodo.id)
        elif isinstance(nodo, ast.Attribute):
            usados.add(nodo.attr)
    return usados


def cadenas_de_codigo(fuente: str) -> set[str]:
    """Literales de texto del código, sin docstrings ni expresiones sueltas."""
    arbol = ast.parse(fuente)
    sueltas = {
        id(n.value) for n in ast.walk(arbol) if isinstance(n, ast.Expr) and _es_cadena(n.value)
    }
    return {
        n.value
        for n in ast.walk(arbol)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in sueltas
    }


# Sobre el árbol real -----------------------------------------------------------------------------


def test_detail_keys_incluye_las_claves_de_notify() -> None:
    assert CLAVES_DE_NOTIFY <= DETAIL_KEYS, sorted(CLAVES_DE_NOTIFY - DETAIL_KEYS)


def test_ninguna_clave_de_notify_nombra_a_una_persona_o_un_dato_de_contacto() -> None:
    for clave in CLAVES_DE_NOTIFY:
        assert not any(p in clave for p in PALABRAS_DE_PERSONA), clave


def test_el_job_tiene_details_literales_y_todos_son_enteros_de_claves_cerradas() -> None:
    fuente = JOB.read_text(encoding="utf-8")
    assert diccionarios_de_details(fuente), "notify.py no arma ningún `details` literal"
    assert problemas_de_details(fuente) == []


def test_el_job_emite_notify_summary_solo_con_conteos() -> None:
    fuente = JOB.read_text(encoding="utf-8")
    assert llamadas_a_alert(fuente, "notify_summary"), "notify.py no emite notify_summary"
    assert problemas_de_resumen(fuente) == []


def test_el_job_usa_generar_enviar_y_recuperar_el_keyring() -> None:
    fuente = JOB.read_text(encoding="utf-8")
    assert {"generate_today", "send_pending", "try_load"} <= nombres_usados(fuente)
    assert "crypto_sealed" in cadenas_de_codigo(fuente)


def test_el_job_marca_sellado_cuando_omite_el_envio() -> None:
    assert "sellado" in cadenas_de_codigo(JOB.read_text(encoding="utf-8"))


# Controles con fuentes falsas --------------------------------------------------------------------


def test_control_una_clave_ajena_o_un_texto_en_details_se_detectan() -> None:
    falsa = (
        "def f(n):\n"
        "    return JobResult(ok=True, details={'enviados': 1, 'nombre': n, 'omitidos': 'dos'})\n"
    )
    assert len(problemas_de_details(falsa)) == 2


def test_control_un_details_limpio_no_da_problemas() -> None:
    limpia = "x = JobResult(ok=True, details={'enviados': 1, 'sellado': 1})\n"
    assert problemas_de_details(limpia) == []


def test_control_el_resumen_con_texto_o_argumentos_ajenos_se_detecta() -> None:
    falsa = (
        "alert('notify_summary', enviados=1, socio='Lucía')\n"
        "alert('notify_summary', fallidos=f'{x}')\n"
        "alert('notify_summary', **ctx)\n"
    )
    assert len(problemas_de_resumen(falsa)) >= 4


def test_control_un_resumen_limpio_no_da_problemas() -> None:
    limpia = "alert('notify_summary', enviados=n, fallidos=0, omitidos=0, pendientes=1)\n"
    assert problemas_de_resumen(limpia) == []
