// S9-X2 (S9-D23, E6) contra el stack de Compose: el cierre del modo tablet por inactividad.
// E6: el servidor NO tiene plazo propio de inactividad del quiosco (`auth/kiosk.py` solo guarda la marca en la sesión de
// refresh); el único plazo es el del front, `TABLET_IDLE_MS` (10 min, GymLayout). Al vencer, `useIdleTimeout` llama a
// `logoutDevice()` -> POST /auth/logout: revoca el refresh, borra la marca y la cookie, y la tablet vuelve a /login.
// Reloj falso (`page.clock`) instalado ANTES de navegar: no se espera de verdad. El reloj del servidor es el real, así que el
// access de 15 min sigue vigente por JWT; lo que prueba "el api ya no acepta la sesión" es el refresh revocado (401).
// Necesita la cuenta del admin del seed (E2E_ADMIN_EMAIL y E2E_ADMIN_PASSWORD) y crea su coach y su clase de hoy. Sin E2E_BASE_URL se omite.
import { expect, test, type Page } from "@playwright/test";
import { TABLET_IDLE_MS } from "../../../src/layouts/idle";
import { ahoraMas, borrarUsuario, cancelarClase, crearCoach, diaBogota, loginComo, MS_MINUTO, sameOriginHeaders, type CoachCreado } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const API = "/api/v1";
const CHECKIN = /\/clases\/[^/]+\/checkin$/;
const UN_SEGUNDO = 1_000;
const ESPERA_MS = 15_000;

interface Preparado {
  coach: CoachCreado;
  sesionId: string;
  adminToken: string;
}

/** Un coach propio y una clase de hoy (POST /class-sessions); `offsetMin` distinto por caso evita el 409 session_duplicate. */
async function preparar(page: Page, offsetMin: number): Promise<Preparado> {
  const adminToken = await loginComo(page);
  const response = await page.request.post(`${API}/class-sessions`, {
    headers: { Authorization: `Bearer ${adminToken}`, ...sameOriginHeaders() },
    data: { starts_at: ahoraMas(offsetMin).toISOString(), duration_min: 60, capacity: 5, name: `E2E idle ${String(Date.now())}` },
  });
  if (!response.ok()) throw new Error(`POST /class-sessions respondió ${String(response.status())}.`);
  const sesionId = ((await response.json()) as { id: string }).id;
  return { coach: await crearCoach(page), sesionId, adminToken };
}

/** Entra al quiosco de la clase con la cuenta del coach y espera a que el servidor active la marca. */
async function entrarAlQuiosco(page: Page, p: Preparado): Promise<void> {
  await loginComo(page, p.coach);
  const kiosk = page.waitForResponse((r) => r.request().method() === "POST" && new URL(r.url()).pathname === `${API}/auth/kiosk`);
  await page.goto(`/clases/${p.sesionId}/checkin`);
  expect((await kiosk).status()).toBe(200);
  await expect(page).toHaveURL(CHECKIN);
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Check-in");
  // Modo tablet: ningún enlace al panel.
  await expect(page.getByRole("link")).toHaveCount(0);
}

test.describe("cierre del modo tablet por inactividad contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL)");
  // Las clases de hoy empiezan dentro de 40 y 41 minutos: pasadas las 23:19 de Bogotá cruzarían la medianoche.
  test.skip(diaBogota(ahoraMas(41)) !== diaBogota(new Date()), "las clases de hoy no caben en el día");

  test("sin tocar la pantalla 10 minutos, la tablet cierra la sesión y el api la rechaza", async ({ page, context }) => {
    test.setTimeout(90_000);
    await page.clock.install();
    await page.setViewportSize({ width: 1024, height: 768 });
    const p = await preparar(page, 40);
    try {
      await entrarAlQuiosco(page, p);
      const refrescos: string[] = [];
      page.on("request", (request) => {
        const ruta = new URL(request.url()).pathname;
        if (ruta === `${API}/auth/refresh`) refrescos.push(ruta);
      });
      const cookie = (await context.cookies()).find((c) => c.name === "apex_refresh");
      expect(cookie).toBeDefined();

      const logout = page.waitForResponse((r) => new URL(r.url()).pathname === `${API}/auth/logout`, { timeout: ESPERA_MS });
      await page.clock.fastForward(TABLET_IDLE_MS + UN_SEGUNDO);

      expect((await logout).status()).toBe(204);
      await expect(page).toHaveURL(/\/login/);
      await expect(page.getByRole("heading", { level: 1, name: "Iniciar sesión" })).toBeVisible();
      expect((await context.cookies()).find((c) => c.name === "apex_refresh")).toBeUndefined();
      // Si el reloj hubiera rotado la cookie antes del cierre, el 401 de abajo no probaría la revocación.
      expect(refrescos).toEqual([]);

      // El api ya no acepta la sesión: ni renovar el access ni volver a marcar el quiosco con esa cookie.
      const headers = { Cookie: `apex_refresh=${cookie?.value ?? ""}`, ...sameOriginHeaders() };
      const refresh = await page.request.post(`${API}/auth/refresh`, { headers });
      expect(refresh.status()).toBe(401);
      const marca = await page.request.post(`${API}/auth/kiosk`, { headers, data: { path: `/clases/${p.sesionId}/checkin` } });
      expect(marca.status()).toBe(401);
    } finally {
      // Un fallo del borrado del coach no se salta la cancelación de la clase, y un fallo de la cancelación (no un 409 por resultados) también falla.
      try {
        await borrarUsuario(page, p.coach.id);
      } finally {
        await cancelarClase(page, p.sesionId);
      }
    }
  });

  test("un toque al minuto 9 reinicia la cuenta: al minuto 10 sigue dentro y recién a los 10 desde el toque se cierra", async ({ page, context }) => {
    test.setTimeout(90_000);
    await page.clock.install();
    await page.setViewportSize({ width: 1024, height: 768 });
    const p = await preparar(page, 41);
    try {
      await entrarAlQuiosco(page, p);
      const cierres: string[] = [];
      page.on("request", (request) => {
        const ruta = new URL(request.url()).pathname;
        if (ruta === `${API}/auth/logout`) cierres.push(ruta);
      });

      await page.clock.fastForward(9 * MS_MINUTO);
      await expect(page).toHaveURL(CHECKIN);
      // Un gesto real del puntero (el hook escucha pointermove y pointerdown) reinicia los 10 minutos.
      await page.mouse.move(40, 40);
      await page.mouse.move(80, 90);

      // Minuto 10 desde el inicio: sin el toque ya habría cerrado.
      await page.clock.fastForward(MS_MINUTO + UN_SEGUNDO);
      await expect(page).toHaveURL(CHECKIN);
      await expect(page.getByRole("heading", { level: 1 })).toContainText("Check-in");
      expect(cierres).toEqual([]);
      expect((await context.cookies()).find((c) => c.name === "apex_refresh")).toBeDefined();

      // Contraprueba: 10 minutos sin tocar desde el gesto sí cierran.
      const logout = page.waitForResponse((r) => new URL(r.url()).pathname === `${API}/auth/logout`, { timeout: ESPERA_MS });
      await page.clock.fastForward(TABLET_IDLE_MS);
      expect((await logout).status()).toBe(204);
      await expect(page).toHaveURL(/\/login/);
    } finally {
      // Un fallo del borrado del coach no se salta la cancelación de la clase, y un fallo de la cancelación (no un 409 por resultados) también falla.
      try {
        await borrarUsuario(page, p.coach.id);
      } finally {
        await cancelarClase(page, p.sesionId);
      }
    }
  });
});
