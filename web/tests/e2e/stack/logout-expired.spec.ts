// S2-F3 · US-044 y H-1 (S2-D35) contra el stack (proyecto `stack`, V4): el cierre de sesión
// se autentica por la cookie, no por el Bearer. Con el access vencido (se envía un Bearer
// inválido), "Cerrar sesión" revoca el refresh, borra la cookie y lleva a /login; recargar `/`
// vuelve a /login y la cookie vieja ya no renueva. Necesita B2 y B3. Sin E2E_BASE_URL se omite.
import { expect, test } from "@playwright/test";
import { loginComo, sameOriginHeaders } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const EXPIRED_BEARER = "Bearer eyJhbGciOiJFZERTQSJ9.eyJleHAiOjF9.vencido";

test.describe("cierre de sesión con el access vencido contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B2 y B3");

  test("tras el logout con el access vencido, recargar / lleva a /login", async ({ page, context }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);
    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: /Hola/ })).toBeVisible();
    const before = (await context.cookies()).find((c) => c.name === "apex_refresh");
    expect(before).toBeDefined();

    await page.route("**/api/v1/auth/logout", (route) =>
      route.continue({ headers: { ...route.request().headers(), authorization: EXPIRED_BEARER } }),
    );
    const logout = page.waitForResponse((r) => r.url().endsWith("/api/v1/auth/logout"));
    await page.getByRole("banner").getByRole("button", { name: /@/ }).click();
    await page.getByRole("menuitem", { name: "Cerrar sesión" }).click();

    expect((await logout).status()).toBe(204);
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("status")).toHaveCount(0);
    expect((await context.cookies()).find((c) => c.name === "apex_refresh")).toBeUndefined();

    await page.goto("/");
    await expect(page).toHaveURL(/\/login\?next=%2F$/);
    await expect(page.getByRole("heading", { level: 1, name: "Iniciar sesión" })).toBeVisible();

    const reused = await page.request.post("/api/v1/auth/refresh", {
      headers: { Cookie: `apex_refresh=${before?.value ?? ""}`, ...sameOriginHeaders() },
    });
    expect(reused.status()).toBe(401);
  });
});
