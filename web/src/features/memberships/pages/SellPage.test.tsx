// S3-F3 · US-084 y US-085 (front): /membresias/vender (Membresia_Vender.html), admin y coach
// (`memberships.sell`).
// - Tres pasos en una página: socio (búsqueda, S2-D41: `q` nunca en la URL), plan activo
//   (`usePlans({ active: true })`, S2-D26) y fechas (inicio hoy en Bogotá; fin y "Precio pactado"
//   de solo lectura, D16), y pago (FirstPaymentSection.test.tsx). Resumen con moneda y fecha de
//   core/i18n/format.
// - Envío: un solo POST por doble clic; `confirm_overpayment` solo si hubo modal (S3-D41); tras el
//   201 la caché de mutaciones no conserva el cuerpo (S3-D52).
// - Errores: 409 `membership_conflict` con "Renovar"; 422 por campo con foco; 503 `busy` sin
//   limpiar el formulario; planes vacíos o con error.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { MEMBERS } from "../../../test/members";
import {
  apiError,
  pickMember,
  pickPlan,
  renderSell,
  SELL_NOW,
  SELL_TODAY,
  sellBodies,
  sellKey,
  sellMembershipOut,
  summaryValue,
} from "../../../test/memberships";
import { PLANS } from "../../../test/plans";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";

const submitButton = () => screen.getByRole("button", { name: /^Vender/ });
const alertBox = () => screen.getByRole("alert");

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

