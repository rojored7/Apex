// S3-F4: montaje de prueba del panel "Registrar pago" abierto por la URL (?pago=), como lo monta
// PanelShell: una pantalla cualquiera y RegisterPaymentPanelHost al lado, en un router de datos con
// la sesión por SessionRoleProvider (signInAs). Datos por defecto: Laura con una membresía Mensual
// pendiente de pago (precio 120.000, pagado 60.000) y los tres medios.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { SessionRoleProvider } from "../core/auth";
import { RegisterPaymentPanelHost } from "../features/payments/components/RegisterPaymentPanelHost";
import { MEMBERS, memberPage } from "./members";
import { MEMBERSHIP_ID, membershipOut, membershipRow, membershipRowsPage } from "./memberships";
import { paymentMethods, paymentOut } from "./payments";
import { mockApi, testQueryClient, type MockHandler, type RecordedCall } from "./server";

/** "Ahora" de las pruebas del panel: 28 oct 2026, 10:00 a. m. en Bogotá. */
export const PAYMENT_NOW = new Date("2026-10-28T15:00:00Z");

export const registerKey = (membershipId: string = MEMBERSHIP_ID): string => `POST /memberships/${membershipId}/payments`;
export const voidKey = (paymentId: string): string => `POST /payments/${paymentId}/void`;

export interface RenderPaymentPanelOptions {
  handlers?: Record<string, MockHandler>;
  queryClient?: QueryClient;
  /** Estado de la navegación de entrada (la precarga desde una anulación). */
  state?: unknown;
}

export function defaultPaymentHandlers(): Record<string, MockHandler> {
  return {
    "GET /payments/methods": paymentMethods(),
    "GET /members": (call) => memberPage(call, [MEMBERS.laura]),
    "GET /memberships": membershipRowsPage([membershipRow()]),
    [`GET /memberships/${MEMBERSHIP_ID}`]: {
      status: 200,
      body: membershipOut({ status: "pending_payment", start_date: "2026-10-25", end_date: "2026-11-24", paid_cop: 60_000 }),
    },
    [registerKey()]: { status: 201, body: paymentOut({ amount_cop: 60_000 }) },
  };
}

export function renderPaymentPanel(entry: string, options: RenderPaymentPanelOptions = {}) {
  const { handlers = {}, queryClient = testQueryClient(), state } = options;
  const mock = mockApi({ ...defaultPaymentHandlers(), ...handlers });
  const [pathname = entry, query] = entry.split("?");
  const router = createMemoryRouter(
    [
      {
        path: "*",
        element: (
          <>
            <main>
              <h1>Pantalla</h1>
            </main>
            <RegisterPaymentPanelHost />
          </>
        ),
      },
    ],
    { initialEntries: [{ pathname, search: query ? `?${query}` : "", state }] },
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

/** Cuerpos de cada POST de registro de pago, en orden. */
export function registerBodies(mock: { callsTo: (key: string) => RecordedCall[] }, membershipId: string = MEMBERSHIP_ID): Record<string, unknown>[] {
  return mock.callsTo(registerKey(membershipId)).map((c) => c.body as Record<string, unknown>);
}

export const paymentPanel = (): HTMLElement => screen.getByRole("dialog", { name: "Registrar pago" });
export const findPaymentPanel = (): Promise<HTMLElement> => screen.findByRole("dialog", { name: "Registrar pago" });
export const membershipSelect = (): HTMLElement => within(paymentPanel()).getByRole("combobox", { name: /^Membresía/ });
export const panelAmount = (): HTMLElement => within(paymentPanel()).getByRole("textbox", { name: /^Valor recibido/ });
export const panelReference = (): HTMLElement | null => within(paymentPanel()).queryByRole("textbox", { name: /^Referencia/ });
export const panelPaidAt = (): HTMLElement => within(paymentPanel()).getByLabelText(/^Fecha y hora del pago/);
export const panelSubmit = (): HTMLElement => within(paymentPanel()).getByRole("button", { name: "Registrar" });
