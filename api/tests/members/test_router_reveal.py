"""`POST /api/v1/members/{member_id}/reveal` por HTTP (S3-B10; US-074; D19, D27, M-1, L-12,
S3-D44, N-20, Q6).

- admin y coach: 200 `{field, value}` con el valor en claro y `Cache-Control: no-store`; la
  auditoría guarda la IP del cliente (`client_ip`), nunca el valor;
- `{"field": "first_name"}` (u otro campo no cifrado) da 422 `validation_error` con
  `field="field"`; un cuerpo con claves de más también (`extra="forbid"`);
- `member` 403 `forbidden` sin fila `reveal`; sin token 401; id inexistente 404
  `member_not_found`; id que no es UUID 422 `field="member_id"`;
- si el commit falla, la respuesta es el 500 del envelope y el cuerpo no lleva el valor (el
  `SessionDep` confirma antes de enviar, S2-R8);
- límites por usuario (S3-D44): la 31 en un minuto da 429 (`members-reveal`); la 201 en una hora
  da 429 (`members-reveal-hour`, con `reloj.advance` para salir de la ventana del minuto) y la
  ventana se libera pasada la hora; la 601 en un día da 429 (`members-reveal-day`: las 600 se
  cargan con `ratelimit.record` en la misma cubeta, 600 peticiones reales no aportan nada); el
  429 nombra la cubeta en el registro `rate limit`; otro usuario pasa;
- M-1: al pasar de 100 en la hora (50 % del cupo horario) aparece `logger.warning("reveal
  volume")` con `user_id` y `count` y sin valores; con 100 todavía no;
- ni el stdout JSON ni `caplog` llevan el valor revelado ni blobs.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as SyncSession

from app.core import ratelimit
from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from app.core.logging import configure_logging
from app.core.security import create_access_token
from tests.conftest import Cabeceras, ClienteDesde, CrearUsuario, UsuarioPrueba
from tests.factories.members import KNOWN, KNOWN_NORMALIZED, make_member
from tests.members._apoyo import MEMBERS, auditoria_del_socio, ruta_reveal

POR_MINUTO = 30
POR_HORA = 200
POR_DIA = 600
AVISO_HORARIO = 100  # 50 % de `members-reveal-hour` (S3-D44)


async def _reveals(session: AsyncSession, member_id: UUID) -> int:
    return len(await auditoria_del_socio(session, member_id, "reveal"))


async def _cargar(bucket: str, usuario: UsuarioPrueba, veces: int, ventana_s: int) -> None:
    """Marca `veces` intentos del usuario en la cubeta, como si hubieran pasado por la ruta."""
    for _ in range(veces):
        await ratelimit.record(bucket, str(usuario.id), window_s=ventana_s, kind="user")


@pytest.mark.parametrize("rol", ["admin", "coach"])
async def test_admin_y_coach_reciben_el_valor_en_claro(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    rol: str,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    quien = await usuario_real(rol)
    r = await app_http.post(
        ruta_reveal(socio_id), json={"field": "document"}, headers=cabeceras(quien)
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"field": "document", "value": KNOWN["document"]}
    assert r.headers["cache-control"] == "no-store"
    filas = await auditoria_del_socio(session, socio_id, "reveal")
    assert [(f["user_id"], f["after"]) for f in filas] == [
        (quien.id, {"field": "document", "ip": "127.0.0.1"})
    ]


async def test_el_contacto_de_emergencia_sale_como_objeto(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    coach = await usuario_real("coach")
    r = await app_http.post(
        ruta_reveal(socio_id), json={"field": "emergency_contact"}, headers=cabeceras(coach)
    )
    assert r.status_code == 200, r.text
    assert r.json() == {
        "field": "emergency_contact",
        "value": {"name": "Rosa", "phone": "3115550199", "relationship": None},
    }


async def test_la_auditoria_guarda_la_ip_del_cliente(
    cliente_desde: ClienteDesde,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    coach = await usuario_real("coach")
    cliente = cliente_desde("203.0.113.7")
    r = await cliente.post(ruta_reveal(socio_id), json={"field": "phone"}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    (fila,) = await auditoria_del_socio(session, socio_id, "reveal")
    assert fila["after"] == {"field": "phone", "ip": "203.0.113.7"}


async def test_un_dado_de_baja_tambien_se_revela(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
) -> None:
    socio = await make_member(
        session, deleted_at=reloj.now_utc() - timedelta(days=1), status="inactive"
    )
    socio_id = socio.id
    coach = await usuario_real("coach")
    r = await app_http.post(
        ruta_reveal(socio_id), json={"field": "document"}, headers=cabeceras(coach)
    )
    assert r.status_code == 200, r.text
    assert r.json()["value"] == KNOWN["document"]


# Validación, rol y existencia ------------------------------------------------------------------


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"field": "first_name"},
        {"field": "document_idx"},
        {"field": "notes"},
        {"field": ""},
        {"field": None},
        {},
    ],
    ids=["nombre", "indice", "notas", "vacio", "nulo", "sin-campo"],
)
async def test_un_campo_que_no_se_revela_da_422_con_field(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    cuerpo: dict[str, object],
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    coach = await usuario_real("coach")
    r = await app_http.post(ruta_reveal(socio_id), json=cuerpo, headers=cabeceras(coach))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", "field")
    assert await _reveals(session, socio_id) == 0


async def test_un_cuerpo_con_claves_de_mas_da_422(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    coach = await usuario_real("coach")
    r = await app_http.post(
        ruta_reveal(socio_id),
        json={"field": "document", "purpose": "mask"},
        headers=cabeceras(coach),
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "purpose"


async def test_el_rol_member_recibe_403_sin_fila_reveal(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    miembro = await usuario_real("member")
    r = await app_http.post(
        ruta_reveal(socio_id), json={"field": "document"}, headers=cabeceras(miembro)
    )
    assert r.status_code == 403, r.text
    assert r.json()["error"]["code"] == "forbidden"
    assert KNOWN["document"] not in r.text
    assert await _reveals(session, socio_id) == 0


async def test_sin_token_recibe_401(
    app_http: AsyncClient, session: AsyncSession, bus_listo: Keyring
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    r = await app_http.post(ruta_reveal(socio_id), json={"field": "document"})
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "unauthorized"
    assert await _reveals(session, socio_id) == 0


async def test_un_id_inexistente_da_404(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.post(
        ruta_reveal("00000000-0000-4000-8000-000000000999"),
        json={"field": "document"},
        headers=cabeceras(coach),
    )
    assert r.status_code == 404, r.text
    assert r.json()["error"]["code"] == "member_not_found"


async def test_un_id_que_no_es_uuid_da_422(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    coach = await usuario_real("coach")
    r = await app_http.post(
        f"{MEMBERS}/no-es-uuid/reveal", json={"field": "document"}, headers=cabeceras(coach)
    )
    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "member_id"


# El commit falla: 500 sin el valor (D19, S2-R8) ------------------------------------------------


async def test_si_el_commit_falla_el_500_no_lleva_el_valor(
    ops_tras_el_rollback: None,
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    coach = await usuario_real("coach")

    def _falla_al_confirmar(_sesion: SyncSession) -> None:
        raise RuntimeError("fallo simulado en before_commit")

    transporte = ASGITransport(app=api_prueba, raise_app_exceptions=False)
    # Primero en la lista: falla antes de que `oplog` vacíe su buffer en la transacción.
    event.listen(SyncSession, "before_commit", _falla_al_confirmar, insert=True)
    try:
        async with AsyncClient(transport=transporte, base_url="http://t") as cliente:
            r = await cliente.post(
                ruta_reveal(socio_id), json={"field": "document"}, headers=cabeceras(coach)
            )
    finally:
        event.remove(SyncSession, "before_commit", _falla_al_confirmar)
    assert r.status_code == 500, r.text
    assert r.json()["error"]["code"] == "internal_error"
    for valor in (*KNOWN_NORMALIZED, "apx1."):
        assert valor not in r.text, valor
    await session.rollback()  # lo que hace `get_session` al fallar el commit
    assert await _reveals(session, socio_id) == 0
    # El `decrypt` sí ocurrió y sobrevive al rollback (D19): lo confirmó otra conexión.
    consulta = text(
        "SELECT purpose FROM crypto.crypto_ops WHERE record_id = :id AND verb = 'decrypt'"
    )
    assert list(await session.scalars(consulta, {"id": socio_id})) == ["reveal"]


# Límites por usuario (S3-D44, M-1) ----------------------------------------------------------


async def test_la_31_en_un_minuto_da_429_y_otro_usuario_pasa(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    caplog: pytest.LogCaptureFixture,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    ruta = ruta_reveal(socio_id)  # el 429 revierte la sesión y expira el objeto
    coach = await usuario_real("coach")
    otro = await usuario_real("coach")
    for numero in range(POR_MINUTO):
        r = await app_http.post(ruta, json={"field": "phone"}, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    caplog.set_level(logging.WARNING)
    r = await app_http.post(ruta, json={"field": "phone"}, headers=cabeceras(coach))
    assert r.status_code == 429, r.text
    assert r.json()["error"]["code"] == "rate_limited"
    assert int(r.headers["retry-after"]) >= 1
    assert "members-reveal" in [getattr(rec, "bucket", None) for rec in caplog.records]
    assert KNOWN["phone"] not in r.text
    r = await app_http.post(ruta, json={"field": "phone"}, headers=cabeceras(otro))
    assert r.status_code == 200, r.text


async def test_la_201_en_una_hora_da_429_y_se_libera_pasada_la_hora(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    reloj: FrozenClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """200 peticiones reales en lotes de 30 (el reloj avanza un minuto entre lotes para salir de
    la ventana del minuto); la 201, dentro de la hora, da 429 por la cubeta horaria."""
    socio = await make_member(session, phone=None, email=None, birth_date=None)
    socio_id = socio.id
    ruta = ruta_reveal(socio_id)
    coach = await usuario_real("coach")
    for numero in range(POR_HORA):
        if numero and numero % POR_MINUTO == 0:
            reloj.advance(minutes=1)
        r = await app_http.post(ruta, json={"field": "document"}, headers=cabeceras(coach))
        assert r.status_code == 200, (numero, r.text)
    reloj.advance(minutes=1)
    caplog.set_level(logging.WARNING)
    r = await app_http.post(ruta, json={"field": "document"}, headers=cabeceras(coach))
    assert r.status_code == 429, r.text
    assert "members-reveal-hour" in [getattr(rec, "bucket", None) for rec in caplog.records]
    reloj.advance(hours=1)
    vigente = create_access_token(coach.id, "coach", None, reloj)  # el de T0 ya venció
    con_vigente = {**cabeceras(coach), "Authorization": f"Bearer {vigente}"}
    r = await app_http.post(ruta, json={"field": "document"}, headers=con_vigente)
    assert r.status_code == 200, r.text


async def test_la_601_en_un_dia_da_429(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    caplog: pytest.LogCaptureFixture,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    coach = await usuario_real("coach")
    await _cargar("members-reveal-day", coach, POR_DIA - 1, 86400)
    r = await app_http.post(
        ruta_reveal(socio_id), json={"field": "document"}, headers=cabeceras(coach)
    )
    assert r.status_code == 200, r.text  # la 600 todavía entra
    caplog.set_level(logging.WARNING)
    r = await app_http.post(
        ruta_reveal(socio_id), json={"field": "document"}, headers=cabeceras(coach)
    )
    assert r.status_code == 429, r.text
    assert "members-reveal-day" in [getattr(rec, "bucket", None) for rec in caplog.records]


def _avisos(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [rec for rec in caplog.records if rec.getMessage() == "reveal volume"]


async def test_con_100_en_la_hora_todavia_no_avisa(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    caplog: pytest.LogCaptureFixture,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    coach = await usuario_real("coach")
    await _cargar("members-reveal-hour", coach, AVISO_HORARIO - 1, 3600)
    caplog.set_level(logging.DEBUG)
    r = await app_http.post(
        ruta_reveal(socio_id), json={"field": "document"}, headers=cabeceras(coach)
    )
    assert r.status_code == 200, r.text
    assert _avisos(caplog) == []


async def test_al_pasar_de_100_en_la_hora_avisa_con_usuario_y_conteo_sin_valores(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    caplog: pytest.LogCaptureFixture,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    coach = await usuario_real("coach")
    await _cargar("members-reveal-hour", coach, AVISO_HORARIO, 3600)
    caplog.set_level(logging.DEBUG)
    r = await app_http.post(
        ruta_reveal(socio_id), json={"field": "document"}, headers=cabeceras(coach)
    )
    assert r.status_code == 200, r.text
    (aviso,) = _avisos(caplog)
    assert aviso.levelno == logging.WARNING
    assert str(getattr(aviso, "user_id", None)) == str(coach.id)
    assert getattr(aviso, "count", None) == AVISO_HORARIO + 1
    volcado = str(aviso.__dict__)
    for valor in (*KNOWN_NORMALIZED, "apx1.", str(socio_id)):
        assert valor not in volcado, valor


# Logs ------------------------------------------------------------------------------------------


async def test_los_logs_no_llevan_el_valor_revelado(
    app_http: AsyncClient,
    api_prueba: FastAPI,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    socio = await make_member(session)
    socio_id = socio.id
    configure_logging(api_prueba.state.settings)  # el handler escribe en el stdout de capsys
    caplog.set_level(logging.DEBUG)
    coach = await usuario_real("coach")
    for campo in ("document", "phone", "email", "birth_date", "emergency_contact"):
        r = await app_http.post(
            ruta_reveal(socio_id), json={"field": campo}, headers=cabeceras(coach)
        )
        assert r.status_code == 200, (campo, r.text)
    salida = capsys.readouterr()
    stdout = salida.out + salida.err
    assert "http_request" in stdout, "no se capturó el log JSON de acceso"
    texto = stdout + caplog.text + " ".join(str(rec.__dict__) for rec in caplog.records)
    for valor in (*KNOWN_NORMALIZED, "apx1."):
        assert valor not in texto, valor


async def test_no_queda_ningun_reveal_de_mas_en_la_base(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
    bus_listo: Keyring,
) -> None:
    """Una petición, una fila `reveal` y un `decrypt` con `purpose='reveal'`."""
    socio = await make_member(session)
    socio_id = socio.id
    coach = await usuario_real("coach")
    r = await app_http.post(
        ruta_reveal(socio_id), json={"field": "email"}, headers=cabeceras(coach)
    )
    assert r.status_code == 200, r.text
    assert await _reveals(session, socio_id) == 1
    consulta = text(
        "SELECT purpose FROM crypto.crypto_ops WHERE record_id = :id AND verb = 'decrypt'"
    )
    assert list(await session.scalars(consulta, {"id": socio_id})) == ["reveal"]
