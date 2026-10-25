// S3-F6 · US-100 (front): el resumen del mes de /pagos (GET /payments/summary?month=AAAA-MM, D23).
// - El mes por defecto es el actual de Bogotá (no el del equipo); se elige con `?mes=AAAA-MM`, que
//   conserva los demás parámetros de la URL. Un `mes` mal formado se ignora.
// - KpiCard: total del mes (con los pagos válidos), uno por medio con la etiqueta de Configuración
//   ("$ 0" cuando es cero) y el contador de anulados.
// - 422 `month` (fuera de 2020 a 2100) se explica; otro error deja Reintentar en las tarjetas.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { axe } from "vitest-axe";
import { apiError } from "../../../test/memberships";
import { paymentMethods, paymentsSummary } from "../../../test/payments";
import { mockApi, testQueryClient, type MockHandler } from "../../../test/server";
import { MonthSummary, monthInputChange } from "./MonthSummary";

function renderSummary(entry = "/pagos", handlers: Record<string, MockHandler> = {}) {
  const mock = mockApi({
    "GET /payments/summary": (call) => {
      const month = new URL(call.url, "http://apex.test").searchParams.get("month") ?? "";
      return { status: 200, body: paymentsSummary({ month }) };
    },
    "GET /payments/methods": paymentMethods(),
    ...handlers,
  });
  const [pathname = entry, query] = entry.split("?");
  const router = createMemoryRouter([{ path: "/pagos", element: <MonthSummary /> }], { initialEntries: [{ pathname, search: query ? `?${query}` : "" }] });
  const view = render(
    <QueryClientProvider client={testQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { mock, router, user: userEvent.setup(), ...view };
}

const summaryMonths = (mock: ReturnType<typeof renderSummary>["mock"]): string[] =>
  mock.callsTo("GET /payments/summary").map((c) => new URL(c.url, "http://apex.test").searchParams.get("month") ?? "");
const region = () => screen.getByRole("region", { name: "Resumen del mes" });
const card = (label: string) => within(region()).getByRole("group", { name: label });
/** Las tarjetas dejaron de cargar (el resumen llegó). */
const loaded = () =>
  waitFor(() => {
    expect(card("Anulados")).not.toHaveAttribute("aria-busy");
  });

beforeEach(() => {
  // 31 oct 2026, 10:00 p. m. en Bogotá: en UTC ya es 1 de noviembre.
  vi.useFakeTimers({ toFake: ["Date"], now: new Date("2026-11-01T03:00:00Z") });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("MonthSummary · mes", () => {
  it("por defecto pide el mes actual de Bogotá, no el de UTC", async () => {
    const { mock } = renderSummary();

    await waitFor(() => {
      expect(summaryMonths(mock)).toEqual(["2026-10"]);
    });
    expect(within(region()).getByLabelText("Mes")).toHaveValue("2026-10");
  });

  it("el mes de la URL (?mes=AAAA-MM) viaja al api", async () => {
    const { mock } = renderSummary("/pagos?mes=2026-09");

    await waitFor(() => {
      expect(summaryMonths(mock)).toEqual(["2026-09"]);
    });
    expect(await within(region()).findByRole("group", { name: "Septiembre 2026 · total" })).toBeInTheDocument();
  });

  it.each([["2026-13"], ["2026-1"], ["octubre"]])("un mes mal formado (%s) se ignora y se usa el actual", async (mes) => {
    const { mock } = renderSummary(`/pagos?mes=${mes}`);

    await waitFor(() => {
      expect(summaryMonths(mock)).toEqual(["2026-10"]);
    });
  });

  it("cambiar el mes lo deja en la URL y conserva los demás parámetros", async () => {
    const { mock, router } = renderSummary("/pagos?method=nequi&offset=25");
    await within(region()).findByRole("group", { name: "Octubre 2026 · total" });

    fireEvent.change(within(region()).getByLabelText("Mes"), { target: { value: "2026-08" } });

    await waitFor(() => {
      expect(router.state.location.search).toBe("?method=nequi&offset=25&mes=2026-08");
    });
    await waitFor(() => {
      expect(summaryMonths(mock).at(-1)).toBe("2026-08");
    });
  });

  it("borrar el mes vuelve al actual y lo quita de la URL", async () => {
    const { router } = renderSummary("/pagos?mes=2026-08");
    await within(region()).findByRole("group", { name: "Agosto 2026 · total" });

    fireEvent.change(within(region()).getByLabelText("Mes"), { target: { value: "" } });

    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
  });
});

describe("MonthSummary · tarjetas", () => {
  it("total con los pagos válidos, uno por medio con su etiqueta y el contador de anulados", async () => {
    renderSummary();

    await loaded();
    expect(card("Octubre 2026 · total")).toHaveTextContent("Octubre 2026 · total$ 18.240.000152 pagos válidos");
    expect(card("Efectivo")).toHaveTextContent("Efectivo$ 9.100.000");
    expect(card("Nequi")).toHaveTextContent("Nequi$ 6.340.000");
    expect(card("Bre-B")).toHaveTextContent("Bre-B$ 2.800.000");
    expect(card("Anulados")).toHaveTextContent("Anulados3No suman al total");
  });

  it("un mes sin pagos muestra $ 0 en cada tarjeta y 0 anulados", async () => {
    renderSummary("/pagos", {
      "GET /payments/summary": { status: 200, body: paymentsSummary({ total_cop: 0, payments_count: 0, voided_count: 0, by_method: { cash: 0, nequi: 0, breb: 0 } }) },
    });

    await loaded();
    expect(card("Octubre 2026 · total")).toHaveTextContent("$ 00 pagos válidos");
    for (const label of ["Efectivo", "Nequi", "Bre-B"]) expect(card(label)).toHaveTextContent(`${label}$ 0`);
    expect(card("Anulados")).toHaveTextContent("Anulados0");
  });

  it("un solo pago válido lo dice en singular", async () => {
    renderSummary("/pagos", { "GET /payments/summary": { status: 200, body: paymentsSummary({ payments_count: 1 }) } });

    await loaded();
    expect(card("Octubre 2026 · total")).toHaveTextContent("1 pago válido");
  });

  it("las etiquetas de los medios salen de Configuración", async () => {
    renderSummary("/pagos", {
      "GET /payments/methods": {
        status: 200,
        body: {
          items: [
            { code: "cash", label: "Caja", hint: "" },
            { code: "nequi", label: "Nequi", hint: "" },
            { code: "breb", label: "Bre-B", hint: "" },
          ],
        },
      },
    });

    expect(await within(region()).findByRole("group", { name: "Caja" })).toHaveTextContent("Caja$ 9.100.000");
  });

  it("mientras carga, las tarjetas lo dicen", async () => {
    renderSummary("/pagos", { "GET /payments/summary": () => new Promise(() => undefined) });

    await waitFor(() => {
      expect(card("Anulados")).toHaveAttribute("aria-busy", "true");
    });
  });

  it("sin violaciones de accesibilidad", async () => {
    const { container } = renderSummary();
    await within(region()).findByRole("group", { name: "Octubre 2026 · total" });

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("MonthSummary · errores", () => {
  it("un 422 de `month` (fuera de 2020 a 2100) se explica con el rango", async () => {
    renderSummary("/pagos?mes=2019-12", { "GET /payments/summary": apiError(422, "validation_error", { field: "month" }) });

    expect(await within(region()).findByRole("alert")).toHaveTextContent("Elige un mes entre enero de 2020 y diciembre de 2100.");
  });

  it("otro error deja Reintentar en las tarjetas y vuelve a pedir el resumen", async () => {
    let fail = true;
    const { mock, user } = renderSummary("/pagos", {
      "GET /payments/summary": () => (fail ? apiError(500, "internal_error") : { status: 200, body: paymentsSummary() }),
    });

    const total = await within(region()).findByRole("group", { name: "Octubre 2026 · total" });
    await within(total).findByText("No se pudo cargar");
    fail = false;
    await user.click(within(total).getByRole("button", { name: "Reintentar" }));

    expect(await within(region()).findByText("$ 18.240.000")).toBeInTheDocument();
    expect(summaryMonths(mock)).toHaveLength(2);
  });
});

describe("revisión S3-F6 (M3) · monthInputChange", () => {
  it("un mes completo se confirma, vacío vuelve al actual y un texto a medias es borrador", () => {
    expect(monthInputChange("2026-08")).toEqual({ kind: "commit", month: "2026-08" });
    expect(monthInputChange(" 2026-08 ")).toEqual({ kind: "commit", month: "2026-08" });
    expect(monthInputChange("")).toEqual({ kind: "clear" });
    expect(monthInputChange("  ")).toEqual({ kind: "clear" });
    expect(monthInputChange("2026-0")).toEqual({ kind: "draft", text: "2026-0" });
    expect(monthInputChange("2026-13")).toEqual({ kind: "draft", text: "2026-13" });
  });
});
