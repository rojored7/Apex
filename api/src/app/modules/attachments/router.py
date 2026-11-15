"""Router de adjuntos (S6-C4, US-150; S6-D24, S6-D37, S6-D45, S6-D57, S6-D59, M-3, M-5, M-6,
ADR-007):
`GET /attachments/{id}`.

Roles `admin` y `coach`; el service decide el 403 de `consent` y `other` para el coach (después de
leer la fila y antes de cobrar la cubeta y de descifrar). La cubeta se elige con la fila: sensibles
`attachments-download` y `-hour`, foto `attachments-photo`. Con la marca de quiosco (S7-D41) solo
se sirve la foto: otro tipo da 403 `kiosk_mode`. El sensible se sirve en memoria
(`file_download`, con su fila `download` ya confirmada); la foto por streaming (`file_stream`), sin
fila por vista. El nombre de descarga nunca es el del objeto. Errores: 404 `attachment_not_found`,
503 `busy` (cupos llenos) y 503 `crypto_unavailable` (custodio sellado).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response

from app.core.db import SessionDep
from app.core.errors import ForbiddenError, responses_for
from app.core.http import file_download, file_stream, no_store
from app.core.ratelimit import enforce_user_limit
from app.core.security import KIOSK_MODE_MESSAGE, StaffDep
from app.modules.attachments import rules, service
from app.modules.attachments.exceptions import StorageUnavailable

router = APIRouter(
    tags=["attachments"], dependencies=[Depends(no_store)], responses=responses_for(401, 403)
)


@router.get(
    "/attachments/{attachment_id}",
    response_class=Response,
    responses=responses_for(404, 422, 429)
    | {200: {"content": {"application/octet-stream": {}}, "description": "Archivo adjunto"}},
)
async def download_attachment(
    request: Request, attachment_id: UUID, principal: StaffDep, session: SessionDep
) -> Response:
    meta = await service.authorize(session, attachment_id, role=principal.role)
    if principal.kiosk and meta.kind != "photo":  # S7-D41: el quiosco solo sirve la foto
        raise ForbiddenError("kiosk_mode", KIOSK_MODE_MESSAGE)
    if meta.sensitive:
        await enforce_user_limit(request, "attachments-download", principal.user_id)
        await enforce_user_limit(request, "attachments-download-hour", principal.user_id)
    else:
        await enforce_user_limit(request, "attachments-photo", principal.user_id)
    cuerpo = await service.open_attachment(
        session, attachment_id, by=principal.user_id, audit=meta.sensitive
    )
    nombre = rules.download_filename(meta.id, meta.mime)
    if cuerpo.data is not None:
        return file_download(cuerpo.data, filename=nombre, media_type=meta.mime)
    if cuerpo.stream is None:  # el service entrega `data` o `stream`; nunca ninguno
        raise StorageUnavailable
    return file_stream(cuerpo.stream, filename=nombre, media_type=meta.mime)
