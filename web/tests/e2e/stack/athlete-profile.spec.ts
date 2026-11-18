// S9-F1 (US-178, US-179, US-184; H-1, L-7) contra el stack de Compose: la pestaña Atleta de la ficha.
// - Un socio ficticio recién creado CON autorización de datos abre la pestaña Atleta (Resumen por defecto, sin «No encontrada»).
// - Registra una medición desde «Registrar medidas», revela el peso (61,2 kg) y lo ve; ningún valor llega en la lista.
// - S9-F3: `?tab=benchmarks` muestra «Fran» y su serie (un resultado de 4:05 creado por el api en una clase de hoy).
// - `?tab=medidas` se conserva al recargar y abrir la pestaña NO pide ninguna vez `/reveal` (solo el clic en «Mostrar peso»).
// Sin E2E_BASE_URL se omite. ESCRITO POR EL ROJO: la ejecuta el orquestador contra el stack (P-E2E), no el agente de pruebas.
import { expect, test } from "@playwright/test";
import { axeViolations } from "../helpers/axe";
import { ahoraMas, cancelarClase, crearClaseDeHoy, crearSocio, darDeBajaSocio, diaBogota, diaLibreDeWod, loginComo, PRIMER_DIA_WOD, sameOriginHeaders, type SocioCreado } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const WEIGHT_KG = "61,2";
const API = "/api/v1";

