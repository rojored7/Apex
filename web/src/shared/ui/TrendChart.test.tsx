// S9-F3 · US-183: TrendChart, gráfica de línea simple en SVG con solo tokens.
// - <svg role="img"> con aria-label que describe la serie con palabras, sin depender del color:
//   «<título>: N puntos. <label>: <texto>; <label>: <texto> (mejor); ...» (un punto: «1 punto»).
// - El mejor punto se distingue por forma (data-best="true" y radio mayor), no solo por color.
// - Un solo punto: un círculo y ninguna línea. Sin puntos: sin SVG, con el mensaje (por omisión «Sin datos para graficar.»).
// - S9-F3 (revisiones): lowerIsBetter invierte la escala vertical; las fechas extremas van en HTML bajo el SVG; con más de 12 puntos el nombre resume; los valores no finitos se ignoran.
// - Ni TrendChart.tsx ni TrendChart.module.css tienen colores ni fuentes literales; el CSS usa variables de tokens.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { render, screen } from "@testing-library/react";
import { axe } from "vitest-axe";
import { TrendChart, type TrendPoint } from "./TrendChart";

const POINTS: TrendPoint[] = [
  { id: "a", label: "12 mar 2026", value: 280, text: "4:40" },
  { id: "b", label: "20 jun 2026", value: 260, text: "4:20" },
  { id: "c", label: "20 oct 2026", value: 245, text: "4:05", isBest: true },
];

const radius = (el: Element): number => Number(el.getAttribute("r"));

describe("TrendChart · accesibilidad", () => {
  it("es una imagen con nombre que describe cada punto con su texto y marca el mejor con palabras", () => {
    render(<TrendChart title="Fran" points={POINTS} />);

    const chart = screen.getByRole("img", { name: /Fran/ });
    expect(chart.tagName.toLowerCase()).toBe("svg");
    const label = chart.getAttribute("aria-label") ?? "";
    expect(label).toContain("Fran: 3 puntos");
    expect(label).toContain("12 mar 2026: 4:40");
    expect(label).toContain("20 jun 2026: 4:20");
    expect(label).toContain("20 oct 2026: 4:05 (mejor)");
    expect(label).not.toContain("4:40 (mejor)");
  });

  it("no tiene violaciones de accesibilidad (sin contraste: lo mide Playwright con estilos reales)", async () => {
    const { container } = render(<TrendChart title="Fran" points={POINTS} />);

    expect(screen.getByRole("img", { name: /Fran/ })).toBeInTheDocument();
    expect(await axe(container, { rules: { "color-contrast": { enabled: false } } })).toHaveNoViolations();
  });
});

describe("TrendChart · puntos", () => {
  it("dibuja un círculo por punto y solo el mejor lleva data-best y un radio mayor", () => {
    const { container } = render(<TrendChart title="Fran" points={POINTS} />);

    const circles = [...container.querySelectorAll("svg circle")];
    expect(circles).toHaveLength(3);
    const best = circles.filter((c) => c.getAttribute("data-best") === "true");
    expect(best).toHaveLength(1);
    const others = circles.filter((c) => c !== best[0]);
    for (const other of others) expect(radius(best[0] as Element)).toBeGreaterThan(radius(other));
  });

  it("une los puntos con una línea (3 puntos, una polilínea con 3 vértices)", () => {
    const { container } = render(<TrendChart title="Fran" points={POINTS} />);

    const line = container.querySelector("svg polyline");
    expect(line).not.toBeNull();
    expect((line?.getAttribute("points") ?? "").trim().split(/\s+/)).toHaveLength(3);
  });

  it("un solo punto: un círculo, ninguna línea y el nombre dice «1 punto»", () => {
    const { container } = render(<TrendChart title="Helen" points={[{ id: "h", label: "20 oct 2026", value: 702, text: "11:42", isBest: true }]} />);

    expect(container.querySelectorAll("svg circle")).toHaveLength(1);
    expect(container.querySelector("svg polyline")).toBeNull();
    expect(screen.getByRole("img", { name: /Helen/ }).getAttribute("aria-label")).toContain("Helen: 1 punto.");
  });

  it("valores iguales (línea plana) no rompen: las coordenadas son números finitos", () => {
    const flat: TrendPoint[] = [
      { id: "a", label: "1 ene 2026", value: 100, text: "100" },
      { id: "b", label: "1 feb 2026", value: 100, text: "100", isBest: true },
    ];
    const { container } = render(<TrendChart title="Plano" points={flat} />);

    for (const c of container.querySelectorAll("svg circle")) {
      expect(Number.isFinite(Number(c.getAttribute("cx")))).toBe(true);
      expect(Number.isFinite(Number(c.getAttribute("cy")))).toBe(true);
    }
  });
});

