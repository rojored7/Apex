// S8-F6 (US-177, S8-D20): prueba de resistencia de la pantalla de TV. Acelera 12 horas con `page.clock` (el reloj es falso: no tarda
// 12 horas), responde GET /tv/today con un tablero fijo de 20 filas (hay rotación de páginas) por `page.route` y mide el heap de
// JavaScript por CDP con una recolección forzada al final de cada cuarto de la corrida. Pasa si el heap del último cuarto no supera
// en más de 20 % al del primero (sin fuga) y si la pantalla sigue mostrando el tablero y pidiendo datos al final.
// No necesita el stack ni docker: sirve el build con `vite preview` (playwright.soak.config.ts). La corre nightly.yml; a mano:
// `npm run soak`. ESCRITA, SIN CORRER en el Sprint 8 (regla de no correr E2E en F6): la primera corrida real deja el heap en el cuaderno.
//
// Modo en tiempo real (S9-X3, S9-D24): con `SOAK_REAL_HOURS=<horas>` (número mayor que 0 y como máximo 5,5) corre OTRA prueba, sin
// `page.clock`: el reloj, los temporizadores y la recolección de memoria son los reales, y el modo acelerado se omite. Mismas
// respuestas fijas por `page.route`. Toma una muestra del heap por CDP cada 10 minutos (`SOAK_SAMPLE_MINUTES` la acorta para
// corridas cortas; debe dar al menos 4 muestras). Las muestras se reparten en 4 cuartos contiguos y pasa si el promedio del último
// no supera en más de 20 % al del primero y si no hubo ningún error de consola ni de página. Escribe las muestras en
// `SOAK_SUMMARY_FILE` (por defecto `test-results/soak-real-heap.md`) y en la salida; el job tv-soak-real las lleva a
// $GITHUB_STEP_SUMMARY. Ejemplo local de 2 minutos: `SOAK_REAL_HOURS=0.03 SOAK_SAMPLE_MINUTES=0.4 npm run soak`.
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname } from "node:path";
import { expect, test, type CDPSession, type Page } from "@playwright/test";

const HOUR_MS = 3_600_000;
const QUARTERS = 4;
const HOURS_PER_QUARTER = 3;
const STEP_MS = 5 * 60_000;
const MAX_GROWTH = 1.2;
const TOKEN = "tokenDeResistencia0123456789abcdefABCDEF";
const MINUTE_MS = 60_000;
const MAX_REAL_HOURS = 5.5;
const DEFAULT_SAMPLE_MINUTES = 10;
const MIN_SAMPLES = 4;
const REFRESH_MS = 30_000;
const TEST_MARGIN_MS = 10 * MINUTE_MS;
const NUMERIC = /^\d+(\.\d+)?$/;
const DEFAULT_SUMMARY_FILE = "test-results/soak-real-heap.md";

/** Lee un número de una variable de entorno; `undefined` si no está definida o está vacía, error si no es un número finito. */
function envNumber(name: string): number | undefined {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === "") return undefined;
  const value = Number(raw);
  if (!NUMERIC.test(raw.trim()) || !Number.isFinite(value)) throw new Error(`${name} debe ser un número (recibido: ${JSON.stringify(raw)})`);
  return value;
}

const REAL_HOURS = envNumber("SOAK_REAL_HOURS");
if (REAL_HOURS !== undefined && (REAL_HOURS <= 0 || REAL_HOURS > MAX_REAL_HOURS)) {
  throw new Error(`SOAK_REAL_HOURS debe ser mayor que 0 y como máximo ${String(MAX_REAL_HOURS)} (recibido: ${String(REAL_HOURS)})`);
}
const SAMPLE_MINUTES = envNumber("SOAK_SAMPLE_MINUTES") ?? DEFAULT_SAMPLE_MINUTES;
if (SAMPLE_MINUTES <= 0) throw new Error(`SOAK_SAMPLE_MINUTES debe ser mayor que 0 (recibido: ${String(SAMPLE_MINUTES)})`);

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
  test.skip(REAL_HOURS !== undefined, "modo SOAK_REAL_HOURS: corre la prueba en tiempo real");
  // V7 L12: el modo acelerado también recoge los errores de consola y de página, como el modo real.
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
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
  expect(errors).toEqual([]);
  expect(requests).toBeGreaterThan(1000);
  expect(last).toBeLessThanOrEqual(first * MAX_GROWTH);
});

