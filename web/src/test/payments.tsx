// S3-F3 (plan del Sprint 3, sección 2, "Front"): datos de prueba de pagos. Imitan el contrato de
// B3 a B6: GET /payments/methods (`{ items }`, D25) y PaymentOut. Las filas y el detalle de la
// lista de pagos (`paymentRow`, `paymentDetail`) llegan con su contrato (B8) en S3-F4 y S3-F6.
import type { components } from "../core/api/types";
import type { MockReply } from "./server";

export type PaymentMethodFixture = components["schemas"]["PaymentMethodOut"];
export type PaymentOutFixture = components["schemas"]["PaymentOut"];

/** Los tres medios fijos en el orden del api, con las etiquetas por defecto (D24). */
export const PAYMENT_METHODS: PaymentMethodFixture[] = [
  { code: "cash", label: "Efectivo", hint: "" },
  { code: "nequi", label: "Nequi", hint: "Número de transacción de Nequi" },
  { code: "breb", label: "Bre-B", hint: "Referencia de la transferencia" },
];

export function paymentMethods(items: PaymentMethodFixture[] = PAYMENT_METHODS): MockReply {
  return { status: 200, body: { items } };
}

export const FIRST_PAYMENT_ID = "77777777-7777-4777-8777-777777777777";

export function paymentOut(overrides: Partial<PaymentOutFixture> = {}): PaymentOutFixture {
  return {
    id: FIRST_PAYMENT_ID,
    membership_id: "66666666-6666-4666-8666-666666666666",
    member_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    amount_cop: 120_000,
    method: "cash",
    reference: null,
    paid_at: "2026-10-28T15:00:00Z",
    registered_by: "00000000-0000-4000-8000-000000000001",
    voided: false,
    voided_at: null,
    voided_by: null,
    void_reason: null,
    created_at: "2026-10-28T15:00:00Z",
    ...overrides,
  };
}

// S3-F4: fila y detalle de la lista de pagos (PaymentRow y PaymentDetail del blueprint B8, D26, con
// `backdated` de S3-D51). Su contrato llega con B8; F6 los ajusta si cambia.
export interface PaymentRowFixture {
  id: string;
  paid_at: string;
  amount_cop: number;
  method: "cash" | "nequi" | "breb";
  reference: string | null;
  voided: boolean;
  void_reason: string | null;
  registered_by: string;
  registered_by_name: string;
  membership_id: string;
  member_id: string;
  member_first_name: string;
  member_last_name: string;
  plan_name: string;
  membership_start_date: string;
  membership_end_date: string;
  backdated: boolean;
}

export interface PaymentDetailFixture extends PaymentRowFixture {
  voided_by: string | null;
  voided_by_name: string | null;
  voided_at: string | null;
  created_at: string;
}

export const PAYMENT_ID = "99999999-9999-4999-8999-999999999999";

export function paymentRow(overrides: Partial<PaymentRowFixture> = {}): PaymentRowFixture {
  return {
    id: PAYMENT_ID,
    paid_at: "2026-10-20T19:10:00Z",
    amount_cop: 120_000,
    method: "nequi",
    reference: "M12345678",
    voided: false,
    void_reason: null,
    registered_by: "00000000-0000-4000-8000-000000000002",
    registered_by_name: "c•••@apex.test",
    membership_id: "66666666-6666-4666-8666-666666666666",
    member_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
    member_first_name: "Laura",
    member_last_name: "Gómez",
    plan_name: "Mensual",
    membership_start_date: "2026-10-29",
    membership_end_date: "2026-11-28",
    backdated: false,
    ...overrides,
  };
}

export function paymentDetail(overrides: Partial<PaymentDetailFixture> = {}): PaymentDetailFixture {
  return { ...paymentRow(), voided_by: null, voided_by_name: null, voided_at: null, created_at: "2026-10-20T19:10:00Z", ...overrides };
}
