// S8-V5b: el texto azul de la variante ghost del Button y de la insignia «Benchmark» del calendario de WODs no llegaba a 4,5:1
// sobre --surface ni sobre --blue-tint (axe color-contrast en el stack). Esta prueba lee los CSS reales y calcula el contraste.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const read = (relative: string): string => readFileSync(resolve(__dirname, relative), "utf8");
const tokensCss = read("../../core/styles/tokens.css");

function tokensOf(block: string): Map<string, string> {
  const map = new Map<string, string>();
  for (const match of block.matchAll(/(--[a-z-]+):\s*(#[0-9A-Fa-f]{6})/g)) map.set(match[1] ?? "", match[2] ?? "");
  return map;
}

const darkBlock = /:root\[data-theme="dark"\]\s*\{([^}]*)\}/.exec(tokensCss)?.[1] ?? "";
const light = tokensOf(/:root\s*\{([\s\S]*?)\n\}/.exec(tokensCss)?.[1] ?? "");
const dark = new Map([...light, ...tokensOf(darkBlock)]);

function luminance(hex: string): number {
  const channels = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * (channels[0] ?? 0) + 0.7152 * (channels[1] ?? 0) + 0.0722 * (channels[2] ?? 0);
}

function ratio(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return ((hi ?? 0) + 0.05) / ((lo ?? 0) + 0.05);
}

function colorOf(css: string, selector: string): string {
  const start = css.indexOf(`\n${selector} {`);
  const block = start < 0 ? "" : css.slice(start, css.indexOf("}", start));
  const line = block.split(";").flatMap((part) => part.split("{")).flatMap((part) => part.split("\n")).map((part) => part.trim()).find((part) => part.startsWith("color:"));
  const name = line?.slice(line.indexOf("(") + 1, line.indexOf(")"));
  if (!name) throw new Error(`sin color en ${selector}`);
  return name;
}

const BACKGROUNDS = ["--surface", "--card", "--blue-tint"] as const;
const CASES: readonly [string, string, string][] = [
  ["Button ghost", read("./Button.module.css"), ".ghost"],
  ["insignia Benchmark", read("../../features/wods/components/WeekCalendar.module.css"), ".badge"],
  ["enlace «+ Crear» del calendario", read("../../features/wods/components/WeekCalendar.module.css"), ".create"],
];

describe("contraste del texto azul de acciones secundarias", () => {
  for (const [name, css, selector] of CASES) {
    for (const [theme, tokens] of [["claro", light], ["oscuro", dark]] as const) {
      for (const bg of BACKGROUNDS) {
        it(`${name} llega a 4,5:1 sobre ${bg} en ${theme}`, () => {
          const fg = tokens.get(colorOf(css, selector));
          const back = tokens.get(bg);
          expect(fg).toBeDefined();
          expect(back).toBeDefined();
          expect(ratio(fg ?? "", back ?? "")).toBeGreaterThanOrEqual(4.5);
        });
      }
    }
  }
});
