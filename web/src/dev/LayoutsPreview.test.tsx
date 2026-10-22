// US-062 T5: la página de muestra de layouts (catalog.html) elige la vista por la URL y
// pinta cada layout con contenido de ejemplo accesible.
import { render, screen } from "@testing-library/react";
import { axe } from "vitest-axe";
import { LayoutsPreview, readPreviewParams } from "./LayoutsPreview";

const OPTIONS = { rules: { "color-contrast": { enabled: false } } };

afterEach(() => {
  delete document.documentElement.dataset.theme;
});

describe("readPreviewParams", () => {
  it("lee vista, rol y tema; valores desconocidos caen a los de defecto", () => {
    expect(readPreviewParams("?vista=panel&rol=coach&tema=dark")).toEqual({ view: "panel", role: "coach", theme: "dark" });
    expect(readPreviewParams("?vista=otra&rol=root&tema=azul")).toEqual({ view: null, role: "admin", theme: "light" });
    expect(readPreviewParams("")).toEqual({ view: null, role: "admin", theme: "light" });
  });
});

describe("LayoutsPreview", () => {
  it("sin vista muestra el índice de enlaces", () => {
    render(<LayoutsPreview search="" />);

    expect(screen.getByRole("heading", { name: "Layouts de muestra" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "TV" })).toHaveAttribute("href", "?vista=tv");
  });

  it("panel del coach con el tema pedido y sin Planes", async () => {
    const { container } = render(<LayoutsPreview search="?vista=panel&rol=coach&tema=dark" />);

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.getByRole("heading", { level: 1, name: "Socios" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Planes" })).not.toBeInTheDocument();
    expect(await axe(container, OPTIONS)).toHaveNoViolations();
  });

  it("portal con el último bloque", async () => {
    const { container } = render(<LayoutsPreview search="?vista=portal" />);

    expect(screen.getByText("Último bloque del contenido")).toBeInTheDocument();
    expect(await axe(container, OPTIONS)).toHaveNoViolations();
  });

  it("tablet del box en oscuro", async () => {
    const { container } = render(<LayoutsPreview search="?vista=gym" />);

    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(screen.getByRole("button", { name: "Llegó" })).toBeInTheDocument();
    expect(await axe(container, OPTIONS)).toHaveNoViolations();
  });

  it("TV", async () => {
    const { container } = render(<LayoutsPreview search="?vista=tv" />);

    expect(screen.getByText("WOD del día")).toBeInTheDocument();
    expect(await axe(container, OPTIONS)).toHaveNoViolations();
  });
});
