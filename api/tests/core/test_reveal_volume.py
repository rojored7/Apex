"""`core/ratelimit.warn_reveal_volume` (S9-W0-3; S9-D5, M-5): el aviso de volumen de `reveal` sale
de `members/router.py` y suma una alerta interna del equipo.

- con 100 intentos en la hora (50 % de `members-reveal-hour`) no avisa; el 101 conserva el
  `logger.warning("reveal volume")` con `user_id` y `count` y llama `alert("reveal_volume",
  revelados=N)` una sola vez por usuario y hora (el 102 no repite);
- el contexto de la alerta es exactamente `{"revelados": N}`: nunca el id del usuario ni del socio;
- otro usuario alerta aparte; pasada la hora, el mismo usuario vuelve a alertar;
- un sink que lanza, o `alert` parcheado para lanzar `ValueError`, no propaga (el `reveal` no da
  500): la llamada va en su propio `try`.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, Request

from app.core import alerts, ratelimit
from app.core.clock import FrozenClock, reset_clock, set_clock
from app.core.ratelimit import USER_LIMITS, warn_reveal_volume

T0 = datetime(2026, 11, 15, 15, 0, 0, tzinfo=UTC)
BUCKET = "members-reveal-hour"
TOPE, VENTANA = USER_LIMITS[BUCKET]
AVISO = TOPE // 2  # 100: con ese conteo todavía no avisa (S3-D44)


class SinkEspia:
    def __init__(self) -> None:
        self.llamadas: list[tuple[str, dict[str, object]]] = []

    def send(self, code: str, context: Mapping[str, object]) -> None:
        self.llamadas.append((code, dict(context)))


class SinkRoto:
    def send(self, code: str, context: Mapping[str, object]) -> None:
        raise RuntimeError("canal caído")


@pytest.fixture
def sinks_aislados() -> Iterator[None]:
    foto = list(alerts._sinks)
    alerts._sinks[:] = []
    try:
        yield
    finally:
        alerts._sinks[:] = foto


@pytest.fixture
def reloj() -> Iterator[FrozenClock]:
    reloj = FrozenClock(T0)
    token = set_clock(reloj)
    try:
        yield reloj
    finally:
        reset_clock(token)


@pytest.fixture
def espia(sinks_aislados: None) -> SinkEspia:
    sink = SinkEspia()
    alerts.register_sink(sink)
    return sink


def _peticion() -> Request:
    aplicacion = FastAPI()
    aplicacion.state.user_limits = USER_LIMITS
    return Request({"type": "http", "app": aplicacion, "headers": [], "client": ("10.1.1.1", 1)})


async def _cargar(usuario: UUID, veces: int) -> None:
    for _ in range(veces):
        await ratelimit.record(BUCKET, str(usuario), window_s=VENTANA, kind="user")


async def test_con_100_en_la_hora_todavia_no_avisa_ni_alerta(
    reloj: FrozenClock, espia: SinkEspia, caplog: pytest.LogCaptureFixture
) -> None:
    usuario = uuid4()
    await _cargar(usuario, AVISO)
    caplog.set_level(logging.DEBUG)

    await warn_reveal_volume(_peticion(), usuario)

    assert espia.llamadas == []
    assert [r for r in caplog.records if r.getMessage() == "reveal volume"] == []


async def test_el_101_avisa_con_usuario_y_conteo_y_alerta_solo_con_el_conteo(
    reloj: FrozenClock, espia: SinkEspia, caplog: pytest.LogCaptureFixture
) -> None:
    usuario = uuid4()
    await _cargar(usuario, AVISO + 1)
    caplog.set_level(logging.DEBUG)

    await warn_reveal_volume(_peticion(), usuario)

    (aviso,) = [r for r in caplog.records if r.getMessage() == "reveal volume"]
    assert aviso.levelno == logging.WARNING
    assert str(getattr(aviso, "user_id", None)) == str(usuario)
    assert getattr(aviso, "count", None) == AVISO + 1
    # El contexto de la alerta es exactamente `{"revelados": N}`: sin id de usuario ni de socio.
    assert espia.llamadas == [("reveal_volume", {"revelados": AVISO + 1})]
    assert str(usuario) not in str(espia.llamadas)


async def test_el_102_no_repite_la_alerta_en_la_misma_hora(
    reloj: FrozenClock, espia: SinkEspia, caplog: pytest.LogCaptureFixture
) -> None:
    usuario = uuid4()
    await _cargar(usuario, AVISO + 1)
    caplog.set_level(logging.DEBUG)
    await warn_reveal_volume(_peticion(), usuario)

    await _cargar(usuario, 1)
    await warn_reveal_volume(_peticion(), usuario)

    assert len(espia.llamadas) == 1
    # El registro sí se repite en cada petición por encima del umbral (conducta de S3-D44).
    assert len([r for r in caplog.records if r.getMessage() == "reveal volume"]) == 2


async def test_otro_usuario_alerta_aparte(reloj: FrozenClock, espia: SinkEspia) -> None:
    primero, segundo = uuid4(), uuid4()
    await _cargar(primero, AVISO + 1)
    await _cargar(segundo, AVISO + 5)

    await warn_reveal_volume(_peticion(), primero)
    await warn_reveal_volume(_peticion(), segundo)

    assert espia.llamadas == [
        ("reveal_volume", {"revelados": AVISO + 1}),
        ("reveal_volume", {"revelados": AVISO + 5}),
    ]


async def test_pasada_la_hora_el_mismo_usuario_vuelve_a_alertar(
    reloj: FrozenClock, espia: SinkEspia
) -> None:
    usuario = uuid4()
    await _cargar(usuario, AVISO + 1)
    await warn_reveal_volume(_peticion(), usuario)
    reloj.advance(hours=1, minutes=1)
    await _cargar(usuario, AVISO + 1)

    await warn_reveal_volume(_peticion(), usuario)

    assert len(espia.llamadas) == 2


async def test_un_sink_que_lanza_no_propaga(
    reloj: FrozenClock, sinks_aislados: None, caplog: pytest.LogCaptureFixture
) -> None:
    alerts.register_sink(SinkRoto())
    usuario = uuid4()
    await _cargar(usuario, AVISO + 1)

    await warn_reveal_volume(_peticion(), usuario)  # no lanza


async def test_alert_que_lanza_value_error_no_propaga(
    reloj: FrozenClock, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def _rota(code: str, **context: object) -> None:
        raise ValueError("clave no admitida")

    monkeypatch.setattr(ratelimit, "alert", _rota)
    usuario = uuid4()
    await _cargar(usuario, AVISO + 1)
    caplog.set_level(logging.DEBUG)

    await warn_reveal_volume(_peticion(), usuario)  # el `reveal` no da 500

    assert [r for r in caplog.records if r.getMessage() == "reveal volume"]
    assert str(usuario) not in "".join(
        str(getattr(r, "error_detail", "")) for r in caplog.records if r.name == "app.ratelimit"
    )


def test_reset_store_olvida_las_alertas_ya_emitidas() -> None:
    """La memoria de «una vez por usuario y hora» es del proceso, como los almacenes: la vacía
    `reset_store` (las pruebas y el reinicio del contenedor)."""
    ratelimit._reveal_alertado["x"] = 1.0
    ratelimit.reset_store()
    assert ratelimit._reveal_alertado == {}
