// US-061 T4: barra superior negra con logo, gimnasio, fecha y hora de Bogotá, usuario y
// menú de usuario accesible.
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TopBar } from "./TopBar";

const USER = { email: "ana@apex.test", roleLabel: "Admin" };

describe("TopBar", () => {
  it("es un banner con el logo de fondo oscuro, el gimnasio por defecto y el usuario", () => {
    render(<TopBar user={USER} />);
    const banner = screen.getByRole("banner");

    expect(within(banner).getByRole("img", { name: "APEX Hybrid Training" })).toHaveAttribute(
      "src",
      "/brand/apex-logo-dark-bg.png",
    );
    expect(within(banner).getByText("APEX")).toBeInTheDocument();
    expect(within(banner).getByText("ana@apex.test · Admin")).toBeInTheDocument();
  });

  it("muestra el nombre del gimnasio recibido", () => {
    render(<TopBar user={USER} gymName="CrossFit Chapinero" />);

    expect(screen.getByText("CrossFit Chapinero")).toBeInTheDocument();
  });

  it("muestra fecha y hora de Bogotá y la actualiza cada minuto", () => {
    // Solo reloj e intervalos: la prueba no usa user-event ni findBy*.
    vi.useFakeTimers({ toFake: ["setInterval", "clearInterval", "Date"] });
    vi.setSystemTime(new Date("2026-10-21T02:30:00Z"));
    try {
      render(<TopBar user={USER} />);
      const time = screen.getByText(/20 oct 2026, 9:30 p\. m\./);
      expect(time.tagName).toBe("TIME");
      expect(time).toHaveAttribute("dateTime", "2026-10-21T02:30:00.000Z");

      act(() => {
        vi.advanceTimersByTime(60_000);
      });
      expect(screen.getByText(/20 oct 2026, 9:31 p\. m\./)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("el menú de usuario abre Mi cuenta y Cerrar sesión con teclado", async () => {
    const user = userEvent.setup();
    const onChangePassword = vi.fn();
    const onLogout = vi.fn();
    render(<TopBar user={USER} onChangePassword={onChangePassword} onLogout={onLogout} />);
    const trigger = screen.getByRole("button", { name: /ana@apex\.test/ });

    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const menu = screen.getByRole("menu");
    expect(within(menu).getByRole("menuitem", { name: "Mi cuenta" })).toHaveFocus();

    await user.keyboard("{ArrowDown}");
    expect(within(menu).getByRole("menuitem", { name: "Cerrar sesión" })).toHaveFocus();
    await user.keyboard("{ArrowDown}");
    expect(within(menu).getByRole("menuitem", { name: "Mi cuenta" })).toHaveFocus();
    await user.keyboard("{ArrowUp}");
    expect(within(menu).getByRole("menuitem", { name: "Cerrar sesión" })).toHaveFocus();
    await user.keyboard("{Enter}");

    expect(onLogout).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("Escape y el clic fuera cierran el menú", async () => {
    const user = userEvent.setup();
    const onChangePassword = vi.fn();
    render(
      <>
        <TopBar user={USER} onChangePassword={onChangePassword} onLogout={vi.fn()} />
        <p>Fuera</p>
      </>,
    );
    const trigger = screen.getByRole("button", { name: /ana@apex\.test/ });

    await user.click(trigger);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();

    await user.click(trigger);
    await user.click(screen.getByText("Fuera"));
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();

    await user.click(trigger);
    await user.click(screen.getByRole("menuitem", { name: "Mi cuenta" }));
    expect(onChangePassword).toHaveBeenCalledTimes(1);
  });

  it("Cerrar sesión queda deshabilitado mientras dura la petición", async () => {
    const user = userEvent.setup();
    const onLogout = vi.fn();
    render(<TopBar user={USER} onLogout={onLogout} logoutPending />);

    await user.click(screen.getByRole("button", { name: /ana@apex\.test/ }));
    const item = screen.getByRole("menuitem", { name: "Cerrando sesión…" });
    expect(item).toHaveAttribute("aria-disabled", "true");
    await user.click(item);
    expect(onLogout).not.toHaveBeenCalled();
  });

  it("sin acciones el usuario se muestra sin menú; sin usuario no hay menú", () => {
    const { rerender } = render(<TopBar user={USER} />);
    expect(screen.queryByRole("button", { name: /ana@apex\.test/ })).not.toBeInTheDocument();
    expect(screen.getByText("ana@apex.test · Admin")).toBeInTheDocument();

    rerender(<TopBar user={null} onLogout={vi.fn()} />);
    expect(screen.queryByText(/@/)).not.toBeInTheDocument();
  });

  it("pinta la ranura del conmutador de tema", () => {
    render(<TopBar user={USER} themeToggle={<button type="button">Tema</button>} />);

    expect(screen.getByRole("button", { name: "Tema" })).toBeInTheDocument();
  });

  it("el botón de menú (celular) declara qué controla y si está abierto", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<TopBar user={USER} navButton={{ expanded: false, controls: "menu-principal", onClick }} />);
    const button = screen.getByRole("button", { name: "Abrir menú" });

    expect(button).toHaveAttribute("aria-controls", "menu-principal");
    expect(button).toHaveAttribute("aria-expanded", "false");
    await user.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("sin navButton no hay botón de menú", () => {
    render(<TopBar user={USER} />);

    expect(screen.queryByRole("button", { name: "Abrir menú" })).not.toBeInTheDocument();
  });
});
