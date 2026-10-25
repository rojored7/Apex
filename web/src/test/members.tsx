// S2-F6: datos y montaje de prueba de /socios y /socios/nuevo. Las filas imitan MemberRowOut de
// GET /members (sin ningún dato cifrado, N-01) y el alta, MemberDetailOut de POST /members (los
// cinco campos sensibles enmascarados). /socios/:id es un marcador: la ficha llega con US-073.
// S3-F2: renderMembers responde también GET /memberships/summary (conteos de los chips) y
// GET /plans (filtro de plan); `memberRows(n)` y `pagedMemberPage` sirven la lista por páginas
// ("Cargar más"); `listCalls` deja fuera la consulta del total (`limit=1&offset=0`, el chip
// "Todos"), que se lee con `totalCalls`.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { SessionRoleProvider } from "../core/auth";
import MemberFormPage from "../features/members/pages/MemberFormPage";
import MembersListPage from "../features/members/pages/MembersListPage";
import { planPage, PLANS } from "./plans";
import { mockApi, testQueryClient, type MockHandler, type MockReply, type RecordedCall } from "./server";

export interface MemberRowFixture {
  id: string;
  first_name: string;
  last_name: string;
  sex: "f" | "m" | "x" | null;
  status: "active" | "inactive";
  deleted_at: string | null;
  membership_status: string | null;
  plan_name: string | null;
  membership_end_date: string | null;
}

const row = (id: string, first_name: string, last_name: string, overrides: Partial<MemberRowFixture> = {}): MemberRowFixture => ({
  id,
  first_name,
  last_name,
  sex: "f",
  status: "active",
  deleted_at: null,
  membership_status: null,
  plan_name: null,
  membership_end_date: null,
  ...overrides,
});

export const MEMBERS = {
  laura: row("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "Laura", "Gómez"),
  andres: row("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", "Andrés", "Ruiz", { sex: "m", status: "inactive" }),
  elena: row("cccccccc-cccc-4ccc-8ccc-cccccccccccc", "Elena", "Vargas", { sex: null, deleted_at: "2026-10-20T15:00:00Z" }),
} as const satisfies Record<string, MemberRowFixture>;

export const MEMBER_ROWS: MemberRowFixture[] = Object.values(MEMBERS);

/** `n` socios "Socio 01 Prueba"… con ids UUID; el primero es Laura Gómez (para buscar "laura"). */
export function memberRows(n: number): MemberRowFixture[] {
  return Array.from({ length: n }, (_, index) => {
    const number = String(index + 1).padStart(2, "0");
    const id = `${String(index + 1).padStart(8, "0")}-0000-4000-8000-000000000000`;
    return index === 0
      ? row(id, "Laura", "Gómez", { membership_status: "active", plan_name: "Mensual", membership_end_date: "2026-11-27" })
      : row(id, `Socio ${number}`, "Prueba", { membership_status: "expired", plan_name: "12 clases", membership_end_date: "2026-10-15" });
  });
}

/** La página de `rows` que piden `limit` y `offset`, con el total de todas. */
export function pagedMemberPage(call: RecordedCall, rows: MemberRowFixture[]): MockReply {
  const url = new URL(call.url, "http://apex.test");
  const limit = Number(url.searchParams.get("limit"));
  const offset = Number(url.searchParams.get("offset"));
  return { status: 200, body: { items: rows.slice(offset, offset + limit), total: rows.length, limit, offset } };
}

export interface MembershipSummaryFixture {
  active: number;
  expiring: number;
  expired: number;
  frozen: number;
  pending_payment: number;
}

/** GET /memberships/summary de Socios_Lista.html: 342 socios, 273 con membresía (69 sin ella). */
export const SOCIOS_SUMMARY: MembershipSummaryFixture = { active: 210, expiring: 18, expired: 41, frozen: 4, pending_payment: 0 };

/** La consulta del total del chip "Todos" (GET /members?limit=1&offset=0). */
export const isTotalCall = (call: RecordedCall): boolean => new URL(call.url, "http://apex.test").searchParams.toString() === "limit=1&offset=0";

export const NEW_MEMBER_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd";
export const EXISTING_MEMBER_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee";

export function memberPage(call: RecordedCall, rows: MemberRowFixture[] = MEMBER_ROWS, total = rows.length): MockReply {
  const url = new URL(call.url, "http://apex.test");
  return { status: 200, body: { items: rows, total, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) } };
}

/** MemberDetailOut del alta, con los campos sensibles enmascarados como los devuelve B7. */
export function memberDetail(warnings: string[] = []): MockReply {
  return {
    status: 201,
    body: {
      id: NEW_MEMBER_ID,
      first_name: "Laura",
      last_name: "Gómez",
      sex: "f",
      status: "active",
      document_type: "CC",
      document: "CC •••• 4417",
      phone: "••• ••• 4567",
      email: "l•••@•••.co",
      birth_date: "••/••/1991",
      emergency_contact: "Registrado",
      data_consent_at: warnings.length > 0 ? null : "2026-10-22T15:00:00Z",
      data_consent_version: warnings.length > 0 ? null : "2026-10",
      deleted_at: null,
      membership_status: null,
      plan_name: null,
      membership_end_date: null,
      created_at: "2026-10-22T15:00:00Z",
      updated_at: "2026-10-22T15:00:00Z",
      warnings,
    },
  };
}

export const apiError = (status: number, code: string, extra: Record<string, unknown> = {}, headers?: Record<string, string>): MockReply => ({
  status,
  body: { error: { code, message: "Mensaje del api.", ...extra } },
  ...(headers ? { headers } : {}),
});

export interface RenderMembersOptions {
  handlers?: Record<string, MockHandler>;
  rows?: MemberRowFixture[];
  queryClient?: QueryClient;
}

export function renderMembers(entry = "/socios", { handlers = {}, rows = MEMBER_ROWS, queryClient = testQueryClient() }: RenderMembersOptions = {}) {
  const mock = mockApi({
    "GET /members": (call) => memberPage(call, rows),
    "POST /members": memberDetail(),
    "GET /memberships/summary": { status: 200, body: SOCIOS_SUMMARY },
    "GET /plans": (call) => planPage(call, [PLANS.clases, PLANS.mensual]),
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
      { path: "/socios", element: shell(<MembersListPage />) },
      { path: "/socios/nuevo", element: shell(<MemberFormPage />) },
      { path: "/socios/:id", element: shell(<h1>Ficha del socio</h1>) },
    ],
    { initialEntries: [entry] },
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

/** Parámetros de cada GET /members de la lista, en orden (sin la consulta del total). */
export function listCalls(mock: { callsTo: (key: string) => RecordedCall[] }): URLSearchParams[] {
  return mock
    .callsTo("GET /members")
    .filter((c) => !isTotalCall(c))
    .map((c) => new URL(c.url, "http://apex.test").searchParams);
}

/** Las consultas del total del chip "Todos". */
export function totalCalls(mock: { callsTo: (key: string) => RecordedCall[] }): RecordedCall[] {
  return mock.callsTo("GET /members").filter(isTotalCall);
}

/** Parámetros de cada GET /plans, en orden. */
export function planCalls(mock: { callsTo: (key: string) => RecordedCall[] }): URLSearchParams[] {
  return mock.callsTo("GET /plans").map((c) => new URL(c.url, "http://apex.test").searchParams);
}
