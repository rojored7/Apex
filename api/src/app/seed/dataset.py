"""Conjunto de datos ficticio de la demostración (S4B-D32). Puro: sin base ni reloj.

`demo_dataset(today, expiring_days)` arma 3 planes y 30 socios con su venta y sus pagos en los
seis estados de membresía. Las fechas cuelgan de `today` y de `expiring_days` (la política de
`settings`), nunca de la hora real, así la prueba y la demostración fijan el mismo "hoy".
Todo dato es ficticio: documentos `999` + 7 dígitos, teléfonos `300 000 00xx`, correos
`demo+NN@ejemplo.invalid`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Final, Literal

DEMO_DOCUMENT_PREFIX = "999"
DemoMethod = Literal["cash", "nequi", "breb"]
DemoStatus = Literal["active", "expiring", "expired", "frozen", "pending_payment", "cancelled"]


@dataclass(frozen=True, slots=True)
class DemoPlan:
    name: str
    price_cop: int
    kind: Literal["days", "classes"]
    duration_days: int
    class_count: int | None = None


@dataclass(frozen=True, slots=True)
class DemoPayment:
    amount_cop: int
    method: DemoMethod
    paid_on: date
    void: bool = False  # el pago se registra y luego se anula con motivo


@dataclass(frozen=True, slots=True)
class DemoFreeze:
    frozen_from: date
    frozen_to: date


@dataclass(frozen=True, slots=True)
class DemoSale:
    plan_name: str
    start_date: date
    expected_status: DemoStatus  # estado guardado de esa membresía tras `recompute_statuses`
    expected_end_date: date  # fin esperado (con la congelación ya sumada)
    first_payment: DemoPayment | None = None
    extra_payments: tuple[DemoPayment, ...] = ()
    freeze: DemoFreeze | None = None
    cancel: bool = False
    renewal: bool = False  # suma una segunda venta con `renew=True` (queda `pending_payment`)


@dataclass(frozen=True, slots=True)
class DemoMember:
    document: str
    first_name: str
    last_name: str
    sex: Literal["f", "m", "x"]
    phone: str
    email: str
    birth_date: date
    sale: DemoSale
    data_consent: bool = True


@dataclass(frozen=True, slots=True)
class DemoSpec:
    plans: tuple[DemoPlan, ...]
    members: tuple[DemoMember, ...]


MENSUAL: Final = DemoPlan("Mensual", 120_000, "days", 30)
TRIMESTRAL: Final = DemoPlan("Trimestral", 320_000, "days", 90)
TIQUETERA: Final = DemoPlan("Tiquetera 12 clases", 150_000, "classes", 60, 12)
PLANS: Final = (MENSUAL, TRIMESTRAL, TIQUETERA)
METODOS: Final[tuple[DemoMethod, ...]] = ("cash", "nequi", "breb")
CONGELACION_DIAS: Final = 8  # hoy - 2 a hoy + 5, dentro de Q9 (30 días, 7 retroactivos)

_NOMBRES: Final = (
    "Camila", "Andrés", "Valentina", "Santiago", "Daniela", "Mateo", "Laura", "Sebastián",
    "Paula", "Julián", "Natalia", "Felipe", "Carolina", "Esteban", "Mariana", "Tomás",
    "Isabela", "Nicolás", "Sofía", "David", "Juliana", "Samuel", "Manuela", "Emilio",
    "Alejandra", "Simón", "Luciana", "Gabriel", "Andrea", "Martín",
)  # fmt: skip
_APELLIDOS: Final = (
    "Rojas Prueba", "Mejía Demo", "Cárdenas Ejemplo", "Ortiz Muestra", "Vargas Piloto",
    "Salazar Ficticio", "Pardo Ensayo", "Quintero Modelo", "Beltrán Falso", "Cortés Simulado",
)  # fmt: skip


def _sexo(i: int) -> Literal["f", "m", "x"]:
    if i % 9 == 0:
        return "x"
    return "f" if i % 2 else "m"


def _completo(plan: DemoPlan, metodo: DemoMethod, cuando: date) -> DemoPayment:
    """El pago del precio completo del plan."""
    return DemoPayment(plan.price_cop, metodo, cuando)


def _plan_que_cabe(preferido: DemoPlan, fin_en: int) -> DemoPlan:
    """El plan preferido si su duración alcanza para que el inicio no caiga en el futuro."""
    return preferido if fin_en <= preferido.duration_days else TRIMESTRAL


def _pagos_de_vigente(
    k: int, plan: DemoPlan, inicio: date, hoy: date
) -> tuple[DemoPayment, tuple[DemoPayment, ...]]:
    """`(primer pago, extras)` de la vigente número `k`: completo, en dos cuotas (k % 4 == 1) o
    con un pago registrado por error y anulado antes del bueno (k == 3)."""
    metodo = METODOS[k % 3]
    if k % 4 == 1:
        primera = DemoPayment(plan.price_cop // 2, metodo, inicio)
        resto = DemoPayment(plan.price_cop - primera.amount_cop, METODOS[(k + 1) % 3], hoy)
        return primera, (resto,)
    if k == 3:
        return DemoPayment(40_000, "cash", inicio, void=True), (_completo(plan, metodo, inicio),)
    return _completo(plan, metodo, inicio), ()


def _vigente(k: int, hoy: date, dias: int) -> DemoSale:
    """Una membresía `active`: fin a más de `expiring_days` días. La primera (k = 0) lleva una
    renovación pendiente."""
    fin_en = dias + 8 + 2 * k
    plan = _plan_que_cabe(PLANS[k % 3], fin_en)
    inicio = hoy + timedelta(days=fin_en - plan.duration_days)
    primero, extras = _pagos_de_vigente(k, plan, inicio, hoy)
    return DemoSale(
        plan.name,
        inicio,
        "active",
        hoy + timedelta(days=fin_en),
        first_payment=primero,
        extra_payments=extras,
        renewal=k == 0,
    )


def _por_vencer(k: int, hoy: date, dias: int) -> DemoSale:
    fin_en = min(4, dias)
    plan = PLANS[k % 3]
    inicio = hoy + timedelta(days=fin_en - plan.duration_days)
    return DemoSale(
        plan.name,
        inicio,
        "expiring",
        hoy + timedelta(days=fin_en),
        first_payment=_completo(plan, METODOS[k % 3], inicio),
    )


def _vencida(k: int, hoy: date) -> DemoSale:
    plan = PLANS[k % 3]
    inicio = hoy - timedelta(days=11 + plan.duration_days)
    return DemoSale(
        plan.name,
        inicio,
        "expired",
        hoy - timedelta(days=11),
        first_payment=_completo(plan, METODOS[(k + 1) % 3], inicio),
    )


def _congelada(k: int, hoy: date) -> DemoSale:
    """Congelada desde hoy - 2 hasta hoy + 5; el fin base (hoy + 25) se corre 8 días."""
    plan = (TRIMESTRAL, TIQUETERA)[k % 2]
    fin_base = hoy + timedelta(days=25)
    inicio = fin_base - timedelta(days=plan.duration_days)
    ventana = DemoFreeze(hoy - timedelta(days=2), hoy + timedelta(days=5))
    return DemoSale(
        plan.name,
        inicio,
        "frozen",
        fin_base + timedelta(days=CONGELACION_DIAS),
        first_payment=_completo(plan, METODOS[k % 3], inicio),
        freeze=ventana,
    )


def _pendiente(k: int, hoy: date) -> DemoSale:
    """Sin pago (k = 0) o con un abono que no cubre el precio."""
    plan = PLANS[k % 3]
    abono = None if k == 0 else DemoPayment(50_000, METODOS[k % 3], hoy)
    return DemoSale(
        plan.name,
        hoy,
        "pending_payment",
        hoy + timedelta(days=plan.duration_days),
        first_payment=abono,
    )


def _anulada(k: int, hoy: date) -> DemoSale:
    inicio = hoy - timedelta(days=5)
    return DemoSale(
        MENSUAL.name,
        inicio,
        "cancelled",
        inicio + timedelta(days=MENSUAL.duration_days),
        first_payment=_completo(MENSUAL, METODOS[k % 3], inicio),
        cancel=True,
    )


def _ventas(hoy: date, dias: int) -> list[DemoSale]:
    """Las 30 ventas: 12 al día, 5 por vencer, 6 vencidas, 2 congeladas, 3 pendientes de pago
    y 2 anuladas."""
    return [
        *(_vigente(k, hoy, dias) for k in range(12)),
        *(_por_vencer(k, hoy, dias) for k in range(5)),
        *(_vencida(k, hoy) for k in range(6)),
        *(_congelada(k, hoy) for k in range(2)),
        *(_pendiente(k, hoy) for k in range(3)),
        *(_anulada(k, hoy) for k in range(2)),
    ]


def _socio(i: int, venta: DemoSale) -> DemoMember:
    """El socio ficticio número `i` (1 a 30)."""
    return DemoMember(
        document=f"{DEMO_DOCUMENT_PREFIX}{i:07d}",
        first_name=_NOMBRES[i - 1],
        last_name=_APELLIDOS[i % len(_APELLIDOS)],
        sex=_sexo(i),
        phone=f"300 000 00{i:02d}",
        email=f"demo+{i:02d}@ejemplo.invalid",
        birth_date=date(1975 + (i * 7) % 30, 1 + i % 12, 1 + (i * 3) % 28),
        sale=venta,
    )


def demo_dataset(today: date, expiring_days: int) -> DemoSpec:
    """3 planes y 30 socios ficticios con ventas y pagos en los seis estados (S4B-D32)."""
    socios = tuple(_socio(i, venta) for i, venta in enumerate(_ventas(today, expiring_days), 1))
    return DemoSpec(plans=PLANS, members=socios)
