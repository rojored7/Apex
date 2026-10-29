// S4A-F2 · US-106 (front): pestaña Historial de la ficha (/socios/:id/historial) sobre HistoryAside.
// - GET /members/{id}/audit con limit 25 y offset; orden del api (seq descendente); "Cargar más"
//   acumula páginas hasta el tope de 20 (MEMBER_HISTORY_MAX_PAGES) y entonces lo avisa.
// - Frases por acción y tabla con quien actuó; "automático (aviso)" en un reveal con propósito.
// - Vacío, error con "Reintentar", 429 de staff-read, fallo al cargar más; el coach la ve.
// - Ningún valor: ni teléfono, ni documento, ni blob, ni correo.
import { screen, waitFor, within } from "@testing-library/react";
import { axe } from "vitest-axe";
import { apiError, ok } from "../../../test/memberDetail";
import {
  DOCUMENT_VALUE,
  historyCalls,
  historyItems,
  historyReply,
  HISTORY_PATH,
  manyHistoryItems,
  PHONE_VALUE,
  renderMemberHistoryTab,
} from "../../../test/history";
import { signInAs, signOutForTests } from "../../../test/session";
import { MEMBER_HISTORY_MAX_PAGES, MEMBER_HISTORY_PAGE_SIZE } from "../api";
import { HISTORY_MESSAGES } from "../memberErrors";
import { HISTORY_CAP_NOTICE } from "./MemberHistoryTab";

const aside = (): Promise<HTMLElement> => screen.findByRole("complementary", { name: "Historial" });
const entries = (): HTMLElement[] => within(screen.getByRole("list")).getAllByRole("listitem");

beforeEach(() => {
  signInAs("admin");
});

afterEach(() => {
  signOutForTests();
  vi.unstubAllGlobals();
});

