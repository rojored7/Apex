// V7 (revisión de Fase 4, hueco E2E) contra el stack de Compose: lo que la pestaña Atleta NO ofrece según el socio y el rol.
// - Socio dado de baja (admin): sin «Registrar medidas», «Registrar récord», «Anular» ni «Invalidar».
// - Socio sin autorización de datos: «Guardar medidas» deshabilitado con el aviso de H-1 y el enlace a la ficha.
// - Coach: «Mostrar» de una medida de un socio dado de baja da el aviso del 403 (solo un administrador).
// - Anular una medición por la interfaz (ConfirmModal): la fila desaparece, el aviso «Medición anulada.» y el foco al encabezado.
// Los socios se dan de baja al terminar y el coach se borra en un `finally`. Sin E2E_BASE_URL se omite.
// ESCRITA, SIN CORRER: la ejecuta el orquestador contra el stack (P-E2E), no el agente que la escribió.
import { expect, test, type Page } from "@playwright/test";
import { axeViolations } from "../helpers/axe";
import { asegurarMovimientoKg, borrarUsuario, crearCoach, crearSocio, darDeBajaSocio, fechaBogota, loginComo, sameOriginHeaders, type SocioCreado } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const API = "/api/v1";
const WEIGHT_G = 61_200;
const RECORD_G = 80_000;

/** El socio ya tiene una medición y un récord manual (por el api, antes de cualquier baja). */
async function conDatosDelAtleta(page: Page, socio: SocioCreado): Promise<void> {
  const headers = { Authorization: `Bearer ${await loginComo(page)}`, ...sameOriginHeaders() };
  const hoy = fechaBogota();
  const medida = await page.request.post(`${API}/athletes/${socio.id}/metrics`, { headers, data: { measured_on: hoy, weight_g: WEIGHT_G } });
  expect(medida.ok()).toBe(true);
  const movimiento = await asegurarMovimientoKg(page, headers);
  const record = await page.request.post(`${API}/athletes/${socio.id}/records`, { headers, data: { kind: "rm", movement_id: movimiento.id, value_g: RECORD_G, achieved_on: hoy } });
  expect(record.ok()).toBe(true);
}

test.describe("Pestaña Atleta: lo que no se ofrece, contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con A3 y C2; en preview no hay api");

  const socios: SocioCreado[] = [];
  // Un socio que la spec ya dio de baja por su cuenta no vuelve a darse de baja en la limpieza.
  const yaDeBaja = new Set<string>();
  test.afterEach(async ({ page }) => {
    for (const socio of socios.splice(0)) {
      if (!yaDeBaja.delete(socio.id)) await darDeBajaSocio(page, socio.id);
    }
  });

  test("un socio dado de baja no muestra «Registrar», «Anular» ni «Invalidar»", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const socio = await crearSocio(page);
    socios.push(socio);
    await conDatosDelAtleta(page, socio);
    await darDeBajaSocio(page, socio.id);
    yaDeBaja.add(socio.id);

    await page.goto(`/socios/${socio.id}/atleta?tab=medidas`);
    await expect(page.getByText("No encontrada")).toHaveCount(0);
    const medidas = page.getByRole("table", { name: "Medidas corporales del socio" });
    await expect(medidas.getByRole("row")).toHaveCount(2);
    await expect(page.getByRole("button", { name: /Registrar medidas/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /Registrar récord/ })).toHaveCount(0);
    await expect(page.getByRole("button", { name: /^Anular/ })).toHaveCount(0);

    await page.getByRole("tab", { name: "Récords" }).click();
    await expect(page.getByRole("table", { name: "Récords del socio" }).getByRole("row")).toHaveCount(2);
    await expect(page.getByRole("button", { name: /^Invalidar/ })).toHaveCount(0);
    expect(await axeViolations(page)).toEqual([]);
  });

  test("un socio sin autorización de datos deja «Guardar medidas» deshabilitado con el aviso y el enlace a la ficha", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);
    const socio = await crearSocio(page, undefined, false);
    socios.push(socio);

    await page.goto(`/socios/${socio.id}/atleta`);
    await page.getByRole("button", { name: /Registrar medidas/ }).click();
    const panel = page.getByRole("dialog", { name: "Registrar medidas" });

    await expect(panel.getByRole("button", { name: "Guardar medidas" })).toBeDisabled();
    await expect(panel).toContainText("Falta la autorización de datos del socio. Regístrala en su ficha para guardar medidas.");
    await expect(panel.getByRole("link", { name: "Ir a la ficha del socio" })).toHaveAttribute("href", `/socios/${socio.id}`);
    expect(await axeViolations(page)).toEqual([]);
  });

  test("el coach no puede mostrar una medida de un socio dado de baja: el aviso dice que solo un administrador", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const socio = await crearSocio(page);
    socios.push(socio);
    await conDatosDelAtleta(page, socio);
    await darDeBajaSocio(page, socio.id);
    yaDeBaja.add(socio.id);
    const coach = await crearCoach(page);
    try {
      await loginComo(page, coach);
      await page.goto(`/socios/${socio.id}/atleta?tab=medidas`);
      const tabla = page.getByRole("table", { name: "Medidas corporales del socio" });
      await tabla.getByRole("button", { name: /^Mostrar peso/ }).click();

      await expect(tabla.getByRole("alert")).toContainText("Este socio está dado de baja: solo un administrador puede mostrar sus medidas.");
      await expect(tabla).not.toContainText("61,2");
    } finally {
      await borrarUsuario(page, coach.id);
    }
  });

  test("anular una medición por la interfaz: la fila desaparece, se avisa y el foco pasa al encabezado", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const socio = await crearSocio(page);
    socios.push(socio);
    await conDatosDelAtleta(page, socio);

    await page.goto(`/socios/${socio.id}/atleta?tab=medidas`);
    const tabla = page.getByRole("table", { name: "Medidas corporales del socio" });
    await expect(tabla.getByRole("row")).toHaveCount(2);
    await tabla.getByRole("button", { name: /^Anular medición del / }).click();
    await page.getByRole("dialog", { name: "¿Anular esta medición?" }).getByRole("button", { name: "Anular medición" }).click();

    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByText("Todavía no hay medidas registradas. Usa «Registrar medidas» para guardar la primera.")).toBeVisible();
    await expect(page.getByRole("status", { name: "Avisos del atleta" })).toHaveText("Medición anulada.");
    await expect(page.getByRole("heading", { level: 2, name: "Medidas corporales" })).toBeFocused();
    expect(await axeViolations(page)).toEqual([]);
  });
});
