// US-062 T2 y T6: portal en una columna con menú inferior de cinco pestañas (DESIGN.md y
// Portal_Inicio.html; la historia pedía seis, manda el diseño aprobado) y tema del teléfono.
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { readFileSync } from "node:fs";
import { PORTAL_TABS } from "./portalTabs";
import { PortalLayout } from "./PortalLayout";

const css = readFileSync("src/layouts/PortalLayout.module.css", "utf8");

function renderPortal(route = "/mi") {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <PortalLayout gymName="Box Norte">
        <p>Último elemento</p>
      </PortalLayout>
    </MemoryRouter>,
  );
}

afterEach(() => {
  delete document.documentElement.dataset.theme;
});

describe("PortalLayout", () => {
  it("PORTAL_TABS son Inicio, Pagos, WODs, Progreso y Yo con sus rutas", () => {
    expect(PORTAL_TABS.map((t) => [t.label, t.to])).toEqual([
      ["Inicio", "/mi"],
      ["Pagos", "/mi/pagos"],
      ["WODs", "/mi/wods"],
      ["Progreso", "/mi/progreso"],
      ["Yo", "/mi/datos"],
    ]);
  });

  it("muestra el menú inferior con texto e icono por destino", () => {
    renderPortal();
    const nav = screen.getByRole("navigation", { name: "Menú del portal" });
    const links = within(nav).getAllByRole("link");

    expect(links.map((l) => l.textContent)).toEqual(["Inicio", "Pagos", "WODs", "Progreso", "Yo"]);
    for (const link of links) expect(link.querySelector("svg")).not.toBeNull();
  });

  it("marca el destino activo con aria-current; Inicio solo en /mi exacto", () => {
    renderPortal("/mi/pagos");
    const nav = screen.getByRole("navigation", { name: "Menú del portal" });

    expect(within(nav).getByRole("link", { name: "Pagos" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Inicio" })).not.toHaveAttribute("aria-current");
  });

  it("el contenido va en <main> con el gimnasio en la cabecera", () => {
    renderPortal();

    expect(within(screen.getByRole("main")).getByText("Último elemento")).toBeInTheDocument();
    expect(screen.getByRole("banner")).toHaveTextContent("Box Norte");
    expect(within(screen.getByRole("banner")).getByRole("img", { name: "APEX" })).toBeInTheDocument();
  });

  it("el relleno inferior del contenido es el alto del menú más el área segura", () => {
    const rule = /\.content\s*\{[^}]*\}/.exec(css)?.[0] ?? "";
    const nav = /\.tabs\s*\{[^}]*\}/.exec(css)?.[0] ?? "";

    expect(rule).toMatch(/padding-bottom:\s*calc\(var\(--portal-tabs-height\)[^;]*env\(safe-area-inset-bottom\)/);
    expect(nav).toMatch(/position:\s*fixed/);
    expect(nav).toMatch(/height:\s*calc\(var\(--portal-tabs-height\)\s*\+\s*env\(safe-area-inset-bottom\)\)/);
    expect(css).toMatch(/--portal-column:\s*600px/);
    expect(css).toMatch(/max-width:\s*var\(--portal-column\)/);
    expect(css).toMatch(/min-height:\s*var\(--control\)/);
  });

  it("sigue el tema del teléfono: quita el tema forzado mientras está montado y lo restaura", () => {
    document.documentElement.dataset.theme = "light";
    const { unmount } = renderPortal();

    expect(document.documentElement.dataset.theme).toBeUndefined();
    unmount();
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
