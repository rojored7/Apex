import { expect, test } from "@playwright/test";

test("la página mínima carga APEX con fuentes locales y sin peticiones externas", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (request) => {
    requests.push(request.url());
  });

  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1, name: "APEX" })).toBeVisible();
  await expect(page.getByText("Año, Bogotá, ÑANDÚ")).toBeVisible();

  const fonts = await page.evaluate(async () => {
    await document.fonts.ready;
    await Promise.all([
      document.fonts.load("16px Michroma"),
      document.fonts.load("400 16px 'Titillium Web'"),
      document.fonts.load("600 16px 'Titillium Web'"),
      document.fonts.load("700 16px 'Titillium Web'"),
    ]);
    const loaded = [...document.fonts].filter((face) => face.status === "loaded").map((face) => `${face.family} ${face.weight}`);
    return {
      michroma: document.fonts.check("16px Michroma"),
      titillium: document.fonts.check("16px 'Titillium Web'"),
      loaded,
    };
  });

  expect(fonts.michroma).toBe(true);
  expect(fonts.titillium).toBe(true);
  expect(fonts.loaded.some((f) => f.includes("Michroma"))).toBe(true);
  expect(fonts.loaded.some((f) => f.includes("Titillium Web"))).toBe(true);

  const external = requests.filter((url) => {
    const { hostname, protocol } = new URL(url);
    return !(protocol === "data:" || hostname === "localhost" || hostname === "127.0.0.1");
  });
  expect(external).toEqual([]);
});
