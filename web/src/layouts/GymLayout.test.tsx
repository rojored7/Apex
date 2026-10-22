// US-062 T3 y T6: tablet del box en oscuro forzado, controles de 56 px y barra mínima.
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { readFileSync } from "node:fs";
import { setViewportWidth } from "../test/server";
import { GymLayout } from "./GymLayout";

const css = readFileSync("src/layouts/GymLayout.module.css", "utf8");

function renderGym() {
  return render(
    <MemoryRouter>
      <GymLayout title="Check-in · 17:00 · Coach María" subtitle="Martes 20 de octubre" exitTo="/clases" exitLabel="Clases">
        <button type="button">Llegó</button>
      </GymLayout>
    </MemoryRouter>,
  );
}

afterEach(() => {
  delete document.documentElement.dataset.theme;
  vi.unstubAllGlobals();
});

describe("GymLayout", () => {
  it("fuerza el tema oscuro aunque el sistema prefiera claro y lo restaura al desmontar", () => {
    setViewportWidth(1024);
    document.documentElement.dataset.theme = "light";
    const { unmount } = renderGym();

    expect(document.documentElement.dataset.theme).toBe("dark");
    unmount();
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("sin tema previo, al desmontar quita el atributo", () => {
    const { unmount } = renderGym();
    unmount();

    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("barra mínima con el nombre de la sesión, subtítulo y salida; sin menú lateral", () => {
    renderGym();
    const banner = screen.getByRole("banner");

    expect(within(banner).getByRole("heading", { level: 1, name: "Check-in · 17:00 · Coach María" })).toBeInTheDocument();
    expect(within(banner).getByText("Martes 20 de octubre")).toBeInTheDocument();
    expect(within(banner).getByRole("link", { name: "Clases" })).toHaveAttribute("href", "/clases");
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(within(screen.getByRole("main")).getByRole("button", { name: "Llegó" })).toBeInTheDocument();
  });

  it("la salida dice Salir por defecto", () => {
    render(
      <MemoryRouter>
        <GymLayout title="Resultados" exitTo="/" />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Salir" })).toBeInTheDocument();
  });

  it("los controles del contenedor miden --control-gym (56 px) sin variantes nuevas", () => {
    const root = /\.root\s*\{[^}]*\}/.exec(css)?.[0] ?? "";
    const exit = /\.exit\s*\{[^}]*\}/.exec(css)?.[0] ?? "";

    expect(root).toMatch(/--control:\s*var\(--control-gym\)/);
    expect(exit).toMatch(/min-height:\s*var\(--control-gym\)/);
    expect(css).toMatch(/:focus-visible[^{]*\{[^}]*outline:[^;]*var\(--(blue-deep|apex-blue)\)/);
  });
});
