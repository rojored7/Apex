"""`python -m app.cli import-members <archivo> --as <correo> [--dry-run] [--report <nombre>]`
(S4B-B1, US-112; S4B-D34, D35, D64, D77; Q17).

Contrato (base real de prueba, `crypto_runtime`; `IMPORT_DIR` es una carpeta de `tmp_path`):
- salida 0 si la cabecera es válida (aunque haya filas rechazadas); 2 si la cabecera no coincide,
  el archivo está fuera de `IMPORT_DIR`, es un enlace, excede un límite o es peligroso, `--as` falta
  o no es un admin activo, o con `ENV=production` falta `--as` o se pide `--db-timeouts off`; 1 si
  falla una escritura;
- salida estándar: una línea `import-members: created=N skipped_existing=N rejected=N
  consent_missing=N notes_ignored=N contacts_omitted=N` y una advertencia que nombra
  `consent_missing` (y otra `notes_ignored`) cuando son mayores que 0;
- reporte (`--report <nombre>`): solo un nombre dentro de `IMPORT_DIR`, creado con `O_EXCL`,
  `O_NOFOLLOW` y modo 0o600; CSV `;` con BOM y columnas `fila;documento;resultado;motivo` donde
  `resultado` es `created`, `skipped_existing` o `rejected` y el documento va enmascarado;
- idempotente por `document_idx`; documentos repetidos dentro del archivo (`1.020.304`,
  `1020-304`, `1 020 304`) se saltan con "documento repetido en el archivo";
- auditoría `insert` por socio a nombre de `--as` y una entrada resumen `members.import_runs` con
  `file_sha256` y conteos, sin nombre de archivo; `--dry-run` no llama a `members.service.create`
  y no escribe nada;
- ni la salida, ni el reporte, ni `caplog` contienen un documento completo, teléfono o correo.
"""

from __future__ import annotations

import os
import re
import stat
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import openpyxl.xml
import pytest
from click.testing import Result
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.cli import app
from app.core.audit import AuditEntry
from app.core.config import Settings
from app.core.crypto.digest import sha256_hex
from app.imports.members_xlsx import MAX_FILE_BYTES, MAX_ROWS, TEMPLATE_HEADER
from app.modules.members import service as members_service
from app.modules.members.models import Member
from tests.cli import _apoyo_demo as demo
from tests.cli._apoyo import conteos_de_tablas, correr
from tests.conftest import CLAVE_PRUEBA
from tests.factories.users import make_user
from tests.factories.xlsx import (
    fila_valida,
    make_members_xlsx,
    make_oversized_xlsx,
    make_xlsx_billion_laughs,
    make_xlsx_with_entry,
    make_xlsx_xxe,
    make_zip_bomb,
    texto_incompresible,
)

Fabrica = async_sessionmaker[AsyncSession]
BOM = b"\xef\xbb\xbf"
CONTEOS_RE = re.compile(r"(\w+)=(\d+)")

pytestmark = pytest.mark.usefixtures("reloj", "limpiar_demo")


# Apoyo ----------------------------------------------------------------------------------------


@pytest.fixture
async def admin(limpiar_demo: Fabrica, argon2_rapido: None) -> Any:
    async with limpiar_demo() as sesion:
        return await make_user(sesion, role="admin", password=CLAVE_PRUEBA)


def _importar(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    archivo: Path,
    *extra: str,
    previo: Sequence[str] = (),
    env: Any = "dev",
) -> Result:
    args = [*previo, "import-members", str(archivo), *extra]
    return correr(app, args, env, base=settings, monkeypatch=monkeypatch)


def _libro(
    import_dir: Path, filas: Sequence[Sequence[object]], nombre: str = "socios.xlsx"
) -> Path:
    return make_members_xlsx(import_dir / nombre, filas)


def _conteos(salida: str) -> dict[str, int]:
    linea = next(ln for ln in salida.splitlines() if "created=" in ln)
    return {clave: int(valor) for clave, valor in CONTEOS_RE.findall(linea)}


