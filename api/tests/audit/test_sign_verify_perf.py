"""Rendimiento de la verificacion de 365 firmas (S6-A3, V8; S6-D62, S6-D81). Marcada `perf`.

Una firma por dia de un ano: 365 filas de `audit.signatures` firmadas con `local`. La verificacion
completa (`run_verification` con `verify_signatures`) usa la clave publica guardada en
`crypto_keys.public_key`: tarda menos de 5 s y NO llama al proveedor de llaves (el espia de
`LocalFileProvider` se arma DESPUES de firmar, de modo que solo cuenta la verificacion).
"""

from __future__ import annotations

import time

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit_verify import run_verification
from app.core.context import SYSTEM_USER_ID
from tests.audit.test_verify_signatures import EspiaDelProveedorLocal
from tests.factories.signatures import cadena_con_firmas

pytestmark = [pytest.mark.perf, pytest.mark.usefixtures("firmador")]

FIRMAS = 365
TOPE_S = 5.0


async def test_365_firmas_se_verifican_en_menos_de_5_s_sin_llamar_al_proveedor(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    await cadena_con_firmas(session, [1] * FIRMAS)
    espia = EspiaDelProveedorLocal(monkeypatch)

    inicio = time.perf_counter()
    vista = await run_verification(session, source="cli", by=SYSTEM_USER_ID)
    total = time.perf_counter() - inicio

    print(
        f"\nverificacion de {vista.signatures_checked} firmas: {total:.2f} s "
        f"(tope {TOPE_S} s); llamadas al proveedor: {len(espia.llamadas)}"
    )
    assert vista.ok is True
    assert (vista.signatures_checked, vista.signatures_valid) == (FIRMAS, FIRMAS)
    assert espia.llamadas == []
    assert total < TOPE_S, total
