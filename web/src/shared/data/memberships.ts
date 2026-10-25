// S3-F4 (E10, S3-D65, S3-D66, condición 8): datos de membresías que comparten varias features. El
// panel de pagos (features/payments) no importa features/memberships: lo común vive aquí.
// - useMembershipSummary(): GET /memberships/summary → cinco enteros (B7, S3-D53) con la clave
//   ["memberships-summary"], la que invalidan vender, registrar y anular. Lo usan la lista de
//   membresías (S3-F5) y los filtros de socios (S3-F2).
// - useMemberOpenMemberships(memberId): las membresías de un socio que reciben pagos, con
//   GET /memberships?member_id=&status=active,expiring,frozen,pending_payment (S3-D66: no espera a
//   GET /members/{id}/memberships de B11). Trae `paid_cop` para calcular el saldo. Clave bajo
//   ["memberships"], así cualquier escritura de membresías o pagos la relee.
// - useMembershipOption(id): GET /memberships/{id} (MembershipOut con el estado efectivo) reducido a
//   los campos de la fila: el panel abierto con `?pago=<membresía>` sabe de quién es y cuánto falta.
// - Esquemas estrictos donde el contrato es la fila (MembershipRow, D35); el detalle se reduce a la
//   fila descartando lo demás (congelaciones, motivo de anulación), que el panel no usa.
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../../core/api/client";
import { pageSchema } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";
import { copAmount } from "./schemas/money";

export const MEMBERSHIP_STATUSES = ["pending_payment", "active", "expiring", "expired", "frozen", "cancelled"] as const;
export type MembershipStatus = (typeof MEMBERSHIP_STATUSES)[number];

/** Estados de una membresía que recibe pagos (las vencidas y anuladas no se ofrecen). */
export const OPEN_MEMBERSHIP_STATUSES = ["active", "expiring", "frozen", "pending_payment"] as const satisfies readonly MembershipStatus[];
/** Un socio tiene a lo sumo una vigente y una futura; 20 deja margen sin paginar. */
export const OPEN_MEMBERSHIPS_LIMIT = 20;

const membershipRowShape = {
  id: z.string().min(1),
  member_id: z.string().min(1),
  member_name: z.string(),
  plan_id: z.string().min(1),
  plan_name: z.string(),
  status: z.enum(MEMBERSHIP_STATUSES),
  start_date: z.string(),
  end_date: z.string(),
  agreed_price_cop: copAmount,
  paid_cop: copAmount,
  classes_total: z.number().int().nullable(),
  classes_remaining: z.number().int().nullable(),
};

export const membershipRowSchema = z.object(membershipRowShape).strict();
export type MembershipRowView = z.infer<typeof membershipRowSchema>;
export const membershipsPageSchema = pageSchema(membershipRowSchema);
/** GET /memberships/{id} reducido a la fila (sin `.strict()`: el detalle trae más campos). */
export const membershipOptionSchema = z.object(membershipRowShape);

export const membershipSummarySchema = z
  .object({ active: copAmount, expiring: copAmount, expired: copAmount, frozen: copAmount, pending_payment: copAmount })
  .strict();
export type MembershipSummaryView = z.infer<typeof membershipSummarySchema>;

export const MEMBERSHIPS_SUMMARY_QUERY_KEY = ["memberships-summary"] as const;

export function openMembershipsKey(memberId: string): readonly ["memberships", "open", string] {
  return ["memberships", "open", memberId];
}

export function membershipOptionKey(id: string): readonly ["memberships", "option", string] {
  return ["memberships", "option", id];
}

export function useMembershipSummary(): UseQueryResult<MembershipSummaryView> {
  return useQuery({
    queryKey: MEMBERSHIPS_SUMMARY_QUERY_KEY,
    queryFn: async ({ signal }) => parseResponse(membershipSummarySchema, await api.get<unknown>("/memberships/summary", { signal })),
  });
}

export function useMemberOpenMemberships(memberId: string | null): UseQueryResult<MembershipRowView[]> {
  return useQuery({
    queryKey: openMembershipsKey(memberId ?? ""),
    queryFn: async ({ signal }) => {
      const query = listParams({ limit: OPEN_MEMBERSHIPS_LIMIT, offset: 0, member_id: memberId ?? "", status: OPEN_MEMBERSHIP_STATUSES.join(",") });
      return parseResponse(membershipsPageSchema, await api.get<unknown>("/memberships", { query, signal })).items;
    },
    enabled: memberId !== null,
  });
}

export function useMembershipOption(id: string | null): UseQueryResult<MembershipRowView> {
  return useQuery({
    queryKey: membershipOptionKey(id ?? ""),
    queryFn: async ({ signal }) => parseResponse(membershipOptionSchema, await api.get<unknown>(`/memberships/${encodeURIComponent(id ?? "")}`, { signal })),
    enabled: id !== null,
  });
}
