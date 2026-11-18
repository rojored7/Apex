// S9-F1 · US-179 y L-7 (S9-D15, S9-D34, S9-D36): un campo de una medición con «Mostrar».
// - «•••» si el api dice `has_*` y «—» si no; el valor en claro nunca llega en la lista.
// - «Mostrar» llama POST /athletes/{id}/metrics/{metric_id}/reveal con UN campo; el claro vive 60 s y se oculta al ocultar,
//   al perder visibilidad (visibilitychange a hidden), al salir de la página y al desmontar.
// - No queda en la caché de TanStack Query (gcTime 0 y reset()), ni en el almacenamiento, ni en la URL, ni en un aria-label.
// - 403 de un coach con el socio dado de baja: lo explica (solo un administrador, S9-D34).
import { act, cleanup, screen } from "@testing-library/react";
import type { MockInstance } from "vitest";
import { fakeTimersUser, restoreRtlTimers, useRtlFakeTimers } from "../../../test/fakeTimers";
import { apiError, cacheText, CLEAR, MEMBER_ID, metricId, renderAthlete, revealPath, revealReply } from "../../../test/athletes";
import { testQueryClient } from "../../../test/server";
import { signInAs, signOutForTests } from "../../../test/session";
import { REVEAL_TTL_MS } from "../../../shared/ui/MaskedValue";
import { MetricField, type MetricFieldProps } from "./MetricField";

/** Todo lo que hay en localStorage y sessionStorage, como texto. */
function storageText(): string {
  const dump = (storage: Storage): string[] => Array.from({ length: storage.length }, (_, i) => `${storage.key(i) ?? ""}=${storage.getItem(storage.key(i) ?? "") ?? ""}`);
  return [...dump(localStorage), ...dump(sessionStorage)].join("\n");
}

const METRIC = metricId(1);
const REVEAL = `POST ${revealPath(METRIC)}`;
const WEIGHT = "61,2 kg";
const base: MetricFieldProps = { memberId: MEMBER_ID, metricId: METRIC, field: "weight_g", has: true };

const flushGc = (): void => {
  act(() => {
    vi.advanceTimersByTime(0);
  });
};

/** Todo texto de atributos aria-label y title del documento. */
const ariaText = (): string =>
  Array.from(document.querySelectorAll("[aria-label],[title]"))
    .map((el) => `${el.getAttribute("aria-label") ?? ""} ${el.getAttribute("title") ?? ""}`)
    .join("\n");

let consoleSpies: MockInstance[] = [];

beforeEach(() => {
  useRtlFakeTimers();
  signInAs("coach");
  consoleSpies = (["log", "info", "warn", "error", "debug"] as const).map((method) => vi.spyOn(console, method).mockImplementation(() => undefined));
});

afterEach(() => {
  for (const spy of consoleSpies) expect(JSON.stringify(spy.mock.calls)).not.toContain("61200");
  cleanup();
  signOutForTests();
  restoreRtlTimers();
  vi.restoreAllMocks();
  localStorage.clear();
  sessionStorage.clear();
});

describe("MetricField · estado en reposo", () => {
  it("con valor guardado muestra «•••» y el botón «Mostrar peso»; no pide nada al abrir", () => {
    const { mock } = renderAthlete(<MetricField {...base} />, { handlers: { [REVEAL]: revealReply } });

    expect(screen.getByText("•••")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mostrar peso" })).toBeInTheDocument();
    expect(mock.callsTo(REVEAL)).toHaveLength(0);
  });

  it("sin valor muestra «—» y ningún botón", () => {
    renderAthlete(<MetricField {...base} has={false} />);

    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByText("•••")).not.toBeInTheDocument();
  });

  it.each([
    ["weight_g", "Mostrar peso"],
    ["height_cm", "Mostrar altura"],
    ["body_fat_pct", "Mostrar % grasa"],
    ["notes", "Mostrar notas"],
  ] as const)("el botón del campo %s se llama «%s»", (field, name) => {
    renderAthlete(<MetricField {...base} field={field} />);

    expect(screen.getByRole("button", { name })).toBeInTheDocument();
  });
});

