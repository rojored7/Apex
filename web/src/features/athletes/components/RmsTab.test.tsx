// S9-F2 · US-180, US-181 (Atleta_Perfil.html, subpestaña «RMs por movimiento»): el RM vigente de cada movimiento, paginado en el servidor.
// - GET /athletes/{id}/rms?limit&offset (25, 50 o 100; `offset` en la URL). Una fila por movimiento: Movimiento, 1RM (kg), Último cambio y Origen.
// - Origen con palabras, nunca solo color: «Manual» o «Automático del WOD». RmOut no trae `result_source`: «Automático (tablet)» solo se
//   puede decir en Récords (RecordOut.result_source, L-4).
// - Vacío con guía; error con Reintentar (403, 404, 429, 5xx). Sin acciones: invalidar vive en Récords.
// DESIGN-GAP: 3RM, 5RM, «máx. reps» y la unidad preferida del diseño (S9-D25; N-45 fija RM = 1RM en kg).
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { apiError, MEMBER_ID, pageReply, renderAthlete, RMS_PATH, rm } from "../../../test/athletes";
import { setViewportWidth, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { RmsTab } from "./RmsTab";

const LIST = `GET ${RMS_PATH}`;

const ROWS = [
  rm(1, { movement_name: "Back Squat", value_g: 85_000, achieved_on: "2026-10-19", source: "derived" }),
  rm(2, { movement_name: "Deadlift", value_g: 110_000, achieved_on: "2026-09-04", source: "manual" }),
  rm(3, { movement_name: "Thruster", value_g: 45_500, achieved_on: "2026-07-23", source: "manual" }),
];

const rows =
  (items: readonly unknown[], total = items.length): MockHandler =>
  (call) =>
    pageReply(call, items, total);

const renderTab = (handlers: Record<string, MockHandler> = {}, route?: string) =>
  renderAthlete(<RmsTab memberId={MEMBER_ID} />, { handlers: { [LIST]: rows(ROWS), ...handlers }, ...(route ? { route } : {}) });
const table = () => screen.getByRole("table", { name: "RMs por movimiento del socio" });
const rowOf = (movement: string): HTMLElement => within(table()).getByText(movement).closest("tr") as HTMLElement;
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

describe("RmsTab · contenido", () => {
  it("pide la lista con limit 25 y offset 0 y muestra Movimiento, 1RM, Último cambio y Origen", async () => {
    const { mock } = renderTab();

    await screen.findByText("Back Squat");
    expect(paramsOf(mock.callsTo(LIST)[0]).get("limit")).toBe("25");
    expect(paramsOf(mock.callsTo(LIST)[0]).get("offset")).toBe("0");
    expect(screen.getByRole("heading", { level: 2, name: "RMs por movimiento" })).toBeInTheDocument();
    for (const name of ["Movimiento", "1RM", "Último cambio", "Origen"]) expect(within(table()).getByRole("columnheader", { name })).toBeInTheDocument();
  });

  it("una fila por movimiento con su 1RM en kg (gramos del contrato) y la fecha del último cambio", async () => {
    renderTab();
    await screen.findByText("Back Squat");

    expect(within(table()).getAllByRole("row")).toHaveLength(ROWS.length + 1);
    expect(rowOf("Back Squat")).toHaveTextContent("85 kg");
    expect(rowOf("Back Squat")).toHaveTextContent("19 oct 2026");
    expect(rowOf("Deadlift")).toHaveTextContent("110 kg");
    expect(rowOf("Deadlift")).toHaveTextContent("4 sept 2026");
    expect(rowOf("Thruster")).toHaveTextContent("45,5 kg");
  });

  it("dice el origen con texto: «Manual» y «Automático del WOD»", async () => {
    renderTab();
    await screen.findByText("Back Squat");

    expect(within(rowOf("Back Squat")).getByText("Automático del WOD")).toBeInTheDocument();
    expect(within(rowOf("Back Squat")).queryByText("Manual")).not.toBeInTheDocument();
    expect(within(rowOf("Deadlift")).getByText("Manual")).toBeInTheDocument();
    expect(within(rowOf("Thruster")).getByText("Manual")).toBeInTheDocument();
  });

  it("RmOut no distingue la tablet: nunca escribe «Automático (tablet)» aquí", async () => {
    renderTab();
    await screen.findByText("Back Squat");

    expect(table()).not.toHaveTextContent("Automático (tablet)");
  });

  it("un movimiento que ya no está en el catálogo se dice con palabras y no queda vacío", async () => {
    renderTab({ [LIST]: rows([rm(4, { movement_name: null, value_g: 60_000 })]) });

    expect(await screen.findByText("Movimiento sin nombre")).toBeInTheDocument();
    expect(screen.getByText("60 kg")).toBeInTheDocument();
  });

  it("no inventa lo que el contrato no trae: sin 3RM, 5RM ni «máx. reps»", async () => {
    renderTab();
    await screen.findByText("Back Squat");

    for (const name of ["3RM", "5RM"]) expect(within(table()).queryByRole("columnheader", { name })).not.toBeInTheDocument();
    expect(table()).not.toHaveTextContent(/máx\. reps/);
  });

  it("es una lista de lectura: no ofrece «Invalidar» ni «Registrar»", async () => {
    renderTab();
    await screen.findByText("Back Squat");

    expect(screen.queryByRole("button", { name: /Invalidar|Registrar/ })).not.toBeInTheDocument();
  });
});

describe("RmsTab · paginación en el servidor", () => {
  it("con 60 RMs pide la segunda página con offset 25 y lo deja en la URL", async () => {
    const { mock, user } = renderTab({ [LIST]: rows(ROWS, 60) });
    await screen.findByText("Back Squat");
    expect(screen.getByText("Página 1 de 3")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Siguiente/ }));

    await waitFor(() => {
      expect(paramsOf(mock.callsTo(LIST).at(-1)).get("offset")).toBe("25");
    });
    expect(paramsOf(mock.callsTo(LIST).at(-1)).get("limit")).toBe("25");
    expect(screen.getByTestId("where")).toHaveTextContent("offset=25");
  });

  it("lee limit y offset de la URL al cargar (sobrevive a recargar)", async () => {
    const { mock } = renderTab({ [LIST]: rows(ROWS, 120) }, `/socios/${MEMBER_ID}/atleta?tab=rms&limit=50&offset=50`);

    await screen.findByText("Back Squat");
    expect(paramsOf(mock.callsTo(LIST)[0]).get("limit")).toBe("50");
    expect(paramsOf(mock.callsTo(LIST)[0]).get("offset")).toBe("50");
    expect(screen.getByText("Página 2 de 3")).toBeInTheDocument();
  });

  it("cambiar el tamaño de página pide limit 50 desde la primera página", async () => {
    const { mock, user } = renderTab({ [LIST]: rows(ROWS, 60) }, `/socios/${MEMBER_ID}/atleta?tab=rms&offset=25`);
    await screen.findByText("Back Squat");

    await user.selectOptions(screen.getByLabelText("Mostrar"), "50");

    await waitFor(() => {
      expect(paramsOf(mock.callsTo(LIST).at(-1)).get("limit")).toBe("50");
    });
    expect(paramsOf(mock.callsTo(LIST).at(-1)).get("offset")).toBe("0");
  });

  it("con una sola página no ofrece más páginas", async () => {
    renderTab();
    await screen.findByText("Back Squat");

    expect(screen.getByText("Página 1 de 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Siguiente/ })).toBeDisabled();
  });

  it("una página fuera de rango (hay RMs pero esta quedó vacía) lo dice y ofrece volver a la primera", async () => {
    const { user, mock } = renderTab({ [LIST]: rows([], 30) }, `/socios/${MEMBER_ID}/atleta?tab=rms&offset=50`);

    expect(await screen.findByText("Esta página ya no tiene RMs.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ir a la primera página" }));
    await waitFor(() => {
      expect(paramsOf(mock.callsTo(LIST).at(-1)).get("offset")).toBe("0");
    });
  });
});

