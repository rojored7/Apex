// S3-F7 · US-093 y US-101: datos y montaje de prueba de las pestañas Membresías y Pagos de la ficha.
// - Las membresías imitan MembershipOut de GET /members/{id}/memberships (B11), con fechas relativas
//   al "hoy" de Bogotá de la corrida: una futura pendiente de pago, la vigente por vencer con un abono
//   y una congelación, una vencida y una anulada, en el orden del api (`start_date` descendente).
// - Los pagos imitan PaymentRow de GET /members/{id}/payments (B11): uno válido con Nequi, uno
//   anulado con motivo y uno retroactivo, en el orden del api (`paid_at` descendente).
// - renderMemberTab monta la pestaña como hija de /socios/:id con un padre que le pasa el socio por el
//   contexto del <Outlet /> (S3-D65), como MemberDetailPage, y marcadores para la venta.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentType } from "react";
import { createMemoryRouter, Outlet, RouterProvider, useLocation } from "react-router";
import type { components } from "../core/api/types";
import { SessionRoleProvider } from "../core/auth";
import { addDaysCivil, todayBogota } from "../core/i18n/format";
import type { MemberTabContext, MemberTabMember } from "../shared/data/members";
import { MEMBER_ID } from "./memberDetail";
import { paymentMethods, paymentRow, type PaymentRowFixture } from "./payments";
import { mockApi, testQueryClient, type MockHandler, type MockReply, type RecordedCall } from "./server";

export { MEMBER_ID };

export type MemberMembershipFixture = components["schemas"]["MembershipOut"];

export const CURRENT_ID = "11111111-1111-4111-8111-111111111111";
export const FUTURE_ID = "22222222-2222-4222-8222-222222222222";
export const PAST_ID = "33333333-3333-4333-8333-333333333333";
export const CANCELLED_ID = "44444444-4444-4444-8444-444444444444";

export const MEMBER_MEMBERSHIPS_PATH = `/members/${MEMBER_ID}/memberships`;
export const MEMBER_PAYMENTS_PATH = `/members/${MEMBER_ID}/payments`;

/** Una fecha civil a `days` días de hoy en Bogotá. */
export function dayFromToday(days: number): string {
  const value = addDaysCivil(todayBogota(), days);
  if (value === null) throw new Error("dayFromToday: hoy no es una fecha civil");
  return value;
}

export function memberMembership(overrides: Partial<MemberMembershipFixture> = {}): MemberMembershipFixture {
  return {
    id: CURRENT_ID,
    member_id: MEMBER_ID,
    member_name: "Laura Gómez",
    plan_id: "55555555-5555-4555-8555-555555555555",
    plan_name: "Mensual",
    status: "expiring",
    start_date: dayFromToday(-22),
    end_date: dayFromToday(8),
    agreed_price_cop: 120_000,
    paid_cop: 60_000,
    classes_total: null,
    classes_remaining: null,
    cancel_reason: null,
    cancelled_at: null,
    freezes: [{ id: "f0000000-0000-4000-8000-000000000001", frozen_from: dayFromToday(-15), frozen_to: dayFromToday(-11), days: 5, created_at: "2026-10-01T15:00:00Z" }],
    created_at: "2026-10-01T15:00:00Z",
    ...overrides,
  };
}

/** Futura, vigente, vencida y anulada, en el orden del api. */
export function memberMemberships(): MemberMembershipFixture[] {
  return [
    memberMembership({ id: FUTURE_ID, plan_name: "Trimestral", status: "pending_payment", start_date: dayFromToday(9), end_date: dayFromToday(99), agreed_price_cop: 320_000, paid_cop: 0, freezes: [] }),
    memberMembership(),
    memberMembership({ id: PAST_ID, status: "expired", start_date: dayFromToday(-60), end_date: dayFromToday(-30), paid_cop: 120_000, freezes: [] }),
    memberMembership({
      id: CANCELLED_ID,
      plan_name: "12 clases",
      status: "cancelled",
      start_date: dayFromToday(-90),
      end_date: dayFromToday(-61),
      agreed_price_cop: 110_000,
      paid_cop: 0,
      classes_total: 12,
      classes_remaining: 12,
      cancel_reason: "Error de venta",
      cancelled_at: "2026-08-01T15:00:00Z",
      freezes: [],
    }),
  ];
}

