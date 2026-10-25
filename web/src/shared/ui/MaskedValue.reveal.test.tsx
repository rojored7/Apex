// S3-F1 · US-074 (cierra el criterio diferido de US-066): "Mostrar" de la ficha conectado a
// POST /members/{id}/reveal con useRevealField (M-9, S3-D52). Con temporizadores falsos:
// - una sola llamada por clic y el claro solo mientras se muestra: se re-enmascara a los 60 s, al
//   ocultar y al desmontar;
// - 403 y 500 no dejan valor en pantalla; 429 dice "Demasiadas consultas; espera un momento";
// - el claro nunca llega a localStorage, sessionStorage, la consola ni la caché de TanStack Query
//   (tras `reset()` la mutación no conserva `data`), y un ErrorBoundary que lanza después de
//   revelar no lo deja en document.body.innerHTML.
// MaskedValue.tsx no cambia de comportamiento (sus pruebas propias siguen en MaskedValue.test.tsx).
import { act, screen } from "@testing-library/react";
import { Component, useState, type ErrorInfo, type ReactNode } from "react";
import type { MockInstance } from "vitest";
import { apiError, MEMBER_ID, REVEAL_PATH, REVEALED, renderSensitiveField } from "../../test/memberDetail";
import { fakeTimersUser, restoreRtlTimers, useRtlFakeTimers } from "../../test/fakeTimers";
import { testQueryClient } from "../../test/server";
import { signInAs, signOutForTests } from "../../test/session";
import { REVEAL_TTL_MS } from "./MaskedValue";

const PLAIN = REVEALED.document;

/** Todo lo que la caché de mutaciones guarda, como texto. */
function mutationCacheText(queryClient: ReturnType<typeof testQueryClient>): string {
  return JSON.stringify(queryClient.getMutationCache().getAll().map((m) => m.state));
}

function storageText(): string {
  const dump = (storage: Storage): string[] => Array.from({ length: storage.length }, (_, i) => `${storage.key(i) ?? ""}=${storage.getItem(storage.key(i) ?? "") ?? ""}`);
  return [...dump(localStorage), ...dump(sessionStorage)].join("\n");
}

const flushGc = (): void => {
  act(() => {
    vi.advanceTimersByTime(0);
  });
};

interface BoundaryState {
  failed: boolean;
}

/** Un ErrorBoundary que, como uno real, podría serializar lo que recibe. */
class TestBoundary extends Component<{ children: ReactNode; onError: (text: string) => void }, BoundaryState> {
  override state: BoundaryState = { failed: false };

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    this.props.onError(`${error.message} ${info.componentStack ?? ""}`);
  }

  override render(): ReactNode {
    return this.state.failed ? <p>Algo salió mal</p> : this.props.children;
  }
}

function Breaker({ children }: { children: ReactNode }) {
  const [broken, setBroken] = useState(false);
  if (broken) throw new Error("fallo al pintar");
  return (
    <>
      {children}
      <button
        type="button"
        onClick={() => {
          setBroken(true);
        }}
      >
        Romper
      </button>
    </>
  );
}