describe("SellPage · estructura (Membresia_Vender.html)", () => {
  it("muestra título, migas, los tres pasos, las tres secciones, el resumen y Cancelar", async () => {
    renderSell();

    expect(screen.getByRole("heading", { level: 1, name: "Vender membresía" })).toBeInTheDocument();
    const crumbs = screen.getByRole("navigation", { name: "Migas" });
    expect(within(crumbs).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Membresías", "Vender"]);
    const steps = screen.getByRole("list", { name: "Pasos de la venta" });
    expect(within(steps).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["1Socio", "2Plan y fechas", "3Pago"]);
    for (const name of ["1 · Socio", "2 · Plan y fechas", "3 · Pago", "Resumen"]) expect(screen.getByRole("heading", { level: 2, name })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Cancelar" })).toHaveAttribute("href", "/socios");
    expect(await screen.findByRole("radio", { name: /^Mensual/ })).toBeInTheDocument();
  });

  it("pide solo los planes activos y los muestra con su duración y precio", async () => {
    const { mock } = renderSell();

    const mensual = await screen.findByRole("radio", { name: "Mensual 30 días · $ 120.000" });
    expect(mensual).not.toBeChecked();
    expect(screen.getByRole("radio", { name: "12 clases 12 clases · 60 días para usarlas · $ 110.000" })).toBeInTheDocument();
    const query = new URL(mock.callsTo("GET /plans")[0]?.url ?? "", "http://apex.test").searchParams;
    expect(query.get("active")).toBe("true");
  });

  it("el inicio es hoy en Bogotá; fin y precio pactado son de solo lectura", async () => {
    const { user } = renderSell();
    await pickPlan(user, "Mensual");

    expect(screen.getByLabelText(/^Inicio/)).toHaveValue(SELL_TODAY);
    const end = screen.getByRole("textbox", { name: "Fin (calculado)" });
    expect(end).toHaveValue("27 nov 2026");
    expect(end).toHaveAttribute("readonly");
    expect(screen.getByText("Vale hasta el 27 nov 2026.")).toBeInTheDocument();
    const price = screen.getByRole("textbox", { name: "Precio pactado" });
    expect(price).toHaveValue("$ 120.000");
    expect(price).toHaveAttribute("readonly");
  });

  it("no tiene violaciones de axe", async () => {
    const { container } = renderSell();
    await screen.findByRole("radio", { name: /^Mensual/ });

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("SellPage · elegir el socio", () => {
  it("busca por texto sin llevar el texto a la URL y muestra plan y estado de cada socio", async () => {
    const { user, router, mock } = renderSell("/membresias/vender", { members: [{ ...MEMBERS.laura, membership_status: "expiring", plan_name: "Mensual" }] });

    await user.type(screen.getByRole("searchbox", { name: "Buscar socio" }), "1020304417");
    const option = await screen.findByRole("button", { name: /Laura Gómez/ });

    expect(option).toHaveTextContent("Mensual · Por vencer");
    expect(router.state.location.search).toBe("");
    expect(new URL(mock.callsTo("GET /members").at(-1)?.url ?? "", "http://apex.test").searchParams.get("q")).toBe("1020304417");
  });

  it("al elegirlo queda en una tarjeta con Cambiar socio, y entra al resumen", async () => {
    const { user } = renderSell();
    await pickMember(user);

    expect(screen.queryByRole("searchbox", { name: "Buscar socio" })).not.toBeInTheDocument();
    expect(summaryValue("Socio")).toBe("Laura Gómez");
    await user.click(screen.getByRole("button", { name: "Cambiar socio" }));
    expect(screen.getByRole("searchbox", { name: "Buscar socio" })).toBeInTheDocument();
    expect(summaryValue("Socio")).toBe("—");
  });

  it("un socio inactivo aparece pero no se puede elegir", async () => {
    const { user } = renderSell();
    await user.type(screen.getByRole("searchbox", { name: "Buscar socio" }), "andr");

    const andres = await screen.findByRole("button", { name: /Andrés Ruiz/ });
    expect(andres).toBeDisabled();
    expect(andres).toHaveTextContent("Inactivo: reactívalo antes de venderle");
  });

  it("sin resultados lo dice y ofrece crear el socio", async () => {
    const { user } = renderSell("/membresias/vender", { members: [] });
    await user.type(screen.getByRole("searchbox", { name: "Buscar socio" }), "zzz");

    expect(await screen.findByText("No encontramos socios con ese texto. Revisa la búsqueda o crea el socio.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "¿No está? Crear socio nuevo" })).toHaveAttribute("href", "/socios/nuevo");
  });

  it("si la búsqueda falla lo dice sin perder lo escrito", async () => {
    const { user } = renderSell("/membresias/vender", { handlers: { "GET /members": apiError(500, "internal_error") } });
    await user.type(screen.getByRole("searchbox", { name: "Buscar socio" }), "laura");

    expect(await screen.findByText("No pudimos buscar socios. Intenta de nuevo en un momento.")).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Buscar socio" })).toHaveValue("laura");
  });
});

describe("SellPage · resumen", () => {
  it("con socio y plan muestra socio, plan, vigencia, precio, pago, saldo y quién registra", async () => {
    const { user } = renderSell();
    await pickMember(user);
    await pickPlan(user, "Mensual");

    expect(summaryValue("Socio")).toBe("Laura Gómez");
    expect(summaryValue("Plan")).toBe("Mensual");
    expect(summaryValue("Vigencia")).toBe("28 oct 2026 – 27 nov 2026");
    expect(summaryValue("Precio")).toBe("$ 120.000");
    expect(summaryValue("Pago")).toBe("$ 120.000 · Efectivo");
    expect(summaryValue("Saldo")).toBe("$ 0");
    expect(summaryValue("Registra")).toBe("coach@apex.test");
  });

  it("un abono deja el saldo pendiente", async () => {
    const { user } = renderSell();
    await pickMember(user);
    await pickPlan(user, "Mensual");
    const amount = screen.getByRole("textbox", { name: /^Valor recibido/ });
    await user.clear(amount);
    await user.type(amount, "60000");

    expect(summaryValue("Pago")).toBe("$ 60.000 · Efectivo");
    expect(summaryValue("Saldo")).toBe("$ 60.000");
  });

  it("sin plan el resumen muestra rayas", () => {
    renderSell();

    for (const label of ["Socio", "Plan", "Vigencia", "Precio", "Saldo"]) expect(summaryValue(label)).toBe("—");
  });
});

describe("SellPage · vender", () => {
  it("vende con pago completo: el cuerpo exacto, y luego la venta registrada con su estado", async () => {
    const { user, mock } = renderSell();
    await pickMember(user);
    await pickPlan(user, "Mensual");
    await user.click(submitButton());

    const done = await screen.findByRole("heading", { level: 2, name: "Venta registrada" });
    expect(sellBodies(mock)).toEqual([
      {
        plan_id: PLANS.mensual.id,
        renew: false,
        start_date: SELL_TODAY,
        first_payment: { amount_cop: 120_000, method: "cash", paid_at: "2026-10-28T15:00:00.000Z", confirm_overpayment: false, confirm_duplicate: false },
      },
    ]);
    expect(done).toHaveFocus();
    const region = screen.getByRole("region", { name: "Venta registrada" });
    expect(within(region).getByText("La membresía de Laura Gómez quedó registrada.")).toBeInTheDocument();
    expect(summaryValue("Estado", region)).toBe("Al día");
    expect(summaryValue("Pagado", region)).toBe("$ 120.000");
    expect(summaryValue("Saldo", region)).toBe("$ 0");
    expect(summaryValue("Vigencia", region)).toBe("28 oct 2026 – 27 nov 2026");
    expect(within(region).getByRole("link", { name: "Ir a Socios" })).toHaveAttribute("href", "/socios");
  });

  it("una venta que queda pendiente de pago lo muestra con su saldo", async () => {
    const { user } = renderSell("/membresias/vender", {
      handlers: { [sellKey()]: { status: 201, body: sellMembershipOut({ status: "pending_payment", paid_cop: 60_000 }) } },
    });
    await pickMember(user);
    await pickPlan(user, "Mensual");
    await user.click(submitButton());

    const region = await screen.findByRole("region", { name: "Venta registrada" });
    expect(summaryValue("Estado", region)).toBe("Pendiente de pago");
    expect(summaryValue("Saldo", region)).toBe("$ 60.000");
  });

  it("sin pago el botón dice Vender y el cuerpo no lleva first_payment", async () => {
    const { user, mock } = renderSell();
    await pickMember(user);
    await pickPlan(user, "Mensual");
    await user.click(screen.getByRole("checkbox", { name: "Registrar el pago ahora" }));

    expect(screen.getByText("La membresía queda Pendiente de pago hasta que registres un pago.")).toBeInTheDocument();
    expect(summaryValue("Pago")).toBe("Sin pago");
    expect(summaryValue("Saldo")).toBe("$ 120.000");
    await user.click(screen.getByRole("button", { name: "Vender" }));

    await screen.findByRole("region", { name: "Venta registrada" });
    expect(sellBodies(mock)).toEqual([{ plan_id: PLANS.mensual.id, renew: false, start_date: SELL_TODAY }]);
  });

  it("invalida membresías, socios, pagos y el resumen de membresías", async () => {
    const { user, queryClient } = renderSell();
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    await pickMember(user);
    await pickPlan(user, "Mensual");
    await user.click(submitButton());
    await screen.findByRole("region", { name: "Venta registrada" });

    const keys = invalidate.mock.calls.map(([filters]) => filters?.queryKey);
    expect(keys).toEqual(expect.arrayContaining([["memberships"], ["members"], ["payments"], ["memberships-summary"]]));
  });

  it("tras el 201 la caché de mutaciones no conserva el cuerpo de la venta (S3-D52)", async () => {
    const { user, queryClient } = renderSell();
    await pickMember(user);
    await pickPlan(user, "Mensual");
    await user.click(submitButton());
    await screen.findByRole("region", { name: "Venta registrada" });

    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
    });
  });

  it("un doble clic envía una sola venta", async () => {
    let release: () => void = () => undefined;
    const { user, mock } = renderSell("/membresias/vender", {
      handlers: {
        [sellKey()]: () =>
          new Promise((resolve) => {
            release = () => {
              resolve({ status: 201, body: sellMembershipOut() });
            };
          }),
      },
    });
    await pickMember(user);
    await pickPlan(user, "Mensual");
    await user.dblClick(submitButton());

    expect(screen.getByRole("button", { name: "Vendiendo…" })).toBeDisabled();
    release();
    await screen.findByRole("region", { name: "Venta registrada" });
    expect(mock.callsTo(sellKey())).toHaveLength(1);
  });

  it("Vender otra membresía vuelve al formulario vacío", async () => {
    const { user } = renderSell();
    await pickMember(user);
    await pickPlan(user, "Mensual");
    await user.click(submitButton());
    await user.click(await screen.findByRole("button", { name: "Vender otra membresía" }));

    expect(screen.getByRole("searchbox", { name: "Buscar socio" })).toHaveValue("");
    expect(await screen.findByRole("radio", { name: /^Mensual/ })).not.toBeChecked();
  });
});

describe("SellPage · validación y errores", () => {
  it("sin socio ni plan no envía y dice qué falta", async () => {
    const { user, mock } = renderSell();
    await screen.findByRole("radio", { name: /^Mensual/ });
    await user.click(submitButton());

    expect(await screen.findByText("Elige el socio al que le vendes la membresía.")).toBeInTheDocument();
    expect(screen.getByText("Elige un plan.")).toBeInTheDocument();
    expect(mock.callsTo(sellKey())).toHaveLength(0);
  });

  it("409 membership_conflict avisa con un enlace Renovar que abre la renovación del socio", async () => {
    const { user, router } = renderSell("/membresias/vender", {
      handlers: { [sellKey()]: apiError(409, "membership_conflict", { existing_id: "88888888-8888-4888-8888-888888888888" }) },
    });
    await pickMember(user);
    await pickPlan(user, "Mensual");
    await user.click(submitButton());

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Laura Gómez ya tiene una membresía vigente o por empezar. Si quieres extenderla, renuévala.");
    expect(alert).toHaveFocus();
    const renew = within(alert).getByRole("link", { name: "Renovar" });
    expect(renew).toHaveAttribute("href", `/membresias/vender?socio=${MEMBERS.laura.id}&renovar=1`);

    await user.click(renew);
    expect(await screen.findByRole("heading", { level: 1, name: "Renovar membresía" })).toBeInTheDocument();
    expect(router.state.location.search).toBe(`?socio=${MEMBERS.laura.id}&renovar=1`);
    expect(summaryValue("Socio")).toBe("Laura Gómez");
  });

  it("422 de inicio va bajo Inicio con foco", async () => {
    const { user } = renderSell("/membresias/vender", { handlers: { [sellKey()]: apiError(422, "start_date_too_retroactive", { field: "start_date" }) } });
    await pickMember(user);
    await pickPlan(user, "Mensual");
    await user.click(submitButton());

    expect(await screen.findByText("La fecha de inicio es demasiado antigua. Elige una más reciente.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Inicio/)).toHaveFocus();
  });

  it.each([
    [apiError(409, "membership_overlap"), "Estas fechas se cruzan con otra membresía del socio. Elige otra fecha de inicio."],
    [apiError(422, "start_date_too_far", { field: "start_date" }), "La fecha de inicio está muy lejos. Elige una dentro del próximo año."],
  ])("%j va bajo Inicio", async (reply, message) => {
    const { user } = renderSell("/membresias/vender", { handlers: { [sellKey()]: reply } });
    await pickMember(user);
    await pickPlan(user, "Mensual");
    await user.click(submitButton());

    expect(await screen.findByText(message)).toBeInTheDocument();
  });

  it("422 plan_inactive va bajo el plan", async () => {
    const { user } = renderSell("/membresias/vender", { handlers: { [sellKey()]: apiError(422, "plan_inactive", { field: "plan_id" }) } });
    await pickMember(user);
    await pickPlan(user, "Mensual");
    await user.click(submitButton());

    expect(await screen.findByText("Este plan ya no está disponible para vender. Elige otro.")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /^Mensual/ })).toHaveFocus();
  });

  it("503 busy muestra que el sistema está ocupado, no reintenta y no limpia el formulario", async () => {
    const { user, mock } = renderSell("/membresias/vender", { handlers: { [sellKey()]: apiError(503, "busy", {}, { "Retry-After": "1" }) } });
    await pickMember(user);
    await pickPlan(user, "Mensual");
    await user.click(submitButton());

    expect(await screen.findByRole("alert")).toHaveTextContent("El sistema está ocupado; intenta de nuevo.");
    expect(mock.callsTo(sellKey())).toHaveLength(1);
    expect(summaryValue("Socio")).toBe("Laura Gómez");
    expect(screen.getByRole("radio", { name: /^Mensual/ })).toBeChecked();
    expect(screen.getByRole("textbox", { name: /^Valor recibido/ })).toHaveValue("$ 120.000");
  });

  it.each([
    [apiError(422, "member_inactive"), "Este socio no está activo. Reactívalo antes de venderle una membresía."],
    [apiError(404, "member_not_found"), "No encontramos a este socio. Búscalo de nuevo."],
    [apiError(403, "forbidden"), "No tienes permiso para vender membresías. Si lo necesitas, pídeselo a un administrador."],
    [apiError(429, "rate_limited", {}, { "Retry-After": "30" }), "Hiciste muchas ventas seguidas. Espera 30 segundos e intenta de nuevo."],
    [apiError(500, "internal_error"), "No pudimos registrar la venta. Intenta de nuevo en un momento."],
    [apiError(409, "payment_limit_reached"), "Esta membresía ya tiene el máximo de pagos registrados. Revisa sus pagos."],
    [{ status: 201, body: { id: 1 } }, "La respuesta del servidor no es válida. Recarga la página e intenta de nuevo."],
  ])("%j se muestra como aviso general", async (reply, message) => {
    const { user } = renderSell("/membresias/vender", { handlers: { [sellKey()]: reply } });
    await pickMember(user);
    await pickPlan(user, "Mensual");
    await user.click(submitButton());

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });

  it("sin conexión lo dice como aviso general", async () => {
    const { user } = renderSell("/membresias/vender", { handlers: { [sellKey()]: () => Promise.reject(new TypeError("Failed to fetch")) } });
    await pickMember(user);
    await pickPlan(user, "Mensual");
    await user.click(submitButton());

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos conectar con el servidor. Intenta de nuevo.");
    expect(alertBox()).toHaveFocus();
  });
});

describe("SellPage · planes", () => {
  it("sin planes activos el coach ve que debe pedirlo a un administrador", async () => {
    renderSell("/membresias/vender", { plans: [] });

    expect(await screen.findByText("No hay planes activos para vender.")).toBeInTheDocument();
    expect(screen.getByText("Pídele a un administrador que active un plan.")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Crear un plan" })).not.toBeInTheDocument();
  });

  it("sin planes activos el admin puede ir a crear uno", async () => {
    signInAs("admin");
    renderSell("/membresias/vender", { plans: [] });

    expect(await screen.findByRole("link", { name: "Crear un plan" })).toHaveAttribute("href", "/planes");
  });

  it("si los planes no cargan lo dice y Reintentar los vuelve a pedir", async () => {
    let fail = true;
    const { user, mock } = renderSell("/membresias/vender", {
      handlers: {
        "GET /plans": (call) =>
          fail
            ? apiError(500, "internal_error")
            : { status: 200, body: { items: [PLANS.mensual], total: 1, limit: Number(new URL(call.url, "http://apex.test").searchParams.get("limit")), offset: 0 } },
      },
    });

    expect(await screen.findByText("No pudimos cargar los planes. Intenta de nuevo.")).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("radio", { name: /^Mensual/ })).toBeInTheDocument();
    expect(mock.callsTo("GET /plans")).toHaveLength(2);
  });
});

describe("SellPage · revisión S3-F3", () => {
  it("MEDIUM 3: al elegir un socio el foco va a Cambiar socio; al cambiarlo, al buscador", async () => {
    const { user } = renderSell();
    await pickMember(user);

    const change = screen.getByRole("button", { name: "Cambiar socio" });
    await waitFor(() => {
      expect(change).toHaveFocus();
    });
    await user.click(change);
    await waitFor(() => {
      expect(screen.getByRole("searchbox", { name: "Buscar socio" })).toHaveFocus();
    });
  });

  it("MEDIUM 4: Enter en el buscador no envía el formulario", async () => {
    const { user } = renderSell();
    await screen.findByRole("radio", { name: /^Mensual/ });
    await user.type(screen.getByRole("searchbox", { name: "Buscar socio" }), "laura{Enter}");

    expect(screen.queryByText("Elige el socio al que le vendes la membresía.")).not.toBeInTheDocument();
    expect(screen.queryByText("Elige un plan.")).not.toBeInTheDocument();
  });

  it("MEDIUM 5: el resultado de la búsqueda se anuncia en una región de estado", async () => {
    const { user } = renderSell("/membresias/vender", { members: [MEMBERS.laura] });
    const status = screen.getByRole("status", { name: "Resultado de la búsqueda" });
    await user.type(screen.getByRole("searchbox", { name: "Buscar socio" }), "laura");

    await waitFor(() => {
      expect(status).toHaveTextContent("1 socio encontrado");
    });
  });

  it("LOW 8: el aviso general se quita al cambiar de socio o de plan", async () => {
    const { user } = renderSell("/membresias/vender", { handlers: { [sellKey()]: apiError(422, "member_inactive") } });
    await pickMember(user);
    await pickPlan(user, "Mensual");
    await user.click(submitButton());
    await screen.findByRole("alert");

    await pickPlan(user, "12 clases");
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    await user.click(submitButton());
    await screen.findByRole("alert");
    await user.click(screen.getByRole("button", { name: "Cambiar socio" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
