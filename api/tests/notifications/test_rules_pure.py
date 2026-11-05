"""Funciones puras de `notifications.rules` (S5-B6, US-120 y US-121; S5-D25). # Rojo B6

- `render(template, context)`: `{nombre} {plan} {vence} {dias}`; `{{` y `}}` son llaves literales;
  variable desconocida, ausente del contexto, llave sin cerrar o con formato (`{nombre!r}`,
  `{nombre.x}`, `{0}`, `{}`) lanzan `TemplateError`; el valor sustituido nunca se vuelve a expandir.
- `validate_template_vars(text, field)`: `TemplateError` con `field` y sin repetir el texto.
- `validate_rule(trigger, offset_days, channel)`: `RuleValidationError` con `field`.
- `target_dates(rule, end_date)` = `end_date + offset_days`; `days_value` = diferencia absoluta;
  `can_skip` solo `pending` y `failed`; `next_attempt_allowed` = `attempts < max_attempts`.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest

from app.modules.notifications.exceptions import RuleValidationError, TemplateError
from app.modules.notifications.models import NotificationRule
from app.modules.notifications.rules import (
    can_skip,
    days_value,
    next_attempt_allowed,
    render,
    render_subject,
    target_dates,
    validate_rule,
    validate_template_vars,
)

CONTEXTO = {"nombre": "Ana", "plan": "Mensual", "vence": "20 oct 2026", "dias": 3}


def _regla(trigger: str, offset_days: int) -> NotificationRule:
    return NotificationRule(
        name="r",
        trigger=trigger,
        offset_days=offset_days,
        channel="whatsapp_link",
        template_id=uuid4(),
        is_active=True,
        created_by=uuid4(),
    )


# render -----------------------------------------------------------------------------------------


def test_render_reemplaza_las_cuatro_variables() -> None:
    texto = "Hola {nombre}, tu plan {plan} vence el {vence} (en {dias} días)."
    assert render(texto, CONTEXTO) == "Hola Ana, tu plan Mensual vence el 20 oct 2026 (en 3 días)."


def test_render_acepta_la_misma_variable_varias_veces() -> None:
    assert render("{nombre} {nombre}", CONTEXTO) == "Ana Ana"


def test_render_convierte_el_entero_dias_a_texto() -> None:
    assert render("{dias}", {**CONTEXTO, "dias": 0}) == "0"


@pytest.mark.parametrize(
    ("plantilla", "esperado"),
    [
        ("Sin variables", "Sin variables"),
        ("", ""),
        ("{{nombre}}", "{nombre}"),
        ("Usa {{ y }} para llaves", "Usa { y } para llaves"),
        ("{{{nombre}}}", "{Ana}"),
        ("{{{{", "{{"),
        ("a%b $c", "a%b $c"),
    ],
)
def test_render_trata_las_llaves_dobles_como_literales(plantilla: str, esperado: str) -> None:
    assert render(plantilla, CONTEXTO) == esperado


def test_render_ignora_claves_de_contexto_que_la_plantilla_no_usa() -> None:
    assert render("{plan}", {**CONTEXTO, "extra": "x"}) == "Mensual"


def test_render_no_vuelve_a_expandir_el_valor_sustituido() -> None:
    contexto = {**CONTEXTO, "nombre": "{plan}", "plan": "{{dias}}"}
    assert render("{nombre}|{plan}", contexto) == "{plan}|{{dias}}"


@pytest.mark.parametrize(
    "plantilla",
    [
        "Hola {apellido}",
        "{Nombre}",
        "{}",
        "{0}",
        "{ nombre }",
        "{nombre!r}",
        "{nombre:>10}",
        "{nombre.upper}",
        "{nombre.__class__}",
        "{nombre[0]}",
        "Hola {nombre",
        "Hola nombre}",
        "}{",
    ],
)
def test_render_rechaza_variables_desconocidas_y_sintaxis_de_formato(plantilla: str) -> None:
    with pytest.raises(TemplateError):
        render(plantilla, CONTEXTO)


def test_render_rechaza_una_variable_conocida_ausente_del_contexto() -> None:
    contexto = {"nombre": "Ana", "plan": "Mensual", "vence": "20 oct 2026"}
    with pytest.raises(TemplateError):
        render("En {dias} días", contexto)


def test_el_error_de_render_es_un_422_de_dominio() -> None:
    with pytest.raises(TemplateError) as capturado:
        render("{apellido}", CONTEXTO)
    assert capturado.value.status == 422


# validate_template_vars -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "texto",
    [
        "Hola {nombre}",
        "{nombre} {plan} {vence} {dias}",
        "Sin variables",
        "{{apellido}} escapado",
        "Llaves {{ y }}",
    ],
)
def test_validate_template_vars_acepta_textos_bien_formados(texto: str) -> None:
    assert validate_template_vars(texto, "body") is None


@pytest.mark.parametrize("campo", ["subject", "body"])
@pytest.mark.parametrize("texto", ["Hola {apellido}", "{nombre", "x}", "{}", "{nombre!r}", "{0}"])
def test_validate_template_vars_rechaza_con_el_campo(campo: str, texto: str) -> None:
    with pytest.raises(TemplateError) as capturado:
        validate_template_vars(texto, campo)
    assert capturado.value.field == campo
    assert capturado.value.status == 422


def test_validate_template_vars_no_repite_el_texto_en_el_mensaje() -> None:
    with pytest.raises(TemplateError) as capturado:
        validate_template_vars("Hola {apellidoultrasecreto}", "body")
    assert "apellidoultrasecreto" not in capturado.value.message


# validate_rule ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("trigger", "offset", "channel"),
    [
        ("membership_expiring", -3, "whatsapp_link"),
        ("membership_expiring", 0, "email"),
        ("membership_expiring", -30, "email"),
        ("membership_expired", 1, "whatsapp_link"),
        ("membership_expired", 15, "email"),
    ],
)
def test_validate_rule_acepta_las_combinaciones_validas(
    trigger: str, offset: int, channel: str
) -> None:
    assert validate_rule(trigger, offset, channel) is None


@pytest.mark.parametrize(
    ("trigger", "offset"),
    [
        ("membership_expiring", 1),
        ("membership_expiring", 7),
        ("membership_expired", 0),
        ("membership_expired", -1),
    ],
)
def test_validate_rule_rechaza_el_signo_equivocado_con_field_offset_days(
    trigger: str, offset: int
) -> None:
    with pytest.raises(RuleValidationError) as capturado:
        validate_rule(trigger, offset, "whatsapp_link")
    assert capturado.value.field == "offset_days"
    assert capturado.value.status == 422


@pytest.mark.parametrize("trigger", ["membership_started", "", "EXPIRING"])
def test_validate_rule_rechaza_un_disparador_desconocido_con_field_trigger(trigger: str) -> None:
    with pytest.raises(RuleValidationError) as capturado:
        validate_rule(trigger, 1, "email")
    assert capturado.value.field == "trigger"


@pytest.mark.parametrize("channel", ["sms", "telegram", "push", "", "EMAIL"])
def test_validate_rule_rechaza_un_canal_desconocido_con_field_channel(channel: str) -> None:
    with pytest.raises(RuleValidationError) as capturado:
        validate_rule("membership_expiring", -3, channel)
    assert capturado.value.field == "channel"


# target_dates y days_value ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("trigger", "offset", "fin", "esperada"),
    [
        ("membership_expiring", -3, date(2026, 10, 25), date(2026, 10, 22)),
        ("membership_expiring", 0, date(2026, 10, 25), date(2026, 10, 25)),
        ("membership_expired", 1, date(2026, 10, 25), date(2026, 10, 26)),
        ("membership_expired", 15, date(2026, 10, 25), date(2026, 11, 9)),
        ("membership_expired", 7, date(2026, 12, 30), date(2027, 1, 6)),
        ("membership_expired", 1, date(2028, 2, 28), date(2028, 2, 29)),
        ("membership_expiring", -3, date(2026, 3, 2), date(2026, 2, 27)),
    ],
)
def test_target_dates_suma_el_desfase_al_fin_de_la_membresia(
    trigger: str, offset: int, fin: date, esperada: date
) -> None:
    assert target_dates(_regla(trigger, offset), fin) == esperada


@pytest.mark.parametrize(
    ("fin", "objetivo", "esperado"),
    [
        (date(2026, 10, 25), date(2026, 10, 22), 3),
        (date(2026, 10, 25), date(2026, 10, 26), 1),
        (date(2026, 10, 25), date(2026, 10, 25), 0),
        (date(2026, 10, 25), date(2026, 11, 9), 15),
        (date(2026, 12, 30), date(2027, 1, 6), 7),
    ],
)
def test_days_value_es_la_diferencia_absoluta_en_dias(
    fin: date, objetivo: date, esperado: int
) -> None:
    resultado = days_value(fin, objetivo)
    assert resultado == esperado and type(resultado) is int


# can_skip y next_attempt_allowed ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("estado", "esperado"),
    [
        ("pending", True),
        ("failed", True),
        ("sent", False),
        ("skipped", False),
        ("desconocido", False),
        ("", False),
    ],
)
def test_can_skip_solo_para_pending_y_failed(estado: str, esperado: bool) -> None:
    assert can_skip(estado) is esperado


@pytest.mark.parametrize(
    ("intentos", "maximo", "esperado"),
    [(0, 3, True), (2, 3, True), (3, 3, False), (4, 3, False), (0, 1, True), (0, 0, False)],
)
def test_next_attempt_allowed_mientras_queden_intentos(
    intentos: int, maximo: int, esperado: bool
) -> None:
    assert next_attempt_allowed(intentos, maximo) is esperado


# Defensa en profundidad (S5-D216) ----------------------------------------------------------------


@pytest.mark.parametrize("salto", ["\n", "\r", "\u2028", "\u2029", "\x85"])
def test_render_subject_rechaza_un_salto_de_linea_tras_sustituir(salto: str) -> None:
    contexto = {**CONTEXTO, "nombre": f"Ana{salto}Bcc: x@y.z"}
    with pytest.raises(TemplateError) as capturado:
        render_subject("Hola {nombre}", contexto)
    assert capturado.value.field == "subject"
    assert "Bcc" not in capturado.value.message


def test_render_subject_se_comporta_como_render_sin_saltos() -> None:
    assert render_subject("Hola {nombre} ({dias})", CONTEXTO) == "Hola Ana (3)"
    assert render_subject("{{x}}", CONTEXTO) == "{x}"


def test_el_cuerpo_si_admite_saltos_de_linea() -> None:
    assert render("{nombre}\n{plan}", CONTEXTO) == "Ana\nMensual"


def test_una_llave_sin_cierre_cercano_falla_rapido_sin_recorrer_el_texto() -> None:
    texto = "{" + "a" * 200_000
    with pytest.raises(TemplateError):
        validate_template_vars(texto, "body")
    with pytest.raises(TemplateError):
        render("{a" * 50_000, CONTEXTO)


def test_un_nombre_de_variable_de_mas_de_16_caracteres_se_rechaza_como_desconocido() -> None:
    with pytest.raises(TemplateError):
        validate_template_vars("{" + "n" * 17 + "}", "body")
