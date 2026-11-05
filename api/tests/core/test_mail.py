"""`core/mail.py` (S5-B4; S5-D64, M-7 a, b y c). Rojo B4.

Con `instalar_smtp` (doble de `smtplib.SMTP`): envío de texto plano; un salto de línea en el asunto
o en el nombre del remitente se rechaza sin enviar (M-7 a); destinatario inválido da
`invalid_recipient`; `starttls` con el contexto por defecto, que verifica el certificado y el nombre
del servidor (M-7 b); `none` solo con `ENV=dev`; `timeout`, `auth`, `refused` y `unknown`; `repr`
sin `to` ni `body`; nunca HTML (M-7 c); la excepción del servidor no se registra con direcciones.
"""

from __future__ import annotations

import ast
import logging
import smtplib
import ssl
import threading
from pathlib import Path
from typing import Any

import pytest

from app.core import mail
from app.core.config import ConfigError, Settings
from app.core.mail import (
    MAIL_ERROR_CODES,
    MailMessage,
    MailResult,
    mail_configured,
    send_mail,
)
from tests.core._canales_apoyo import (
    SMTP_COMPLETO,
    SmtpFalso,
    instalar_smtp,
    settings_canales,
)

DESTINO = "socia.privada@correo.test"
MAIL_PY = Path(mail.__file__)


