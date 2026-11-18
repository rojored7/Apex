// S9-F3 · US-183 (Atleta_Perfil.html, subpestaña «Benchmarks»): la serie de un benchmark del socio.
// - GET /athletes/{id}/benchmarks?limit=200&offset=0 (los chips; se piden páginas de 200 hasta 1.000 y se avisa si no caben) y
//   GET /athletes/{id}/benchmarks/{benchmark_id} (la serie: hasta 200 intentos por fecha ascendente, sin paginar).
// - Chips en el grupo «Benchmark» con `?benchmark=<id>`; sin parámetro (o con uno que no está en la lista) vale el primero de la lista.
// - Tabla «Intentos del socio en <nombre>»: Fecha, Marca, Nivel y Diferencia, del intento más reciente al más antiguo (orden descendente, como el diseño).
// - Diferencia con el intento anterior (formatScoreDelta) solo si el nivel no cambió; si cambió, «Cambió de nivel»; el primero, «Primera vez»;
//   si no se puede comparar (rondas + repeticiones, DNF), «—».
// - TrendChart con la misma serie; la tabla es su equivalente accesible.
// DESIGN-GAP: la columna «Escaló» del diseño no está en el contrato; «Solo se compara entre intentos del mismo nivel.» va como nota.
import { useState } from "react";
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import {
  apiError,
  attempt,
  BENCHMARKS_PATH,
  benchmarkId,
  benchmarkRow,
  FRAN_ATTEMPTS,
  FRAN_ROW,
  FRAN_SERIES,
  HELEN_ROW,
  HELEN_SERIES,
  MEMBER_ID,
  pageReply,
  renderAthlete,
  seriesOf,
  seriesPath,
} from "../../../test/athletes";
import { setViewportWidth, type MockHandler, type MockReply, type RecordedCall } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { BenchmarksTab } from "./BenchmarksTab";

const LIST = `GET ${BENCHMARKS_PATH}`;
const FRAN = benchmarkId(1);
const HELEN = benchmarkId(3);
const BASE = `/socios/${MEMBER_ID}/atleta?tab=benchmarks`;

const CINDY_ROW = benchmarkRow({ benchmark_id: benchmarkId(2), name: "Cindy", score_type: "rounds_reps", attempts: 2 });
const CINDY_SERIES = seriesOf(CINDY_ROW, [attempt(21, { wod_date: "2026-05-04", rounds: 5, reps: 12 }), attempt(22, { wod_date: "2026-09-07", rounds: 6, reps: 3, is_best: true })]);
const CLEAN_ROW = benchmarkRow({ benchmark_id: benchmarkId(5), name: "Max Clean", score_type: "load", attempts: 2 });
const CLEAN_SERIES = seriesOf(CLEAN_ROW, [attempt(31, { wod_date: "2026-04-01", load_g: 100_000 }), attempt(32, { wod_date: "2026-08-12", load_g: 102_500, is_best: true })]);
const PULLUPS_ROW = benchmarkRow({ benchmark_id: benchmarkId(4), name: "Max Pull-ups", score_type: "reps", attempts: 2 });
const PULLUPS_SERIES = seriesOf(PULLUPS_ROW, [attempt(41, { wod_date: "2026-02-03", reps: 30 }), attempt(42, { wod_date: "2026-07-14", reps: 35, is_best: true })]);

const ROWS = [FRAN_ROW, HELEN_ROW];
const listOf =
  (rows: readonly unknown[], total = rows.length): MockHandler =>
  (call) =>
    pageReply(call, rows, total);
const ok = (body: unknown): MockReply => ({ status: 200, body });

const defaults = (): Record<string, MockHandler> => ({
  [LIST]: listOf(ROWS),
  [`GET ${seriesPath(FRAN)}`]: ok(FRAN_SERIES),
  [`GET ${seriesPath(HELEN)}`]: ok(HELEN_SERIES),
});

