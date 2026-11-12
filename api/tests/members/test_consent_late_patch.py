"""`PATCH /members/{id}` con `data_consent: true` sobre un socio sin autorización (S6-C3, US-149;
S6-D46, M-11).

La autorización tardía fija `data_consent_at` con el reloj Y copia la versión vigente de la
política en `data_consent_version`; ambas columnas quedan en la fila `update` de auditoría con su
antes y su después. Un socio que ya tenía autorización no cambia (ni fila `update` ni evento). La
versión no la manda el cliente: `MemberPatch` es `extra="forbid"` y `data_consent_version` da 422
(el esquema del PATCH es cerrado, así que se elige 422 y no «se ignora»). `MemberUpdated` lleva
solo nombres de columnas, nunca la fecha ni la versión.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.crypto.keyring import Keyring
from app.modules.members import service
from app.modules.members.schemas import MemberDetailOut, MemberPatch
from tests.conftest import T0, Cabeceras, CapturarEventos, CrearUsuario, UsuarioPrueba
from tests.factories.members import make_member
from tests.members._apoyo import auditoria_del_socio, fila_socio, peticion, ruta_socio
from tests.members._consentimiento import HOY, VERSION, publicar_politica


@pytest.fixture
async def coach(usuario_real: CrearUsuario, bus_listo: Keyring) -> UsuarioPrueba:
    return await usuario_real("coach")


async def editar(
    session: AsyncSession, quien: UsuarioPrueba, member_id: UUID, **campos: Any
) -> MemberDetailOut:
    patch = MemberPatch.model_validate(campos)
    with peticion(session, quien.id):
        salida = await service.update(session, member_id, patch, role=quien.role)
        await session.commit()
    return salida


async def test_la_autorizacion_tardia_fija_la_fecha_y_copia_la_version_vigente(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    await publicar_politica(session, coach.id, corte=HOY)
    socio = await make_member(session, data_consent_at=None)

    salida = await editar(session, coach, socio.id, data_consent=True)

    fila = await fila_socio(session, socio.id)
    assert fila["data_consent_at"] == reloj.now_utc()
    assert fila["data_consent_version"] == VERSION
    assert salida.data_consent_at == reloj.now_utc()
    assert salida.data_consent_version == VERSION
    assert salida.warnings == []


async def test_sin_corte_la_autorizacion_tardia_tambien_copia_la_version(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    await publicar_politica(session, coach.id, corte=None)
    socio = await make_member(session, data_consent_at=None)

    await editar(session, coach, socio.id, data_consent=True)

    assert (await fila_socio(session, socio.id))["data_consent_version"] == VERSION


async def test_la_version_copiada_es_la_vigente_al_momento_de_la_autorizacion(
    session: AsyncSession, coach: UsuarioPrueba
) -> None:
    await publicar_politica(session, coach.id, corte=None, version="2026-02")
    socio = await make_member(session, data_consent_at=None)

    await editar(session, coach, socio.id, data_consent=True)

    assert (await fila_socio(session, socio.id))["data_consent_version"] == "2026-02"


async def test_la_auditoria_update_lleva_fecha_y_version_con_antes_y_despues(
    session: AsyncSession, coach: UsuarioPrueba, reloj: FrozenClock
) -> None:
    await publicar_politica(session, coach.id, corte=HOY)
    socio = await make_member(session, data_consent_at=None)

    await editar(session, coach, socio.id, data_consent=True)

    (update,) = await auditoria_del_socio(session, socio.id, "update")
    assert set(update["after"]) == {"data_consent_at", "data_consent_version"}
    assert update["after"]["data_consent_version"] == VERSION
    assert update["before"] is not None
    assert update["before"].get("data_consent_at") is None
    assert update["before"].get("data_consent_version") is None
    assert update["user_id"] == coach.id


async def test_member_updated_nombra_las_columnas_y_no_lleva_valores(
    session: AsyncSession,
    coach: UsuarioPrueba,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    await publicar_politica(session, coach.id, corte=HOY)
    socio = await make_member(session, data_consent_at=None)
    recibidos = capturar_eventos(service.MemberUpdated)

    await editar(session, coach, socio.id, data_consent=True)

    (evento,) = recibidos
    assert evento.member_id == socio.id
    assert "data_consent_at" in evento.changed_fields
    texto = repr(evento)
    assert VERSION not in texto
    assert "2026-10-21" not in texto


async def test_un_socio_ya_autorizado_no_cambia_ni_audita_ni_emite(
    session: AsyncSession,
    coach: UsuarioPrueba,
    reloj: FrozenClock,
    capturar_eventos: CapturarEventos,
) -> None:
    await publicar_politica(session, coach.id, corte=HOY)
    original = T0 - timedelta(days=90)
    socio = await make_member(session, data_consent_at=original, data_consent_version="2025-01")
    antes = await fila_socio(session, socio.id)
    recibidos = capturar_eventos(service.MemberUpdated)

    salida = await editar(session, coach, socio.id, data_consent=True)

    despues = await fila_socio(session, socio.id)
    assert despues["data_consent_at"] == original
    assert despues["data_consent_version"] == "2025-01"
    assert despues == antes
    assert salida.data_consent_version == "2025-01"
    assert await auditoria_del_socio(session, socio.id, "update") == []
    assert recibidos == []


# HTTP: la versión no la manda el cliente (M-11) -----------------------------------------------


async def test_http_la_autorizacion_tardia_responde_la_ficha_con_la_version(
    app_http: AsyncClient,
    coach: UsuarioPrueba,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    await publicar_politica(session, coach.id, corte=HOY)
    socio = await make_member(session, data_consent_at=None)

    r = await app_http.patch(
        ruta_socio(socio.id), json={"data_consent": True}, headers=cabeceras(coach)
    )

    assert r.status_code == 200, r.text
    assert r.json()["data_consent_version"] == VERSION
    assert r.json()["warnings"] == []


@pytest.mark.parametrize("campo", ["data_consent_version", "data_consent_at", "enforce_consent"])
async def test_http_el_cliente_no_puede_enviar_la_version_ni_la_fecha_ni_enforce_consent(
    app_http: AsyncClient,
    coach: UsuarioPrueba,
    cabeceras: Cabeceras,
    session: AsyncSession,
    campo: str,
) -> None:
    await publicar_politica(session, coach.id, corte=HOY)
    socio = await make_member(session, data_consent_at=None)
    socio_id = socio.id
    antes = await fila_socio(session, socio_id)

    r = await app_http.patch(
        ruta_socio(socio_id),
        json={"data_consent": True, campo: "2000-01"},
        headers=cabeceras(coach),
    )

    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"
    assert await fila_socio(session, socio_id) == antes
