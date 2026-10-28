// S3-F5 · US-089, US-090, US-091 y US-092 (front): /membresias (Membresias.html), admin y coach
// (`memberships.view`).
// - Encabezado con el total y "Vender membresía" (`memberships.sell`); el resumen de socios por
//   estado (GET /memberships/summary, useMembershipSummary) en KpiCard; chips de estado (varios a la
//   vez) con "Pendiente de pago" en texto (Q3, DESIGN-GAP); plan; rango "Vence entre".
// - Filtros en la URL: `status` separado por comas (también hacia el api, D18), `plan_id`,
//   `ends_from` y `ends_to`; un valor desconocido no viaja. La búsqueda vive en memoria (S2-D41).
// - Columnas: socio (enlace a la ficha), plan y precio, inicio, fin, clases restantes, pagado
//   ("$ 60.000 de $ 120.000 · abono"), StatusTag y acciones de la fila: Renovar
//   (`memberships.sell`), Registrar saldo (`payments.register`, abre el panel con `?pago=`),
//   Congelar (`memberships.freeze`, solo al día o por vencer) y Anular (`memberships.cancel`, solo
//   admin).
// - Estados: carga, vacío con y sin filtros, página pasada, error con Reintentar, 403, 422 y 429.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { MEMBERS } from "../../../test/members";
import {
  ANDRES_MEMBERSHIP_ID,
  apiError,
  cancelKey,
  findMembershipRow,
  freezeKey,
  MEMBERSHIP_ID,
  MEMBERSHIP_ROWS,
  membershipListCalls,
  membershipRow,
  membershipsPage,
  membershipSummary,
  renderMemberships,
  SELL_NOW,
} from "../../../test/memberships";
import { PLANS } from "../../../test/plans";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { pageNotice } from "../../../test/users";

const lastCall = (mock: Parameters<typeof membershipListCalls>[0]): URLSearchParams => {
  const calls = membershipListCalls(mock);
  const last = calls[calls.length - 1];
  if (!last) throw new Error("sin llamadas a GET /memberships");
  return last;
};
const chip = (name: string) => within(screen.getByRole("group", { name: "Estado" })).getByRole("button", { name: new RegExp(`^${name}`) });

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

