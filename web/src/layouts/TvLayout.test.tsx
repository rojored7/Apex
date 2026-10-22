// US-062 T4 y T6: TV de 1920 × 1080 en oscuro, sin cursor, sin foco y sin desplazamiento.
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { TV_HEIGHT, TV_WIDTH, TvLayout, tvScale } from "./TvLayout";

const css = readFileSync("src/layouts/TvLayout.module.css", "utf8");

afterEach(() => {
  delete document.documentElement.dataset.theme;
});

describe("tvScale", () => {
  it("1 en una pantalla 1080p; menor en una más pequeña; conserva la proporción", () => {
    expect(tvScale(TV_WIDTH, TV_HEIGHT)).toBe(1);
    expect(tvScale(1280, 720)).toBeCloseTo(2 / 3);
    expect(tvScale(3840, 1080)).toBe(1);
    expect(tvScale(1920, 2160)).toBe(1);
    expect(tvScale(3840, 2160)).toBe(2);
  });

  it("con medidas inválidas devuelve 1", () => {
    expect(tvScale(0, 0)).toBe(1);
    expect(tvScale(Number.NaN, 1080)).toBe(1);
  });
});

describe("TvLayout", () => {
  it("fuerza el tema oscuro y lo restaura al desmontar", () => {
    document.documentElement.dataset.theme = "light";
    const { unmount } = render(<TvLayout>WOD del día</TvLayout>);

    expect(document.documentElement.dataset.theme).toBe("dark");
    unmount();
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("el escenario es inerte y Tab no enfoca nada", async () => {
    const user = userEvent.setup();
    render(
      <TvLayout>
        <h1>Helen</h1>
        <p>3 rondas</p>
      </TvLayout>,
    );
    const stage = screen.getByTestId("tv-stage");

    expect(stage).toHaveAttribute("inert");
    expect(stage).toHaveAttribute("aria-label", "Pantalla del gimnasio");
    await user.tab();
    expect(document.body).toHaveFocus();
  });

  it("escala el escenario al tamaño de la ventana y reacciona al cambio", () => {
    vi.stubGlobal("innerWidth", 1280);
    vi.stubGlobal("innerHeight", 720);
    try {
      render(<TvLayout>WOD</TvLayout>);
      const stage = screen.getByTestId("tv-stage");
      expect(stage.style.transform).toBe(`scale(${String(2 / 3)})`);

      vi.stubGlobal("innerWidth", 1920);
      vi.stubGlobal("innerHeight", 1080);
      act(() => {
        window.dispatchEvent(new Event("resize"));
      });
      expect(stage.style.transform).toBe("scale(1)");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("1920 × 1080 sin desplazamiento ni cursor", () => {
    const stage = /\.stage\s*\{[^}]*\}/.exec(css)?.[0] ?? "";
    const root = /\.root\s*\{[^}]*\}/.exec(css)?.[0] ?? "";

    expect(stage).toMatch(/width:\s*1920px/);
    expect(stage).toMatch(/height:\s*1080px/);
    expect(root).toMatch(/overflow:\s*hidden/);
    expect(root).toMatch(/cursor:\s*none/);
    expect(stage).toMatch(/cursor:\s*none/);
  });
});
