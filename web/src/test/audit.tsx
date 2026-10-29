// S4A-F1 (plan del Sprint 4A, sección 2, front): datos y montaje de prueba de /sistema/auditoria.
// Las filas imitan AuditRow de GET /audit, el detalle AuditDetail de GET /audit/{seq} y las
// verificaciones VerifyResultOut y VerifyStartedOut de POST /audit/verify (audit/schemas.py).
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import AuditPage from "../features/system/pages/AuditPage";
import { mockApi, testQueryClient, type MockHandler, type MockReply, type RecordedCall } from "./server";
import { ALL_ROWS, OWN_ID, pageReply } from "./users";

export const SYSTEM_ID = "00000000-0000-0000-0000-000000000001";
export const COACH_ID = "22222222-2222-4222-8222-222222222222";
export const LAURA_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
export const KEY_ID = "5f0c2a7e-1b3d-4c5e-8f9a-0b1c2d3e4f5a";
export const AUDIT_PATH = "/sistema/auditoria";

export interface AuditRowFixture {
  seq: number;
  at: string;
  user_id: string;
  user_email: string | null;
  user_name: string | null;
  action: "insert" | "update" | "delete" | "reveal" | "export" | "download" | "login" | "verify";
  table_name: string;
  record_id: string | null;
  subject_member_id: string | null;
}

export function auditRow(overrides: Partial<AuditRowFixture> = {}): AuditRowFixture {
  return {
    seq: 88412,
    at: "2026-10-20T16:52:08Z",
    user_id: OWN_ID,
    user_email: "admin@apex.test",
    user_name: "admin",
    action: "update",
    table_name: "members.members",
    record_id: LAURA_ID,
    subject_member_id: LAURA_ID,
    ...overrides,
  };
}

/** Una edición de Ana, un pago del coach y un cambio de estado del worker. */
export const AUDIT_ROWS: AuditRowFixture[] = [
  auditRow(),
  auditRow({ seq: 88411, at: "2026-10-20T19:10:00Z", user_id: COACH_ID, user_email: "carlos@apex.test", user_name: "carlos", action: "insert", table_name: "payments.payments", record_id: "99999999-9999-4999-8999-999999999999" }),
  auditRow({ seq: 88410, at: "2026-10-20T12:00:00Z", user_id: SYSTEM_ID, user_email: "system@apex.local", user_name: "system", table_name: "memberships.memberships", record_id: "66666666-6666-4666-8666-666666666666" }),
];

export const encryptedMarker = (keyId: string | null = KEY_ID) => ({ encrypted: true, key_id: keyId, alg: keyId === null ? null : "A256GCM" });

export function auditDetail(overrides: Record<string, unknown> = {}) {
  return {
    ...auditRow(),
    before: { phone: encryptedMarker(), notes: "Llamar en la tarde" },
    after: { phone: encryptedMarker(), notes: "Llamar en la mañana" },
    prev_hash: "a".repeat(64),
    hash: "b".repeat(64),
    changes: [
      { field: "phone", kind: "changed", before: encryptedMarker(), after: encryptedMarker(), encrypted: true },
      { field: "notes", kind: "changed", before: "Llamar en la tarde", after: "Llamar en la mañana", encrypted: false },
    ],
    ...overrides,
  };
}

export function verifyResult(overrides: Record<string, unknown> = {}) {
  return {
    ok: true,
    rows_checked: 3418,
    through_seq: 88412,
    broken_at_seq: null,
    started_at: "2026-10-21T15:00:00Z",
    finished_at: "2026-10-21T15:00:02Z",
    triggered_by: OWN_ID,
    source: "api",
    ...overrides,
  };
}

export function verifyStarted(last: Record<string, unknown> | null = verifyResult()) {
  return { status: "running", last };
}

/** La página de GET /audit con las filas, el limit y el offset pedidos. */
export function auditPageReply(call: RecordedCall, rows: AuditRowFixture[] = AUDIT_ROWS, total = rows.length): MockReply {
  const url = new URL(call.url, "http://apex.test");
  return { status: 200, body: { items: rows, total, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) } };
}

/** La URL de una llamada como URLSearchParams. */
export const queryOf = (call: RecordedCall | undefined): URLSearchParams => new URL(call?.url ?? "/", "http://apex.test").searchParams;

export interface RenderAuditOptions {
  handlers?: Record<string, MockHandler>;
  queryClient?: QueryClient;
}

/** Montaje de /sistema/auditoria con la lista, los usuarios, la última verificación y un detalle. */
export function renderAuditPage(entry = AUDIT_PATH, { handlers = {}, queryClient = testQueryClient() }: RenderAuditOptions = {}) {
  const mock = mockApi({
    "GET /audit": (call) => auditPageReply(call),
    "GET /users": (call) => pageReply(call, ALL_ROWS),
    "GET /audit/verify/last": { status: 200, body: verifyResult() },
    "GET /audit/88412": { status: 200, body: auditDetail() },
    ...handlers,
  });
  const router = createMemoryRouter(
    [
      {
        path: AUDIT_PATH,
        element: (
          <main>
            <AuditPage />
          </main>
        ),
      },
      { path: "/socios/:id", element: <h1>Ficha del socio</h1> },
    ],
    { initialEntries: [entry] },
  );
  const view = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { mock, router, queryClient, user: userEvent.setup(), ...view };
}
