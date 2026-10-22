// S2-F4a (US-045 a US-048) contra el stack de Compose (proyecto `stack`, V4 del plan): el
// admin crea un coach desde Usuarios, copia el enlace de activación, lo abre en otra ventana
// (otro contexto, sin la sesión del admin), fija una contraseña de 12 o más caracteres y entra
// como coach a `/`. El coach no ve Usuarios ni Configuración. axe en cada pantalla.
// Necesita B2/B3 (login, refresh, /auth/me) y B4 (POST /users, POST /auth/reset). Sin
// E2E_BASE_URL se omite: la variante contra `vite preview` es ../users-access.spec.ts.
// Idempotente: correo y contraseña únicos por corrida (V4 corre las specs dos veces).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { esperarTransiciones, loginComo } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const RUN = Date.now().toString(36);
const COACH_EMAIL = `coach-activa-${RUN}@apex.test`;
const COACH_PASSWORD = `Coach-activa-${RUN}-e2e!`;

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test.describe("alta y activación de un coach contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B2 a B4; en preview corre users-access.spec.ts");

  test("el admin crea un coach, el coach activa su cuenta con el enlace y entra sin Usuarios ni Configuración", async ({ page, browser, context }) => {
    await context.grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);

    // 1. Admin: lista y alta.
    await page.goto("/sistema/usuarios");
    await expect(page.getByRole("heading", { level: 1, name: /Usuarios del sistema/ })).toBeVisible();
    await expect(page.getByRole("table", { name: "Usuarios" })).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);

    await page.getByRole("button", { name: "Nuevo usuario del equipo" }).click();
    const panel = page.getByRole("dialog", { name: "Nuevo usuario del equipo" });
    await panel.getByRole("textbox", { name: /^Correo/ }).fill(COACH_EMAIL);
    await panel.getByRole("combobox", { name: /^Rol/ }).selectOption("coach");
    await panel.getByRole("button", { name: "Crear usuario" }).click();

    const linkBox = panel.getByRole("textbox", { name: "Enlace de activación" });
    await expect(linkBox).toBeVisible();
    await expect(panel.getByText("Entrega este enlace por un medio seguro; vence en 72 horas.")).toBeVisible();
    const link = await linkBox.inputValue();
    expect(link).toMatch(/\/restablecer\/[A-Za-z0-9_-]{20,}$/);
    await panel.getByRole("button", { name: "Copiar" }).click();
    await expect(panel.getByText("Enlace copiado.")).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(link);
    expect(await axeViolations(page)).toEqual([]);

    // Al cerrar, el enlace ya no está en la página.
    await panel.getByRole("button", { name: "Listo" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(await page.content()).not.toContain(link);

    // El coach aparece pendiente de activación (la búsqueda nunca va a la URL, S2-D41).
    await page.getByRole("searchbox", { name: "Buscar" }).fill(COACH_EMAIL);
    const row = page.getByRole("row").filter({ hasText: COACH_EMAIL });
    await expect(row.getByText("Pendiente de activación")).toBeVisible();
    expect(page.url()).not.toContain("coach-activa");

    // 2. Otra ventana, sin la sesión del admin: activar con el enlace.
    const coachContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const coach = await coachContext.newPage();
    await coach.goto(new URL(link).pathname);
    await expect(coach.getByRole("heading", { level: 1, name: "Nueva contraseña" })).toBeVisible();
    await expect.poll(() => new URL(coach.url()).pathname).toBe("/restablecer");
    expect(await axeViolations(coach)).toEqual([]);

    await coach.getByLabel(/^Contraseña nueva/).fill(COACH_PASSWORD);
    await coach.getByLabel(/^Repite la contraseña nueva/).fill(COACH_PASSWORD);
    await coach.getByRole("button", { name: "Guardar contraseña" }).click();
    await expect(coach.getByRole("heading", { level: 1, name: "Iniciar sesión" })).toBeVisible();
    await expect(coach.getByText("Tu contraseña quedó guardada. Inicia sesión con ella.")).toBeVisible();

    // 3. El coach entra a / y su menú no tiene Usuarios ni Configuración.
    await coach.getByRole("textbox", { name: "Correo" }).fill(COACH_EMAIL);
    await coach.getByLabel("Contraseña").fill(COACH_PASSWORD);
    await coach.getByRole("button", { name: "Entrar" }).click();
    await expect.poll(() => new URL(coach.url()).pathname).toBe("/");
    const nav = coach.getByRole("navigation", { name: "Menú principal" });
    await expect(nav.getByRole("link", { name: "Inicio" })).toBeVisible();
    await expect(nav.getByRole("link", { name: "Usuarios y roles" })).toHaveCount(0);
    await expect(nav.getByRole("link", { name: "Configuración" })).toHaveCount(0);
    expect(await axeViolations(coach)).toEqual([]);

    // El enlace ya se usó: abrirlo otra vez no sirve.
    const again = await coachContext.newPage();
    await again.goto(new URL(link).pathname);
    await again.getByLabel(/^Contraseña nueva/).fill(`${COACH_PASSWORD}2`);
    await again.getByLabel(/^Repite la contraseña nueva/).fill(`${COACH_PASSWORD}2`);
    await again.getByRole("button", { name: "Guardar contraseña" }).click();
    await expect(again.getByRole("alert")).toHaveText("El enlace ya no es válido. Pide uno nuevo al administrador.");

    await coachContext.close();
  });
});
