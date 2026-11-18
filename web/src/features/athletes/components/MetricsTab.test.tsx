// S9-F1 · US-178, US-179 (Atleta_Perfil.html, subpestaña «Medidas corporales»): la lista completa y paginada en el servidor.
// - GET /athletes/{id}/metrics?limit&offset (25, 50 o 100; `offset` en la URL). Solo `has_*`: ningún valor llega en la lista (S9-D16).
// - Columnas: Fecha, Peso, Altura, % grasa, Notas, Registró y la acción «Anular» (POST .../void, sin cuerpo) con ConfirmModal.
// - Vacío con guía; error con Reintentar; socio dado de baja: sin «Anular» y el reveal del coach da 403 explicado (S9-D34).
// DESIGN-GAP (código): la gráfica de peso y la columna «Cintura» del diseño no están en el contrato (S9-F1).
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { apiError, MEMBER_ID, METRICS_PATH, metric, metricId, pageReply, renderAthlete, revealPath, revealReply, voidPath } from "../../../test/athletes";
import { setViewportWidth, type MockHandler } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { MetricsTab } from "./MetricsTab";

const LIST = `GET ${METRICS_PATH}`;

const ROWS = [
  metric(1, { measured_on: "2026-10-01", recorded_by_name: "Carlos" }),
  metric(2, { measured_on: "2026-09-01", has_height: false, has_body_fat: true, recorded_by_name: "Carlos" }),
  metric(3, { measured_on: "2026-08-01", has_weight: true, has_height: false, has_body_fat: false, has_notes: true, recorded_by_name: null }),
];

const rows =
  (items: readonly unknown[], total = items.length): MockHandler =>
  (call) =>
    pageReply(call, items, total);

const renderTab = (handlers: Record<string, MockHandler> = {}, deleted = false, route?: string) =>
  renderAthlete(<MetricsTab memberId={MEMBER_ID} memberDeleted={deleted} />, { handlers: { [LIST]: rows(ROWS), ...handlers }, ...(route ? { route } : {}) });
const table = () => screen.getByRole("table", { name: "Medidas corporales del socio" });
const paramsOf = (call: { url: string } | undefined): URLSearchParams => new URL(call?.url ?? "", "http://apex.test").searchParams;

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("MetricsTab · contenido", () => {
  it("pide la lista con limit 25 y offset 0 y muestra Fecha, Peso, Altura, % grasa, Notas y Registró", async () => {
    const { mock } = renderTab();

    await screen.findByText("1 oct 2026");
    expect(paramsOf(mock.callsTo(LIST)[0]).get("limit")).toBe("25");
    expect(paramsOf(mock.callsTo(LIST)[0]).get("offset")).toBe("0");
    const body = within(table());
    for (const name of ["Fecha", "Peso", "Altura", "% grasa", "Notas", "Registró"]) expect(body.getByRole("columnheader", { name })).toBeInTheDocument();
    expect(body.getByText("1 sept 2026")).toBeInTheDocument();
    expect(body.getByText("1 ago 2026")).toBeInTheDocument();
    expect(body.getAllByText("Carlos")).toHaveLength(2);
  });

  it("cada campo con valor es «•••» con su botón «Mostrar» y el que no, «—»; ningún valor llega en la lista", async () => {
    renderTab();

    const first = (await screen.findByText("1 oct 2026")).closest("tr") as HTMLElement;
    expect(within(first).getByRole("button", { name: "Mostrar peso" })).toBeInTheDocument();
    expect(within(first).getByRole("button", { name: "Mostrar altura" })).toBeInTheDocument();
    expect(within(first).getByRole("button", { name: "Mostrar % grasa" })).toBeInTheDocument();
    expect(within(first).queryByRole("button", { name: "Mostrar notas" })).not.toBeInTheDocument();
    const third = screen.getByText("1 ago 2026").closest("tr") as HTMLElement;
    expect(within(third).getByRole("button", { name: "Mostrar notas" })).toBeInTheDocument();
    expect(within(third).queryByRole("button", { name: "Mostrar altura" })).not.toBeInTheDocument();
    expect(within(third).getAllByText("—").length).toBeGreaterThanOrEqual(3);
    expect(table().textContent).not.toMatch(/61,2|165 cm|22 %/);
  });

  it("«Mostrar peso» de una fila llama al reveal de ESA medición con el campo weight_g", async () => {
    const { mock, user } = renderTab({ [`POST ${revealPath(metricId(2))}`]: revealReply });
    const second = (await screen.findByText("1 sept 2026")).closest("tr") as HTMLElement;

    await user.click(within(second).getByRole("button", { name: "Mostrar peso" }));

    expect(await within(second).findByText("61,2 kg")).toBeInTheDocument();
    expect(mock.callsTo(`POST ${revealPath(metricId(2))}`)[0]?.body).toEqual({ field: "weight_g" });
    expect(mock.calls.filter((c) => c.path.endsWith("/reveal"))).toHaveLength(1);
  });

  it("al abrir la pestaña no se pide ningún reveal", async () => {
    const { mock } = renderTab();
    await screen.findByText("1 oct 2026");

    expect(mock.calls.filter((c) => c.path.includes("/reveal"))).toHaveLength(0);
  });
});

