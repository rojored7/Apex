// S8-F4 (US-169, US-170, S8-D15, S8-D31, S8-D40) contra el stack de Compose: /clases/:id/resultados en modo quiosco con la CUENTA DE UN COACH.
// Registra 15 resultados con pausas de tecleo (uno «No terminó», una corrección) y MIDE el tiempo total: debe quedar bajo 5 minutos
// (S8-D40; el valor va al cuaderno como anotación `tiempo-15-resultados`). Comprueba el contador, que el leaderboard del WOD refleja
// todo (en un contexto de admin aparte, para no salir del modo tablet) y que nunca sale una petición a /reveal ni a /members/{id}.
// Necesita B1 a B4, C4 (quiosco), la cuenta del admin del seed y al menos un movimiento activo. Sin E2E_BASE_URL se omite.
// ESCRITO, SIN CORRER: el stack de desarrollo está roto y su reparación espera al usuario (Sprint 8, F4).
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { borrarUsuario, crearCoach, crearSocio, darDeBajaSocio, diaLibreDeWod, esperarTransiciones, loginComo, sameOriginHeaders, type SocioCreado } from "../helpers/stack";

const ON_STACK = process.env.E2E_BASE_URL !== undefined;
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa"];
const API = "/api/v1";
const TOTAL = 15;
const MAX_MS = 5 * 60_000;
const TYPING_PAUSE_MS = 120;
const MS_MINUTO = 60_000;
const BOGOTA_OFFSET_MS = 5 * 60 * 60 * 1_000;
const FIRST_DAY = Date.UTC(2033, 0, 1);

const diaBogota = (instante: Date): string => new Date(instante.getTime() - BOGOTA_OFFSET_MS).toISOString().slice(0, 10);