describe("MemberHistoryTab · lista", () => {
  it("pide la primera página de 25 y pinta las frases en el orden del api (más reciente primero)", async () => {
    const { mock } = renderMemberHistoryTab();
    const region = await aside();
    await within(region).findByText("juan mostró el documento");

    expect(within(region).getByRole("heading", { level: 2, name: "Historial" })).toBeInTheDocument();
    expect(entries().map((li) => li.querySelector("b")?.textContent)).toEqual([
      "juan mostró el documento",
      "ana anuló un pago",
      "juan registró un pago",
      "Sistema marcó la membresía como vencida o por vencer",
      "ana vendió una membresía",
      "ana editó correo y teléfono",
      "Sistema mostró el teléfono",
      "ana creó el socio",
    ]);
    const [params] = historyCalls(mock);
    expect(params?.get("limit")).toBe(String(MEMBER_HISTORY_PAGE_SIZE));
    expect(params?.get("offset")).toBe("0");
    expect(mock.callsTo(`GET ${HISTORY_PATH}`)).toHaveLength(1);
  });

  it("cada entrada lleva su entidad y la fecha de Bogotá; el reveal automático lleva 'automático (aviso)'", async () => {
    renderMemberHistoryTab();
    await screen.findByText("juan mostró el documento");
    const items = entries();

    expect(items[0]).toHaveTextContent("Socio · 20 oct 2026, 9:30 p. m.");
    expect(items[1]).toHaveTextContent("Pago ·");
    expect(items[3]).toHaveTextContent("Membresía ·");
    expect(within(items[6] as HTMLElement).getByText("automático (aviso)")).toBeInTheDocument();
    expect(items.filter((li) => li.textContent.includes("automático (aviso)"))).toHaveLength(1);
  });

  it("ningún valor se muestra: ni teléfono, ni documento, ni blob, ni correo", async () => {
    const { container } = renderMemberHistoryTab();
    await screen.findByText("juan mostró el documento");

    for (const value of [PHONE_VALUE, DOCUMENT_VALUE, "apx1.", "@"]) expect(container.textContent).not.toContain(value);
  });

  it("vacío dice 'Sin cambios registrados' sin botón de cargar más", async () => {
    renderMemberHistoryTab({ handlers: { [`GET ${HISTORY_PATH}`]: historyReply([]) } });

    expect(await screen.findByText("Sin cambios registrados")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cargar más" })).not.toBeInTheDocument();
  });

  it("mientras carga lo anuncia", () => {
    renderMemberHistoryTab({ handlers: { [`GET ${HISTORY_PATH}`]: () => new Promise(() => undefined) } });

    expect(screen.getByText("Cargando historial")).toBeInTheDocument();
  });

  it("el coach también la ve", async () => {
    signInAs("coach");
    renderMemberHistoryTab();

    expect(await screen.findByText("juan mostró el documento")).toBeInTheDocument();
  });

  it("sin violaciones de axe", async () => {
    const { container } = renderMemberHistoryTab();
    await screen.findByText("juan mostró el documento");

    expect(await axe(container)).toHaveNoViolations();
  });
});

describe("MemberHistoryTab · Cargar más", () => {
  it("acumula la página siguiente con offset 25 y desaparece al llegar al total", async () => {
    const items = manyHistoryItems(30);
    const { mock, user } = renderMemberHistoryTab({ handlers: { [`GET ${HISTORY_PATH}`]: historyReply(items) } });
    await waitFor(() => {
      expect(screen.getAllByRole("listitem")).toHaveLength(25);
    });

    await user.click(screen.getByRole("button", { name: "Cargar más" }));

    await waitFor(() => {
      expect(screen.getAllByRole("listitem")).toHaveLength(30);
    });
    expect(historyCalls(mock).map((p) => p.get("offset"))).toEqual(["0", "25"]);
    expect(screen.queryByRole("button", { name: "Cargar más" })).not.toBeInTheDocument();
  });

  it("no repite una entrada que se corrió de página (mismo seq)", async () => {
    const items = manyHistoryItems(30);
    const shifted = [items[0], ...items.slice(0, 29)];
    let call = 0;
    const { user } = renderMemberHistoryTab({
      handlers: {
        [`GET ${HISTORY_PATH}`]: (c) => {
          call += 1;
          return historyReply(call === 1 ? items : (shifted as typeof items), 30)(c);
        },
      },
    });
    await waitFor(() => {
      expect(screen.getAllByRole("listitem")).toHaveLength(25);
    });

    await user.click(screen.getByRole("button", { name: "Cargar más" }));

    await waitFor(() => {
      expect(screen.getAllByRole("listitem")).toHaveLength(29);
    });
  });

  it(`deja de ofrecer "Cargar más" en la página ${String(MEMBER_HISTORY_MAX_PAGES)} y lo avisa`, async () => {
    const items = manyHistoryItems(MEMBER_HISTORY_PAGE_SIZE * (MEMBER_HISTORY_MAX_PAGES + 2));
    const { mock, user } = renderMemberHistoryTab({ handlers: { [`GET ${HISTORY_PATH}`]: historyReply(items) } });
    for (let page = 1; page < MEMBER_HISTORY_MAX_PAGES; page += 1) {
      const button = await screen.findByRole("button", { name: "Cargar más" });
      await user.click(button);
      await waitFor(() => {
        expect(screen.getAllByRole("listitem")).toHaveLength(MEMBER_HISTORY_PAGE_SIZE * (page + 1));
      });
    }

    expect(screen.queryByRole("button", { name: "Cargar más" })).not.toBeInTheDocument();
    expect(screen.getByText(HISTORY_CAP_NOTICE)).toBeInTheDocument();
    expect(historyCalls(mock)).toHaveLength(MEMBER_HISTORY_MAX_PAGES);
  }, 30_000);

  it("si falla cargar más, conserva las entradas, lo avisa y el botón reintenta", async () => {
    const items = manyHistoryItems(30);
    let fail = false;
    const { user } = renderMemberHistoryTab({
      handlers: {
        [`GET ${HISTORY_PATH}`]: (c) => (fail ? apiError(500, "internal_error") : historyReply(items)(c)),
      },
    });
    await waitFor(() => {
      expect(screen.getAllByRole("listitem")).toHaveLength(25);
    });
    fail = true;

    await user.click(screen.getByRole("button", { name: "Cargar más" }));

    expect(await screen.findByText(HISTORY_MESSAGES.loadMoreFailed)).toBeInTheDocument();
    expect(screen.getAllByRole("listitem")).toHaveLength(25);
    fail = false;
    await user.click(screen.getByRole("button", { name: "Cargar más" }));
    await waitFor(() => {
      expect(screen.getAllByRole("listitem")).toHaveLength(30);
    });
  });
});

describe("MemberHistoryTab · errores", () => {
  it("un error del api muestra el mensaje y Reintentar vuelve a pedir", async () => {
    let fail = true;
    const { mock, user } = renderMemberHistoryTab({
      handlers: { [`GET ${HISTORY_PATH}`]: (c) => (fail ? apiError(500, "internal_error") : historyReply(historyItems())(c)) },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(HISTORY_MESSAGES.failed);
    fail = false;
    await user.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByText("juan mostró el documento")).toBeInTheDocument();
    expect(mock.callsTo(`GET ${HISTORY_PATH}`)).toHaveLength(2);
  });

  it("429 (staff-read) dice 'Demasiadas consultas; espera un momento'", async () => {
    renderMemberHistoryTab({ handlers: { [`GET ${HISTORY_PATH}`]: apiError(429, "rate_limited", {}, { "Retry-After": "30" }) } });

    expect(await screen.findByRole("alert")).toHaveTextContent("Demasiadas consultas; espera un momento");
  });

  it("404 dice que el socio ya no existe", async () => {
    renderMemberHistoryTab({ handlers: { [`GET ${HISTORY_PATH}`]: apiError(404, "member_not_found") } });
    expect(await screen.findByRole("alert")).toHaveTextContent(HISTORY_MESSAGES.notFound);
  });

  it("una respuesta con valores (before, after o user_email) es inválida y no se pinta", async () => {
    const leaked = { ...historyItems()[0], before: { phone: PHONE_VALUE } };
    const { container } = renderMemberHistoryTab({ handlers: { [`GET ${HISTORY_PATH}`]: ok({ items: [leaked], total: 1, limit: 25, offset: 0 }) } });

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(container.textContent).not.toContain(PHONE_VALUE);
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });
});

describe("MemberHistoryTab · revisión de seguridad (LOW-1)", () => {
  it("un :id sin forma de UUID no pide nada y dice que el socio no existe (sin cargar para siempre)", async () => {
    const { mock } = renderMemberHistoryTab({ entry: "/socios/no-es-un-uuid/historial" });

    expect(await screen.findByRole("alert")).toHaveTextContent(HISTORY_MESSAGES.notFound);
    expect(screen.queryByText("Cargando historial")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reintentar" })).not.toBeInTheDocument();
    expect(mock.calls).toHaveLength(0);
  });
});