describe("MetricsTab · paginación en el servidor", () => {
  it("con 60 medidas pide la segunda página con offset 25 y lo deja en la URL", async () => {
    const { mock, user } = renderTab({ [LIST]: rows(ROWS, 60) });
    await screen.findByText("1 oct 2026");
    expect(screen.getByText("Página 1 de 3")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Siguiente/ }));

    await waitFor(() => {
      expect(paramsOf(mock.callsTo(LIST).at(-1)).get("offset")).toBe("25");
    });
    expect(paramsOf(mock.callsTo(LIST).at(-1)).get("limit")).toBe("25");
    expect(screen.getByTestId("where")).toHaveTextContent("offset=25");
  });

  it("lee limit y offset de la URL al cargar (sobrevive a recargar)", async () => {
    const { mock } = renderTab({ [LIST]: rows(ROWS, 120) }, false, `/socios/${MEMBER_ID}/atleta?tab=medidas&limit=50&offset=50`);

    await screen.findByText("1 oct 2026");
    expect(paramsOf(mock.callsTo(LIST)[0]).get("limit")).toBe("50");
    expect(paramsOf(mock.callsTo(LIST)[0]).get("offset")).toBe("50");
    expect(screen.getByText("Página 2 de 3")).toBeInTheDocument();
  });

  it("cambiar el tamaño de página pide limit 50 desde la primera página", async () => {
    const { mock, user } = renderTab({ [LIST]: rows(ROWS, 60) }, false, `/socios/${MEMBER_ID}/atleta?tab=medidas&offset=25`);
    await screen.findByText("1 oct 2026");

    await user.selectOptions(screen.getByLabelText("Mostrar"), "50");

    await waitFor(() => {
      expect(paramsOf(mock.callsTo(LIST).at(-1)).get("limit")).toBe("50");
    });
    expect(paramsOf(mock.callsTo(LIST).at(-1)).get("offset")).toBe("0");
  });

  it("con una sola página no ofrece más páginas", async () => {
    renderTab();
    await screen.findByText("1 oct 2026");

    expect(screen.getByText("Página 1 de 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Siguiente/ })).toBeDisabled();
  });
});

