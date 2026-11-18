// S9-F1 · US-184 (Atleta_Perfil.html, subpestaña «Resumen»): GET /athletes/{id}/summary, sin ninguna medida (S9-D16).
// - Cuatro tarjetas: «Medidas corporales» (cuántas y la fecha de la última), «RMs por movimiento» (cuántos vigentes), «Récords recientes»
//   (los tres vigentes más recientes con su origen en palabras) y «Benchmarks» (con cuántos hay intentos); cada «Ver todas» lleva a su
//   subpestaña con `?tab=`.
// - Estados: carga, error con Reintentar (403, 404, 5xx), vacío por tarjeta y el aviso `truncated`.
// DESIGN-GAP (código): la gráfica de peso, el selector «peso, % grasa, cintura…» y «Laura (portal)» no están en el contrato.
import { cleanup, screen, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { apiError, EMPTY_SUMMARY, MEMBER_ID, renderAthlete, SUMMARY_PATH, summary, summaryRecord } from "../../../test/athletes";
import { setViewportWidth, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { SummaryCards } from "./SummaryCards";

const GET = `GET ${SUMMARY_PATH}`;
const BASE = `/socios/${MEMBER_ID}/atleta`;

const renderCards = (handlers: Record<string, MockHandler> = {}) => renderAthlete(<SummaryCards memberId={MEMBER_ID} />, { handlers: { [GET]: { status: 200, body: summary() }, ...handlers } });
const card = (name: string): HTMLElement => screen.getByRole("heading", { level: 2, name }).closest("section") as HTMLElement;

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("coach");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("SummaryCards · contenido", () => {
  it("pide el resumen una vez, sin parámetros, y no toca ningún reveal ni la lista de medidas", async () => {
    const { mock } = renderCards();

    await screen.findByRole("heading", { level: 2, name: "Medidas corporales" });
    expect(mock.callsTo(GET)).toHaveLength(1);
    expect(new URL(mock.callsTo(GET)[0]?.url ?? "", "http://apex.test").search).toBe("");
    expect(mock.calls.filter((c) => c.path.includes("/reveal") || c.path.endsWith("/metrics"))).toHaveLength(0);
  });

  it("muestra las cuatro tarjetas con el título del diseño", async () => {
    renderCards();

    for (const name of ["Medidas corporales", "RMs por movimiento", "Récords recientes", "Benchmarks"]) {
      expect(await screen.findByRole("heading", { level: 2, name })).toBeInTheDocument();
    }
  });

  it("Medidas corporales: cuántas hay y la fecha de la última, sin ningún valor, con «Ver todas (9)» a la subpestaña Medidas", async () => {
    renderCards();

    const section = await screen.findByRole("heading", { level: 2, name: "Medidas corporales" }).then((h) => h.closest("section") as HTMLElement);
    expect(within(section).getByText("9 mediciones registradas")).toBeInTheDocument();
    expect(within(section).getByText("Última medición: 1 oct 2026")).toBeInTheDocument();
    expect(within(section).getByRole("link", { name: "Ver todas (9)" })).toHaveAttribute("href", `${BASE}?tab=medidas`);
    expect(within(section).getByText(/Medidas cifradas en la base/)).toBeInTheDocument();
    expect(section.textContent).not.toMatch(/\d+,\d kg|\d+ cm|\d+ %/);
  });

  it("con una sola medición dice «1 medición registrada»", async () => {
    renderCards({ [GET]: { status: 200, body: summary({ metrics_count: 1 }) } });

    expect(await screen.findByText("1 medición registrada")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver todas (1)" })).toBeInTheDocument();
  });

  it("RMs por movimiento: cuántos vigentes y «Ver todos (14)» a la subpestaña RMs", async () => {
    renderCards();

    await screen.findByRole("heading", { level: 2, name: "RMs por movimiento" });
    const section = card("RMs por movimiento");
    expect(within(section).getByText("14 RMs vigentes")).toBeInTheDocument();
    expect(within(section).getByRole("link", { name: "Ver todos (14)" })).toHaveAttribute("href", `${BASE}?tab=rms`);
  });

  it("Benchmarks: con cuántos hay intentos y «Ver todos» a la subpestaña Benchmarks", async () => {
    renderCards();

    await screen.findByRole("heading", { level: 2, name: "Benchmarks" });
    const section = card("Benchmarks");
    expect(within(section).getByText("3 benchmarks con intentos")).toBeInTheDocument();
    expect(within(section).getByRole("link", { name: "Ver todos" })).toHaveAttribute("href", `${BASE}?tab=benchmarks`);
  });
});

describe("SummaryCards · récords recientes", () => {
  it("muestra Fecha, Récord, Valor y Origen de los tres vigentes, en el orden del api", async () => {
    renderCards();

    await screen.findByRole("heading", { level: 2, name: "Récords recientes" });
    const table = within(card("Récords recientes")).getByRole("table");
    for (const name of ["Fecha", "Récord", "Valor", "Origen"]) expect(within(table).getByRole("columnheader", { name })).toBeInTheDocument();
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(3);
    expect(within(rows[0] as HTMLElement).getByText("20 oct 2026")).toBeInTheDocument();
    expect(within(rows[0] as HTMLElement).getByText("Helen (benchmark)")).toBeInTheDocument();
    expect(within(rows[0] as HTMLElement).getByText("11:42 RX")).toBeInTheDocument();
    expect(within(rows[1] as HTMLElement).getByText("19 oct 2026")).toBeInTheDocument();
    expect(within(rows[1] as HTMLElement).getByText("Back Squat 1RM")).toBeInTheDocument();
    expect(within(rows[1] as HTMLElement).getByText("85 kg")).toBeInTheDocument();
    expect(within(rows[2] as HTMLElement).getByText("4 sept 2026")).toBeInTheDocument();
    expect(within(rows[2] as HTMLElement).getByText("Deadlift 1RM")).toBeInTheDocument();
    expect(within(rows[2] as HTMLElement).getByText("110 kg")).toBeInTheDocument();
  });

  it("el origen se dice con palabras: «automático del WOD» o «manual», y un derivado enlaza a su WOD", async () => {
    renderCards();

    await screen.findByRole("heading", { level: 2, name: "Récords recientes" });
    const rows = within(card("Récords recientes")).getAllByRole("row").slice(1);
    expect(within(rows[0] as HTMLElement).getByText("automático")).toBeInTheDocument();
    expect(within(rows[0] as HTMLElement).getByText(/del WOD/)).toBeInTheDocument();
    expect(within(rows[0] as HTMLElement).getByRole("link", { name: "ver" })).toHaveAttribute("href", "/wods/f2f2f2f2-0000-4000-8000-0000000000aa");
    expect(within(rows[1] as HTMLElement).getByRole("link", { name: "ver" })).toHaveAttribute("href", "/wods/f2f2f2f2-0000-4000-8000-0000000000bb");
    expect(within(rows[2] as HTMLElement).getByText("manual")).toBeInTheDocument();
    expect(within(rows[2] as HTMLElement).queryByRole("link", { name: "ver" })).not.toBeInTheDocument();
  });

  it("«Ver todos» de los récords lleva a la subpestaña Récords", async () => {
    renderCards();

    await screen.findByRole("heading", { level: 2, name: "Récords recientes" });
    expect(within(card("Récords recientes")).getByRole("link", { name: "Ver todos" })).toHaveAttribute("href", `${BASE}?tab=records`);
  });

  it("formatea cada marca: DNF, rondas, repeticiones, carga y el nivel escalado", async () => {
    const records = [
      summaryRecord({ id: "d0d0d0d0-0000-4000-8000-0000000000a1", kind: "benchmark", benchmark_name: "Fran", score_type: "time", capped: true, reps: 18, level: "rx_plus", achieved_on: "2026-10-15" }),
      summaryRecord({ id: "d0d0d0d0-0000-4000-8000-0000000000a2", kind: "benchmark", benchmark_name: "Cindy", score_type: "rounds_reps", rounds: 14, reps: 3, level: "scaled", achieved_on: "2026-10-14" }),
      summaryRecord({ id: "d0d0d0d0-0000-4000-8000-0000000000a3", kind: "benchmark", benchmark_name: "Grace", score_type: "load", load_g: 102_500, level: "rx", achieved_on: "2026-10-13" }),
    ];
    renderCards({ [GET]: { status: 200, body: summary({ recent_records: records }) } });

    await screen.findByRole("heading", { level: 2, name: "Récords recientes" });
    const table = within(card("Récords recientes")).getByRole("table");
    expect(within(table).getByText("DNF · 18 reps RX+")).toBeInTheDocument();
    expect(within(table).getByText("14 + 3 Escalado")).toBeInTheDocument();
    expect(within(table).getByText("102,5 kg RX")).toBeInTheDocument();
  });

  it("sin récords dice que todavía no hay y no pinta la tabla", async () => {
    renderCards({ [GET]: { status: 200, body: summary({ recent_records: [] }) } });

    await screen.findByRole("heading", { level: 2, name: "Récords recientes" });
    const section = card("Récords recientes");
    expect(within(section).getByText("Todavía no hay récords vigentes.")).toBeInTheDocument();
    expect(within(section).queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("SummaryCards · vacío y tope", () => {
  it("un socio sin nada registrado ve un vacío por tarjeta y ningún «Ver todas»", async () => {
    renderCards({ [GET]: { status: 200, body: EMPTY_SUMMARY } });

    expect(await screen.findByText("Todavía no hay medidas registradas.")).toBeInTheDocument();
    expect(screen.getByText("Todavía no hay RMs vigentes.")).toBeInTheDocument();
    expect(screen.getByText("Todavía no hay récords vigentes.")).toBeInTheDocument();
    expect(screen.getByText("Todavía no hay intentos en benchmarks.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Ver todas?/ })).not.toBeInTheDocument();
  });

  it("con `truncated` avisa que el resumen puede quedar corto y no inventa benchmarks recientes", async () => {
    renderCards({ [GET]: { status: 200, body: summary({ truncated: true }) } });

    expect(await screen.findByText("El resumen puede quedar corto: hay más marcas de las que se leen aquí. Revisa cada subpestaña para verlas todas.")).toBeInTheDocument();
  });

  it("sin `truncated` no muestra ese aviso", async () => {
    renderCards();

    await screen.findByRole("heading", { level: 2, name: "Benchmarks" });
    expect(screen.queryByText(/El resumen puede quedar corto/)).not.toBeInTheDocument();
  });
});

describe("SummaryCards · estados de la carga", () => {
  it("mientras carga lo anuncia y no pinta las tarjetas", () => {
    renderCards({ [GET]: () => new Promise(() => undefined) });

    expect(screen.getByRole("status")).toHaveTextContent("Cargando el resumen…");
    expect(screen.queryByRole("heading", { level: 2 })).not.toBeInTheDocument();
  });

  it("un error 500 dice qué hacer y Reintentar vuelve a pedir", async () => {
    let calls = 0;
    const { user } = renderCards({
      [GET]: () => {
        calls += 1;
        return calls === 1 ? apiError(500, "internal_error") : { status: 200, body: summary() };
      },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar el resumen. Intenta de nuevo en un momento.");
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("heading", { level: 2, name: "Medidas corporales" })).toBeInTheDocument();
  });

  it("un 403 explica que no tiene permiso y un 404 que el socio ya no existe", async () => {
    renderCards({ [GET]: apiError(403, "forbidden") });
    expect(await screen.findByRole("alert")).toHaveTextContent("No tienes permiso para ver el perfil del atleta.");
    cleanup();

    renderCards({ [GET]: apiError(404, "member_not_found") });
    expect(await screen.findByRole("alert")).toHaveTextContent("Este socio ya no existe. Vuelve a Socios y elige otro.");
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderCards();
    await screen.findByRole("heading", { level: 2, name: "Récords recientes" });

    expect(await axe(container)).toHaveNoViolations();
  });
});
