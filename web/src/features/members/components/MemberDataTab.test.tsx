// S4A-F2 · US-106 (front; E8 del plan: este archivo nace en el Rojo de F2): la caja "Historial
// reciente" de la pestaña Datos (Socio_Ficha.html) con las 5 últimas entradas de
// GET /members/{id}/audit y el enlace "Ver historial completo →" a /socios/:id/historial. Cierra el
// criterio diferido de US-066 (HistoryAside conectado al api).
import { screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { DETAIL_PATH, MEMBER_ID, apiError, renderMemberDetail } from "../../../test/memberDetail";
import { DOCUMENT_VALUE, historyCalls, historyItems, historyReply, HISTORY_PATH, PHONE_VALUE } from "../../../test/history";
import { setViewportWidth } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { MEMBER_HISTORY_PREVIEW_SIZE } from "../api";
import { HISTORY_MESSAGES } from "../memberErrors";

const recent = (): Promise<HTMLElement> => screen.findByRole("complementary", { name: "Historial" });

beforeEach(() => {
  setViewportWidth(1440);
  signInAs("admin");
});

afterEach(() => {
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("MemberDataTab · Historial reciente", () => {
  it("pide las 5 últimas (limit 5, offset 0) y las pinta con su frase, sin Cargar más", async () => {
    const { mock } = renderMemberDetail(undefined, { handlers: { [`GET ${HISTORY_PATH}`]: historyReply(historyItems()) } });
    const box = await recent();

    expect(within(box).getByRole("heading", { level: 2, name: "Historial reciente" })).toBeInTheDocument();
    await within(box).findByText("juan mostró el documento");
    const items = within(box).getAllByRole("listitem");
    expect(items).toHaveLength(MEMBER_HISTORY_PREVIEW_SIZE);
    expect(items.map((li) => li.querySelector("b")?.textContent)).toEqual([
      "juan mostró el documento",
      "ana anuló un pago",
      "juan registró un pago",
      "Sistema marcó la membresía como vencida o por vencer",
      "ana vendió una membresía",
    ]);
    const [params] = historyCalls(mock);
    expect(params?.get("limit")).toBe("5");
    expect(params?.get("offset")).toBe("0");
    expect(within(box).queryByRole("button", { name: /Cargar más|Ver más/ })).not.toBeInTheDocument();
  });

  it("el enlace 'Ver historial completo →' lleva a la pestaña Historial", async () => {
    const { user } = renderMemberDetail(undefined, { handlers: { [`GET ${HISTORY_PATH}`]: historyReply(historyItems()) } });
    const box = await recent();
    const link = within(box).getByRole("link", { name: "Ver historial completo →" });

    expect(link).toHaveAttribute("href", `/socios/${MEMBER_ID}/historial`);
    await user.click(link);

    expect(screen.getByTestId("location").textContent).toBe(`/socios/${MEMBER_ID}/historial`);
    expect(screen.getByRole("tab", { name: "Historial" })).toHaveAttribute("aria-selected", "true");
  });

  it("la caja convive con los datos de contacto y no muestra ningún valor del historial", async () => {
    const { container } = renderMemberDetail(undefined, { handlers: { [`GET ${HISTORY_PATH}`]: historyReply(historyItems()) } });
    const box = await recent();
    await within(box).findByText("juan mostró el documento");

    expect(screen.getByRole("heading", { level: 2, name: "Datos de contacto" })).toBeInTheDocument();
    for (const value of [PHONE_VALUE, DOCUMENT_VALUE, "apx1."]) expect(box.textContent).not.toContain(value);
    expect(container.textContent).not.toContain(PHONE_VALUE);
  });

  it("sin entradas dice 'Sin cambios registrados' y conserva el enlace", async () => {
    renderMemberDetail();
    const box = await recent();

    expect(await within(box).findByText("Sin cambios registrados")).toBeInTheDocument();
    expect(within(box).getByRole("link", { name: "Ver historial completo →" })).toBeInTheDocument();
  });

  it("un 429 avisa en la caja con Reintentar y la ficha sigue en pantalla", async () => {
    let fail = true;
    const { mock, user } = renderMemberDetail(undefined, {
      handlers: { [`GET ${HISTORY_PATH}`]: (c) => (fail ? apiError(429, "rate_limited") : historyReply(historyItems())(c)) },
    });
    const box = await recent();

    expect(await within(box).findByRole("alert")).toHaveTextContent(HISTORY_MESSAGES.tooMany);
    expect(screen.getByRole("heading", { level: 2, name: "Datos de contacto" })).toBeInTheDocument();
    fail = false;
    await user.click(within(box).getByRole("button", { name: "Reintentar" }));

    expect(await within(box).findByText("juan mostró el documento")).toBeInTheDocument();
    await waitFor(() => {
      expect(mock.callsTo(`GET ${HISTORY_PATH}`)).toHaveLength(2);
    });
    expect(mock.callsTo(`GET ${DETAIL_PATH}`)).toHaveLength(1);
  });

  it("el coach también ve la caja", async () => {
    signInAs("coach");
    renderMemberDetail(undefined, { handlers: { [`GET ${HISTORY_PATH}`]: historyReply(historyItems()) } });

    expect(await within(await recent()).findByText("juan mostró el documento")).toBeInTheDocument();
  });

  it("sin violaciones de axe", async () => {
    const { container } = renderMemberDetail(undefined, { handlers: { [`GET ${HISTORY_PATH}`]: historyReply(historyItems()) } });
    await within(await recent()).findByText("juan mostró el documento");

    expect(await axe(container)).toHaveNoViolations();
  });
});
