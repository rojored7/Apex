"""`core/pagination.chunked` e `ID_BATCH` (S3-W0-2; S3-D59, D-5).

Las lecturas por lote entre módulos (`refs_for`, `_enrich`, `status_for`, `sums_not_voided`)
parten la lista de ids en lotes de `ID_BATCH` para que ninguna sentencia ligue una lista sin
tope en `= ANY(:ids)`.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from app.core.pagination import ID_BATCH, chunked


def test_id_batch_es_200() -> None:
    assert ID_BATCH == 200


@pytest.mark.parametrize(
    ("total", "tamanos"),
    [(0, []), (1, [1]), (200, [200]), (201, [200, 1]), (450, [200, 200, 50])],
    ids=["0", "1", "200", "201", "450"],
)
def test_chunked_parte_en_lotes_de_id_batch(total: int, tamanos: list[int]) -> None:
    ids = [UUID(int=i) for i in range(total)]
    lotes = list(chunked(ids))
    assert [len(lote) for lote in lotes] == tamanos
    assert [i for lote in lotes for i in lote] == ids  # mismo orden, sin repetir ni omitir


def test_chunked_con_tamano_propio_conserva_el_orden() -> None:
    assert [list(lote) for lote in chunked([5, 4, 3, 2, 1], 2)] == [[5, 4], [3, 2], [1]]


def test_chunked_devuelve_un_iterador_y_no_toca_la_entrada() -> None:
    entrada = [1, 2, 3]
    iterador = chunked(entrada, 2)
    assert iter(iterador) is iterador
    assert list(next(iterador)) == [1, 2]
    assert entrada == [1, 2, 3]


@pytest.mark.parametrize("tamano", [0, -1])
def test_chunked_rechaza_un_tamano_no_positivo(tamano: int) -> None:
    with pytest.raises(ValueError, match="size"):
        list(chunked([1, 2], tamano))
