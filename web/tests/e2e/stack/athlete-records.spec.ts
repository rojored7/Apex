// S9-F2 (US-180, US-181; L-4) contra el stack de Compose: RMs y Récords de la pestaña Atleta.
// - Un resultado de 100 kg (WOD por carga con un movimiento principal en kg, en una clase de hoy) crea el RM automático: se ve en
//   «RMs por movimiento» (100 kg, «Automático del WOD») y en «Récords» (Vigente, enlace al WOD, sin «Invalidar»).
// - Se corrige el resultado a 90 kg (PUT /results con supersedes_id): el récord de 100 kg queda invalidado («Resultado corregido»)
//   y el RM vigente pasa a 90 kg.
// Solo la cuenta del admin del seed (no crea coach, así que no hay `borrarUsuario`); el socio se da de baja y la clase se cancela al terminar
// (el WOD de 2033 se queda: el api no borra WODs). Segundo caso: registrar un récord manual por el panel y luego invalidarlo.
// Si no hay un movimiento activo en kg, lo crea con un nombre ficticio único.
// Sin E2E_BASE_URL se omite. ESCRITO POR EL ROJO: la ejecuta el orquestador contra el stack (P-E2E), no el agente de pruebas.
import { expect, test } from "@playwright/test";
import { axeViolations } from "../helpers/axe";
import { ahoraMas, asegurarMovimientoKg, cancelarClase, crearClaseDeHoy, crearSocio, darDeBajaSocio, diaBogota, diaLibreDeWod, loginComo, PRIMER_DIA_WOD, sameOriginHeaders, type SocioCreado } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const API = "/api/v1";
const LOAD_G = 100_000;
const CORRECTED_G = 90_000;

