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
