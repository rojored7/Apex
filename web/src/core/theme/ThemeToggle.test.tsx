// US-068 T4: botón de 44 px con texto accesible que alterna el tema del panel.
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { readFileSync } from "node:fs";
import { getTheme, resetThemeForTests } from "./theme";
import { ThemeToggle } from "./ThemeToggle";

const css = readFileSync("src/core/theme/ThemeToggle.module.css", "utf8");

beforeEach(() => {
  localStorage.clear();
  resetThemeForTests();
});

afterEach(() => {
  // L7 (revisión del Sprint 2): desmontar antes de reiniciar el tema (avisa a los suscriptores).
  cleanup();
  localStorage.clear();
  resetThemeForTests();
});

describe("ThemeToggle", () => {
  it("en claro ofrece el oscuro y al pulsar cambia el tema y el texto", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);

    const button = screen.getByRole("button", { name: "Cambiar a tema oscuro" });
    await user.click(button);

    expect(getTheme()).toBe("dark");
    expect(screen.getByRole("button", { name: "Cambiar a tema claro" })).toBe(button);
  });

  it("funciona con teclado (Enter y Espacio)", async () => {
    const user = userEvent.setup();
    render(<ThemeToggle />);

    await user.tab();
    await user.keyboard("{Enter}");
    expect(getTheme()).toBe("dark");
    await user.keyboard(" ");
    expect(getTheme()).toBe("light");
  });

  it("mide 44 px y tiene foco visible con tokens", () => {
    expect(css).toMatch(/min-width:\s*var\(--control\)/);
    expect(css).toMatch(/min-height:\s*var\(--control\)/);
    expect(css).toMatch(/:focus-visible[^{]*\{[^}]*outline:[^;]*var\(--(apex-blue|blue-deep)\)/);
  });

  it("es accesible", async () => {
    const { container } = render(<ThemeToggle />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
