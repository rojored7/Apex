"""Alta de socios y autorización de datos (S6-C3, US-149; S6-D46, M-11, Q16).

`POST /members` no cambia de contrato (`data_consent: bool`): la obligación nace de
`settings.privacy.consent_required_from`.

- con el corte vigente (hoy o pasado) el alta sin `data_consent=true` da 422 `validation_error`
  con `field = "data_consent_at"` y no crea nada; con `true` da 201 y copia la versión vigente de
  política (`data_consent_version`); sin política publicada que copiar, 409
  `privacy_version_missing`
  y tampoco crea nada;
- sin corte (fecha nula, Q16) o con corte futuro el alta sin autorización sigue dando 201 con
  `warnings = ["data_consent_missing"]`;
- `data_consent_version` y `enforce_consent` enviados por el cliente son 422 por `extra="forbid"`
  (M-11): la versión la decide el servidor y `enforce_consent` nunca va por HTTP;
- `service.create(..., enforce_consent=False)` (import y seed) no exige nada aunque el corte esté
  vigente.
"""

from __future__ import annotations

import inspect
from datetime import date
from typing import Any
from uuid import UUID

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import actor_scope
from app.core.crypto.keyring import Keyring
from app.modules.members import service
from app.modules.members.exceptions import MemberValidationError
from app.modules.members.schemas import MemberCreate
from app.modules.settings.service import update_section
from tests.conftest import T0, Cabeceras, CrearUsuario, UsuarioPrueba
from tests.factories.members import KNOWN_NORMALIZED
from tests.members._apoyo import MEMBERS, cuantos_socios, cuerpo, entrada, fila_socio
from tests.members._consentimiento import (
    AYER,
    HOY,
    MANANA,
    VERSION,
    publicar_politica,
    quitar_version,
)
from tests.settings._apoyo import PRIVACY_OK


@pytest.fixture
async def admin(usuario_real: CrearUsuario, bus_listo: Keyring) -> UsuarioPrueba:
    return await usuario_real("admin")


async def _alta(
    app_http: AsyncClient, cabeceras: Cabeceras, quien: UsuarioPrueba, **cambios: Any
) -> Any:
    return await app_http.post(MEMBERS, json=cuerpo(**cambios), headers=cabeceras(quien))


# Con el corte vigente -------------------------------------------------------------------------


@pytest.mark.parametrize("corte", [HOY, AYER], ids=["hoy", "pasado"])
async def test_con_el_corte_vigente_el_alta_sin_autorizacion_da_422_data_consent_at(
    app_http: AsyncClient,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    session: AsyncSession,
    corte: date,
) -> None:
    await publicar_politica(session, admin.id, corte=corte)
    antes = await cuantos_socios(session)

    r = await _alta(app_http, cabeceras, admin, data_consent=False)

    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert (error["code"], error["field"]) == ("validation_error", "data_consent_at")
    assert await cuantos_socios(session) == antes


