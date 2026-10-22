// S2-F2: contenedores que leen la sesión y entregan sus datos a los layouts presentacionales
// (PanelShell, PortalShell, TvShell) y el marco de las pantallas de acceso.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { resetThemeForTests } from "../core/theme/theme";
import { mockApi, testQueryClient } from "../test/server";
import { signInAs, signOutForTests } from "../test/session";
import { AccessLayout } from "./AccessLayout";
import { PanelShell } from "./PanelShell";
import { GymShell, PortalShell, TvShell } from "./ZoneShells";

afterEach(() => {
  signOutForTests();
  vi.unstubAllGlobals();
  delete document.documentElement.dataset.theme;
});

function inRouter(element: ReactNode, path = "/") {
  const router = createMemoryRouter([{ element, children: [{ path: "*", element: <h1>Contenido</h1>, handle: { title: "Check-in" } }] }], {
    initialEntries: [path],
  });
  // S2-F4a: PanelShell monta el panel "Mi cuenta", que usa TanStack Query.
  return render(
    <QueryClientProvider client={testQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("PanelShell", () => {
  it("lleva a la TopBar el correo, la etiqueta del rol y el gimnasio de la sesión", () => {
    signInAs("admin", { gymName: "Box Norte" });
    inRouter(<PanelShell />);

    const banner = screen.getByRole("banner");
    expect(banner).toHaveTextContent("admin@apex.test · Admin");
    expect(banner).toHaveTextContent("Box Norte");
    expect(within(screen.getByRole("main")).getByRole("heading", { name: "Contenido" })).toBeInTheDocument();
  });

  it("arma el menú con el rol de la sesión y las features del sprint", () => {
    signInAs("coach");
    inRouter(<PanelShell />);

    const nav = screen.getByRole("navigation", { name: "Menú principal" });
    expect(within(nav).getAllByRole("link").map((l) => l.textContent)).toEqual(["Inicio", "Socios"]);
  });

  it("lleva el conmutador de tema (US-068) y aplica el claro por defecto del panel", async () => {
    signInAs("admin");
    inRouter(<PanelShell />);

    expect(document.documentElement.dataset.theme).toBe("light");
    await userEvent.setup().click(within(screen.getByRole("banner")).getByRole("button", { name: "Cambiar a tema oscuro" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    // L7 (revisión del Sprint 2): desmontar antes de reiniciar el tema (avisa a los suscriptores).
    cleanup();
    localStorage.clear();
    resetThemeForTests();
  });

  it("S2-F4a: 'Mi cuenta' del menú de usuario abre el panel con los datos y el cambio de contraseña", async () => {
    mockApi({
      "GET /auth/me": {
        status: 200,
        body: { id: "00000000-0000-4000-8000-000000000001", email: "admin@apex.test", role: "admin", member_id: null, gym_name: "Box Norte", must_change_password: false },
      },
    });
    signInAs("admin");
    inRouter(<PanelShell />);
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: /admin@apex\.test/ }));
    await user.click(within(screen.getByRole("menu", { name: "Menú de usuario" })).getByRole("menuitem", { name: "Mi cuenta" }));

    const panel = await screen.findByRole("dialog", { name: "Mi cuenta" });
    expect(await within(panel).findByText("Box Norte")).toBeInTheDocument();
    expect(within(panel).getByLabelText(/^Contraseña actual/)).toBeInTheDocument();
    await user.click(within(panel).getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("dialog", { name: "Mi cuenta" })).not.toBeInTheDocument();
  });

  it("sin sesión pinta el marco sin usuario", () => {
    inRouter(<PanelShell />);

    expect(screen.getByRole("banner")).not.toHaveTextContent("@");
  });
});

describe("PortalShell, GymShell y TvShell", () => {
  it("PortalShell usa el gimnasio de la sesión", () => {
    signInAs("member", { gymName: "Box Sur" });
    inRouter(<PortalShell />, "/mi");

    expect(screen.getByRole("banner")).toHaveTextContent("Box Sur");
    expect(screen.getByRole("navigation", { name: "Menú del portal" })).toBeInTheDocument();
  });

  it("GymShell toma el título del handle de la ruta y sale al panel", () => {
    signInAs("coach");
    inRouter(<GymShell />, "/clases/1/checkin");

    expect(within(screen.getByRole("banner")).getByRole("heading", { level: 1, name: "Check-in" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Salir" })).toHaveAttribute("href", "/");
  });

  it("TvShell monta el escenario de la TV", () => {
    inRouter(<TvShell />, "/tv");

    expect(screen.getByTestId("tv-stage")).toBeInTheDocument();
  });
});

describe("AccessLayout", () => {
  it("centra la tarjeta con el logo de fondo claro dentro de <main>", async () => {
    const { container } = render(
      <MemoryRouter>
        <AccessLayout>
          <h1>Iniciar sesión</h1>
        </AccessLayout>
      </MemoryRouter>,
    );

    const main = screen.getByRole("main");
    expect(within(main).getByRole("img", { name: "APEX Hybrid Training" })).toHaveAttribute("src", "/brand/apex-logo-light-bg.png");
    expect(within(main).getByRole("heading", { name: "Iniciar sesión" })).toBeInTheDocument();
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(await axe(container)).toHaveNoViolations();
  });
});
