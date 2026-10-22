// S2-F3 · US-044: "Cerrar sesión" de la TopBar en la app real (App + router + PanelShell).
// - Llama POST /auth/logout, deshabilita la opción mientras dura ("Cerrando sesión…").
// - Tras el 204 y tras un fallo (red o 5xx) la sesión queda limpia, se publica `logout` en
//   apex-auth, se vacía la caché y se navega a /login.
// - H-1: si el servidor no confirmó el cierre, /login lo dice; nunca se presenta como éxito.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../../App";
import { queryClient } from "../../core/api/queryClient";
import { getAccessToken, getSession, installSessionBridge } from "../../core/auth/session";
import { createAppRouter } from "../../routes";
import { installTabDoubles, posted, resetTabDoubles } from "../../test/authChannel";
import { mockApi, type MockHandler, type MockReply } from "../../test/server";
import { signInAs, signOutForTests } from "../../test/session";

let uninstall: (() => void) | null = null;

function renderPanel(handler: MockHandler) {
  installTabDoubles();
  uninstall = installSessionBridge();
  const mock = mockApi({ "POST /auth/logout": handler });
  signInAs("admin", { gymName: "Box Norte" });
  queryClient.setQueryData(["socios"], { items: ["ana"] });
  const router = createAppRouter({ initialEntries: ["/"] });
  render(<App router={router} />);
  return { mock, router, user: userEvent.setup() };
}

async function openUserMenu(user: ReturnType<typeof userEvent.setup>): Promise<HTMLElement> {
  await user.click(await screen.findByRole("button", { name: /admin@apex\.test/ }));
  return screen.getByRole("menu", { name: "Menú de usuario" });
}

afterEach(() => {
  uninstall?.();
  uninstall = null;
  signOutForTests();
  resetTabDoubles();
  queryClient.clear();
  vi.unstubAllGlobals();
  delete document.documentElement.dataset.theme;
});

describe("TopBar · Cerrar sesión", () => {
  it("tras el 204: sesión limpia, mensaje publicado, caché vacía y /login sin aviso", async () => {
    const { mock, router, user } = renderPanel({ status: 204 });
    expect(await screen.findByRole("heading", { level: 1, name: /Hola/ })).toBeInTheDocument();

    const menu = await openUserMenu(user);
    await user.click(within(menu).getByRole("menuitem", { name: "Cerrar sesión" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Iniciar sesión" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(router.state.location.search).toBe("");
    expect(mock.callsTo("POST /auth/logout")).toHaveLength(1);
    expect(getSession()).toMatchObject({ status: "anonymous", reason: "logout" });
    expect(getAccessToken()).toBeNull();
    expect(queryClient.getQueryData(["socios"])).toBeUndefined();
    expect(posted.map((m) => (m.data as { type: string }).type)).toEqual(["logout"]);
    expect(screen.queryByText(/No se pudo cerrar la sesión/)).toBeNull();
  });

  it("mientras dura la petición la opción dice 'Cerrando sesión…' y no repite el POST", async () => {
    let release: (reply: MockReply) => void = () => undefined;
    const { mock, user } = renderPanel(
      () =>
        new Promise<MockReply>((resolve) => {
          release = resolve;
        }),
    );
    await screen.findByRole("heading", { level: 1, name: /Hola/ });

    await user.click(within(await openUserMenu(user)).getByRole("menuitem", { name: "Cerrar sesión" }));
    const pendingItem = within(await openUserMenu(user)).getByRole("menuitem", { name: "Cerrando sesión…" });
    expect(pendingItem).toHaveAttribute("aria-disabled", "true");
    await user.click(pendingItem);
    expect(mock.callsTo("POST /auth/logout")).toHaveLength(1);

    release({ status: 204 });
    expect(await screen.findByRole("heading", { level: 1, name: "Iniciar sesión" })).toBeInTheDocument();
  });

  it.each<[string, MockHandler]>([
    ["sin red", () => Promise.reject(new TypeError("Failed to fetch"))],
    ["con un 500", { status: 500, body: { error: { code: "internal_error", message: "boom" } } }],
    ["con un 502 de Nginx", { status: 502, body: "<html>" }],
  ])("H-1 %s: limpia, publica y va a /login con el aviso de cierre no confirmado", async (_caso, handler) => {
    const { router, user } = renderPanel(handler);
    await screen.findByRole("heading", { level: 1, name: /Hola/ });

    await user.click(within(await openUserMenu(user)).getByRole("menuitem", { name: "Cerrar sesión" }));

    expect(await screen.findByRole("heading", { level: 1, name: "Iniciar sesión" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(screen.getByRole("status")).toHaveTextContent("No se pudo cerrar la sesión en el servidor.");
    expect(getSession()).toMatchObject({ status: "anonymous", reason: "logout_unconfirmed" });
    expect(getAccessToken()).toBeNull();
    expect(queryClient.getQueryData(["socios"])).toBeUndefined();
    expect(posted.map((m) => (m.data as { type: string }).type)).toEqual(["logout"]);
  });
});