async def _socios(fabrica: Fabrica) -> int:
    return (await demo.contar(fabrica))["socios"]


async def _conteos_base(fabrica: Fabrica) -> dict[str, int]:
    async with fabrica() as sesion:
        return await conteos_de_tablas(sesion)


async def _auditoria_de(fabrica: Fabrica, tabla: str) -> list[AuditEntry]:
    async with fabrica() as sesion:
        filas = await sesion.scalars(
            select(AuditEntry).where(AuditEntry.table_name == tabla).order_by(AuditEntry.seq)
        )
        return list(filas)


# Caso feliz e idempotencia --------------------------------------------------------------------


async def test_tres_filas_validas_crean_tres_socios(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    archivo = _libro(import_dir, [fila_valida(1), fila_valida(2), fila_valida(3)])

    resultado = _importar(settings_importacion, monkeypatch, archivo, "--as", admin.email)

    assert resultado.exit_code == 0, resultado.output
    conteos = _conteos(resultado.output)
    assert (conteos["created"], conteos["skipped_existing"], conteos["rejected"]) == (3, 0, 0)
    assert await _socios(limpiar_demo) == 3
    assert admin.email not in resultado.output


async def test_reimportar_salta_los_tres_sin_escribir_socios_ni_cifrado(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    archivo = _libro(import_dir, [fila_valida(1), fila_valida(2), fila_valida(3)])
    primera = _importar(settings_importacion, monkeypatch, archivo, "--as", admin.email)
    assert primera.exit_code == 0, primera.output
    antes = await _conteos_base(limpiar_demo)
    auditoria_antes = len(await _auditoria_de(limpiar_demo, "members.members"))

    segunda = _importar(settings_importacion, monkeypatch, archivo, "--as", admin.email)

    assert segunda.exit_code == 0, segunda.output
    conteos = _conteos(segunda.output)
    assert (conteos["created"], conteos["skipped_existing"]) == (0, 3)
    despues = await _conteos_base(limpiar_demo)
    assert despues["members"] == antes["members"] == 3
    assert despues["crypto_ops"] == antes["crypto_ops"]
    assert len(await _auditoria_de(limpiar_demo, "members.members")) == auditoria_antes


async def test_variantes_del_mismo_documento_dentro_del_archivo(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    filas = [
        fila_valida(1, documento="1.020.304", correo=None, telefono=None),
        fila_valida(2, documento="1020-304", correo=None, telefono=None),
        fila_valida(3, documento="1 020 304", correo=None, telefono=None),
    ]
    archivo = _libro(import_dir, filas)

    resultado = _importar(
        settings_importacion, monkeypatch, archivo, "--as", admin.email, "--report", "r.csv"
    )

    assert resultado.exit_code == 0, resultado.output
    conteos = _conteos(resultado.output)
    assert conteos["created"] == 1
    assert conteos["skipped_existing"] + conteos["rejected"] == 2
    assert await _socios(limpiar_demo) == 1
    reporte = (import_dir / "r.csv").read_bytes().decode("utf-8-sig")
    assert reporte.count("documento repetido en el archivo") == 2
    assert "1020304" not in resultado.output + reporte  # sólo enmascarado


async def test_una_fila_rechazada_no_impide_crear_el_resto(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    filas = [fila_valida(1), fila_valida(2, fecha_nacimiento="2001-02-30"), fila_valida(3)]
    archivo = _libro(import_dir, filas)

    resultado = _importar(
        settings_importacion, monkeypatch, archivo, "--as", admin.email, "--report", "r.csv"
    )

    assert resultado.exit_code == 0, resultado.output  # cabecera válida: 0 aunque haya rechazos
    conteos = _conteos(resultado.output)
    assert (conteos["created"], conteos["rejected"]) == (2, 1)
    assert await _socios(limpiar_demo) == 2
    reporte = (import_dir / "r.csv").read_bytes().decode("utf-8-sig")
    assert "2001-02-30" not in resultado.output + reporte  # sin el valor de la celda
    [linea] = [ln for ln in reporte.splitlines() if ln.startswith("3;")]  # fila 3 de la hoja
    assert "rejected" in linea


# Consentimiento, notas y contacto -------------------------------------------------------------


async def test_los_importados_quedan_sin_autorizacion_y_la_salida_advierte(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    archivo = _libro(import_dir, [fila_valida(1), fila_valida(2), fila_valida(3)])

    resultado = _importar(settings_importacion, monkeypatch, archivo, "--as", admin.email)

    assert resultado.exit_code == 0, resultado.output
    assert _conteos(resultado.output)["consent_missing"] == 3
    advertencias = [ln for ln in resultado.output.splitlines() if "consent_missing" in ln]
    assert len(advertencias) >= 2  # la línea de conteos y la advertencia
    async with limpiar_demo() as sesion:
        sin_autorizacion = await sesion.scalar(
            select(func.count()).select_from(Member).where(Member.data_consent_at.is_(None))
        )
    assert sin_autorizacion == 3


async def test_notas_se_ignora_y_el_contacto_incompleto_se_omite(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    filas = [
        fila_valida(1, notas="texto-privado-de-la-nota"),
        fila_valida(2, contacto_emergencia_telefono=None),
        fila_valida(3),
    ]
    archivo = _libro(import_dir, filas)

    resultado = _importar(
        settings_importacion, monkeypatch, archivo, "--as", admin.email, "--report", "r.csv"
    )

    assert resultado.exit_code == 0, resultado.output
    conteos = _conteos(resultado.output)
    assert (conteos["created"], conteos["notes_ignored"], conteos["contacts_omitted"]) == (3, 1, 1)
    assert "notes_ignored" in resultado.output.replace("notes_ignored=1", "", 1)  # advertencia
    reporte = (import_dir / "r.csv").read_bytes().decode("utf-8-sig")
    assert "contacto omitido" in reporte
    assert "texto-privado-de-la-nota" not in resultado.output + reporte
    async with limpiar_demo() as sesion:
        sin_contacto = await sesion.scalar(
            text("SELECT count(*) FROM members.members WHERE emergency_contact IS NULL")
        )
        total = await sesion.scalar(select(func.count()).select_from(Member))
    assert (sin_contacto, total) == (1, 3)


# Auditoría ------------------------------------------------------------------------------------


async def test_cada_alta_se_audita_a_nombre_de_as_y_hay_un_resumen_sin_nombre_de_archivo(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    archivo = _libro(import_dir, [fila_valida(1), fila_valida(2), fila_valida(3)])

    resultado = _importar(settings_importacion, monkeypatch, archivo, "--as", admin.email)

    assert resultado.exit_code == 0, resultado.output
    altas = [
        e for e in await _auditoria_de(limpiar_demo, "members.members") if e.action == "insert"
    ]
    assert len(altas) == 3 and {e.user_id for e in altas} == {admin.id}
    [resumen] = await _auditoria_de(limpiar_demo, "members.import_runs")
    assert resumen.action == "insert" and resumen.user_id == admin.id
    assert resumen.record_id is not None
    despues = resumen.after or {}
    assert despues["file_sha256"] == sha256_hex(archivo.read_bytes())
    esperado = {"rows": 3, "created": 3, "skipped_existing": 0, "rejected": 0}
    assert {k: despues[k] for k in esperado} == esperado
    assert (despues["consent_missing"], despues["notes_ignored"]) == (3, 0)
    assert "file_name" not in despues and "socios.xlsx" not in str(despues)
    assert "socios.xlsx" not in resultado.output  # tampoco se repite el nombre


# --dry-run ------------------------------------------------------------------------------------


async def test_dry_run_no_escribe_nada_ni_llama_a_create_y_da_el_mismo_reporte(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    archivo = _libro(import_dir, [fila_valida(1), fila_valida(2, sexo="z"), fila_valida(3)])
    antes = await _conteos_base(limpiar_demo)
    llamadas: list[object] = []
    create_real = members_service.create

    async def create_espiada(*args: Any, **kwargs: Any) -> Any:
        llamadas.append(args)
        return await create_real(*args, **kwargs)

    monkeypatch.setattr(members_service, "create", create_espiada)

    simulada = _importar(
        settings_importacion,
        monkeypatch,
        archivo,
        "--as",
        admin.email,
        "--dry-run",
        "--report",
        "simulado.csv",
    )

    assert simulada.exit_code == 0, simulada.output
    assert llamadas == []
    assert await _conteos_base(limpiar_demo) == antes  # members, audit_log y crypto_ops
    assert _conteos(simulada.output)["created"] == 2

    monkeypatch.setattr(members_service, "create", create_real)
    real = _importar(
        settings_importacion, monkeypatch, archivo, "--as", admin.email, "--report", "real.csv"
    )
    assert real.exit_code == 0, real.output
    assert (import_dir / "simulado.csv").read_bytes() == (import_dir / "real.csv").read_bytes()


# Confinamiento de rutas -----------------------------------------------------------------------


async def test_archivo_fuera_de_import_dir_sale_con_2(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    fuera = make_members_xlsx(tmp_path / "fuera" / "socios.xlsx", [fila_valida(1)])

    resultado = _importar(settings_importacion, monkeypatch, fuera, "--as", admin.email)

    assert resultado.exit_code == 2, resultado.output
    assert await _socios(limpiar_demo) == 0
    assert str(tmp_path) not in resultado.output  # sin rutas en el mensaje


async def test_un_enlace_simbolico_dentro_de_import_dir_sale_con_2(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    real = make_members_xlsx(tmp_path / "fuera" / "real.xlsx", [fila_valida(1)])
    enlace = import_dir / "enlace.xlsx"
    try:
        enlace.symlink_to(real)
    except OSError:
        pytest.skip("este sistema no permite crear enlaces simbólicos sin privilegios (sí en CI)")

    resultado = _importar(settings_importacion, monkeypatch, enlace, "--as", admin.email)

    assert resultado.exit_code == 2, resultado.output
    assert await _socios(limpiar_demo) == 0


async def test_archivo_inexistente_sale_con_2(
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    resultado = _importar(
        settings_importacion, monkeypatch, import_dir / "no-existe.xlsx", "--as", admin.email
    )

    assert resultado.exit_code == 2, resultado.output


@pytest.mark.parametrize("nombre", ["../fuera.csv", "sub/reporte.csv", "..", "a/../../b.csv"])
async def test_report_con_ruta_en_lugar_de_nombre_sale_con_2(
    nombre: str,
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    archivo = _libro(import_dir, [fila_valida(1)])

    resultado = _importar(
        settings_importacion, monkeypatch, archivo, "--as", admin.email, "--report", nombre
    )

    assert resultado.exit_code == 2, resultado.output
    assert not (import_dir.parent / "fuera.csv").exists()
    assert await _socios(limpiar_demo) == 0  # se valida antes de escribir socios


async def test_report_absoluto_hacia_otro_archivo_no_lo_toca(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    ajeno = tmp_path / "kek.bin"
    ajeno.write_bytes(b"SECRETO-DE-PRUEBA")
    archivo = _libro(import_dir, [fila_valida(1)])

    resultado = _importar(
        settings_importacion, monkeypatch, archivo, "--as", admin.email, "--report", str(ajeno)
    )

    assert resultado.exit_code == 2, resultado.output
    assert ajeno.read_bytes() == b"SECRETO-DE-PRUEBA"
    assert await _socios(limpiar_demo) == 0


async def test_report_hacia_un_enlace_no_toca_el_destino(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    ajeno = tmp_path / "destino.txt"
    ajeno.write_bytes(b"INTACTO")
    enlace = import_dir / "reporte.csv"
    try:
        enlace.symlink_to(ajeno)
    except OSError:
        pytest.skip("este sistema no permite crear enlaces simbólicos sin privilegios (sí en CI)")
    archivo = _libro(import_dir, [fila_valida(1)])

    resultado = _importar(
        settings_importacion, monkeypatch, archivo, "--as", admin.email, "--report", "reporte.csv"
    )

    assert resultado.exit_code == 2, resultado.output
    assert ajeno.read_bytes() == b"INTACTO"
    assert await _socios(limpiar_demo) == 0


async def test_report_existente_no_se_pisa(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    previo = import_dir / "reporte.csv"
    previo.write_bytes(b"CONTENIDO-PREVIO")
    archivo = _libro(import_dir, [fila_valida(1)])

    resultado = _importar(
        settings_importacion, monkeypatch, archivo, "--as", admin.email, "--report", "reporte.csv"
    )

    assert resultado.exit_code == 2, resultado.output
    assert previo.read_bytes() == b"CONTENIDO-PREVIO"
    assert await _socios(limpiar_demo) == 0


async def test_el_reporte_es_un_csv_con_bom_modo_600_y_documentos_enmascarados(
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    archivo = _libro(import_dir, [fila_valida(1), fila_valida(2), fila_valida(3)])

    resultado = _importar(
        settings_importacion, monkeypatch, archivo, "--as", admin.email, "--report", "r.csv"
    )

    assert resultado.exit_code == 0, resultado.output
    crudo = (import_dir / "r.csv").read_bytes()
    assert crudo.startswith(BOM)
    lineas = crudo.decode("utf-8-sig").splitlines()
    assert lineas[0] == "fila;documento;resultado;motivo"
    assert len(lineas) == 4
    assert all(re.fullmatch(r"\d+;•••\d{3};created;.*", ln) for ln in lineas[1:]), lineas
    if os.name == "posix":
        assert stat.S_IMODE((import_dir / "r.csv").stat().st_mode) == 0o600


# Límites y archivos peligrosos ----------------------------------------------------------------


async def test_extension_xlsm_sale_con_2(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    archivo = _libro(import_dir, [fila_valida(1)], nombre="socios.xlsm")

    resultado = _importar(settings_importacion, monkeypatch, archivo, "--as", admin.email)

    assert resultado.exit_code == 2, resultado.output
    assert await _socios(limpiar_demo) == 0


@pytest.mark.parametrize(
    "entrada",
    [
        "xl/vbaProject.bin",
        "xl/externalLinks/externalLink1.xml",
        "xl/embeddings/objeto.bin",
        "xl/activeX/activeX1.xml",
        "xl/macrosheets/sheet1.xml",
        "../fuera.xml",
    ],
)
async def test_entradas_del_zip_peligrosas_salen_con_2(
    entrada: str,
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    archivo = make_xlsx_with_entry(import_dir / "socios.xlsx", entrada)

    resultado = _importar(settings_importacion, monkeypatch, archivo, "--as", admin.email)

    assert resultado.exit_code == 2, resultado.output
    assert await _socios(limpiar_demo) == 0


async def test_shared_strings_de_11_mb_sale_con_2(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    once_mb = 11 * 1024 * 1024
    archivo = make_xlsx_with_entry(
        import_dir / "socios.xlsx", "xl/sharedStrings.xml", texto_incompresible(once_mb)
    )
    assert archivo.stat().st_size < MAX_FILE_BYTES, "debe aislar el tope de sharedStrings"

    resultado = _importar(settings_importacion, monkeypatch, archivo, "--as", admin.email)

    assert resultado.exit_code == 2, resultado.output
    assert await _socios(limpiar_demo) == 0


async def test_archivo_de_10_mb_mas_uno_sale_con_2(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    archivo = make_oversized_xlsx(import_dir / "socios.xlsx", MAX_FILE_BYTES + 1)
    assert archivo.stat().st_size > MAX_FILE_BYTES

    resultado = _importar(settings_importacion, monkeypatch, archivo, "--as", admin.email)

    assert resultado.exit_code == 2, resultado.output
    assert await _socios(limpiar_demo) == 0


async def test_bomba_de_zip_sale_con_2(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    archivo = make_zip_bomb(import_dir / "socios.xlsx")
    assert archivo.stat().st_size < 1024 * 1024  # pocos KB comprimida, 60 MB descomprimida

    resultado = _importar(settings_importacion, monkeypatch, archivo, "--as", admin.email)

    assert resultado.exit_code == 2, resultado.output
    assert await _socios(limpiar_demo) == 0


async def test_mas_de_5000_filas_salen_con_2_sin_escribir(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    assert MAX_ROWS == 5000
    filas = [fila_valida(n) for n in range(1, MAX_ROWS + 2)]
    archivo = _libro(import_dir, filas)

    resultado = _importar(settings_importacion, monkeypatch, archivo, "--as", admin.email)

    assert resultado.exit_code == 2, resultado.output
    assert await _socios(limpiar_demo) == 0


async def test_hoja_vacia_sale_con_2(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    archivo = make_members_xlsx(import_dir / "vacia.xlsx", [], header=None)

    resultado = _importar(settings_importacion, monkeypatch, archivo, "--as", admin.email)

    assert resultado.exit_code == 2, resultado.output
    assert await _socios(limpiar_demo) == 0


async def test_cabecera_distinta_a_q17_sale_con_2_sin_escribir(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    otra = [TEMPLATE_HEADER[0], TEMPLATE_HEADER[2], TEMPLATE_HEADER[1], *TEMPLATE_HEADER[3:]]
    archivo = make_members_xlsx(import_dir / "socios.xlsx", [fila_valida(1)], header=otra)

    resultado = _importar(settings_importacion, monkeypatch, archivo, "--as", admin.email)

    assert resultado.exit_code == 2, resultado.output
    assert await _socios(limpiar_demo) == 0


# XML malicioso --------------------------------------------------------------------------------


async def test_xxe_con_entidad_externa_se_rechaza_sin_leer_el_archivo(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secreto = tmp_path / "secreto.txt"
    secreto.write_text("MARCA-XXE-SECRETA-4471", encoding="utf-8")
    archivo = make_xlsx_xxe(import_dir / "socios.xlsx", secreto)

    with caplog.at_level("DEBUG"):
        resultado = _importar(settings_importacion, monkeypatch, archivo, "--as", admin.email)

    assert resultado.exit_code == 2, resultado.output
    assert "MARCA-XXE-SECRETA-4471" not in resultado.output + caplog.text
    assert await _socios(limpiar_demo) == 0


async def test_billion_laughs_se_rechaza(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    archivo = make_xlsx_billion_laughs(import_dir / "socios.xlsx")

    resultado = _importar(settings_importacion, monkeypatch, archivo, "--as", admin.email)

    assert resultado.exit_code == 2, resultado.output
    assert await _socios(limpiar_demo) == 0


def test_openpyxl_corre_con_defusedxml_y_sin_lxml() -> None:
    """S4B-D64: `openpyxl` protegido (`DEFUSEDXML`) y sin `lxml`, que no lo está igual."""
    assert openpyxl.xml.DEFUSEDXML is True  # type: ignore[attr-defined]
    assert not openpyxl.xml.LXML  # type: ignore[attr-defined]


# Actor y producción ---------------------------------------------------------------------------


async def test_sin_as_sale_con_2_sin_escribir(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archivo = _libro(import_dir, [fila_valida(1)])

    resultado = _importar(settings_importacion, monkeypatch, archivo)

    assert resultado.exit_code == 2, resultado.output
    assert "--as" in resultado.output
    assert await _socios(limpiar_demo) == 0


async def test_as_de_un_coach_o_inexistente_sale_con_2(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    argon2_rapido: None,
) -> None:
    async with limpiar_demo() as sesion:
        coach = await make_user(sesion, role="coach", password=CLAVE_PRUEBA)
    archivo = _libro(import_dir, [fila_valida(1)])

    for correo in (coach.email, "nadie@test.apex"):
        resultado = _importar(settings_importacion, monkeypatch, archivo, "--as", correo)
        assert resultado.exit_code == 2, resultado.output
        assert correo not in resultado.output
    assert await _socios(limpiar_demo) == 0


async def test_produccion_con_db_timeouts_off_sale_con_2(
    limpiar_demo: Fabrica,
    settings_importacion_produccion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    archivo = _libro(import_dir, [fila_valida(1)])

    resultado = _importar(
        settings_importacion_produccion,
        monkeypatch,
        archivo,
        "--as",
        admin.email,
        previo=("--db-timeouts", "off"),
        env="production",
    )

    assert resultado.exit_code == 2, resultado.output
    assert "--db-timeouts" in resultado.output
    assert await _socios(limpiar_demo) == 0


async def test_produccion_sin_as_sale_con_2(
    limpiar_demo: Fabrica,
    settings_importacion_produccion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archivo = _libro(import_dir, [fila_valida(1)])

    resultado = _importar(settings_importacion_produccion, monkeypatch, archivo, env="production")

    assert resultado.exit_code == 2, resultado.output
    assert "--as" in resultado.output
    assert await _socios(limpiar_demo) == 0


async def test_produccion_con_as_admin_importa(
    limpiar_demo: Fabrica,
    settings_importacion_produccion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    archivo = _libro(import_dir, [fila_valida(1)])

    resultado = _importar(
        settings_importacion_produccion,
        monkeypatch,
        archivo,
        "--as",
        admin.email,
        env="production",
    )

    assert resultado.exit_code == 0, resultado.output
    assert await _socios(limpiar_demo) == 1


# Sin datos personales en la salida ------------------------------------------------------------


async def test_ni_la_salida_ni_el_reporte_ni_el_log_repiten_documento_telefono_o_correo(
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    filas = [fila_valida(1), fila_valida(2), fila_valida(3, fecha_nacimiento="2001-02-30")]
    archivo = _libro(import_dir, filas)

    with caplog.at_level("DEBUG"):
        resultado = _importar(
            settings_importacion, monkeypatch, archivo, "--as", admin.email, "--report", "r.csv"
        )

    assert resultado.exit_code == 0, resultado.output
    reporte = (import_dir / "r.csv").read_bytes().decode("utf-8-sig")
    conjunto = resultado.output + reporte + caplog.text
    for fila in filas:
        documento, _, _, telefono, correo = (str(c) for c in fila[:5])
        contacto = str(fila[8])
        for dato in (documento, telefono, correo, contacto):
            assert dato not in conjunto, "se repite un dato personal completo"


# Fallo a mitad (revisión de seguridad de B1, MEDIUM) -------------------------------------------


async def test_un_fallo_a_mitad_deja_resumen_parcial_y_reporte_y_sale_con_1(
    limpiar_demo: Fabrica,
    settings_importacion: Settings,
    import_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    admin: Any,
) -> None:
    from app.imports import members_xlsx

    real = members_xlsx.create_member
    llamadas = {"n": 0}

    async def con_fallo(*args: Any, **kwargs: Any) -> bool:
        llamadas["n"] += 1
        if llamadas["n"] == 3:
            raise RuntimeError("fallo inyectado en la tercera alta")
        return await real(*args, **kwargs)

    monkeypatch.setattr(members_xlsx, "create_member", con_fallo)
    archivo = _libro(import_dir, [fila_valida(n) for n in range(1, 6)])

    resultado = _importar(
        settings_importacion, monkeypatch, archivo, "--as", admin.email, "--report", "r.csv"
    )

    assert resultado.exit_code == 1, resultado.output
    assert await _socios(limpiar_demo) == 2  # lo confirmado hasta ahí
    [resumen] = await _auditoria_de(limpiar_demo, "members.import_runs")
    despues = resumen.after or {}
    assert despues["partial"] is True and despues["created"] == 2
    assert despues["file_sha256"] == sha256_hex(archivo.read_bytes())
    reporte = (import_dir / "r.csv").read_bytes().decode("utf-8-sig").splitlines()
    assert len(reporte) == 3  # cabecera y las dos altas
    assert "fallo inyectado" not in resultado.output
