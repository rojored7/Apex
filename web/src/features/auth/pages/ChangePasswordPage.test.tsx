// S2-F4a · US-045 y S2-D18 (front): /cambiar-clave, con sesión y cualquier rol. Toda ruta con
// sesión lleva aquí mientras must_change_password sea verdadero (RequireAuth); al terminar va
// al inicio del rol (homeFor). Usa el router real de la app con una tabla de prueba.
import { QueryClientProvider } from "@tanstack/react-query";
import { screen, render, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RouterProvider } from "react-router";
import { axe } from "vitest-axe";
import { ENABLED_FEATURES, type Feature } from "../../../config/features";
import type { RouteDef } from "../../../config/routeTable";
import { getAccessToken, getSession } from "../../../core/auth/session";
import { SessionRoleProvider } from "../../../core/auth/SessionRole";
import { createAppRouter } from "../../../routes";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";

const CURRENT = "Clave-inicial-2026";
const NEXT = "Clave-nueva-segura-2026";

const page = (text: string) => async () => Promise.resolve({ default: () => <h1>{text}</h1> });

const TABLE: RouteDef[] = [
  { path: "/login", title: "Iniciar sesión", feature: "auth", access: "public", layout: "access", load: page("Pantalla de login") },
  { path: "/cambiar-clave", title: "Cambiar contraseña", feature: "auth", access: "session", layout: "access", load: () => import("./ChangePasswordPage") },
  { path: "/", title: "Inicio", feature: "dashboard", access: "dashboard.view", layout: "panel", load: page("Inicio del panel") },
  { path: "/socios", title: "Socios", feature: "members", access: "members.view", layout: "panel", load: page("Lista de socios") },
  { path: "/mi", title: "Inicio", feature: "portal", access: "me.home.view", layout: "portal", load: page("Portal del socio") },
];

const ENABLED = new Set<Feature>([...ENABLED_FEATURES, "portal"]);

function renderAt(path: string, handlers: Record<string, MockHandler> = {}) {
  const mock = mockApi({
    "POST /auth/me/password": { status: 200, body: { access_token: "access-nuevo", token_type: "bearer", expires_in: 900 } },
    "POST /auth/logout": { status: 204 },
    ...handlers,
  });
  const router = createAppRouter({ table: TABLE, enabled: ENABLED, initialEntries: [path] });
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <SessionRoleProvider>
        <RouterProvider router={router} />
      </SessionRoleProvider>
    </QueryClientProvider>,
  );
  return { mock, router, user: userEvent.setup(), ...view };
}

const currentBox = () => screen.getByLabelText(/^Contraseña actual/);
const newBox = () => screen.getByLabelText(/^Contraseña nueva/);
const confirmBox = () => screen.getByLabelText(/^Repite la contraseña nueva/);

async function fillAndSave(user: ReturnType<typeof userEvent.setup>): Promise<void> {
  await user.type(currentBox(), CURRENT);
  await user.type(newBox(), NEXT);
  await user.type(confirmBox(), NEXT);
  await user.click(screen.getByRole("button", { name: "Cambiar contraseña" }));
}

afterEach(() => {
  signOutForTests();
  vi.unstubAllGlobals();
  delete document.documentElement.dataset.theme;
});

describe("ChangePasswordPage · contraseña obligatoria (S2-D18)", () => {
  it("con must_change_password, una ruta del panel lleva a /cambiar-clave con el aviso", async () => {
    signInAs("admin", { mustChangePassword: true });
    const { router, container } = renderAt("/socios");

    expect(await screen.findByRole("heading", { level: 1, name: "Cambia tu contraseña" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/cambiar-clave");
    expect(screen.getByText("Antes de seguir, cambia la contraseña inicial de tu cuenta.")).toBeInTheDocument();
    expect(screen.getByText("admin@apex.test")).toBeInTheDocument();
    expect(currentBox()).toHaveFocus();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("al terminar toma el access nuevo, deja must_change_password en falso y va al inicio del admin", async () => {
    signInAs("admin", { mustChangePassword: true });
    const { mock, router, user } = renderAt("/socios");
    await screen.findByRole("heading", { name: "Cambia tu contraseña" });

    await fillAndSave(user);

    expect(await screen.findByRole("heading", { name: "Inicio del panel" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/");
    expect(getSession().user?.mustChangePassword).toBe(false);
    expect(getAccessToken()).toBe("access-nuevo");
    expect(mock.callsTo("POST /auth/me/password")[0]?.body).toEqual({ current_password: CURRENT, new_password: NEXT });
  });

  it("un coach termina en / y un socio en /mi", async () => {
    signInAs("member", { mustChangePassword: true });
    const { user } = renderAt("/cambiar-clave");
    await screen.findByRole("heading", { name: "Cambia tu contraseña" });

    await fillAndSave(user);

    expect(await screen.findByRole("heading", { name: "Portal del socio" })).toBeInTheDocument();
  });

  it("422 current_password queda bajo su campo y no navega", async () => {
    signInAs("coach", { mustChangePassword: true });
    const { router, user } = renderAt("/cambiar-clave", {
      "POST /auth/me/password": { status: 422, body: { error: { code: "invalid_current_password", message: "x", field: "current_password" } } },
    });
    await screen.findByRole("heading", { name: "Cambia tu contraseña" });

    await fillAndSave(user);

    expect(await screen.findByText("La contraseña actual no es correcta. Revísala e intenta de nuevo.")).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/cambiar-clave");
    expect(getSession().user?.mustChangePassword).toBe(true);
  });
});

describe("ChangePasswordPage · sin obligación", () => {
  it("sin must_change_password se puede usar igual, sin el aviso", async () => {
    signInAs("coach");
    const { user } = renderAt("/cambiar-clave");
    await screen.findByRole("heading", { name: "Cambia tu contraseña" });

    expect(screen.queryByText("Antes de seguir, cambia la contraseña inicial de tu cuenta.")).not.toBeInTheDocument();
    await fillAndSave(user);
    expect(await screen.findByRole("heading", { name: "Inicio del panel" })).toBeInTheDocument();
  });

  it("'Cerrar sesión' cierra la sesión y lleva al login", async () => {
    signInAs("admin", { mustChangePassword: true });
    const { mock, user } = renderAt("/cambiar-clave");
    await screen.findByRole("heading", { name: "Cambia tu contraseña" });

    await user.click(screen.getByRole("button", { name: "Cerrar sesión" }));

    expect(await screen.findByRole("heading", { name: "Pantalla de login" })).toBeInTheDocument();
    await waitFor(() => {
      expect(mock.callsTo("POST /auth/logout")).toHaveLength(1);
    });
    expect(getSession().status).toBe("anonymous");
  });
});