def _codigo() -> str:
    """El código de `mail.py` sin docstrings: lo que dice la prosa no cuenta."""
    arbol = ast.parse(MAIL_PY.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            cuerpo = nodo.body
            if (
                cuerpo
                and isinstance(cuerpo[0], ast.Expr)
                and isinstance(cuerpo[0].value, ast.Constant)
            ):
                if isinstance(cuerpo[0].value.value, str):
                    nodo.body = cuerpo[1:] or [ast.Pass()]
    return ast.unparse(arbol)


@pytest.fixture
def smtp_falso(monkeypatch: pytest.MonkeyPatch) -> SmtpFalso:
    return instalar_smtp(monkeypatch)


@pytest.fixture
def configuracion() -> Settings:
    return settings_canales(**SMTP_COMPLETO)


def _mensaje(**cambios: Any) -> MailMessage:
    base: dict[str, Any] = {
        "to": DESTINO,
        "subject": "Tu membresía vence pronto",
        "body": "Hola, tu plan vence el viernes.",
    }
    return MailMessage(**{**base, **cambios})


# Envío -----------------------------------------------------------------------------------------


async def test_envia_un_correo_de_texto_plano_y_devuelve_ok(
    smtp_falso: SmtpFalso, configuracion: Settings
) -> None:
    resultado = await send_mail(
        configuracion,
        _mensaje(reply_to="recepcion@gimnasio.test", from_name="APEX CrossFit"),
    )

    assert resultado == MailResult(ok=True, error_code=None)
    assert len(smtp_falso.conexiones) == 1
    conexion = smtp_falso.conexiones[0]
    assert (conexion.host, conexion.port) == ("smtp.ejemplo.test", 587)
    [enviado] = conexion.mensajes
    assert enviado["To"] == DESTINO
    assert "apex@ejemplo.test" in str(enviado["From"])
    assert "APEX CrossFit" in str(enviado["From"])
    assert enviado["Subject"] == "Tu membresía vence pronto"
    assert "recepcion@gimnasio.test" in str(enviado["Reply-To"])
    assert enviado.get_content_type() == "text/plain"
    assert not enviado.is_multipart()
    assert enviado.get_content().strip() == "Hola, tu plan vence el viernes."


async def test_abre_la_conexion_con_el_timeout_de_settings_y_en_otro_hilo(
    smtp_falso: SmtpFalso,
) -> None:
    configuracion = settings_canales(**SMTP_COMPLETO, NOTIFY_NET_TIMEOUT_S=7)

    await send_mail(configuracion, _mensaje())

    conexion = smtp_falso.conexiones[0]
    assert conexion.kwargs.get("timeout") == 7
    assert conexion.hilo != threading.get_ident(), "smtplib bloquea: va en asyncio.to_thread"


async def test_starttls_va_antes_del_login_y_el_login_antes_del_envio(
    smtp_falso: SmtpFalso, configuracion: Settings
) -> None:
    await send_mail(configuracion, _mensaje())

    conexion = smtp_falso.conexiones[0]
    pasos = [e for e in conexion.eventos if e in ("starttls", "login", "send_message")]
    assert pasos == ["starttls", "login", "send_message"]
    assert conexion.credenciales == ("apex", "clave-smtp-no-real")


async def test_starttls_usa_el_contexto_por_defecto_que_verifica_certificado_y_nombre(
    smtp_falso: SmtpFalso, configuracion: Settings
) -> None:
    await send_mail(configuracion, _mensaje())

    contexto = smtp_falso.conexiones[0].contexto
    assert isinstance(contexto, ssl.SSLContext), "starttls sin contexto no verifica nada"
    assert contexto.verify_mode == ssl.CERT_REQUIRED
    assert contexto.check_hostname is True


async def test_con_tls_none_en_desarrollo_no_hace_starttls(smtp_falso: SmtpFalso) -> None:
    configuracion = settings_canales(**SMTP_COMPLETO, SMTP_TLS_MODE="none", ENV="dev")

    resultado = await send_mail(configuracion, _mensaje())

    assert resultado.ok is True
    assert "starttls" not in smtp_falso.conexiones[0].eventos


def test_tls_none_se_rechaza_al_cargar_fuera_de_dev() -> None:
    with pytest.raises(ConfigError) as excinfo:
        settings_canales(
            **SMTP_COMPLETO,
            SMTP_TLS_MODE="none",
            ENV="production",
            COOKIE_SECURE=True,
        )
    assert "SMTP_TLS_MODE" in excinfo.value.invalid


async def test_send_mail_no_envia_con_tls_none_fuera_de_dev_aunque_la_configuracion_lo_permita(
    smtp_falso: SmtpFalso,
) -> None:
    """Defensa en profundidad: una `Settings` armada a mano (`model_copy` no valida) con
    `none` y `ENV=production` no puede mandar un correo ni sus credenciales sin cifrar."""
    insegura = settings_canales(**SMTP_COMPLETO).model_copy(
        update={"SMTP_TLS_MODE": "none", "ENV": "production"}
    )

    resultado = await send_mail(insegura, _mensaje())

    assert resultado.ok is False
    assert resultado.error_code in MAIL_ERROR_CODES
    assert smtp_falso.mensajes == []
    assert all(c.credenciales is None for c in smtp_falso.conexiones)


# Inyección de cabeceras (M-7 a) -------------------------------------------------------------------


@pytest.mark.parametrize(
    "cambios",
    [
        {"subject": "Ana\r\nBcc: espia@malo.test"},
        {"subject": "Ana\nBcc: espia@malo.test"},
        {"from_name": "Ana\r\nBcc: espia@malo.test"},
        {"from_name": "Ana\nBcc: espia@malo.test"},
        {"reply_to": "ana@x.test\r\nBcc: espia@malo.test"},
        # Revisión de seguridad (LOW 2): separadores de línea de Unicode y NEL.
        {"subject": "Ana\u2028Bcc: espia@malo.test"},
        {"subject": "Ana\u2029Bcc: espia@malo.test"},
        {"subject": "Ana\x85Bcc: espia@malo.test"},
        {"from_name": "Ana\u2028Bcc: espia@malo.test"},
        {"from_name": "Ana\u2029Bcc: espia@malo.test"},
        {"from_name": "Ana\x85Bcc: espia@malo.test"},
    ],
    ids=[
        "asunto_crlf",
        "asunto_lf",
        "nombre_crlf",
        "nombre_lf",
        "reply_to_crlf",
        "asunto_u2028",
        "asunto_u2029",
        "asunto_nel",
        "nombre_u2028",
        "nombre_u2029",
        "nombre_nel",
    ],
)
async def test_un_salto_de_linea_en_una_cabecera_se_rechaza_sin_enviar(
    smtp_falso: SmtpFalso, configuracion: Settings, cambios: dict[str, str]
) -> None:
    resultado = await send_mail(configuracion, _mensaje(**cambios))

    assert resultado.ok is False
    assert resultado.error_code in MAIL_ERROR_CODES
    assert smtp_falso.mensajes == [], "el mensaje con cabeceras inyectadas no debe salir"
    assert resultado.error_code == "unknown"
    assert smtp_falso.conexiones == []


# Destinatario ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "destino",
    [
        "sin-arroba",
        "dos@@correo.test",
        "con espacio@correo.test",
        "ana@sinpunto",
        "",
        "ana@correo.test\r\nBcc: espia@malo.test",
    ],
)
async def test_destinatario_invalido_da_invalid_recipient_sin_conectar(
    smtp_falso: SmtpFalso, configuracion: Settings, destino: str
) -> None:
    resultado = await send_mail(configuracion, _mensaje(to=destino))

    assert resultado == MailResult(ok=False, error_code="invalid_recipient")
    assert smtp_falso.conexiones == [], "un destinatario inválido no abre ni la conexión"


