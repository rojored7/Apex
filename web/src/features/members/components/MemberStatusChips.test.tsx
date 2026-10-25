// S3-F2 · US-071 (front): chips de estado de /socios (Socios_Lista.html) montados en la lista.
// - Todos, Al día, Por vencer, Vencidos, Congelados, Pendiente de pago (DESIGN-GAP Q3), Sin
//   membresía y Dados de baja (admin y coach, N-20), modo único y `aria-pressed`.
// - Conteos de GET /memberships/summary (D37); "Todos" es el total de socios vivos (GET /members
//   sin filtros) y "Sin membresía" es ese total menos la suma de los cinco estados.
// - El chip vive en la URL (`membership_status` o `status=deleted`, los nombres del api) y
//   cambiarlo vuelve a la primera página en una sola navegación.
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { apiError, isTotalCall, listCalls, memberPage, MEMBER_ROWS, renderMembers, SOCIOS_SUMMARY, totalCalls } from "../../../test/members";
import { setViewportWidth, type RecordedCall } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";

const chips = () => screen.getByRole("group", { name: "Estado" });
const chip = (name: RegExp) => within(chips()).getByRole("button", { name });

/** La lista con 3 filas y el total del box de Socios_Lista.html (342). */
const withTotal = (total: number) => ({ "GET /members": (call: RecordedCall) => (isTotalCall(call) ? memberPage(call, MEMBER_ROWS.slice(0, 1), total) : memberPage(call)) });

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("MemberStatusChips · chips y conteos (D37)", () => {
  it("muestra Todos y los siete chips en el orden del diseño, con los conteos del resumen", async () => {
    renderMembers("/socios", { handlers: withTotal(342) });

    await waitFor(() => {
      expect(chip(/^Todos/)).toHaveTextContent("342");
    });
    expect(within(chips()).getAllByRole("button").map((b) => b.textContent)).toEqual([
      "Todos342",
      "Al día210",
      "Por vencer18",
      "Vencidos41",
      "Congelados4",
      "Pendiente de pago0",
      "Sin membresía69",
      "Dados de baja",
    ]);
  });

  it("pide el resumen una vez y el total sin filtros con limit=1", async () => {
    const { mock } = renderMembers("/socios", { handlers: withTotal(342) });
    await waitFor(() => {
      expect(chip(/^Sin membresía/)).toHaveTextContent("69");
    });

    expect(mock.callsTo("GET /memberships/summary")).toHaveLength(1);
    expect(totalCalls(mock)).toHaveLength(1);
  });

  it("'Sin membresía' nunca es negativo aunque el resumen sume más que el total", async () => {
    renderMembers("/socios", { handlers: withTotal(100) });

    await waitFor(() => {
      expect(chip(/^Todos/)).toHaveTextContent("100");
    });
    expect(chip(/^Sin membresía/).textContent).toBe("Sin membresía0");
  });

  it("si el resumen falla los chips siguen sirviendo, sin conteos de estado", async () => {
    const { mock, user } = renderMembers("/socios", { handlers: { ...withTotal(342), "GET /memberships/summary": apiError(500, "internal") } });
    await waitFor(() => {
      expect(chip(/^Todos/)).toHaveTextContent("342");
    });

    expect(chip(/^Al día/).textContent).toBe("Al día");
    expect(chip(/^Sin membresía/).textContent).toBe("Sin membresía");
    await user.click(chip(/^Vencidos/));

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.get("membership_status")).toBe("expired");
    });
  });

  it("'Por vencer' y 'Pendiente de pago' llevan el tono de advertencia y 'Vencidos' el de peligro", async () => {
    renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(chip(/^Por vencer/)).toHaveClass("warning");
    expect(chip(/^Pendiente de pago/)).toHaveClass("warning");
    expect(chip(/^Vencidos/)).toHaveClass("danger");
  });
});

