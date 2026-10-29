// S4A-F4 · US-082 (front; S4A-D24, S4A-D34): dar de baja un plan desde la fila de /planes.
// - "Dar de baja" pide confirmación con ConfirmModal; el 204 quita la fila al releer la lista y deja
//   el aviso "Plan dado de baja".
// - El 409 `plan_has_active_memberships` cierra la confirmación y muestra el mensaje del api (solo el
//   conteo, S4A-D60) con el botón "Desactivar", que llama a useSetPlanActive.
// - El coach no ve la acción. La caché de mutaciones no conserva `variables` (useSensitiveMutation).
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { apiError, MANAGED_ROWS, planStore, PLANS, renderPlans } from "../../../test/plans";

const IN_USE = "Este plan tiene 4 membresías activas, desactívalo en su lugar.";
const CONSEQUENCE = "El plan sale de la lista y ya no se puede vender. Solo se puede si no tiene membresías activas.";

const inUseStore = () =>
  planStore(MANAGED_ROWS, {
    deleteReply: (id) => (id === PLANS.mensual.id ? apiError(409, "plan_has_active_memberships", { message: IN_USE }) : null),
  });

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  cleanup();
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("PlansPage · Dar de baja (US-082)", () => {
  it("pide confirmación con el nombre del plan; el 204 quita la fila y avisa", async () => {
    const store = planStore();
    const { mock, user } = renderPlans("/planes", { handlers: store.handlers });
    await screen.findByText("2 activos · 1 inactivo");

    await user.click(screen.getByRole("button", { name: "Dar de baja: Promo apertura" }));
    const modal = screen.getByRole("dialog", { name: "¿Dar de baja el plan Promo apertura?" });
    expect(modal).toHaveAccessibleDescription(CONSEQUENCE);
    expect(await axe(document.body)).toHaveNoViolations();
    await user.click(within(modal).getByRole("button", { name: "Dar de baja" }));

    expect(await screen.findByText("Plan dado de baja: Promo apertura.")).toBeInTheDocument();
    expect(mock.callsTo(`DELETE /plans/${PLANS.promo.id}`)).toHaveLength(1);
    await waitFor(() => {
      expect(screen.queryByRole("link", { name: "Promo apertura" })).not.toBeInTheDocument();
    });
    expect(screen.getByRole("link", { name: "Mensual" })).toBeInTheDocument();
    expect(await screen.findByText("2 activos · 0 inactivos")).toBeInTheDocument();
  });

  it("'Volver' cierra la confirmación sin dar de baja", async () => {
    const store = planStore();
    const { mock, user } = renderPlans("/planes", { handlers: store.handlers });
    await screen.findByRole("link", { name: "Promo apertura" });

    await user.click(screen.getByRole("button", { name: "Dar de baja: Promo apertura" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Volver" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mock.callsTo(`DELETE /plans/${PLANS.promo.id}`)).toHaveLength(0);
  });

  it("el 409 plan_has_active_memberships muestra el mensaje del api y el botón Desactivar", async () => {
    const store = inUseStore();
    const { user } = renderPlans("/planes", { handlers: store.handlers });
    await screen.findByRole("link", { name: "Mensual" });

    await user.click(screen.getByRole("button", { name: "Dar de baja: Mensual" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Dar de baja" }));

    const blocked = await screen.findByRole("alert");
    expect(blocked).toHaveTextContent(IN_USE);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(within(blocked).getByRole("button", { name: /^Desactivar/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mensual" })).toBeInTheDocument();
    expect(await axe(document.body)).toHaveNoViolations();
  });

  it("'Desactivar' del 409 llama a useSetPlanActive (POST /deactivate), quita el aviso y cambia el estado", async () => {
    const store = inUseStore();
    const { mock, user } = renderPlans("/planes", { handlers: store.handlers });
    await screen.findByRole("link", { name: "Mensual" });

    await user.click(screen.getByRole("button", { name: "Dar de baja: Mensual" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Dar de baja" }));
    const blocked = await screen.findByRole("alert");
    await user.click(within(blocked).getByRole("button", { name: /^Desactivar/ }));

    expect(await screen.findByText("Plan desactivado: Mensual.")).toBeInTheDocument();
    expect(mock.callsTo(`POST /plans/${PLANS.mensual.id}/deactivate`)).toHaveLength(1);
    expect(screen.queryByText(IN_USE)).not.toBeInTheDocument();
    await waitFor(() => {
      expect(within(screen.getByRole("link", { name: "Mensual" }).closest("tr") as HTMLElement).getByText("Inactivo")).toBeInTheDocument();
    });
  });

  it("revisión de seguridad de F4 (LOW-2): dos clics seguidos en Desactivar del aviso hacen una sola petición", async () => {
    const store = inUseStore();
    const { mock, user } = renderPlans("/planes", { handlers: store.handlers });
    await screen.findByRole("link", { name: "Mensual" });

    await user.click(screen.getByRole("button", { name: "Dar de baja: Mensual" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Dar de baja" }));
    const button = within(await screen.findByRole("alert")).getByRole("button", { name: /^Desactivar/ });
    fireEvent.click(button);
    fireEvent.click(button);

    expect(await screen.findByText("Plan desactivado: Mensual.")).toBeInTheDocument();
    expect(mock.callsTo(`POST /plans/${PLANS.mensual.id}/deactivate`)).toHaveLength(1);
  });

  it("un 409 sin mensaje del api usa el texto propio", async () => {
    const { user } = renderPlans("/planes", { handlers: { [`DELETE /plans/${PLANS.mensual.id}`]: apiError(409, "plan_has_active_memberships", { message: "" }) } });
    await screen.findByRole("link", { name: "Mensual" });

    await user.click(screen.getByRole("button", { name: "Dar de baja: Mensual" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Dar de baja" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Este plan tiene membresías activas, desactívalo en su lugar.");
  });

  it("un 404 se explica dentro de la confirmación", async () => {
    const { user } = renderPlans("/planes", { handlers: { [`DELETE /plans/${PLANS.promo.id}`]: apiError(404, "plan_not_found") } });
    await screen.findByRole("link", { name: "Promo apertura" });

    await user.click(screen.getByRole("button", { name: "Dar de baja: Promo apertura" }));
    const modal = screen.getByRole("dialog");
    await user.click(within(modal).getByRole("button", { name: "Dar de baja" }));

    expect(await within(modal).findByRole("alert")).toHaveTextContent("Este plan ya estaba dado de baja. La lista se actualiza sola.");
  });

  it("el coach no ve 'Dar de baja'", async () => {
    signInAs("coach");
    renderPlans("/planes", { rows: MANAGED_ROWS.filter((row) => row.is_active) });
    await screen.findByRole("link", { name: "Mensual" });

    expect(screen.queryByRole("button", { name: /^Dar de baja/ })).not.toBeInTheDocument();
  });
});

describe("PlansPage · caché de mutaciones de la baja (S3-D52, S4A-D35)", () => {
  it("tras el 204 la caché de mutaciones no conserva el id ni el resultado", async () => {
    const store = planStore();
    const { queryClient, user } = renderPlans("/planes", { handlers: store.handlers });
    await screen.findByRole("link", { name: "Promo apertura" });

    await user.click(screen.getByRole("button", { name: "Dar de baja: Promo apertura" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Dar de baja" }));
    await screen.findByText("Plan dado de baja: Promo apertura.");

    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll()).toEqual([]);
    });
  });

  it("tras el 409 tampoco queda la mutación con sus variables", async () => {
    const store = inUseStore();
    const { queryClient, user } = renderPlans("/planes", { handlers: store.handlers });
    await screen.findByRole("link", { name: "Mensual" });

    await user.click(screen.getByRole("button", { name: "Dar de baja: Mensual" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Dar de baja" }));
    await screen.findByRole("alert");

    await waitFor(() => {
      expect(queryClient.getMutationCache().getAll().every((mutation) => mutation.state.variables === undefined)).toBe(true);
    });
  });
});
