// S3-F3 (S3-D65, condición 8): búsqueda de socios para elegir uno desde otra feature (vender una
// membresía; en S3-F4, registrar un pago). La lista de /socios sigue en features/members.
// - useMembersSearch(q): GET /members?q=&limit=10&offset=0 con la clave ["members", "search", q].
//   Sin texto no pide nada. `q` viaja solo en la petición: el hook nunca toca la URL de la app
//   (S2-D41). Una búsqueda (puede ser un documento o un teléfono) no se queda en la caché al
//   dejar de usarse ni se repite al volver a la ventana (gastaría el límite members-search).
// - memberOptionSchema no es estricto (a diferencia de memberRowSchema, N-01): toma solo lo que
//   el selector muestra y descarta el resto, así un campo nuevo de MemberRowOut no lo rompe.
import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../../core/api/client";
import { pageSchema, type Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";

export const MEMBERS_SEARCH_LIMIT = 10;

export const memberOptionSchema = z.object({
  id: z.string().min(1),
  first_name: z.string(),
  last_name: z.string(),
  status: z.enum(["active", "inactive"]),
  deleted_at: z.string().nullable(),
  membership_status: z.string().nullish(),
  plan_name: z.string().nullish(),
});
export type MemberOption = z.infer<typeof memberOptionSchema>;

export const membersSearchSchema = pageSchema(memberOptionSchema);

export function membersSearchKey(q: string): readonly ["members", "search", string] {
  return ["members", "search", q];
}

/** "Laura Gómez". */
export function memberFullName(member: Pick<MemberOption, "first_name" | "last_name">): string {
  return `${member.first_name} ${member.last_name}`.trim();
}

export function useMembersSearch(q: string): UseQueryResult<Page<MemberOption>> {
  const text = q.trim();
  return useQuery({
    queryKey: membersSearchKey(text),
    queryFn: async ({ signal }) =>
      parseResponse(membersSearchSchema, await api.get<unknown>("/members", { query: listParams({ limit: MEMBERS_SEARCH_LIMIT, offset: 0, q: text }), signal })),
    enabled: text !== "",
    placeholderData: keepPreviousData,
    gcTime: 0,
    refetchOnWindowFocus: false,
  });
}
