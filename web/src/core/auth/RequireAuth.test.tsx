// US-053 T4 y T7: sin sesión se va a /login?next=<ruta>; al recargar se restaura una sola
// vez (un refresh y un me); con must_change_password se va a /cambiar-clave (S2-D18).
import { act, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { mockApi } from "../../test/server";
import { signInAs, signOutForTests } from "../../test/session";
import { RequireAuth } from "./RequireAuth";
import { clearSession } from "./session";

const ME = {
  id: "11111111-1111-4111-8111-111111111111",
  email: "coach@apex.test",
  role: "coach",
  member_id: null,
  gym_name: "Box Norte",
  must_change_password: false,
};
const REFRESH = { access_token: "nuevo-access", token_type: "bearer", expires_in: 900 };

function setup(path: string) {
  const router = createMemoryRouter(
    [
      { path: "/login", element: <h1>Pantalla de login</h1> },
      {
        element: <RequireAuth />,
        children: [
          { path: "/socios", element: <h1>Socios</h1> },
          { path: "/cambiar-clave", element: <h1>Cambiar contraseña</h1> },
        ],
      },
    ],
    { initialEntries: [path] },
  );
  render(
    <StrictMode>
      <RouterProvider router={router} />
    </StrictMode>,
  );
  return router;
}

afterEach(() => {
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("RequireAuth", () => {
  it("con sesión muestra la ruta sin pedir nada al api", () => {
    const api = mockApi({});
    signInAs("coach");
    setup("/socios");

    expect(screen.getByRole("heading", { name: "Socios" })).toBeInTheDocument();
    expect(api.calls).toHaveLength(0);
  });

  it("al recargar restaura con un refresh y un me (también en StrictMode) y muestra la ruta", async () => {
    const api = mockApi({ "POST /auth/refresh": { status: 200, body: REFRESH }, "GET /auth/me": { status: 200, body: ME } });
    setup("/socios");

    expect(screen.getByRole("status")).toHaveTextContent("Cargando");
    expect(await screen.findByRole("heading", { name: "Socios" })).toBeInTheDocument();
    expect(api.callsTo("POST /auth/refresh")).toHaveLength(1);
    expect(api.callsTo("GET /auth/me")).toHaveLength(1);
  });

  it("sin sesión en /socios lleva a /login?next=/socios conservando la query", async () => {
    mockApi({ "POST /auth/refresh": { status: 401, body: { error: { code: "invalid_refresh", message: "x" } } } });
    const router = setup("/socios?status=deleted");

    expect(await screen.findByRole("heading", { name: "Pantalla de login" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
    expect(new URLSearchParams(router.state.location.search).get("next")).toBe("/socios?status=deleted");
  });

  it("tras un cierre de sesión no vuelve a restaurar: va directo a /login", async () => {
    const api = mockApi({});
    signInAs("coach");
    signOutForTests();
    const { clearSession } = await import("./session");
    clearSession("logout");
    setup("/socios");

    expect(await screen.findByRole("heading", { name: "Pantalla de login" })).toBeInTheDocument();
    expect(api.calls).toHaveLength(0);
  });

  it("con must_change_password va a /cambiar-clave y deja entrar ahí", async () => {
    signInAs("admin", { mustChangePassword: true });
    const router = setup("/socios");

    expect(await screen.findByRole("heading", { name: "Cambiar contraseña" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/cambiar-clave");
  });
});

describe("RequireAuth tras cerrar la sesión (S2-F3)", () => {
  it.each(["logout", "logout_unconfirmed"] as const)("con la razón %s va a /login sin next", async (reason) => {
    signInAs("coach");
    const router = setup("/socios");
    expect(screen.getByRole("heading", { name: "Socios" })).toBeInTheDocument();

    act(() => {
      clearSession(reason);
    });

    expect(await screen.findByRole("heading", { name: "Pantalla de login" })).toBeInTheDocument();
    expect(`${router.state.location.pathname}${router.state.location.search}`).toBe("/login");
  });

  it("con la sesión vencida conserva next para volver", async () => {
    signInAs("coach");
    const router = setup("/socios?estado=activo");

    act(() => {
      clearSession("expired");
    });

    expect(await screen.findByRole("heading", { name: "Pantalla de login" })).toBeInTheDocument();
    expect(router.state.location.search).toBe(`?next=${encodeURIComponent("/socios?estado=activo")}`);
  });
});
