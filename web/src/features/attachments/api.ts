// S6-F3 · US-150: datos de los adjuntos de un socio.
// - useMemberAttachments(memberId, { limit, offset }): GET /members/{id}/attachments con la clave
//   ["attachments", "member", memberId, params]; la página se valida con Zod. Subir o reemplazar un
//   adjunto (F4) invalida ["attachments"]. La descarga no pasa por la caché: la hace el botón con
//   api.blob dentro de una mutación sensible (shared/data/download).
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { api } from "../../core/api/client";
import type { Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";
import { attachmentsPageSchema, type AttachmentView } from "./schemas";

export interface MemberAttachmentsParams {
  limit: number;
  offset: number;
}

export function memberAttachmentsKey(memberId: string, params: MemberAttachmentsParams): readonly ["attachments", "member", string, MemberAttachmentsParams] {
  return ["attachments", "member", memberId, params];
}

export function useMemberAttachments(memberId: string | null, params: MemberAttachmentsParams): UseQueryResult<Page<AttachmentView>> {
  return useQuery({
    queryKey: memberAttachmentsKey(memberId ?? "", params),
    queryFn: async ({ signal }) =>
      parseResponse(attachmentsPageSchema, await api.get<unknown>(`/members/${encodeURIComponent(memberId ?? "")}/attachments`, { query: listParams({ ...params }), signal })),
    enabled: memberId !== null,
    placeholderData: (previous, previousQuery) => (previousQuery?.queryKey[2] === (memberId ?? "") ? previous : undefined),
  });
}
