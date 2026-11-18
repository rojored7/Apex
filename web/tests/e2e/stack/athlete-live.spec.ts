// V7 (revisión de Fase 4, hueco E2E) contra el stack de Compose: guardar un resultado por la pantalla de resultados relee las
// vistas del atleta (invalidateResultViews -> invalidateAthleteViews) SIN recargar la página.
// - Se abre «RMs por movimiento» de un socio (vacío: queda en la caché de TanStack), se navega DENTRO de la SPA a la pantalla de
//   resultados de su clase (history.pushState + popstate: no hay recarga), se valida 100 kg por la interfaz y se vuelve atrás.
//   El RM automático aparece sin recargar; sin la invalidación se vería la lista vacía de la caché. Un marcador en `window` prueba
//   que la página nunca se recargó.
// Datos: una clase de hoy con un WOD por carga (movimiento principal en kg) y el socio presente. Después de las 23:49 de Bogotá
// la spec se omite. Sin E2E_BASE_URL se omite.
// ESCRITA, SIN CORRER: la ejecuta el orquestador contra el stack (P-E2E), no el agente que la escribió.
import { expect, test } from "@playwright/test";
import { axeViolations } from "../helpers/axe";
import { ahoraMas, asegurarMovimientoKg, cancelarClase, crearClaseDeHoy, crearSocio, darDeBajaSocio, diaBogota, diaLibreDeWod, loginComo, PRIMER_DIA_WOD, sameOriginHeaders, type SocioCreado } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const API = "/api/v1";

test.describe("La pestaña Atleta se actualiza al guardar un resultado, contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con A3 y C2; en preview no hay api");

  const socios: SocioCreado[] = [];
  const sesiones: string[] = [];
  test.afterEach(async ({ page }) => {
    const fallos: Error[] = [];
    try {
      for (const socio of socios.splice(0)) await darDeBajaSocio(page, socio.id);
    } catch (error) {
      fallos.push(error instanceof Error ? error : new Error(String(error)));
    }
    // Con resultados la clase no se cancela (409 locked_by_results): cancelarClase tolera solo eso.
    for (const id of sesiones.splice(0)) {
      try {
        await cancelarClase(page, id);
      } catch (error) {
        fallos.push(error instanceof Error ? error : new Error(String(error)));
      }
    }
    if (fallos[0]) throw fallos[0];
  });

  test("validar 100 kg en la pantalla de resultados deja el RM nuevo en Atleta sin recargar", async ({ page }) => {
    const inicio = ahoraMas(10);
    test.skip(diaBogota(inicio) !== diaBogota(new Date()), "después de las 23:49 de Bogotá la clase de hoy no cabe en el día");
    await page.setViewportSize({ width: 1440, height: 900 });
    const headers = { Authorization: `Bearer ${await loginComo(page)}`, ...sameOriginHeaders() };

    const movimiento = await asegurarMovimientoKg(page, headers);
    const nombre = `Vivo E2E ${Date.now().toString(36)}`;
    const sesionId = await crearClaseDeHoy(page, headers, inicio, nombre);
    sesiones.push(sesionId);
    const wod = await page.request.post(`${API}/wods`, {
      headers,
      data: { date: await diaLibreDeWod(page, PRIMER_DIA_WOD), title: nombre, description: "", score_type: "load", movements: [{ movement_id: movimiento.id, position: 1, reps: "1", is_primary: true, notes: "" }] },
    });
    expect(wod.ok()).toBe(true);
    const wodId = ((await wod.json()) as { id: string }).id;
    expect((await page.request.patch(`${API}/class-sessions/${sesionId}`, { headers, data: { wod_id: wodId } })).ok()).toBe(true);
    const socio = await crearSocio(page);
    socios.push(socio);
    expect((await page.request.post(`${API}/attendance`, { headers, data: { session_id: sesionId, member_id: socio.id } })).ok()).toBe(true);

    // RMs vacío: queda en la caché.
    await page.goto(`/socios/${socio.id}/atleta?tab=rms`);
    await expect(page.getByText("Todavía no hay RMs registrados. Usa «Registrar récord» para guardar el primero.")).toBeVisible();
    await page.evaluate(() => {
      (window as unknown as { __sinRecarga: boolean }).__sinRecarga = true;
    });

    // Navegación dentro de la SPA (sin recarga) a la pantalla de resultados de la clase.
    await page.evaluate((ruta) => {
      window.history.pushState({}, "", ruta);
      window.dispatchEvent(new PopStateEvent("popstate"));
    }, `/clases/${sesionId}/resultados`);
    await expect(page.getByRole("heading", { level: 1, name: new RegExp(`^Resultados · ${nombre}`) })).toBeVisible();
    await page.getByRole("list", { name: "Asistieron" }).getByRole("button").first().click();
    await page.getByLabel("Carga (kg)").fill("100");
    await page.getByRole("button", { name: /Guardar y siguiente/ }).click();
    await expect(page.getByLabel("Registrados 1 de 1")).toBeVisible();

    // Atrás: de vuelta a Atleta con el RM nuevo, sin recargar.
    await page.goBack();
    await expect(page).toHaveURL(new RegExp(`/socios/${socio.id}/atleta\\?tab=rms`));
    const fila = page.getByRole("table", { name: "RMs por movimiento del socio" }).getByRole("row").filter({ hasText: movimiento.name });
    await expect(fila).toContainText("100 kg");
    await expect(fila.getByText("Automático del WOD")).toBeVisible();
    expect(await page.evaluate(() => (window as unknown as { __sinRecarga?: boolean }).__sinRecarga)).toBe(true);
    expect(await axeViolations(page)).toEqual([]);
  });
});
