"""`0041_results_session_index` (S8-V7b, M-2 de la revisión final): índice por sesión.

`ix_wod_results_session_current ON results.wod_results (session_id, member_id) WHERE is_current
AND session_id IS NOT NULL`: lo usan `session_has_current_results`,
`sessions_with_current_results` y `member_has_current_result_in_session`, con la sesión o la
asistencia ya bloqueadas. Es migración NUEVA: `0040` ya está aplicada en desarrollo (S8-D47 dejó
de valer).
"""

from __future__ import annotations

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from tests.migrations._apoyo_notificaciones import consultar

REVISION = "0041_results_session_index"
PADRE = "0040_results_void"
INDICE = "ix_wod_results_session_current"
SQL_INDICE = (
    "SELECT indexdef FROM pg_indexes WHERE schemaname = 'results' "
    "AND tablename = 'wod_results' AND indexname = $1"
)


def test_cuelga_de_0040_y_tiene_id_corto(alembic_config: Config) -> None:
    assert len(REVISION) <= 32
    revision = ScriptDirectory.from_config(alembic_config).get_revision(REVISION)
    assert revision is not None and revision.down_revision == PADRE


def test_indice_parcial_por_sesion(migrated_database: str) -> None:
    (ix,) = consultar(migrated_database, SQL_INDICE, INDICE)
    definicion = ix["indexdef"]
    assert "(session_id, member_id)" in definicion
    assert "is_current" in definicion and "session_id IS NOT NULL" in definicion


def test_downgrade_y_upgrade_son_reversibles(
    alembic_config: Config, migrated_database: str
) -> None:
    try:
        command.downgrade(alembic_config, PADRE)
        assert consultar(migrated_database, SQL_INDICE, INDICE) == []
    finally:
        command.upgrade(alembic_config, "head")
    assert len(consultar(migrated_database, SQL_INDICE, INDICE)) == 1
