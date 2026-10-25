// S3-F3 (S3-D65, condición 8): búsqueda de socios para elegir uno desde otra feature (vender una
// membresía; en S3-F4, registrar un pago). La lista de /socios sigue en features/members.
// - useMembersSearch(q): GET /members?q=&limit=10&offset=0 con la clave ["members", "search", q].
//   Sin texto no pide nada. `q` viaja solo en la petición: el hook nunca toca la URL de la app
//   (S2-D41). Una búsqueda (puede ser un documento o un teléfono) no se queda en la caché al
//   dejar de usarse ni se repite al volver a la ventana (gastaría el límite members-search).
// - memberOptionSchema no es estricto (a diferencia de memberRowSchema, N-01): toma solo lo que
//   el selector muestra y descarta el resto, así un campo nuevo de MemberRowOut no lo rompe.
import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useOutletContext } from "react-router";
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

// S3-F7 (S3-D65): lo que la ficha del socio (features/members) pasa por el contexto de su <Outlet />
// a las pestañas de otras features (Membresías y Pagos). Ninguna feature importa de otra: el contrato
// vive aquí y la ficha lo cumple con su MemberDetailView. Sin ficha (la pestaña montada sola) es null.
export interface MemberTabMember {
  id: string;
  first_name: string;
  last_name: string;
  /** No nulo: el socio está dado de baja y su ficha es de solo lectura (N-20). */
  deleted_at: string | null;
}

export interface MemberTabContext {
  member: MemberTabMember;
}

/** El socio de la ficha que pinta esta pestaña, o null. */
export function useMemberTab(): MemberTabMember | null {
  const context = useOutletContext<MemberTabContext | undefined>();
  return context?.member ?? null;
}

// S3-F7 (pendiente de S3-F1): el nombre de un socio que llega solo con su id en la URL (la venta con
// `?socio=` y el panel de pagos con `?pago=nuevo&socio=`), para no decir "Socio elegido". GET
// /members/{id} con la clave ["member-name", id] (fuera del prefijo ["members"]: revisión S3-F7, LOW de
// seguridad; las escrituras que invalidan ["members"] no la releen ni descifran otra vez); toma solo
// el nombre, sin `.strict()`. Sin id no pide nada.
const memberNameSchema = z.object({ id: z.string().min(1), first_name: z.string(), last_name: z.string() });

export const MEMBER_NAME_STALE_MS = 5 * 60 * 1_000;

export function memberNameKey(memberId: string): readonly ["member-name", string] {
  return ["member-name", memberId];
}

export function useMemberName(memberId: string | null): UseQueryResult<string> {
  return useQuery({
    queryKey: memberNameKey(memberId ?? ""),
    // El nombre casi no cambia y cada lectura descifra las máscaras de la ficha (crypto_ops): no se
    // repite al volver a la ventana ni en los próximos 5 minutos.
    staleTime: MEMBER_NAME_STALE_MS,
    refetchOnWindowFocus: false,
    queryFn: async ({ signal }) => memberFullName(parseResponse(memberNameSchema, await api.get<unknown>(`/members/${encodeURIComponent(memberId ?? "")}`, { signal }))),
    enabled: memberId !== null,
  });
}
