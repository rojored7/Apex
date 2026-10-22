// S2-F2: la app monta QueryClientProvider, SessionRoleProvider y RouterProvider. Sin sesión
// "/" termina en /login; con sesión restaurada, en Inicio dentro del panel.
import { render, screen, within } from "@testing-library/react";
import { App } from "./App";
import { createAppRouter } from "./routes";
import { mockApi } from "./test/server";
import { signOutForTests } from "./test/session";

const ME = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "ana@apex.test",
  role: "admin",
  member_id: null,
  gym_name: "Box Norte",
  must_change_password: false,
};

afterEach(() => {
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("App", () => {
  it("sin sesión, / lleva a /login con next", async () => {
    mockApi({ "POST /auth/refresh": { status: 401, body: { error: { code: "invalid_refresh", message: "x" } } } });
    const router = createAppRouter({ initialEntries: ["/"] });
    render(<App router={router} />);

    expect(await screen.findByRole("heading", { level: 1, name: "Iniciar sesión" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(new URLSearchParams(router.state.location.search).get("next")).toBe("/");
  });

  it("con la cookie de refresh vigente, / muestra Inicio en el panel con el gimnasio", async () => {
    mockApi({
      "POST /auth/refresh": { status: 200, body: { access_token: "a", token_type: "bearer", expires_in: 900 } },
      "GET /auth/me": { status: 200, body: ME },
    });
    render(<App router={createAppRouter({ initialEntries: ["/"] })} />);

    expect(await screen.findByRole("heading", { level: 1, name: "Hola, ana@apex.test" })).toBeInTheDocument();
    expect(screen.getByText("Box Norte")).toBeInTheDocument();
    expect(within(screen.getByRole("navigation", { name: "Menú principal" })).getByRole("link", { name: "Configuración" })).toBeInTheDocument();
  });

  it("sin router explícito crea el del navegador", async () => {
    mockApi({ "POST /auth/refresh": { status: 401, body: { error: { code: "invalid_refresh", message: "x" } } } });
    render(<App />);

    expect(await screen.findByRole("heading", { level: 1, name: "Iniciar sesión" })).toBeInTheDocument();
  });
});
