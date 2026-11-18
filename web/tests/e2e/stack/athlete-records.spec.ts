// S9-F2 (US-180, US-181; L-4) contra el stack de Compose: RMs y Récords de la pestaña Atleta.
// - Un resultado de 100 kg (WOD por carga con un movimiento principal en kg, en una clase de hoy) crea el RM automático: se ve en
//   «RMs por movimiento» (100 kg, «Automático del WOD») y en «Récords» (Vigente, enlace al WOD, sin «Invalidar»).
// - Se corrige el resultado a 90 kg (PUT /results con supersedes_id): el récord de 100 kg queda invalidado («Resultado corregido»)
//   y el RM vigente pasa a 90 kg.
// Solo la cuenta del admin del seed (no crea coach, así que no hay `borrarUsuario`); el socio se da de baja y la clase se cancela al terminar
// (el WOD de 2033 se queda: el api no borra WODs). Segundo caso: registrar un récord manual por el panel y luego invalidarlo.
// Si no hay un movimiento activo en kg, lo crea con un nombre ficticio único.
// Sin E2E_BASE_URL se omite. ESCRITO POR EL ROJO: la ejecuta el orquestador contra el stack (P-E2E), no el agente de pruebas.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { crearSocio, darDeBajaSocio, diaLibreDeWod, esperarTransiciones, loginComo, sameOriginHeaders, type SocioCreado } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const API = "/api/v1";
const MS_MINUTO = 60_000;
const BOGOTA_OFFSET_MS = 5 * 60 * 60 * 1_000;
const FIRST_DAY = Date.UTC(2033, 0, 1);
const LOAD_G = 100_000;
const CORRECTED_G = 90_000;

interface Movimiento {
  id: string;
  name: string;
}

/** Un movimiento activo que se mide en kg: el primero que haya o, si no hay ninguno, uno nuevo con nombre ficticio único. */
async function asegurarMovimientoKg(page: Page, headers: Record<string, string>): Promise<Movimiento> {
  const lista = (await (await page.request.get(`${API}/movements?limit=200&offset=0&active=true`, { headers })).json()) as { items: { id: string; name: string; unit: string }[] };
  const existente = lista.items.find((item) => item.unit === "kg");
  if (existente !== undefined) return existente;
  const nombre = `Mov kg E2E ${Date.now().toString(36)}`;
  const creado = await page.request.post(`${API}/movements`, { headers, data: { name: nombre, category: "weightlifting", unit: "kg" } });
  expect(creado.ok()).toBe(true);
  return { id: ((await creado.json()) as { id: string }).id, name: nombre };
}

/**
 * Crea la clase de hoy en `inicio` o en el primer minuto libre de los cinco siguientes. Una clase con resultados no se puede
 * cancelar (409 `locked_by_results`, por diseño), así que la de una corrida anterior sigue «programada» y repetir el minuto da
 * 409 `session_duplicate`.
 */
async function crearClaseDeHoy(page: Page, headers: Record<string, string>, inicio: Date, nombre: string): Promise<string> {
  for (let intento = 0; intento < 5; intento += 1) {
    const startsAt = new Date(inicio.getTime() + intento * MS_MINUTO).toISOString();
    const respuesta = await page.request.post(`${API}/class-sessions`, { headers, data: { starts_at: startsAt, duration_min: 60, capacity: 10, name: nombre } });
    if (respuesta.ok()) return ((await respuesta.json()) as { id: string }).id;
    const codigo = ((await respuesta.json().catch(() => ({}))) as { error?: { code?: string } }).error?.code;
    if (respuesta.status() !== 409 || codigo !== "session_duplicate") throw new Error(`POST /class-sessions respondió ${String(respuesta.status())}.`);
  }
  throw new Error("POST /class-sessions: los cinco minutos siguientes ya tienen una clase de esta spec.");
}

const diaBogota = (instante: Date): string => new Date(instante.getTime() - BOGOTA_OFFSET_MS).toISOString().slice(0, 10);

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

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
    // Las clases no se borran: se cancelan. Con resultados no se puede (409 locked_by_results, por diseño): solo eso se tolera; cualquier otra respuesta falla.
    if (porCancelar.length > 0) {
      const headers = { Authorization: `Bearer ${await loginComo(page)}`, ...sameOriginHeaders() };
      for (const id of porCancelar) {
        const cancelada = await page.request.post(`${API}/class-sessions/${id}/cancel`, { headers, data: { reason: "limpieza E2E" } });
        if (!cancelada.ok() && cancelada.status() !== 409) fallos.push(new Error(`POST /class-sessions/{id}/cancel respondió ${String(cancelada.status())}.`));
      }
    }
    if (fallos[0]) throw fallos[0];
  });

  test("un resultado de 100 kg crea el RM automático y corregirlo lo deja invalidado", async ({ page }) => {
    // La clase de hoy empieza dentro de 10 minutos (el check-in no bloquea por hora, N-38): pasadas las 23:49 de Bogotá cruzaría la medianoche.
    const inicio = new Date(Math.floor((Date.now() + 10 * MS_MINUTO) / MS_MINUTO) * MS_MINUTO);
    test.skip(diaBogota(inicio) !== diaBogota(new Date()), "después de las 23:49 de Bogotá la clase de hoy no cabe en el día");
    await page.setViewportSize({ width: 1440, height: 900 });
    const adminToken = await loginComo(page);
    const headers = { Authorization: `Bearer ${adminToken}`, ...sameOriginHeaders() };

    // Datos: un movimiento activo en kg, un WOD por carga con ese movimiento principal, una clase de hoy con el socio presente.
    const movimiento = await asegurarMovimientoKg(page, headers);
    const nombre = `Récords E2E ${Date.now().toString(36)}`;
    const wodDate = await diaLibreDeWod(page, FIRST_DAY);
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
    await expect(filaRecord).toContainText("Se corrige corrigiendo el resultado que lo originó.");
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
