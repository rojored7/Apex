// S5-F5 · US-136 (front): el aviso global de custodio no disponible. El cliente del api lo
// pide con reportCustodyUnavailable (503 crypto_unavailable); el host lo muestra discreto en el
// panel, respeta Retry-After (se retira solo al vencer la espera) y se puede cerrar a mano.
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { CustodyNoticeHost } from "./CustodyNoticeHost";
import { clearCustodyNotice, CUSTODY_DEFAULT_RETRY_S, reportCustodyUnavailable } from "./custodyNotice";

afterEach(() => {
  cleanup();
  clearCustodyNotice();
  delete document.documentElement.dataset.theme;
  vi.useRealTimers();
});

describe("CustodyNoticeHost", () => {
  it("sin aviso pendiente no pinta nada", () => {
    const { container } = render(<CustodyNoticeHost />);

    expect(container).toBeEmptyDOMElement();
  });

  it("dice qué pasó y qué hacer, con los segundos de Retry-After", () => {
    render(<CustodyNoticeHost />);

    act(() => {
      reportCustodyUnavailable(45);
    });

    const notice = screen.getByRole("status");
    expect(notice).toHaveTextContent("Los datos protegidos no están disponibles por ahora.");
    expect(notice).toHaveTextContent("Intenta de nuevo en 45 segundos. Si sigue igual, avisa al administrador del sistema.");
  });

  it("sin Retry-After usa el valor por defecto y en singular dice 1 segundo", () => {
    render(<CustodyNoticeHost />);

    act(() => {
      reportCustodyUnavailable(undefined);
    });
    expect(screen.getByRole("status")).toHaveTextContent(`en ${String(CUSTODY_DEFAULT_RETRY_S)} segundos`);

    act(() => {
      reportCustodyUnavailable(1);
    });
    expect(screen.getByRole("status")).toHaveTextContent("en 1 segundo.");
  });

  it("se retira solo cuando pasa la espera de Retry-After", () => {
    vi.useFakeTimers();
    render(<CustodyNoticeHost />);
    act(() => {
      reportCustodyUnavailable(30);
    });

    act(() => {
      vi.advanceTimersByTime(29_999);
    });
    expect(screen.getByRole("status")).toBeInTheDocument();
    act(() => {
      vi.advanceTimersByTime(1);
    });

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("un nuevo 503 reinicia la espera", () => {
    vi.useFakeTimers();
    render(<CustodyNoticeHost />);
    act(() => {
      reportCustodyUnavailable(30);
    });
    act(() => {
      vi.advanceTimersByTime(20_000);
    });
    act(() => {
      reportCustodyUnavailable(30);
    });

    act(() => {
      vi.advanceTimersByTime(20_000);
    });

    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("'Cerrar aviso' lo retira", async () => {
    const user = userEvent.setup();
    render(<CustodyNoticeHost />);
    act(() => {
      reportCustodyUnavailable(30);
    });

    await user.click(screen.getByRole("button", { name: "Cerrar aviso" }));

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it.each([
    ["claro", null],
    ["oscuro", "dark"],
  ])("no tiene violaciones de accesibilidad en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    const { container } = render(<CustodyNoticeHost />);
    act(() => {
      reportCustodyUnavailable(30);
    });

    expect(await axe(container)).toHaveNoViolations();
  });
});
