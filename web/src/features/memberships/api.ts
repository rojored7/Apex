// S3-F3 · US-084, US-085 y US-088 (front): vender (con primer pago opcional) y renovar.
// - useSellMembership(memberId): POST /members/{id}/memberships → 201 SellMembershipOut. Vender y
//   renovar usan este mismo endpoint (regla 9 de CLAUDE.md, D5). El cuerpo lleva un monto y quizá
//   una referencia: pasa por useSensitiveMutation (S3-D52, M-9; Fase 4 M6), así la caché de
//   mutaciones no conserva `variables` después de responder. Al salir bien invalida lo mismo que un
//   pago (INVALIDATE_AFTER_PAYMENT, Fase 4 M1: también el resumen del mes de /pagos). Sin reintentos: una escritura
//   nunca se repite sola (el cliente tampoco reintenta un 503 `busy` en escrituras).
// - useRenewalPreview(memberId, planId): GET /members/{id}/memberships/renewal-preview?plan_id=
//   con la clave ["renewal-preview", memberId, planId] (Fase 4 L5: fuera de ["memberships"], así
//   una venta o un pago no la piden de nuevo mientras la pantalla muestra "Venta registrada");
//   `staleTime: 0`: cada vez que se abre la venta se calcula de nuevo. Solo con socio y plan. Al
//   cambiar de plan se pide de nuevo.
import { keepPreviousData, useQuery, useQueryClient, type QueryClient, type UseQueryResult } from "@tanstack/react-query";
import { api } from "../../core/api/client";
import { isApiError } from "../../core/api/errors";
import type { Page } from "../../core/api/page";
import { listParams, type ListQueryParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";
import { HTTP_CONFLICT, HTTP_NOT_FOUND } from "../../core/api/status";
import type { operations } from "../../core/api/types";
import { useSensitiveMutation } from "../../core/api/useSensitiveMutation";
import { membershipsPageSchema, type MembershipRowView } from "../../shared/data/memberships";
import { INVALIDATE_AFTER_PAYMENT } from "../../shared/data/payments";
import { membershipOutSchema, renewalPreviewSchema, sellMembershipOutSchema, type MembershipOutView, type RenewalPreviewView, type SellMembershipBody, type SellMembershipOutView } from "./schemas";

/** Lo que una venta deja viejo (S3-D53; Fase 4 M1: lo mismo que un pago, con el resumen del mes). */
export const SELL_INVALIDATES = INVALIDATE_AFTER_PAYMENT;

export interface SellMembership {
  /** Vende con este cuerpo; rechaza con el ApiError del api. */
  sell: (body: SellMembershipBody) => Promise<SellMembershipOutView>;
  isPending: boolean;
}

const membershipsOf = (memberId: string): string => `/members/${encodeURIComponent(memberId)}/memberships`;

export function renewalPreviewKey(memberId: string | null, planId: string | null): readonly ["renewal-preview", string, string] {
  return ["renewal-preview", memberId ?? "", planId ?? ""];
}

export function useSellMembership(memberId: string | null): SellMembership {
  const queryClient = useQueryClient();
  const { mutateAsync, isPending } = useSensitiveMutation<SellMembershipOutView, Error, SellMembershipBody>({
    mutationFn: async (body) => {
      if (memberId === null) throw new Error("useSellMembership: falta el socio");
      return parseResponse(sellMembershipOutSchema, await api.post<unknown>(membershipsOf(memberId), { body }));
    },
    onSuccess: () => {
      // Sin esperar las relecturas: la venta ya terminó.
      for (const queryKey of SELL_INVALIDATES) void queryClient.invalidateQueries({ queryKey });
    },
  });
  return { sell: mutateAsync, isPending };
}

export function useRenewalPreview(memberId: string | null, planId: string | null): UseQueryResult<RenewalPreviewView> {
  return useQuery({
    queryKey: renewalPreviewKey(memberId, planId),
    staleTime: 0,
    // Revisión final (LOW 3): bajo "Venta registrada" la consulta sigue montada; volver a la ventana no
    // la repite (respondería 409 y dejaría la venta bloqueada). Se calcula al abrir la venta.
    refetchOnWindowFocus: false,
    queryFn: async ({ signal }) =>
      parseResponse(renewalPreviewSchema, await api.get<unknown>(`${membershipsOf(memberId ?? "")}/renewal-preview`, { query: { plan_id: planId ?? "" }, signal })),
    enabled: memberId !== null && planId !== null,
  });
}



// S3-F5 · US-089, US-090, US-091 y US-092 (front): la lista de membresías y sus escrituras.
// - useMemberships(params): GET /memberships con la clave ["memberships", "list", params]; los
//   filtros son parte de la clave. `status` viaja separado por comas (D18). Filas estrictas
//   (MembershipRow, D35). Mientras llega la página nueva se conserva la anterior; con `q` no queda
//   en la caché ni se repite al volver a la ventana (S2-D41: gastaría el cupo de búsqueda).
// - useMembership(id): GET /memberships/{id} (MembershipOut con el estado efectivo, B7).
// - useFreezeMembership y useCancelMembership: POST /memberships/{id}/freeze { frozen_from,
//   frozen_to } (admin y coach) y POST /memberships/{id}/cancel { reason } (solo admin) → 200
//   MembershipOut. Llevan fechas o un motivo: pasan por useSensitiveMutation (S3-D52); el modal
//   también llama a `reset()` al cerrar. Al salir bien invalidan lo que cambia el estado de una
//   membresía: la lista (y el panel de pagos, bajo ["memberships"]), el resumen y los socios (estado
//   en su lista). Un 409 o un 404 dicen que lo que se ve quedó viejo: se releen la lista y el
//   resumen. Sin reintentos: una escritura nunca se repite sola.
//   Desviación del blueprint F5: no invalidan ["payments"]; congelar y anular no tocan pagos (D3).
/** Fase 4 L1: derivado del contrato. `status` son estados separados por comas ("active,expiring"). */
export type MembershipsParams = ListQueryParams<MembershipsQuery, "q" | "status" | "plan_id" | "ends_from" | "ends_to">;
type MembershipsQuery = NonNullable<operations["list_memberships_api_v1_memberships_get"]["parameters"]["query"]>;

/** Lo que deja viejo congelar o anular una membresía. */
export const MEMBERSHIP_WRITE_INVALIDATES = [["memberships"], ["memberships-summary"], ["members"]] as const;
/** Lo que se relee cuando el api dice que la membresía cambió (409) o ya no existe (404). */
const STALE_ON_CONFLICT = [["memberships"], ["memberships-summary"]] as const;

export function membershipsQueryKey(params: MembershipsParams): readonly ["memberships", "list", MembershipsParams] {
  return ["memberships", "list", params];
}

export function membershipQueryKey(id: string): readonly ["memberships", "detail", string] {
  return ["memberships", "detail", id];
}

const membershipOf = (id: string): string => `/memberships/${encodeURIComponent(id)}`;

export function useMemberships(params: MembershipsParams): UseQueryResult<Page<MembershipRowView>> {
  return useQuery({
    queryKey: membershipsQueryKey(params),
    queryFn: async ({ signal }) => parseResponse(membershipsPageSchema, await api.get<unknown>("/memberships", { query: listParams({ ...params }), signal })),
    placeholderData: keepPreviousData,
    ...(params.q ? { gcTime: 0, refetchOnWindowFocus: false } : {}),
  });
}

export function useMembership(id: string | null): UseQueryResult<MembershipOutView> {
  return useQuery({
    queryKey: membershipQueryKey(id ?? ""),
    queryFn: async ({ signal }) => parseResponse(membershipOutSchema, await api.get<unknown>(membershipOf(id ?? ""), { signal })),
    enabled: id !== null,
  });
}

export interface FreezeInput {
  id: string;
  frozen_from: string;
  frozen_to: string;
}

export interface FreezeMembership {
  /** Congela; rechaza con el ApiError del api. */
  freeze: (input: FreezeInput) => Promise<MembershipOutView>;
  isPending: boolean;
  /** Olvida la última mutación (y sus variables) en la caché. */
  reset: () => void;
}

export interface CancelInput {
  id: string;
  /** Ya recortado (cancelMembershipSchema). */
  reason: string;
}

export interface CancelMembership {
  cancel: (input: CancelInput) => Promise<MembershipOutView>;
  isPending: boolean;
}

/** Al salir bien: lo que deja viejo congelar o anular. */
function invalidateAfterWrite(queryClient: QueryClient): void {
  for (const queryKey of MEMBERSHIP_WRITE_INVALIDATES) void queryClient.invalidateQueries({ queryKey });
}

/** Un 409 o un 404: lo que se ve quedó viejo; se releen la lista y el resumen. */
function invalidateIfStale(queryClient: QueryClient, error: Error): void {
  if (!isApiError(error) || (error.status !== HTTP_CONFLICT && error.status !== HTTP_NOT_FOUND)) return;
  for (const queryKey of STALE_ON_CONFLICT) void queryClient.invalidateQueries({ queryKey });
}

export function useFreezeMembership(): FreezeMembership {
  const queryClient = useQueryClient();
  const { reset, mutateAsync, isPending } = useSensitiveMutation<MembershipOutView, Error, FreezeInput>({
    mutationFn: async ({ id, frozen_from, frozen_to }) =>
      parseResponse(membershipOutSchema, await api.post<unknown>(`${membershipOf(id)}/freeze`, { body: { frozen_from, frozen_to } })),
    onSuccess: () => {
      invalidateAfterWrite(queryClient);
    },
    onError: (error) => {
      invalidateIfStale(queryClient, error);
    },
  });
  return { freeze: mutateAsync, isPending, reset };
}

export function useCancelMembership(): CancelMembership {
  const queryClient = useQueryClient();
  const { mutateAsync, isPending } = useSensitiveMutation<MembershipOutView, Error, CancelInput>({
    mutationFn: async ({ id, reason }) => parseResponse(membershipOutSchema, await api.post<unknown>(`${membershipOf(id)}/cancel`, { body: { reason } })),
    onSuccess: () => {
      invalidateAfterWrite(queryClient);
    },
    onError: (error) => {
      invalidateIfStale(queryClient, error);
    },
  });
  return { cancel: mutateAsync, isPending };
}
