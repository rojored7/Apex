"""`python -m app.cli seed --demo` (S4B-B1, US-111; S4B-D31, D32, D33, D65).

Contrato (base real de prueba, `crypto_runtime`, reloj `T0` = 2026-10-21 en Bogotá):
- sobre una base vacía crea exactamente el catálogo de `demo_dataset` (3 planes, 30 socios y sus
  ventas y pagos), los estados guardados son los esperados y coinciden con `compute_status`
  (`recompute_statuses` otra vez no cambia nada); `document`, `phone`, `email`, `birth_date` y
  `emergency_contact` están cifrados (`apx1.`);
- la auditoría va a nombre del usuario técnico o de `--as`; `verify-audit` da "Cadena íntegra";
- segunda corrida: mismos conteos, cero filas nuevas en `audit_log` y `crypto_ops`, y la salida
  dice "seed de demo ya aplicado";
- un socio real (documento `1020304`) -> salida 2 sin escribir; con `--force-demo-on-non-empty`
  siembra;
- no es atómico: un corte a mitad (excepción en la venta del socio 7) deja los socios ya dados de
  alta y repetir el comando completa lo que falta sin duplicar;
- con `ENV=production`: sin `--as` -> 2; sin `--allow-production` -> 2; con ambos solo corre si
  `current_database()` termina en `_demo`, `_ensayo` o `_smoke` (consulta constante
  `CURRENT_DATABASE_SQL`, que aquí se reemplaza por otra constante); si no -> 2 con un mensaje fijo
  que nombra los sufijos;
- por socio, exactamente dos transacciones (un `COMMIT` en `_ensure_member` y uno en
  `_sell_and_pay`) y `lock_member` antes de la venta;
- el tablero cuadra con los datos de demostración; la salida solo trae conteos.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Awaitable, Callable, Iterator
from typing import Any
from uuid import UUID

import pytest
from click.testing import Result
from sqlalchemy import event, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cli import app
from app.core import locks
from app.core.audit import AuditEntry
from app.core.config import Settings
from app.core.context import SYSTEM_USER_ID
from app.core.crypto.keyring import Keyring
from app.core.crypto.models import CryptoKey
from app.modules.dashboard import service as dashboard_service
from app.modules.members.models import Member
from app.modules.memberships import service as memberships_service
from app.modules.plans.models import Plan
from app.seed import apply as seed_apply
from tests.cli import _apoyo_demo as demo
from tests.cli._apoyo import correr
from tests.conftest import CLAVE_PRUEBA
from tests.factories.members import make_member
from tests.factories.users import make_user
from tests.memberships.conftest import bus_confirmado, sin_cache_de_resumen  # noqa: F401

Fabrica = async_sessionmaker[AsyncSession]
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

pytestmark = pytest.mark.usefixtures("reloj", "limpiar_demo")


def _sembrar(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    *extra: str,
    env: str = "dev",
) -> Result:
    efectivo: Any = env
    return correr(app, ["seed", "--demo", *extra], efectivo, base=settings, monkeypatch=monkeypatch)


async def _admin(fabrica: Fabrica) -> Any:
    async with fabrica() as sesion:
        return await make_user(sesion, role="admin", password=CLAVE_PRUEBA)


# Base vacía -----------------------------------------------------------------------------------


async def test_base_vacia_crea_el_catalogo_exacto(
    limpiar_demo: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    esperado = demo.esperados(demo.catalogo())

    resultado = _sembrar(settings_prueba, monkeypatch)

    assert resultado.exit_code == 0, resultado.output
    conteo = await demo.contar(limpiar_demo)
    assert {k: conteo[k] for k in esperado} == esperado
    async with limpiar_demo() as sesion:
        nombres = set(await sesion.scalars(select(Plan.name)))
    assert nombres == {plan.name for plan in demo.catalogo().plans}


async def test_estados_guardados_son_los_del_catalogo_y_coinciden_con_compute_status(
    limpiar_demo: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = _sembrar(settings_prueba, monkeypatch)
    assert resultado.exit_code == 0, resultado.output

    guardados = await demo.estados_guardados(limpiar_demo)

    assert guardados == demo.estados_esperados(demo.catalogo())
    assert set(guardados) == {
        "active",
        "expiring",
        "expired",
        "frozen",
        "pending_payment",
        "cancelled",
    }
    resumen = await memberships_service.recompute_statuses(limpiar_demo, today=demo.HOY)
    assert resumen.cambiadas == 0, resumen
    assert resumen.errores == 0 and resumen.busy_omitidos == 0


async def test_los_cinco_datos_sensibles_estan_cifrados_en_reposo(
    limpiar_demo: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _sembrar(settings_prueba, monkeypatch).exit_code == 0
    spec = demo.catalogo()

    async with limpiar_demo() as sesion:
        filas = (
            await sesion.execute(
                text(
                    "SELECT document, phone, email, birth_date::text, emergency_contact "
                    "FROM members.members"
                )
            )
        ).all()

    assert len(filas) == 30
    for fila in filas:
        for valor in fila:
            if valor is not None:
                assert str(valor).startswith("apx1."), "dato sensible en claro"
    claros = {s.document for s in spec.members} | {s.phone for s in spec.members}
    assert not any(c in str(f) for f in filas for c in claros)
    async with limpiar_demo() as sesion:
        sin_consentimiento = await sesion.scalar(
            select(func.count()).select_from(Member).where(Member.data_consent_at.is_(None))
        )
    assert sin_consentimiento == 0


# Auditoría ------------------------------------------------------------------------------------

TABLAS_DE_NEGOCIO = [
    "plans.plans",
    "members.members",
    "memberships.memberships",
    "payments.payments",
]


async def _actores_de_negocio(fabrica: Fabrica) -> set[UUID]:
    async with fabrica() as sesion:
        filas = await sesion.scalars(
            select(AuditEntry.user_id).where(AuditEntry.table_name.in_(TABLAS_DE_NEGOCIO))
        )
        return set(filas)


async def test_sin_as_la_auditoria_va_al_usuario_tecnico(
    limpiar_demo: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _sembrar(settings_prueba, monkeypatch).exit_code == 0

    assert await _actores_de_negocio(limpiar_demo) == {SYSTEM_USER_ID}
    async with limpiar_demo() as sesion:
        altas = await sesion.scalar(
            select(func.count())
            .select_from(AuditEntry)
            .where(AuditEntry.table_name == "members.members", AuditEntry.action == "insert")
        )
    assert altas == 30


async def test_con_as_la_auditoria_va_a_nombre_del_admin(
    limpiar_demo: Fabrica,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    argon2_rapido: None,
) -> None:
    admin = await _admin(limpiar_demo)

    resultado = _sembrar(settings_prueba, monkeypatch, "--as", admin.email)

    assert resultado.exit_code == 0, resultado.output
    assert await _actores_de_negocio(limpiar_demo) == {admin.id}
    assert admin.email not in resultado.output


async def test_la_cadena_de_auditoria_queda_integra(
    limpiar_demo: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _sembrar(settings_prueba, monkeypatch).exit_code == 0

    verificacion = correr(
        app, ["verify-audit"], "dev", base=settings_prueba, monkeypatch=monkeypatch
    )

    assert verificacion.exit_code == 0, verificacion.output
    assert "ntegra" in verificacion.output


# Idempotencia y reanudación -------------------------------------------------------------------


async def test_segunda_corrida_no_cambia_nada(
    limpiar_demo: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _sembrar(settings_prueba, monkeypatch).exit_code == 0
    antes = await demo.contar(limpiar_demo)

    segunda = _sembrar(settings_prueba, monkeypatch)

    assert segunda.exit_code == 0, segunda.output
    assert "seed de demo ya aplicado" in segunda.output
    assert await demo.contar(limpiar_demo) == antes  # incluye audit_log y crypto_ops


async def _canales(fabrica: Fabrica) -> tuple[dict[str, Any], int]:
    from app.modules.settings import service as settings_service

    async with fabrica() as sesion:
        seccion = await settings_service.get_section(sesion, "channels")
    return seccion.value, seccion.version


async def test_deja_correo_y_whatsapp_habilitados_sin_tocar_telegram(
    limpiar_demo: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """V11c (S5-D265, D269): sin fila los canales están apagados y los avisos de la demostración
    nacerían omitidos."""
    assert _sembrar(settings_prueba, monkeypatch).exit_code == 0

    valor, _ = await _canales(limpiar_demo)

    assert valor["email"]["enabled"] is True
    assert valor["whatsapp"]["enabled"] is True
    assert valor["telegram"]["enabled"] is False


async def test_la_segunda_corrida_no_reescribe_los_canales(
    limpiar_demo: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _sembrar(settings_prueba, monkeypatch).exit_code == 0
    _, version = await _canales(limpiar_demo)

    assert _sembrar(settings_prueba, monkeypatch).exit_code == 0

    assert (await _canales(limpiar_demo))[1] == version


@pytest.fixture
async def socio_real(
    limpiar_demo: Fabrica,
    bus_confirmado: Keyring,  # noqa: F811
) -> None:
    """Un socio que no es de demostración (documento `1020304`), con commit real. Depende de
    `limpiar_demo` primero: este deja `crypto_keys` vacía y `bus_confirmado` las crea."""
    async with limpiar_demo() as sesion:
        await make_member(sesion, document="1020304", phone=None, email=None)


@pytest.mark.usefixtures("socio_real")
async def test_socio_real_sale_2_sin_escribir(
    limpiar_demo: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = _sembrar(settings_prueba, monkeypatch)

    assert resultado.exit_code == 2, resultado.output
    conteo = await demo.contar(limpiar_demo)
    assert (conteo["socios"], conteo["planes"], conteo["membresias"], conteo["pagos"]) == (
        1,
        0,
        0,
        0,
    )
    assert "1020304" not in resultado.output


@pytest.mark.usefixtures("socio_real")
async def test_force_demo_on_non_empty_siembra_junto_al_socio_real(
    limpiar_demo: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = _sembrar(settings_prueba, monkeypatch, "--force-demo-on-non-empty")

    assert resultado.exit_code == 0, resultado.output
    assert (await demo.contar(limpiar_demo))["socios"] == 31


async def test_corte_a_mitad_y_reanudacion_sin_duplicar(
    limpiar_demo: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = seed_apply._sell_and_pay
    llamadas = {"n": 0}

    async def cortada(*args: Any, **kwargs: Any) -> Any:
        llamadas["n"] += 1
        if llamadas["n"] == 7:
            raise RuntimeError("corte inyectado en el socio 7")
        return await original(*args, **kwargs)

    monkeypatch.setattr(seed_apply, "_sell_and_pay", cortada)

    corte = _sembrar(settings_prueba, monkeypatch)

    assert corte.exit_code == 1, corte.output
    a_medias = await demo.contar(limpiar_demo)
    assert a_medias["socios"] == 7  # transacción 1 del socio 7 confirmada; la 2 se deshizo
    assert 0 < a_medias["membresias"] < demo.esperados(demo.catalogo())["membresias"]

    monkeypatch.setattr(seed_apply, "_sell_and_pay", original)
    reanudado = _sembrar(settings_prueba, monkeypatch)

    assert reanudado.exit_code == 0, reanudado.output
    esperado = demo.esperados(demo.catalogo())
    conteo = await demo.contar(limpiar_demo)
    assert {k: conteo[k] for k in esperado} == esperado
    async with limpiar_demo() as sesion:
        distintos = await sesion.scalar(select(func.count(func.distinct(Member.document_idx))))
    assert distintos == 30
    assert await demo.estados_guardados(limpiar_demo) == demo.estados_esperados(demo.catalogo())


# Producción -----------------------------------------------------------------------------------


async def test_produccion_sin_as_sale_2(
    limpiar_demo: Fabrica, settings_produccion: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    resultado = _sembrar(settings_produccion, monkeypatch, "--allow-production", env="production")

    assert resultado.exit_code == 2, resultado.output
    assert "--as" in resultado.output
    assert (await demo.contar(limpiar_demo))["socios"] == 0


async def test_produccion_sin_allow_production_sale_2(
    limpiar_demo: Fabrica,
    settings_produccion: Settings,
    monkeypatch: pytest.MonkeyPatch,
    argon2_rapido: None,
) -> None:
    admin = await _admin(limpiar_demo)

    resultado = _sembrar(settings_produccion, monkeypatch, "--as", admin.email, env="production")

    assert resultado.exit_code == 2, resultado.output
    assert "--allow-production" in resultado.output
    assert (await demo.contar(limpiar_demo))["socios"] == 0


async def test_allow_production_sobre_apex_test_sale_2_con_mensaje_fijo(
    limpiar_demo: Fabrica,
    settings_produccion: Settings,
    monkeypatch: pytest.MonkeyPatch,
    argon2_rapido: None,
) -> None:
    """S4B-D65: la base de la prueba (`apex_test`) no termina en un sufijo seguro."""
    admin = await _admin(limpiar_demo)
    args = ("--as", admin.email, "--allow-production")

    resultado = _sembrar(settings_produccion, monkeypatch, *args, env="production")

    assert resultado.exit_code == 2, resultado.output
    for sufijo in ("_demo", "_ensayo", "_smoke"):
        assert sufijo in resultado.output
    assert (await demo.contar(limpiar_demo))["socios"] == 0


@pytest.mark.parametrize("base", ["apex", "apexdemo", "apex_demo_old", "apex_test", "demo"])
async def test_allow_production_con_un_nombre_sin_sufijo_seguro_sale_2(
    base: str,
    limpiar_demo: Fabrica,
    settings_produccion: Settings,
    monkeypatch: pytest.MonkeyPatch,
    argon2_rapido: None,
) -> None:
    from app.cli_ops import seed_demo

    monkeypatch.setattr(seed_demo, "CURRENT_DATABASE_SQL", f"SELECT '{base}'")
    admin = await _admin(limpiar_demo)

    resultado = _sembrar(
        settings_produccion,
        monkeypatch,
        "--as",
        admin.email,
        "--allow-production",
        env="production",
    )

    assert resultado.exit_code == 2, resultado.output
    assert (await demo.contar(limpiar_demo))["socios"] == 0


@pytest.mark.parametrize("base", ["apex_demo", "apex_ensayo", "apex_smoke"])
async def test_allow_production_con_sufijo_seguro_escribe(
    base: str,
    limpiar_demo: Fabrica,
    settings_produccion: Settings,
    monkeypatch: pytest.MonkeyPatch,
    argon2_rapido: None,
) -> None:
    """La consulta constante se reemplaza por otra constante: el caso real (`apex_ensayo`) corre
    en V2 del sprint."""
    from app.cli_ops import seed_demo

    monkeypatch.setattr(seed_demo, "CURRENT_DATABASE_SQL", f"SELECT '{base}'")
    admin = await _admin(limpiar_demo)

    resultado = _sembrar(
        settings_produccion,
        monkeypatch,
        "--as",
        admin.email,
        "--allow-production",
        env="production",
    )

    assert resultado.exit_code == 0, resultado.output
    assert (await demo.contar(limpiar_demo))["socios"] == 30
    assert await _actores_de_negocio(limpiar_demo) == {admin.id}


# Transacciones y candados ---------------------------------------------------------------------


@pytest.fixture
def commits() -> Iterator[list[None]]:
    """Cada `COMMIT` de cualquier motor del proceso (el seed crea el suyo)."""
    visto: list[None] = []

    def anotar(_conexion: Any) -> None:
        visto.append(None)

    event.listen(Engine, "commit", anotar)
    try:
        yield visto
    finally:
        event.remove(Engine, "commit", anotar)


async def test_por_socio_exactamente_dos_transacciones(
    limpiar_demo: Fabrica,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    commits: list[None],
) -> None:
    por_funcion: dict[str, list[int]] = {"_ensure_member": [], "_sell_and_pay": []}

    def espiar(nombre: str) -> Callable[..., Awaitable[Any]]:
        original = getattr(seed_apply, nombre)

        async def envuelta(*args: Any, **kwargs: Any) -> Any:
            antes = len(commits)
            try:
                return await original(*args, **kwargs)
            finally:
                por_funcion[nombre].append(len(commits) - antes)

        return envuelta

    for nombre in por_funcion:
        monkeypatch.setattr(seed_apply, nombre, espiar(nombre))

    resultado = _sembrar(settings_prueba, monkeypatch)

    assert resultado.exit_code == 0, resultado.output
    assert por_funcion["_ensure_member"] == [1] * 30  # transacción 1: el alta
    assert por_funcion["_sell_and_pay"] == [1] * 30  # transacción 2: venta y pagos


async def test_lock_member_precede_a_la_venta_de_cada_socio(
    limpiar_demo: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    eventos: list[tuple[str, UUID]] = []
    lock_original = locks.lock_member
    venta_original = seed_apply._sell_back_dated

    async def lock_espiado(session: AsyncSession, member_id: UUID, *a: Any, **k: Any) -> Any:
        eventos.append(("lock", member_id))
        return await lock_original(session, member_id, *a, **k)

    async def venta_espiada(session: AsyncSession, **venta: Any) -> Any:
        eventos.append(("sell", venta["member_id"]))
        return await venta_original(session, **venta)

    monkeypatch.setattr(locks, "lock_member", lock_espiado)
    monkeypatch.setattr(seed_apply, "lock_member", lock_espiado, raising=False)
    monkeypatch.setattr(seed_apply, "_sell_back_dated", venta_espiada)

    resultado = _sembrar(settings_prueba, monkeypatch)

    assert resultado.exit_code == 0, resultado.output
    ventas = [(i, socio) for i, (tipo, socio) in enumerate(eventos) if tipo == "sell"]
    assert len(ventas) >= 30
    for posicion, socio in ventas:
        antes = [tipo for tipo, otro in eventos[:posicion] if otro == socio]
        assert "lock" in antes, "la venta se hizo sin tomar antes el candado del socio"


# Tablero y salida -----------------------------------------------------------------------------


async def test_el_tablero_cuadra_con_los_datos_de_demostracion(
    limpiar_demo: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _sembrar(settings_prueba, monkeypatch).exit_code == 0
    spec = demo.catalogo()
    por_estado = demo.estados_de_socios(spec)
    ingresos = sum(
        pago.amount_cop
        for socio in spec.members
        for pago in (
            ([socio.sale.first_payment] if socio.sale.first_payment else [])
            + list(socio.sale.extra_payments)
        )
        if not pago.void
        and (pago.paid_on.year, pago.paid_on.month) == (demo.HOY.year, demo.HOY.month)
    )

    async with limpiar_demo() as sesion:
        tablero = await dashboard_service.summary(sesion, with_finances=True)

    assert tablero.today == demo.HOY
    assert (
        tablero.members_active,
        tablero.members_expiring,
        tablero.members_expired,
        tablero.members_frozen,
        tablero.members_pending_payment,
    ) == tuple(
        por_estado[k] for k in ("active", "expiring", "expired", "frozen", "pending_payment")
    )
    assert tablero.income_month == "2026-10"
    assert tablero.income_month_cop == ingresos


async def test_la_salida_solo_trae_conteos(
    limpiar_demo: Fabrica,
    settings_prueba: Settings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("DEBUG"):
        resultado = _sembrar(settings_prueba, monkeypatch)

    assert resultado.exit_code == 0, resultado.output
    conjunto = resultado.output + caplog.text
    assert UUID_RE.search(conjunto) is None
    for socio in demo.catalogo().members:
        for dato in (socio.document, socio.phone, socio.email, socio.first_name, socio.last_name):
            assert dato not in conjunto, "la salida repite un dato de un socio"
    assert re.search(r"\d", resultado.output), "debe informar conteos"


async def test_las_llaves_de_cifrado_las_crea_el_comando_sin_llaves_previas(
    limpiar_demo: Fabrica, settings_prueba: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`limpiar_demo` deja `crypto_keys` vacía: `crypto_runtime` las crea (`ensure_keys`)."""
    async with limpiar_demo() as sesion:
        assert await sesion.scalar(select(func.count()).select_from(CryptoKey)) == 0

    assert _sembrar(settings_prueba, monkeypatch).exit_code == 0

    async with limpiar_demo() as sesion:
        llaves = Counter(await sesion.scalars(select(CryptoKey.data_class)))
    assert llaves["member.document"] >= 1


async def test_base_con_nombre_no_demo_sale_2_antes_de_crear_llaves(
    limpiar_demo: Fabrica,
    settings_produccion: Settings,
    monkeypatch: pytest.MonkeyPatch,
    argon2_rapido: None,
) -> None:
    """Revisión de seguridad de B1 (MEDIUM): la guarda de la base (M-7) corre antes de que el
    comando cargue o cree llaves; una base de producción sin llaves sigue sin llaves."""
    admin = await _admin(limpiar_demo)
    async with limpiar_demo() as sesion:
        assert await sesion.scalar(select(func.count()).select_from(CryptoKey)) == 0
    args = ("--as", admin.email, "--allow-production")

    resultado = _sembrar(settings_produccion, monkeypatch, *args, env="production")

    assert resultado.exit_code == 2, resultado.output
    async with limpiar_demo() as sesion:
        assert await sesion.scalar(select(func.count()).select_from(CryptoKey)) == 0
    assert (await demo.contar(limpiar_demo))["crypto_ops"] == 0
