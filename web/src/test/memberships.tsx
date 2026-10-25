// S3-F3 (plan del Sprint 3, sección 2, "Front"): datos y montaje de prueba de la venta. Imitan el
// contrato de B1 a B6: MembershipOut, SellMembershipOut (201 de POST /members/{id}/memberships) y
// RenewalPreviewOut. Las filas de la lista (`membershipRow`) y el resumen (`summary`) llegan con su
// contrato (B7) en S3-F4 y S3-F5.
// renderSell monta /membresias/vender en un router de datos, como PanelShell (nav y main), con la
// sesión por SessionRoleProvider (signInAs), y marcadores para /socios y /socios/:id.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import type { ReactNode } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import type { components } from "../core/api/types";
import { SessionRoleProvider } from "../core/auth";
import SellPage from "../features/memberships/pages/SellPage";
import { MEMBERS, memberPage, type MemberRowFixture } from "./members";
import { FIRST_PAYMENT_ID, paymentMethods } from "./payments";
import { planPage, PLANS, type PlanFixture } from "./plans";
import { mockApi, testQueryClient, type MockHandler, type MockReply, type RecordedCall } from "./server";

export type MembershipOutFixture = components["schemas"]["MembershipOut"];
export type SellMembershipOutFixture = components["schemas"]["SellMembershipOut"];
export type RenewalPreviewFixture = components["schemas"]["RenewalPreviewOut"];

export const MEMBERSHIP_ID = "66666666-6666-4666-8666-666666666666";
export const EXISTING_MEMBERSHIP_ID = "88888888-8888-4888-8888-888888888888";

/** "Hoy" de las pruebas de la venta: 28 oct 2026, 10:00 a. m. en Bogotá. */
export const SELL_NOW = new Date("2026-10-28T15:00:00Z");
export const SELL_TODAY = "2026-10-28";

export function membershipOut(overrides: Partial<MembershipOutFixture> = {}): MembershipOutFixture {
  return {
    id: MEMBERSHIP_ID,
    member_id: MEMBERS.laura.id,
    member_name: "Laura Gómez",
    plan_id: PLANS.mensual.id,
    plan_name: "Mensual",
    status: "active",
    start_date: SELL_TODAY,
    end_date: "2026-11-27",
    agreed_price_cop: 120_000,
    paid_cop: 120_000,
    classes_total: null,
    classes_remaining: null,
    cancel_reason: null,
    cancelled_at: null,
    freezes: [],
    created_at: "2026-10-28T15:00:00Z",
    ...overrides,
  };
}

export function sellMembershipOut(overrides: Partial<SellMembershipOutFixture> = {}): SellMembershipOutFixture {
  return { ...membershipOut(), first_payment_id: FIRST_PAYMENT_ID, ...overrides };
}

export function renewalPreview(overrides: Partial<RenewalPreviewFixture> = {}): RenewalPreviewFixture {
  return { start_date: "2026-10-29", end_date: "2026-11-28", agreed_price_cop: 120_000, current_end_date: "2026-10-28", ...overrides };
}

export const apiError = (status: number, code: string, extra: Record<string, unknown> = {}, headers?: Record<string, string>): MockReply => ({
  status,
  body: { error: { code, message: "Mensaje del api.", ...extra } },
  ...(headers ? { headers } : {}),
});

/** Planes activos de la venta, en el orden del api. */
export const ACTIVE_PLANS: PlanFixture[] = [PLANS.clases, PLANS.mensual];

export const sellKey = (memberId: string = MEMBERS.laura.id): string => `POST /members/${memberId}/memberships`;
export const previewKey = (memberId: string = MEMBERS.laura.id): string => `GET /members/${memberId}/memberships/renewal-preview`;

export interface RenderSellOptions {
  handlers?: Record<string, MockHandler>;
  plans?: PlanFixture[];
  members?: MemberRowFixture[];
  queryClient?: QueryClient;
  /** Estado de la navegación de entrada (por ejemplo el nombre del socio al renovar). */
  state?: unknown;
}

export function renderSell(entry = "/membresias/vender", options: RenderSellOptions = {}) {
  const { handlers = {}, plans = ACTIVE_PLANS, members = [MEMBERS.laura, MEMBERS.andres], queryClient = testQueryClient(), state } = options;
  const mock = mockApi({
    "GET /plans": (call) => planPage(call, plans),
    "GET /payments/methods": paymentMethods(),
    "GET /members": (call) => memberPage(call, members),
    [sellKey()]: { status: 201, body: sellMembershipOut() },
    [previewKey()]: { status: 200, body: renewalPreview() },
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
  const router = createMemoryRouter(
    [
      { path: "/membresias/vender", element: shell(<SellPage />) },
      { path: "/socios", element: shell(<h1>Socios</h1>) },
      { path: "/socios/:id", element: shell(<h1>Ficha del socio</h1>) },
      { path: "/planes", element: shell(<h1>Planes</h1>) },
    ],
    { initialEntries: [state === undefined ? entry : { pathname: entry.split("?")[0] ?? entry, search: entry.includes("?") ? `?${entry.split("?")[1] ?? ""}` : "", state }] },
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

/** Cuerpos de cada POST de venta, en orden. */
export function sellBodies(mock: { callsTo: (key: string) => RecordedCall[] }, memberId: string = MEMBERS.laura.id): Record<string, unknown>[] {
  return mock.callsTo(sellKey(memberId)).map((c) => c.body as Record<string, unknown>);
}

/** Valor de una fila del resumen ("Socio", "Vigencia", "Saldo"...). */
export function summaryValue(label: string, region: HTMLElement = screen.getByRole("complementary", { name: "Resumen" })): string {
  const term = within(region).getByText(label, { selector: "dt" });
  return term.nextElementSibling?.textContent ?? "";
}

/** Busca y elige un socio en el paso 1. */
export async function pickMember(user: UserEvent, text = "laura", name: RegExp = /Laura Gómez/): Promise<void> {
  await user.type(screen.getByRole("searchbox", { name: "Buscar socio" }), text);
  await user.click(await screen.findByRole("button", { name }));
}

/** Elige un plan en el paso 2 (la etiqueta empieza por el nombre del plan). */
export async function pickPlan(user: UserEvent, name: string): Promise<void> {
  await user.click(await screen.findByRole("radio", { name: new RegExp(`^${name}`) }));
}