describe("TrendChart · sin datos", () => {
  it("sin puntos no dibuja ninguna imagen y dice «Sin datos para graficar.»", () => {
    const { container } = render(<TrendChart title="Fran" points={[]} />);

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(container.querySelector("svg")).toBeNull();
    expect(screen.getByText("Sin datos para graficar.")).toBeInTheDocument();
  });

  it("acepta su propio mensaje de vacío", () => {
    render(<TrendChart title="Fran" points={[]} emptyMessage="Aún no hay intentos." />);

    expect(screen.getByText("Aún no hay intentos.")).toBeInTheDocument();
    expect(screen.queryByText("Sin datos para graficar.")).not.toBeInTheDocument();
  });
});

describe("TrendChart · solo tokens", () => {
  const read = (name: string): string => readFileSync(fileURLToPath(new URL(name, import.meta.url)), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

  it("el componente no tiene colores ni fuentes literales", () => {
    const tsx = read("./TrendChart.tsx");

    expect(tsx).not.toMatch(/#[0-9a-f]{3,8}\b/i);
    expect(tsx).not.toMatch(/\b(rgba?|hsla?|oklch|oklab)\(/i);
    expect(tsx).not.toMatch(/(fill|stroke)=["'](?!none|currentColor)/);
  });

  it("su CSS existe, usa variables de tokens y no tiene colores ni fuentes literales", () => {
    const css = read("./TrendChart.module.css");

    expect(css).toMatch(/var\(--/);
    expect(css).not.toMatch(/#[0-9a-f]{3,8}\b/i);
    expect(css).not.toMatch(/\b(rgba?|hsla?|hwb|lab|lch|oklch|oklab)\(/i);
    expect(css).not.toMatch(/font-family\s*:(?!\s*(var\(|inherit))/);
  });
});

const cyOf = (container: HTMLElement): number[] => [...container.querySelectorAll("svg circle")].map((c) => Number(c.getAttribute("cy")));
const cxOf = (container: HTMLElement): number[] => [...container.querySelectorAll("svg circle")].map((c) => Number(c.getAttribute("cx")));

describe("TrendChart · sentido vertical (M2)", () => {
  it("por omisión el valor mayor queda arriba (cy menor)", () => {
    const { container } = render(<TrendChart title="Carga" points={POINTS} />);

    const [high, , low] = cyOf(container);
    expect(high).toBeLessThan(low ?? 0);
  });

  it("con lowerIsBetter el valor menor queda arriba y el mejor (el menor) tiene la cy menor", () => {
    const { container } = render(<TrendChart title="Fran" points={POINTS} lowerIsBetter />);

    const ys = cyOf(container);
    const best = container.querySelector('svg circle[data-best="true"]');
    expect(Number(best?.getAttribute("cy"))).toBe(Math.min(...ys));
    expect(ys[2]).toBeLessThan(ys[0] ?? 0);
  });

  it("con el mejor al máximo y sin lowerIsBetter, el mejor también tiene la cy menor", () => {
    const rising: TrendPoint[] = [
      { id: "a", label: "1 ene 2026", value: 100, text: "100" },
      { id: "b", label: "1 feb 2026", value: 120, text: "120", isBest: true },
    ];
    const { container } = render(<TrendChart title="Carga" points={rising} />);

    const best = container.querySelector('svg circle[data-best="true"]');
    expect(Number(best?.getAttribute("cy"))).toBe(Math.min(...cyOf(container)));
  });
});

describe("TrendChart · reparto horizontal y etiquetas (M3, L14)", () => {
  it("reparte los puntos parejo de izquierda a derecha en el orden recibido", () => {
    const { container } = render(<TrendChart title="Fran" points={POINTS} />);

    const [a, b, c] = cxOf(container);
    expect(a).toBeLessThan(b ?? 0);
    expect(b).toBeLessThan(c ?? 0);
    expect((b ?? 0) - (a ?? 0)).toBeCloseTo((c ?? 0) - (b ?? 0), 0);
  });

  it("las fechas extremas van en HTML debajo del SVG, no como texto SVG", () => {
    const { container } = render(<TrendChart title="Fran" points={POINTS} />);

    expect(container.querySelector("svg text")).toBeNull();
    for (const label of ["12 mar 2026", "20 oct 2026"]) {
      const node = screen.getByText(label);
      expect(node.closest("svg")).toBeNull();
    }
    expect(screen.queryByText("20 jun 2026")).not.toBeInTheDocument();
  });

  it("un solo punto: una sola etiqueta", () => {
    render(<TrendChart title="Helen" points={[{ id: "h", label: "20 oct 2026", value: 702, text: "11:42", isBest: true }]} />);

    expect(screen.getAllByText("20 oct 2026")).toHaveLength(1);
  });

  it("la línea y los puntos usan trazo que no se escala (legibles en 320 y 375 px)", () => {
    const name = "./TrendChart.module.css";
    const css = readFileSync(fileURLToPath(new URL(name, import.meta.url)), "utf8");

    expect(css.match(/vector-effect:\s*non-scaling-stroke/g)?.length ?? 0).toBeGreaterThanOrEqual(3);
  });
});

describe("TrendChart · muchos puntos y valores raros (M4, L6)", () => {
  const many = (n: number): TrendPoint[] => Array.from({ length: n }, (_, i) => ({ id: `p${String(i)}`, label: `d${String(i)}`, value: 100 + i, text: `t${String(i)}`, isBest: i === 5 }));

  it("hasta 12 puntos el nombre los lista todos", () => {
    render(<TrendChart title="Serie" points={many(12)} />);

    const label = screen.getByRole("img").getAttribute("aria-label") ?? "";
    expect(label).toContain("12 puntos");
    expect(label).toContain("d7: t7");
  });

  it("con más de 12 puntos el nombre resume: cantidad, primero, último y mejor", () => {
    render(<TrendChart title="Serie" points={many(20)} />);

    const label = screen.getByRole("img").getAttribute("aria-label") ?? "";
    expect(label).toContain("20 puntos");
    expect(label).toContain("primero d0: t0");
    expect(label).toContain("último d19: t19");
    expect(label).toContain("mejor d5: t5");
    expect(label).not.toContain("d7: t7");
  });

  it("ignora valores no finitos y deja coordenadas finitas con 1 y 1e12", () => {
    const odd: TrendPoint[] = [
      { id: "a", label: "a", value: 1, text: "1" },
      { id: "n", label: "n", value: Number.NaN, text: "NaN" },
      { id: "i", label: "i", value: Number.POSITIVE_INFINITY, text: "inf" },
      { id: "b", label: "b", value: 1e12, text: "1e12", isBest: true },
    ];
    const { container } = render(<TrendChart title="Raro" points={odd} />);

    expect(container.querySelectorAll("svg circle")).toHaveLength(2);
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("2 puntos");
    for (const value of [...cyOf(container), ...cxOf(container)]) expect(Number.isFinite(value)).toBe(true);
  });

  it("si ningún valor es finito dice que no hay datos", () => {
    render(<TrendChart title="Raro" points={[{ id: "n", label: "n", value: Number.NaN, text: "NaN" }]} />);

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("Sin datos para graficar.")).toBeInTheDocument();
  });

});
