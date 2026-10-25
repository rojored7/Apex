// S3-F5 (US-089, US-090; demo 5 del blueprint, S3-D72) contra el stack de Compose (proyecto
// `stack`). El admin crea por el api tres socios (documento aleatorio por corrida) y un plan:
// 1. Una membresía activa (pago completo): la congela 10 días desde hoy por el modal de /membresias,
//    ve el aviso con el nuevo fin y el estado "Congelado".
// 2. Una membresía vendida 7 días atrás con dos congelaciones ya terminadas (por el api): la tercera
//    por el modal da el 409 `freeze_limit_reached` ("ya usó todas las congelaciones").
// 3. Una pendiente de pago (sin pago): la anula con motivo y ve "Cancelado".
// axe en cada paso; al terminar da de baja a los socios (baja lógica). Se corre en V4 (sin Docker
// desde el worktree); sin E2E_BASE_URL se omite.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import {
  congelarPorApi,
  crearPlan,
  crearSocio,
  darDeBajaSocio,
  esperarTransiciones,
  fechaBogota,
  loginComo,
  venderMembresia,
  venderMembresiaDesde,
  type SocioCreado,
} from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const REASON = "Membresía vendida por error en la prueba";

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

/** Busca al socio por su documento (índice ciego) en /membresias y devuelve su fila. */
async function findRow(page: Page, socio: SocioCreado) {
  await page.goto("/membresias?status=active,expiring,expired,frozen,pending_payment,cancelled");
  await page.getByRole("searchbox", { name: "Buscar socio" }).fill(socio.documento);
  const row = page.getByRole("row", { name: new RegExp(socio.nombre) });
  await expect(row).toHaveCount(1);
  return row;
}

test.describe("congelar y anular membresías contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B2, B6 y B7; se corre en V4");

  const socios: SocioCreado[] = [];

  test.afterEach(async ({ page }) => {
    for (const socio of socios.splice(0)) await darDeBajaSocio(page, socio.id);
  });

  test("congela 10 días, la tercera congelación da 409 y anula una pendiente", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const plan = await crearPlan(page);
    const activa = await crearSocio(page);
    const limite = await crearSocio(page);
    const pendiente = await crearSocio(page);
    socios.push(activa, limite, pendiente);
    expect((await venderMembresia(page, activa.id, plan.id, { amount_cop: plan.precio, method: "cash" })).status).toBe("active");
    const conDos = await venderMembresiaDesde(page, limite.id, plan.id, fechaBogota(-7), { amount_cop: plan.precio, method: "cash" });
    expect(await congelarPorApi(page, conDos.id, fechaBogota(-7), fechaBogota(-6))).toBe(200);
    expect(await congelarPorApi(page, conDos.id, fechaBogota(-5), fechaBogota(-4))).toBe(200);
    expect((await venderMembresia(page, pendiente.id, plan.id)).status).toBe("pending_payment");
    await loginComo(page);

    // 1. Congelar 10 días desde hoy.
    let row = await findRow(page, activa);
    await row.getByRole("button", { name: `Congelar la membresía de ${activa.nombre}` }).click();
    let modal = page.getByRole("dialog", { name: `Congelar la membresía de ${activa.nombre}` });
    await expect(modal.getByLabel(/^Desde/)).toHaveValue(fechaBogota(0));
    await modal.getByLabel(/^Hasta/).fill(fechaBogota(9));
    await expect(modal.getByText(/^Son 10 días; la membresía terminará el /)).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
    await modal.getByRole("button", { name: "Congelar" }).click();
    await expect(modal).toHaveCount(0);
    await expect(page.getByText(`Membresía de ${activa.nombre} congelada. Ahora termina el `, { exact: false })).toBeVisible();
    row = await findRow(page, activa);
    await expect(row).toContainText("Congelado");

    // 2. La tercera congelación: 409 freeze_limit_reached en el modal.
    row = await findRow(page, limite);
    await row.getByRole("button", { name: `Congelar la membresía de ${limite.nombre}` }).click();
    modal = page.getByRole("dialog", { name: `Congelar la membresía de ${limite.nombre}` });
    await modal.getByLabel(/^Hasta/).fill(fechaBogota(1));
    await modal.getByRole("button", { name: "Congelar" }).click();
    await expect(modal.getByRole("alert")).toHaveText("Esta membresía ya usó todas las congelaciones que permite el gimnasio.");
    expect(await axeViolations(page)).toEqual([]);
    await modal.getByRole("button", { name: "Volver" }).click();

    // 3. Anular la pendiente con motivo.
    row = await findRow(page, pendiente);
    await expect(row).toContainText("Pendiente de pago");
    await row.getByRole("button", { name: `Anular la membresía de ${pendiente.nombre}` }).click();
    const cancel = page.getByRole("dialog", { name: `¿Anular la membresía de ${pendiente.nombre}?` });
    await cancel.getByRole("textbox", { name: /^Motivo/ }).fill(REASON);
    expect(await axeViolations(page)).toEqual([]);
    await cancel.getByRole("button", { name: "Sí, anular" }).click();
    await expect(cancel).toHaveCount(0);
    await expect(page.getByText(`Membresía de ${pendiente.nombre} anulada. Sus pagos siguen registrados.`)).toBeVisible();
    row = await findRow(page, pendiente);
    await expect(row).toContainText("Cancelado");
  });
});
