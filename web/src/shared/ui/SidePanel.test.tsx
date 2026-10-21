// US-065 T2 y T4: panel lateral con trampa de foco y confirmación al descartar cambios.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { useState } from "react";
import { Button } from "./Button";
import { SidePanel } from "./SidePanel";

function Harness({ dirty = false, onClose }: { dirty?: boolean; onClose?: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => { setOpen(true); }}>
        Nuevo plan
      </button>
      <SidePanel
        open={open}
        title="Editar plan · 12 clases"
        isDirty={dirty}
        onClose={() => {
          onClose?.();
          setOpen(false);
        }}
        footer={<Button type="submit">Guardar</Button>}
      >
        <label htmlFor="nombre">Nombre</label>
        <input id="nombre" defaultValue="12 clases" />
      </SidePanel>
    </>
  );
}

async function openPanel(dirty = false, onClose?: () => void) {
  const user = userEvent.setup();
  render(<Harness dirty={dirty} {...(onClose ? { onClose } : {})} />);
  await user.click(screen.getByRole("button", { name: "Nuevo plan" }));
  return user;
}

describe("SidePanel", () => {
  it("cerrado no renderiza nada", () => {
    render(<Harness />);

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("es un diálogo modal con título asociado, ✕, Cancelar y el pie", async () => {
    await openPanel();

    const dialog = screen.getByRole("dialog", { name: "Editar plan · 12 clases" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("button", { name: "Cerrar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar" })).toBeInTheDocument();
  });

  it("atrapa el foco y lo devuelve al botón que lo abrió", async () => {
    const user = await openPanel();

    expect(screen.getByRole("button", { name: "Cerrar" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("textbox", { name: "Nombre" })).toHaveFocus();
    await user.tab();
    await user.tab();
    expect(screen.getByRole("button", { name: "Guardar" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Cerrar" })).toHaveFocus();

    await user.click(screen.getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nuevo plan" })).toHaveFocus();
  });

  it("sin cambios, Escape cierra de una vez", async () => {
    const onClose = vi.fn();
    const user = await openPanel(false, onClose);

    await user.keyboard("{Escape}");

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("con cambios, Escape pregunta y Volver mantiene el panel", async () => {
    const onClose = vi.fn();
    const user = await openPanel(true, onClose);

    await user.keyboard("{Escape}");

    expect(screen.getByRole("dialog", { name: "¿Descartar los cambios?" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Volver" }));
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog", { name: "¿Descartar los cambios?" })).not.toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Editar plan · 12 clases" })).toBeInTheDocument();
  });

  it("con cambios, ✕ pregunta y Descartar cambios cierra", async () => {
    const onClose = vi.fn();
    const user = await openPanel(true, onClose);

    await user.click(screen.getByRole("button", { name: "Cerrar" }));
    await user.click(screen.getByRole("button", { name: "Descartar cambios" }));

    expect(onClose).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("con cambios, clic fuera pregunta; clic dentro no", async () => {
    const onClose = vi.fn();
    const user = await openPanel(true, onClose);

    await user.click(screen.getByRole("textbox", { name: "Nombre" }));
    expect(screen.queryByRole("dialog", { name: "¿Descartar los cambios?" })).not.toBeInTheDocument();

    await user.click(screen.getByTestId("side-panel-backdrop"));
    expect(screen.getByRole("dialog", { name: "¿Descartar los cambios?" })).toBeInTheDocument();
  });

  it("sin cambios, clic fuera cierra", async () => {
    const onClose = vi.fn();
    const user = await openPanel(false, onClose);

    await user.click(screen.getByTestId("side-panel-backdrop"));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ocupa todo el ancho en celular y anima solo con transform (CSS)", () => {
    const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "SidePanel.module.css"), "utf8");

    expect(css).toMatch(/@media \(width < 768px\)[\s\S]*\.panel\s*\{[^}]*width:\s*100%/);
    expect(css).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
    expect(css).toMatch(/transform/);
  });
});
