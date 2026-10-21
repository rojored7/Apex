// US-065 T1: trampa de foco compartida por SidePanel y ConfirmModal.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef, useState } from "react";
import { useFocusTrap } from "./useFocusTrap";

function Trap({ label, onEscape, withInitial = false }: { label: string; onEscape?: () => void; withInitial?: boolean }) {
  const initialRef = useRef<HTMLInputElement>(null);
  const ref = useFocusTrap<HTMLDivElement>(true, { onEscape, ...(withInitial ? { initialFocusRef: initialRef } : {}) });
  return (
    <div ref={ref} data-testid={label}>
      <button type="button">{`${label} primero`}</button>
      <input aria-label={`${label} campo`} ref={initialRef} />
      <button type="button">{`${label} último`}</button>
    </div>
  );
}

function Harness({ nested = false, onEscape }: { nested?: boolean; onEscape?: () => void }) {
  const [open, setOpen] = useState(false);
  const [inner, setInner] = useState(false);
  return (
    <>
      <button type="button" onClick={() => { setOpen(true); }}>
        Abrir
      </button>
      <button type="button">Fuera</button>
      {open ? (
        <>
          <Trap label="Panel" onEscape={onEscape ?? (() => { setOpen(false); })} />
          {nested ? (
            <button type="button" onClick={() => { setInner(true); }}>
              Abrir interno
            </button>
          ) : null}
          {inner ? <Trap label="Modal" onEscape={() => { setInner(false); }} withInitial /> : null}
        </>
      ) : null}
      <button type="button" onClick={() => { setOpen(false); }}>
        Cerrar externo
      </button>
    </>
  );
}

function EmptyTrap() {
  const ref = useFocusTrap<HTMLDivElement>(true);
  return (
    <div ref={ref} tabIndex={-1} aria-label="Vacío">
      Sin controles
    </div>
  );
}

function Inactive() {
  const ref = useFocusTrap<HTMLDivElement>(false);
  return (
    <div ref={ref}>
      <button type="button">Dentro inactivo</button>
    </div>
  );
}

afterEach(() => {
  document.body.style.overflow = "";
});

describe("useFocusTrap", () => {
  it("mueve el foco al primer control al activarse y bloquea el desplazamiento del body", async () => {
    const user = userEvent.setup();
    render(<Harness />);

    await user.click(screen.getByRole("button", { name: "Abrir" }));

    expect(screen.getByRole("button", { name: "Panel primero" })).toHaveFocus();
    expect(document.body.style.overflow).toBe("hidden");
  });

  it("cicla Tab y Mayús+Tab dentro del contenedor", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Abrir" }));

    await user.tab();
    await user.tab();
    expect(screen.getByRole("button", { name: "Panel último" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Panel primero" })).toHaveFocus();
    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Panel último" })).toHaveFocus();
  });

  it("si el foco quedó fuera, Tab lo devuelve al contenedor", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Abrir" }));

    screen.getByRole("button", { name: "Fuera" }).focus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Panel primero" })).toHaveFocus();

    screen.getByRole("button", { name: "Fuera" }).focus();
    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Panel último" })).toHaveFocus();
  });

  it("Escape llama a onEscape y al cerrar devuelve el foco al que abrió", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Abrir" }));

    await user.keyboard("{Escape}");

    expect(screen.queryByTestId("Panel")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Abrir" })).toHaveFocus();
    expect(document.body.style.overflow).toBe("");
  });

  it("con trampas anidadas solo la de arriba responde a Tab y Escape", async () => {
    const user = userEvent.setup();
    const panelEscape = vi.fn();
    render(<Harness nested onEscape={panelEscape} />);
    await user.click(screen.getByRole("button", { name: "Abrir" }));
    await user.click(screen.getByRole("button", { name: "Abrir interno" }));

    expect(screen.getByRole("textbox", { name: "Modal campo" })).toHaveFocus();
    await user.tab();
    await user.tab();
    expect(screen.getByRole("button", { name: "Modal primero" })).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(panelEscape).not.toHaveBeenCalled();
    expect(screen.queryByTestId("Modal")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Abrir interno" })).toHaveFocus();
    expect(document.body.style.overflow).toBe("hidden");

    await user.keyboard("{Escape}");
    expect(panelEscape).toHaveBeenCalledTimes(1);
  });

  it("sin controles enfoca el propio contenedor y Tab no se escapa", async () => {
    const user = userEvent.setup();
    render(<EmptyTrap />);
    const box = screen.getByLabelText("Vacío");

    expect(box).toHaveFocus();
    await user.tab();
    expect(box).toHaveFocus();
  });

  it("con el foco en el propio contenedor, Tab y Mayús+Tab no se escapan", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Abrir" }));
    const panel = screen.getByTestId("Panel");
    panel.tabIndex = -1;

    panel.focus();
    await user.tab({ shift: true });
    expect(screen.getByRole("button", { name: "Panel último" })).toHaveFocus();
    panel.focus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Panel primero" })).toHaveFocus();
  });

  it("inactiva no toca el foco ni el body", () => {
    render(<Inactive />);

    expect(screen.getByRole("button", { name: "Dentro inactivo" })).not.toHaveFocus();
    expect(document.body.style.overflow).toBe("");
  });

  it("ignora teclas que no son Tab ni Escape", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    await user.click(screen.getByRole("button", { name: "Abrir" }));

    await user.keyboard("a");

    expect(screen.getByRole("button", { name: "Panel primero" })).toHaveFocus();
  });
});
