// S2-F7: datos y montaje de prueba de /planes. Las filas imitan PlanOut de B9 (GET /plans,
// GET /plans/{id} y el 201 de POST /plans). El montaje usa un router de datos con /planes, igual
// que PanelShell (nav y main), y la sesión por SessionRoleProvider (signInAs).
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { SessionRoleProvider } from "../core/auth";
import PlansPage from "../features/plans/pages/PlansPage";
import { mockApi, testQueryClient, type MockHandler, type MockReply, type RecordedCall } from "./server";

export interface PlanFixture {
  id: string;
  name: string;
  price_cop: number;
  kind: "days" | "classes";
  duration_days: number;
  class_count: number | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const plan = (id: string, name: string, overrides: Partial<PlanFixture> = {}): PlanFixture => ({
  id,
  name,
  price_cop: 120_000,
  kind: "days",
  duration_days: 30,
  class_count: null,
  is_active: true,
  created_at: "2026-10-20T15:00:00Z",
  updated_at: "2026-10-20T15:00:00Z",
  ...overrides,
});

export const PLANS = {
  mensual: plan("11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "Mensual"),
  clases: plan("22222222-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "12 clases", { price_cop: 110_000, kind: "classes", duration_days: 60, class_count: 12 }),
  promo: plan("33333333-cccc-4ccc-8ccc-cccccccccccc", "Promo apertura", { price_cop: 90_000, is_active: false }),
} as const satisfies Record<string, PlanFixture>;

/** En el orden del api (por nombre). */
export const PLAN_ROWS: PlanFixture[] = [PLANS.clases, PLANS.mensual, PLANS.promo];

export const NEW_PLAN = plan("44444444-dddd-4ddd-8ddd-dddddddddddd", "Trimestral", { price_cop: 320_000, duration_days: 90 });
export const EXISTING_PLAN_ID = "55555555-eeee-4eee-8eee-eeeeeeeeeeee";

export function planPage(call: RecordedCall, rows: PlanFixture[] = PLAN_ROWS, total = rows.length): MockReply {
  const url = new URL(call.url, "http://apex.test");
  return { status: 200, body: { items: rows, total, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) } };
}

export const apiError = (status: number, code: string, extra: Record<string, unknown> = {}, headers?: Record<string, string>): MockReply => ({
  status,
  body: { error: { code, message: "Mensaje del api.", ...extra } },
  ...(headers ? { headers } : {}),
});

/** Manejadores de GET /plans/{id} para cada plan de prueba. */
export function detailHandlers(rows: PlanFixture[] = PLAN_ROWS): Record<string, MockHandler> {
  return Object.fromEntries(rows.map((row) => [`GET /plans/${row.id}`, { status: 200, body: row }]));
}

export interface RenderPlansOptions {
  handlers?: Record<string, MockHandler>;
  rows?: PlanFixture[];
  queryClient?: QueryClient;
}

export function renderPlans(entry = "/planes", { handlers = {}, rows = PLAN_ROWS, queryClient = testQueryClient() }: RenderPlansOptions = {}) {
  const mock = mockApi({ "GET /plans": (call) => planPage(call, rows), "POST /plans": { status: 201, body: NEW_PLAN }, ...detailHandlers(), ...handlers });
  const shell = (page: ReactNode) => (
    <>
      <nav aria-label="Menú principal">
        <a href="/">Inicio</a>
      </nav>
      <main>{page}</main>
    </>
  );
  const router = createMemoryRouter([{ path: "/planes", element: shell(<PlansPage />) }], { initialEntries: [entry] });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SessionRoleProvider>
        <RouterProvider router={router} />
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, router, queryClient, user: userEvent.setup(), ...view };
}

/** Parámetros de cada GET /plans, en orden. */
export function listCalls(mock: { callsTo: (key: string) => RecordedCall[] }): URLSearchParams[] {
  return mock.callsTo("GET /plans").map((c) => new URL(c.url, "http://apex.test").searchParams);
}
