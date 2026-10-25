// S3-F6 · US-098, US-099 y US-100 (front): /pagos (Pagos.html), admin y coach (`payments.view`).
// - Encabezado con el total y "Registrar pago" (`payments.register`, abre el panel con ?pago=nuevo).
// - Resumen del mes arriba (MonthSummary, su prueba aparte).
// - Filtros en la URL: rango de fechas (el día de Bogotá pasa a UTC y `to` es exclusivo), medio,
//   registró, estado Todos/Válidos/Anulados que arranca en Todos (D37) y retroactivos; un valor
//   desconocido no viaja. La búsqueda vive en memoria (S2-D41) y viaja como `q`.
// - Columnas: socio (enlace a la ficha), fecha y hora de Bogotá, membresía ("Mensual 29 oct–28 nov"),
//   valor, medio, referencia, registró (el correo parcial tal cual, S3-D57) y estado (StatusTag
//   "Válido" o "Anulado", marca "Retroactivo"); "Ver" abre el detalle. Sin editar ni borrar.
// - Estados: carga, vacío con y sin filtros, página pasada, error con Reintentar, 403, 422 y 429.
import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { apiError, SELL_NOW } from "../../../test/memberships";
import {
  DIEGO_PAYMENT_ID,
  findPaymentRow,
  PAYMENT_ID,
  PAYMENT_ROWS,
  paymentDetail,
  paymentDetailKey,
  paymentListCalls,
  paymentOut,
  paymentRow,
  paymentsPage,
  renderPayments,
  SOFIA_PAYMENT_ID,
} from "../../../test/payments";
import { voidKey } from "../../../test/paymentPanel";
import { setViewportWidth } from "../../../test/server";
import { registeredByOptions } from "./PaymentsPage";
import { signInAs, signOutForTests } from "../../../test/session";

const lastCall = (mock: Parameters<typeof paymentListCalls>[0]): URLSearchParams => {
  const calls = paymentListCalls(mock);
  const last = calls[calls.length - 1];
  if (!last) throw new Error("sin llamadas a GET /payments");
  return last;
};

