// US-068 T5: el catálogo (catalog.html) muestra los 16 componentes en sus estados, cada
// StatusTag con texto, y elige tema y vista por la URL.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { signOutForTests } from "../test/session";
import { CatalogApp, KIT_COMPONENTS } from "./Catalog";

const OPTIONS = { rules: { "color-contrast": { enabled: false } } };

afterEach(() => {
  signOutForTests();
  delete document.documentElement.dataset.theme;
});

describe("Catalog", () => {
  it("tiene una sección con título por cada uno de los 16 componentes", () => {
    render(<CatalogApp search="" />);

    expect(KIT_COMPONENTS).toHaveLength(16);
    for (const name of KIT_COMPONENTS) {
      expect(screen.getByRole("region", { name })).toBeInTheDocument();
    }
  });

  it("cada StatusTag del catálogo lleva texto además del color", () => {
    render(<CatalogApp search="" />);
    const tags = within(screen.getByRole("region", { name: "StatusTag" })).getAllByText(/./, { selector: "[data-status]" });

    expect(tags.length).toBeGreaterThanOrEqual(7);
    for (const tag of tags) expect(tag.textContent.trim().length).toBeGreaterThan(0);
  });

  it("enlaza a los cuatro layouts de muestra", () => {
    render(<CatalogApp search="" />);
    const nav = screen.getByRole("navigation", { name: "Layouts de muestra" });

    for (const view of ["panel", "portal", "gym", "tv"]) {
      expect(within(nav).getAllByRole("link").some((a) => a.getAttribute("href")?.includes(`vista=${view}`))).toBe(true);
    }
  });

  it("?tema=dark pinta el catálogo en oscuro", () => {
    render(<CatalogApp search="?tema=dark" />);
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("con ?vista= pinta el layout de muestra en lugar del kit", () => {
    render(<CatalogApp search="?vista=tv" />);
    expect(screen.getByTestId("tv-stage")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Button" })).not.toBeInTheDocument();
  });

  it("abre el panel lateral y el modal de confirmación de muestra", async () => {
    const user = userEvent.setup();
    render(<CatalogApp search="" />);

    await user.click(screen.getByRole("button", { name: "Abrir panel lateral" }));
    expect(screen.getByRole("dialog", { name: "Nuevo plan" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Cancelar" }));

    await user.click(screen.getByRole("button", { name: "Abrir modal de confirmación" }));
    expect(screen.getByRole("dialog", { name: "¿Anular este pago?" })).toBeInTheDocument();
  });

  it("es accesible (sin contraste: lo mide Playwright con estilos reales)", async () => {
    const { container } = render(<CatalogApp search="" />);
    expect(await axe(container, OPTIONS)).toHaveNoViolations();
  });
});
