// US-061 T3 y T6: marco del panel (TopBar, SideNav, contenido), "Saltar al contenido",
// orden de tabulación y cajón en celular.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { ENABLED_FEATURES } from "../config/features";
import type { Role } from "../core/auth";
import { setViewportWidth } from "../test/server";
import { buildNavItems } from "./nav";
import { PanelLayout } from "./PanelLayout";

const USER = { email: "ana@apex.test", roleLabel: "Admin" };

function renderPanel(role: Role, route = "/socios") {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route element={<PanelLayout user={USER} gymName="Box Norte" navGroups={buildNavItems(role, ENABLED_FEATURES)} />}>
          <Route path="*" element={<button type="button">Acción de la página</button>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("PanelLayout", () => {
  it("monta TopBar, menú y el contenido de la ruta dentro de <main id=contenido>", () => {
    renderPanel("admin");

    expect(screen.getByRole("banner")).toHaveTextContent("Box Norte");
    expect(screen.getByRole("navigation", { name: "Menú principal" })).toBeInTheDocument();
    const main = screen.getByRole("main");
    expect(main).toHaveAttribute("id", "contenido");
    expect(main).toHaveAttribute("tabindex", "-1");
    expect(within(main).getByRole("button", { name: "Acción de la página" })).toBeInTheDocument();
  });

  it("el admin ve Planes y Sistema; el coach no", () => {
    const { unmount } = renderPanel("admin");
    expect(screen.getByRole("link", { name: "Planes" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Usuarios y roles" })).toBeInTheDocument();
    unmount();

    renderPanel("coach");
    expect(screen.queryByRole("link", { name: "Planes" })).not.toBeInTheDocument();
    for (const label of ["Usuarios y roles", "Auditoría", "Llaves de cifrado", "Configuración"]) {
      expect(screen.queryByRole("link", { name: label })).not.toBeInTheDocument();
    }
  });

  it("acepta el contenido como hijos sin router de rutas", () => {
    render(
      <MemoryRouter>
        <PanelLayout user={USER} navGroups={[]}>
          <p>Hijo directo</p>
        </PanelLayout>
      </MemoryRouter>,
    );

    expect(within(screen.getByRole("main")).getByText("Hijo directo")).toBeInTheDocument();
  });

  it("el primer Tab llega a Saltar al contenido, que lleva el foco a <main>", async () => {
    const user = userEvent.setup();
    renderPanel("admin");

    await user.tab();
    const skip = screen.getByRole("link", { name: "Saltar al contenido" });
    expect(skip).toHaveFocus();
    expect(skip).toHaveAttribute("href", "#contenido");
    await user.keyboard("{Enter}");
    expect(screen.getByRole("main")).toHaveFocus();
  });

  it("el orden de tabulación es TopBar, menú y contenido", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/"]}>
        <PanelLayout
          user={USER}
          navGroups={buildNavItems("coach", ENABLED_FEATURES)}
          onLogout={vi.fn()}
          themeToggle={<button type="button">Tema</button>}
        >
          <button type="button">Acción de la página</button>
        </PanelLayout>
      </MemoryRouter>,
    );

    const order: string[] = [];
    for (let i = 0; i < 6; i += 1) {
      await user.tab();
      order.push(document.activeElement?.textContent ?? "");
    }
    expect(order[0]).toBe("Saltar al contenido");
    const themeIndex = order.indexOf("Tema");
    const homeIndex = order.indexOf("Inicio");
    const pageIndex = order.indexOf("Acción de la página");
    expect(themeIndex).toBeGreaterThan(0);
    expect(homeIndex).toBeGreaterThan(themeIndex);
    expect(pageIndex).toBeGreaterThan(homeIndex);
  });

  it("en escritorio el menú va en línea y no hay botón de menú", () => {
    setViewportWidth(1280);
    renderPanel("admin");

    expect(screen.queryByRole("button", { name: "Abrir menú" })).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Socios" })).toBeInTheDocument();
  });

  it("con 390 px el menú se oculta; el botón abre el cajón y Escape lo cierra devolviendo el foco", async () => {
    setViewportWidth(390);
    const user = userEvent.setup();
    renderPanel("coach");

    expect(screen.queryByRole("navigation", { name: "Menú principal" })).not.toBeInTheDocument();
    const button = screen.getByRole("button", { name: "Abrir menú" });
    expect(button).toHaveAttribute("aria-expanded", "false");

    await user.click(button);
    const dialog = screen.getByRole("dialog", { name: "Menú principal" });
    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(button).toHaveAttribute("aria-controls", dialog.id);
    expect(within(dialog).getByRole("link", { name: "Socios" })).toBeInTheDocument();
    expect(within(dialog).queryByRole("link", { name: "Planes" })).not.toBeInTheDocument();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });
});
