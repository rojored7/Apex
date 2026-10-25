// S3-F2 (US-072; S3-D72) contra el stack de Compose (proyecto `stack`): a 390 px /socios se
// muestra en tarjetas y "Cargar más" trae la segunda página del api real (offset=25). Necesita
// al menos 26 socios vivos: si la base tiene menos, los crea por el api con documento aleatorio
// hasta llegar a 26 (una sola vez por base: en la corrida siguiente ya están y no se crea
// ninguno). No se dan de baja al terminar, a propósito: son el relleno que la spec necesita y
// darlos de baja obligaría a recrearlos en cada corrida (plan F2.2). axe en claro y oscuro.
// Sin E2E_BASE_URL se omite: la variante contra `vite preview` es ../members-mobile.spec.ts.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { capture, documentoAleatorio, esperarTransiciones, loginComo, sameOriginHeaders } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const API = "/api/v1";
const NEEDED = 26;
const PAGE_SIZE = 25;

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

async function totalSocios(page: Page, headers: Record<string, string>): Promise<number> {
  const response = await page.request.get(`${API}/members?limit=1&offset=0`, { headers });
  if (!response.ok()) throw new Error(`GET /members respondió ${String(response.status())}.`);
  return ((await response.json()) as { total: number }).total;
}

/** Crea socios por el api (un solo login) hasta que haya `NEEDED` vivos; devuelve el total. */
async function asegurarSocios(page: Page, token: string): Promise<number> {
  const headers = { ...sameOriginHeaders(), Authorization: `Bearer ${token}` };
  let total = await totalSocios(page, headers);
  const run = Date.now().toString(36);
  for (let index = total; index < NEEDED; index += 1) {
    const created = await page.request.post(`${API}/members`, {
      headers,
      data: { first_name: "Relleno", last_name: `Movil${run}${String(index)}`, document_type: "CC", document: documentoAleatorio(), data_consent: true },
    });
    if (!created.ok()) throw new Error(`POST /members respondió ${String(created.status())}.`);
    total += 1;
  }
  return total;
}

test.describe("lista de socios en el celular contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B9b; en preview corre members-mobile.spec.ts");

  test("a 390 px la lista son tarjetas y 'Cargar más' trae la segunda página", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    const token = await loginComo(page);
    const total = await asegurarSocios(page, token);
    const secondPage: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.pathname === `${API}/members` && url.searchParams.get("offset") === String(PAGE_SIZE)) secondPage.push(url.search);
    });

    await page.goto("/socios");
    const cards = page.getByRole("list", { name: "Socios" }).getByRole("listitem");
    await expect(cards).toHaveCount(PAGE_SIZE);
    await expect(page.getByRole("table")).toHaveCount(0);
    expect(await axeViolations(page)).toEqual([]);
    await capture(page, "socios-movil-stack", "light", 390);

    await page.getByRole("button", { name: "Cargar más" }).click();

    await expect(cards).toHaveCount(Math.min(total, PAGE_SIZE * 2));
    expect(secondPage).toEqual([`?limit=${String(PAGE_SIZE)}&offset=${String(PAGE_SIZE)}`]);
    await expect(page.getByText(`Mostrando ${String(Math.min(total, PAGE_SIZE * 2))} de`)).toBeVisible();
    const sizes = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, inner: window.innerWidth }));
    expect(sizes.scroll).toBeLessThanOrEqual(sizes.inner);
    expect(await axeViolations(page)).toEqual([]);
    await capture(page, "socios-movil-stack-cargar-mas", "light", 390);

    await page.emulateMedia({ colorScheme: "dark" });
    expect(await axeViolations(page)).toEqual([]);
    await capture(page, "socios-movil-stack", "dark", 390);
  });
});