describe("MembershipsPage · estructura (Membresias.html)", () => {
  it("título con el total y 'Vender membresía' para quien vende", async () => {
    renderMemberships();

    expect(await screen.findByRole("heading", { level: 1, name: "Membresías3 en total" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Vender membresía" })).toHaveAttribute("href", "/membresias/vender");
  });

  it("el resumen de socios por estado sale de GET /memberships/summary en tarjetas", async () => {
    const { mock } = renderMemberships();

    const summary = await screen.findByRole("region", { name: "Socios por estado de su membresía" });
    const values: [string, string][] = [
      ["Al día", "210"],
      ["Por vencer", "18"],
      ["Vencidos", "12"],
      ["Congelados", "3"],
      ["Pendientes de pago", "5"],
    ];
    for (const [label, value] of values) {
      await waitFor(() => {
        expect(within(summary).getByRole("group", { name: label })).toHaveTextContent(`${label}${value}`);
      });
    }
    expect(mock.callsTo("GET /memberships/summary")).toHaveLength(1);
  });

  it("si el resumen falla, sus tarjetas lo dicen y Reintentar lo pide de nuevo", async () => {
    let fail = true;
    const { user, mock } = renderMemberships("/membresias", {
      handlers: { "GET /memberships/summary": () => (fail ? apiError(500, "internal_error") : { status: 200, body: membershipSummary() }) },
    });
    const summary = await screen.findByRole("region", { name: "Socios por estado de su membresía" });
    const card = await within(summary).findByRole("group", { name: "Al día" });
    await waitFor(() => {
      expect(card).toHaveTextContent("No se pudo cargar");
    });

    fail = false;
    await user.click(within(card).getByRole("button", { name: "Reintentar" }));

    await waitFor(() => {
      expect(within(summary).getByRole("group", { name: "Al día" })).toHaveTextContent("Al día210");
    });
    expect(mock.callsTo("GET /memberships/summary")).toHaveLength(2);
  });

  it("chips de estado con texto, también 'Pendiente de pago' (Q3), ninguno activo al entrar", async () => {
    renderMemberships();

    const group = await screen.findByRole("group", { name: "Estado" });
    expect(within(group).getAllByRole("button").map((b) => b.textContent)).toEqual(["Activas", "Por vencer", "Vencidas", "Congeladas", "Pendiente de pago", "Anuladas"]);
    for (const button of within(group).getAllByRole("button")) expect(button).toHaveAttribute("aria-pressed", "false");
  });

  it("filtros: buscar socio, plan (con los planes) y 'Vence entre'", async () => {
    renderMemberships();

    const search = screen.getByRole("searchbox", { name: "Buscar socio" });
    expect(search).toHaveAttribute("placeholder", "Nombre o documento");
    const plan = screen.getByRole("combobox", { name: "Plan" });
    await waitFor(() => {
      expect(within(plan).getAllByRole("option").map((o) => o.textContent)).toEqual(["Cualquiera", "12 clases", "Mensual", "Promo apertura"]);
    });
    const range = screen.getByRole("group", { name: "Vence entre" });
    expect(within(range).getByLabelText("Desde")).toHaveAttribute("type", "date");
    expect(within(range).getByLabelText("Hasta")).toHaveAttribute("type", "date");
  });

  it("columnas del diseño y la fila de un abono: socio con enlace a su ficha, plan y precio, fechas y pagado", async () => {
    renderMemberships();

    const row = await findMembershipRow("Laura Gómez");
    const headers = within(screen.getByRole("table", { name: "Membresías" })).getAllByRole("columnheader").map((h) => h.textContent);
    expect(headers).toEqual(["Socio", "Plan", "Inicio", "Fin", "Clases restantes", "Pagado", "Estado", "Acciones"]);
    expect(within(row).getByRole("link", { name: "Laura Gómez" })).toHaveAttribute("href", `/socios/${MEMBERS.laura.id}`);
    const cells = within(row).getAllByRole("cell").map((c) => c.textContent);
    expect(cells.slice(1, 7)).toEqual(["Mensual · $ 120.000", "25 oct 2026", "24 nov 2026", "—", "$ 60.000 de $ 120.000 · abono", "Pendiente de pago"]);
  });

  it("un plan de clases dice las restantes y una pagada completa lo dice", async () => {
    renderMemberships();

    const row = await findMembershipRow("Andrés Ruiz");
    const cells = within(row).getAllByRole("cell").map((c) => c.textContent);
    expect(cells.slice(1, 7)).toEqual(["12 clases · $ 110.000", "1 sept 2026", "31 oct 2026", "2 de 12", "$ 110.000 · pagado", "Por vencer"]);
  });

  it("no tiene violaciones de axe", async () => {
    vi.useRealTimers();
    const { container } = renderMemberships();
    await findMembershipRow("Laura Gómez");

    expect(await axe(container)).toHaveNoViolations();
  });

  it("en celular la lista son tarjetas con las acciones", async () => {
    setViewportWidth(390);
    renderMemberships();

    const cards = await screen.findByRole("list", { name: "Membresías" });
    expect(within(cards).getAllByRole("listitem")).toHaveLength(3);
    expect(within(cards).getByRole("link", { name: "Laura Gómez" })).toHaveAttribute("href", `/socios/${MEMBERS.laura.id}`);
    expect(within(cards).getByRole("button", { name: "Congelar la membresía de Elena Vargas" })).toBeInTheDocument();
  });
});

describe("MembershipsPage · filtros en la URL", () => {
  it("sin filtros pide la primera página de 25 sin estado (el api excluye las anuladas)", async () => {
    const { mock } = renderMemberships();
    await findMembershipRow("Laura Gómez");

    expect(Object.fromEntries(lastCall(mock))).toEqual({ limit: "25", offset: "0" });
  });

  it("varios chips: status separado por comas en la URL y hacia el api, y vuelve a la primera página", async () => {
    const { user, mock, router } = renderMemberships("/membresias?offset=25");
    await findMembershipRow("Laura Gómez");

    await user.click(chip("Pendiente de pago"));
    await user.click(chip("Por vencer"));

    expect(chip("Por vencer")).toHaveAttribute("aria-pressed", "true");
    expect(chip("Pendiente de pago")).toHaveAttribute("aria-pressed", "true");
    expect(new URLSearchParams(router.state.location.search).get("status")).toBe("expiring,pending_payment");
    expect(router.state.location.search).not.toContain("offset");
    await waitFor(() => {
      expect(lastCall(mock).get("status")).toBe("expiring,pending_payment");
    });
    expect(lastCall(mock).get("offset")).toBe("0");
  });

  it("quitar el último chip quita status de la URL", async () => {
    const { user, router, mock } = renderMemberships("/membresias?status=frozen");
    await findMembershipRow("Laura Gómez");

    await user.click(chip("Congeladas"));

    expect(router.state.location.search).toBe("");
    await waitFor(() => {
      expect(lastCall(mock).has("status")).toBe(false);
    });
  });

  it("desde la URL: los estados conocidos se marcan y viajan en orden; uno desconocido no", async () => {
    const { mock } = renderMemberships("/membresias?status=frozen,basura,active");
    await findMembershipRow("Laura Gómez");

    expect(chip("Activas")).toHaveAttribute("aria-pressed", "true");
    expect(chip("Congeladas")).toHaveAttribute("aria-pressed", "true");
    expect(chip("Vencidas")).toHaveAttribute("aria-pressed", "false");
    expect(lastCall(mock).get("status")).toBe("active,frozen");
  });

  it("el plan queda en la URL como plan_id y viaja al api", async () => {
    const { user, mock, router } = renderMemberships();
    const plan = screen.getByRole("combobox", { name: "Plan" });
    await within(plan).findByRole("option", { name: "Mensual" });

    await user.selectOptions(plan, PLANS.mensual.id);

    expect(new URLSearchParams(router.state.location.search).get("plan_id")).toBe(PLANS.mensual.id);
    await waitFor(() => {
      expect(lastCall(mock).get("plan_id")).toBe(PLANS.mensual.id);
    });
  });

  it("un plan_id que no es un UUID no viaja", async () => {
    const { mock } = renderMemberships("/membresias?plan_id=basura");
    await findMembershipRow("Laura Gómez");

    expect(lastCall(mock).has("plan_id")).toBe(false);
  });

  it("'Vence entre' queda en la URL como ends_from y ends_to y viaja al api", async () => {
    const { mock, router } = renderMemberships();
    await findMembershipRow("Laura Gómez");
    const range = screen.getByRole("group", { name: "Vence entre" });

    fireEvent.change(within(range).getByLabelText("Desde"), { target: { value: "2026-10-01" } });
    fireEvent.change(within(range).getByLabelText("Hasta"), { target: { value: "2026-10-31" } });

    const search = new URLSearchParams(router.state.location.search);
    expect([search.get("ends_from"), search.get("ends_to")]).toEqual(["2026-10-01", "2026-10-31"]);
    await waitFor(() => {
      expect([lastCall(mock).get("ends_from"), lastCall(mock).get("ends_to")]).toEqual(["2026-10-01", "2026-10-31"]);
    });
  });

  it("un rango invertido se explica y no viaja al api", async () => {
    const { mock } = renderMemberships("/membresias?ends_from=2026-10-31&ends_to=2026-10-01");
    await findMembershipRow("Laura Gómez");

    expect(screen.getByText("La segunda fecha de 'Vence entre' es anterior a la primera. Corrígela para filtrar por vencimiento.")).toBeInTheDocument();
    expect(lastCall(mock).has("ends_from")).toBe(false);
    expect(lastCall(mock).has("ends_to")).toBe(false);
  });

  it("una fecha mal escrita en la URL no viaja", async () => {
    const { mock } = renderMemberships("/membresias?ends_from=ayer&ends_to=2026-10-31");
    await findMembershipRow("Laura Gómez");

    expect(lastCall(mock).has("ends_from")).toBe(false);
    expect(lastCall(mock).get("ends_to")).toBe("2026-10-31");
  });

  it("la búsqueda viaja al api pero nunca a la URL (S2-D41)", async () => {
    const { user, mock, router } = renderMemberships();
    await findMembershipRow("Laura Gómez");

    await user.type(screen.getByRole("searchbox", { name: "Buscar socio" }), "gómez");

    await waitFor(() => {
      expect(lastCall(mock).get("q")).toBe("gómez");
    });
    expect(router.state.location.search).not.toContain("q=");
    expect(router.state.location.search).not.toContain("g%C3%B3mez");
  });

  it("Limpiar quita estado, plan, rango y búsqueda", async () => {
    const { user, router, mock } = renderMemberships(`/membresias?status=active&plan_id=${PLANS.mensual.id}&ends_from=2026-10-01&ends_to=2026-10-31&limit=50`);
    await findMembershipRow("Laura Gómez");

    await user.click(screen.getByRole("button", { name: "Limpiar" }));

    expect(router.state.location.search).toBe("?limit=50");
    await waitFor(() => {
      expect(Object.fromEntries(lastCall(mock))).toEqual({ limit: "50", offset: "0" });
    });
  });

  it("paginación: 'Mostrar' 25, 50 o 100 en la URL y siguiente página con offset", async () => {
    const { user, mock, router } = renderMemberships("/membresias", { handlers: { "GET /memberships": (call) => membershipsPage(call, MEMBERSHIP_ROWS, 120) } });
    await findMembershipRow("Laura Gómez");
    const pagination = screen.getByRole("navigation", { name: "Paginación" });
    const size = within(pagination).getByRole("combobox", { name: "Mostrar" });
    expect(within(size).getAllByRole("option").map((o) => o.textContent)).toEqual(["25", "50", "100"]);

    await user.selectOptions(size, "50");
    expect(new URLSearchParams(router.state.location.search).get("limit")).toBe("50");
    await waitFor(() => {
      expect(lastCall(mock).get("limit")).toBe("50");
    });

    await user.click(within(pagination).getByRole("button", { name: /Siguiente/ }));
    await waitFor(() => {
      expect(lastCall(mock).get("offset")).toBe("50");
    });
  });
});

describe("MembershipsPage · acciones de la fila", () => {
  it("coach: Renovar y Registrar saldo en un abono; sin Congelar (pendiente) ni Anular (solo admin)", async () => {
    renderMemberships("/membresias?status=pending_payment");

    const row = await findMembershipRow("Laura Gómez");
    expect(within(row).getByRole("link", { name: "Renovar la membresía de Laura Gómez" })).toHaveAttribute("href", `/membresias/vender?socio=${MEMBERS.laura.id}&renovar=1`);
    expect(within(row).getByRole("link", { name: "Registrar saldo de Laura Gómez" })).toHaveAttribute("href", `/membresias?status=pending_payment&pago=${MEMBERSHIP_ID}`);
    expect(within(row).queryByRole("button", { name: /^Congelar/ })).toBeNull();
    expect(within(row).queryByRole("button", { name: /^Anular/ })).toBeNull();
  });

  it("coach: una al día o por vencer se congela; pagada completa no tiene Registrar saldo", async () => {
    renderMemberships();

    for (const name of ["Elena Vargas", "Andrés Ruiz"]) {
      const row = await findMembershipRow(name);
      expect(within(row).getByRole("button", { name: `Congelar la membresía de ${name}` })).toBeInTheDocument();
      expect(within(row).queryByRole("link", { name: /^Registrar saldo/ })).toBeNull();
    }
    expect(screen.queryByRole("button", { name: /^Anular/ })).toBeNull();
  });

  it("admin: Anular en cada membresía no anulada", async () => {
    signInAs("admin");
    renderMemberships();

    await findMembershipRow("Laura Gómez");
    expect(screen.getAllByRole("button", { name: /^Anular la membresía de/ }).map((b) => b.getAttribute("aria-label"))).toEqual([
      "Anular la membresía de Laura Gómez",
      "Anular la membresía de Andrés Ruiz",
      "Anular la membresía de Elena Vargas",
    ]);
  });

  it("una anulada no tiene acciones; una vencida con saldo no se cobra ni se congela, pero se renueva", async () => {
    signInAs("admin");
    renderMemberships("/membresias?status=cancelled,expired", {
      rows: [
        membershipRow({ member_name: "Laura Gómez", status: "cancelled" }),
        membershipRow({ id: ANDRES_MEMBERSHIP_ID, member_id: MEMBERS.andres.id, member_name: "Andrés Ruiz", status: "expired" }),
      ],
    });

    const cancelled = await findMembershipRow("Laura Gómez");
    expect(within(cancelled).queryAllByRole("button")).toHaveLength(0);
    expect(within(cancelled).getAllByRole("link")).toHaveLength(1);
    expect(within(cancelled).getAllByRole("cell").at(-1)).toHaveTextContent("—");
    const expired = await findMembershipRow("Andrés Ruiz");
    expect(within(expired).getByRole("link", { name: "Renovar la membresía de Andrés Ruiz" })).toBeInTheDocument();
    expect(within(expired).queryByRole("link", { name: /^Registrar saldo/ })).toBeNull();
    expect(within(expired).queryByRole("button", { name: /^Congelar/ })).toBeNull();
    expect(within(expired).getByRole("button", { name: "Anular la membresía de Andrés Ruiz" })).toBeInTheDocument();
  });

  it("Renovar lleva a la venta con el socio y su nombre en el estado de la navegación", async () => {
    const { user, router } = renderMemberships();
    const row = await findMembershipRow("Laura Gómez");

    await user.click(within(row).getByRole("link", { name: "Renovar la membresía de Laura Gómez" }));

    expect(router.state.location.pathname).toBe("/membresias/vender");
    expect(router.state.location.search).toBe(`?socio=${MEMBERS.laura.id}&renovar=1`);
    expect(router.state.location.state).toEqual({ memberName: "Laura Gómez" });
  });

  it("Registrar saldo abre el panel de pagos por la URL (?pago=) sin salir de la lista", async () => {
    const { user, router } = renderMemberships("/membresias?status=pending_payment&limit=50");
    const row = await findMembershipRow("Laura Gómez");

    await user.click(within(row).getByRole("link", { name: "Registrar saldo de Laura Gómez" }));

    expect(router.state.location.pathname).toBe("/membresias");
    const search = new URLSearchParams(router.state.location.search);
    expect([search.get("pago"), search.get("status"), search.get("limit")]).toEqual([MEMBERSHIP_ID, "pending_payment", "50"]);
  });

  it("Congelar abre el modal; al congelar se cierra, avisa el nuevo fin y relee la lista y el resumen", async () => {
    const { user, mock } = renderMemberships();
    const row = await findMembershipRow("Elena Vargas");
    const before = membershipListCalls(mock).length;

    await user.click(within(row).getByRole("button", { name: "Congelar la membresía de Elena Vargas" }));
    const dialog = screen.getByRole("dialog", { name: "Congelar la membresía de Elena Vargas" });
    const to = within(dialog).getByLabelText(/^Hasta/);
    fireEvent.change(to, { target: { value: "2026-11-06" } });
    await user.click(within(dialog).getByRole("button", { name: "Congelar" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(mock.callsTo(freezeKey()).map((c) => c.body)).toEqual([{ frozen_from: "2026-10-28", frozen_to: "2026-11-06" }]);
    expect(pageNotice()).toHaveTextContent("Membresía de Elena Vargas congelada. Ahora termina el 10 nov 2026.");
    await waitFor(() => {
      expect(membershipListCalls(mock).length).toBeGreaterThan(before);
    });
    expect(mock.callsTo("GET /memberships/summary").length).toBeGreaterThan(1);
  });

  it("admin: Anular abre el modal con motivo; al anular avisa y relee la lista", async () => {
    signInAs("admin");
    const { user, mock } = renderMemberships();
    const row = await findMembershipRow("Elena Vargas");
    const before = membershipListCalls(mock).length;

    await user.click(within(row).getByRole("button", { name: "Anular la membresía de Elena Vargas" }));
    const dialog = screen.getByRole("dialog", { name: "¿Anular la membresía de Elena Vargas?" });
    await user.type(within(dialog).getByRole("textbox", { name: /^Motivo/ }), "Vendida por error");
    await user.click(within(dialog).getByRole("button", { name: "Sí, anular" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    expect(mock.callsTo(cancelKey()).map((c) => c.body)).toEqual([{ reason: "Vendida por error" }]);
    expect(pageNotice()).toHaveTextContent("Membresía de Elena Vargas anulada. Sus pagos siguen registrados.");
    await waitFor(() => {
      expect(membershipListCalls(mock).length).toBeGreaterThan(before);
    });
  });

  it("Volver del modal de congelar no envía nada ni deja aviso", async () => {
    const { user, mock } = renderMemberships();
    const row = await findMembershipRow("Elena Vargas");

    await user.click(within(row).getByRole("button", { name: "Congelar la membresía de Elena Vargas" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Volver" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mock.callsTo(freezeKey())).toHaveLength(0);
    expect(pageNotice().textContent).toBe("");
  });

  it("el aviso se puede cerrar", async () => {
    const { user } = renderMemberships();
    const row = await findMembershipRow("Elena Vargas");
    await user.click(within(row).getByRole("button", { name: "Congelar la membresía de Elena Vargas" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/^Hasta/), { target: { value: "2026-11-06" } });
    await user.click(within(dialog).getByRole("button", { name: "Congelar" }));
    await waitFor(() => {
      expect(pageNotice()).toHaveTextContent(/congelada/);
    });

    await user.click(screen.getByRole("button", { name: "Cerrar aviso" }));

    expect(pageNotice().textContent).toBe("");
  });
});

describe("MembershipsPage · estados", () => {
  it("mientras carga muestra el esqueleto de la tabla", async () => {
    renderMemberships("/membresias", { handlers: { "GET /memberships": () => new Promise(() => undefined) } });

    expect((await screen.findAllByTestId("skeleton-row")).length).toBeGreaterThan(0);
  });

  it("sin membresías ni filtros invita a vender la primera", async () => {
    renderMemberships("/membresias", { rows: [] });

    expect(await screen.findByText("Todavía no hay membresías vigentes. Las anuladas se ven con el chip Anuladas.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Vender la primera membresía" })).toHaveAttribute("href", "/membresias/vender");
  });

  it("con filtros y sin resultados: 'No hay membresías con estos filtros' y Limpiar filtros", async () => {
    const { user, router } = renderMemberships("/membresias?status=frozen", { rows: [] });

    expect(await screen.findByText("No hay membresías con estos filtros")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Limpiar filtros" }));

    expect(router.state.location.search).toBe("");
  });

  it("una página pasada del final ofrece volver a la primera", async () => {
    const { user, router } = renderMemberships("/membresias?offset=75", { handlers: { "GET /memberships": (call) => membershipsPage(call, [], 3) } });

    expect(await screen.findByText("Esta página ya no tiene membresías.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ir a la primera página" }));

    expect(router.state.location.search).toBe("");
  });

  it("un error se explica y Reintentar pide la lista de nuevo", async () => {
    let fail = true;
    const { user, mock } = renderMemberships("/membresias", {
      handlers: { "GET /memberships": (call) => (fail ? apiError(500, "internal_error") : membershipsPage(call)) },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos cargar las membresías. Intenta de nuevo.");
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await findMembershipRow("Laura Gómez")).toBeInTheDocument();
    expect(membershipListCalls(mock)).toHaveLength(2);
  });

  it.each([
    [403, "forbidden", {}, "No tienes permiso para ver las membresías. Si lo necesitas, pídeselo a un administrador."],
    [422, "validation_error", {}, "Revisa los filtros: alguna fecha o estado no es válido. Límpialos e intenta de nuevo."],
    [429, "rate_limited", { "Retry-After": "30" }, "Hiciste muchas búsquedas seguidas. Espera 30 segundos e intenta de nuevo."],
  ])("%i %s se explica en palabras de la pantalla", async (status, code, headers, message) => {
    renderMemberships("/membresias", { handlers: { "GET /memberships": apiError(status, code, {}, headers) } });

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
  });

  it("sin `memberships.sell` no hay 'Vender membresía' ni Renovar", async () => {
    signInAs("member");
    renderMemberships();

    await findMembershipRow("Laura Gómez");
    expect(screen.queryByRole("link", { name: "Vender membresía" })).toBeNull();
    expect(screen.queryByRole("link", { name: /^Renovar/ })).toBeNull();
    expect(screen.queryByRole("link", { name: /^Registrar saldo/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Congelar/ })).toBeNull();
  });
});

describe("MembershipsPage · revisión S3-F5", () => {
  it("L7: tras anular, el foco va al aviso (la fila anulada sale de la vista y su botón con ella)", async () => {
    signInAs("admin");
    const { user } = renderMemberships();
    const row = await findMembershipRow("Elena Vargas");

    await user.click(within(row).getByRole("button", { name: "Anular la membresía de Elena Vargas" }));
    const dialog = screen.getByRole("dialog", { name: "¿Anular la membresía de Elena Vargas?" });
    await user.type(within(dialog).getByRole("textbox", { name: /^Motivo/ }), "Vendida por error");
    await user.click(within(dialog).getByRole("button", { name: "Sí, anular" }));

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).toBeNull();
    });
    await waitFor(() => {
      expect(pageNotice().firstElementChild).toHaveFocus();
    });
  });

  it("L7: tras congelar, el foco va al aviso", async () => {
    const { user } = renderMemberships();
    const row = await findMembershipRow("Elena Vargas");
    await user.click(within(row).getByRole("button", { name: "Congelar la membresía de Elena Vargas" }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/^Hasta/), { target: { value: "2026-11-06" } });

    await user.click(within(dialog).getByRole("button", { name: "Congelar" }));

    await waitFor(() => {
      expect(pageNotice().firstElementChild).toHaveFocus();
    });
  });
});

describe("MembershipsPage · planes cortados (Fase 4 L8)", () => {
  it("si el filtro de plan no trae todos los planes, lo dice bajo el select", async () => {
    renderMemberships("/membresias", { handlers: { "GET /plans": { status: 200, body: { items: [PLANS.clases, PLANS.mensual], total: 230, limit: 200, offset: 0 } } } });

    await waitFor(() => {
      expect(screen.getByRole("combobox", { name: "Plan" })).toHaveAccessibleDescription("Se muestran 2 de 230 planes. Si falta el que buscas, avísale a un administrador.");
    });
  });
});