async def test_con_el_corte_vigente_el_alta_sin_el_campo_tambien_da_422(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    """`data_consent` omitido vale `false`: es el mismo caso que enviarlo apagado."""
    await publicar_politica(session, admin.id, corte=HOY)
    datos = cuerpo()
    del datos["data_consent"]

    r = await app_http.post(MEMBERS, json=datos, headers=cabeceras(admin))

    assert r.status_code == 422, r.text
    assert r.json()["error"]["field"] == "data_consent_at"
    assert await cuantos_socios(session) == 0


@pytest.mark.parametrize("corte", [HOY, AYER], ids=["hoy", "pasado"])
async def test_con_el_corte_vigente_y_autorizacion_da_201_y_copia_la_version_publicada(
    app_http: AsyncClient,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    session: AsyncSession,
    corte: date,
) -> None:
    await publicar_politica(session, admin.id, corte=corte)

    r = await _alta(app_http, cabeceras, admin, data_consent=True)

    assert r.status_code == 201, r.text
    datos = r.json()
    assert datos["data_consent_version"] == VERSION
    assert datos["warnings"] == []
    fila = await fila_socio(session, UUID(datos["id"]))
    assert fila["data_consent_at"] == T0
    assert fila["data_consent_version"] == VERSION


async def test_la_version_copiada_es_la_vigente_al_momento_del_alta(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    await publicar_politica(session, admin.id, corte=HOY, version="2026-01")
    primero = await _alta(app_http, cabeceras, admin, data_consent=True)
    with actor_scope(admin.id):
        await update_section(
            session,
            "privacy",
            {**PRIVACY_OK, "policy_version": "2026-12", "consent_required_from": HOY},
            1,
            admin.id,
        )
        await session.commit()

    segundo = await _alta(
        app_http, cabeceras, admin, data_consent=True, document="1098765432", email=None
    )

    assert primero.status_code == 201 and segundo.status_code == 201, segundo.text
    assert primero.json()["data_consent_version"] == "2026-01"
    assert segundo.json()["data_consent_version"] == "2026-12"


async def test_con_el_corte_vigente_pero_sin_politica_publicada_da_409_privacy_version_missing(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    await publicar_politica(session, admin.id, corte=HOY)
    await quitar_version(session)

    r = await _alta(app_http, cabeceras, admin, data_consent=True)

    assert r.status_code == 409, r.text
    assert r.json()["error"]["code"] == "privacy_version_missing"
    assert await cuantos_socios(session) == 0


async def test_el_409_no_repite_ningun_dato_del_socio(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras, session: AsyncSession
) -> None:
    await publicar_politica(session, admin.id, corte=HOY)
    await quitar_version(session)

    r = await _alta(app_http, cabeceras, admin, data_consent=True)

    assert r.status_code == 409, r.text
    for valor in KNOWN_NORMALIZED:
        assert valor not in r.text, valor


# Sin corte o con corte futuro (Q16) -----------------------------------------------------------


@pytest.mark.parametrize("corte", [None, MANANA], ids=["sin-corte", "corte-futuro"])
async def test_sin_corte_vigente_el_alta_sin_autorizacion_sigue_dando_201_con_aviso(
    app_http: AsyncClient,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    session: AsyncSession,
    corte: date | None,
) -> None:
    await publicar_politica(session, admin.id, corte=corte)

    r = await _alta(app_http, cabeceras, admin, data_consent=False)

    assert r.status_code == 201, r.text
    datos = r.json()
    assert datos["warnings"] == ["data_consent_missing"]
    assert datos["data_consent_at"] is None and datos["data_consent_version"] is None
    fila = await fila_socio(session, UUID(datos["id"]))
    assert fila["data_consent_at"] is None and fila["data_consent_version"] is None


async def test_sin_politica_publicada_ni_corte_el_alta_sin_autorizacion_da_201(
    app_http: AsyncClient, admin: UsuarioPrueba, cabeceras: Cabeceras
) -> None:
    r = await _alta(app_http, cabeceras, admin, data_consent=False)

    assert r.status_code == 201, r.text
    assert r.json()["warnings"] == ["data_consent_missing"]


@pytest.mark.parametrize("corte", [None, MANANA], ids=["sin-corte", "corte-futuro"])
async def test_sin_corte_vigente_la_autorizacion_enviada_tambien_copia_la_version(
    app_http: AsyncClient,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    session: AsyncSession,
    corte: date | None,
) -> None:
    """S6-D46: la versión se copia siempre que la autorización queda registrada y hay política."""
    await publicar_politica(session, admin.id, corte=corte)

    r = await _alta(app_http, cabeceras, admin, data_consent=True)

    assert r.status_code == 201, r.text
    assert r.json()["data_consent_version"] == VERSION
    assert (await fila_socio(session, UUID(r.json()["id"])))["data_consent_version"] == VERSION


# M-11: lo que el cliente no puede mandar --------------------------------------------------------


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("data_consent_version", "2000-01"), ("enforce_consent", False)],
)
async def test_el_cliente_no_puede_enviar_la_version_ni_enforce_consent(
    app_http: AsyncClient,
    admin: UsuarioPrueba,
    cabeceras: Cabeceras,
    session: AsyncSession,
    campo: str,
    valor: object,
) -> None:
    await publicar_politica(session, admin.id, corte=HOY)

    r = await _alta(app_http, cabeceras, admin, data_consent=True, **{campo: valor})

    assert r.status_code == 422, r.text
    assert r.json()["error"]["code"] == "validation_error"
    assert await cuantos_socios(session) == 0


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("data_consent_version", "2000-01"), ("enforce_consent", False), ("data_consent_at", None)],
)
def test_member_create_prohibe_esos_campos_por_extra_forbid(campo: str, valor: object) -> None:
    with pytest.raises(ValidationError) as capturado:
        MemberCreate.model_validate(cuerpo(**{campo: valor}))
    assert [e["type"] for e in capturado.value.errors()] == ["extra_forbidden"]


def test_enforce_consent_es_solo_por_nombre_y_vale_verdadero_por_defecto() -> None:
    parametro = inspect.signature(service.create).parameters["enforce_consent"]
    assert parametro.kind is inspect.Parameter.KEYWORD_ONLY
    assert parametro.default is True


# Service: la exención del import y del seed ----------------------------------------------------


async def _crear(
    session: AsyncSession, quien: UsuarioPrueba, data: MemberCreate, **opciones: Any
) -> Any:
    with actor_scope(quien.id):
        salida = await service.create(session, data, **opciones)
        await session.commit()
    return salida


async def test_service_con_el_corte_vigente_exige_la_autorizacion_por_defecto(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    await publicar_politica(session, admin.id, corte=HOY)

    with pytest.raises(MemberValidationError) as capturado, actor_scope(admin.id):
        await service.create(session, entrada(data_consent=False))
    await session.rollback()

    assert capturado.value.field == "data_consent_at"
    assert await cuantos_socios(session) == 0


async def test_service_enforce_consent_false_no_exige_nada_con_el_corte_vigente(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    await publicar_politica(session, admin.id, corte=HOY)

    salida = await _crear(session, admin, entrada(data_consent=False), enforce_consent=False)

    assert salida.warnings == ["data_consent_missing"]
    assert salida.data_consent_at is None
    fila = await fila_socio(session, salida.id)
    assert fila["data_consent_at"] is None


async def test_service_enforce_consent_false_tampoco_da_409_sin_politica_publicada(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    await publicar_politica(session, admin.id, corte=HOY)
    await quitar_version(session)

    salida = await _crear(session, admin, entrada(data_consent=False), enforce_consent=False)

    assert salida.data_consent_at is None
