"""`scripts/dev/telegram_fake.py` (S5-B4; S5-D78). Rojo B4.

Se carga por ruta (el script vive fuera del paquete) y se prueba su función pura `handle`, sin red:
acepta `POST /bot<token>/sendMessage` con `chat_id` y `text`, responde como Telegram y devuelve la
línea que va a stdout (el JSON recibido, nunca el token). Estático: solo biblioteca estándar.
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "telegram_fake.py"
TOKEN = "123456:AAH-token-no-real-1234567890"  # noqa: S105
RUTA = f"/bot{TOKEN}/sendMessage"


def _cargar() -> ModuleType:
    especificacion = importlib.util.spec_from_file_location("telegram_fake", SCRIPT)
    assert especificacion is not None and especificacion.loader is not None
    modulo = importlib.util.module_from_spec(especificacion)
    especificacion.loader.exec_module(modulo)
    return modulo


@pytest.fixture
def fake() -> ModuleType:
    return _cargar()


def _cuerpo(**datos: object) -> bytes:
    return json.dumps({"chat_id": "-100123", "text": "Respaldo con problemas", **datos}).encode()


def test_el_script_existe_y_usa_solo_la_biblioteca_estandar() -> None:
    assert SCRIPT.is_file()
    arbol = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    raices = {
        a.name.split(".")[0] for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names
    } | {
        (n.module or "").split(".")[0]
        for n in ast.walk(arbol)
        if isinstance(n, ast.ImportFrom) and n.level == 0
    }
    ajenas = {r for r in raices if r not in __import__("sys").stdlib_module_names}
    assert ajenas == set(), f"el fake corre en python:3.12-alpine pelado: {sorted(ajenas)}"


def test_send_message_responde_ok_y_escribe_el_json_sin_el_token(fake: ModuleType) -> None:
    estado, respuesta, linea = fake.handle("POST", RUTA, _cuerpo())

    assert estado == 200
    assert respuesta["ok"] is True
    assert isinstance(respuesta["result"], dict)
    assert isinstance(respuesta["result"]["message_id"], int)
    assert linea is not None and "\n" not in linea
    assert json.loads(linea) == json.loads(_cuerpo())
    assert TOKEN not in linea and "AAH-token" not in linea


@pytest.mark.parametrize(
    ("metodo", "ruta", "cuerpo", "estado"),
    [
        ("GET", RUTA, b"", 405),
        ("POST", f"/bot{TOKEN}/getMe", b"{}", 404),
        ("POST", "/sendMessage", b"{}", 404),
        ("POST", RUTA, b"no es json", 400),
        ("POST", RUTA, json.dumps({"text": "sin chat"}).encode(), 400),
        ("POST", RUTA, json.dumps({"chat_id": "1"}).encode(), 400),
        ("POST", RUTA, b'["lista"]', 400),
    ],
    ids=["get", "otro_metodo_api", "sin_bot", "no_json", "sin_chat", "sin_texto", "lista"],
)
def test_lo_que_no_es_un_send_message_valido_se_rechaza_sin_escribir(
    fake: ModuleType, metodo: str, ruta: str, cuerpo: bytes, estado: int
) -> None:
    codigo, respuesta, linea = fake.handle(metodo, ruta, cuerpo)

    assert codigo == estado
    assert respuesta["ok"] is False
    assert linea is None


def test_main_existe_y_es_invocable(fake: ModuleType) -> None:
    assert callable(fake.main)


# Revisión de seguridad (LOW 7): `Content-Length` hostil ----------------------------------------


def test_main_modulo_expone_el_tope_de_cuerpo_de_1_mib(fake: ModuleType) -> None:
    assert fake.MAX_BODY == 1024 * 1024


@pytest.mark.parametrize("largo", ["abc", "-5", "", "99999999999"])
def test_un_content_length_invalido_o_enorme_se_acota_sin_excepcion(
    fake: ModuleType, largo: str
) -> None:
    leido = fake.body_length(largo)

    assert 0 <= leido <= fake.MAX_BODY


def test_un_content_length_valido_se_respeta(fake: ModuleType) -> None:
    assert fake.body_length("123") == 123
    assert fake.body_length(None) == 0