describe("MetricField · mostrar", () => {
  it("una pulsación hace UNA llamada con el campo pedido y muestra el peso en kg con un decimal", async () => {
    const user = fakeTimersUser();
    const { mock } = renderAthlete(<MetricField {...base} />, { handlers: { [REVEAL]: revealReply } });

    await user.dblClick(screen.getByRole("button", { name: "Mostrar peso" }));

    expect(await screen.findByText(WEIGHT)).toBeInTheDocument();
    const calls = mock.callsTo(REVEAL);
    expect(calls).toHaveLength(1);
    expect(calls[0]?.body).toEqual({ field: "weight_g" });
    expect(calls[0]?.path).toBe(`/athletes/${MEMBER_ID}/metrics/${METRIC}/reveal`);
    expect(screen.queryByText("•••")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ocultar peso" })).toBeInTheDocument();
  });

  it.each([
    ["height_cm", "Mostrar altura", "165 cm"],
    ["body_fat_pct", "Mostrar % grasa", "22 %"],
    ["notes", "Mostrar notas", CLEAR.notes],
  ] as const)("el campo %s se muestra como «%s»", async (field, name, text) => {
    const user = fakeTimersUser();
    const { mock } = renderAthlete(<MetricField {...base} field={field} />, { handlers: { [REVEAL]: revealReply } });

    await user.click(screen.getByRole("button", { name }));

    expect(await screen.findByText(text)).toBeInTheDocument();
    expect(mock.callsTo(REVEAL)[0]?.body).toEqual({ field });
  });

  it("Ocultar lo enmascara al instante y otra pulsación vuelve a pedirlo (cada vista queda auditada)", async () => {
    const user = fakeTimersUser();
    const { mock } = renderAthlete(<MetricField {...base} />, { handlers: { [REVEAL]: revealReply } });

    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));
    await user.click(await screen.findByRole("button", { name: "Ocultar peso" }));

    expect(document.body).not.toHaveTextContent(WEIGHT);
    expect(screen.getByText("•••")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));
    await screen.findByText(WEIGHT);
    expect(mock.callsTo(REVEAL)).toHaveLength(2);
  });
});

describe("MetricField · el valor vive poco (L-7)", () => {
  it("vuelve a «•••» a los 60 s", async () => {
    const user = fakeTimersUser();
    renderAthlete(<MetricField {...base} />, { handlers: { [REVEAL]: revealReply } });
    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));
    await screen.findByText(WEIGHT);

    act(() => {
      vi.advanceTimersByTime(REVEAL_TTL_MS - 1);
    });
    expect(screen.getByText(WEIGHT)).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(1);
    });

    expect(document.body).not.toHaveTextContent(WEIGHT);
    expect(screen.getByText("•••")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mostrar peso" })).toBeInTheDocument();
  });

  it("se oculta al perder la visibilidad de la pestaña, antes de los 60 s", async () => {
    const user = fakeTimersUser();
    renderAthlete(<MetricField {...base} />, { handlers: { [REVEAL]: revealReply } });
    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));
    await screen.findByText(WEIGHT);
    const visibility = vi.spyOn(document, "visibilityState", "get");

    visibility.mockReturnValue("visible");
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(screen.getByText(WEIGHT)).toBeInTheDocument();
    visibility.mockReturnValue("hidden");
    act(() => {
      document.dispatchEvent(new Event("visibilitychange"));
    });

    expect(document.body).not.toHaveTextContent(WEIGHT);
    expect(screen.getByText("•••")).toBeInTheDocument();
  });

  it("se oculta al salir de la página (pagehide)", async () => {
    const user = fakeTimersUser();
    renderAthlete(<MetricField {...base} />, { handlers: { [REVEAL]: revealReply } });
    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));
    await screen.findByText(WEIGHT);

    act(() => {
      window.dispatchEvent(new Event("pagehide"));
    });

    expect(document.body).not.toHaveTextContent(WEIGHT);
  });

  it("si la respuesta llega con la pestaña oculta, el valor no queda a la vista al volver", async () => {
    const user = fakeTimersUser();
    let answer: (reply: ReturnType<typeof revealReply>) => void = () => undefined;
    const pending = new Promise<ReturnType<typeof revealReply>>((resolve) => {
      answer = resolve;
    });
    renderAthlete(<MetricField {...base} />, { handlers: { [REVEAL]: () => pending } });
    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");

    await act(async () => {
      answer({ status: 200, body: { field: "weight_g", value: CLEAR.weight_g } });
      await Promise.resolve();
    });
    visibility.mockReturnValue("visible");

    expect(document.body).not.toHaveTextContent(WEIGHT);
    expect(screen.getByRole("button", { name: "Mostrar peso" })).toBeInTheDocument();
  });

  it("al desmontar el valor no queda en el DOM", async () => {
    const user = fakeTimersUser();
    const { unmount } = renderAthlete(<MetricField {...base} />, { handlers: { [REVEAL]: revealReply } });
    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));
    await screen.findByText(WEIGHT);

    unmount();

    expect(document.body.innerHTML).not.toContain(WEIGHT);
  });
});

