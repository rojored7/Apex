// Utilidades de los E2E contra el stack de Compose (proyecto `stack`, S2-W0-1).
// Las capturas cubren los cuatro anchos de US-068 en tema claro y oscuro; el tema lo da
// `prefers-color-scheme` (tokens.css), que Playwright emula con `colorScheme`.
// `loginComo` y `crearCoach` llegan con el login real (S2-B2/S2-F3).
import type { Page } from "@playwright/test";

export type Theme = "light" | "dark";

export const VIEWPORTS: readonly number[] = [320, 768, 1024, 1440];
export const THEMES: readonly Theme[] = ["light", "dark"];
const CAPTURE_HEIGHT = 900;

export function captureName(name: string, theme: Theme, width: number): string {
  return `test-results/captures/${name}-${theme}-${String(width)}.png`;
}

export async function capture(page: Page, name: string, theme: Theme, width: number): Promise<string> {
  const path = captureName(name, theme, width);
  await page.setViewportSize({ width, height: CAPTURE_HEIGHT });
  await page.emulateMedia({ colorScheme: theme });
  await page.screenshot({ path, fullPage: true });
  return path;
}
