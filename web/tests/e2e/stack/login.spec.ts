// S2-F3 · US-042 contra el stack de Compose (proyecto `stack`, V4 del plan): la pantalla de
// login real contra el api real. Necesita B2 (login, refresh y cookie) y B3 (GET /auth/me).
// Sin E2E_BASE_URL se omite; la variante contra `vite preview` con el api simulado es
// ../login-form.spec.ts. Idempotente: no crea datos (V4 corre las specs dos veces).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { datosDeBase } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;

async function entrar(page: Page, email: string, password: string): Promise<void> {
  await page.getByRole("textbox", { name: "Correo" }).fill(email);
  await page.getByLabel("Contraseña").fill(password);
  await page.getByRole("button", { name: "Entrar" }).click();
}

test.describe("login contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B2 y B3; en preview corre login-form.spec.ts");

  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test("el admin entra, ve Inicio con su gimnasio y la recarga conserva la sesión", async ({ page }) => {
    const admin = datosDeBase();
    await page.goto("/login");
    const axe = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(axe.violations).toEqual([]);

    await entrar(page, admin.email, admin.password);

    await expect(page).toHaveURL(/\/$/);
    await expect(page.getByRole("heading", { level: 1, name: /Hola/ })).toBeVisible();
    await expect(page.getByRole("banner")).toContainText(admin.email);
    const cookies = await page.context().cookies();
    const refresh = cookies.find((c) => c.name === "apex_refresh");
    expect(refresh?.httpOnly).toBe(true);
    expect(refresh?.path).toBe("/api/v1/auth");
    expect(refresh?.sameSite).toBe("Strict");

    await page.reload();
    await expect(page.getByRole("heading", { level: 1, name: /Hola/ })).toBeVisible();
    const stored = await page.evaluate(() => [localStorage, sessionStorage].map((s) => Array.from({ length: s.length }, (_, i) => `${s.key(i) ?? ""}=${s.getItem(s.key(i) ?? "") ?? ""}`).join("|")).join("|"));
    expect(stored).not.toMatch(/eyJ[\w-]+\.[\w-]+\./);
  });

  test("una contraseña mala da el error genérico, conserva el correo y no abre sesión", async ({ page }) => {
    const admin = datosDeBase();
    await page.goto("/login");

    await entrar(page, admin.email, `${admin.password}-mala`);

    await expect(page.getByRole("alert")).toContainText("Correo o contraseña incorrectos");
    await expect(page.getByRole("textbox", { name: "Correo" })).toHaveValue(admin.email);
    await expect(page.getByLabel("Contraseña")).toHaveValue("");
    await expect(page).toHaveURL(/\/login/);
  });

  test("con next de una ruta del rol vuelve ahí tras entrar", async ({ page }) => {
    const admin = datosDeBase();
    await page.goto("/sistema/configuracion");
    await expect(page).toHaveURL(/\/login\?next=%2Fsistema%2Fconfiguracion$/);

    await entrar(page, admin.email, admin.password);

    await expect(page).toHaveURL(/\/sistema\/configuracion$/);
    await expect(page.getByRole("heading", { level: 1, name: /Configuración/ })).toBeVisible();
  });

  test("el api rechaza un login desde otro origen con 403 sin tocar la cookie", async ({ page }) => {
    const admin = datosDeBase();
    const response = await page.request.post("/api/v1/auth/login", {
      headers: { Origin: "https://otro.example" },
      data: admin,
    });

    expect(response.status()).toBe(403);
    expect(response.headers()["set-cookie"] ?? "").not.toContain("apex_refresh=");
  });
});