describe("MetricsTab · Anular (US-178, S9-D33)", () => {
  const VOID_FIRST = `POST ${voidPath(metricId(1))}`;
  const voided = { status: 200, body: metric(1, { voided_at: "2026-10-21T15:00:00Z" }) };

  it("«Anular» abre un ConfirmModal que explica la consecuencia y no pide motivo", async () => {
    const { user, mock } = renderTab({ [VOID_FIRST]: voided });
    await screen.findByText("1 oct 2026");

    await user.click(screen.getByRole("button", { name: "Anular medición del 1 oct 2026" }));

    const dialog = screen.getByRole("dialog", { name: "¿Anular esta medición?" });
    expect(within(dialog).getByText("La medición deja de contarse y se conserva en la auditoría. No se puede deshacer.")).toBeInTheDocument();
    expect(within(dialog).queryByRole("textbox")).not.toBeInTheDocument();
    expect(mock.callsTo(VOID_FIRST)).toHaveLength(0);
  });

  it("cancelar no anula nada", async () => {
    const { user, mock } = renderTab({ [VOID_FIRST]: voided });
    await screen.findByText("1 oct 2026");
    await user.click(screen.getByRole("button", { name: "Anular medición del 1 oct 2026" }));

    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancelar" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.callsTo(VOID_FIRST)).toHaveLength(0);
  });

  it("confirmar hace POST void de esa medición sin cuerpo y relee la lista", async () => {
    let reads = 0;
    const { user, mock } = renderTab({
      [VOID_FIRST]: voided,
      [LIST]: (call) => {
        reads += 1;
        return pageReply(call, reads === 1 ? ROWS : ROWS.slice(1));
      },
    });
    await screen.findByText("1 oct 2026");
    await user.click(screen.getByRole("button", { name: "Anular medición del 1 oct 2026" }));

    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Anular medición" }));

    await waitFor(() => {
      expect(screen.queryByText("1 oct 2026")).not.toBeInTheDocument();
    });
    expect(mock.callsTo(VOID_FIRST)).toHaveLength(1);
    expect(mock.callsTo(VOID_FIRST)[0]?.body).toBeUndefined();
    expect(mock.callsTo(VOID_FIRST)[0]?.path).toBe(`/athletes/${MEMBER_ID}/metrics/${metricId(1)}/void`);
    expect(mock.callsTo(LIST)).toHaveLength(2);
  });

  it("403 (coach que no la registró o pasaron 24 horas) lo explica dentro del modal y lo deja abierto", async () => {
    const { user } = renderTab({ [VOID_FIRST]: apiError(403, "forbidden") });
    await screen.findByText("1 oct 2026");
    await user.click(screen.getByRole("button", { name: "Anular medición del 1 oct 2026" }));

    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Anular medición" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Solo un administrador puede anular esta medición. Un coach solo anula la que registró él en las últimas 24 horas.");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("409 metric_already_voided dice que ya estaba anulada y relee la lista", async () => {
    const { user, mock } = renderTab({ [VOID_FIRST]: apiError(409, "metric_already_voided") });
    await screen.findByText("1 oct 2026");
    await user.click(screen.getByRole("button", { name: "Anular medición del 1 oct 2026" }));

    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Anular medición" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Esta medición ya estaba anulada. Actualizamos la lista.");
    await waitFor(() => {
      expect(mock.callsTo(LIST).length).toBeGreaterThanOrEqual(2);
    });
  });
});

describe("MetricsTab · socio dado de baja (S9-D34)", () => {
  it("no ofrece «Anular» en ninguna fila", async () => {
    renderTab({}, true);
    await screen.findByText("1 oct 2026");

    expect(screen.queryByRole("button", { name: /^Anular/ })).not.toBeInTheDocument();
  });

  it("el coach que intenta mostrar un valor recibe el 403 explicado y el valor no aparece", async () => {
    signInAs("coach");
    const { user } = renderTab({ [`POST ${revealPath(metricId(1))}`]: apiError(403, "forbidden") }, true);
    const first = (await screen.findByText("1 oct 2026")).closest("tr") as HTMLElement;

    await user.click(within(first).getByRole("button", { name: "Mostrar peso" }));

    expect(await within(first).findByRole("alert")).toHaveTextContent("Este socio está dado de baja: solo un administrador puede mostrar sus medidas.");
    expect(first).not.toHaveTextContent("61,2");
  });

  it("el admin sí puede mostrar un valor de un socio dado de baja", async () => {
    const { user } = renderTab({ [`POST ${revealPath(metricId(1))}`]: revealReply }, true);
    const first = (await screen.findByText("1 oct 2026")).closest("tr") as HTMLElement;

    await user.click(within(first).getByRole("button", { name: "Mostrar peso" }));

    expect(await within(first).findByText("61,2 kg")).toBeInTheDocument();
  });
});