describe("MemberStatusChips · el chip en la URL y en la petición", () => {
  it("sin chip, 'Todos' está activo y la petición no lleva estado", async () => {
    const { mock } = renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(chip(/^Todos/)).toHaveAttribute("aria-pressed", "true");
    expect(chip(/^Al día/)).toHaveAttribute("aria-pressed", "false");
    expect(listCalls(mock)[0]?.toString()).toBe("limit=25&offset=0");
  });

  it.each([
    [/^Al día/, "active"],
    [/^Por vencer/, "expiring"],
    [/^Vencidos/, "expired"],
    [/^Congelados/, "frozen"],
    [/^Pendiente de pago/, "pending_payment"],
    [/^Sin membresía/, "none"],
  ])("el chip %s pide membership_status=%s y lo deja en la URL", async (name, value) => {
    const { mock, router, user } = renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    await user.click(chip(name));

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.toString()).toBe(`limit=25&offset=0&membership_status=${value}`);
    });
    expect(router.state.location.search).toBe(`?membership_status=${value}`);
    expect(chip(name)).toHaveAttribute("aria-pressed", "true");
    expect(chip(/^Todos/)).toHaveAttribute("aria-pressed", "false");
  });

  it("cambiar de chip desde la página 3 vuelve a offset=0", async () => {
    const { mock, router, user } = renderMembers("/socios?offset=50&sort=first_name", { handlers: { "GET /members": (call) => memberPage(call, MEMBER_ROWS, 90) } });
    await screen.findByRole("link", { name: "Laura Gómez" });

    await user.click(chip(/^Congelados/));

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.toString()).toBe("limit=25&offset=0&membership_status=frozen&sort=first_name");
    });
    expect(router.state.location.search).toBe("?sort=first_name&membership_status=frozen");
  });

  it("de 'Dados de baja' a 'Al día' quita status=deleted en la misma navegación", async () => {
    const { mock, router, user } = renderMembers("/socios?status=deleted");
    await screen.findByRole("link", { name: "Laura Gómez" });

    await user.click(chip(/^Al día/));

    await waitFor(() => {
      expect(router.state.location.search).toBe("?membership_status=active");
    });
    expect(listCalls(mock).at(-1)?.toString()).toBe("limit=25&offset=0&membership_status=active");
    expect(listCalls(mock).some((p) => p.get("status") === "deleted" && p.has("membership_status"))).toBe(false);
  });

  it("de 'Vencidos' a 'Dados de baja' pide status=deleted sin membership_status", async () => {
    const { mock, router, user } = renderMembers("/socios?membership_status=expired");
    await screen.findByRole("link", { name: "Laura Gómez" });

    await user.click(chip(/^Dados de baja/));

    await waitFor(() => {
      expect(router.state.location.search).toBe("?status=deleted");
    });
    expect(listCalls(mock).at(-1)?.toString()).toBe("limit=25&offset=0&status=deleted");
  });

  it("'Todos' quita el chip; pulsar el chip activo también", async () => {
    const { router, user } = renderMembers("/socios?membership_status=frozen");
    await screen.findByRole("link", { name: "Laura Gómez" });

    await user.click(chip(/^Todos/));
    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });

    await user.click(chip(/^Congelados/));
    await waitFor(() => {
      expect(router.state.location.search).toBe("?membership_status=frozen");
    });
    await user.click(chip(/^Congelados/));
    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
  });

  it("recargar con un chip en la URL lo marca y lo pide", async () => {
    const { mock } = renderMembers("/socios?membership_status=pending_payment");
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(chip(/^Pendiente de pago/)).toHaveAttribute("aria-pressed", "true");
    expect(listCalls(mock)[0]?.get("membership_status")).toBe("pending_payment");
  });

  it("un membership_status desconocido en la URL no viaja y deja 'Todos'", async () => {
    const { mock } = renderMembers("/socios?membership_status=cancelled");
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(listCalls(mock)[0]?.toString()).toBe("limit=25&offset=0");
    expect(chip(/^Todos/)).toHaveAttribute("aria-pressed", "true");
  });

  it("con status=deleted y membership_status a la vez manda la baja y la membresía no viaja", async () => {
    const { mock } = renderMembers("/socios?status=deleted&membership_status=active");
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(listCalls(mock)[0]?.toString()).toBe("limit=25&offset=0&status=deleted");
    expect(chip(/^Dados de baja/)).toHaveAttribute("aria-pressed", "true");
  });
});

describe("MemberStatusChips · 'Dados de baja' por rol (N-20)", () => {
  it.each(["admin", "coach"] as const)("el %s ve 'Dados de baja'", async (role) => {
    signInAs(role);
    renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(chip(/^Dados de baja/)).toBeInTheDocument();
  });

  it("sin members.view no aparece 'Dados de baja' ni viaja status=deleted", async () => {
    signInAs("member");
    const { mock } = renderMembers("/socios?status=deleted");
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(within(chips()).queryByRole("button", { name: /Dados de baja/ })).not.toBeInTheDocument();
    expect(listCalls(mock)[0]?.has("status")).toBe(false);
  });
});

describe("MemberStatusChips · después de un alta", () => {
  it("invalidar ['members'] relee el total del chip 'Todos'", async () => {
    let total = 342;
    const { mock, queryClient } = renderMembers("/socios", {
      handlers: { "GET /members": (call) => (isTotalCall(call) ? memberPage(call, MEMBER_ROWS.slice(0, 1), total) : memberPage(call)) },
    });
    await waitFor(() => {
      expect(chip(/^Todos/)).toHaveTextContent("342");
    });

    total = 343;
    await queryClient.invalidateQueries({ queryKey: ["members"] });

    await waitFor(() => {
      expect(chip(/^Todos/)).toHaveTextContent("343");
    });
    expect(totalCalls(mock)).toHaveLength(2);
    expect(chip(/^Al día/)).toHaveTextContent(String(SOCIOS_SUMMARY.active));
  });
});
