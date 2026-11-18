// V7 L12: la comprobación de accesibilidad con axe que repetían las specs del stack. Va aparte de stack.ts porque las pruebas de
// vitest de tests/unit cargan stack.ts y no necesitan axe.
import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { esperarTransiciones } from "./stack";

export const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];

/** Las violaciones de WCAG 2.1 AA de la página, una línea cada una (vacío si no hay ninguna). */
export async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}
