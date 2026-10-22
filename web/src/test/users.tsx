// S2-F4b: datos y montaje de prueba de /sistema/usuarios (lista, acciones por fila, panel de
// edición y reenvío del enlace). Las filas imitan UserRow de GET /users y las cuentas, UserOut
// de GET /users/{id}. La sesión es la de signInAs("admin"): su id es OWN_ID, el de la primera fila.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import UsersPage from "../features/system/pages/UsersPage";
import { mockApi, testQueryClient, type MockHandler, type MockReply, type RecordedCall } from "./server";
import { testUser } from "./session";

export interface UserRowFixture {
  id: string;
  email: string;
  role: "admin" | "coach" | "member";
  status: "active" | "pending_activation" | "locked" | "inactive" | "deleted";
  member_id: string | null;
  last_login_at: string | null;
  created_at: string;
  active_sessions: number;
}

export const OWN_ID = testUser("admin").id;

const row = (id: string, email: string, overrides: Partial<UserRowFixture> = {}): UserRowFixture => ({
  id,
  email,
  role: "coach",
  status: "active",
  member_id: null,
  last_login_at: "2026-10-21T19:30:00Z",
  created_at: "2026-10-01T12:00:00Z",
  active_sessions: 0,
  ...overrides,
});

/** La propia cuenta, otro admin activo, un coach activo, uno pendiente, uno bloqueado y uno dado de baja. */
export const USERS = {
  own: row(OWN_ID, "admin@apex.test", { role: "admin", active_sessions: 2 }),
  admin: row("66666666-6666-4666-8666-666666666666", "otra-admin@apex.test", { role: "admin", active_sessions: 1 }),
  coach: row("22222222-2222-4222-8222-222222222222", "carlos@apex.test", { active_sessions: 3 }),
  pending: row("44444444-4444-4444-8444-444444444444", "nuevo@apex.test", { status: "pending_activation", last_login_at: null }),
  pendingAdmin: row("77777777-7777-4777-8777-777777777777", "admin-nueva@apex.test", { role: "admin", status: "pending_activation", last_login_at: null }),
  locked: row("33333333-3333-4333-8333-333333333333", "luis@apex.test", { status: "locked" }),
  deleted: row("55555555-5555-4555-8555-555555555555", "ex@apex.test", { status: "deleted" }),
} as const satisfies Record<string, UserRowFixture>;

export const ALL_ROWS: UserRowFixture[] = Object.values(USERS);

export function pageReply(call: RecordedCall, rows: UserRowFixture[] = ALL_ROWS): MockReply {
  const url = new URL(call.url, "http://apex.test");
  return { status: 200, body: { items: rows, total: rows.length, limit: Number(url.searchParams.get("limit")), offset: Number(url.searchParams.get("offset")) } };
}

/** UserOut de una fila (lo que responden GET, PATCH, lock y unlock). */
export function userOut(fixture: UserRowFixture, overrides: Partial<UserRowFixture> = {}) {
  const merged = { ...fixture, ...overrides };
  return { id: merged.id, email: merged.email, role: merged.role, status: merged.status, member_id: merged.member_id, must_change_password: false };
}

export const apiError = (status: number, code: string, message = "Mensaje del api.", extra: Record<string, unknown> = {}): MockReply => ({
  status,
  body: { error: { code, message, ...extra } },
});

/** GET /users/{id} de todas las filas de prueba. */
export function detailHandlers(rows: UserRowFixture[] = ALL_ROWS): Record<string, MockHandler> {
  return Object.fromEntries(rows.map((r) => [`GET /users/${r.id}`, { status: 200, body: userOut(r) }]));
}

export interface RenderUsersOptions {
  handlers?: Record<string, MockHandler>;
  rows?: UserRowFixture[];
  queryClient?: QueryClient;
}

export function renderUsersPage(entry = "/sistema/usuarios", { handlers = {}, rows = ALL_ROWS, queryClient = testQueryClient() }: RenderUsersOptions = {}) {
  const mock = mockApi({ "GET /users": (call) => pageReply(call, rows), ...detailHandlers(rows), ...handlers });
  const router = createMemoryRouter(
    [
      {
        path: "/sistema/usuarios",
        element: (
          <main>
            <UsersPage />
          </main>
        ),
      },
      { path: "/login", element: <h1>Iniciar sesión</h1> },
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

/** La fila de la tabla (escritorio) de una cuenta, por su correo. */
export async function findRow(email: string): Promise<HTMLElement> {
  const link = await screen.findByRole("link", { name: email });
  const tr = link.closest("tr");
  if (!tr) throw new Error(`sin fila para ${email}`);
  return tr;
}