async function axeViolations(page: Page): Promise<string[]> {
  await esperarTransiciones(page);
  const result = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  return result.violations.map((v) => `${v.id}: ${v.help} -> ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

test.describe("registro de resultados en la tablet contra el stack", () => {
  test.skip(!ON_STACK, "solo contra el stack (E2E_BASE_URL) con B1 a B4 y C4; en preview no hay api");

  const socios: SocioCreado[] = [];
  test.afterEach(async ({ page }) => {
    for (const socio of socios.splice(0)) await darDeBajaSocio(page, socio.id);
  });

  test("15 resultados en quiosco, uno «No terminó» y una corrección, en menos de 5 minutos", async ({ page, browser }) => {
    // Las clases de hoy empiezan dentro de 2 horas: pasadas las 21:00 de Bogotá cruzarían la medianoche.
    const inicio = new Date(Math.floor((Date.now() + 120 * MS_MINUTO) / MS_MINUTO) * MS_MINUTO);
    test.skip(diaBogota(inicio) !== diaBogota(new Date()), "después de las 21:00 de Bogotá la clase de hoy no cabe en el día");
    test.setTimeout(10 * MS_MINUTO);
    await page.setViewportSize({ width: 1024, height: 768 });
    const adminToken = await loginComo(page);
    const WOD_DATE = await diaLibreDeWod(page, FIRST_DAY);
    const headers = { Authorization: `Bearer ${adminToken}`, ...sameOriginHeaders() };

    // Datos: clase de hoy, WOD por tiempo con time cap, 15 asistentes.
    const nombre = `Resultados E2E ${Date.now().toString(36)}`;
    const sesion = await page.request.post(`${API}/class-sessions`, { headers, data: { starts_at: inicio.toISOString(), duration_min: 60, capacity: 30, name: nombre } });
    expect(sesion.ok()).toBe(true);
    const sesionId = ((await sesion.json()) as { id: string }).id;
    const movimientos = (await (await page.request.get(`${API}/movements?limit=1&offset=0&active=true`, { headers })).json()) as { items: { id: string }[] };
    const movimientoId = movimientos.items[0]?.id;
    expect(movimientoId).toBeTruthy();
    const wodRespuesta = await page.request.post(`${API}/wods`, {
      headers,
      data: {
        date: WOD_DATE,
        title: nombre,
        description: "",
        score_type: "time",
        time_cap_s: 1200,
        movements: [{ movement_id: movimientoId, position: 1, reps: "21", is_primary: true, notes: "" }],
      },
    });
    expect(wodRespuesta.ok()).toBe(true);
    const wodId = ((await wodRespuesta.json()) as { id: string }).id;
    expect((await page.request.patch(`${API}/class-sessions/${sesionId}`, { headers, data: { wod_id: wodId } })).ok()).toBe(true);
    for (let i = 0; i < TOTAL; i += 1) {
      const socio = await crearSocio(page);
      socios.push(socio);
      expect((await page.request.post(`${API}/attendance`, { headers, data: { session_id: sesionId, member_id: socio.id } })).ok()).toBe(true);
    }

    const coach = await crearCoach(page);
    try {
      await loginComo(page, coach);
      const llamadas: string[] = [];
      page.on("request", (request) => llamadas.push(new URL(request.url()).pathname));
      await page.goto(`/clases/${sesionId}/resultados`);
      await expect(page.getByRole("heading", { level: 1, name: new RegExp(`^Resultados · ${nombre}`) })).toBeVisible();
      await expect(page.getByText("No encontrada")).toHaveCount(0);
      await expect(page.getByLabel(`Registrados 0 de ${String(TOTAL)}`)).toBeVisible();
      expect(await axeViolations(page)).toEqual([]);

      const empezo = Date.now();
      for (let i = 1; i <= TOTAL; i += 1) {
        const esCorte = i === TOTAL;
        if (esCorte) {
          await page.getByRole("button", { name: "No terminó" }).click();
          await page.getByLabel("Repeticiones completadas").pressSequentially("135", { delay: TYPING_PAUSE_MS });
        } else {
          await page.getByLabel("Tiempo (mm:ss)").pressSequentially(`${String(8 + (i % 10))}:${String(10 + i)}`, { delay: TYPING_PAUSE_MS });
        }
        await page.getByRole("button", { name: /Guardar y siguiente/ }).click();
        await expect(page.getByLabel(`Registrados ${String(i)} de ${String(TOTAL)}`)).toBeVisible();
      }
      const transcurrido = Date.now() - empezo;
      test.info().annotations.push({ type: "tiempo-15-resultados", description: `${String(Math.round(transcurrido / 1000))} s` });
      expect(transcurrido).toBeLessThan(MAX_MS);

      // Corrección: el primero se corrige a 7:07 (PUT con supersedes_id y la misma sesión).
      const lista = page.getByRole("list", { name: "Asistieron" });
      await lista.getByRole("button").first().click();
      const campo = page.getByLabel("Tiempo (mm:ss)");
      await campo.fill("7:07");
      await page.getByRole("button", { name: /Guardar y siguiente/ }).click();
      await expect(lista.getByRole("button").filter({ hasText: "7:07" })).toHaveCount(1);
      await expect(page.getByLabel(`Registrados ${String(TOTAL)} de ${String(TOTAL)}`)).toBeVisible();
      expect(llamadas.filter((path) => path.includes("/reveal") || /\/members\/[^/]+$/.test(path))).toEqual([]);

      // El leaderboard del WOD refleja todo (un contexto de admin aparte: la tablet sigue confinada).
      const contexto = await browser.newContext(process.env.E2E_BASE_URL === undefined ? {} : { baseURL: process.env.E2E_BASE_URL });
      try {
        const otra = await contexto.newPage();
        await loginComo(otra);
        await otra.goto(`/wods/${wodId}`);
        await expect(otra.getByRole("heading", { level: 1, name: nombre })).toBeVisible();
        await expect(otra.getByText("7:07")).toBeVisible();
        await expect(otra.getByText("DNF · 135 reps")).toBeVisible();
        await otra.getByRole("tab", { name: /^Todos los resultados/ }).click();
        await expect(otra.getByText(/en tablet/).first()).toBeVisible();
      } finally {
        await contexto.close();
      }
    } finally {
      await borrarUsuario(page, coach.id);
    }
  });
});