function quarterMeans(samples: readonly number[]): number[] {
  const groups: number[][] = Array.from({ length: QUARTERS }, () => []);
  samples.forEach((value, index) => groups[Math.floor((index * QUARTERS) / samples.length)]?.push(value));
  return groups.map((group) => group.reduce((sum, value) => sum + value, 0) / group.length);
}

function summary(hours: number, sampleMs: number, samples: readonly number[], means: readonly number[], requests: number, errors: readonly string[]): string {
  const mib = (bytes: number): string => (bytes / 1_048_576).toFixed(2);
  const lines = [
    "### TV en tiempo real (tv-soak-real)",
    `Horas: ${String(hours)} | intervalo de muestra: ${(sampleMs / MINUTE_MS).toFixed(2)} min | muestras: ${String(samples.length)} | peticiones al tablero: ${String(requests)} | errores de consola: ${String(errors.length)}`,
    "",
    "| Muestra | Heap (MiB) |",
    "| --- | --- |",
    ...samples.map((value, index) => `| ${String(index + 1)} | ${mib(value)} |`),
    "",
    `Promedio por cuarto (MiB): ${means.map(mib).join(" / ")}`,
    `Último / primero: ${((means[QUARTERS - 1] ?? 0) / (means[0] || 1)).toFixed(3)} (tope ${String(MAX_GROWTH)})`,
  ];
  return `${lines.join("\n")}\n`;
}

test("la TV aguanta en tiempo real sin fuga de memoria ni errores de consola", async ({ page }) => {
  test.skip(REAL_HOURS === undefined, "defina SOAK_REAL_HOURS (0 < horas <= 5,5) para correr la prueba en tiempo real");
  const hours = REAL_HOURS ?? 0;
  const totalMs = hours * HOUR_MS;
  const sampleMs = SAMPLE_MINUTES * MINUTE_MS;
  const sampleCount = Math.floor(totalMs / sampleMs);
  if (sampleCount < MIN_SAMPLES) {
    throw new Error(`con ${String(hours)} h y muestras cada ${String(SAMPLE_MINUTES)} min salen ${String(sampleCount)} muestras; se necesitan al menos ${String(MIN_SAMPLES)} (acorte SOAK_SAMPLE_MINUTES)`);
  }
  test.setTimeout(totalMs + TEST_MARGIN_MS);

  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  let requests = 0;
  await page.route("**/api/v1/tv/today", async (route) => {
    requests += 1;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(board()) });
  });
  await page.route("**/api/v1/auth/logout", (route) => route.fulfill({ status: 204 }));
  await page.setViewportSize({ width: 1920, height: 1080 });
  const client = await page.context().newCDPSession(page);
  await client.send("Performance.enable");

  await page.goto(`/tv#token=${TOKEN}`);
  await expect(page.getByRole("heading", { name: "Helen" })).toBeVisible();
  expect(new URL(page.url()).hash).toBe("");

  const samples: number[] = [];
  for (let index = 0; index < sampleCount; index += 1) {
    await page.waitForTimeout(sampleMs);
    await expect(page.getByRole("heading", { name: "Helen" })).toBeVisible();
    samples.push(await heapBytes(client));
    process.stdout.write(`soak-real muestra ${String(index + 1)}/${String(sampleCount)} heap=${String(Math.round(samples[index] ?? 0))} bytes\n`);
  }

  const means = quarterMeans(samples);
  const report = summary(hours, sampleMs, samples, means, requests, errors);
  const file = process.env.SOAK_SUMMARY_FILE ?? DEFAULT_SUMMARY_FILE;
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, report);
  process.stdout.write(report);
  test.info().annotations.push({ type: "heap-muestras-bytes", description: samples.map((value) => String(Math.round(value))).join(" ") });

  expect(errors).toEqual([]);
  expect(requests).toBeGreaterThanOrEqual(Math.max(2, Math.floor(totalMs / REFRESH_MS / 2)));
  expect(means[QUARTERS - 1] ?? Number.POSITIVE_INFINITY).toBeLessThanOrEqual((means[0] ?? 0) * MAX_GROWTH);
});