const filters = () => screen.getByRole("search");
const select = (name: string) => within(filters()).getByRole("combobox", { name });

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"], now: SELL_NOW });
  setViewportWidth(1440);
  signInAs("coach");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("PaymentsPage · estructura (Pagos.html)", () => {
  it("título con el total y 'Registrar pago' que abre el panel con ?pago=nuevo", async () => {
    renderPayments();

    expect(await screen.findByRole("heading", { level: 1, name: "Pagos3 en total" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Registrar pago" })).toHaveAttribute("href", "/pagos?pago=nuevo");
  });

  it("'Registrar pago' conserva los filtros de la URL", async () => {
    renderPayments("/pagos?method=nequi");

    expect(await screen.findByRole("link", { name: "Registrar pago" })).toHaveAttribute("href", "/pagos?method=nequi&pago=nuevo");
  });

  it("el resumen del mes está arriba de los filtros", async () => {
    renderPayments();

    const summary = await screen.findByRole("region", { name: "Resumen del mes" });
    expect(summary.compareDocumentPosition(filters()) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("cada fila: socio con enlace a la ficha, fecha y hora de Bogotá, membresía, valor, medio, referencia, registró y estado", async () => {
    renderPayments();

    const row = await findPaymentRow("Laura Gómez");
    const cells = within(row).getAllByRole("cell");
    expect(within(row).getByRole("link", { name: "Laura Gómez" })).toHaveAttribute("href", "/socios/aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa");
    expect(cells.map((cell) => cell.textContent)).toEqual([
      "Laura Gómez",
      "20 oct 2026, 2:10 p. m.",
      "Mensual 29 oct–28 nov",
      "$ 120.000",
      "Nequi",
      "M12345678",
      "c•••@apex.test",
      "Válido",
      "Ver",
    ]);
  });

  it("sin referencia muestra una raya y el registró del admin es su correo parcial", async () => {
    renderPayments();

    const row = await findPaymentRow("Diego Mora");
    const cells = within(row).getAllByRole("cell");
    expect(cells[4]).toHaveTextContent("Efectivo");
    expect(cells[5]).toHaveTextContent("—");
    expect(cells[6]).toHaveTextContent("a•••@apex.test");
  });

  it("registró en null (cuenta que ya no existe) muestra una raya", async () => {
    renderPayments("/pagos", { rows: [paymentRow({ registered_by_name: null })] });

    const row = await findPaymentRow("Laura Gómez");
    expect(within(row).getAllByRole("cell")[6]).toHaveTextContent("—");
  });

  it("un pago anulado lleva 'Anulado' con texto y uno retroactivo la marca 'Retroactivo'", async () => {
    renderPayments();

    const row = await findPaymentRow("Sofía Pardo");
    expect(within(row).getByText("Anulado")).toHaveAttribute("data-payment", "voided");
    expect(within(row).getByText("Retroactivo")).toBeInTheDocument();
    expect(within(await findPaymentRow("Laura Gómez")).queryByText("Retroactivo")).not.toBeInTheDocument();
  });

  it("el medio se muestra con la etiqueta de Configuración", async () => {
    renderPayments("/pagos", {
      handlers: {
        "GET /payments/methods": {
          status: 200,
          body: {
            items: [
              { code: "cash", label: "Efectivo", hint: "" },
              { code: "nequi", label: "Nequi del box", hint: "" },
              { code: "breb", label: "Bre-B", hint: "" },
            ],
          },
        },
      },
    });

    const row = await findPaymentRow("Laura Gómez");
    await waitFor(() => {
      expect(within(row).getAllByRole("cell")[4]).toHaveTextContent("Nequi del box");
    });
  });

  it("no hay botones ni enlaces de editar o borrar (un pago nunca se edita)", async () => {
    signInAs("admin");
    renderPayments();
    await findPaymentRow("Laura Gómez");

    expect(screen.queryByRole("button", { name: /editar|borrar|eliminar/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /editar|borrar|eliminar/i })).not.toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad con la lista cargada", async () => {
    const { container } = renderPayments();
    await findPaymentRow("Laura Gómez");

    expect(await axe(container)).toHaveNoViolations();
  });

  it("en celular la lista son tarjetas con el socio como enlace", async () => {
    setViewportWidth(390);
    renderPayments();

    const list = await screen.findByRole("list", { name: "Pagos" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(3);
    expect(within(list).getByRole("link", { name: "Laura Gómez" })).toBeInTheDocument();
  });
});

describe("PaymentsPage · filtros en la URL", () => {
  it("sin filtros pide la primera página de 25 sin estado (Todos, D37)", async () => {
    const { mock } = renderPayments();
    await findPaymentRow("Laura Gómez");

    const params = lastCall(mock);
    expect(Object.fromEntries(params)).toEqual({ limit: "25", offset: "0" });
    expect(select("Estado")).toHaveValue("");
    expect(within(select("Estado")).getByRole("option", { selected: true })).toHaveTextContent("Todos");
  });

  it("el rango de la URL viaja en UTC: 'Desde' es el día de Bogotá a las 00:00 y 'Hasta' es exclusivo (día siguiente)", async () => {
    const { mock } = renderPayments("/pagos?from=2026-10-01&to=2026-10-20");
    await findPaymentRow("Laura Gómez");

    const params = lastCall(mock);
    expect(params.get("from")).toBe("2026-10-01T05:00:00.000Z");
    expect(params.get("to")).toBe("2026-10-21T05:00:00.000Z");
    expect(within(filters()).getByLabelText("Desde")).toHaveValue("2026-10-01");
    expect(within(filters()).getByLabelText("Hasta")).toHaveValue("2026-10-20");
  });

  it("elegir las fechas las deja en la URL como días y las manda en UTC", async () => {
    const { mock, router } = renderPayments();
    await findPaymentRow("Laura Gómez");

    fireEvent.change(within(filters()).getByLabelText("Desde"), { target: { value: "2026-10-05" } });
    await waitFor(() => {
      expect(router.state.location.search).toBe("?from=2026-10-05");
    });
    fireEvent.change(within(filters()).getByLabelText("Hasta"), { target: { value: "2026-10-31" } });
    await waitFor(() => {
      expect(router.state.location.search).toBe("?from=2026-10-05&to=2026-10-31");
    });
    await waitFor(() => {
      expect(lastCall(mock).get("to")).toBe("2026-11-01T05:00:00.000Z");
    });
    expect(lastCall(mock).get("from")).toBe("2026-10-05T05:00:00.000Z");
  });

  it("un rango invertido no viaja y se explica", async () => {
    const { mock } = renderPayments("/pagos?from=2026-10-20&to=2026-10-01");
    await findPaymentRow("Laura Gómez");

    expect(screen.getByText("La fecha 'Hasta' es anterior a 'Desde'. Corrígela para filtrar por fecha.")).toBeInTheDocument();
    expect(lastCall(mock).has("from")).toBe(false);
    expect(lastCall(mock).has("to")).toBe(false);
  });

  it("medio, registró, estado y retroactivos de la URL viajan al api", async () => {
    const { mock } = renderPayments(`/pagos?method=nequi&registered_by=00000000-0000-4000-8000-000000000002&voided=true&backdated=true`);
    await findPaymentRow("Laura Gómez");

    const params = lastCall(mock);
    expect(params.get("method")).toBe("nequi");
    expect(params.get("registered_by")).toBe("00000000-0000-4000-8000-000000000002");
    expect(params.get("voided")).toBe("true");
    expect(params.get("backdated")).toBe("true");
    expect(select("Medio")).toHaveValue("nequi");
    expect(select("Estado")).toHaveValue("true");
    expect(select("Retroactivos")).toHaveValue("true");
  });

  it("nada desconocido viaja: medio, usuario, estado, retroactivo o fecha que no existen", async () => {
    const { mock } = renderPayments("/pagos?method=card&registered_by=yo&voided=quizas&backdated=1&from=2026-02-30&to=ayer&offset=0");
    await findPaymentRow("Laura Gómez");

    expect(Object.fromEntries(lastCall(mock))).toEqual({ limit: "25", offset: "0" });
  });

  it("Estado: 'Válidos' manda voided=false y 'Anulados' voided=true; 'Todos' lo quita", async () => {
    const { mock, router } = renderPayments();
    await findPaymentRow("Laura Gómez");

    fireEvent.change(select("Estado"), { target: { value: "false" } });
    await waitFor(() => {
      expect(lastCall(mock).get("voided")).toBe("false");
    });
    expect(router.state.location.search).toBe("?voided=false");
    fireEvent.change(select("Estado"), { target: { value: "true" } });
    await waitFor(() => {
      expect(lastCall(mock).get("voided")).toBe("true");
    });
    fireEvent.change(select("Estado"), { target: { value: "" } });
    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
    await waitFor(() => {
      expect(lastCall(mock).has("voided")).toBe(false);
    });
  });

  it("Medio ofrece los tres medios con 'Todos' y filtra por el código", async () => {
    const { mock } = renderPayments();
    await findPaymentRow("Laura Gómez");

    expect(within(select("Medio")).getAllByRole("option").map((o) => o.textContent)).toEqual(["Todos", "Efectivo", "Nequi", "Bre-B"]);
    fireEvent.change(select("Medio"), { target: { value: "breb" } });
    await waitFor(() => {
      expect(lastCall(mock).get("method")).toBe("breb");
    });
  });

  it("Registró ofrece 'Yo' (la sesión) y quienes aparecen en la página, con su correo parcial", async () => {
    const { mock } = renderPayments();
    await findPaymentRow("Laura Gómez");

    const options = within(select("Registró")).getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual(["Cualquiera", "Yo (coach@apex.test)", "a•••@apex.test"]);
    fireEvent.change(select("Registró"), { target: { value: "00000000-0000-4000-8000-000000000001" } });
    await waitFor(() => {
      expect(lastCall(mock).get("registered_by")).toBe("00000000-0000-4000-8000-000000000001");
    });
  });

  it("un usuario de la URL que no está en la página sigue visible como 'Usuario elegido'", async () => {
    renderPayments("/pagos?registered_by=12345678-1234-4234-8234-123456789012");
    await findPaymentRow("Laura Gómez");

    expect(select("Registró")).toHaveValue("12345678-1234-4234-8234-123456789012");
    expect(within(select("Registró")).getByRole("option", { selected: true })).toHaveTextContent("Usuario elegido");
  });

  it("Retroactivos: 'Solo retroactivos' manda backdated=true y 'Sin retroactivos' backdated=false", async () => {
    const { mock } = renderPayments();
    await findPaymentRow("Laura Gómez");

    fireEvent.change(select("Retroactivos"), { target: { value: "true" } });
    await waitFor(() => {
      expect(lastCall(mock).get("backdated")).toBe("true");
    });
    fireEvent.change(select("Retroactivos"), { target: { value: "false" } });
    await waitFor(() => {
      expect(lastCall(mock).get("backdated")).toBe("false");
    });
  });

  it("la búsqueda viaja como q pero nunca llega a la URL (S2-D41)", async () => {
    const { mock, router, user } = renderPayments();
    await findPaymentRow("Laura Gómez");

    await user.type(within(filters()).getByRole("searchbox", { name: "Buscar" }), "M12345678");
    await waitFor(() => {
      expect(lastCall(mock).get("q")).toBe("M12345678");
    });
    expect(router.state.location.search).not.toContain("M12345678");
  });

  it("un q en la URL se ignora", async () => {
    const { mock } = renderPayments("/pagos?q=1020304050");
    await findPaymentRow("Laura Gómez");

    expect(lastCall(mock).has("q")).toBe(false);
  });

  it("Limpiar borra filtros y búsqueda y conserva el mes del resumen", async () => {
    const { router, user } = renderPayments("/pagos?mes=2026-09&method=nequi&voided=true");
    await findPaymentRow("Laura Gómez");

    await user.click(within(filters()).getByRole("button", { name: "Limpiar" }));

    await waitFor(() => {
      expect(router.state.location.search).toBe("?mes=2026-09");
    });
  });
});

describe("PaymentsPage · paginación", () => {
  it("con más de una página pinta Pagination y la siguiente pide offset 25", async () => {
    const { mock, user } = renderPayments("/pagos", { handlers: { "GET /payments": (call) => paymentsPage(call, PAYMENT_ROWS, 60) } });
    await findPaymentRow("Laura Gómez");

    await user.click(screen.getByRole("button", { name: /siguiente/i }));

    await waitFor(() => {
      expect(lastCall(mock).get("offset")).toBe("25");
    });
  });

  it("el tamaño de página de la URL viaja (50)", async () => {
    const { mock } = renderPayments("/pagos?limit=50");
    await findPaymentRow("Laura Gómez");

    expect(lastCall(mock).get("limit")).toBe("50");
  });

  it("una página pasada del final lo dice y vuelve a la primera", async () => {
    const { user, router } = renderPayments("/pagos?offset=50", { handlers: { "GET /payments": (call) => paymentsPage(call, [], 3) } });

    expect(await screen.findByText("Esta página ya no tiene pagos.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ir a la primera página" }));
    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
  });
});

describe("PaymentsPage · vacío y errores", () => {
  it("vacío sin filtros invita a registrar el primer pago", async () => {
    renderPayments("/pagos", { rows: [] });

    expect(await screen.findByText("Todavía no hay pagos registrados.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Registrar el primer pago" })).toHaveAttribute("href", "/pagos?pago=nuevo");
  });

  it("vacío con filtros: 'No hay pagos con estos filtros' y Limpiar filtros", async () => {
    const { user, router } = renderPayments("/pagos?method=breb", { rows: [] });

    expect(await screen.findByText("No hay pagos con estos filtros")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }));
    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
  });

  it("un error de la lista se explica y Reintentar la pide de nuevo", async () => {
    let fail = true;
    const { mock, user } = renderPayments("/pagos", {
      handlers: { "GET /payments": (call) => (fail ? apiError(500, "internal_error") : paymentsPage(call)) },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar los pagos. Intenta de nuevo.");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    await findPaymentRow("Laura Gómez");
    expect(paymentListCalls(mock).length).toBeGreaterThanOrEqual(2);
  });

  it("un 422 de las fechas pide revisarlas", async () => {
    renderPayments("/pagos?from=2019-01-01", { handlers: { "GET /payments": apiError(422, "validation_error", { field: "from" }) } });

    expect(await screen.findByRole("alert")).toHaveTextContent("Revisa las fechas del filtro: alguna está fuera del rango permitido. Límpialas e intenta de nuevo.");
  });

  it("un 403 dice que no tiene permiso", async () => {
    renderPayments("/pagos", { handlers: { "GET /payments": apiError(403, "forbidden") } });

    expect(await screen.findByRole("alert")).toHaveTextContent("No tienes permiso para ver los pagos. Si lo necesitas, pídeselo a un administrador.");
  });

  it("un 429 de la búsqueda dice cuánto esperar", async () => {
    renderPayments("/pagos", { handlers: { "GET /payments": apiError(429, "rate_limited", {}, { "Retry-After": "30" }) } });

    expect(await screen.findByRole("alert")).toHaveTextContent("Hiciste muchas búsquedas seguidas. Espera 30 segundos e intenta de nuevo.");
  });
});

describe("PaymentsPage · detalle", () => {
  it("'Ver' abre el detalle del pago de esa fila", async () => {
    const { mock, user } = renderPayments("/pagos", {
      handlers: { [paymentDetailKey(DIEGO_PAYMENT_ID)]: { status: 200, body: paymentDetail({ id: DIEGO_PAYMENT_ID, member_first_name: "Diego", member_last_name: "Mora", method: "cash", reference: null }) } },
    });

    await user.click(within(await findPaymentRow("Diego Mora")).getByRole("button", { name: "Ver el pago de Diego Mora" }));

    const dialog = await screen.findByRole("dialog", { name: "Detalle del pago" });
    expect(await within(dialog).findByRole("link", { name: "Diego Mora" })).toBeInTheDocument();
    expect(mock.callsTo(paymentDetailKey(DIEGO_PAYMENT_ID))).toHaveLength(1);
  });

  it("Cerrar devuelve a la lista", async () => {
    const { user } = renderPayments();

    await user.click(within(await findPaymentRow("Laura Gómez")).getByRole("button", { name: "Ver el pago de Laura Gómez" }));
    const dialog = await screen.findByRole("dialog", { name: "Detalle del pago" });
    await user.click(within(dialog).getByRole("button", { name: "Cerrar" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("el admin anula desde el detalle y la lista se relee", async () => {
    signInAs("admin");
    let voided = false;
    const { mock, user } = renderPayments("/pagos", {
      handlers: {
        "GET /payments": (call) => paymentsPage(call, voided ? [paymentRow({ id: SOFIA_PAYMENT_ID, voided: true, void_reason: "Duplicado" })] : PAYMENT_ROWS),
        [voidKey(PAYMENT_ID)]: () => {
          voided = true;
          return { status: 200, body: paymentOut({ id: PAYMENT_ID, method: "nequi", reference: "M12345678", voided: true, voided_at: "2026-10-28T15:00:00Z", voided_by: "u", void_reason: "Duplicado" }) };
        },
      },
    });

    await user.click(within(await findPaymentRow("Laura Gómez")).getByRole("button", { name: "Ver el pago de Laura Gómez" }));
    const dialog = await screen.findByRole("dialog", { name: "Detalle del pago" });
    await user.click(await within(dialog).findByRole("button", { name: "Anular pago" }));
    const confirm = await screen.findByRole("dialog", { name: "¿Anular este pago?" });
    await user.type(within(confirm).getByRole("textbox", { name: /^Motivo/ }), "Duplicado");
    await user.click(within(confirm).getByRole("button", { name: "Anular pago" }));

    expect(await screen.findByRole("dialog", { name: "Pago anulado" })).toBeInTheDocument();
    await waitFor(() => {
      expect(paymentListCalls(mock).length).toBeGreaterThanOrEqual(2);
    });
  });
});

describe("revisión S3-F6", () => {
  it("M1: si el panel cierra la anulación por fuera, 'Ver' vuelve a abrir el detalle (no la anulación)", async () => {
    signInAs("admin");
    const { user, router } = renderPayments();

    await user.click(within(await findPaymentRow("Laura Gómez")).getByRole("button", { name: "Ver el pago de Laura Gómez" }));
    await user.click(await within(await screen.findByRole("dialog", { name: "Detalle del pago" })).findByRole("button", { name: "Anular pago" }));
    expect(await screen.findByRole("dialog", { name: "¿Anular este pago?" })).toBeInTheDocument();

    await act(async () => {
      await router.navigate("/pagos?pago=nuevo");
    });
    expect(screen.queryByRole("dialog", { name: "¿Anular este pago?" })).not.toBeInTheDocument();
    await act(async () => {
      await router.navigate("/pagos");
    });
    await user.click(within(await findPaymentRow("Laura Gómez")).getByRole("button", { name: "Ver el pago de Laura Gómez" }));

    expect(await screen.findByRole("dialog", { name: "Detalle del pago" })).toBeInTheDocument();
    expect(screen.queryByRole("dialog", { name: "¿Anular este pago?" })).not.toBeInTheDocument();
  });

  it("M2: dos correos parciales iguales se distinguen con un número", () => {
    const options = registeredByOptions(
      null,
      [
        { id: "u1", name: "c•••@apex.test" },
        { id: "u2", name: "c•••@apex.test" },
        { id: "u3", name: null },
      ],
      "",
    );

    expect(options.map((o) => o.label)).toEqual(["c•••@apex.test", "c•••@apex.test (2)", "Usuario sin correo"]);
  });

  it("M2: al filtrar por una persona las demás vistas siguen en 'Registró'", async () => {
    const { mock } = renderPayments("/pagos", {
      handlers: {
        "GET /payments": (call) => {
          const who = new URL(call.url, "http://apex.test").searchParams.get("registered_by");
          return paymentsPage(call, who ? PAYMENT_ROWS.filter((r) => r.registered_by === who) : PAYMENT_ROWS);
        },
      },
    });
    await findPaymentRow("Laura Gómez");

    fireEvent.change(select("Registró"), { target: { value: "00000000-0000-4000-8000-000000000001" } });
    await waitFor(() => {
      expect(lastCall(mock).get("registered_by")).toBe("00000000-0000-4000-8000-000000000001");
    });
    await waitFor(() => {
      expect(screen.queryByRole("link", { name: "Laura Gómez" })).not.toBeInTheDocument();
    });

    expect(within(select("Registró")).getAllByRole("option").map((o) => o.textContent)).toEqual(["Cualquiera", "Yo (coach@apex.test)", "a•••@apex.test"]);
  });

  it("L6: mientras llega la página nueva el encabezado no muestra el total anterior", async () => {
    let release: () => void = () => undefined;
    const { user } = renderPayments("/pagos", {
      handlers: {
        "GET /payments": (call) => {
          const offset = new URL(call.url, "http://apex.test").searchParams.get("offset");
          if (offset === "0") return paymentsPage(call, PAYMENT_ROWS, 60);
          return new Promise((resolve) => {
            release = () => {
              resolve(paymentsPage(call, PAYMENT_ROWS, 60));
            };
          });
        },
      },
    });
    expect(await screen.findByRole("heading", { level: 1, name: "Pagos60 en total" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /siguiente/i }));

    expect(await screen.findByRole("heading", { level: 1, name: "Pagos" })).toBeInTheDocument();
    release();
    expect(await screen.findByRole("heading", { level: 1, name: "Pagos60 en total" })).toBeInTheDocument();
  });
});
