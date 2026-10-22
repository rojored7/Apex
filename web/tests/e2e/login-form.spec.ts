// S2-F3 (US-042, US-044) contra `vite preview`: la pantalla de login y el cierre de sesión en
// un navegador real con el api simulado por page.route. La variante contra el stack (cookie,
// refresh y base reales) es stack/login.spec.ts. Accesibilidad con @axe-core/playwright,
// sin desborde a 320, 390 y 1440 px, y capturas en test-results/captures/.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const EMAIL = "admin@apex.test";

const json = (route: Route, status: number, body: unknown, headers: Record<string, string> = {}) =>
  route.fulfill({ status, contentType: "application/json", headers, body: JSON.stringify(body) });

const ME = { id: "11111111-1111-4111-8111-111111111111", email: EMAIL, role: "admin", member_id: null, gym_name: "Box E2E", must_change_password: false };

async function fakeAuth(page: Page, login: (route: Route) => Promise<void>): Promise<void> {
  await page.route("**/api/v1/auth/refresh", (route) => json(route, 401, { error: { code: "invalid_refresh", message: "x" } }));
  await page.route("**/api/v1/auth/login", login);
  await page.route("**/api/v1/auth/me", (route) => json(route, 200, ME));
}

const loginOk = (route: Route) =>
  json(route, 200, { access_token: "e2e-access", token_type: "bearer", expires_in: 900, must_change_password: false, user: { id: ME.id, email: EMAIL, role: "admin" } });

async function entrar(page: Page, password = "Clave-segura-2026"): Promise<void> {
  await page.getByRole("textbox", { name: "Correo" }).fill(EMAIL);
  await page.getByLabel("Contraseña").fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
}

async function noOverflow(page: Page): Promise<void> {
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
}

for (const width of [320, 390, 1440]) {
  test(`la tarjeta de login a ${String(width)} px pasa axe, no desborda y tiene captura`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await fakeAuth(page, loginOk);
    await page.goto("/login");

    await expect(page.getByRole("heading", { level: 1, name: "Iniciar sesión" })).toBeVisible();
    await expect(page.getByRole("textbox", { name: "Correo" })).toBeFocused();
    const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
    expect(result.violations).toEqual([]);
    await noOverflow(page);
    await page.screenshot({ path: `test-results/captures/login-light-${String(width)}.png`, fullPage: true });
  });
}

test("el admin entra y llega a Inicio con el nombre del gimnasio de me", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await fakeAuth(page, loginOk);
  await page.goto("/login");

  await entrar(page);

  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { level: 1, name: /Hola/ })).toBeVisible();
  await expect(page.getByRole("banner")).toContainText("Box E2E");
  const stored = await page.evaluate(() => [localStorage, sessionStorage].map((s) => Array.from({ length: s.length }, (_, i) => `${s.key(i) ?? ""}=${s.getItem(s.key(i) ?? "") ?? ""}`).join("|")).join("|"));
  expect(stored).not.toContain("e2e-access");
});

test("credenciales malas: error sobre la tarjeta, conserva el correo y el error pasa axe", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fakeAuth(page, (route) => json(route, 401, { error: { code: "invalid_credentials", message: "x" } }));
  await page.goto("/login");

  await entrar(page, "mala");

  await expect(page.getByRole("alert")).toHaveText("Correo o contraseña incorrectos. Revísalos e intenta de nuevo.");
  await expect(page.getByRole("textbox", { name: "Correo" })).toHaveValue(EMAIL);
  await expect(page.getByLabel("Contraseña")).toHaveValue("");
  await expect(page.getByLabel("Contraseña")).toBeFocused();
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  expect(result.violations).toEqual([]);
  await page.screenshot({ path: "test-results/captures/login-error-light-390.png", fullPage: true });
});

test("429: cuenta atrás de Retry-After con el botón bloqueado", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await fakeAuth(page, (route) => json(route, 429, { error: { code: "rate_limited", message: "x" } }, { "Retry-After": "2" }));
  await page.goto("/login");

  await entrar(page);

  await expect(page.getByRole("alert")).toContainText("Demasiados intentos. Espera");
  await expect(page.getByRole("button", { name: "Entrar" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Entrar" })).toBeEnabled({ timeout: 5_000 });
  await expect(page.getByRole("alert")).toHaveText("Ya puedes intentarlo de nuevo.");
});

test("H-1: cerrar sesión con el servidor caído limpia y avisa en /login", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await fakeAuth(page, loginOk);
  await page.route("**/api/v1/auth/logout", (route) => json(route, 502, "bad gateway"));
  await page.goto("/login");
  await entrar(page);
  await expect(page.getByRole("heading", { level: 1, name: /Hola/ })).toBeVisible();

  await page.getByRole("banner").getByRole("button", { name: /admin@apex\.test/ }).click();
  await page.getByRole("menuitem", { name: "Cerrar sesión" }).click();

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("status")).toContainText("No se pudo cerrar la sesión en el servidor.");
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  expect(result.violations).toEqual([]);
});