const renderTab = (handlers: Record<string, MockHandler> = {}, route = BASE) => renderAthlete(<BenchmarksTab memberId={MEMBER_ID} />, { handlers: { ...defaults(), ...handlers }, route });
const table = (name = "Fran") => screen.getByRole("table", { name: `Intentos del socio en ${name}` });
const rowOf = (date: string, name = "Fran"): HTMLElement => {
  const found = within(table(name))
    .getAllByRole("row")
    .slice(1)
    .find((row) => row.textContent.includes(date));
  if (!found) throw new Error(`Sin fila ${date}`);
  return found;
};
const cellsOf = (row: HTMLElement): string[] => within(row).getAllByRole("cell").map((cell) => cell.textContent.trim());
const paramsOf = (call: { url: string } | undefined): URLSearchParams => new URL(call?.url ?? "", "http://apex.test").searchParams;

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("coach");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("BenchmarksTab · chips y peticiones", () => {
  it("pide la lista con limit 200 y offset 0 y ofrece un chip por benchmark en el grupo «Benchmark»", async () => {
    const { mock } = renderTab();

    await screen.findByRole("table", { name: "Intentos del socio en Fran" });
    expect(paramsOf(mock.callsTo(LIST)[0]).get("limit")).toBe("200");
    expect(paramsOf(mock.callsTo(LIST)[0]).get("offset")).toBe("0");
    expect(screen.getByRole("heading", { level: 2, name: "Benchmarks" })).toBeInTheDocument();
    const chips = screen.getByRole("group", { name: "Benchmark" });
    expect(within(chips).getAllByRole("button").map((b) => b.textContent)).toEqual(["Fran", "Helen"]);
  });

  it("sin `?benchmark=` queda elegido el primero de la lista y pide solo su serie", async () => {
    const { mock } = renderTab();

    await screen.findByRole("table", { name: "Intentos del socio en Fran" });
    expect(screen.getByRole("button", { name: "Fran" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Helen" })).toHaveAttribute("aria-pressed", "false");
    expect(mock.callsTo(`GET ${seriesPath(FRAN)}`)).toHaveLength(1);
    expect(mock.callsTo(`GET ${seriesPath(HELEN)}`)).toHaveLength(0);
  });

  it("lee `?benchmark=` de la URL al cargar y pide la serie de ese benchmark", async () => {
    const { mock } = renderTab({}, `${BASE}&benchmark=${HELEN}`);

    expect(await screen.findByRole("table", { name: "Intentos del socio en Helen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Helen" })).toHaveAttribute("aria-pressed", "true");
    expect(mock.callsTo(`GET ${seriesPath(FRAN)}`)).toHaveLength(0);
  });

  it("un `?benchmark=` que no está en la lista se ignora: elige el primero y nunca pide esa serie", async () => {
    const stray = benchmarkId(9);
    const { mock } = renderTab({}, `${BASE}&benchmark=${stray}`);

    expect(await screen.findByRole("table", { name: "Intentos del socio en Fran" })).toBeInTheDocument();
    expect(mock.callsTo(`GET ${seriesPath(stray)}`)).toHaveLength(0);
  });

  it("pulsar «Helen» deja `benchmark=<id>` en la URL y pide su serie", async () => {
    const { mock, user } = renderTab();
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    await user.click(screen.getByRole("button", { name: "Helen" }));

    expect(await screen.findByRole("table", { name: "Intentos del socio en Helen" })).toBeInTheDocument();
    expect(screen.getByTestId("where")).toHaveTextContent(`benchmark=${HELEN}`);
    expect(screen.getByRole("button", { name: "Helen" })).toHaveAttribute("aria-pressed", "true");
    expect(mock.callsTo(`GET ${seriesPath(HELEN)}`)).toHaveLength(1);
  });

  it("al cambiar de chip no se mezclan series: mientras llega la de Helen no queda ni una fila de Fran", async () => {
    const { user } = renderTab({ [`GET ${seriesPath(HELEN)}`]: () => new Promise(() => undefined) });
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    await user.click(screen.getByRole("button", { name: "Helen" }));

    await waitFor(() => {
      expect(screen.queryByText("20 oct 2026")).not.toBeInTheDocument();
    });
    expect(screen.queryByRole("table", { name: "Intentos del socio en Fran" })).not.toBeInTheDocument();
    expect(screen.queryByText("4:05")).not.toBeInTheDocument();
  });

  it("carrera: la respuesta tardía de Fran no pisa la de Helen", async () => {
    let release: (reply: MockReply) => void = () => undefined;
    const late = new Promise<MockReply>((resolve) => {
      release = resolve;
    });
    const { user } = renderTab({ [`GET ${seriesPath(FRAN)}`]: () => late });
    await screen.findByRole("button", { name: "Helen" });

    await user.click(screen.getByRole("button", { name: "Helen" }));
    expect(await screen.findByRole("table", { name: "Intentos del socio en Helen" })).toBeInTheDocument();
    release(ok(FRAN_SERIES));

    await waitFor(() => {
      expect(screen.getByRole("table", { name: "Intentos del socio en Helen" })).toBeInTheDocument();
    });
    expect(screen.queryByRole("table", { name: "Intentos del socio en Fran" })).not.toBeInTheDocument();
    expect(screen.queryByText("4:05")).not.toBeInTheDocument();
  });

  it("todas sus consultas cuelgan de [«athlete-benchmarks», id, ...] (así las relee invalidateRecordViews, y solo las de este socio)", async () => {
    const { queryClient } = renderTab();
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    const keys = queryClient
      .getQueryCache()
      .getAll()
      .map((query) => query.queryKey);
    expect(keys.length).toBeGreaterThanOrEqual(2);
    for (const key of keys) {
      expect(key[0]).toBe("athlete-benchmarks");
      expect(key[1]).toBe(MEMBER_ID);
    }
  });
});

describe("BenchmarksTab · la tabla de intentos", () => {
  it("tiene las columnas Fecha, Marca, Nivel y Diferencia, y no inventa la columna «Escaló» (DESIGN-GAP)", async () => {
    renderTab();
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(within(table()).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Fecha", "Marca", "Nivel", "Diferencia"]);
    expect(screen.queryByRole("columnheader", { name: "Escaló" })).not.toBeInTheDocument();
  });

  it("lista los cinco intentos del más reciente al más antiguo (como el diseño; la gráfica va en orden cronológico)", async () => {
    renderTab();
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    const rows = within(table()).getAllByRole("row").slice(1);
    expect(rows.map((row) => cellsOf(row)[0])).toEqual(["2 nov 2026", "20 oct 2026", "20 jun 2026", "12 mar 2026", "10 ene 2026"]);
  });

  it("la marca es el tiempo del intento y el nivel va con palabras: 8:15 Escalado, 4:40 RX, 4:20 RX, 4:05 RX y 4:10 RX", async () => {
    renderTab();
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    const expected: [string, string, string][] = [
      ["10 ene 2026", "8:15", "Escalado"],
      ["12 mar 2026", "4:40", "RX"],
      ["20 jun 2026", "4:20", "RX"],
      ["20 oct 2026", "4:05", "RX"],
      ["2 nov 2026", "4:10", "RX"],
    ];
    for (const [date, mark, level] of expected) {
      const cells = cellsOf(rowOf(date));
      expect(cells[1]).toContain(mark);
      expect(cells[2]).toBe(level);
    }
  });

  it("«Mejor» es texto y está solo en el intento is_best (4:05)", async () => {
    renderTab();
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(within(table()).getAllByText("Mejor")).toHaveLength(1);
    expect(within(rowOf("20 oct 2026")).getByText("Mejor")).toBeInTheDocument();
    for (const date of ["10 ene 2026", "12 mar 2026", "20 jun 2026", "2 nov 2026"]) expect(within(rowOf(date)).queryByText("Mejor")).not.toBeInTheDocument();
  });

  it("diferencias con el intento anterior del mismo nivel: tiempo menor es mejor (−0:20, −0:15) y subir se ve con «+0:05»", async () => {
    renderTab();
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(cellsOf(rowOf("20 jun 2026"))[3]).toBe("−0:20");
    expect(cellsOf(rowOf("20 oct 2026"))[3]).toBe("−0:15");
    expect(cellsOf(rowOf("2 nov 2026"))[3]).toBe("+0:05");
  });

  it("el primer intento dice «Primera vez» y el que cambió de nivel dice «Cambió de nivel» sin diferencia numérica", async () => {
    renderTab();
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(cellsOf(rowOf("10 ene 2026"))[3]).toBe("Primera vez");
    const changed = cellsOf(rowOf("12 mar 2026"))[3] ?? "";
    expect(changed).toContain("Cambió de nivel");
    expect(changed).not.toMatch(/[−+]\d/);
    expect(within(table()).getAllByText(/Cambió de nivel/)).toHaveLength(1);
  });

  it("explica que solo se compara entre intentos del mismo nivel", async () => {
    renderTab();
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(screen.getByText("Solo se compara entre intentos del mismo nivel.")).toBeInTheDocument();
  });

  it("carga: 100 kg y 102,5 kg dan «+2,5 kg» y la marca dice «102,5 kg»", async () => {
    renderTab({ [LIST]: listOf([CLEAN_ROW]), [`GET ${seriesPath(benchmarkId(5))}`]: ok(CLEAN_SERIES) });

    await screen.findByRole("table", { name: "Intentos del socio en Max Clean" });
    expect(cellsOf(rowOf("1 abr 2026", "Max Clean"))[1]).toBe("100 kg");
    expect(cellsOf(rowOf("12 ago 2026", "Max Clean"))[1]).toContain("102,5 kg");
    expect(cellsOf(rowOf("12 ago 2026", "Max Clean"))[3]).toBe("+2,5 kg");
  });

  it("repeticiones: 30 y 35 reps dan «+5 reps» y la marca dice «35 reps»", async () => {
    renderTab({ [LIST]: listOf([PULLUPS_ROW]), [`GET ${seriesPath(benchmarkId(4))}`]: ok(PULLUPS_SERIES) });

    await screen.findByRole("table", { name: "Intentos del socio en Max Pull-ups" });
    expect(cellsOf(rowOf("14 jul 2026", "Max Pull-ups"))[1]).toContain("35 reps");
    expect(cellsOf(rowOf("14 jul 2026", "Max Pull-ups"))[3]).toBe("+5 reps");
    expect(within(rowOf("14 jul 2026", "Max Pull-ups")).getByText("Mejor")).toBeInTheDocument();
  });

  it("rondas + repeticiones: la marca dice «6 + 3» y la diferencia es «—» (no hay tamaño de ronda para comparar)", async () => {
    renderTab({ [LIST]: listOf([CINDY_ROW]), [`GET ${seriesPath(benchmarkId(2))}`]: ok(CINDY_SERIES) });

    await screen.findByRole("table", { name: "Intentos del socio en Cindy" });
    expect(cellsOf(rowOf("4 may 2026", "Cindy"))[1]).toContain("5 + 12");
    expect(cellsOf(rowOf("7 sept 2026", "Cindy"))[1]).toContain("6 + 3");
    expect(cellsOf(rowOf("7 sept 2026", "Cindy"))[3]).toBe("—");
  });

  it("un intento cortado (DNF) dice «DNF» y no se compara, ni él ni el siguiente", async () => {
    const dnf = seriesOf(FRAN_ROW, [
      attempt(51, { wod_date: "2026-03-01", seconds: 300 }),
      attempt(52, { wod_date: "2026-04-01", seconds: 900, capped: true, reps: 18 }),
      attempt(53, { wod_date: "2026-05-01", seconds: 290, is_best: true }),
    ]);
    renderTab({ [`GET ${seriesPath(FRAN)}`]: ok(dnf) });

    await screen.findByRole("table", { name: "Intentos del socio en Fran" });
    expect(cellsOf(rowOf("1 abr 2026"))[1]).toContain("DNF");
    expect(cellsOf(rowOf("1 abr 2026"))[3]).toBe("—");
    expect(cellsOf(rowOf("1 may 2026"))[3]).toBe("—");
  });

  it("un solo intento: una fila, «Mejor» y «Primera vez»", async () => {
    renderTab({ [LIST]: listOf([HELEN_ROW]) }, `${BASE}&benchmark=${HELEN}`);

    await screen.findByRole("table", { name: "Intentos del socio en Helen" });
    expect(within(table("Helen")).getAllByRole("row")).toHaveLength(2);
    expect(within(rowOf("20 oct 2026", "Helen")).getByText("Mejor")).toBeInTheDocument();
    expect(cellsOf(rowOf("20 oct 2026", "Helen"))[3]).toBe("Primera vez");
  });
});

describe("BenchmarksTab · la gráfica", () => {
  it("dibuja la misma serie en un TrendChart con nombre accesible (imagen), junto a la tabla que es su equivalente", async () => {
    renderTab();
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    const chart = screen.getByRole("img", { name: /Fran/ });
    const label = chart.getAttribute("aria-label") ?? "";
    expect(label).toContain("4 puntos");
    expect(label).not.toContain("10 ene 2026");
    expect(label).toContain("20 oct 2026: 4:05 (mejor)");
    expect(label).toContain("2 nov 2026: 4:10");
  });

  it("con Helen, un solo punto, la gráfica lo dice en singular", async () => {
    renderTab({ [LIST]: listOf([HELEN_ROW]) }, `${BASE}&benchmark=${HELEN}`);
    await screen.findByRole("table", { name: "Intentos del socio en Helen" });

    expect(screen.getByRole("img", { name: /Helen/ }).getAttribute("aria-label")).toContain("1 punto");
  });
});

describe("BenchmarksTab · estados", () => {
  it("sin benchmarks con intentos dice «Sin intentos en benchmarks», sin chips, tabla ni petición de serie", async () => {
    const { mock } = renderTab({ [LIST]: listOf([]) });

    expect(await screen.findByText("Sin intentos en benchmarks")).toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Benchmark" })).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByText(/No hay datos/)).not.toBeInTheDocument();
    expect(mock.calls.filter((call) => call.path.startsWith(`${BENCHMARKS_PATH}/`))).toHaveLength(0);
  });

  it("una serie vacía (200 con lista vacía) lo dice con el nombre del benchmark, sin tabla ni gráfica", async () => {
    renderTab({ [`GET ${seriesPath(FRAN)}`]: ok(seriesOf(FRAN_ROW, [])) });

    expect(await screen.findByText("Este socio todavía no tiene intentos validados en Fran.")).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Intentos del socio en Fran" })).not.toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("mientras carga ya pidió la lista y no muestra el vacío ni filas", async () => {
    const { mock } = renderTab({ [LIST]: () => new Promise(() => undefined) });

    await waitFor(() => {
      expect(mock.callsTo(LIST)).toHaveLength(1);
    });
    expect(screen.queryByText("Sin intentos en benchmarks")).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("si la serie tiene más de 200 intentos avisa que se muestran los 200 más recientes", async () => {
    renderTab({ [`GET ${seriesPath(FRAN)}`]: ok({ ...FRAN_SERIES, truncated: true }) });

    expect(await screen.findByText("Se muestran los 200 intentos más recientes.")).toBeInTheDocument();
  });

  it("sin truncar no avisa nada de 200", async () => {
    renderTab();
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(screen.queryByText(/200 intentos/)).not.toBeInTheDocument();
  });

  it("si hay más benchmarks de los que caben en 5 páginas de 200 avisa el tope y no pinta paginación", async () => {
    renderTab({ [LIST]: listOf(ROWS, 1230) });

    expect(await screen.findByText("Se muestran los primeros 1.000 benchmarks.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Siguiente/ })).not.toBeInTheDocument();
  });

  it("con 230 benchmarks pide una segunda página (offset 200) y no avisa tope", async () => {
    const { mock } = renderTab({ [LIST]: listOf(ROWS, 230) });
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    await waitFor(() => {
      expect(mock.callsTo(LIST)).toHaveLength(2);
    });
    expect(paramsOf(mock.callsTo(LIST)[1]).get("offset")).toBe("200");
    expect(screen.queryByText(/primeros/)).not.toBeInTheDocument();
  });

  it("sin más de 200 benchmarks no hay aviso de límite", async () => {
    renderTab();
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(screen.queryByText(/Se muestran los primeros/)).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderTab();
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("BenchmarksTab · errores explicados", () => {
  it("lista 403: no tiene permiso para ver los benchmarks de este socio", async () => {
    renderTab({ [LIST]: apiError(403, "forbidden") });

    expect(await screen.findByText("No tienes permiso para ver los benchmarks de este socio.")).toBeInTheDocument();
  });

  it("lista 404: el socio ya no existe", async () => {
    renderTab({ [LIST]: apiError(404, "member_not_found") });

    expect(await screen.findByText("Este socio ya no existe. Vuelve a Socios y elige otro.")).toBeInTheDocument();
  });

  it("lista 429: dice cuánto esperar", async () => {
    renderTab({ [LIST]: apiError(429, "rate_limited", {}, { "Retry-After": "30" }) });

    expect(await screen.findByText("Hiciste muchas consultas seguidas. Espera 30 segundos e intenta de nuevo.")).toBeInTheDocument();
  });

  it("lista 500: dice qué hacer, sin el texto técnico, y Reintentar vuelve a pedir", async () => {
    let calls = 0;
    const { user } = renderTab({
      [LIST]: (call: RecordedCall) => {
        calls += 1;
        return calls === 1 ? apiError(500, "internal_error") : pageReply(call, ROWS);
      },
    });

    expect(await screen.findByText("No pudimos cargar los benchmarks. Intenta de nuevo en un momento.")).toBeInTheDocument();
    expect(screen.queryByText("Mensaje del api.")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("table", { name: "Intentos del socio en Fran" })).toBeInTheDocument();
  });

  it("serie 404 benchmark_not_found: dice que el benchmark ya no está y deja elegir otro chip", async () => {
    const { user } = renderTab({ [`GET ${seriesPath(FRAN)}`]: apiError(404, "benchmark_not_found") });

    expect(await screen.findByText("Este benchmark ya no está en el catálogo. Elige otro.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Helen" }));
    expect(await screen.findByRole("table", { name: "Intentos del socio en Helen" })).toBeInTheDocument();
  });

  it("serie 403: no tiene permiso para ver los benchmarks de este socio", async () => {
    renderTab({ [`GET ${seriesPath(FRAN)}`]: apiError(403, "forbidden") });

    expect(await screen.findByText("No tienes permiso para ver los benchmarks de este socio.")).toBeInTheDocument();
  });

  it("serie 500: dice que no pudo cargar la serie, con Reintentar", async () => {
    let calls = 0;
    const { user } = renderTab({
      [`GET ${seriesPath(FRAN)}`]: () => {
        calls += 1;
        return calls === 1 ? apiError(500, "internal_error") : ok(FRAN_SERIES);
      },
    });

    expect(await screen.findByText("No pudimos cargar la serie de este benchmark. Intenta de nuevo en un momento.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("table", { name: "Intentos del socio en Fran" })).toBeInTheDocument();
  });
});

describe("BenchmarksTab · revisión S9-F3 (gráfica por nivel, truncado, orden y bordes)", () => {
  it("L7: la gráfica solo grafica el nivel del intento más reciente, con una leyenda en texto", async () => {
    renderTab();
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(screen.getByText("Gráfica de intentos en RX")).toBeInTheDocument();
    const label = screen.getByRole("img", { name: /Fran/ }).getAttribute("aria-label") ?? "";
    expect(label).toContain("4 puntos");
    expect(label).not.toContain("10 ene 2026");
    // La tabla sigue mostrando los cinco, incluido el escalado.
    expect(within(table()).getAllByRole("row")).toHaveLength(6);
  });

  it("L7: la gráfica omite los intentos DNF (la tabla los sigue mostrando)", async () => {
    const dnf = seriesOf(FRAN_ROW, [
      attempt(51, { wod_date: "2026-03-01", seconds: 300 }),
      attempt(52, { wod_date: "2026-04-01", seconds: 900, capped: true, reps: 18 }),
      attempt(53, { wod_date: "2026-05-01", seconds: 290, is_best: true }),
    ]);
    renderTab({ [`GET ${seriesPath(FRAN)}`]: ok(dnf) });
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(screen.getByRole("img", { name: /Fran/ }).getAttribute("aria-label")).toContain("2 puntos");
    expect(within(table()).getAllByRole("row")).toHaveLength(4);
  });

  it("L7: si todos los intentos del nivel reciente son DNF la gráfica dice que no hay datos", async () => {
    const onlyDnf = seriesOf(FRAN_ROW, [attempt(54, { wod_date: "2026-04-01", seconds: 900, capped: true, reps: 18, is_best: true })]);
    renderTab({ [`GET ${seriesPath(FRAN)}`]: ok(onlyDnf) });
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.getByText("Sin datos para graficar.")).toBeInTheDocument();
  });

  it("L7: el nivel de la leyenda sale del intento más reciente (RX+)", async () => {
    const plus = seriesOf(FRAN_ROW, [attempt(61, { wod_date: "2026-03-01", level: "rx", seconds: 300 }), attempt(62, { wod_date: "2026-05-01", level: "rx_plus", level_changed: true, seconds: 290, is_best: true })]);
    renderTab({ [`GET ${seriesPath(FRAN)}`]: ok(plus) });
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(screen.getByText("Gráfica de intentos en RX+")).toBeInTheDocument();
    expect(cellsOf(rowOf("1 may 2026"))[2]).toBe("RX+");
  });

  it("M1: con la serie truncada el intento más antiguo mostrado no es «Primera vez» sino «—»", async () => {
    renderTab({ [`GET ${seriesPath(FRAN)}`]: ok({ ...FRAN_SERIES, truncated: true }) });
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(cellsOf(rowOf("10 ene 2026"))[3]).toBe("—");
    expect(cellsOf(rowOf("20 jun 2026"))[3]).toBe("−0:20");
  });

  it("dos intentos con la misma fecha: se comparan en el orden del api", async () => {
    const same = seriesOf(FRAN_ROW, [attempt(71, { wod_date: "2026-05-01", seconds: 300 }), attempt(72, { wod_date: "2026-05-01", seconds: 290, is_best: true })]);
    renderTab({ [`GET ${seriesPath(FRAN)}`]: ok(same) });
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    const rows = within(table()).getAllByRole("row").slice(1);
    expect(rows.map((row) => cellsOf(row)[3])).toEqual(["−0:10", "Primera vez"]);
  });

  it("si el api manda los intentos en orden no ascendente, la diferencia sigue siendo contra el anterior en el tiempo", async () => {
    renderTab({ [`GET ${seriesPath(FRAN)}`]: ok(seriesOf(FRAN_ROW, [...FRAN_ATTEMPTS].reverse())) });
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(cellsOf(rowOf("20 jun 2026"))[3]).toBe("−0:20");
    expect(cellsOf(rowOf("10 ene 2026"))[3]).toBe("Primera vez");
    expect(within(table()).getAllByRole("row").slice(1).map((row) => cellsOf(row)[0])).toEqual(["2 nov 2026", "20 oct 2026", "20 jun 2026", "12 mar 2026", "10 ene 2026"]);
  });

  it("un empate con el intento anterior dice «Sin cambio»", async () => {
    const tie = seriesOf(FRAN_ROW, [attempt(81, { wod_date: "2026-05-01", seconds: 300 }), attempt(82, { wod_date: "2026-06-01", seconds: 300, is_best: true })]);
    renderTab({ [`GET ${seriesPath(FRAN)}`]: ok(tie) });
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(cellsOf(rowOf("1 jun 2026"))[3]).toBe("Sin cambio");
  });

  it("un score_type desconocido no rompe: la marca y la diferencia dicen «—» y no hay gráfica", async () => {
    const odd = benchmarkRow({ score_type: "parsec" });
    const series = seriesOf(odd, [attempt(91, { wod_date: "2026-05-01", seconds: 300 }), attempt(92, { wod_date: "2026-06-01", seconds: 290, is_best: true })]);
    renderTab({ [LIST]: listOf([odd]), [`GET ${seriesPath(FRAN)}`]: ok(series) });
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(cellsOf(rowOf("1 jun 2026"))[1]).toContain("—");
    expect(cellsOf(rowOf("1 jun 2026"))[3]).toBe("—");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("serie 429: dice cuánto esperar", async () => {
    renderTab({ [`GET ${seriesPath(FRAN)}`]: apiError(429, "rate_limited", {}, { "Retry-After": "30" }) });

    expect(await screen.findByText("Hiciste muchas consultas seguidas. Espera 30 segundos e intenta de nuevo.")).toBeInTheDocument();
  });

  it("serie 404 member_not_found: dice que el socio ya no existe (no que el benchmark)", async () => {
    renderTab({ [`GET ${seriesPath(FRAN)}`]: apiError(404, "member_not_found") });

    expect(await screen.findByText("Este socio ya no existe. Vuelve a Socios y elige otro.")).toBeInTheDocument();
    expect(screen.queryByText("Este benchmark ya no está en el catálogo. Elige otro.")).not.toBeInTheDocument();
  });

  it("rondas + repeticiones se dibuja como rondas×1000 + reps, con reps topadas en 999", async () => {
    const huge = seriesOf(CINDY_ROW, [attempt(101, { wod_date: "2026-05-01", rounds: 5, reps: 5000 }), attempt(102, { wod_date: "2026-06-01", rounds: 6, reps: 0, is_best: true })]);
    const { container } = renderTab({ [LIST]: listOf([CINDY_ROW]), [`GET ${seriesPath(benchmarkId(2))}`]: ok(huge) });
    await screen.findByRole("table", { name: "Intentos del socio en Cindy" });

    const [first, second] = [...container.querySelectorAll("svg circle")].map((c) => Number(c.getAttribute("cy")));
    expect(second).toBeLessThan(first ?? 0);
  });

  it("un intento sin la marca de su tipo sale en la tabla pero no en la gráfica", async () => {
    const gap = seriesOf(FRAN_ROW, [attempt(111, { wod_date: "2026-05-01", seconds: 300 }), attempt(112, { wod_date: "2026-06-01", seconds: null }), attempt(113, { wod_date: "2026-07-01", seconds: 280, is_best: true })]);
    renderTab({ [`GET ${seriesPath(FRAN)}`]: ok(gap) });
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(within(table()).getAllByRole("row")).toHaveLength(4);
    expect(screen.getByRole("img", { name: /Fran/ }).getAttribute("aria-label")).toContain("2 puntos");
  });

  it("el tiempo se grafica con «menor es mejor»: el mejor punto queda arriba", async () => {
    const { container } = renderTab();
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    const circles = [...container.querySelectorAll("svg circle")];
    const best = circles.find((c) => c.getAttribute("data-best") === "true");
    expect(Number(best?.getAttribute("cy"))).toBe(Math.min(...circles.map((c) => Number(c.getAttribute("cy")))));
  });

  it("la carga se grafica con «mayor es mejor»: el mejor punto queda arriba", async () => {
    const { container } = renderTab({ [LIST]: listOf([CLEAN_ROW]), [`GET ${seriesPath(benchmarkId(5))}`]: ok(CLEAN_SERIES) });
    await screen.findByRole("table", { name: "Intentos del socio en Max Clean" });

    const circles = [...container.querySelectorAll("svg circle")];
    const best = circles.find((c) => c.getAttribute("data-best") === "true");
    expect(Number(best?.getAttribute("cy"))).toBe(Math.min(...circles.map((c) => Number(c.getAttribute("cy")))));
  });

  it("L10: si la relectura falla con datos viejos no se pintan gráfica ni notas, solo el error", async () => {
    let calls = 0;
    const { queryClient } = renderTab({
      [`GET ${seriesPath(FRAN)}`]: () => {
        calls += 1;
        return calls === 1 ? ok({ ...FRAN_SERIES, truncated: true }) : apiError(500, "internal_error");
      },
    });
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    await queryClient.invalidateQueries({ queryKey: ["athlete-benchmarks"] });

    expect(await screen.findByText("No pudimos cargar la serie de este benchmark. Intenta de nuevo en un momento.")).toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByText("Solo se compara entre intentos del mismo nivel.")).not.toBeInTheDocument();
    expect(screen.queryByText("Se muestran los 200 intentos más recientes.")).not.toBeInTheDocument();
  });

  it("L11: el error es un aviso (role=alert) con Reintentar, sin tabla", async () => {
    renderTab({ [`GET ${seriesPath(FRAN)}`]: apiError(500, "internal_error") });

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("No pudimos cargar la serie de este benchmark. Intenta de nuevo en un momento.")).toBeInTheDocument();
    expect(within(alert).getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("L12: «Mejor» es una píldora de StatusTag (texto, no solo color)", async () => {
    const { container } = renderTab();
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    expect(container.querySelectorAll('[data-mark="best"]')).toHaveLength(1);
    expect(container.querySelector('[data-mark="best"]')).toHaveTextContent("Mejor");
  });

  it("S2: si la serie que llega es de otro benchmark se rechaza como respuesta inválida y no se pinta", async () => {
    renderTab({ [`GET ${seriesPath(FRAN)}`]: ok(HELEN_SERIES) });

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("cambiar de socio (memberId) pide la lista del otro y no deja ver las filas del anterior", async () => {
    const other = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
    const otherList = `GET /athletes/${other}/benchmarks`;
    const otherSeries = seriesOf(CINDY_ROW, [attempt(121, { wod_date: "2026-05-04", rounds: 5, reps: 12, is_best: true })]);
    function Switch() {
      const [id, setId] = useState(MEMBER_ID);
      return (
        <>
          <button
            type="button"
            onClick={() => {
              setId(other);
            }}
          >
            otro socio
          </button>
          <BenchmarksTab memberId={id} />
        </>
      );
    }
    const { mock, user } = renderAthlete(<Switch />, {
      handlers: { ...defaults(), [otherList]: listOf([CINDY_ROW]), [`GET /athletes/${other}/benchmarks/${benchmarkId(2)}`]: ok(otherSeries) },
      route: BASE,
    });
    await screen.findByRole("table", { name: "Intentos del socio en Fran" });

    await user.click(screen.getByRole("button", { name: "otro socio" }));

    expect(await screen.findByRole("table", { name: "Intentos del socio en Cindy" })).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: "Intentos del socio en Fran" })).not.toBeInTheDocument();
    expect(mock.callsTo(otherList)).toHaveLength(1);
  });
});
