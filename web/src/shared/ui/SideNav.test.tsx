// US-061 T5 y T6: menú lateral por grupos, ítem activo no solo por color y modo cajón.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { MemoryRouter } from "react-router";
import { FEATURES, type Feature } from "../../config/features";
import { buildNavItems } from "../../layouts/nav";
import { SideNav } from "./SideNav";

const ALL: ReadonlySet<Feature> = new Set(FEATURES);

function renderNav(route: string, mode: "inline" | "drawer" = "inline") {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <SideNav groups={buildNavItems("admin", ALL)} mode={mode} open />
    </MemoryRouter>,
  );
}

function Drawer() {
  const [open, setOpen] = useState(false);
  return (
    <MemoryRouter initialEntries={["/socios"]}>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => {
          setOpen(true);
        }}
      >
        Abrir menú
      </button>
      <SideNav
        id="menu"
        groups={buildNavItems("coach", ALL)}
        mode="drawer"
        open={open}
        onClose={() => {
          setOpen(false);
        }}
      />
      <p>Contenido</p>
    </MemoryRouter>
  );
}

describe("SideNav", () => {
  it("es una navegación con nombre y títulos de grupo", () => {
    renderNav("/");
    const nav = screen.getByRole("navigation", { name: "Menú principal" });

    expect(within(nav).getByText("Gestión")).toBeInTheDocument();
    expect(within(nav).getByText("Sistema")).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: "Socios" })).toHaveAttribute("href", "/socios");
  });

  it("marca la entrada activa con aria-current y una clase no cromática", () => {
    renderNav("/socios");

    const active = screen.getByRole("link", { name: "Socios" });
    expect(active).toHaveAttribute("aria-current", "page");
    expect(active.className).toContain("active");
    expect(screen.getByRole("link", { name: "Inicio" })).not.toHaveAttribute("aria-current");
  });

  it("Inicio solo está activo en la ruta exacta", () => {
    renderNav("/");

    expect(screen.getByRole("link", { name: "Inicio" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Socios" })).not.toHaveAttribute("aria-current");
  });

  it("los enlaces se recorren con Tab en el orden del menú", async () => {
    const user = userEvent.setup();
    renderNav("/");

    await user.tab();
    expect(screen.getByRole("link", { name: "Inicio" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("link", { name: "Clases de hoy" })).toHaveFocus();
  });

  it("cada entrada lleva su texto aunque el menú se pliegue a iconos", () => {
    renderNav("/");

    for (const link of screen.getAllByRole("link")) {
      expect(link.textContent.trim().length).toBeGreaterThan(0);
    }
  });

  it("en modo cajón cerrado no pinta nada", () => {
    render(
      <MemoryRouter>
        <SideNav groups={buildNavItems("admin", ALL)} mode="drawer" open={false} />
      </MemoryRouter>,
    );

    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  it("el cajón es un diálogo con foco atrapado; Escape lo cierra y devuelve el foco al botón", async () => {
    const user = userEvent.setup();
    render(<Drawer />);
    const opener = screen.getByRole("button", { name: "Abrir menú" });

    await user.click(opener);
    const dialog = screen.getByRole("dialog", { name: "Menú principal" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("id", "menu");
    expect(within(dialog).getByRole("button", { name: "Cerrar menú" })).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(opener).toHaveFocus();
  });

  it("el cajón se cierra con el botón, con clic fuera y al elegir una entrada", async () => {
    const user = userEvent.setup();
    render(<Drawer />);
    const opener = screen.getByRole("button", { name: "Abrir menú" });

    await user.click(opener);
    await user.click(screen.getByRole("button", { name: "Cerrar menú" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(opener);
    await user.click(screen.getByTestId("sidenav-backdrop"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    await user.click(opener);
    await user.click(screen.getByRole("link", { name: "Inicio" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("el cajón muestra solo las entradas del rol", async () => {
    const user = userEvent.setup();
    render(<Drawer />);

    await user.click(screen.getByRole("button", { name: "Abrir menú" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).queryByRole("link", { name: "Planes" })).not.toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Socios" })).toBeInTheDocument();
  });
});
