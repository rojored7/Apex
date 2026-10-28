// S2-F6 (US-069, US-070) contra el stack de Compose (proyecto `stack`, V4 del plan): el admin
// registra un socio con documento único, lo busca por documento (índice ciego, B8) y por
// nombre, y el coach lo ve en la lista. axe en cada pantalla. El documento no llega a la URL.
// Necesita B2 a B4, B7 y B8. Sin E2E_BASE_URL se omite: la variante contra `vite preview` es
// ../members.spec.ts. Idempotente: documento y apellido únicos por corrida (V4 corre dos veces).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { borrarUsuario, crearCoach, esperarTransiciones, loginComo } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const RUN = Date.now().toString();
const DOCUMENT = RUN.slice(-10);
const LAST_NAME = `Prueba${Date.now().toString(36)}`;
const FULL_NAME = `Sara ${LAST_NAME}`;

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

async function search(page: Page, text: string): Promise<void> {
  await page.getByRole("searchbox", { name: "Buscar" }).fill(text);
  await expect(page.getByRole("link", { name: FULL_NAME })).toBeVisible();
  expect(page.url()).not.toContain(encodeURIComponent(text));
  expect(page.url()).not.toContain(text);
}

test.describe("alta y lista de socios contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B2 a B4, B7 y B8; en preview corre members.spec.ts");

  test("el admin registra un socio, lo busca por documento y por nombre, y el coach lo ve", async ({ browser, page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);
    await page.goto("/socios/nuevo");

    await page.getByRole("textbox", { name: /^Nombres/ }).fill("Sara");
    await page.getByRole("textbox", { name: /^Apellidos/ }).fill(LAST_NAME);
    await page.getByRole("textbox", { name: /^Número de documento/ }).fill(DOCUMENT);
    await page.getByRole("textbox", { name: /^Teléfono \(WhatsApp\)/ }).fill("3001234567");
    await page.getByRole("checkbox", { name: "El socio autorizó el tratamiento de datos" }).check();
    expect(await axeViolations(page)).toEqual([]);
    await page.getByRole("button", { name: "Guardar" }).click();

    await expect(page).toHaveURL(/\/socios$/);
    await expect(page.getByText(`Socio registrado: ${FULL_NAME}.`)).toBeVisible();
    await expect(page.getByText(/Falta la autorización/)).toHaveCount(0);
    expect(await axeViolations(page)).toEqual([]);

    await search(page, DOCUMENT);
    await search(page, LAST_NAME);

    // El mismo documento otra vez: 409 con enlace al socio existente.
    await page.goto("/socios/nuevo");
    await page.getByRole("textbox", { name: /^Nombres/ }).fill("Otra");
    await page.getByRole("textbox", { name: /^Apellidos/ }).fill(LAST_NAME);
    await page.getByRole("textbox", { name: /^Número de documento/ }).fill(DOCUMENT);
    await page.getByRole("button", { name: "Guardar" }).click();
    await expect(page.getByRole("link", { name: "Ver socio existente" })).toHaveAttribute("href", /^\/socios\/[0-9a-f-]{36}$/);

    const coach = await crearCoach(page);
    const context = await browser.newContext({ baseURL: process.env.E2E_BASE_URL ?? "" });
    try {
      const coachPage = await context.newPage();
      await coachPage.setViewportSize({ width: 390, height: 844 });
      await loginComo(coachPage, coach);
      await coachPage.goto("/socios");
      await coachPage.getByRole("searchbox", { name: "Buscar" }).fill(LAST_NAME);
      await expect(coachPage.getByRole("link", { name: FULL_NAME })).toBeVisible();
      expect(await axeViolations(coachPage)).toEqual([]);
    } finally {
      await context.close();
      await borrarUsuario(page, coach.id);
    }
  });
});