test.describe("Pestaña Atleta de la ficha contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con A3 y C2; en preview no hay api");

  const socios: SocioCreado[] = [];
  const sesiones: string[] = [];
  test.afterEach(async ({ page }) => {
    const porCancelar = sesiones.splice(0);
    const fallos: Error[] = [];
    try {
      for (const socio of socios.splice(0)) await darDeBajaSocio(page, socio.id);
    } catch (error) {
      // La baja falló: la cancelación de clases se intenta igual y el fallo se relanza al final.
      fallos.push(error instanceof Error ? error : new Error(String(error)));
    }
    // Con resultados la clase no se cancela (409 locked_by_results, por diseño, S9-D68): cancelarClase tolera solo eso; cualquier otra respuesta falla. Los WODs de 2033 no se borran (no hay borrado de WODs por diseño).
    for (const id of porCancelar) {
      try {
        await cancelarClase(page, id);
      } catch (error) {
        fallos.push(error instanceof Error ? error : new Error(String(error)));
      }
    }
    if (fallos[0]) throw fallos[0];
  });

  test("abre la ficha y la pestaña Atleta, registra una medición, revela el peso y lo ve", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);
    const socio = await crearSocio(page);
    socios.push(socio);
    const reveals: string[] = [];
    page.on("request", (request) => {
      if (request.method() === "POST" && request.url().includes("/reveal")) reveals.push(request.url());
    });

    await page.goto(`/socios/${socio.id}`);
    await page.getByRole("tab", { name: "Atleta" }).click();
    await expect(page.getByText("No encontrada")).toHaveCount(0);
    await expect(page).toHaveURL(new RegExp(`/socios/${socio.id}/atleta`));
    await expect(page.getByRole("tab", { name: "Resumen" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("heading", { level: 2, name: "Medidas corporales" })).toBeVisible();
    await expect(page.getByText("Todavía no hay medidas registradas.")).toBeVisible();

    await page.getByRole("button", { name: /Registrar medidas/ }).click();
    const panel = page.getByRole("dialog", { name: "Registrar medidas" });
    await panel.getByLabel(/^Peso/).fill(WEIGHT_KG);
    await panel.getByRole("button", { name: "Guardar medidas" }).click();
    await expect(panel).toBeHidden();

    await page.getByRole("tab", { name: "Medidas corporales" }).click();
    await expect(page).toHaveURL(/tab=medidas/);
    const table = page.getByRole("table", { name: "Medidas corporales del socio" });
    await expect(table).toBeVisible();
    await expect(table.getByRole("button", { name: /^Mostrar peso/ })).toBeVisible();
    await expect(table).not.toContainText(WEIGHT_KG);
    expect(reveals).toEqual([]);

    await table.getByRole("button", { name: /^Mostrar peso/ }).click();
    await expect(table.getByText(`${WEIGHT_KG} kg`)).toBeVisible();
    expect(reveals).toHaveLength(1);
    expect(decodeURIComponent(page.url())).not.toContain(WEIGHT_KG);
    expect(await axeViolations(page)).toEqual([]);
  });

  test("?tab=medidas se conserva al recargar y abrir la pestaña no pide ningún reveal", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await loginComo(page);
    const socio = await crearSocio(page);
    socios.push(socio);
    const reveals: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/reveal")) reveals.push(request.url());
    });

    await page.goto(`/socios/${socio.id}/atleta?tab=medidas`);
    await expect(page.getByRole("tab", { name: "Medidas corporales" })).toHaveAttribute("aria-selected", "true");
    await page.reload();

    await expect(page).toHaveURL(/tab=medidas/);
    await expect(page.getByRole("tab", { name: "Medidas corporales" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByText("Todavía no hay medidas registradas. Usa «Registrar medidas» para guardar la primera.")).toBeVisible();
    expect(reveals).toEqual([]);
  });

  test("?tab=benchmarks muestra «Fran» y su serie con la marca de un resultado de 4:05", async ({ page }) => {
    // La clase de hoy empieza dentro de 10 minutos (el check-in no bloquea por hora, N-38): pasadas las 23:49 de Bogotá cruzaría la medianoche.
    const inicio = ahoraMas(10);
    test.skip(diaBogota(inicio) !== diaBogota(new Date()), "después de las 23:49 de Bogotá la clase de hoy no cabe en el día");
    await page.setViewportSize({ width: 1440, height: 900 });
    const headers = { Authorization: `Bearer ${await loginComo(page)}`, ...sameOriginHeaders() };

    // Datos: el benchmark Fran lo siembra `seed-benchmarks`; un WOD de Fran en un día libre de 2033, una clase de hoy y 245 s (4:05) validados.
    const benchmarks = (await (await page.request.get(`${API}/benchmarks?limit=200&offset=0`, { headers })).json()) as { items: { id: string; name: string }[] };
    const fran = benchmarks.items.find((item) => item.name === "Fran");
    expect(fran, "falta el benchmark Fran: corre seed-benchmarks").toBeDefined();
    const nombre = `Fran E2E ${Date.now().toString(36)}`;
    const wodDate = await diaLibreDeWod(page, PRIMER_DIA_WOD);
    const sesionId = await crearClaseDeHoy(page, headers, inicio, nombre);
    sesiones.push(sesionId);
    // El api exige de 1 a 30 movimientos por WOD (`validate_wod`): basta uno activo cualquiera, sin carga.
    const activos = (await (await page.request.get(`${API}/movements?limit=1&offset=0&active=true`, { headers })).json()) as { items: { id: string }[] };
    const movimientoId = activos.items[0]?.id;
    expect(movimientoId, "hace falta un movimiento activo en el catálogo").toBeDefined();
    const movements = [{ movement_id: movimientoId, position: 1, reps: "21-15-9", is_primary: false, notes: "" }];
    const wod = await page.request.post(`${API}/wods`, { headers, data: { date: wodDate, title: "Fran", description: "", score_type: "time", benchmark_id: fran?.id, movements } });
    expect(wod.ok()).toBe(true);
    const wodId = ((await wod.json()) as { id: string }).id;
    expect((await page.request.patch(`${API}/class-sessions/${sesionId}`, { headers, data: { wod_id: wodId } })).ok()).toBe(true);
    const socio = await crearSocio(page);
    socios.push(socio);
    expect((await page.request.post(`${API}/attendance`, { headers, data: { session_id: sesionId, member_id: socio.id } })).ok()).toBe(true);
    const registro = await page.request.put(`${API}/results`, { headers, data: { member_id: socio.id, wod_id: wodId, session_id: sesionId, level: "rx", seconds: 245 } });
    expect(registro.ok()).toBe(true);

    await page.goto(`/socios/${socio.id}/atleta?tab=benchmarks`);
    await expect(page.getByText("No encontrada")).toHaveCount(0);
    await expect(page.getByRole("tab", { name: "Benchmarks" })).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("button", { name: "Fran", exact: true })).toHaveAttribute("aria-pressed", "true");
    const tabla = page.getByRole("table", { name: "Intentos del socio en Fran" });
    const fila = tabla.getByRole("row").filter({ hasText: "4:05" });
    await expect(fila.getByText("Mejor")).toBeVisible();
    await expect(fila).toContainText("RX");
    await expect(fila).toContainText("Primera vez");
    await expect(page.getByRole("img", { name: /Fran: 1 punto/ })).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);
  });
});