describe("MetricField · el valor no se guarda en ningún sitio (L-7)", () => {
  it("la caché de TanStack Query no lo conserva: gcTime 0 y reset() tras responder", async () => {
    const user = fakeTimersUser();
    const queryClient = testQueryClient();
    renderAthlete(<MetricField {...base} />, { queryClient, handlers: { [REVEAL]: revealReply } });

    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));
    await screen.findByText(WEIGHT);
    flushGc();

    expect(cacheText(queryClient)).not.toContain("61200");
    expect(cacheText(queryClient)).not.toContain("61,2");
    expect(queryClient.getMutationCache().getAll()).toHaveLength(0);
  });

  it("no llega a localStorage ni a sessionStorage", async () => {
    const user = fakeTimersUser();
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    renderAthlete(<MetricField {...base} />, { handlers: { [REVEAL]: revealReply } });

    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));
    await screen.findByText(WEIGHT);

    expect(JSON.stringify(setItem.mock.calls)).not.toContain("61200");
    expect(JSON.stringify(setItem.mock.calls)).not.toContain("61,2");
    expect(storageText()).not.toContain("61200");
    expect(storageText()).not.toContain("61,2");
  });

  it("no está en la URL ni en ningún aria-label o title, ni mostrado ni oculto", async () => {
    const user = fakeTimersUser();
    renderAthlete(<MetricField {...base} />, { handlers: { [REVEAL]: revealReply } });

    expect(ariaText()).not.toMatch(/61/);
    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));
    await screen.findByText(WEIGHT);

    expect(ariaText()).not.toMatch(/61/);
    expect(screen.getByTestId("where")).toHaveTextContent(`/socios/${MEMBER_ID}/atleta`);
    expect(screen.getByTestId("where").textContent).not.toMatch(/61/);
    expect(window.location.href).not.toMatch(/61/);
  });
});

