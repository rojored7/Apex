"""Hallazgos de la revisión de seguridad de S2-B8 (US-070).

- MEDIUM-1: un `q` con caracteres de control (`%00`) llegaba a PostgreSQL como parámetro y
  asyncpg lo rechaza (`0x00` no es UTF-8 válido para el servidor): 500 con traza. `classify_query`
  quita los caracteres de control (categoría `Cc`, salvo los espacios, que `strip` y la
  normalización ya tratan) antes de clasificar; `GET /members?q=a%00b` responde 200.
- LOW-4: `classify_query` normaliza el término a NFC, así una tilde combinada (`"Jose\\u0301"`)
  se pliega igual que la precompuesta de la columna (`"José"`).
- Regresión del escape con PostgreSQL real: `\\` no da error ni coincide con todo; `100%` y
  `a_b` no actúan como comodines.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.keyring import Keyring
from app.core.pagination import PageParams
from app.modules.members import service
from app.modules.members.schemas import MemberListQuery
from tests.conftest import Cabeceras, CrearUsuario
from tests.factories.members import make_member, unique_document
from tests.members._apoyo import MEMBERS


async def _socio(session: AsyncSession, first_name: str, last_name: str) -> str:
    socio = await make_member(
        session,
        first_name=first_name,
        last_name=last_name,
        document=unique_document(),
        phone=None,
        email=None,
    )
    return str(socio.id)


@pytest.mark.parametrize("termino", ["a\x00b", "\x00", "ab\x07", "a\x1fb"])
def test_classify_query_quita_los_caracteres_de_control(termino: str) -> None:
    plan = service.classify_query(termino)
    for valor in (plan.q, plan.name_pattern, plan.by_document, plan.by_phone, plan.by_email):
        assert valor is None or not any(ord(c) < 32 or ord(c) == 127 for c in valor), valor


def test_un_termino_solo_de_controles_da_el_plan_vacio() -> None:
    assert service.classify_query("\x00\x01") == service.classify_query(None)


def test_classify_query_normaliza_a_nfc() -> None:
    plan = service.classify_query("José")
    assert plan.q == "José"
    assert plan.name_pattern == "%José%"


async def test_un_q_con_nul_por_http_no_da_500(
    app_http: AsyncClient,
    usuario_real: CrearUsuario,
    cabeceras: Cabeceras,
    session: AsyncSession,
) -> None:
    ana = await _socio(session, "Ana", "Ruiz")
    coach = await usuario_real("coach")
    r = await app_http.get(MEMBERS, params={"q": "an\x00a"}, headers=cabeceras(coach))
    assert r.status_code == 200, r.text
    assert [f["id"] for f in r.json()["items"]] == [ana]


async def test_una_tilde_combinada_encuentra_a_la_precompuesta(
    session: AsyncSession, bus_listo: Keyring
) -> None:
    jose = await _socio(session, "José", "Pérez")
    await _socio(session, "Pedro", "Ruiz")
    with actor_scope(SYSTEM_USER_ID):
        pagina = await service.list(session, MemberListQuery(q="José"), PageParams())
    assert [str(f.id) for f in pagina.items] == [jose]


@pytest.mark.parametrize(
    ("termino", "esperado"),
    [("\\", "barra"), ("100%", "cien"), ("a_b", "guion")],
)
async def test_el_escape_funciona_contra_postgresql(
    session: AsyncSession, bus_listo: Keyring, termino: str, esperado: str
) -> None:
    socios = {
        "barra": await _socio(session, "Ana", "Bar\\ra"),
        "cien": await _socio(session, "Club", "100%"),
        "sin-cien": await _socio(session, "Club", "1000"),
        "guion": await _socio(session, "Ana", "a_b"),
        "sin-guion": await _socio(session, "Ana", "axb"),
    }
    with actor_scope(SYSTEM_USER_ID):
        pagina = await service.list(session, MemberListQuery(q=termino), PageParams())
    assert [str(f.id) for f in pagina.items] == [socios[esperado]]
