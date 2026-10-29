"""Lecturas de quién actuó para la auditoría (S4A-B4; S4A-D16, S4A-D19, S4A-D54).

`auth.service`:
- `user_names_for(session, ids) -> dict[UUID, str]`: `display_name` = parte local del correo
  (`ana.perez` de `ana.perez@ejemplo.local`) y `Sistema` para `SYSTEM_USER_ID`; incluye borrados;
  un id inexistente no aparece; por lotes (`ID_BATCH`, 450 ids = 3 lotes);
- `user_refs_for(session, ids) -> dict[UUID, UserRef]`: además el correo (`system@apex.local`
  para el técnico);
- `search_user_ids(session, term, *, local_part_only=False, limit=200) -> set[UUID]`: correo
  parcial sin mayúsculas ni tildes (`sql_fold`), `%` y `_` literales (un `_` sin escapar
  coincidiría con cualquier carácter), con `local_part_only` el dominio no cuenta; como máximo
  `limit`; un término vacío o solo de espacios da `set()`; incluye borrados;
- `names_for` (correo por id, lo usa `payments`) e `ids_by_email` (exacta, la usa `resolve_actor`)
  no cambian.
La tabla `auth.users` de `db_test` puede tener otras filas confirmadas: las búsquedas se comparan
contra el conjunto de usuarios creados en la prueba (intersección), y el técnico se nombra aparte.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID
from app.modules.auth import service
from app.modules.auth.schemas import UserRef
from tests.conftest import CrearUsuario, UsuarioPrueba

ANA = "ana.perez@ejemplo.local"
JUAN = "juan.rios@ejemplo.local"
JOSE = "josé.muñoz@ejemplo.local"
GUION = "ana_x@otro.co"
SIN_GUION = "anaxx@otro.co"
CIEN = "cien%real@otro.co"
CIENX = "cienxxreal@otro.co"


@pytest.fixture
async def gente(usuario_real: CrearUsuario) -> dict[str, UsuarioPrueba]:
    correos = {
        "ana": ANA,
        "juan": JUAN,
        "jose": JOSE,
        "guion": GUION,
        "sin_guion": SIN_GUION,
        "cien": CIEN,
        "cienx": CIENX,
    }
    gente = {clave: await usuario_real("coach", email=correo) for clave, correo in correos.items()}
    gente["borrado"] = await usuario_real("coach", email="baja.total@ejemplo.local", borrado=True)
    return gente


def _ids(gente: dict[str, UsuarioPrueba], *claves: str) -> set[UUID]:
    return {gente[c].id for c in claves}


async def _buscar(
    session: AsyncSession, gente: dict[str, UsuarioPrueba], term: str, **opciones: object
) -> set[UUID]:
    hallados = await service.search_user_ids(session, term, **opciones)  # type: ignore[arg-type]
    return hallados & {u.id for u in gente.values()}


# user_names_for y user_refs_for --------------------------------------------------------------


async def test_user_names_for_parte_local_y_sistema(
    session: AsyncSession, gente: dict[str, UsuarioPrueba]
) -> None:
    nombres = await service.user_names_for(
        session, [gente["ana"].id, gente["jose"].id, SYSTEM_USER_ID]
    )
    assert nombres == {
        gente["ana"].id: "ana.perez",
        gente["jose"].id: "josé.muñoz",
        SYSTEM_USER_ID: "Sistema",
    }


async def test_user_names_for_incluye_borrados_y_omite_inexistentes(
    session: AsyncSession, gente: dict[str, UsuarioPrueba]
) -> None:
    inexistente = uuid4()
    nombres = await service.user_names_for(session, [gente["borrado"].id, inexistente])
    assert nombres == {gente["borrado"].id: "baja.total"}
    assert await service.user_names_for(session, []) == {}


async def test_user_names_for_por_lotes(
    session: AsyncSession, gente: dict[str, UsuarioPrueba]
) -> None:
    ids = [uuid4() for _ in range(449)] + [gente["juan"].id]
    assert await service.user_names_for(session, ids) == {gente["juan"].id: "juan.rios"}


async def test_user_refs_for_lleva_el_correo(
    session: AsyncSession, gente: dict[str, UsuarioPrueba]
) -> None:
    refs = await service.user_refs_for(session, [gente["ana"].id, SYSTEM_USER_ID, uuid4()])
    assert refs == {
        gente["ana"].id: UserRef(id=gente["ana"].id, email=ANA, display_name="ana.perez"),
        SYSTEM_USER_ID: UserRef(
            id=SYSTEM_USER_ID, email="system@apex.local", display_name="Sistema"
        ),
    }
    assert await service.user_refs_for(session, []) == {}


async def test_user_ref_es_inmutable() -> None:
    ref = UserRef(id=SYSTEM_USER_ID, email="system@apex.local", display_name="Sistema")
    with pytest.raises(AttributeError):
        ref.email = "otro@x.co"  # type: ignore[misc]


# search_user_ids ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("term", "esperados"),
    [
        ("perez", ("ana",)),
        ("PÉREZ", ("ana",)),
        ("Ana.Perez@Ejemplo", ("ana",)),
        ("RÍOS", ("juan",)),
        ("munoz", ("jose",)),
        ("MUÑOZ", ("jose",)),
        ("jose", ("jose",)),
        ("ejemplo.local", ("ana", "juan", "jose", "borrado")),
        ("baja", ("borrado",)),
        ("no-existe-nadie", ()),
    ],
    ids=[
        "parcial",
        "mayus-tilde",
        "mixto",
        "tilde",
        "sin-tilde",
        "con-tilde",
        "nombre",
        "dominio",
        "borrado",
        "nadie",
    ],
)
async def test_search_parcial_sin_mayusculas_ni_tildes(
    session: AsyncSession, gente: dict[str, UsuarioPrueba], term: str, esperados: tuple[str, ...]
) -> None:
    assert await _buscar(session, gente, term) == _ids(gente, *esperados)


async def test_search_escapa_guion_bajo_y_porcentaje(
    session: AsyncSession, gente: dict[str, UsuarioPrueba]
) -> None:
    assert await _buscar(session, gente, "a_x") == _ids(gente, "guion")
    assert await _buscar(session, gente, "n%r") == _ids(gente, "cien")
    assert await _buscar(session, gente, "_") == _ids(gente, "guion")
    assert await _buscar(session, gente, "%") == _ids(gente, "cien")
    assert await _buscar(session, gente, "\\") == set()


async def test_search_local_part_only_no_mira_el_dominio(
    session: AsyncSession, gente: dict[str, UsuarioPrueba]
) -> None:
    assert await _buscar(session, gente, "ejemplo") == _ids(gente, "ana", "juan", "jose", "borrado")
    assert await _buscar(session, gente, "ejemplo", local_part_only=True) == set()
    assert await _buscar(session, gente, "ANA", local_part_only=True) == _ids(
        gente, "ana", "guion", "sin_guion"
    )
    assert await _buscar(session, gente, "@", local_part_only=True) == set()


async def test_search_encuentra_al_tecnico(session: AsyncSession) -> None:
    assert SYSTEM_USER_ID in await service.search_user_ids(session, "system@apex")


@pytest.mark.parametrize("term", ["", "   ", "\x07"])
async def test_search_con_termino_vacio_da_conjunto_vacio(
    session: AsyncSession, gente: dict[str, UsuarioPrueba], term: str
) -> None:
    assert await service.search_user_ids(session, term) == set()


async def test_search_respeta_el_limite(
    session: AsyncSession, gente: dict[str, UsuarioPrueba]
) -> None:
    hallados = await service.search_user_ids(session, "otro.co", limit=2)
    assert len(hallados) == 2
    assert hallados <= _ids(gente, "guion", "sin_guion", "cien", "cienx")


# Regresión: names_for e ids_by_email no cambian ----------------------------------------------


async def test_names_for_sigue_dando_el_correo(
    session: AsyncSession, gente: dict[str, UsuarioPrueba]
) -> None:
    assert await service.names_for(session, [gente["ana"].id, SYSTEM_USER_ID]) == {
        gente["ana"].id: ANA,
        SYSTEM_USER_ID: "system@apex.local",
    }


async def test_ids_by_email_sigue_siendo_exacta_y_sin_borrados(
    session: AsyncSession, gente: dict[str, UsuarioPrueba]
) -> None:
    assert await service.ids_by_email(session, ["  ANA.PEREZ@ejemplo.local "]) == {
        ANA: gente["ana"].id
    }
    assert await service.ids_by_email(session, ["ana.perez"]) == {}
    assert await service.ids_by_email(session, ["baja.total@ejemplo.local"]) == {}
