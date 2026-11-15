// S8-F6 (US-177, S8-D19, S8-D20, S8-D32, L-4) contra el stack de Compose: la TV abre con el token del enlace en el FRAGMENTO, deja la URL
// limpia, pide GET /tv/today con 200 y solo X-Device-Token, y al rotar el token desde Configuración queda en «Token inválido».
// - El token se genera por el api (POST /settings/tv/regenerate-token con el admin del seed) y vive solo en la memoria de la prueba:
//   no se imprime ni se guarda. La TV es un contexto limpio, sin cookies ni sesión.
// - Captura a 1920 × 1080 (la pantalla es de oscuro y fija). Necesita C1, C2 y el seed. Sin E2E_BASE_URL se omite.
// Deja la TV como estaba: restaura refresco y ranking y revoca el token de la prueba (restaurarTv, en finally).
// ESCRITO, SIN CORRER: el stack de desarrollo está roto y su reparación espera al usuario (Sprint 8, F6).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { capture, esperarTransiciones, fijarTv, leerEstadoTv, loginComo, restaurarTv, sameOriginHeaders } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const API = "/api/v1";
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const REFRESH_WAIT_MS = 90_000;
// El refresco de la TV se baja a 15 s (el mínimo) al empezar: con 300 s la espera de «Token inválido» no cabe en REFRESH_WAIT_MS.
const REFRESH_SECONDS = 15;

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

function tokenDe(enlace: string): string {
  const token = new URL(enlace).hash.replace(/^#token=/, "");
  expect(token).toMatch(/^[A-Za-z0-9_-]{16,200}$/);
  return token;
}

test.describe("Pantalla de TV contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con C1 y C2; en preview no hay api");

  test("abre con #token=, limpia la URL, muestra el tablero y queda en «Token inválido» al rotar el token", async ({ page, browser }) => {
    test.setTimeout(5 * 60_000);
    const adminToken = await loginComo(page);
    const headers = { Authorization: `Bearer ${adminToken}`, ...sameOriginHeaders() };
    const antes = await leerEstadoTv(page, headers);
    try {
      await fijarTv(page, headers, { refresh_seconds: REFRESH_SECONDS, show_leaderboard: antes.show_leaderboard });
      const generar = async (): Promise<string> => {
        const respuesta = await page.request.post(`${API}/settings/tv/regenerate-token`, { headers });
        expect(respuesta.ok()).toBe(true);
        return tokenDe(((await respuesta.json()) as { url: string }).url);
      };
      const token = await generar();

      // La TV: un contexto limpio, sin cookies ni sesión.
      const contexto = await browser.newContext({ viewport: { width: 1920, height: 1080 }, baseURL: process.env.E2E_BASE_URL ?? "" });
      const tv = await contexto.newPage();
      const pedidos: { url: string; cabecera: string | undefined; autorizacion: string | undefined }[] = [];
      tv.on("request", (request) => {
        if (request.url().includes("/tv/today")) {
          pedidos.push({ url: request.url(), cabecera: request.headers()["x-device-token"], autorizacion: request.headers()["authorization"] });
        }
      });
      const respuesta200 = tv.waitForResponse((response) => response.url().includes("/api/v1/tv/today") && response.status() === 200);
      await tv.goto(`/tv#token=${token}`);
      await respuesta200;

      expect(new URL(tv.url()).pathname).toBe("/tv");
      expect(new URL(tv.url()).hash).toBe("");
      expect(tv.url()).not.toContain(token);
      expect(pedidos[0]?.cabecera).toBe(token);
      expect(pedidos[0]?.autorizacion).toBeUndefined();
      expect(pedidos[0]?.url).not.toContain("token");
      await expect(tv.getByText("Solo nombre y puntaje: nunca datos personales en la TV")).toBeVisible();
      await expect(tv.getByRole("img", { name: "APEX Hybrid Training" }).first()).toBeVisible();
      await capture(tv, "tv", "dark", 1920);
      expect(await axeViolations(tv)).toEqual([]);

      // Regenerar desde Configuración (aquí por el api): la TV vieja queda con «Token inválido» tras su siguiente lectura.
      await generar();
      await expect(tv.getByText("Token inválido. Pide un enlace nuevo en Configuración")).toBeVisible({ timeout: REFRESH_WAIT_MS });
      await contexto.close();
    } finally {
      await restaurarTv(page, headers, antes);
    }
  });
});
