"""`rules.apply_freeze` (S3-B2, US-089; blueprint B2 "Rojo"; D14, Q9, RN-07, N-25). Puras, sin base.

"Hoy" es 2026-10-21 salvo donde se dice. La membresía base va del 2026-10-01 al 2026-10-31
(estado guardado `active`; con `expiring_days = 7` hoy es `active`: faltan 10 días). Fechas a mano
(RN-07, `days = (frozen_to - frozen_from) + 1`, el fin se corre esos días):
- 21 a 30 de octubre son 10 días: el fin pasa del 31 de octubre al 10 de noviembre;
- un día (hoy a hoy) corre el fin al 1 de noviembre;
- con hoy = 2026-10-15, la ventana futura 20 a 24 de octubre (5 días) corre el fin al 5 de
  noviembre y la membresía sigue `active` (quedan 21 días);
- Q9 con `max_retroactive_days = 7`: desde el 14 de octubre (hoy - 7) se acepta y desde el 13 no;
  `max_days = 30`: hoy a 2026-11-19 (30 días) se acepta y hasta el 20 (31) no; `max_count = 2`:
  la segunda se acepta y la tercera no.

Orden de validación de D14 (lo fija la prueba de orden): estado efectivo (409
`membership_not_freezable`), fechas invertidas (422 `validation_error`, `field="frozen_to"`),
retroactividad (422 `freeze_too_retroactive`, `field="frozen_from"`), vigencia (422
`freeze_outside_validity`, `field="frozen_from"`), ya programada (409 `freeze_already_scheduled`),
veces (409 `freeze_limit_reached`) y días (409 `freeze_days_exceeded`, con los días disponibles en
el mensaje). `frozen_to = 9999-12-31` da `freeze_days_exceeded` y nunca `OverflowError`. La entrada
no se muta.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import date, timedelta
from uuid import UUID

import pytest

from app.modules.memberships.rules import (
    FreezeError,
    FreezeLimits,
    FreezeOutcome,
    FreezeWindow,
    MembershipSnapshot,
    MembershipStatus,
    apply_freeze,
    compute_status,
)

HOY = date(2026, 10, 21)
INICIO = date(2026, 10, 1)
FIN = date(2026, 10, 31)
EXPIRING_DAYS = 7
LIMITES = FreezeLimits(max_days=30, max_count=2, max_retroactive_days=7)
ID = UUID("0000000b-0000-4000-8000-00000000b001")


def _m(
    status: MembershipStatus = MembershipStatus.active,
    start: date = INICIO,
    end: date = FIN,
    classes_remaining: int | None = None,
) -> MembershipSnapshot:
    return MembershipSnapshot(
        id=ID, status=status, start_date=start, end_date=end, classes_remaining=classes_remaining
    )


def _congelar(
    desde: date,
    hasta: date,
    *,
    m: MembershipSnapshot | None = None,
    previas: tuple[FreezeWindow, ...] | list[FreezeWindow] = (),
    limites: FreezeLimits = LIMITES,
    hoy: date = HOY,
) -> FreezeOutcome:
    return apply_freeze(m or _m(), previas, desde, hasta, limites, hoy, EXPIRING_DAYS)


def _rechazo(desde: date, hasta: date, **kwargs: object) -> FreezeError:
    with pytest.raises(FreezeError) as error:
        _congelar(desde, hasta, **kwargs)  # type: ignore[arg-type]
    return error.value


def _firma(error: FreezeError) -> tuple[str, str | None, int]:
    return (error.code, error.field, error.status)


# Caso feliz y RN-07 -------------------------------------------------------------------------------


def test_diez_dias_desde_hoy_corren_el_fin_al_10_de_noviembre_y_queda_congelada() -> None:
    salida = _congelar(HOY, date(2026, 10, 30))
    assert salida.window == FreezeWindow(HOY, date(2026, 10, 30))
    assert salida.window.days == 10
    assert salida.new_end_date == date(2026, 11, 10)
    despues = replace(_m(), end_date=salida.new_end_date)
    assert compute_status(despues, HOY, EXPIRING_DAYS, [salida.window]) == MembershipStatus.frozen


def test_una_ventana_de_un_dia_suma_un_dia() -> None:
    salida = _congelar(HOY, HOY)
    assert salida.window.days == 1
    assert salida.new_end_date == date(2026, 11, 1)


def test_una_ventana_futura_corre_el_fin_y_la_membresia_sigue_al_dia() -> None:
    hoy = date(2026, 10, 15)
    salida = _congelar(date(2026, 10, 20), date(2026, 10, 24), hoy=hoy)
    assert salida.window.days == 5
    assert salida.new_end_date == date(2026, 11, 5)
    despues = replace(_m(), end_date=salida.new_end_date)
    assert compute_status(despues, hoy, EXPIRING_DAYS, [salida.window]) == MembershipStatus.active


def test_una_por_vencer_tambien_se_congela() -> None:
    """Fin el 25: faltan 4 días, `expiring` (D14 acepta `active` o `expiring`)."""
    salida = _congelar(HOY, date(2026, 10, 23), m=_m(end=date(2026, 10, 25)))
    assert salida.new_end_date == date(2026, 10, 28)


def test_n25_dentro_de_la_ventana_es_frozen_y_fuera_vuelve_al_estado_por_fecha() -> None:
    """Tras congelar 21 a 30 de octubre (fin 10 de noviembre): `frozen` el 21 y el 30; el 31
    quedan 10 días (`active`); el 3 de noviembre quedan 7 (`expiring`); el 11, `expired`."""
    salida = _congelar(HOY, date(2026, 10, 30))
    despues = replace(_m(), end_date=salida.new_end_date)
    ventanas = [salida.window]
    esperados = {
        HOY: MembershipStatus.frozen,
        date(2026, 10, 30): MembershipStatus.frozen,
        date(2026, 10, 31): MembershipStatus.active,
        date(2026, 11, 3): MembershipStatus.expiring,
        date(2026, 11, 11): MembershipStatus.expired,
    }
    for dia, estado in esperados.items():
        assert compute_status(despues, dia, EXPIRING_DAYS, ventanas) == estado, dia


# Q9: retroactividad, días y veces en sus fronteras ---------------------------------------------


def test_hoy_menos_7_se_acepta_y_hoy_menos_8_es_freeze_too_retroactive() -> None:
    salida = _congelar(date(2026, 10, 14), date(2026, 10, 20))
    assert (salida.window.days, salida.new_end_date) == (7, date(2026, 11, 7))
    error = _rechazo(date(2026, 10, 13), date(2026, 10, 20))
    assert _firma(error) == ("freeze_too_retroactive", "frozen_from", 422)


def test_sin_retroactividad_permitida_solo_desde_hoy() -> None:
    limites = replace(LIMITES, max_retroactive_days=0)
    assert _congelar(HOY, HOY, limites=limites).new_end_date == date(2026, 11, 1)
    error = _rechazo(HOY - timedelta(days=1), HOY, limites=limites)
    assert error.code == "freeze_too_retroactive"


def test_30_dias_exactos_se_aceptan_y_31_son_freeze_days_exceeded() -> None:
    salida = _congelar(HOY, date(2026, 11, 19))
    assert (salida.window.days, salida.new_end_date) == (30, date(2026, 11, 30))
    error = _rechazo(HOY, date(2026, 11, 20))
    assert _firma(error) == ("freeze_days_exceeded", None, 409)
    assert "30" in error.message


def test_los_dias_de_las_ventanas_previas_cuentan_para_el_tope() -> None:
    """Una previa ya terminada de 10 días (1 a 10 de octubre): quedan 20; 20 se aceptan, 21 no, y
    el mensaje dice los 20 disponibles."""
    previas = [FreezeWindow(date(2026, 10, 1), date(2026, 10, 10))]
    salida = _congelar(HOY, date(2026, 11, 9), previas=previas)
    assert (salida.window.days, salida.new_end_date) == (20, date(2026, 11, 20))
    error = _rechazo(HOY, date(2026, 11, 10), previas=previas)
    assert error.code == "freeze_days_exceeded"
    assert "20" in error.message


def test_la_segunda_se_acepta_y_la_tercera_es_freeze_limit_reached() -> None:
    una = [FreezeWindow(date(2026, 10, 1), date(2026, 10, 2))]
    dos = [*una, FreezeWindow(date(2026, 10, 5), date(2026, 10, 6))]
    assert _congelar(HOY, HOY, previas=una).new_end_date == date(2026, 11, 1)
    error = _rechazo(HOY, HOY, previas=dos)
    assert _firma(error) == ("freeze_limit_reached", None, 409)


def test_con_cero_veces_permitidas_ninguna_congelacion_entra() -> None:
    error = _rechazo(HOY, HOY, limites=replace(LIMITES, max_count=0))
    assert error.code == "freeze_limit_reached"


def test_una_previa_que_termino_ayer_no_esta_programada() -> None:
    previas = [FreezeWindow(date(2026, 10, 15), date(2026, 10, 20))]
    assert _congelar(HOY, HOY, previas=previas).new_end_date == date(2026, 11, 1)


# Rechazos por forma y por estado -----------------------------------------------------------------


def test_fechas_invertidas_son_validation_error_en_frozen_to_sin_value_error() -> None:
    error = _rechazo(date(2026, 10, 25), date(2026, 10, 24))
    assert _firma(error) == ("validation_error", "frozen_to", 422)


@pytest.mark.parametrize(
    ("m", "desde", "hasta"),
    [
        (_m(start=date(2026, 10, 18)), date(2026, 10, 15), date(2026, 10, 25)),
        (_m(start=date(2026, 10, 25), end=date(2026, 11, 24)), HOY, date(2026, 10, 26)),
        (
            _m(start=date(2026, 9, 1), end=date(2026, 10, 25)),
            date(2026, 10, 26),
            date(2026, 10, 27),
        ),
    ],
    ids=["antes-del-inicio", "membresia-que-aun-no-empieza", "despues-del-fin"],
)
def test_frozen_from_fuera_de_la_vigencia_es_freeze_outside_validity(
    m: MembershipSnapshot, desde: date, hasta: date
) -> None:
    error = _rechazo(desde, hasta, m=m)
    assert _firma(error) == ("freeze_outside_validity", "frozen_from", 422)


def test_frozen_from_en_el_ultimo_dia_de_vigencia_se_acepta() -> None:
    salida = _congelar(FIN, FIN)
    assert salida.new_end_date == date(2026, 11, 1)


def test_una_ventana_futura_ya_programada_es_freeze_already_scheduled() -> None:
    previas = [FreezeWindow(date(2026, 10, 25), date(2026, 10, 27))]
    error = _rechazo(HOY, HOY, previas=previas)
    assert _firma(error) == ("freeze_already_scheduled", None, 409)


@pytest.mark.parametrize(
    ("m", "previas"),
    [
        (_m(status=MembershipStatus.pending_payment), []),
        (_m(), [FreezeWindow(date(2026, 10, 20), date(2026, 10, 22))]),
        (_m(start=date(2026, 9, 1), end=date(2026, 10, 20)), []),
        (_m(classes_remaining=0), []),
        (_m(status=MembershipStatus.cancelled), []),
    ],
    ids=["pendiente-de-pago", "congelada-hoy", "vencida-por-fecha", "sin-clases", "cancelada"],
)
def test_los_estados_no_congelables_son_membership_not_freezable(
    m: MembershipSnapshot, previas: list[FreezeWindow]
) -> None:
    error = _rechazo(HOY, HOY, m=m, previas=previas)
    assert _firma(error) == ("membership_not_freezable", None, 409)


# Orden de validación (D14) -----------------------------------------------------------------------


def test_el_estado_va_antes_que_las_fechas_invertidas() -> None:
    error = _rechazo(
        date(2026, 10, 25), date(2026, 10, 24), m=_m(status=MembershipStatus.pending_payment)
    )
    assert error.code == "membership_not_freezable"


def test_las_fechas_invertidas_van_antes_que_la_retroactividad() -> None:
    error = _rechazo(date(2026, 10, 2), date(2026, 10, 1))
    assert error.code == "validation_error"


def test_la_retroactividad_va_antes_que_la_vigencia() -> None:
    """Desde el 1 de septiembre: fuera de la vigencia y también más de 7 días atrás."""
    error = _rechazo(date(2026, 9, 1), date(2026, 9, 2))
    assert error.code == "freeze_too_retroactive"


def test_la_vigencia_va_antes_que_la_ya_programada() -> None:
    previas = [FreezeWindow(date(2026, 10, 25), date(2026, 10, 27))]
    error = _rechazo(date(2026, 11, 5), date(2026, 11, 6), previas=previas)
    assert error.code == "freeze_outside_validity"


def test_la_ya_programada_va_antes_que_el_tope_de_veces() -> None:
    previas = [
        FreezeWindow(date(2026, 10, 1), date(2026, 10, 2)),
        FreezeWindow(date(2026, 10, 25), date(2026, 10, 27)),
    ]
    error = _rechazo(HOY, HOY, previas=previas)
    assert error.code == "freeze_already_scheduled"


def test_el_tope_de_veces_va_antes_que_el_de_dias() -> None:
    """Dos previas que ya suman los 30 días: la tercera es `freeze_limit_reached`."""
    previas = [
        FreezeWindow(date(2026, 10, 1), date(2026, 10, 15)),
        FreezeWindow(date(2026, 10, 16), date(2026, 10, 30)),
    ]
    error = _rechazo(
        date(2026, 10, 31), date(2026, 10, 31), previas=previas, hoy=date(2026, 10, 31)
    )
    assert error.code == "freeze_limit_reached"


# Robustez e inmutabilidad ------------------------------------------------------------------------


def test_frozen_to_enorme_es_freeze_days_exceeded_sin_overflow() -> None:
    error = _rechazo(HOY, date(9999, 12, 31))
    assert _firma(error) == ("freeze_days_exceeded", None, 409)


def test_la_entrada_no_se_muta() -> None:
    m = _m()
    previas = [FreezeWindow(date(2026, 10, 1), date(2026, 10, 2))]
    copia = list(previas)
    salida = _congelar(HOY, date(2026, 10, 30), m=m, previas=previas)
    assert previas == copia and len(previas) == 1
    assert m == _m() and m.end_date == FIN
    assert salida.window not in previas


def test_los_valores_de_congelacion_son_inmutables() -> None:
    salida = _congelar(HOY, HOY)
    with pytest.raises(FrozenInstanceError):
        salida.new_end_date = FIN  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        LIMITES.max_days = 99  # type: ignore[misc]


def test_freeze_error_lleva_codigo_campo_y_estado() -> None:
    error = FreezeError("freeze_outside_validity", field="frozen_from", status=422)
    assert _firma(error) == ("freeze_outside_validity", "frozen_from", 422)
    assert FreezeError("freeze_limit_reached").status == 409
