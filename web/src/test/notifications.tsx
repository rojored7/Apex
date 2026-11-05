// S5-F1: datos y montaje de prueba de /avisos/hoy. Las filas imitan NotificationOut de B7
// (GET /notifications/today, POST /notifications/{id}/skip). El montaje usa un router de datos con
// /avisos/hoy dentro de nav y main, igual que PanelShell, y la sesión por SessionRoleProvider.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { SessionRoleProvider } from "../core/auth";
import TodayPage from "../features/notifications/pages/TodayPage";
import { mockApi, testQueryClient, type MockHandler, type MockReply, type RecordedCall } from "./server";

export interface NotificationFixture {
  id: string;
  rule_id: string;
  member_id: string;
  member_name: string;
  membership_id: string;
  target_date: string;
  channel: "email" | "whatsapp_link";
  status: "pending" | "sent" | "failed" | "skipped";
  rendered_subject: string;
  rendered_body: string;
  attempts: number;
  last_error: string | null;
  sent_at: string | null;
  sent_by: string | null;
  skip_reason: string | null;
  created_at: string;
  updated_at: string;
}

const RULE_ID = "aaaaaaaa-0000-4000-8000-000000000001";

const notification = (n: number, overrides: Partial<NotificationFixture>): NotificationFixture => ({
  id: `0000000${String(n)}-1111-4111-8111-111111111111`,
  rule_id: RULE_ID,
  member_id: `0000000${String(n)}-2222-4222-8222-222222222222`,
  member_name: "Socio de prueba",
  membership_id: `0000000${String(n)}-3333-4333-8333-333333333333`,
  target_date: "2026-10-20",
  channel: "whatsapp_link",
  status: "pending",
  rendered_subject: "Tu plan vence hoy",
  rendered_body: "Hola, tu plan vence hoy.",
  attempts: 0,
  last_error: null,
  sent_at: null,
  sent_by: null,
  skip_reason: null,
  created_at: "2026-10-20T12:00:00Z",
  updated_at: "2026-10-20T12:00:00Z",
  ...overrides,
});

export const NOTIFICATIONS = {
  juan: notification(1, {
    member_name: "Juan Pérez",
    rendered_subject: "Tu plan Trimestral vence hoy",
    rendered_body: "Hola Juan, tu plan Trimestral en APEX vence hoy, 20 de octubre. Renuévalo en el box.",
  }),
  camila: notification(2, {
    member_name: "Camila Torres",
    target_date: "2026-10-15",
    rendered_subject: "Tu plan Mensual venció",
    rendered_body: "Hola Camila, tu plan Mensual venció el 15 de octubre. Te extrañamos en el box.",
  }),
  andres: notification(3, {
    member_name: "Andrés Ruiz",
    channel: "email",
    status: "failed",
    attempts: 3,
    last_error: "timeout",
    rendered_subject: "Te quedan 2 clases",
    rendered_body: "Hola Andrés, te quedan 2 clases de tu plan de 12.",
  }),
  laura: notification(4, {
    member_name: "Laura Gómez",
    channel: "email",
    rendered_subject: "Tu plan vence en 8 días",
    rendered_body: "Hola Laura, tu plan Mensual vence el 28 de octubre.",
  }),
} as const satisfies Record<string, NotificationFixture>;

export const TODAY_ROWS: NotificationFixture[] = [NOTIFICATIONS.juan, NOTIFICATIONS.camila, NOTIFICATIONS.andres, NOTIFICATIONS.laura];

/** La URL que devuelve el api: el teléfono (ficticio) solo vive aquí. */
export const WA_URL = "https://wa.me/573201234567?text=Hola%20Juan";

export const apiError = (status: number, code: string, extra: Record<string, unknown> = {}, headers?: Record<string, string>, message = "Mensaje del api."): MockReply => ({
  status,
  body: { error: { code, message, ...extra } },
  ...(headers ? { headers } : {}),
});

export function todayPage(call: RecordedCall, rows: NotificationFixture[] = TODAY_ROWS, total = rows.length): MockReply {
  const url = new URL(call.url, "http://apex.test");
  return { status: 200, body: { items: rows, total, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) } };
}

/** Parámetros de cada GET /notifications/today, en orden. */
export function todayCalls(mock: { callsTo: (key: string) => RecordedCall[] }): URLSearchParams[] {
  return mock.callsTo("GET /notifications/today").map((c) => new URL(c.url, "http://apex.test").searchParams);
}

export interface RenderTodayOptions {
  handlers?: Record<string, MockHandler>;
  rows?: NotificationFixture[];
  total?: number;
  queryClient?: QueryClient;
}

export function renderToday(entry = "/avisos/hoy", { handlers = {}, rows = TODAY_ROWS, total, queryClient = testQueryClient() }: RenderTodayOptions = {}) {
  const mock = mockApi({ "GET /notifications/today": (call) => todayPage(call, rows, total), ...handlers });
  const router = createMemoryRouter(
    [
      {
        path: "/avisos/hoy",
        element: (
          <>
            <nav aria-label="Menú principal">
              <a href="/">Inicio</a>
            </nav>
            <main>
              <TodayPage />
            </main>
          </>
        ),
      },
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
