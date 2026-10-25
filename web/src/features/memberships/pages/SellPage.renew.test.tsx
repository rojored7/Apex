// S3-F3 · US-088 (front): renovar en /membresias/vender?socio=:id&renovar=1. Mismo endpoint de la
// venta con `renew: true` y sin `start_date` (regla 9 de CLAUDE.md, Q1); la fecha la calcula el
// servidor y se muestra con GET /members/{id}/memberships/renewal-preview?plan_id=, que se pide de
// nuevo al cambiar de plan. 409 `future_membership_exists` (en la vista previa o al vender) enlaza
// a la ficha del socio.
import { cleanup, screen, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { MEMBERS } from "../../../test/members";
import {
  apiError,
  pickPlan,
  previewKey,
  renderSell,
  renewalPreview,
  SELL_NOW,
  sellBodies,
  sellKey,
  sellMembershipOut,
  summaryValue,
} from "../../../test/memberships";
import { PLANS } from "../../../test/plans";
import type { RecordedCall } from "../../../test/server";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";

const RENEW = `/membresias/vender?socio=${MEMBERS.laura.id}&renovar=1`;
const STATE = { memberName: "Laura Gómez" };

const planOf = (call: RecordedCall): string | null => new URL(call.url, "http://apex.test").searchParams.get("plan_id");

/** La vista previa según el plan pedido: Mensual 30 días, 12 clases 60 días. */
const byPlan = (call: RecordedCall) =>
  planOf(call) === PLANS.clases.id
    ? { status: 200, body: renewalPreview({ end_date: "2026-12-28", agreed_price_cop: 110_000 }) }
    : { status: 200, body: renewalPreview() };

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

describe("SellPage en modo renovar", () => {
  it("entra con el socio fijo, sin buscador, y no pide la vista previa hasta elegir plan", async () => {
    const { mock } = renderSell(RENEW, { state: STATE });

    expect(screen.getByRole("heading", { level: 1, name: "Renovar membresía" })).toBeInTheDocument();
    expect(within(screen.getByRole("navigation", { name: "Migas" })).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Membresías", "Renovar"]);
    expect(screen.queryByRole("searchbox", { name: "Buscar socio" })).not.toBeInTheDocument();
    expect(summaryValue("Socio")).toBe("Laura Gómez");
    await screen.findByRole("radio", { name: /^Mensual/ });
    expect(mock.callsTo(previewKey())).toHaveLength(0);
  });

  it("la fecha calculada se ve y no se puede editar: empieza al día siguiente de que termine la actual", async () => {
    const { user, mock } = renderSell(RENEW, { state: STATE, handlers: { [previewKey()]: byPlan } });
    await pickPlan(user, "Mensual");

    expect(await screen.findByText("Empieza el 29 oct 2026, al día siguiente de que termine la actual.")).toBeInTheDocument();
    const start = screen.getByRole("textbox", { name: "Inicio" });
    expect(start).toHaveValue("29 oct 2026");
    expect(start).toHaveAttribute("readonly");
    expect(screen.getByRole("textbox", { name: "Fin (calculado)" })).toHaveValue("28 nov 2026");
    expect(summaryValue("Vigencia")).toBe("29 oct 2026 – 28 nov 2026");
    expect(summaryValue("Precio")).toBe("$ 120.000");
    expect(planOf(mock.callsTo(previewKey())[0] as RecordedCall)).toBe(PLANS.mensual.id);
  });

  it("cambiar de plan vuelve a pedir la vista previa y actualiza fechas, precio y valor", async () => {
    const { user, mock } = renderSell(RENEW, { state: STATE, handlers: { [previewKey()]: byPlan } });
    await pickPlan(user, "Mensual");
    await screen.findByText("Empieza el 29 oct 2026, al día siguiente de que termine la actual.");
    await pickPlan(user, "12 clases");

    expect(await screen.findByDisplayValue("28 dic 2026")).toBeInTheDocument();
    expect(summaryValue("Precio")).toBe("$ 110.000");
    expect(screen.getByRole("textbox", { name: /^Valor recibido/ })).toHaveValue("$ 110.000");
    expect(mock.callsTo(previewKey()).map(planOf)).toEqual([PLANS.mensual.id, PLANS.clases.id]);
  });

  it("sin membresía actual dice solo cuándo empieza", async () => {
    const { user } = renderSell(RENEW, { state: STATE, handlers: { [previewKey()]: { status: 200, body: renewalPreview({ current_end_date: null }) } } });
    await pickPlan(user, "Mensual");

    expect(await screen.findByText("Empieza el 29 oct 2026.")).toBeInTheDocument();
  });

  it("vende con renew: true y sin start_date", async () => {
    const { user, mock } = renderSell(RENEW, { state: STATE });
    await pickPlan(user, "Mensual");
    await screen.findByText(/^Empieza el 29 oct 2026/);
    await user.click(screen.getByRole("button", { name: "Vender y cobrar" }));

    await screen.findByRole("region", { name: "Venta registrada" });
    const [body] = sellBodies(mock);
    expect(body).toMatchObject({ plan_id: PLANS.mensual.id, renew: true });
    expect(body).not.toHaveProperty("start_date");
  });

  it("409 future_membership_exists en la vista previa avisa con enlace a la ficha y no deja vender", async () => {
    const { user, mock } = renderSell(RENEW, {
      state: STATE,
      handlers: { [previewKey()]: apiError(409, "future_membership_exists", { existing_id: "88888888-8888-4888-8888-888888888888" }) },
    });
    await pickPlan(user, "Mensual");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Laura Gómez ya tiene una renovación por empezar. Revísala en su ficha.");
    expect(within(alert).getByRole("link", { name: "Ver ficha del socio" })).toHaveAttribute("href", `/socios/${MEMBERS.laura.id}`);
    expect(screen.getByRole("button", { name: "Vender y cobrar" })).toBeDisabled();
    expect(mock.callsTo(sellKey())).toHaveLength(0);
  });

  it("409 future_membership_exists al vender también enlaza a la ficha", async () => {
    const { user } = renderSell(RENEW, { state: STATE, handlers: { [sellKey()]: apiError(409, "future_membership_exists") } });
    await pickPlan(user, "Mensual");
    await screen.findByText(/^Empieza el 29 oct 2026/);
    await user.click(screen.getByRole("button", { name: "Vender y cobrar" }));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("link", { name: "Ver ficha del socio" })).toHaveAttribute("href", `/socios/${MEMBERS.laura.id}`);
  });

  it("si la vista previa falla lo dice con Reintentar", async () => {
    let fail = true;
    const { user } = renderSell(RENEW, { state: STATE, handlers: { [previewKey()]: () => (fail ? apiError(500, "internal_error") : { status: 200, body: renewalPreview() }) } });
    await pickPlan(user, "Mensual");

    expect(await screen.findByText("No pudimos calcular las fechas de la renovación. Intenta de nuevo.")).toBeInTheDocument();
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByText(/^Empieza el 29 oct 2026/)).toBeInTheDocument();
  });

  it("sin el nombre en la navegación muestra 'Socio elegido' y, tras vender, el nombre del api", async () => {
    const { user } = renderSell(RENEW, { handlers: { [sellKey()]: { status: 201, body: sellMembershipOut({ member_name: "Laura Gómez" }) } } });

    expect(summaryValue("Socio")).toBe("Socio elegido");
    await pickPlan(user, "Mensual");
    await screen.findByText(/^Empieza el 29 oct 2026/);
    await user.click(screen.getByRole("button", { name: "Vender y cobrar" }));

    const region = await screen.findByRole("region", { name: "Venta registrada" });
    expect(within(region).getByText("La membresía de Laura Gómez quedó registrada.")).toBeInTheDocument();
  });

  it("un socio que no es un id válido se ignora: vuelve a la venta normal con buscador", () => {
    renderSell("/membresias/vender?socio=no-es-un-id&renovar=1");

    expect(screen.getByRole("heading", { level: 1, name: "Vender membresía" })).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "Buscar socio" })).toBeInTheDocument();
  });

  it("?socio= sin renovar fija el socio y vende normal, con inicio editable", () => {
    renderSell(`/membresias/vender?socio=${MEMBERS.laura.id}`, { state: STATE });

    expect(screen.getByRole("heading", { level: 1, name: "Vender membresía" })).toBeInTheDocument();
    expect(summaryValue("Socio")).toBe("Laura Gómez");
    expect(screen.getByLabelText(/^Inicio/)).not.toHaveAttribute("readonly");
    expect(screen.getByRole("link", { name: "Cambiar socio" })).toHaveAttribute("href", "/membresias/vender");
  });

  it("no tiene violaciones de axe con la vista previa", async () => {
    const { user, container } = renderSell(RENEW, { state: STATE });
    await pickPlan(user, "Mensual");
    await screen.findByText(/^Empieza el 29 oct 2026/);

    expect(await axe(container)).toHaveNoViolations();
  });
});
