// S4A-F2 · US-106: datos y montaje de prueba del historial del socio (GET /members/{id}/audit).
// - historyItem imita MemberHistoryItem de S4A-B5: sin valores, solo nombres de campo (`fields`),
//   `user_name` (parte local del correo o "Sistema") y `purpose` de un reveal automático.
// - HISTORY_ITEMS es la línea de tiempo de Laura en el orden del api (`seq` descendente): mostró el
//   documento, anuló un pago, registró un pago, el sistema marcó la membresía, vendió una membresía,
//   editó teléfono y correo, un aviso automático y el alta.
// - PHONE_VALUE y DOCUMENT_VALUE son valores que nunca deben aparecer: el api no los manda y la
//   pantalla no los pinta.
// - renderMemberHistoryTab monta la pestaña como hija de /socios/:id con el socio por el contexto.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, Outlet, RouterProvider } from "react-router";
import { SessionRoleProvider } from "../core/auth";
import MemberHistoryTab from "../features/members/components/MemberHistoryTab";
import type { MemberHistoryItemView } from "../features/members/schemas";
import { SYSTEM_USER_ID } from "../shared/lib/audit-labels";
import type { MemberTabContext } from "../shared/data/members";
import { MEMBER_ID } from "./memberDetail";
import { pageOf, TAB_MEMBER } from "./memberTabs";
import { mockApi, testQueryClient, type MockHandler, type MockReply, type RecordedCall } from "./server";

export { MEMBER_ID, SYSTEM_USER_ID };

export const HISTORY_PATH = `/members/${MEMBER_ID}/audit`;
export const ANA_ID = "a0a0a0a0-0000-4000-8000-000000000001";
export const JUAN_ID = "a0a0a0a0-0000-4000-8000-000000000002";
export const MEMBERSHIP_ID = "11111111-1111-4111-8111-111111111111";
export const PAYMENT_ID = "aaaa0000-0000-4000-8000-000000000001";

/** Valores que el api nunca manda en el historial: la pantalla no puede mostrarlos. */
export const PHONE_VALUE = "3001234567";
export const DOCUMENT_VALUE = "1020304417";

export function historyItem(overrides: Partial<MemberHistoryItemView> = {}): MemberHistoryItemView {
  return {
    seq: 1,
    at: "2026-10-20T15:00:00Z",
    user_id: ANA_ID,
    user_name: "ana",
    action: "update",
    table_name: "members.members",
    record_id: MEMBER_ID,
    fields: [],
    purpose: null,
    ...overrides,
  };
}

/** La línea de tiempo de Laura en el orden del api (`seq` descendente). */
export function historyItems(): MemberHistoryItemView[] {
  return [
    historyItem({ seq: 18, at: "2026-10-21T02:30:00Z", user_id: JUAN_ID, user_name: "juan", action: "reveal", fields: ["document"] }),
    historyItem({ seq: 17, at: "2026-10-20T22:00:00Z", table_name: "payments.payments", record_id: PAYMENT_ID, fields: ["voided", "voided_at", "voided_by"] }),
    historyItem({ seq: 16, at: "2026-10-20T21:00:00Z", user_id: JUAN_ID, user_name: "juan", action: "insert", table_name: "payments.payments", record_id: PAYMENT_ID }),
    historyItem({ seq: 15, at: "2026-10-20T10:00:00Z", user_id: SYSTEM_USER_ID, user_name: "Sistema", table_name: "memberships.memberships", record_id: MEMBERSHIP_ID, fields: ["status"] }),
    historyItem({ seq: 14, at: "2026-10-19T15:00:00Z", action: "insert", table_name: "memberships.memberships", record_id: MEMBERSHIP_ID }),
    historyItem({ seq: 13, at: "2026-10-18T15:00:00Z", fields: ["email", "phone"] }),
    historyItem({ seq: 12, at: "2026-10-17T15:00:00Z", user_id: SYSTEM_USER_ID, user_name: "Sistema", action: "reveal", fields: ["phone"], purpose: "notify" }),
    historyItem({ seq: 11, at: "2026-10-16T15:00:00Z", action: "insert" }),
  ];
}

/** `count` entradas de edición de teléfono con `seq` descendente desde `top`. */
export function manyHistoryItems(count: number, top = 1000): MemberHistoryItemView[] {
  return Array.from({ length: count }, (_, i) => historyItem({ seq: top - i, fields: ["phone"] }));
}

/** Responde la página pedida (limit y offset de la URL) de `items`, con `total` (por defecto su largo). */
export function historyReply(items: readonly MemberHistoryItemView[], total = items.length): (call: RecordedCall) => MockReply {
  return (call: RecordedCall) => {
    const url = new URL(call.url, "http://apex.test");
    const limit = Number(url.searchParams.get("limit"));
    const offset = Number(url.searchParams.get("offset"));
    return pageOf(call, items.slice(offset, offset + limit), total);
  };
}

/** Los parámetros de cada GET del historial, en orden. */
export function historyCalls(mock: { callsTo: (key: string) => RecordedCall[] }): URLSearchParams[] {
  return mock.callsTo(`GET ${HISTORY_PATH}`).map((call) => new URL(call.url, "http://apex.test").searchParams);
}

function Ficha() {
  return (
    <>
      <nav aria-label="Menú principal">
        <a href="/">Inicio</a>
      </nav>
      <main>
        <h1>Ficha</h1>
        <Outlet context={{ member: TAB_MEMBER } satisfies MemberTabContext} />
      </main>
    </>
  );
}

export interface RenderHistoryOptions {
  handlers?: Record<string, MockHandler>;
  queryClient?: QueryClient;
  /** La URL inicial (por defecto la pestaña del socio de prueba). */
  entry?: string;
}

/** Monta la pestaña Historial como hija de /socios/:id. */
export function renderMemberHistoryTab({ handlers = {}, queryClient = testQueryClient(), entry = `/socios/${MEMBER_ID}/historial` }: RenderHistoryOptions = {}) {
  const mock = mockApi({ [`GET ${HISTORY_PATH}`]: historyReply(historyItems()), ...handlers });
  const router = createMemoryRouter([{ path: "/socios/:id", element: <Ficha />, children: [{ path: "/socios/:id/historial", element: <MemberHistoryTab /> }] }], {
    initialEntries: [entry],
  });
  const view = render(
    <QueryClientProvider client={queryClient}>
      <SessionRoleProvider>
        <RouterProvider router={router} />
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, router, queryClient, user: userEvent.setup(), ...view };
}
