"""Los lotes de la rotación (S6-R1, S6-D111, S6-D116).

`rotate_job.BATCH_FILES` es la constante propia de `core/crypto` (el núcleo no importa módulos) y
debe valer lo mismo que `attachments.reencrypt.BATCH_SIZE` (10: los candados de fila del lote se
sostienen durante la E/S de cada objeto, S6-D111): si una cambia sin la otra, el tope efectivo
`min(batch_size, BATCH_SIZE)` deja de ser el que se lee en el código. `BATCH_ROWS` no cambia (500).
"""

from __future__ import annotations

from app.core.crypto import rotate_job, service
from app.modules.attachments import reencrypt


def test_batch_files_es_igual_al_batch_size_del_reencryptor_de_adjuntos() -> None:
    assert rotate_job.BATCH_FILES == reencrypt.BATCH_SIZE == 10


def test_batch_rows_es_el_lote_de_filas_del_servicio_y_vale_500() -> None:
    assert rotate_job.BATCH_ROWS == service.BATCH_SIZE == 500


def test_las_constantes_de_la_rotacion_son_las_del_plan() -> None:
    assert rotate_job.ROTATION_SLOTS == 1
    assert rotate_job.ROTATION_MAX_S == 3600
