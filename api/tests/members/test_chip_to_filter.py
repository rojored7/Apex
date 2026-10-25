"""`members.chip_to_filter` (S3-B9b, US-071 T1 y T6; D22, N-20): los siete chips de la lista.

- "Al día" `active`, "Por vencer" `expiring`, "Vencidos" `expired`, "Congelados" `frozen`,
  "Pendiente de pago" `pending_payment` (Q3) y "Sin membresía" `none` fijan `membership_status`
  y dejan `status` sin tocar; "Dados de baja" `deleted` fija `status="deleted"` y ningún estado
  de membresía (N-20: admin y coach).
- Un chip desconocido (también en mayúsculas, con espacios o vacío) da `ValueError`.
- `MEMBER_CHIPS` son exactamente los siete, en el orden de la pantalla, y cada filtro es una
  entrada válida de `MemberListQuery`.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict
from typing import get_args

import pytest

from app.modules.members.schemas import MemberListQuery, MembershipFilterStatus
from app.modules.members.service import MEMBER_CHIPS, MemberChipFilter, chip_to_filter

ESTADOS_DE_MEMBRESIA = ("active", "expiring", "expired", "frozen", "pending_payment", "none")


def test_los_siete_chips_en_el_orden_de_la_pantalla() -> None:
    assert MEMBER_CHIPS == (*ESTADOS_DE_MEMBRESIA, "deleted")


def test_los_estados_del_filtro_son_los_seis_de_membresia() -> None:
    assert get_args(MembershipFilterStatus) == ESTADOS_DE_MEMBRESIA


@pytest.mark.parametrize("chip", ESTADOS_DE_MEMBRESIA)
def test_cada_chip_de_membresia_fija_su_estado_y_no_toca_status(chip: str) -> None:
    filtro = chip_to_filter(chip)
    assert filtro == MemberChipFilter(status=None, membership_status=chip)  # type: ignore[arg-type]


def test_dados_de_baja_fija_status_deleted_sin_estado_de_membresia() -> None:
    assert chip_to_filter("deleted") == MemberChipFilter(status="deleted", membership_status=None)


@pytest.mark.parametrize("chip", MEMBER_CHIPS)
def test_cada_filtro_es_una_entrada_valida_de_la_lista(chip: str) -> None:
    filtros = MemberListQuery(**asdict(chip_to_filter(chip)))
    assert (filtros.status, filtros.membership_status) == (
        ("deleted", None) if chip == "deleted" else (None, chip)
    )


@pytest.mark.parametrize(
    "chip", ["moroso", "ACTIVE", " active", "active ", "", "inactive", "Al día", "cancelled"]
)
def test_un_chip_desconocido_da_value_error(chip: str) -> None:
    with pytest.raises(ValueError, match=r"(?i)chip"):
        chip_to_filter(chip)


def test_el_filtro_es_inmutable() -> None:
    filtro = chip_to_filter("active")
    with pytest.raises(FrozenInstanceError):
        filtro.status = "deleted"  # type: ignore[misc]
