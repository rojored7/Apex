"""`notifications.service` de plantillas con PostgreSQL real (S5-B6, US-120; S5-D24, S5-D25).
# Rojo B6

- `create_template`: `TemplateOut`, `created_by` = actor, una fila `insert` en la auditoría; el
  nombre se recorta; un nombre repetido da `TemplateNameTaken` (409, `field="name"`,
  `existing_id`) y no escribe; una variable desconocida en `subject` o `body` da `TemplateError`
  con ese `field` y no escribe.
- `update_template`: aplica solo lo enviado; un nombre ajeno repetido da 409; el propio nombre no
  choca consigo mismo; sin cambios no audita; id inexistente da `TemplateNotFound`.
- `get_template` y `list_templates` (búsqueda `q` sin tildes ni mayúsculas, comodines escapados,
  orden `name, id`, paginación).
- `preview(subject, body)`: renderiza con el contexto de ejemplo y no escribe nada.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import FrozenClock
from app.core.pagination import PageParams
from app.modules.notifications import service
from app.modules.notifications.exceptions import (
    TemplateError,
    TemplateNameTaken,
    TemplateNotFound,
)
from app.modules.notifications.schemas import PreviewOut, TemplateOut, TemplatePatch
from tests.conftest import CrearUsuario, UsuarioPrueba
from tests.factories.notifications import make_template
from tests.notifications._apoyo import (
    CAMPOS_PLANTILLA,
    EJEMPLO_RENDER,
    EJEMPLO_TEXTO,
    T_PLANTILLAS,
    contar,
    en_peticion,
    fila,
    filas_de_auditoria,
    plantilla_in,
)


@pytest.fixture
async def admin(usuario_real: CrearUsuario, reloj: FrozenClock) -> UsuarioPrueba:
    return await usuario_real("admin")


# create_template --------------------------------------------------------------------------------


async def test_create_template_devuelve_el_contrato_y_guarda_la_fila(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    salida = await en_peticion(
        session, admin.id, lambda: service.create_template(session, plantilla_in())
    )
    assert isinstance(salida, TemplateOut)
    assert set(salida.model_dump()) == CAMPOS_PLANTILLA
    assert (salida.name, salida.subject) == ("Vence pronto", "Tu membresía vence pronto")
    guardada = await fila(session, T_PLANTILLAS, salida.id)
    assert guardada["created_by"] == admin.id
    assert guardada["body"] == salida.body
    assert guardada["created_at"] == salida.created_at


async def test_create_template_audita_un_insert_a_nombre_del_actor(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    await en_peticion(session, admin.id, lambda: service.create_template(session, plantilla_in()))
    assert await filas_de_auditoria(session, T_PLANTILLAS) == [("insert", admin.id)]


async def test_create_template_recorta_el_nombre(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    salida = await en_peticion(
        session, admin.id, lambda: service.create_template(session, plantilla_in(name="  Venció  "))
    )
    assert salida.name == "Venció"


async def test_create_template_con_nombre_repetido_da_409_y_no_escribe(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    existente = await make_template(session, name="Vence pronto")
    antes = await contar(session, T_PLANTILLAS)
    with pytest.raises(TemplateNameTaken) as capturado:
        await en_peticion(
            session,
            admin.id,
            lambda: service.create_template(session, plantilla_in(name=" Vence pronto ")),
        )
    error = capturado.value
    assert (error.status, error.code, error.field) == (409, "template_name_taken", "name")
    assert error.existing_id == existente.id
    await session.rollback()
    assert await contar(session, T_PLANTILLAS) == antes


@pytest.mark.parametrize("campo", ["subject", "body"])
async def test_create_template_con_variable_desconocida_da_422_con_el_campo(
    session: AsyncSession, admin: UsuarioPrueba, campo: str
) -> None:
    datos = plantilla_in(**{campo: "Hola {apellido}"})
    with pytest.raises(TemplateError) as capturado:
        await en_peticion(session, admin.id, lambda: service.create_template(session, datos))
    assert capturado.value.field == campo
    assert await contar(session, T_PLANTILLAS) == 0


# update_template --------------------------------------------------------------------------------


async def test_update_template_aplica_solo_lo_enviado(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    base = await make_template(session, name="Vence pronto", subject="Asunto", body="Hola {nombre}")
    parche = TemplatePatch(body="Hola {nombre}, vence el {vence}")
    salida = await en_peticion(
        session, admin.id, lambda: service.update_template(session, base.id, parche)
    )
    assert salida.body == "Hola {nombre}, vence el {vence}"
    assert (salida.name, salida.subject) == ("Vence pronto", "Asunto")
    guardada = await fila(session, T_PLANTILLAS, base.id)
    assert guardada["body"] == "Hola {nombre}, vence el {vence}"


async def test_update_template_audita_un_update_a_nombre_del_actor(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    base = await make_template(session)
    await en_peticion(
        session,
        admin.id,
        lambda: service.update_template(session, base.id, TemplatePatch(subject="Nuevo asunto")),
    )
    assert await filas_de_auditoria(session, T_PLANTILLAS) == [
        ("insert", base.created_by),
        ("update", admin.id),
    ]


async def test_update_template_sin_cambios_no_audita(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    base = await make_template(session)
    antes = await filas_de_auditoria(session, T_PLANTILLAS)
    salida = await en_peticion(
        session, admin.id, lambda: service.update_template(session, base.id, TemplatePatch())
    )
    assert salida.id == base.id and salida.name == base.name
    assert await filas_de_auditoria(session, T_PLANTILLAS) == antes


async def test_update_template_conserva_su_propio_nombre_sin_choque(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    base = await make_template(session, name="Vence pronto")
    salida = await en_peticion(
        session,
        admin.id,
        lambda: service.update_template(
            session, base.id, TemplatePatch(name="Vence pronto", subject="Otro")
        ),
    )
    assert salida.subject == "Otro"


async def test_update_template_con_el_nombre_de_otra_da_409_con_su_id(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    otra = await make_template(session, name="Venció")
    base = await make_template(session, name="Vence pronto")
    with pytest.raises(TemplateNameTaken) as capturado:
        await en_peticion(
            session,
            admin.id,
            lambda: service.update_template(session, base.id, TemplatePatch(name="Venció")),
        )
    assert capturado.value.existing_id == otra.id
    await session.rollback()


async def test_update_template_con_variable_desconocida_da_422_y_no_cambia_nada(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    base = await make_template(session, body="Hola {nombre}")
    with pytest.raises(TemplateError) as capturado:
        await en_peticion(
            session,
            admin.id,
            lambda: service.update_template(session, base.id, TemplatePatch(body="Hola {x}")),
        )
    assert capturado.value.field == "body"
    await session.rollback()
    assert (await fila(session, T_PLANTILLAS, base.id))["body"] == "Hola {nombre}"


async def test_update_template_inexistente_da_404(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    with pytest.raises(TemplateNotFound) as capturado:
        await en_peticion(
            session,
            admin.id,
            lambda: service.update_template(session, uuid4(), TemplatePatch(name="X")),
        )
    assert (capturado.value.status, capturado.value.code) == (404, "template_not_found")


# get_template y list_templates ------------------------------------------------------------------


async def test_get_template_devuelve_la_plantilla(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    base = await make_template(session, name="Venció")
    salida = await service.get_template(session, base.id)
    assert salida.id == base.id and salida.name == "Venció"


async def test_get_template_inexistente_da_404(session: AsyncSession, admin: UsuarioPrueba) -> None:
    with pytest.raises(TemplateNotFound):
        await service.get_template(session, uuid4())


async def test_list_templates_ordena_por_nombre_y_pagina(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    for nombre in ("Delta", "Alfa", "Charlie", "Bravo", "Eco"):
        await make_template(session, name=nombre)
    pagina = await service.list_templates(session, None, PageParams(limit=2, offset=2))
    assert (pagina.total, pagina.limit, pagina.offset) == (5, 2, 2)
    assert [t.name for t in pagina.items] == ["Charlie", "Delta"]


async def test_list_templates_busca_sin_tildes_ni_mayusculas(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    await make_template(session, name="Vence pronto")
    await make_template(session, name="Venció")
    por_tilde = await service.list_templates(session, "VENCIO", PageParams())
    assert [t.name for t in por_tilde.items] == ["Venció"]
    por_texto = await service.list_templates(session, "pronto", PageParams())
    assert [t.name for t in por_texto.items] == ["Vence pronto"]


async def test_list_templates_trata_los_comodines_como_texto(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    await make_template(session, name="Vence pronto")
    for comodin in ("%", "_", "V_nce"):
        pagina = await service.list_templates(session, comodin, PageParams())
        assert pagina.total == 0, comodin


async def test_list_templates_sin_filas_devuelve_pagina_vacia(
    session: AsyncSession, admin: UsuarioPrueba
) -> None:
    pagina = await service.list_templates(session, None, PageParams())
    assert (pagina.items, pagina.total) == ([], 0)


# preview ----------------------------------------------------------------------------------------


def test_preview_renderiza_asunto_y_cuerpo_con_el_contexto_de_ejemplo() -> None:
    salida = service.preview(EJEMPLO_TEXTO, f"Cuerpo: {EJEMPLO_TEXTO}")
    assert isinstance(salida, PreviewOut)
    assert salida.subject == EJEMPLO_RENDER
    assert salida.body == f"Cuerpo: {EJEMPLO_RENDER}"


def test_preview_respeta_las_llaves_literales() -> None:
    salida = service.preview("Usa {{nombre}}", "Hola {nombre}")
    assert (salida.subject, salida.body) == ("Usa {nombre}", "Hola Ana")


@pytest.mark.parametrize(
    ("asunto", "cuerpo", "campo"), [("{x}", "ok", "subject"), ("ok", "{x}", "body")]
)
def test_preview_con_variable_desconocida_da_422_con_el_campo(
    asunto: str, cuerpo: str, campo: str
) -> None:
    with pytest.raises(TemplateError) as capturado:
        service.preview(asunto, cuerpo)
    assert capturado.value.field == campo


async def test_preview_no_escribe_nada(session: AsyncSession, admin: UsuarioPrueba) -> None:
    service.preview("Hola {nombre}", "Plan {plan}")
    assert await contar(session, T_PLANTILLAS) == 0
    assert await filas_de_auditoria(session, T_PLANTILLAS) == []
