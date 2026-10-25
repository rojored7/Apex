// S2-F6 · US-069 y US-070 (front): datos de socios.
// - useMembers(params): GET /members con la clave ["members", params]; la página se valida con
//   Zod (una forma inesperada es `invalid_response`). La petición usa el `signal` de TanStack
//   Query: al cambiar la búsqueda, la anterior se cancela. `q` viaja solo en la petición (nunca
//   en la URL de la app, S2-D41) y mientras llega la página nueva se conserva la anterior.
// - useCreateMember(): POST /members → 201 MemberDetailOut (enmascarado). gcTime 0: el cuerpo
//   del alta (documento, teléfono, correo) no se queda en la caché de mutaciones. Al salir bien
//   invalida ["members"]. Los errores llegan como ApiError (409 con `existingId`, 422 con
//   `field`, 429 con `retryAfterS`) y los traduce memberErrors.ts.
// - S3-F2 (US-071, US-072): los filtros `membership_status` y `plan_id` (D22);
//   useMembersInfinite(params) para "Cargar más" en el celular (clave
//   ["members", "infinite", params], `offset` por página, hasta MEMBERS_MAX_PAGES páginas, M-9) y
//   useMembersTotal() para el chip "Todos" (clave ["members", "total"]). Las tres claves cuelgan
//   de ["members"], que invalida el alta.
import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type InfiniteData,
  type UseInfiniteQueryResult,
  type UseMutationResult,
  type UseQueryResult,
} from "@tanstack/react-query";
import { api } from "../../core/api/client";
import type { Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";
import { DATA_CONSENT_MISSING, memberDetailSchema, membersPageSchema, type MemberCreateBody, type MemberRowView, type MembershipFilterStatus } from "./schemas";

export interface MembersParams {
  limit: number;
  offset: number;
  q?: string;
  status?: string;
  sort?: string;
  /** S3-F2 (D22): el estado de la membresía que decide el del socio. */
  membership_status?: MembershipFilterStatus;
  /** S3-F2 (D22): el plan de esa membresía (UUID). */
  plan_id?: string;
}

/** "Cargar más" (US-072): los mismos filtros sin `offset`; cada página lo pone. */
export type MembersInfiniteParams = Omit<MembersParams, "offset">;

/** M-9 punto 4 (S3-D52): "Cargar más" no acumula sin límite en la memoria del celular. */
export const MEMBERS_MAX_PAGES = 20;

export function membersInfiniteKey(params: MembersInfiniteParams): readonly ["members", "infinite", MembersInfiniteParams] {
  return ["members", "infinite", params];
}

export const MEMBERS_TOTAL_KEY = ["members", "total"] as const;
export const MEMBERS_INFINITE_KEY = ["members", "infinite"] as const;

/** El offset de la página siguiente, o undefined si ya se trajo todo. */
export function nextMembersOffset(last: Page<unknown>): number | undefined {
  const next = last.offset + last.limit;
  return next < last.total ? next : undefined;
}

async function fetchMembersPage(query: MembersParams, signal: AbortSignal): Promise<Page<MemberRowView>> {
  return parseResponse(membersPageSchema, await api.get<unknown>("/members", { query: listParams({ ...query }), signal }));
}

export function useMembersInfinite(params: MembersInfiniteParams): UseInfiniteQueryResult<InfiniteData<Page<MemberRowView>, number>> {
  return useInfiniteQuery({
    queryKey: membersInfiniteKey(params),
    queryFn: ({ pageParam, signal }) => fetchMembersPage({ ...params, offset: pageParam }, signal),
    initialPageParam: 0,
    getNextPageParam: nextMembersOffset,
    // M-9 (S3-D52): la pantalla deja de ofrecer "Cargar más" en la página 20; este tope es la red.
    maxPages: MEMBERS_MAX_PAGES,
    // Revisión S3-F2 (M3): releer al volver a la ventana pediría en serie todas las páginas
    // cargadas (hasta 20) y gastaría el límite de búsquedas; la lista se relee al cambiar filtros.
    refetchOnWindowFocus: false,
    ...(params.q ? { gcTime: 0 } : {}),
  });
}

/**
 * El total de socios vivos (GET /members sin filtros, `limit=1`): el conteo del chip "Todos" y la
 * base de "Sin membresía" (D37). Cuelga de ["members"]: un alta lo relee.
 */
export function useMembersTotal(): UseQueryResult<number> {
  return useQuery({
    queryKey: MEMBERS_TOTAL_KEY,
    queryFn: async ({ signal }) => (await fetchMembersPage({ limit: 1, offset: 0 }, signal)).total,
  });
}

export interface CreatedMember {
  id: string;
  firstName: string;
  lastName: string;
  /** El alta salió sin la autorización de tratamiento de datos (`data_consent_missing`). */
  consentMissing: boolean;
}

export const MEMBERS_QUERY_KEY = ["members"] as const;

export function membersQueryKey(params: MembersParams): readonly ["members", MembersParams] {
  return ["members", params];
}

export function useMembers(params: MembersParams): UseQueryResult<Page<MemberRowView>> {
  return useQuery({
    queryKey: membersQueryKey(params),
    queryFn: ({ signal }) => fetchMembersPage(params, signal),
    placeholderData: keepPreviousData,
    // S2-D41: una búsqueda (documento, teléfono, correo) no se queda en la caché al dejar de
    // usarse ni se repite al volver a la ventana (gastaría el límite members-search).
    ...(params.q ? { gcTime: 0, refetchOnWindowFocus: false } : {}),
  });
}

export function useCreateMember(): UseMutationResult<CreatedMember, Error, MemberCreateBody> {
  const queryClient = useQueryClient();
  return useMutation<CreatedMember, Error, MemberCreateBody>({
    mutationFn: async (body) => {
      const { id, first_name, last_name, warnings } = parseResponse(memberDetailSchema, await api.post<unknown>("/members", { body }));
      return { id, firstName: first_name, lastName: last_name, consentMissing: warnings.includes(DATA_CONSENT_MISSING) };
    },
    gcTime: 0,
    onSuccess: () => {
      // Revisión S3-F2 (M3): las tarjetas del celular vuelven a la primera página en vez de releer
      // en serie todas las que se habían cargado.
      void queryClient.resetQueries({ queryKey: MEMBERS_INFINITE_KEY });
      // Sin esperar la relectura: el alta ya terminó y la lista se pide al volver a /socios.
      void queryClient.invalidateQueries({ queryKey: MEMBERS_QUERY_KEY });
    },
  });
}
