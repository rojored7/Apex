// US-053 T8: "el coach no ve Planes". Contra `vite preview`, con /auth/refresh y /auth/me
// simulados por page.route (la sesión real la ejerce la variante contra el stack en la
// validación del sprint, V4). El coach escribe /planes y /sistema/configuracion en la barra y
// ve "Sin permiso"; el menú no muestra Planes ni Sistema; el admin ve los dos.
import { expect, test, type Page } from "@playwright/test";

type TestRole = "admin" | "coach";

async function sessionAs(page: Page, role: TestRole): Promise<void> {
  await page.route("**/api/v1/auth/refresh", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ access_token: `e2e-${role}`, token_type: "bearer", expires_in: 900 }) }),
  );
  await page.route("**/api/v1/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "11111111-1111-4111-8111-111111111111",
        email: `${role}@apex.test`,
        role,
        member_id: null,
        gym_name: "Box E2E",
        must_change_password: false,
      }),
    }),
  );
}

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
});

for (const path of ["/planes", "/sistema/configuracion"]) {
  test(`el coach que abre ${path} ve Sin permiso y el menú no muestra Planes ni Sistema`, async ({ page }) => {
    await sessionAs(page, "coach");
    await page.goto(path);

    await expect(page.getByRole("heading", { level: 1, name: "Sin permiso" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Ir al inicio" })).toHaveAttribute("href", "/");
    const nav = page.getByRole("navigation", { name: "Menú principal" });
    await expect(nav.getByRole("link", { name: "Socios" })).toBeVisible();
    for (const label of ["Planes", "Usuarios y roles", "Configuración"]) await expect(nav.getByRole("link", { name: label })).toHaveCount(0);
  });
}

test("el admin ve Planes y Sistema y entra a /planes", async ({ page }) => {
  await sessionAs(page, "admin");
  await page.goto("/planes");

  await expect(page.getByRole("heading", { level: 1, name: "Planes" })).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Menú principal" });
  await expect(nav.getByRole("link", { name: "Planes" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Usuarios y roles" })).toBeVisible();
  await expect(nav.getByRole("link", { name: "Configuración" })).toBeVisible();
});

test("sin sesión /socios lleva a /login?next=/socios", async ({ page }) => {
  await page.route("**/api/v1/auth/refresh", (route) =>
    route.fulfill({ status: 401, contentType: "application/json", body: JSON.stringify({ error: { code: "invalid_refresh", message: "Tu sesión terminó." } }) }),
  );
  await page.goto("/socios");

  await expect(page.getByRole("heading", { level: 1, name: "Iniciar sesión" })).toBeVisible();
  const url = new URL(page.url());
  expect(url.pathname).toBe("/login");
  expect(url.searchParams.get("next")).toBe("/socios");
});

test("una ruta de una versión futura da No encontrada", async ({ page }) => {
  await sessionAs(page, "admin");
  await page.goto("/clases");

  await expect(page.getByRole("heading", { level: 1, name: "No encontrada" })).toBeVisible();
});

test("el token de acceso no queda en localStorage ni en sessionStorage", async ({ page }) => {
  await sessionAs(page, "admin");
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1, name: "Hola, admin@apex.test" })).toBeVisible();
  const stored = await page.evaluate(() =>
    [localStorage, sessionStorage]
      .flatMap((storage) => Array.from({ length: storage.length }, (_, i) => storage.getItem(storage.key(i) ?? "") ?? ""))
      .join("|"),
  );
  expect(stored).not.toContain("e2e-admin");
});