describe("MaskedValue con POST /members/{id}/reveal (S3-F1, S3-D52)", () => {
  let consoleSpies: MockInstance[] = [];

  beforeEach(() => {
    useRtlFakeTimers();
    signInAs("coach");
    consoleSpies = (["log", "info", "warn", "error", "debug"] as const).map((method) => vi.spyOn(console, method).mockImplementation(() => undefined));
  });

  afterEach(() => {
    for (const spy of consoleSpies) expect(JSON.stringify(spy.mock.calls)).not.toContain(PLAIN);
    signOutForTests();
    restoreRtlTimers();
    vi.restoreAllMocks();
    localStorage.clear();
    sessionStorage.clear();
  });

  it("una pulsación hace una sola llamada con el campo y muestra el claro", async () => {
    const user = fakeTimersUser();
    const { mock } = renderSensitiveField();

    await user.dblClick(screen.getByRole("button", { name: "Mostrar" }));

    expect(await screen.findByText(PLAIN)).toBeInTheDocument();
    const calls = mock.callsTo(`POST ${REVEAL_PATH}`);
    expect(calls).toHaveLength(1);
    expect(calls[0]?.body).toEqual({ field: "document" });
    expect(calls[0]?.path).toBe(`/members/${MEMBER_ID}/reveal`);
  });

  it("vuelve a enmascararse a los 60 s y otra pulsación vuelve a pedirlo (cada vista queda auditada)", async () => {
    const user = fakeTimersUser();
    const { mock } = renderSensitiveField();

    await user.click(screen.getByRole("button", { name: "Mostrar" }));
    await screen.findByText(PLAIN);
    act(() => {
      vi.advanceTimersByTime(REVEAL_TTL_MS);
    });

    expect(document.body).not.toHaveTextContent(PLAIN);
    expect(screen.getByText("CC •••• 4417")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Mostrar" }));
    await screen.findByText(PLAIN);
    expect(mock.callsTo(`POST ${REVEAL_PATH}`)).toHaveLength(2);
  });

  it("Ocultar lo enmascara al instante", async () => {
    const user = fakeTimersUser();
    renderSensitiveField();

    await user.click(screen.getByRole("button", { name: "Mostrar" }));
    await user.click(await screen.findByRole("button", { name: "Ocultar" }));

    expect(document.body).not.toHaveTextContent(PLAIN);
    expect(screen.getByText("CC •••• 4417")).toBeInTheDocument();
  });

  it("al desmontar el claro no queda en el DOM", async () => {
    const user = fakeTimersUser();
    const { unmount } = renderSensitiveField();

    await user.click(screen.getByRole("button", { name: "Mostrar" }));
    await screen.findByText(PLAIN);
    unmount();

    expect(document.body.innerHTML).not.toContain(PLAIN);
  });

  it("un 403 avisa sin permiso y no muestra ningún valor", async () => {
    const user = fakeTimersUser();
    renderSensitiveField({}, { handlers: { [`POST ${REVEAL_PATH}`]: apiError(403, "forbidden") } });

    await user.click(screen.getByRole("button", { name: "Mostrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No tienes permiso para ver este dato");
    expect(screen.getByText("CC •••• 4417")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(PLAIN);
  });

  it("un 500 dice qué pasó y qué hacer, sin valor y sin el texto técnico del api", async () => {
    const user = fakeTimersUser();
    renderSensitiveField({}, { handlers: { [`POST ${REVEAL_PATH}`]: apiError(500, "internal_error") } });

    await user.click(screen.getByRole("button", { name: "Mostrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No pudimos mostrar el dato. Intenta de nuevo en un momento.");
    expect(screen.queryByText("Mensaje del api.")).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(PLAIN);
  });

  it("un 429 (cualquiera de los tres cupos) dice 'Demasiadas consultas; espera un momento'", async () => {
    const user = fakeTimersUser();
    renderSensitiveField({}, { handlers: { [`POST ${REVEAL_PATH}`]: apiError(429, "rate_limited", {}, { "Retry-After": "40" }) } });

    await user.click(screen.getByRole("button", { name: "Mostrar" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Demasiadas consultas; espera un momento");
    expect(document.body).not.toHaveTextContent(PLAIN);
  });

  it("el claro nunca llega a localStorage ni a sessionStorage", async () => {
    const user = fakeTimersUser();
    const setItem = vi.spyOn(Storage.prototype, "setItem");
    renderSensitiveField();

    await user.click(screen.getByRole("button", { name: "Mostrar" }));
    await screen.findByText(PLAIN);

    expect(JSON.stringify(setItem.mock.calls)).not.toContain(PLAIN);
    expect(storageText()).not.toContain(PLAIN);
  });

  it("la caché de TanStack Query no conserva el valor: reset() tras responder y la mutación sale de la caché (gcTime 0)", async () => {
    const user = fakeTimersUser();
    const queryClient = testQueryClient();
    renderSensitiveField({}, { queryClient });

    await user.click(screen.getByRole("button", { name: "Mostrar" }));
    await screen.findByText(PLAIN);
    flushGc();

    // Mientras se ve en pantalla, ya no está en la caché de mutaciones ni en la de consultas.
    expect(mutationCacheText(queryClient)).not.toContain(PLAIN);
    expect(queryClient.getMutationCache().getAll().some((m) => m.state.data !== undefined)).toBe(false);
    expect(JSON.stringify(queryClient.getQueryCache().getAll().map((q) => q.state.data))).not.toContain(PLAIN);

    act(() => {
      vi.advanceTimersByTime(REVEAL_TTL_MS);
    });
    flushGc();

    expect(document.body).not.toHaveTextContent(PLAIN);
    expect(queryClient.getMutationCache().getAll()).toEqual([]);
  });

  it("el contacto de emergencia se revela aplanado y tampoco queda en la caché", async () => {
    const user = fakeTimersUser();
    const queryClient = testQueryClient();
    renderSensitiveField({ field: "emergency_contact", label: "Contacto de emergencia", masked: "Registrado" }, { queryClient });

    await user.click(screen.getByRole("button", { name: "Mostrar" }));

    expect(await screen.findByText("Marta Gómez · Madre · 3110000008")).toBeInTheDocument();
    flushGc();
    expect(mutationCacheText(queryClient)).not.toContain("3110000008");
  });

  it("un ErrorBoundary que lanza después de revelar no deja el valor en document.body.innerHTML", async () => {
    const user = fakeTimersUser();
    const caught: string[] = [];
    renderSensitiveField(
      {},
      {
        wrap: (field) => (
          <TestBoundary onError={(text) => caught.push(text)}>
            <Breaker>{field}</Breaker>
          </TestBoundary>
        ),
      },
    );

    await user.click(screen.getByRole("button", { name: "Mostrar" }));
    await screen.findByText(PLAIN);
    await user.click(screen.getByRole("button", { name: "Romper" }));

    expect(await screen.findByText("Algo salió mal")).toBeInTheDocument();
    expect(document.body.innerHTML).not.toContain(PLAIN);
    expect(caught.join(" ")).not.toContain(PLAIN);
  });
});
