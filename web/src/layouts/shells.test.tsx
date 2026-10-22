// S2-F2: contenedores que leen la sesión y entregan sus datos a los layouts presentacionales
// (PanelShell, PortalShell, TvShell) y el marco de las pantallas de acceso.
import { render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { resetThemeForTests } from "../core/theme/theme";
import { signInAs, signOutForTests } from "../test/session";
import { AccessLayout } from "./AccessLayout";
import { PanelShell } from "./PanelShell";
import { GymShell, PortalShell, TvShell } from "./ZoneShells";

afterEach(() => {
  signOutForTests();
  delete document.documentElement.dataset.theme;
});

function inRouter(element: ReactNode, path = "/") {
  const router = createMemoryRouter([{ element, children: [{ path: "*", element: <h1>Contenido</h1>, handle: { title: "Check-in" } }] }], {
    initialEntries: [path],
  });
  return render(<RouterProvider router={router} />);
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
    localStorage.clear();
    resetThemeForTests();
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