describe("RmsTab · estados", () => {
  it("sin RMs guía a registrar el primero y no dice «No hay datos»", async () => {
    renderTab({ [LIST]: rows([]) });

    expect(await screen.findByText("Todavía no hay RMs registrados. Usa «Registrar récord» para guardar el primero.")).toBeInTheDocument();
    expect(screen.queryByText(/No hay datos/)).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("mientras carga ya pidió la lista y no muestra filas ni el vacío", async () => {
    const { mock } = renderTab({ [LIST]: () => new Promise(() => undefined) });

    await waitFor(() => {
      expect(mock.callsTo(LIST)).toHaveLength(1);
    });
    expect(screen.queryByText(/Todavía no hay RMs/)).not.toBeInTheDocument();
    expect(screen.queryByText("Back Squat")).not.toBeInTheDocument();
  });

  it("un error 500 dice qué hacer y Reintentar vuelve a pedir", async () => {
    let calls = 0;
    const { user } = renderTab({
      [LIST]: (call) => {
        calls += 1;
        return calls === 1 ? apiError(500, "internal_error") : pageReply(call, ROWS);
      },
    });

    expect(await screen.findByText("No pudimos cargar los RMs. Intenta de nuevo en un momento.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("Back Squat")).toBeInTheDocument();
  });

  it("un 403 explica que no tiene permiso para ver los RMs", async () => {
    renderTab({ [LIST]: apiError(403, "forbidden") });

    expect(await screen.findByText("No tienes permiso para ver los RMs de este socio.")).toBeInTheDocument();
  });

  it("un 404 dice que el socio ya no existe", async () => {
    renderTab({ [LIST]: apiError(404, "member_not_found") });

    expect(await screen.findByText("Este socio ya no existe. Vuelve a Socios y elige otro.")).toBeInTheDocument();
  });

  it("un 429 dice cuánto esperar", async () => {
    renderTab({ [LIST]: apiError(429, "rate_limited", {}, { "Retry-After": "30" }) });

    expect(await screen.findByText("Hiciste muchas consultas seguidas. Espera 30 segundos e intenta de nuevo.")).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderTab();
    await screen.findByText("Back Squat");

    expect(await axe(container)).toHaveNoViolations();
  });
});
