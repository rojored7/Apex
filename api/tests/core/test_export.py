"""`core/export.py` (S5-B12, US-138, US-139; S5-D41, S5-D60, S5-D82; L-6). Rojo B12.

- `escape_formula`: apóstrofo si empieza por `=`, `+`, `-`, `@`, tabulador o retorno de carro;
  `+57...` también (L-6, documentado); el resto queda igual; es idempotente en lo ya escapado.
- `csv_stream`: BOM UTF-8 una sola vez al inicio, `;`, `\\r\\n`, comillas mínimas (solo si hay `;`,
  `"` o salto de línea; la comilla se duplica), enteros tal cual (sin apóstrofo, `-5000` incluido),
  un fragmento por fila y perezoso; NO escapa fórmulas (lo hace quien arma la fila).
- `single_flight`: un flujo por usuario; el segundo lanza `ExportInProgress` (409
  `export_in_progress`); se libera al salir, también por excepción; otro usuario no estorba.
- `EXPORT_MAX_ROWS == 20_000` y es el valor por defecto de `Settings.EXPORT_MAX_ROWS`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.core import export as export_modulo
from app.core.config import Settings
from app.core.export import (
    EXPORT_MAX_ROWS,
    FLIGHT_STALE_S,
    ExportInProgress,
    ExportTooLarge,
    csv_stream,
    escape_formula,
    guarded_body,
    single_flight,
)

BOM = b"\xef\xbb\xbf"


class CorteDelCliente(Exception):
    pass


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("=1+1", "'=1+1"),
        ("+57 300 765 4321", "'+57 300 765 4321"),  # L-6: el teléfono con prefijo también
        ("-5000", "'-5000"),
        ("@cmd", "'@cmd"),
        ("\tcolumna", "'\tcolumna"),
        ("\rretorno", "'\rretorno"),
        ('=HYPERLINK("http://x")', '\'=HYPERLINK("http://x")'),
    ],
)
def test_escape_formula_antepone_apostrofo_a_los_seis_disparadores(
    entrada: str, esperado: str
) -> None:
    assert escape_formula(entrada) == esperado


@pytest.mark.parametrize(
    "texto", ["", "Lucía", "a=1", "3001234567", "x+y", "correo@x.co", " =1", "'=ya escapado"]
)
def test_escape_formula_deja_igual_lo_que_no_empieza_por_un_disparador(texto: str) -> None:
    assert escape_formula(texto) == texto


def test_csv_stream_arma_bom_cabecera_y_filas_con_punto_y_coma_y_crlf() -> None:
    cuerpo = b"".join(csv_stream(["a", "b"], [["1", "2"], ["3", "4"]]))
    assert cuerpo == BOM + b"a;b\r\n1;2\r\n3;4\r\n"


def test_csv_stream_sin_filas_es_solo_bom_y_cabecera() -> None:
    assert b"".join(csv_stream(["a", "b"], [])) == BOM + b"a;b\r\n"


def test_csv_stream_el_bom_va_una_sola_vez_y_al_principio() -> None:
    cuerpo = b"".join(csv_stream(["a"], [["1"], ["2"]]))
    assert cuerpo.startswith(BOM)
    assert cuerpo.count(BOM) == 1


def test_csv_stream_comillas_minimas_y_comilla_duplicada() -> None:
    cuerpo = b"".join(csv_stream(["c"], [["x;y"], ['dice "hola"'], ["l1\nl2"], ["simple"]]))
    esperado = BOM + b'c\r\n"x;y"\r\n"dice ""hola"""\r\n"l1\nl2"\r\nsimple\r\n'
    assert cuerpo == esperado


def test_csv_stream_los_enteros_salen_sin_apostrofo_ni_comillas() -> None:
    cuerpo = b"".join(csv_stream(["monto"], [[120000], [-5000], [0]]))
    assert cuerpo == BOM + b"monto\r\n120000\r\n-5000\r\n0\r\n"


def test_csv_stream_codifica_utf_8() -> None:
    cuerpo = b"".join(csv_stream(["nombre"], [["José Muñoz"]]))
    assert cuerpo.endswith("José Muñoz\r\n".encode())


def test_csv_stream_no_escapa_formulas_eso_es_de_quien_arma_la_fila() -> None:
    cuerpo = b"".join(csv_stream(["c"], [["=1+1"]]))
    assert cuerpo == BOM + b"c\r\n=1+1\r\n"


