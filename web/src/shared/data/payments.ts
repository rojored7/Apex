// S3-F7 (S3-D65, condición 8): datos de pagos que comparten varias features.
// - paymentRowSchema y paymentsPageSchema: la fila de GET /payments y de GET /members/{id}/payments
//   (PaymentRow del contrato de B8 y B11, D26, con `backdated` de S3-D51), estricta y con enteros.
//   Nace en features/payments/schemas.ts (S3-F6) y se muda aquí porque la pide useMemberPayments;
//   features/payments la reexporta.
// - useMemberPayments(memberId, { voided, limit, offset }): GET /members/{id}/payments (B11) con la
//   clave ["payments", "member", memberId, params]: registrar y anular invalidan ["payments"] y la
//   pestaña se relee sola. `voided` ausente trae todos; `false`, solo los válidos ("Ocultar
//   anulados"). Orden del api: `paid_at` descendente y, en empate, `id` descendente. Sin cupo propio
//   (D28): la pestaña no busca personas. Mientras llega la página nueva se conserva la anterior (del mismo socio).
import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { z } from "zod";
import { api } from "../../core/api/client";
import { pageSchema, type Page } from "../../core/api/page";
import { listParams } from "../../core/api/query";
import { parseResponse } from "../../core/api/response";
import { copInt } from "./schemas/money";
import { paymentMethodCodeSchema } from "./schemas/payment";

/**
 * Fase 4 del Sprint 3 (M1): lo que deja viejo un pago, y por eso lo invalidan registrarlo, anularlo y
 * vender (la venta puede traer el primer pago): pagos, el resumen del mes de /pagos, membresías, su
 * resumen y socios (el estado en la lista). Una sola lista para que ninguna escritura olvide una clave.
 */
export const INVALIDATE_AFTER_PAYMENT = [["payments"], ["payments-summary"], ["memberships"], ["memberships-summary"], ["members"]] as const;

// Las fechas de la membresía son civiles ("AAAA-MM-DD"); `registered_by_name` es el correo parcial
// ("l•••@dominio", S3-D57) y llega en null si la cuenta ya no existe.
export const paymentRowShape = {
  id: z.string().min(1),
  membership_id: z.string().min(1),
  member_id: z.string().min(1),
  member_first_name: z.string(),
  member_last_name: z.string(),
  plan_name: z.string(),
  membership_start_date: z.string(),
  membership_end_date: z.string(),
  amount_cop: copInt,
  method: paymentMethodCodeSchema,
  reference: z.string().nullable(),
  paid_at: z.string(),
  registered_by: z.string().min(1),
  registered_by_name: z.string().nullable(),
  voided: z.boolean(),
  void_reason: z.string().nullable(),
  /** S3-D51: registrado más de 24 h después de `paid_at`. */
  backdated: z.boolean(),
};

export const paymentRowSchema = z.object(paymentRowShape).strict();
export type PaymentRowView = z.infer<typeof paymentRowSchema>;
export const paymentsPageSchema = pageSchema(paymentRowSchema);

export interface MemberPaymentsParams {
  /** Ausente: todos; `false`: solo los válidos; `true`: solo los anulados. */
  voided?: boolean;
  limit: number;
  offset: number;
}

export function memberPaymentsKey(memberId: string, params: MemberPaymentsParams): readonly ["payments", "member", string, MemberPaymentsParams] {
  return ["payments", "member", memberId, params];
}

export function useMemberPayments(memberId: string | null, params: MemberPaymentsParams): UseQueryResult<Page<PaymentRowView>> {
  return useQuery({
    queryKey: memberPaymentsKey(memberId ?? "", params),
    queryFn: async ({ signal }) =>
      parseResponse(paymentsPageSchema, await api.get<unknown>(`/members/${encodeURIComponent(memberId ?? "")}/payments`, { query: listParams({ ...params }), signal })),
    enabled: memberId !== null,
    // Revisión S3-F7 (M1): conserva la página anterior solo si es del mismo socio.
    placeholderData: (previous, previousQuery) => (previousQuery?.queryKey[2] === (memberId ?? "") ? previous : undefined),
  });
}
