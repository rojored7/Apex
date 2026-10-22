"""`auth.service.list_users` con PostgreSQL real (S2-B3; US-045; S2-D1, regla de datos 6).

- Nunca incluye al usuario técnico (`SYSTEM_USER_ID`, N-15).
- Sin `status` excluye las cuentas borradas (`deleted_at IS NULL`); con `status` usa el espejo
  SQL `status_filter` (los cinco estados).
- `q` busca en el correo con `ILIKE` escapando `%`, `_` y la barra invertida.
- Orden `email ASC` (con la clave primaria como desempate de `paginate`).
- `active_sessions` cuenta solo los refresh vigentes (`expires_at > ahora`) y no revocados.
Cada prueba aísla sus correos con una etiqueta única y la usa en `q`.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.pagination import Page, PageParams
from app.core.security import hash_opaque_token, new_opaque_token
from app.modules.auth import service
from app.modules.auth.models import RefreshToken
from app.modules.auth.schemas import UserRow
from tests.auth._cuentas import CAMPOS_USER_ROW, etiqueta
from tests.conftest import T0, CrearUsuario

TODO = PageParams(limit=200, offset=0)


async def _lista(
    session: AsyncSession,
    *,
    q: str | None = None,
    role: str | None = None,
    status: str | None = None,
    page: PageParams = TODO,
) -> Page[UserRow]:
    return await service.list_users(
        session,
        q=q,
        role=role,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        page=page,
    )


def _correo(prefijo: str, tag: str) -> str:
    return f"{prefijo}-{tag}@test.apex"


async def _refresh(
    session: AsyncSession,
    user_id: UUID,
    *,
    expira_en: timedelta = timedelta(days=7),
    revocado: bool = False,
) -> None:
    with actor_scope(SYSTEM_USER_ID):
        session.add(
            RefreshToken(
                user_id=user_id,
                token_hash=hash_opaque_token(new_opaque_token()),
                expires_at=T0 + expira_en,
                revoked_at=T0 - timedelta(minutes=1) if revocado else None,
                family_started_at=T0 - timedelta(days=1),
                created_by=SYSTEM_USER_ID,
            )
        )
        await session.flush()
        await session.commit()


async def test_nunca_incluye_al_usuario_tecnico(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    await usuario_real("admin")
    pagina = await _lista(session)
    assert SYSTEM_USER_ID not in {fila.id for fila in pagina.items}
    assert (await _lista(session, q="system@apex.local")).total == 0
    assert (await _lista(session, status="inactive", q="system")).total == 0


async def test_ordena_por_correo_y_pagina_con_total(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    tag = etiqueta()
    for prefijo in ("carla", "ana", "beto"):
        await usuario_real("coach", email=_correo(prefijo, tag))
    pagina = await _lista(session, q=tag)
    assert [f.email for f in pagina.items] == [
        _correo("ana", tag),
        _correo("beto", tag),
        _correo("carla", tag),
    ]
    assert pagina.total == 3
    primera = await _lista(session, q=tag, page=PageParams(limit=2, offset=0))
    segunda = await _lista(session, q=tag, page=PageParams(limit=2, offset=2))
    assert [f.email for f in primera.items] == [_correo("ana", tag), _correo("beto", tag)]
    assert [f.email for f in segunda.items] == [_correo("carla", tag)]
    assert (primera.total, primera.limit, primera.offset) == (3, 2, 0)
    assert (segunda.total, segunda.limit, segunda.offset) == (3, 2, 2)


async def test_q_busca_sin_distinguir_mayusculas_dentro_del_correo(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    tag = etiqueta()
    ana = await usuario_real("coach", email=_correo("ana.gomez", tag))
    await usuario_real("coach", email=_correo("beto", tag))
    pagina = await _lista(session, q=f"GOMEZ-{tag.upper()}")
    assert [f.id for f in pagina.items] == [ana.id]


@pytest.mark.parametrize(
    ("literal", "parecido"),
    [("x_y", "xay"), ("p%q", "pzzq"), ("r\\s", "rs")],
    ids=["guion-bajo", "porcentaje", "barra"],
)
async def test_q_escapa_los_comodines_de_like(
    literal: str,
    parecido: str,
    session: AsyncSession,
    usuario_real: CrearUsuario,
    reloj: FrozenClock,
) -> None:
    tag = etiqueta()
    exacto = await usuario_real("coach", email=_correo(literal, tag))
    await usuario_real("coach", email=_correo(parecido, tag))
    pagina = await _lista(session, q=f"{literal}-{tag}")
    assert [f.id for f in pagina.items] == [exacto.id]


async def test_q_de_un_solo_guion_bajo_no_es_comodin(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    """Blueprint: `q="_"` va escapado; sin escape casaría con todos los correos."""
    tag = etiqueta()
    await usuario_real("coach", email=_correo("singuion", tag))
    con = await usuario_real("coach", email=f"con_guion-{tag}@test.apex")
    ids = {f.id for f in (await _lista(session, q="_")).items}
    assert con.id in ids
    assert all("_" in f.email for f in (await _lista(session, q="_")).items)


async def test_filtra_por_rol(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    tag = etiqueta()
    admin = await usuario_real("admin", email=_correo("admin", tag))
    coach = await usuario_real("coach", email=_correo("coach", tag))
    socio = await usuario_real("member", email=_correo("socio", tag))
    assert [f.id for f in (await _lista(session, q=tag, role="admin")).items] == [admin.id]
    assert [f.id for f in (await _lista(session, q=tag, role="coach")).items] == [coach.id]
    assert [f.id for f in (await _lista(session, q=tag, role="member")).items] == [socio.id]


async def test_sin_status_excluye_borrados_y_con_status_usa_los_cinco_estados(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    tag = etiqueta()
    ids = {
        "active": (await usuario_real("coach", email=_correo("a1", tag))).id,
        "inactive": (await usuario_real("coach", email=_correo("a2", tag), activo=False)).id,
        "locked": (await usuario_real("coach", email=_correo("a3", tag), bloqueado=True)).id,
        "pending_activation": (
            await usuario_real("coach", email=_correo("a4", tag), password=None)
        ).id,
        "deleted": (await usuario_real("coach", email=_correo("a5", tag), borrado=True)).id,
    }
    sin_filtro = await _lista(session, q=tag)
    assert {f.id for f in sin_filtro.items} == set(ids.values()) - {ids["deleted"]}
    assert sin_filtro.total == 4
    for estado, user_id in ids.items():
        pagina = await _lista(session, q=tag, status=estado)
        assert [f.id for f in pagina.items] == [user_id], estado
        assert pagina.items[0].status == estado


async def test_active_sessions_cuenta_solo_refresh_vigentes_y_no_revocados(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    tag = etiqueta()
    con_sesiones = await usuario_real("coach", email=_correo("con", tag))
    sin_sesiones = await usuario_real("coach", email=_correo("sin", tag))
    await _refresh(session, con_sesiones.id)  # vigente
    await _refresh(session, con_sesiones.id)  # vigente
    await _refresh(session, con_sesiones.id, revocado=True)
    await _refresh(session, con_sesiones.id, expira_en=-timedelta(seconds=1))  # vencido
    await _refresh(session, con_sesiones.id, expira_en=timedelta(0))  # vence justo ahora
    await _refresh(session, sin_sesiones.id, revocado=True)
    por_id = {f.id: f for f in (await _lista(session, q=tag)).items}
    assert por_id[con_sesiones.id].active_sessions == 2
    assert por_id[sin_sesiones.id].active_sessions == 0


async def test_active_sessions_usa_el_reloj_de_la_app(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    tag = etiqueta()
    coach = await usuario_real("coach", email=_correo("reloj", tag))
    await _refresh(session, coach.id, expira_en=timedelta(hours=1))
    assert (await _lista(session, q=tag)).items[0].active_sessions == 1
    reloj.advance(hours=2)
    assert (await _lista(session, q=tag)).items[0].active_sessions == 0


async def test_cada_fila_trae_solo_los_campos_del_contrato(
    session: AsyncSession, usuario_real: CrearUsuario, reloj: FrozenClock
) -> None:
    tag = etiqueta()
    pendiente = await usuario_real("coach", email=_correo("pend", tag), password=None)
    fila = (await _lista(session, q=tag)).items[0]
    assert isinstance(fila, UserRow)
    assert set(fila.model_dump()) == CAMPOS_USER_ROW
    assert fila.id == pendiente.id
    assert fila.status == "pending_activation"
    assert fila.last_login_at is None
    assert fila.created_at is not None
    assert "argon2" not in fila.model_dump_json()
