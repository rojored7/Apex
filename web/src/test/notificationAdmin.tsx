// S5-F2: datos y montaje de prueba de /avisos/reglas y /avisos/historial. Las filas imitan RuleOut,
// TemplateOut y NotificationOut de B6 y B7. El montaje usa un router de datos con la ruta dentro de
// nav y main, igual que PanelShell, y la sesión por SessionRoleProvider (signInAs).
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { SessionRoleProvider } from "../core/auth";
import HistoryPage from "../features/notifications/pages/HistoryPage";
import RulesPage from "../features/notifications/pages/RulesPage";
import { NOTIFICATIONS, apiError } from "./notifications";
import { mockApi, testQueryClient, type MockHandler, type MockReply, type RecordedCall } from "./server";

export { apiError };

export const TEMPLATE_IDS = { porVencer: "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa", vencido: "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb" } as const;
export const RULE_IDS = { porVencer: "cccccccc-1111-4111-8111-cccccccccccc", venceHoy: "dddddddd-2222-4222-8222-dddddddddddd", vencido: "eeeeeeee-3333-4333-8333-eeeeeeeeeeee" } as const;

export interface TemplateFixture {
  id: string;
  name: string;
  subject: string;
  body: string;
  created_at: string;
  updated_at: string;
}

export interface RuleFixture {
  id: string;
  name: string;
  trigger: "membership_expiring" | "membership_expired";
  offset_days: number;
  channel: "email" | "whatsapp_link";
  template_id: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

const STAMP = "2026-10-20T15:00:00Z";

export const TEMPLATES: Record<"porVencer" | "vencido", TemplateFixture> = {
  porVencer: { id: TEMPLATE_IDS.porVencer, name: "por_vencer", subject: "Tu plan vence pronto", body: "Hola {nombre}, tu plan {plan} vence el {vence}.", created_at: STAMP, updated_at: "2026-10-22T15:00:00Z" },
  vencido: { id: TEMPLATE_IDS.vencido, name: "vencido", subject: "Tu plan venció", body: "Hola {nombre}, tu plan {plan} venció hace {dias} días.", created_at: STAMP, updated_at: STAMP },
};

export const RULES: Record<"porVencer" | "venceHoy" | "vencido", RuleFixture> = {
  porVencer: { id: RULE_IDS.porVencer, name: "Por vencer", trigger: "membership_expiring", offset_days: -3, channel: "email", template_id: TEMPLATE_IDS.porVencer, is_active: true, created_at: STAMP, updated_at: STAMP },
  venceHoy: { id: RULE_IDS.venceHoy, name: "Vence hoy", trigger: "membership_expiring", offset_days: 0, channel: "whatsapp_link", template_id: TEMPLATE_IDS.porVencer, is_active: true, created_at: STAMP, updated_at: STAMP },
  vencido: { id: RULE_IDS.vencido, name: "Vencido", trigger: "membership_expired", offset_days: 1, channel: "whatsapp_link", template_id: TEMPLATE_IDS.vencido, is_active: false, created_at: STAMP, updated_at: STAMP },
};

export const RULE_ROWS: RuleFixture[] = [RULES.porVencer, RULES.venceHoy, RULES.vencido];
export const TEMPLATE_ROWS: TemplateFixture[] = [TEMPLATES.porVencer, TEMPLATES.vencido];

export function pageOf(call: RecordedCall, rows: readonly unknown[], total = rows.length): MockReply {
  const url = new URL(call.url, "http://apex.test");
  return { status: 200, body: { items: rows, total, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) } };
}

/** Una fila del historial: NotificationOut con otro estado. */
export const HISTORY_ROWS = [
  { ...NOTIFICATIONS.juan, rule_id: RULE_IDS.venceHoy, status: "sent", sent_at: "2026-10-20T13:12:00Z", sent_by: "11111111-1111-4111-8111-111111111111" },
  { ...NOTIFICATIONS.laura, rule_id: RULE_IDS.porVencer, status: "sent", sent_at: "2026-10-20T12:00:00Z", sent_by: null },
  { ...NOTIFICATIONS.andres, rule_id: RULE_IDS.porVencer, status: "failed", last_error: "timeout" },
  { ...NOTIFICATIONS.camila, rule_id: RULE_IDS.vencido, status: "skipped", skip_reason: "pidió no contactar", sent_by: null },
];

export function defaultHandlers(): Record<string, MockHandler> {
  return {
    "GET /notification-rules": (call) => pageOf(call, RULE_ROWS),
    "GET /notification-templates": (call) => pageOf(call, TEMPLATE_ROWS),
    "GET /notifications": (call) => pageOf(call, HISTORY_ROWS),
    "POST /notification-rules": (call) => ({ status: 201, body: { ...RULES.porVencer, id: "ffffffff-4444-4444-8444-ffffffffffff", ...(call.body as object) } }),
    "POST /notification-templates": (call) => ({ status: 201, body: { ...TEMPLATES.porVencer, id: "ffffffff-5555-4555-8555-ffffffffffff", ...(call.body as object) } }),
  };
}

export interface RenderAdminOptions {
  handlers?: Record<string, MockHandler>;
  queryClient?: QueryClient;
}

function mount(path: string, element: React.ReactNode, entry: string, { handlers = {}, queryClient = testQueryClient() }: RenderAdminOptions) {
  const mock = mockApi({ ...defaultHandlers(), ...handlers });
  const router = createMemoryRouter(
    [
      {
        path,
        element: (
          <>
            <nav aria-label="Menú principal">
              <a href="/">Inicio</a>
            </nav>
            <main>{element}</main>
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

export const renderRules = (entry = "/avisos/reglas", options: RenderAdminOptions = {}) => mount("/avisos/reglas", <RulesPage />, entry, options);
export const renderHistory = (entry = "/avisos/historial", options: RenderAdminOptions = {}) => mount("/avisos/historial", <HistoryPage />, entry, options);

/** Parámetros de cada GET a `key` ("GET /notification-rules"), en orden. */
export function callsOf(mock: { callsTo: (key: string) => RecordedCall[] }, key: string): URLSearchParams[] {
  return mock.callsTo(key).map((c) => new URL(c.url, "http://apex.test").searchParams);
}