test.describe("RMs y Récords de la pestaña Atleta contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B1 a B5 y C2; en preview no hay api");

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

  test("un resultado de 100 kg crea el RM automático y corregirlo lo deja invalidado", async ({ page }) => {
    // La clase de hoy empieza dentro de 10 minutos (el check-in no bloquea por hora, N-38): pasadas las 23:49 de Bogotá cruzaría la medianoche.
    const inicio = ahoraMas(10);
    test.skip(diaBogota(inicio) !== diaBogota(new Date()), "después de las 23:49 de Bogotá la clase de hoy no cabe en el día");
    await page.setViewportSize({ width: 1440, height: 900 });
    const adminToken = await loginComo(page);
    const headers = { Authorization: `Bearer ${adminToken}`, ...sameOriginHeaders() };

    // Datos: un movimiento activo en kg, un WOD por carga con ese movimiento principal, una clase de hoy con el socio presente.
    const movimiento = await asegurarMovimientoKg(page, headers);
    const nombre = `Récords E2E ${Date.now().toString(36)}`;
    const wodDate = await diaLibreDeWod(page, PRIMER_DIA_WOD);
    const sesionId = await crearClaseDeHoy(page, headers, inicio, nombre);
    sesiones.push(sesionId);
    const wod = await page.request.post(`${API}/wods`, {
      headers,
      data: { date: wodDate, title: nombre, description: "", score_type: "load", movements: [{ movement_id: movimiento.id, position: 1, reps: "1", is_primary: true, notes: "" }] },
    });
    expect(wod.ok()).toBe(true);
    const wodId = ((await wod.json()) as { id: string }).id;
    expect((await page.request.patch(`${API}/class-sessions/${sesionId}`, { headers, data: { wod_id: wodId } })).ok()).toBe(true);
    const socio = await crearSocio(page);
    socios.push(socio);
    expect((await page.request.post(`${API}/attendance`, { headers, data: { session_id: sesionId, member_id: socio.id } })).ok()).toBe(true);

    // El coach (aquí el admin, por la mesa) valida 100 kg: el api deriva el RM en la misma transacción.
    const registro = await page.request.put(`${API}/results`, { headers, data: { member_id: socio.id, wod_id: wodId, session_id: sesionId, level: "rx", load_g: LOAD_G } });
    expect(registro.ok()).toBe(true);
    const resultadoId = ((await registro.json()) as { id: string }).id;

    // RMs por movimiento: 100 kg, automático del WOD.
    await page.goto(`/socios/${socio.id}/atleta?tab=rms`);
    await expect(page.getByText("No encontrada")).toHaveCount(0);
    const rms = page.getByRole("table", { name: "RMs por movimiento del socio" });
    const filaRm = rms.getByRole("row").filter({ hasText: movimiento.name });
    await expect(filaRm).toContainText("100 kg");
    await expect(filaRm.getByText("Automático del WOD")).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);

    // Récords: vigente con texto, enlace al WOD, explicación y sin «Invalidar».
    await page.getByRole("tab", { name: "Récords" }).click();
    await expect(page).toHaveURL(/tab=records/);
    const records = page.getByRole("table", { name: "Récords del socio" });
    const filaRecord = records.getByRole("row").filter({ hasText: `${movimiento.name} 1RM` });
    await expect(filaRecord).toContainText("100 kg");
    await expect(filaRecord.getByText("Vigente")).toBeVisible();
    await expect(filaRecord.getByRole("link", { name: `Ver el WOD de ${movimiento.name} 1RM` })).toHaveAttribute("href", `/wods/${wodId}`);
    await expect(filaRecord).toContainText("Para cambiarlo, corrige el resultado que lo originó.");
    await expect(filaRecord.getByRole("button", { name: /^Invalidar / })).toHaveCount(0);
    expect(await axeViolations(page)).toEqual([]);

    // Corregir el resultado a 90 kg: el récord de 100 kg queda invalidado y el RM vigente baja a 90 kg.
    const correccion = await page.request.put(`${API}/results`, {
      headers,
      data: { member_id: socio.id, wod_id: wodId, session_id: sesionId, level: "rx", load_g: CORRECTED_G, supersedes_id: resultadoId },
    });
    expect(correccion.ok()).toBe(true);

    await page.goto(`/socios/${socio.id}/atleta?tab=records&invalidated=1`);
    await expect(page.getByRole("button", { name: "Ver invalidados" })).toHaveAttribute("aria-pressed", "true");
    const todos = page.getByRole("table", { name: "Récords del socio" });
    const filaViejo = todos.getByRole("row").filter({ hasText: "100 kg" });
    await expect(filaViejo.getByText("Invalidado")).toBeVisible();
    await expect(filaViejo).toContainText("Resultado corregido");
    await expect(filaViejo.getByText("Vigente")).toHaveCount(0);
    const filaNuevo = todos.getByRole("row").filter({ hasText: "90 kg" });
    await expect(filaNuevo.getByText("Vigente")).toBeVisible();

    await page.getByRole("tab", { name: "RMs por movimiento" }).click();
    await expect(page.getByRole("table", { name: "RMs por movimiento del socio" }).getByRole("row").filter({ hasText: movimiento.name })).toContainText("90 kg");
  });

  test("registrar un récord manual por el panel y luego invalidarlo con la confirmación", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const adminToken = await loginComo(page);
    const headers = { Authorization: `Bearer ${adminToken}`, ...sameOriginHeaders() };
    const movimiento = await asegurarMovimientoKg(page, headers);
    const socio = await crearSocio(page);
    socios.push(socio);

    await page.goto(`/socios/${socio.id}/atleta?tab=records`);
    await expect(page.getByText("Todavía no hay récords registrados. Usa «Registrar récord» para guardar el primero.")).toBeVisible();

    // Registrar: el panel pide movimiento, carga y fecha (hoy); no exige la autorización de datos.
    await page.getByRole("button", { name: /Registrar récord/ }).click();
    const panel = page.getByRole("dialog", { name: "Registrar récord" });
    await panel.getByLabel(/^Movimiento/).selectOption({ label: movimiento.name });
    await panel.getByLabel(/^Carga [(]kg[)]/).fill("80");
    await panel.getByRole("button", { name: "Guardar récord" }).click();
    await expect(page.getByRole("status").filter({ hasText: "Récord guardado." })).toBeVisible();

    const records = page.getByRole("table", { name: "Récords del socio" });
    const fila = records.getByRole("row").filter({ hasText: `${movimiento.name} 1RM` });
    await expect(fila).toContainText("80 kg");
    await expect(fila.getByText("Vigente")).toBeVisible();
    await expect(fila.getByText(/^Manual/)).toBeVisible();
    expect(await axeViolations(page)).toEqual([]);

    // Invalidar: ConfirmModal sin motivo; el récord sale de la lista y reaparece con «Ver invalidados».
    await fila.getByRole("button", { name: /^Invalidar .* 1RM del / }).click();
    await page.getByRole("dialog", { name: "¿Invalidar este récord?" }).getByRole("button", { name: "Invalidar récord" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByText("Todavía no hay récords registrados. Usa «Registrar récord» para guardar el primero.")).toBeVisible();

    await page.getByRole("button", { name: "Ver invalidados" }).click();
    const invalidado = page.getByRole("table", { name: "Récords del socio" }).getByRole("row").filter({ hasText: `${movimiento.name} 1RM` });
    await expect(invalidado.getByText("Invalidado")).toBeVisible();
    await expect(invalidado).toContainText("Error de digitación");
    await expect(invalidado.getByRole("button", { name: /^Invalidar / })).toHaveCount(0);
  });
});