def test_csv_stream_acepta_otro_delimitador() -> None:
    cuerpo = b"".join(csv_stream(["a", "b"], [["1", "2"]], delimiter=","))
    assert cuerpo == BOM + b"a,b\r\n1,2\r\n"


def test_csv_stream_es_perezoso_cabecera_primero_y_una_fila_por_fragmento() -> None:
    consumidas: list[int] = []

    def filas() -> Iterator[list[str]]:
        for n in range(3):
            consumidas.append(n)
            yield [str(n)]

    flujo = csv_stream(["h"], filas())
    assert next(flujo) == BOM + b"h\r\n"
    assert consumidas == []
    assert next(flujo) == b"0\r\n"
    assert consumidas == [0]
    assert list(flujo) == [b"1\r\n", b"2\r\n"]


def test_single_flight_el_segundo_del_mismo_usuario_lanza_export_in_progress() -> None:
    usuario = uuid4()
    with single_flight(usuario), pytest.raises(ExportInProgress) as error:
        with single_flight(usuario):
            pass
    assert error.value.status == 409
    assert error.value.code == "export_in_progress"


def test_single_flight_otro_usuario_no_estorba() -> None:
    with single_flight(uuid4()), single_flight(uuid4()):
        pass


def test_single_flight_se_libera_al_salir() -> None:
    usuario = uuid4()
    with single_flight(usuario):
        pass
    with single_flight(usuario):
        pass


def test_single_flight_se_libera_si_el_bloque_falla() -> None:
    usuario = uuid4()
    with pytest.raises(CorteDelCliente), single_flight(usuario):
        raise CorteDelCliente("se cortó")
    with single_flight(usuario):
        pass


def test_el_tope_por_defecto_es_20_mil_filas_y_export_too_large_es_422() -> None:
    assert EXPORT_MAX_ROWS == 20_000
    error = ExportTooLarge()
    assert (error.status, error.code) == (422, "export_too_large")


def test_settings_usa_el_mismo_tope_por_defecto(settings_prueba: Settings) -> None:
    assert settings_prueba.EXPORT_MAX_ROWS == EXPORT_MAX_ROWS


# Candado con dueño y latido (S5-D254) -----------------------------------------------------------


def test_un_flujo_caducado_reemplazado_no_borra_el_candado_del_segundo_al_liberarse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    usuario = uuid4()
    primero = single_flight(usuario)
    primero.acquire()
    with monkeypatch.context() as parche:
        parche.setattr(export_modulo, "FLIGHT_STALE_S", 0.0)
        segundo = single_flight(usuario)
        segundo.acquire()  # el primero caducó: lo reemplaza
    primero.release()  # no es el dueño: no toca la entrada del segundo
    with pytest.raises(ExportInProgress):
        single_flight(usuario).acquire()
    segundo.release()
    single_flight(usuario).acquire()
    single_flight(usuario).release()  # no es dueño: la entrada del anterior sigue
    with pytest.raises(ExportInProgress):
        single_flight(usuario).acquire()


def test_touch_renueva_el_instante_del_candado(monkeypatch: pytest.MonkeyPatch) -> None:
    ahora = [1000.0]
    monkeypatch.setattr(export_modulo, "time", SimpleNamespace(monotonic=lambda: ahora[0]))
    usuario = uuid4()
    vuelo = single_flight(usuario)
    vuelo.acquire()
    ahora[0] += FLIGHT_STALE_S - 1
    vuelo.touch()
    ahora[0] += FLIGHT_STALE_S - 1  # sin `touch` ya habría caducado
    with pytest.raises(ExportInProgress):
        single_flight(usuario).acquire()
    ahora[0] += FLIGHT_STALE_S
    single_flight(usuario).acquire()  # caducó de verdad


async def test_guarded_body_da_latido_en_cada_trozo_y_suelta_al_terminar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ahora = [1000.0]
    monkeypatch.setattr(export_modulo, "time", SimpleNamespace(monotonic=lambda: ahora[0]))
    usuario = uuid4()

    async def cuerpo() -> AsyncIterator[bytes]:
        for _ in range(3):
            yield b"x"

    vuelo = single_flight(usuario)
    vuelo.acquire()
    async for _ in guarded_body(vuelo, cuerpo()):
        ahora[0] += FLIGHT_STALE_S - 1
        with pytest.raises(ExportInProgress):
            single_flight(usuario).acquire()
    single_flight(usuario).acquire()  # terminó: el flujo quedó libre
