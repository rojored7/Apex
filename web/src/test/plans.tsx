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
  /** S4A-B7 (S4A-D25): "Socios con él"; el api lo manda siempre (el esquema lo pone en 0 si falta). */
  active_members_count?: number;
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

/** S4A-F4: "Socios con él" de cada plan de prueba. */
export const MEMBERS_WITH_PLAN = { mensual: 4, clases: 12, promo: 0 } as const;

/** S4A-F4: las filas de /planes con su conteo (Mensual 4, 12 clases 12, Promo 0). */
export const MANAGED_ROWS: PlanFixture[] = [
  { ...PLANS.clases, active_members_count: MEMBERS_WITH_PLAN.clases },
  { ...PLANS.mensual, active_members_count: MEMBERS_WITH_PLAN.mensual },
  { ...PLANS.promo, active_members_count: MEMBERS_WITH_PLAN.promo },
];

/** S4A-F4: ¿es una lectura de los totales (dos GET /plans con limit=1 y active)? */
export function isCountCall(params: URLSearchParams): boolean {
  return params.get("limit") === "1" && params.has("active");
}

/**
 * S4A-F4: GET /plans de la pantalla. Las lecturas de los totales cuentan las filas por `active`; la
 * lista responde como planPage (todas las filas, sin filtrar).
 */
export function plansReply(call: RecordedCall, rows: PlanFixture[] = MANAGED_ROWS): MockReply {
  const params = new URL(call.url, "http://apex.test").searchParams;
  if (!isCountCall(params)) return planPage(call, rows);
  const active = params.get("active") === "true";
  const matching = rows.filter((row) => row.is_active === active);
  return { status: 200, body: { items: matching.slice(0, 1), total: matching.length, limit: 1, offset: 0 } };
}

/**
 * S4A-F4: un api de planes con estado para las acciones de la fila. PATCH, activate, deactivate y
 * DELETE cambian las filas; GET /plans (lista y totales) responde con lo que queda. `deleteReply`
 * permite simular el 409 de la baja.
 */
export function planStore(initial: PlanFixture[] = MANAGED_ROWS, { deleteReply }: { deleteReply?: (id: string) => MockReply | null } = {}) {
  let rows = initial.map((row) => ({ ...row }));
  const update = (id: string, change: Partial<PlanFixture>): MockReply => {
    rows = rows.map((row) => (row.id === id ? { ...row, ...change, updated_at: "2026-10-29T15:00:00Z" } : row));
    const found = rows.find((row) => row.id === id);
    return found ? { status: 200, body: found } : apiError(404, "plan_not_found");
  };
  const handlers: Record<string, MockHandler> = { "GET /plans": (call) => plansReply(call, rows) };
  for (const { id } of initial) {
    handlers[`PATCH /plans/${id}`] = (call) => update(id, call.body as Partial<PlanFixture>);
    handlers[`POST /plans/${id}/activate`] = () => update(id, { is_active: true });
    handlers[`POST /plans/${id}/deactivate`] = () => update(id, { is_active: false });
    handlers[`DELETE /plans/${id}`] = () => {
      const reply = deleteReply?.(id);
      if (reply) return reply;
      rows = rows.filter((row) => row.id !== id);
      return { status: 204 };
    };
  }
  return { handlers, rows: () => rows };
}

export interface RenderPlansOptions {
  handlers?: Record<string, MockHandler>;
  rows?: PlanFixture[];
  queryClient?: QueryClient;
}

export function renderPlans(entry = "/planes", { handlers = {}, rows = MANAGED_ROWS, queryClient = testQueryClient() }: RenderPlansOptions = {}) {
  const mock = mockApi({ "GET /plans": (call) => plansReply(call, rows), "POST /plans": { status: 201, body: NEW_PLAN }, ...detailHandlers(), ...handlers });
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

/** S4A-F4: parámetros de cada GET /plans de la lista, en orden (sin las lecturas de los totales, limit=1). */
export function listCalls(mock: { callsTo: (key: string) => RecordedCall[] }): URLSearchParams[] {
  return allPlanCalls(mock).filter((p) => !isCountCall(p));
}

/** S4A-F4: las lecturas de los totales (limit=1 con active=true o false). */
export function countCalls(mock: { callsTo: (key: string) => RecordedCall[] }): URLSearchParams[] {
  return allPlanCalls(mock).filter(isCountCall);
}

function allPlanCalls(mock: { callsTo: (key: string) => RecordedCall[] }): URLSearchParams[] {
  return mock.callsTo("GET /plans").map((c) => new URL(c.url, "http://apex.test").searchParams);
}
