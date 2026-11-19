"""`POST /athletes/{member_id}/metrics/{metric_id}/reveal` por HTTP (S9-A2, US-179; S9-D15, S9-D34,
S9-D35; M-4, L-2). Contrato del blueprint §3, ruta 3.

- admin y coach: 200 `{field, value}` con `Cache-Control: no-store`; la auditoría guarda la IP
  del cliente, nunca el valor; `member` 403, sin token 401, quiosco 403 `kiosk_mode`;
- 422 de `field` (otro nombre, vacío, nulo, ausente, claves de más) sin repetir el valor;
- 404 `metric_not_found` (de otro socio o inexistente) y `member_not_found`; 409 `metric_voided`;
- socio dado de baja: admin 200, coach 403 `forbidden` sin fila `decrypt` (M-4);
- blob que no decodifica: 500 `internal_error` sin el texto del error (L-2);
- custodio sellado: 503 `crypto_unavailable` con `Retry-After: 30` y sin filas;
- las tres cubetas compartidas con la ficha (`members-reveal`, `-hour`, `-day`) dan 429 y la alerta
  de volumen lleva solo `{"revelados": N}`, sin id de usuario (S9-D35);
- ni el stdout JSON ni `caplog` llevan el valor revelado.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import alerts, ratelimit
from app.core.clock import FrozenClock
from app.core.crypto.keyring import configure_keyring
from app.core.logging import configure_logging
from app.core.security import create_access_token
from tests.athletes._apoyo import alta, ops_de, reveals_de, ruta_reveal
from tests.auth._sesion import ORIGEN
from tests.conftest import Cabeceras, CrearUsuario, UsuarioPrueba
from tests.factories.athletes import make_metric
from tests.factories.triggers import disable_user_sql
from tests.notifications._apoyo_avisos import ANTES, socio

pytestmark = pytest.mark.usefixtures("reloj", "bus_listo")

POR_MINUTO = 30
POR_HORA = 200
POR_DIA = 600
AVISO_HORARIO = 100  # 50 % de `members-reveal-hour` (S3-D44)


class SinkEspia:
    def __init__(self) -> None:
        self.llamadas: list[tuple[str, dict[str, object]]] = []

    def send(self, code: str, context: Mapping[str, object]) -> None:
        self.llamadas.append((code, dict(context)))


@pytest.fixture
def espia() -> Iterator[SinkEspia]:
    foto = list(alerts._sinks)
    alerts._sinks[:] = []
    sink = SinkEspia()
    alerts.register_sink(sink)
    try:
        yield sink
    finally:
        alerts._sinks[:] = foto


async def _cargar(bucket: str, usuario: UsuarioPrueba, veces: int, ventana_s: int) -> None:
    for _ in range(veces):
        await ratelimit.record(bucket, str(usuario.id), window_s=ventana_s, kind="user")


async def _escena(
    session: AsyncSession, usuario_real: CrearUsuario, rol: str = "coach", **cambios: Any
) -> tuple[UsuarioPrueba, str, Any]:
    quien = await usuario_real(rol)
    miembro = await socio(session, consentido=True)
    medicion = await alta(session, quien.id, miembro.id, **cambios)
    return quien, ruta_reveal(miembro.id, medicion.id), medicion


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_reciben_el_valor_en_claro(
    rol: str,
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    quien, ruta, medicion = await _escena(session, usuario_real, rol)
    metric_id = medicion.id

    r = await app_http.post(ruta, json={"field": "weight_g"}, headers=cabeceras(quien))

    assert r.status_code == 200, r.text
    assert r.json() == {"field": "weight_g", "value": 62_500}
    assert r.headers["cache-control"] == "no-store"
    (fila,) = await reveals_de(session, metric_id)
    assert (fila["user_id"], fila["after"]) == (quien.id, {"field": "weight_g", "ip": "127.0.0.1"})
    assert len(await ops_de(session, metric_id, "decrypt")) == 1


async def test_las_notas_salen_como_texto_y_un_campo_vacio_como_null(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    quien, ruta, medicion = await _escena(session, usuario_real, height_cm=None)
    h = cabeceras(quien)

    notas = await app_http.post(ruta, json={"field": "notes"}, headers=h)
    vacio = await app_http.post(ruta, json={"field": "height_cm"}, headers=h)

    assert notas.json() == {"field": "notes", "value": "Primera medición del año"}
    assert vacio.status_code == 200 and vacio.json() == {"field": "height_cm", "value": None}
    # P6 (S9-D37): sondear un campo vacío también deja su fila `reveal`.
    filas = await reveals_de(session, medicion.id)
    assert sorted(f["after"]["field"] for f in filas) == ["height_cm", "notes"]


async def test_socio_403_y_sin_token_401_sin_filas(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    _, ruta, medicion = await _escena(session, usuario_real)
    metric_id = medicion.id
    rol_socio = await usuario_real("member")

    r = await app_http.post(ruta, json={"field": "weight_g"}, headers=cabeceras(rol_socio))
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert "62500" not in r.text
    sin = await app_http.post(ruta, json={"field": "weight_g"})
    assert sin.status_code == 401 and sin.json()["error"]["code"] == "unauthorized"
    assert await reveals_de(session, metric_id) == []


async def test_en_modo_quiosco_403_kiosk_mode_sin_filas(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
    session: AsyncSession,
) -> None:
    quien, ruta, medicion = await _escena(session, usuario_real)
    metric_id = medicion.id
    acceso = create_access_token(quien.id, "coach", None, reloj, kiosk=True)
    cab = {"Authorization": f"Bearer {acceso}", "Origin": ORIGEN}

    r = await app_http.post(ruta, json={"field": "weight_g"}, headers=cab)

    assert r.status_code == 403 and r.json()["error"]["code"] == "kiosk_mode"
    assert await reveals_de(session, metric_id) == []


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"field": "first_name"},
        {"field": "weight_kg"},
        {"field": "WEIGHT_G"},
        {"field": ""},
        {"field": None},
        {},
    ],
    ids=["nombre", "otro", "mayusculas", "vacio", "nulo", "sin-campo"],
)
async def test_un_campo_que_no_se_revela_da_422_con_field_sin_repetir_el_valor(
    cuerpo: dict[str, object],
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    quien, ruta, medicion = await _escena(session, usuario_real)
    metric_id = medicion.id

    r = await app_http.post(ruta, json=cuerpo, headers=cabeceras(quien))

    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", "field")
    valor = cuerpo.get("field")
    if valor:
        assert str(valor) not in r.text
    assert r.headers["cache-control"] == "no-store"
    assert await reveals_de(session, metric_id) == []


async def test_un_cuerpo_con_claves_de_mas_da_422(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    quien, ruta, _ = await _escena(session, usuario_real)

    r = await app_http.post(
        ruta, json={"field": "weight_g", "purpose": "export"}, headers=cabeceras(quien)
    )

    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "purpose"


async def test_ids_que_no_son_uuid_dan_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    quien = await usuario_real("coach")
    r = await app_http.post(
        "/api/v1/athletes/no-es-uuid/metrics/tampoco/reveal",
        json={"field": "weight_g"},
        headers=cabeceras(quien),
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "member_id"


async def test_medicion_de_otro_socio_o_inexistente_da_404_metric_not_found(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    quien, _, medicion = await _escena(session, usuario_real)
    metric_id = medicion.id
    ajeno = await socio(session, consentido=True)
    ruta_ajena = ruta_reveal(ajeno.id, metric_id)
    h = cabeceras(quien)

    r = await app_http.post(ruta_ajena, json={"field": "weight_g"}, headers=h)

    assert r.status_code == 404 and r.json()["error"]["code"] == "metric_not_found"
    assert "62500" not in r.text
    assert await reveals_de(session, metric_id) == []
    assert await ops_de(session, metric_id, "decrypt") == []


async def test_socio_inexistente_da_404_member_not_found(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    quien, _, medicion = await _escena(session, usuario_real)
    r = await app_http.post(
        ruta_reveal("00000000-0000-4000-8000-000000000999", medicion.id),
        json={"field": "weight_g"},
        headers=cabeceras(quien),
    )
    assert r.status_code == 404 and r.json()["error"]["code"] == "member_not_found"


async def test_medicion_anulada_da_409_metric_voided(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    quien = await usuario_real("coach")
    miembro = await socio(session, consentido=True)
    medicion = await make_metric(session, miembro.id, voided=True)
    metric_id = medicion.id
    ruta = ruta_reveal(miembro.id, metric_id)

    r = await app_http.post(ruta, json={"field": "weight_g"}, headers=cabeceras(quien))

    assert r.status_code == 409 and r.json()["error"]["code"] == "metric_voided"
    assert r.headers["cache-control"] == "no-store"
    assert await reveals_de(session, metric_id) == []
    assert await ops_de(session, metric_id, "decrypt") == []


async def test_socio_dado_de_baja_admin_200_y_coach_403_sin_decrypt(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    admin = await usuario_real("admin")
    coach = await usuario_real("coach")
    baja = await socio(session, consentido=True, deleted_at=ANTES, status="inactive")
    medicion = await make_metric(session, baja.id)
    metric_id = medicion.id
    ruta = ruta_reveal(baja.id, metric_id)

    r = await app_http.post(ruta, json={"field": "weight_g"}, headers=cabeceras(coach))
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"
    assert "62500" not in r.text
    assert await reveals_de(session, metric_id) == []
    assert await ops_de(session, metric_id, "decrypt") == []

    r = await app_http.post(ruta, json={"field": "weight_g"}, headers=cabeceras(admin))
    assert r.status_code == 200 and r.json()["value"] == 62_500
    assert len(await reveals_de(session, metric_id)) == 1


async def test_un_blob_que_no_decodifica_da_500_internal_error_sin_el_texto(
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    quien, ruta, medicion = await _escena(session, usuario_real)
    metric_id = medicion.id
    await session.execute(text(disable_user_sql("athletes.body_metrics")))
    await session.execute(
        text("UPDATE athletes.body_metrics SET height_cm = weight_g WHERE id = :i"),
        {"i": metric_id},
    )
    await session.commit()
    transporte = ASGITransport(app=api_prueba, raise_app_exceptions=False)

    async with AsyncClient(transport=transporte, base_url="http://t") as cliente:
        r = await cliente.post(ruta, json={"field": "height_cm"}, headers=cabeceras(quien))

    assert r.status_code == 500, r.text
    error = r.json()["error"]
    assert error["code"] == "internal_error"
    for fragmento in ("MetricDecodeError", "62500", "apx1.", "height_cm"):
        assert fragmento not in r.text, fragmento
    assert await reveals_de(session, metric_id) == []


async def test_con_el_custodio_sellado_503_crypto_unavailable_sin_filas(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    quien, ruta, medicion = await _escena(session, usuario_real)
    metric_id = medicion.id
    configure_keyring(None)  # el custodio se selló: no hay llaves en memoria

    r = await app_http.post(ruta, json={"field": "weight_g"}, headers=cabeceras(quien))

    assert r.status_code == 503, r.text
    assert r.json()["error"]["code"] == "crypto_unavailable"
    assert r.headers["retry-after"] == "30"
    assert r.headers["cache-control"] == "no-store"
    assert "62500" not in r.text
    assert await reveals_de(session, metric_id) == []


# Cubetas compartidas con la ficha (S9-D15) y alerta de volumen (S9-D35) ------------------------


async def test_la_31_en_un_minuto_da_429_por_members_reveal_y_otro_usuario_pasa(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    quien, ruta, _ = await _escena(session, usuario_real)
    otro = await usuario_real("coach")
    for numero in range(POR_MINUTO):
        r = await app_http.post(ruta, json={"field": "weight_g"}, headers=cabeceras(quien))
        assert r.status_code == 200, (numero, r.text)
    caplog.set_level(logging.WARNING)

    r = await app_http.post(ruta, json={"field": "weight_g"}, headers=cabeceras(quien))

    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert "members-reveal" in [getattr(rec, "bucket", None) for rec in caplog.records]
    assert "62500" not in r.text
    r = await app_http.post(ruta, json={"field": "weight_g"}, headers=cabeceras(otro))
    assert r.status_code == 200, r.text


async def test_la_cubeta_horaria_de_la_ficha_tambien_limita_el_reveal_de_medidas(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    quien, ruta, medicion = await _escena(session, usuario_real)
    metric_id = medicion.id
    await _cargar("members-reveal-hour", quien, POR_HORA, 3600)
    caplog.set_level(logging.WARNING)

    r = await app_http.post(ruta, json={"field": "weight_g"}, headers=cabeceras(quien))

    assert r.status_code == 429, r.text
    assert "members-reveal-hour" in [getattr(rec, "bucket", None) for rec in caplog.records]
    assert await reveals_de(session, metric_id) == []


async def test_la_601_en_un_dia_da_429_por_members_reveal_day(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    quien, ruta, _ = await _escena(session, usuario_real)
    await _cargar("members-reveal-day", quien, POR_DIA - 1, 86400)
    r = await app_http.post(ruta, json={"field": "weight_g"}, headers=cabeceras(quien))
    assert r.status_code == 200, r.text  # la 600 todavía entra
    caplog.set_level(logging.WARNING)

    r = await app_http.post(ruta, json={"field": "weight_g"}, headers=cabeceras(quien))

    assert r.status_code == 429, r.text
    assert "members-reveal-day" in [getattr(rec, "bucket", None) for rec in caplog.records]


async def test_con_100_en_la_hora_todavia_no_alerta(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    espia: SinkEspia,
) -> None:
    quien, ruta, _ = await _escena(session, usuario_real)
    await _cargar("members-reveal-hour", quien, AVISO_HORARIO - 1, 3600)

    r = await app_http.post(ruta, json={"field": "weight_g"}, headers=cabeceras(quien))

    assert r.status_code == 200, r.text
    assert espia.llamadas == []


async def test_al_pasar_de_100_en_la_hora_alerta_solo_con_el_conteo(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    espia: SinkEspia,
    caplog: pytest.LogCaptureFixture,
) -> None:
    quien, ruta, medicion = await _escena(session, usuario_real)
    metric_id = medicion.id
    await _cargar("members-reveal-hour", quien, AVISO_HORARIO, 3600)
    caplog.set_level(logging.DEBUG)

    r = await app_http.post(ruta, json={"field": "weight_g"}, headers=cabeceras(quien))

    assert r.status_code == 200, r.text
    assert espia.llamadas == [("reveal_volume", {"revelados": AVISO_HORARIO + 1})]
    volcado = str(espia.llamadas)
    for ajeno in (str(quien.id), str(metric_id), "62500"):
        assert ajeno not in volcado, ajeno
    (aviso,) = [r_ for r_ in caplog.records if r_.getMessage() == "reveal volume"]
    assert str(getattr(aviso, "user_id", None)) == str(quien.id)
    assert str(metric_id) not in str(aviso.__dict__)


# Registros -----------------------------------------------------------------------------------


async def test_los_logs_no_llevan_el_valor_revelado(
    app_http: AsyncClient,
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    quien, ruta, _ = await _escena(
        session, usuario_real, weight_g=73_417, notes="Nota privada de la atleta"
    )
    configure_logging(api_prueba.state.settings)
    caplog.set_level(logging.DEBUG)

    for campo in ("weight_g", "notes"):
        r = await app_http.post(ruta, json={"field": campo}, headers=cabeceras(quien))
        assert r.status_code == 200, (campo, r.text)

    salida = capsys.readouterr()
    stdout = salida.out + salida.err
    assert "http_request" in stdout, "no se capturó el log JSON de acceso"
    texto = stdout + caplog.text + " ".join(str(rec.__dict__) for rec in caplog.records)
    for claro in ("73417", "073417", "Nota privada de la atleta", "apx1."):
        assert claro not in texto, claro
