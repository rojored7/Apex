// S3-F3 (plan del Sprint 3, sección 2, "Front"): datos de prueba de pagos. Imitan el contrato de
// B3 a B8: GET /payments/methods (`{ items }`, D25), PaymentOut, PaymentRow, PaymentDetail y
// PaymentsSummary.
// S3-F6: renderPayments monta /pagos (Pagos.html) en un router de datos (nav y main, como
// PanelShell), con la sesión por SessionRoleProvider (signInAs) y un marcador para la ficha.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import type { components } from "../core/api/types";
import { SessionRoleProvider } from "../core/auth";
import PaymentsPage from "../features/payments/pages/PaymentsPage";
import { mockApi, testQueryClient, type MockHandler, type MockReply, type RecordedCall } from "./server";

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

// S3-F4 y S3-F6: fila y detalle de la lista de pagos (PaymentRow y PaymentDetail del contrato de B8,
// D26, con `backdated` de S3-D51 y el correo parcial de S3-D57).
export type PaymentRowFixture = components["schemas"]["PaymentRow"];
export type PaymentDetailFixture = components["schemas"]["PaymentDetail"];
export type PaymentsSummaryFixture = components["schemas"]["PaymentsSummary"];

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

// S3-F6: tres filas que cubren Pagos.html: Laura con Nequi y referencia (la registró el coach), Diego
// en efectivo sin referencia (la registró el admin) y Sofía con Bre-B anulada y retroactiva.
export const COACH_ID = "00000000-0000-4000-8000-000000000002";
export const ADMIN_ID = "00000000-0000-4000-8000-000000000001";
export const DIEGO_PAYMENT_ID = "99999999-9999-4999-8999-000000000002";
export const SOFIA_PAYMENT_ID = "99999999-9999-4999-8999-000000000003";

export const PAYMENT_ROWS: PaymentRowFixture[] = [
  paymentRow(),
  paymentRow({
    id: DIEGO_PAYMENT_ID,
    paid_at: "2026-10-20T16:52:00Z",
    method: "cash",
    reference: null,
    registered_by: ADMIN_ID,
    registered_by_name: "a•••@apex.test",
    membership_id: "66666666-6666-4666-8666-000000000002",
    member_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    member_first_name: "Diego",
    member_last_name: "Mora",
    membership_start_date: "2026-10-20",
    membership_end_date: "2026-11-19",
  }),
  paymentRow({
    id: SOFIA_PAYMENT_ID,
    paid_at: "2026-10-19T23:28:00Z",
    amount_cop: 60_000,
    method: "breb",
    reference: "BRB-99812",
    voided: true,
    void_reason: "Duplicado",
    membership_id: "66666666-6666-4666-8666-000000000003",
    member_id: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
    member_first_name: "Sofía",
    member_last_name: "Pardo",
    membership_start_date: "2026-09-25",
    membership_end_date: "2026-10-24",
    backdated: true,
  }),
];

/** La página de GET /payments con el limit y el offset pedidos. */
export function paymentsPage(call: RecordedCall, rows: PaymentRowFixture[] = PAYMENT_ROWS, total = rows.length): MockReply {
  const url = new URL(call.url, "http://apex.test");
  return { status: 200, body: { items: rows, total, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) } };
}

export function paymentsSummary(overrides: Partial<PaymentsSummaryFixture> = {}): PaymentsSummaryFixture {
  return {
    month: "2026-10",
    total_cop: 18_240_000,
    payments_count: 152,
    voided_count: 3,
    by_method: { cash: 9_100_000, nequi: 6_340_000, breb: 2_800_000 },
    ...overrides,
  };
}

export const paymentDetailKey = (id: string = PAYMENT_ID): string => `GET /payments/${id}`;

export interface RenderPaymentsOptions {
  handlers?: Record<string, MockHandler>;
  rows?: PaymentRowFixture[];
  queryClient?: QueryClient;
}

export function renderPayments(entry = "/pagos", options: RenderPaymentsOptions = {}) {
  const { handlers = {}, rows = PAYMENT_ROWS, queryClient = testQueryClient() } = options;
  const mock = mockApi({
    "GET /payments": (call) => paymentsPage(call, rows),
    "GET /payments/summary": { status: 200, body: paymentsSummary() },
    "GET /payments/methods": paymentMethods(),
    [paymentDetailKey()]: { status: 200, body: paymentDetail() },
    ...handlers,
  });
  const shell = (page: ReactNode) => (
    <>
      <nav aria-label="Menú principal">
        <a href="/">Inicio</a>
      </nav>
      <main>{page}</main>
    </>
  );
  const [pathname = entry, query] = entry.split("?");
  const router = createMemoryRouter(
    [
      { path: "/pagos", element: shell(<PaymentsPage />) },
      { path: "/socios/:id", element: shell(<h1>Ficha del socio</h1>) },
    ],
    { initialEntries: [{ pathname, search: query ? `?${query}` : "" }] },
  );
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SessionRoleProvider>
        <RouterProvider router={router} />
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, router, queryClient, user: userEvent.setup(), ...view };
}

/** Los parámetros de cada GET /payments (la lista; el resumen y el detalle van aparte). */
export function paymentListCalls(mock: { callsTo: (key: string) => RecordedCall[] }): URLSearchParams[] {
  return mock.callsTo("GET /payments").map((c) => new URL(c.url, "http://apex.test").searchParams);
}

/** La fila de escritorio de un socio, por su nombre (la primera columna es el enlace a la ficha). */
export async function findPaymentRow(name: string): Promise<HTMLElement> {
  const link = await screen.findByRole("link", { name });
  const tr = link.closest("tr");
  if (!tr) throw new Error(`sin fila para ${name}`);
  return tr;
}
