// S8-F6 (US-177, S8-D20): prueba de resistencia de la pantalla de TV. Acelera 12 horas con `page.clock` (el reloj es falso: no tarda
// 12 horas), responde GET /tv/today con un tablero fijo de 20 filas (hay rotación de páginas) por `page.route` y mide el heap de
// JavaScript por CDP con una recolección forzada al final de cada cuarto de la corrida. Pasa si el heap del último cuarto no supera
// en más de 20 % al del primero (sin fuga) y si la pantalla sigue mostrando el tablero y pidiendo datos al final.
// No necesita el stack ni docker: sirve el build con `vite preview` (playwright.soak.config.ts). La corre nightly.yml; a mano:
// `npm run soak`. ESCRITA, SIN CORRER en el Sprint 8 (regla de no correr E2E en F6): la primera corrida real deja el heap en el cuaderno.
import { expect, test, type CDPSession, type Page } from "@playwright/test";

const HOUR_MS = 3_600_000;
const QUARTERS = 4;
const HOURS_PER_QUARTER = 3;
const STEP_MS = 5 * 60_000;
const MAX_GROWTH = 1.2;
const TOKEN = "tokenDeResistencia0123456789abcdefABCDEF";

function board(): unknown {
  const leaderboard = Array.from({ length: 20 }, (_, index) => ({
    display_name: `Atleta ${String(index + 1)} X.`,
    level: "rx",
    position: index + 1,
    score: { capped: false, load_g: null, reps: null, rounds: null, seconds: 600 + index },
  }));
  return {
    date: "2026-10-20",
    refresh_seconds: 30,
    show_leaderboard: true,
    wod: {
      title: "Helen",
      description: "3 rondas por tiempo",
      is_benchmark: true,
      score_type: "time",
      time_cap_s: 1200,
      movements: [
        { name: "Run 400 m", reps: "1", load_rx_m_g: null, load_rx_f_g: null },
        { name: "Kettlebell swing", reps: "21", load_rx_m_g: 24000, load_rx_f_g: 16000 },
        { name: "Pull-up", reps: "12", load_rx_m_g: null, load_rx_f_g: null },
      ],
    },
    leaderboard,
  };
}

async function heapBytes(client: CDPSession): Promise<number> {
  await client.send("HeapProfiler.collectGarbage");
  const { metrics } = await client.send("Performance.getMetrics");
  const used = metrics.find((metric) => metric.name === "JSHeapUsedSize");
  if (used === undefined) throw new Error("CDP no devolvió JSHeapUsedSize");
  return used.value;
}

async function runFor(page: Page, totalMs: number): Promise<void> {
  for (let elapsed = 0; elapsed < totalMs; elapsed += STEP_MS) await page.clock.runFor(Math.min(STEP_MS, totalMs - elapsed));
}

test("la TV aguanta 12 horas sin fuga de memoria", async ({ page }) => {
  let requests = 0;
  await page.route("**/api/v1/tv/today", async (route) => {
    requests += 1;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(board()) });
  });
  await page.route("**/api/v1/auth/logout", (route) => route.fulfill({ status: 204 }));
  await page.clock.install({ time: new Date("2026-10-20T11:00:00Z") });
  await page.setViewportSize({ width: 1920, height: 1080 });
  const client = await page.context().newCDPSession(page);
  await client.send("Performance.enable");

  await page.goto(`/tv#token=${TOKEN}`);
  await expect(page.getByRole("heading", { name: "Helen" })).toBeVisible();
  expect(new URL(page.url()).hash).toBe("");

  const heaps: number[] = [];
  for (let quarter = 0; quarter < QUARTERS; quarter += 1) {
    await runFor(page, HOURS_PER_QUARTER * HOUR_MS);
    await expect(page.getByRole("heading", { name: "Helen" })).toBeVisible();
    heaps.push(await heapBytes(client));
  }

  const first = heaps[0] ?? 0;
  const last = heaps[QUARTERS - 1] ?? Number.POSITIVE_INFINITY;
  test.info().annotations.push({ type: "heap-por-cuarto-bytes", description: heaps.map((value) => String(Math.round(value))).join(" ") });
  expect(requests).toBeGreaterThan(1000);
  expect(last).toBeLessThanOrEqual(first * MAX_GROWTH);
});