describe("MetricsTab · estados", () => {
  it("sin medidas guía a registrar la primera y no dice «No hay datos»", async () => {
    renderTab({ [LIST]: rows([]) });

    expect(await screen.findByText("Todavía no hay medidas registradas. Usa «Registrar medidas» para guardar la primera.")).toBeInTheDocument();
    expect(screen.queryByText(/No hay datos/)).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("mientras carga ya pidió la lista y no muestra filas ni el vacío", async () => {
    const { mock } = renderTab({ [LIST]: () => new Promise(() => undefined) });

    await waitFor(() => {
      expect(mock.callsTo(LIST)).toHaveLength(1);
    });
    expect(screen.queryByText(/Todavía no hay medidas/)).not.toBeInTheDocument();
    expect(screen.queryByText("1 oct 2026")).not.toBeInTheDocument();
  });

  it("un error 500 dice qué hacer y Reintentar vuelve a pedir", async () => {
    let calls = 0;
    const { user } = renderTab({
      [LIST]: (call) => {
        calls += 1;
        return calls === 1 ? apiError(500, "internal_error") : pageReply(call, ROWS);
      },
    });

    expect(await screen.findByText("No pudimos cargar las medidas. Intenta de nuevo en un momento.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText("1 oct 2026")).toBeInTheDocument();
  });

  it("un 403 explica que no tiene permiso para ver las medidas", async () => {
    renderTab({ [LIST]: apiError(403, "forbidden") });

    expect(await screen.findByText("No tienes permiso para ver las medidas de este socio.")).toBeInTheDocument();
  });

  it("un 404 dice que el socio ya no existe", async () => {
    renderTab({ [LIST]: apiError(404, "member_not_found") });

    expect(await screen.findByText("Este socio ya no existe. Vuelve a Socios y elige otro.")).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = renderTab();
    await screen.findByText("1 oct 2026");

    expect(await axe(container)).toHaveNoViolations();
  });
});

// S9-F1 (revisión M1): los mensajes de «Anular» que prometen «Actualizamos la lista» la actualizan de verdad.
describe("MetricsTab · Anular, errores que releen o esperan (revisión M1)", () => {
  const VOID_FIRST = `POST ${voidPath(metricId(1))}`;

  it("404 dice que la medición ya no existe y relee la lista", async () => {
    const { user, mock } = renderTab({ [VOID_FIRST]: apiError(404, "metric_not_found") });
    await screen.findByText("1 oct 2026");
    await user.click(screen.getByRole("button", { name: "Anular medición del 1 oct 2026" }));

    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Anular medición" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Esta medición ya no existe. Actualizamos la lista.");
    await waitFor(() => {
      expect(mock.callsTo(LIST).length).toBeGreaterThanOrEqual(2);
    });
  });

  it("429 dice cuánto esperar y no relee la lista", async () => {
    const { user, mock } = renderTab({ [VOID_FIRST]: apiError(429, "rate_limited", {}, { "Retry-After": "30" }) });
    await screen.findByText("1 oct 2026");
    await user.click(screen.getByRole("button", { name: "Anular medición del 1 oct 2026" }));

    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Anular medición" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Anulaste muchas medidas seguidas. Espera 30 segundos e intenta de nuevo.");
    expect(mock.callsTo(LIST)).toHaveLength(1);
  });
});
