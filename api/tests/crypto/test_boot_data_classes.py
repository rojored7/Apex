"""Prueba de arranque de clases de dato (S9-W0-3; S9-D35, hallazgo 7): toda clase del registro que
cifra (`encrypt=True`) tiene una fila `encrypt` activa tras `ensure_keys`, y la segunda llamada no
crea otra. Con una clase falsa por `override_registry` la prueba cubre también las que lleguen
después (`athlete.metric`, A1): si alguien registra una clase y `ensure_keys` no la crea, falla aquí
y no en producción.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import SYSTEM_USER_ID, actor_scope
from app.core.crypto.bootstrap import ensure_keys
from app.core.crypto.local_provider import LocalFileProvider
from app.core.crypto.models import CryptoKey
from app.core.crypto.registry import REGISTRY, DataClassSpec, override_registry

FALSA = DataClassSpec("prueba.clase_futura", True, None, False, "str", ())


async def _activas(session: AsyncSession, purpose: str, data_class: str) -> int:
    total = await session.scalar(
        select(func.count())
        .select_from(CryptoKey)
        .where(
            CryptoKey.purpose == purpose,
            CryptoKey.data_class == data_class,
            CryptoKey.state == "active",
        )
    )
    return int(total or 0)


async def test_toda_clase_que_cifra_tiene_su_fila_encrypt_activa_tras_ensure_keys(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider
) -> None:
    registro = {**REGISTRY, FALSA.name: FALSA}
    with override_registry(registro), actor_scope(SYSTEM_USER_ID):
        await ensure_keys(sin_llaves, proveedor_local, lambda _n: proveedor_local)

        cifran = sorted(n for n, s in registro.items() if s.encrypt)
        assert FALSA.name in cifran
        for clase in cifran:
            assert await _activas(sin_llaves, "encrypt", clase) == 1, clase


async def test_la_segunda_llamada_no_crea_otra_fila_de_la_clase_falsa(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider
) -> None:
    registro = {**REGISTRY, FALSA.name: FALSA}
    with override_registry(registro), actor_scope(SYSTEM_USER_ID):
        await ensure_keys(sin_llaves, proveedor_local, lambda _n: proveedor_local)
        antes = await sin_llaves.scalar(select(func.count()).select_from(CryptoKey))
        await ensure_keys(sin_llaves, proveedor_local, lambda _n: proveedor_local)
        despues = await sin_llaves.scalar(select(func.count()).select_from(CryptoKey))

        assert antes == despues
        assert await _activas(sin_llaves, "encrypt", FALSA.name) == 1


async def test_las_clases_sin_cifrado_no_reciben_fila_encrypt(
    sin_llaves: AsyncSession, proveedor_local: LocalFileProvider
) -> None:
    with actor_scope(SYSTEM_USER_ID):
        await ensure_keys(sin_llaves, proveedor_local, lambda _n: proveedor_local)

    for nombre, spec in REGISTRY.items():
        if not spec.encrypt:
            assert await _activas(sin_llaves, "encrypt", nombre) == 0, nombre