/** La página de un listado con el limit y el offset pedidos. */
export function pageOf(call: RecordedCall, rows: readonly unknown[], total = rows.length): MockReply {
  const url = new URL(call.url, "http://apex.test");
  return { status: 200, body: { items: rows, total, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) } };
}

export const VALID_PAYMENT_ID = "aaaa0000-0000-4000-8000-000000000001";
export const VOIDED_PAYMENT_ID = "aaaa0000-0000-4000-8000-000000000002";
export const BACKDATED_PAYMENT_ID = "aaaa0000-0000-4000-8000-000000000003";

/** Un pago válido con Nequi, uno anulado con motivo y uno retroactivo, en el orden del api. */
export function memberPayments(): PaymentRowFixture[] {
  return [
    paymentRow({ id: VALID_PAYMENT_ID, member_id: MEMBER_ID, membership_id: CURRENT_ID, paid_at: "2026-10-20T19:10:00Z", amount_cop: 60_000, method: "nequi", reference: "M12345678" }),
    paymentRow({
      id: VOIDED_PAYMENT_ID,
      member_id: MEMBER_ID,
      membership_id: CURRENT_ID,
      paid_at: "2026-10-18T14:00:00Z",
      amount_cop: 60_000,
      method: "breb",
      reference: "BRB-99812",
      voided: true,
      void_reason: "Duplicado",
    }),
    paymentRow({
      id: BACKDATED_PAYMENT_ID,
      member_id: MEMBER_ID,
      membership_id: PAST_ID,
      paid_at: "2026-09-01T15:00:00Z",
      amount_cop: 120_000,
      method: "cash",
      reference: null,
      registered_by_name: "a•••@apex.test",
      backdated: true,
    }),
  ];
}

export const TAB_MEMBER: MemberTabMember = { id: MEMBER_ID, first_name: "Laura", last_name: "Gómez", deleted_at: null };
export const DELETED_TAB_MEMBER: MemberTabMember = { ...TAB_MEMBER, deleted_at: "2026-10-20T15:00:00Z" };

function Location() {
  const location = useLocation();
  return <span data-testid="location">{`${location.pathname}${location.search}`}</span>;
}

function Ficha({ member }: { member: MemberTabMember | null }) {
  return (
    <>
      <nav aria-label="Menú principal">
        <a href="/">Inicio</a>
      </nav>
      <main>
        <h1>Ficha</h1>
        {member ? <Outlet context={{ member } satisfies MemberTabContext} /> : <Outlet />}
      </main>
      <Location />
    </>
  );
}

export interface RenderTabOptions {
  handlers?: Record<string, MockHandler>;
  queryClient?: QueryClient;
  /** El socio del contexto de la ficha; null monta la pestaña sin él. */
  member?: MemberTabMember | null;
}

/** Monta una pestaña como hija de /socios/:id (`segment` es "membresias" o "pagos"). */
export function renderMemberTab(Tab: ComponentType, segment: "membresias" | "pagos", entry = `/socios/${MEMBER_ID}/${segment}`, options: RenderTabOptions = {}) {
  const { handlers = {}, queryClient = testQueryClient(), member = TAB_MEMBER } = options;
  const mock = mockApi({
    [`GET ${MEMBER_MEMBERSHIPS_PATH}`]: (call) => pageOf(call, memberMemberships()),
    [`GET ${MEMBER_PAYMENTS_PATH}`]: (call) => pageOf(call, memberPayments()),
    "GET /payments/methods": paymentMethods(),
    ...handlers,
  });
  const router = createMemoryRouter(
    [
      { path: "/socios/:id", element: <Ficha member={member} />, children: [{ path: `/socios/:id/${segment}`, element: <Tab /> }] },
      { path: "/membresias/vender", element: <h1>Vender membresía</h1> },
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

/** Los parámetros de cada GET de la lista, en orden. */
export function listCallsTo(mock: { callsTo: (key: string) => RecordedCall[] }, path: string): URLSearchParams[] {
  return mock.callsTo(`GET ${path}`).map((call) => new URL(call.url, "http://apex.test").searchParams);
}
