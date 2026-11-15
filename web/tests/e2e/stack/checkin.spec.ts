// S7-F4 (US-159, US-161, S7-D24, S7-D27) contra el stack de Compose: el check-in en modo tablet. Corre en V5, no en F4.
// Cubre: socio al día y socio vencido en la misma sesión, el duplicado (409), una sesión de otro día que registra con la bandera
// «Otro día» y sin 409, la tiquetera de 10 clases (10 → 9 al registrar → 10 al quitar), que durante la prueba no sale ninguna
// petición a /reveal ni /members/{id}, y la salida del modo tablet con la contraseña. axe en cada paso.
// Necesita C1 a C3 y la cuenta del admin del seed (E2E_ADMIN_EMAIL y E2E_ADMIN_PASSWORD). Sin E2E_BASE_URL se omite.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import {
  crearPlan,
  crearSocio,
  darDeBajaSocio,
  datosDeBase,
  esperarTransiciones,
  fechaBogota,
  loginComo,
  sameOriginHeaders,
  venderMembresia,
  venderMembresiaDesde,
  type SocioCreado,
} from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const API = "/api/v1";

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

interface SesionCreada {
  id: string;
}

/** Sesión extra por el api (POST /class-sessions, S7-D11) a una hora de Bogotá dada; `dias` la mueve respecto de hoy. */
async function crearSesion(page: Page, token: string, dias: number): Promise<SesionCreada> {
  const headers = { Authorization: `Bearer ${token}` };
  const dia = fechaBogota(dias);
  const response = await page.request.post(`${API}/class-sessions`, { headers, data: { starts_at: `${dia}T17:00:00-05:00`, duration_min: 60, capacity: 12, name: `E2E ${String(Date.now())}` } });
  if (!response.ok()) throw new Error(`POST /class-sessions respondió ${String(response.status())}.`);
  return (await response.json()) as SesionCreada;
}

async function clasesQuedan(page: Page, token: string, socioId: string): Promise<number | null> {
  const response = await page.request.get(`${API}/members/${socioId}/memberships`, { headers: { Authorization: `Bearer ${token}` } });
  const body = (await response.json()) as { items: { classes_remaining: number | null }[] };
  return body.items[0]?.classes_remaining ?? null;
}

async function buscar(page: Page, nombre: string): Promise<void> {
  await page.getByRole("searchbox", { name: "Buscar socio" }).fill(nombre);
  await expect(page.getByRole("list", { name: "Socios encontrados" })).toBeVisible();
}

test.describe("check-in en modo tablet contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con C1 a C3");

  const socios: SocioCreado[] = [];

  test.afterEach(async ({ page }) => {
    for (const socio of socios.splice(0)) await darDeBajaSocio(page, socio.id);
  });

  test("al día, vencido, duplicado, otro día, tiquetera y salida con contraseña", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    const token = await loginComo(page);
    const llamadas: string[] = [];
    page.on("request", (request) => llamadas.push(new URL(request.url()).pathname));

    const alDia = await crearSocio(page);
    const vencido = await crearSocio(page);
    const tiquetera = await crearSocio(page);
    socios.push(alDia, vencido, tiquetera);
    const plan = await crearPlan(page);
    await venderMembresia(page, alDia.id, plan.id, { amount_cop: plan.precio, method: "cash" });
    await venderMembresiaDesde(page, vencido.id, plan.id, fechaBogota(-60), { amount_cop: plan.precio, method: "cash" });
    const headers = { Authorization: `Bearer ${token}`, ...sameOriginHeaders() };
    const diez = await page.request.post(`${API}/plans`, { headers, data: { name: `0 E2E diez ${String(Date.now())}`, price_cop: 150_000, kind: "classes", duration_days: 60, class_count: 10 } });
    const planDiez = (await diez.json()) as { id: string };
    await venderMembresia(page, tiquetera.id, planDiez.id, { amount_cop: 150_000, method: "cash" });
    const hoy = await crearSesion(page, token, 0);
    const otroDia = await crearSesion(page, token, 7);

    await page.goto(`/clases/${hoy.id}/checkin`);
    await expect(page.getByRole("heading", { level: 1 })).toContainText("Check-in");
    expect(await axeViolations(page)).toEqual([]);
    // Modo tablet: ningún enlace al panel.
    await expect(page.getByRole("link")).toHaveCount(0);

    // Al día: «Llegó», sin bandera.
    await buscar(page, alDia.nombre);
    await page.getByRole("button", { name: "Llegó", exact: true }).click();
    await expect(page.getByRole("status", { name: "Resultado del check-in" })).toContainText(`${alDia.nombre} llegó.`);
    // Duplicado: 409 con su mensaje.
    await buscar(page, alDia.nombre);
    await expect(page.getByRole("button", { name: "Ya llegó" })).toBeDisabled();

    // Vencido: entra igual y queda marcado.
    await buscar(page, vencido.nombre);
    await page.getByRole("button", { name: "Llegó igual" }).click();
    await expect(page.getByRole("list", { name: "Asistentes" }).getByText("Vencido")).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);

    // Tiquetera: 10 → 9 al registrar → 10 al quitar.
    expect(await clasesQuedan(page, token, tiquetera.id)).toBe(10);
    await buscar(page, tiquetera.nombre);
    await page.getByRole("button", { name: "Llegó", exact: true }).click();
    await expect(page.getByRole("list", { name: "Asistentes" }).getByText(tiquetera.nombre)).toBeVisible();
    expect(await clasesQuedan(page, token, tiquetera.id)).toBe(9);
    await page.getByRole("button", { name: `Quitar a ${tiquetera.nombre}` }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Quitar asistencia" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(await clasesQuedan(page, token, tiquetera.id)).toBe(10);

    // Otra fecha: 201 con la bandera «Otro día», sin 409 y sin error.
    await page.goto(`/clases/${otroDia.id}/checkin`);
    await buscar(page, alDia.nombre);
    await page.getByRole("button", { name: "Llegó", exact: true }).click();
    await expect(page.getByRole("list", { name: "Asistentes" }).getByText("Otro día")).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);

    // La tablet nunca revela datos cifrados ni lee la ficha.
    expect(llamadas.filter((ruta) => ruta.includes("/reveal"))).toEqual([]);
    expect(llamadas.filter((ruta) => /\/members\/[^/]+$/.test(ruta) && !ruta.endsWith("/members/export"))).toEqual([]);

    // Salir del modo tablet exige la contraseña.
    await page.getByRole("button", { name: "Clases" }).click();
    const dialogo = page.getByRole("dialog", { name: "¿Salir del modo tablet?" });
    await dialogo.getByLabel(/Contraseña/).fill("contraseña-equivocada");
    await dialogo.getByRole("button", { name: "Salir del modo tablet" }).click();
    await expect(dialogo.getByRole("alert")).toContainText("Contraseña incorrecta");
    await dialogo.getByLabel(/Contraseña/).fill(datosDeBase().password);
    await dialogo.getByRole("button", { name: "Salir del modo tablet" }).click();
    await expect(page).toHaveURL(/\/clases$/);
  });
});
