// S3-F2 · US-071 (front): filtro "Plan" de /socios (Socios_Lista.html), montado en la lista.
// - `<select>` dentro de `Field` (FilterBar) con `usePlans({ active: true })` de shared/data: el
//   coach no ve /planes pero sí GET /plans?active=true (S2-D26).
// - `plan_id` vive en la URL; cambiarlo vuelve a la primera página. Un valor que no es UUID no
//   viaja; un plan de la URL que la lista no trae sigue elegido como "Plan elegido".
import { cleanup, screen, waitFor, within } from "@testing-library/react";
import { apiError, listCalls, memberPage, MEMBER_ROWS, planCalls, renderMembers } from "../../../test/members";
import { PLANS } from "../../../test/plans";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";

const planSelect = () => screen.getByRole("combobox", { name: "Plan" });
const OTHER_PLAN = "99999999-9999-4999-8999-999999999999";

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("PlanFilter", () => {
  it("es un select con nombre accesible 'Plan', 'Cualquiera' y los planes activos", async () => {
    renderMembers();

    await waitFor(() => {
      expect(within(planSelect()).getAllByRole("option").map((o) => o.textContent)).toEqual(["Cualquiera", "12 clases", "Mensual"]);
    });
    expect(planSelect()).toHaveValue("");
    expect(planSelect().tagName).toBe("SELECT");
    expect(planSelect().closest("form")).toHaveAttribute("role", "search");
  });

  it.each(["admin", "coach"] as const)("el %s pide solo los planes activos (GET /plans?active=true)", async (role) => {
    signInAs(role);
    const { mock } = renderMembers();
    await screen.findByRole("link", { name: "Laura Gómez" });

    await waitFor(() => {
      expect(planCalls(mock)).toHaveLength(1);
    });
    expect(planCalls(mock)[0]?.toString()).toBe("limit=200&offset=0&active=true");
  });

  it("elegir un plan lo deja en la URL, lo pide y vuelve a la primera página", async () => {
    const { mock, router, user } = renderMembers("/socios?offset=25", { handlers: { "GET /members": (call) => memberPage(call, MEMBER_ROWS, 60) } });
    await screen.findByRole("link", { name: "Laura Gómez" });
    await waitFor(() => {
      expect(within(planSelect()).getAllByRole("option")).toHaveLength(3);
    });

    await user.selectOptions(planSelect(), "Mensual");

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.toString()).toBe(`limit=25&offset=0&plan_id=${PLANS.mensual.id}`);
    });
    expect(router.state.location.search).toBe(`?plan_id=${PLANS.mensual.id}`);
    expect(planSelect()).toHaveValue(PLANS.mensual.id);
  });

  it("el plan se combina con el chip en la misma petición", async () => {
    const { mock, user } = renderMembers(`/socios?membership_status=expired`);
    await screen.findByRole("link", { name: "Laura Gómez" });
    await waitFor(() => {
      expect(within(planSelect()).getAllByRole("option")).toHaveLength(3);
    });

    await user.selectOptions(planSelect(), "12 clases");

    await waitFor(() => {
      expect(listCalls(mock).at(-1)?.toString()).toBe(`limit=25&offset=0&membership_status=expired&plan_id=${PLANS.clases.id}`);
    });
  });

  it("'Cualquiera' quita el plan de la URL y de la petición", async () => {
    const { mock, router, user } = renderMembers(`/socios?plan_id=${PLANS.mensual.id}`);
    await screen.findByRole("link", { name: "Laura Gómez" });
    await waitFor(() => {
      expect(planSelect()).toHaveValue(PLANS.mensual.id);
    });

    await user.selectOptions(planSelect(), "Cualquiera");

    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
    expect(listCalls(mock).at(-1)?.has("plan_id")).toBe(false);
  });

  it("Limpiar quita el plan y el chip", async () => {
    const { router, user } = renderMembers(`/socios?plan_id=${PLANS.mensual.id}&membership_status=active`);
    await screen.findByRole("link", { name: "Laura Gómez" });

    await user.click(screen.getByRole("button", { name: "Limpiar" }));

    await waitFor(() => {
      expect(router.state.location.search).toBe("");
    });
  });

  it("un plan_id que no es un UUID no viaja y el select queda en 'Cualquiera'", async () => {
    const { mock } = renderMembers("/socios?plan_id=1%20OR%201=1");
    await screen.findByRole("link", { name: "Laura Gómez" });

    expect(listCalls(mock)[0]?.toString()).toBe("limit=25&offset=0");
    expect(planSelect()).toHaveValue("");
  });

  it("un plan de la URL que la lista no trae sigue elegido como 'Plan elegido'", async () => {
    const { mock } = renderMembers(`/socios?plan_id=${OTHER_PLAN}`);
    await screen.findByRole("link", { name: "Laura Gómez" });

    await waitFor(() => {
      expect(within(planSelect()).getAllByRole("option").map((o) => o.textContent)).toEqual(["Cualquiera", "12 clases", "Mensual", "Plan elegido"]);
    });
    expect(planSelect()).toHaveValue(OTHER_PLAN);
    expect(listCalls(mock)[0]?.get("plan_id")).toBe(OTHER_PLAN);
  });

  it("si GET /plans falla el filtro queda en 'Cualquiera' y la lista sigue", async () => {
    renderMembers("/socios", { handlers: { "GET /plans": apiError(500, "internal") } });

    expect(await screen.findByRole("link", { name: "Laura Gómez" })).toBeInTheDocument();
    expect(within(planSelect()).getAllByRole("option").map((o) => o.textContent)).toEqual(["Cualquiera"]);
  });
});
