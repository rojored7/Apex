"""Revisión de seguridad de S2-B9 (`security-reviewer`), hallazgos corregidos.

- M1: `PlanCreate.name` aceptaba caracteres de control y de formato. Un NUL llegaba como parámetro
  a PostgreSQL (500 con traza, como el `q` de S2-B8) y un nombre solo de U+200B pasaba el CHECK
  `btrim(name) <> ''`. Ahora da 422 `field="name"`. El nombre se normaliza a NFC, así "Promoción"
  compuesta y descompuesta chocan en `uq_plans_name_alive` (409).
- L1: `PlanListQuery.q` rechaza los controles como `SearchQuery`.
"""

from __future__ import annotations

import unicodedata

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.modules.plans.schemas import PlanCreate, PlanListQuery
from tests.conftest import Cabeceras, CrearUsuario
from tests.plans._apoyo import PLANS, cuerpo


@pytest.mark.parametrize(
    "nombre",
    [
        "a" + chr(0x00) + "b",
        "Men" + chr(0x1F) + "sual",
        "Plan" + chr(0x7F),
        chr(0x200B),
        "Men" + chr(0x200B) + "sual",
        chr(0x200E) + chr(0x200F),
        chr(0x2060),
    ],
    ids=["nul", "us", "del", "solo-zwsp", "zwsp-en-medio", "marcas-de-direccion", "word-joiner"],
)
def test_el_nombre_con_controles_o_formato_falla_en_name(nombre: str) -> None:
    with pytest.raises(ValidationError) as error:
        PlanCreate.model_validate(cuerpo(name=nombre))
    (detalle,) = error.value.errors()
    assert detalle["loc"] == ("name",)
    assert nombre not in str(detalle["msg"])


@pytest.mark.parametrize(
    "nombre", [chr(0x3000), chr(0x00A0) + chr(0x2003)], ids=["ideografico", "nbsp-em"]
)
def test_el_nombre_solo_de_espacios_unicode_falla_en_name(nombre: str) -> None:
    with pytest.raises(ValidationError) as error:
        PlanCreate.model_validate(cuerpo(name=nombre))
    assert error.value.errors()[0]["loc"] == ("name",)


def test_el_nombre_se_normaliza_a_nfc() -> None:
    descompuesto = unicodedata.normalize("NFD", "Promoción")
    assert descompuesto != "Promoción"
    assert PlanCreate.model_validate(cuerpo(name=descompuesto)).name == "Promoción"


def test_plan_list_query_rechaza_controles_en_q() -> None:
    with pytest.raises(ValidationError) as error:
        PlanListQuery(q="a\x00b")
    assert error.value.errors()[0]["loc"] == ("q",)
    assert PlanListQuery(q="Promoción").q == "Promoción"


async def test_post_con_nul_en_el_nombre_da_422_y_no_500(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    r = await app_http.post(PLANS, json=cuerpo(name="a\x00b"), headers=cabeceras(admin))
    assert r.status_code == 422, r.text
    error = r.json()["error"]
    assert error["code"] == "validation_error" and error["field"] == "name"


async def test_nfc_y_nfd_del_mismo_nombre_chocan_por_http(
    app_http: AsyncClient, usuario_real: CrearUsuario, cabeceras: Cabeceras
) -> None:
    admin = await usuario_real("admin")
    primero = await app_http.post(PLANS, json=cuerpo(name="Promoción"), headers=cabeceras(admin))
    nfd = unicodedata.normalize("NFD", "promoción")
    segundo = await app_http.post(PLANS, json=cuerpo(name=nfd), headers=cabeceras(admin))
    assert primero.status_code == 201, primero.text
    assert segundo.status_code == 409, segundo.text
    assert segundo.json()["error"]["existing_id"] == primero.json()["id"]