# Errores del servidor -------------------------------------------------------------------------


@pytest.mark.parametrize("etapa", ["init", "starttls", "login", "send_message"])
async def test_un_timeout_en_cualquier_etapa_da_timeout(
    smtp_falso: SmtpFalso, configuracion: Settings, etapa: str
) -> None:
    smtp_falso.fallo, smtp_falso.etapa = TimeoutError("timed out"), etapa

    resultado = await send_mail(configuracion, _mensaje())

    assert resultado == MailResult(ok=False, error_code="timeout")


async def test_la_autenticacion_fallida_da_auth(
    smtp_falso: SmtpFalso, configuracion: Settings
) -> None:
    smtp_falso.fallo = smtplib.SMTPAuthenticationError(535, b"credenciales rechazadas")
    smtp_falso.etapa = "login"

    resultado = await send_mail(configuracion, _mensaje())

    assert resultado == MailResult(ok=False, error_code="auth")
    assert smtp_falso.mensajes == []


@pytest.mark.parametrize(
    "fallo",
    [
        smtplib.SMTPRecipientsRefused({DESTINO: (550, b"no existe")}),
        smtplib.SMTPSenderRefused(550, b"remitente no autorizado", "apex@ejemplo.test"),
    ],
    ids=["destinatarios", "remitente"],
)
async def test_un_rechazo_del_servidor_da_refused(
    smtp_falso: SmtpFalso, configuracion: Settings, fallo: Exception
) -> None:
    smtp_falso.fallo, smtp_falso.etapa = fallo, "send_message"

    resultado = await send_mail(configuracion, _mensaje())

    assert resultado == MailResult(ok=False, error_code="refused")


@pytest.mark.parametrize(
    "fallo",
    [smtplib.SMTPException("raro"), RuntimeError("otro"), OSError("red caída")],
    ids=["smtp", "runtime", "oserror"],
)
async def test_cualquier_otro_fallo_da_unknown_y_no_propaga(
    smtp_falso: SmtpFalso, configuracion: Settings, fallo: Exception
) -> None:
    smtp_falso.fallo, smtp_falso.etapa = fallo, "send_message"

    resultado = await send_mail(configuracion, _mensaje())

    assert resultado == MailResult(ok=False, error_code="unknown")


async def test_la_conexion_se_cierra_aunque_el_envio_falle(
    smtp_falso: SmtpFalso, configuracion: Settings
) -> None:
    smtp_falso.fallo, smtp_falso.etapa = RuntimeError("falló"), "send_message"

    await send_mail(configuracion, _mensaje())

    assert [c.cerrada for c in smtp_falso.conexiones] == [True]


