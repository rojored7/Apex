// S2-F6 · US-069 y US-070 (front): datos de socios.
// - useMembers(params): GET /members con la clave ["members", params]; la página se valida con
//   Zod (una forma inesperada es `invalid_response`). La petición usa el `signal` de TanStack
//   Query: al cambiar la búsqueda, la anterior se cancela. `q` viaja solo en la petición (nunca
//   en la URL de la app, S2-D41) y mientras llega la página nueva se conserva la anterior.
// - useCreateMember(): POST /members → 201 MemberDetailOut (enmascarado). useSensitiveMutation
//   (Fase 4 M6): el cuerpo del alta (documento, teléfono, correo) no se queda en la caché de mutaciones. Al salir bien
//   invalida ["members"]. Los errores llegan como ApiError (409 con `existingId`, 422 con
//   `field`, 429 con `retryAfterS`) y los traduce memberErrors.ts.
// - S3-F2 (US-071, US-072): los filtros `membership_status` y `plan_id` (D22);
//   useMembersInfinite(params) para "Cargar más" en el celular (clave
//   ["members", "infinite", params], `offset` por página, hasta MEMBERS_MAX_PAGES páginas, M-9) y
//   useMembersTotal() para el chip "Todos" (clave ["members", "total"]). Las tres claves cuelgan
//   de ["members"], que invalida el alta.
// - S3-F1 (US-073 a US-076): useMember, useRevealField, useUpdateMember, useDeactivateMember y
//   useReactivateMember; ver su bloque al final.
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
import { useSensitiveMutation } from "../../core/api/useSensitiveMutation";
import { memberFullName, memberNameKey } from "../../shared/data/members";
import { isMemberId } from "./memberLinks";
import {
  DATA_CONSENT_MISSING,
  memberDetailSchema,
  memberDetailViewSchema,
  membersPageSchema,
  revealOutSchema,
  type MemberCreateBody,
  type MemberDetailView,
  type MemberPatchBody,
  type MemberRowView,
  type MembershipFilterStatus,
  type RevealField,
  type RevealOutView,
} from "./schemas";

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

/**
 * Fase 4 del Sprint 3 (L7; ajuste de la revisión final): las tarjetas cargadas no se guardan en la
 * caché al dejar de mostrarse (`gcTime: 0`). Al volver a /socios o a unos filtros ya vistos la lista
 * empieza en la primera página con una sola petición, en vez de releer en serie todas las que se
 * habían cargado (hasta 20). Mientras la pantalla está montada no cambia nada.
 */
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
    // L7 (y S2-D41 con `q`): nada de la lista infinita queda en la caché al dejar de usarse.
    gcTime: 0,
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
  return useSensitiveMutation<CreatedMember, Error, MemberCreateBody>({
    mutationFn: async (body) => {
      const { id, first_name, last_name, warnings } = parseResponse(memberDetailSchema, await api.post<unknown>("/members", { body }));
      return { id, firstName: first_name, lastName: last_name, consentMissing: warnings.includes(DATA_CONSENT_MISSING) };
    },
    onSuccess: () => {
      // Revisión S3-F2 (M3): las tarjetas del celular vuelven a la primera página en vez de releer
      // en serie todas las que se habían cargado.
      void queryClient.resetQueries({ queryKey: MEMBERS_INFINITE_KEY });
      // Sin esperar la relectura: el alta ya terminó y la lista se pide al volver a /socios.
      void queryClient.invalidateQueries({ queryKey: MEMBERS_QUERY_KEY });
    },
  });
}

// ---------------------------------------------------------------------------------------------
// S3-F1 · US-073 a US-076: la ficha (GET), revelar (POST reveal), editar (PATCH), dar de baja
// (DELETE) y reactivar (POST reactivate).
// - useMember(id): clave ["members", "detail", id] con el `gcTime` normal: la ficha solo trae
//   máscaras (N-01). Cuelga de ["members"]: editar, dar de baja y reactivar la releen.
// - useRevealField(id): useSensitiveMutation (Fase 4 M6), sin setQueryData ni invalidaciones. Quien
//   la usa (MemberSensitiveField) además llama a `reset()` en cuanto tiene el valor (S3-D52, M-9): el
//   claro no queda en `mutation.data` ni en la caché de mutaciones; solo en el estado de MaskedValue.
// - useUpdateMember(id): el cuerpo lleva datos sensibles nuevos: useSensitiveMutation. Al salir bien
//   deja la ficha enmascarada que responde el api, relee ["members"] (lista, tarjetas y total) y
//   pone el nombre nuevo en ["member-name", id] (Fase 4 L3: la venta y el panel de pagos lo leen).
// - useDeactivateMember() y useReactivateMember(): solo llevan el id; al salir bien releen
//   ["members"] (la ficha pasa a solo lectura o vuelve a ser editable, y la lista cambia).

export function memberDetailKey(id: string): readonly ["members", "detail", string] {
  return ["members", "detail", id];
}

const memberPath = (id: string): string => `/members/${encodeURIComponent(id)}`;

export function useMember(id: string): UseQueryResult<MemberDetailView> {
  return useQuery({
    queryKey: memberDetailKey(id),
    queryFn: async ({ signal }) => parseResponse(memberDetailViewSchema, await api.get<unknown>(memberPath(id), { signal })),
    // Revisión S3-F1 (LOW-3): un `:id` sin forma de UUID no se pide (la pantalla da "no encontrado").
    enabled: isMemberId(id),
  });
}

export function useRevealField(id: string): UseMutationResult<RevealOutView, Error, RevealField> {
  return useSensitiveMutation<RevealOutView, Error, RevealField>({
    mutationFn: async (field) => parseResponse(revealOutSchema, await api.post<unknown>(`${memberPath(id)}/reveal`, { body: { field } })),
  });
}

export interface UpdateMember {
  /** Guarda el cuerpo; rechaza con el ApiError del api. */
  update: (body: MemberPatchBody) => Promise<MemberDetailView>;
  isPending: boolean;
}

export function useUpdateMember(id: string): UpdateMember {
  const queryClient = useQueryClient();
  const { mutateAsync, isPending } = useSensitiveMutation<MemberDetailView, Error, MemberPatchBody>({
    mutationFn: async (body) => parseResponse(memberDetailViewSchema, await api.patch<unknown>(memberPath(id), { body })),
    onSuccess: (member) => {
      queryClient.setQueryData(memberDetailKey(id), member);
      queryClient.setQueryData(memberNameKey(id), memberFullName(member));
      void queryClient.invalidateQueries({ queryKey: MEMBERS_QUERY_KEY });
    },
  });
  return { update: mutateAsync, isPending };
}

export function useDeactivateMember(): UseMutationResult<null, Error, string> {
  const queryClient = useQueryClient();
  return useMutation<null, Error, string>({
    mutationFn: async (memberId) => {
      await api.delete<unknown>(memberPath(memberId));
      return null;
    },
    // Revisión S3-F1 (LOW-7): se espera la relectura; la ficha ya es de solo lectura cuando avisa.
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: MEMBERS_QUERY_KEY });
    },
  });
}

export function useReactivateMember(): UseMutationResult<MemberDetailView, Error, string> {
  const queryClient = useQueryClient();
  return useMutation<MemberDetailView, Error, string>({
    mutationFn: async (memberId) => parseResponse(memberDetailViewSchema, await api.post<unknown>(`${memberPath(memberId)}/reactivate`)),
    onSuccess: (member) => {
      queryClient.setQueryData(memberDetailKey(member.id), member);
      void queryClient.invalidateQueries({ queryKey: MEMBERS_QUERY_KEY });
    },
  });
}
