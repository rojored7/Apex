// S2-F6 · US-069 y US-070 (front): datos de socios.
// - useMembers(params): GET /members con la clave ["members", params]; la página se valida con
//   Zod (una forma inesperada es `invalid_response`). La petición usa el `signal` de TanStack
//   Query: al cambiar la búsqueda, la anterior se cancela. `q` viaja solo en la petición (nunca
//   en la URL de la app, S2-D41) y mientras llega la página nueva se conserva la anterior.
// - useCreateMember(): POST /members → 201 MemberDetailOut (enmascarado). gcTime 0: el cuerpo
//   del alta (documento, teléfono, correo) no se queda en la caché de mutaciones. Al salir bien
//   invalida ["members"]. Los errores llegan como ApiError (409 con `existingId`, 422 con
//   `field`, 429 con `retryAfterS`) y los traduce memberErrors.ts.
import { keepPreviousData, useMutation, useQuery, useQueryClient, type UseMutationResult, type UseQueryResult } from "@tanstack/react-query";
import { api } from "../../core/api/client";
import type { Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";
import { DATA_CONSENT_MISSING, memberDetailSchema, membersPageSchema, type MemberCreateBody, type MemberRowView } from "./schemas";

export interface MembersParams {
  limit: number;
  offset: number;
  q?: string;
  status?: string;
  sort?: string;
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
    queryFn: async ({ signal }) => parseResponse(membersPageSchema, await api.get<unknown>("/members", { query: listParams({ ...params }), signal })),
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
      // Sin esperar la relectura: el alta ya terminó y la lista se pide al volver a /socios.
      void queryClient.invalidateQueries({ queryKey: MEMBERS_QUERY_KEY });
    },
  });
}