async def test_el_mensaje_de_la_excepcion_con_direcciones_no_llega_al_log_ni_al_resultado(
    smtp_falso: SmtpFalso, configuracion: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    smtp_falso.fallo = smtplib.SMTPRecipientsRefused({DESTINO: (550, b"buzon de socia.privada")})
    smtp_falso.etapa = "send_message"

    resultado = await send_mail(configuracion, _mensaje())

    texto = caplog.text + " ".join(str(vars(r)) for r in caplog.records) + repr(resultado)
    assert "socia.privada" not in texto
    assert "clave-smtp-no-real" not in texto
    assert all(r.exc_info is None for r in caplog.records), "el traceback lleva el mensaje"


# Correo no configurado ------------------------------------------------------------------------


def test_mail_configured_pide_host_y_remitente() -> None:
    assert mail_configured(settings_canales(**SMTP_COMPLETO)) is True
    assert mail_configured(settings_canales()) is False
    sin_host = settings_canales(**SMTP_COMPLETO).model_copy(update={"SMTP_HOST": None})
    sin_remitente = settings_canales(**SMTP_COMPLETO).model_copy(update={"SMTP_FROM": None})
    assert mail_configured(sin_host) is False
    assert mail_configured(sin_remitente) is False


async def test_sin_correo_configurado_no_conecta_y_devuelve_fallo(smtp_falso: SmtpFalso) -> None:
    resultado = await send_mail(settings_canales(), _mensaje())

    assert resultado.ok is False
    assert resultado.error_code in MAIL_ERROR_CODES
    assert smtp_falso.conexiones == []


# Datos del mensaje y del resultado --------------------------------------------------------------


def test_el_repr_del_mensaje_no_lleva_el_destinatario_ni_el_cuerpo() -> None:
    mensaje = _mensaje(body="Cuerpo con datos privados 1020304417")

    texto = repr(mensaje) + str(mensaje)

    assert DESTINO not in texto
    assert "socia.privada" not in texto
    assert "1020304417" not in texto
    assert "Tu membresía vence pronto" in texto, "el asunto sí ayuda a depurar"


def test_los_codigos_de_error_son_los_cinco_del_plan() -> None:
    assert MAIL_ERROR_CODES == ("timeout", "auth", "refused", "invalid_recipient", "unknown")


# Solo texto plano (M-7 c) -------------------------------------------------------------------------


async def test_un_cuerpo_con_html_viaja_literal_en_texto_plano(
    smtp_falso: SmtpFalso, configuracion: Settings
) -> None:
    cuerpo = '<b>Hola</b> <a href="https://malo.test">haz clic</a>'

    await send_mail(configuracion, _mensaje(body=cuerpo))

    [enviado] = smtp_falso.mensajes
    partes = list(enviado.walk())
    assert [p.get_content_type() for p in partes] == ["text/plain"]
    assert cuerpo in enviado.get_content()


def test_mail_py_nunca_arma_html_ni_alternativas() -> None:
    fuente = _codigo()
    arbol = ast.parse(fuente)
    llamadas = {
        getattr(n.func, "attr", getattr(n.func, "id", ""))
        for n in ast.walk(arbol)
        if isinstance(n, ast.Call)
    }
    assert "add_alternative" not in llamadas
    assert "text/html" not in fuente
    assert 'subtype="html"' not in fuente


def test_mail_py_usa_to_thread_starttls_y_el_contexto_por_defecto() -> None:
    """Estático: la prueba funcional de arriba lo vigila con el doble; esto fija el cómo."""
    fuente = _codigo()
    assert "asyncio.to_thread" in fuente
    assert "starttls(" in fuente
    assert "ssl.create_default_context" in fuente
    assert "_create_unverified_context" not in fuente
    assert "CERT_NONE" not in fuente
    assert "SMTP_SSL" not in fuente
