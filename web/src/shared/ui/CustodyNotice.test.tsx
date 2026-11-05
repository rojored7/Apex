// S5-F5 · US-136: aviso discreto (presentacional) de custodio de llaves no disponible.
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { CustodyNotice } from "./CustodyNotice";

afterEach(() => {
  cleanup();
  delete document.documentElement.dataset.theme;
});

describe("CustodyNotice", () => {
  it("es una región de estado con qué pasó y qué hacer", () => {
    render(<CustodyNotice retryAfterS={30} onDismiss={vi.fn()} />);

    const notice = screen.getByRole("status");
    expect(notice).toHaveTextContent("Los datos protegidos no están disponibles por ahora.");
    expect(notice).toHaveTextContent("Intenta de nuevo en 30 segundos. Si sigue igual, avisa al administrador del sistema.");
  });

  it("Cerrar aviso llama a onDismiss", async () => {
    const onDismiss = vi.fn();
    render(<CustodyNotice retryAfterS={30} onDismiss={onDismiss} />);

    await userEvent.setup().click(screen.getByRole("button", { name: "Cerrar aviso" }));

    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["claro", null],
    ["oscuro", "dark"],
  ])("no tiene violaciones de accesibilidad en tema %s", async (_name, theme) => {
    if (theme) document.documentElement.dataset.theme = theme;
    const { container } = render(<CustodyNotice retryAfterS={1} onDismiss={vi.fn()} />);

    expect(await axe(container)).toHaveNoViolations();
  });
});