describe("MetricField · errores", () => {
  it("403 de un coach con el socio dado de baja: explica que solo un administrador puede verlo", async () => {
    const user = fakeTimersUser();
    renderAthlete(<MetricField {...base} memberDeleted />, { handlers: { [REVEAL]: apiError(403, "forbidden") } });

    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Este socio está dado de baja: solo un administrador puede mostrar sus medidas.");
    expect(screen.getByText("•••")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(WEIGHT);
  });

  it("403 con el socio vivo dice que no tiene permiso, sin hablar de la baja", async () => {
    const user = fakeTimersUser();
    renderAthlete(<MetricField {...base} />, { handlers: { [REVEAL]: apiError(403, "forbidden") } });

    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("No tienes permiso para ver este dato");
    expect(alert).not.toHaveTextContent("dado de baja");
  });

  it("409 metric_voided dice que la medición está anulada", async () => {
    const user = fakeTimersUser();
    renderAthlete(<MetricField {...base} />, { handlers: { [REVEAL]: apiError(409, "metric_voided") } });

    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Esta medición está anulada y ya no se puede mostrar.");
  });

  it("429 dice «Demasiadas consultas; espera un momento» y no muestra nada", async () => {
    const user = fakeTimersUser();
    renderAthlete(<MetricField {...base} />, { handlers: { [REVEAL]: apiError(429, "rate_limited", {}, { "Retry-After": "40" }) } });

    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Demasiadas consultas; espera un momento");
    expect(document.body).not.toHaveTextContent(WEIGHT);
  });

  it("503 crypto_unavailable dice qué hacer y no muestra nada", async () => {
    const user = fakeTimersUser();
    renderAthlete(<MetricField {...base} />, { handlers: { [REVEAL]: apiError(503, "crypto_unavailable", {}, { "Retry-After": "30" }) } });

    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos mostrar el dato. Intenta de nuevo en un momento.");
    expect(document.body).not.toHaveTextContent(WEIGHT);
  });

  it("500 dice qué hacer, sin el texto técnico del api", async () => {
    const user = fakeTimersUser();
    renderAthlete(<MetricField {...base} />, { handlers: { [REVEAL]: apiError(500, "internal_error") } });

    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos mostrar el dato. Intenta de nuevo en un momento.");
    expect(screen.queryByText("Mensaje del api.")).not.toBeInTheDocument();
  });
});

// S9-F1 (revisión M2, seguridad L3 y L4): el valor se anuncia, el reveal en vuelo se cancela al desmontar y una respuesta rara se rechaza.
describe("MetricField · revisión", () => {
  it("el valor revelado se anuncia: su contenedor es aria-live polite", async () => {
    const user = fakeTimersUser();
    renderAthlete(<MetricField {...base} />, { handlers: { [REVEAL]: revealReply } });
    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));

    expect(await screen.findByText(WEIGHT)).toHaveAttribute("aria-live", "polite");
  });

  it("desmontar con el reveal en vuelo cancela la petición y no deja nada en pantalla", async () => {
    const user = fakeTimersUser();
    const { mock, unmount } = renderAthlete(<MetricField {...base} />, { handlers: { [REVEAL]: () => new Promise(() => undefined) } });
    await user.click(screen.getByRole("button", { name: "Mostrar peso" }));
    expect(mock.callsTo(REVEAL)).toHaveLength(1);
    expect(mock.callsTo(REVEAL)[0]?.signal?.aborted).toBe(false);

    unmount();

    expect(mock.callsTo(REVEAL)[0]?.signal?.aborted).toBe(true);
    expect(document.body.innerHTML).not.toContain(WEIGHT);
  });

  it.each([
    ["el campo de la respuesta no es el pedido", { field: "height_cm", value: 165 }],
    ["el peso llega como texto", { field: "weight_g", value: "61200" }],
    ["el peso no es entero", { field: "weight_g", value: 61200.5 }],
    ["las notas llegan como número", { field: "notes", value: 5 }],
  ])("rechaza la respuesta si %s", async (_name, body) => {
    const user = fakeTimersUser();
    const field = body.field === "notes" ? "notes" : "weight_g";
    renderAthlete(<MetricField {...base} field={field} />, { handlers: { [REVEAL]: { status: 200, body } } });

    await user.click(screen.getByRole("button", { name: field === "notes" ? "Mostrar notas" : "Mostrar peso" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("La respuesta del servidor no es válida. Recarga la página e intenta de nuevo.");
    expect(document.body).not.toHaveTextContent(/61,2 kg|61200|165 cm/);
  });
});
