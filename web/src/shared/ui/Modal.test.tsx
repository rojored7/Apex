// S2-F4b: diálogo de contenido del kit (hermano de ConfirmModal para mostrar un resultado).
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "vitest-axe";
import { Button } from "./Button";
import { Modal } from "./Modal";

afterEach(() => {
  cleanup();
});

function renderModal({ busy = false, open = true }: { busy?: boolean; open?: boolean } = {}) {
  const onClose = vi.fn();
  render(
    <Modal open={open} title="Reenviar enlace" busy={busy} onClose={onClose} actions={<Button onClick={onClose}>Listo</Button>}>
      <p>Contenido del diálogo.</p>
    </Modal>,
  );
  return { onClose, user: userEvent.setup() };
}

describe("Modal", () => {
  it("cerrado no pinta nada", () => {
    renderModal({ open: false });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("es un diálogo modal con su título, el contenido y las acciones", () => {
    renderModal();

    const dialog = screen.getByRole("dialog", { name: "Reenviar enlace" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveTextContent("Contenido del diálogo.");
    expect(screen.getByRole("button", { name: "Listo" })).toBeInTheDocument();
    expect(dialog).not.toHaveAttribute("aria-busy");
  });

  it("L8 (revisión del Sprint 2): el cuerpo es la descripción accesible del diálogo", () => {
    renderModal();

    expect(screen.getByRole("dialog", { name: "Reenviar enlace" })).toHaveAccessibleDescription("Contenido del diálogo.");
  });

  it("Escape cierra", async () => {
    const { onClose, user } = renderModal();

    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ocupado, Escape no cierra y el diálogo lo anuncia", async () => {
    const { onClose, user } = renderModal({ busy: true });

    await user.keyboard("{Escape}");

    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toHaveAttribute("aria-busy", "true");
  });

  it("el foco entra al diálogo", () => {
    renderModal();

    expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement);
  });

  it("no tiene violaciones de accesibilidad", async () => {
    renderModal();

    expect(await axe(document.body)).toHaveNoViolations();
  });
});
