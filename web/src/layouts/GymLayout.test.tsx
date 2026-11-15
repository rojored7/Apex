// US-062 T3 y T6: tablet del box en oscuro forzado, controles de 56 px y barra mínima.
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { useGym } from "../shared/hooks/gymContext";
import { MemoryRouter } from "react-router";
import { readFileSync } from "node:fs";
import { setViewportWidth } from "../test/server";
import { GymLayout, type TabletOptions } from "./GymLayout";

const css = readFileSync("src/layouts/GymLayout.module.css", "utf8");

function renderGym() {
  return render(
    <MemoryRouter>
      <GymLayout title="Check-in · 17:00 · Coach María" subtitle="Martes 20 de octubre" exitTo="/clases" exitLabel="Clases">
        <button type="button">Llegó</button>
      </GymLayout>
    </MemoryRouter>,
  );
}

afterEach(() => {
  delete document.documentElement.dataset.theme;
  vi.unstubAllGlobals();
});

describe("GymLayout", () => {
  it("fuerza el tema oscuro aunque el sistema prefiera claro y lo restaura al desmontar", () => {
    setViewportWidth(1024);
    document.documentElement.dataset.theme = "light";
    const { unmount } = renderGym();

    expect(document.documentElement.dataset.theme).toBe("dark");
    unmount();
    expect(document.documentElement.dataset.theme).toBe("light");
  });

  it("sin tema previo, al desmontar quita el atributo", () => {
    const { unmount } = renderGym();
    unmount();

    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("barra mínima con el nombre de la sesión, subtítulo y salida; sin menú lateral", () => {
    renderGym();
    const banner = screen.getByRole("banner");

    expect(within(banner).getByRole("heading", { level: 1, name: "Check-in · 17:00 · Coach María" })).toBeInTheDocument();
    expect(within(banner).getByText("Martes 20 de octubre")).toBeInTheDocument();
    expect(within(banner).getByRole("link", { name: "Clases" })).toHaveAttribute("href", "/clases");
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
    expect(within(screen.getByRole("main")).getByRole("button", { name: "Llegó" })).toBeInTheDocument();
  });

  it("la salida dice Salir por defecto", () => {
    render(
      <MemoryRouter>
        <GymLayout title="Resultados" exitTo="/" />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Salir" })).toBeInTheDocument();
  });

  it("los controles del contenedor miden --control-gym (56 px) sin variantes nuevas", () => {
    const root = /\.root\s*\{[^}]*\}/.exec(css)?.[0] ?? "";
    const exit = /\.exit\s*\{[^}]*\}/.exec(css)?.[0] ?? "";

    expect(root).toMatch(/--control:\s*var\(--control-gym\)/);
    expect(exit).toMatch(/min-height:\s*var\(--control-gym\)/);
    expect(css).toMatch(/:focus-visible[^{]*\{[^}]*outline:[^;]*var\(--(blue-deep|apex-blue)\)/);
  });
});

// S7-F4 · S7-D24 (H-2): modo tablet. Sin enlaces al panel, cierre a los 10 minutos de inactividad y salida con contraseña.
function renderTablet(overrides: Partial<TabletOptions> = {}, children?: ReactNode) {
  const tablet: TabletOptions = { verifyPassword: vi.fn(() => Promise.resolve(null)), onLeave: vi.fn(), onIdle: vi.fn(), ...overrides };
  render(
    <MemoryRouter>
      <GymLayout title="Check-in" exitTo="/clases" exitLabel="Clases" tablet={tablet}>
        {children ?? <button type="button">Llegó</button>}
      </GymLayout>
    </MemoryRouter>,
  );
  return tablet;
}

function Vender() {
  const { requestLeave } = useGym();
  return (
    <button
      type="button"
      onClick={() => {
        requestLeave("/membresias/vender?socio=m1");
      }}
    >
      Vender
    </button>
  );
}

describe("GymLayout · modo tablet", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("sin_enlaces_al_panel: la salida es un botón y no hay ningún enlace", () => {
    renderTablet();

    expect(screen.queryAllByRole("link")).toHaveLength(0);
    expect(screen.getByRole("button", { name: "Clases" })).toBeInTheDocument();
  });

  it("fuera del modo tablet la salida sigue siendo un enlace", () => {
    renderGym();
    expect(screen.getByRole("link", { name: "Clases" })).toBeInTheDocument();
  });

  it("salir_exige_contrasena: pide la contraseña, la verifica y solo entonces sale", async () => {
    const user = userEvent.setup();
    const verifyPassword = vi.fn((password: string) => Promise.resolve(password === "buena" ? null : "Contraseña incorrecta. Escríbela de nuevo."));
    const tablet = renderTablet({ verifyPassword });

    await user.click(screen.getByRole("button", { name: "Clases" }));
    const dialog = screen.getByRole("dialog", { name: "¿Salir del modo tablet?" });
    expect(tablet.onLeave).not.toHaveBeenCalled();
    await user.type(within(dialog).getByLabelText(/Contraseña/), "mala");
    await user.click(within(dialog).getByRole("button", { name: "Salir del modo tablet" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Contraseña incorrecta. Escríbela de nuevo.");
    expect(tablet.onLeave).not.toHaveBeenCalled();
    await user.clear(within(dialog).getByLabelText(/Contraseña/));
    await user.type(within(dialog).getByLabelText(/Contraseña/), "buena");
    await user.click(within(dialog).getByRole("button", { name: "Salir del modo tablet" }));

    await waitFor(() => { expect(tablet.onLeave).toHaveBeenCalledWith("/clases"); });
  });

  it("una acción que sale del modo (Vender) pide la contraseña y sale a su destino", async () => {
    const user = userEvent.setup();
    const tablet = renderTablet({}, <Vender />);

    await user.click(screen.getByRole("button", { name: "Vender" }));
    await user.type(screen.getByLabelText(/Contraseña/), "buena");
    await user.click(screen.getByRole("button", { name: "Salir del modo tablet" }));

    await waitFor(() => { expect(tablet.onLeave).toHaveBeenCalledWith("/membresias/vender?socio=m1"); });
  });

  it("Volver cierra el diálogo y sigue en modo tablet", async () => {
    const user = userEvent.setup();
    const tablet = renderTablet();
    await user.click(screen.getByRole("button", { name: "Clases" }));
    await user.click(screen.getByRole("button", { name: "Volver" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(tablet.onLeave).not.toHaveBeenCalled();
  });

  it("cierre_por_inactividad: a los 10 minutos sin tocar nada llama onIdle; tocar reinicia la cuenta", () => {
    vi.useFakeTimers();
    const tablet = renderTablet();

    vi.advanceTimersByTime(9 * 60_000);
    fireEvent.pointerDown(document.body);
    vi.advanceTimersByTime(9 * 60_000);
    expect(tablet.onIdle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(60_000);
    expect(tablet.onIdle).toHaveBeenCalledTimes(1);
  });

  it("fuera del modo tablet no hay cierre por inactividad", () => {
    vi.useFakeTimers();
    renderGym();
    vi.advanceTimersByTime(60 * 60_000);
    expect(screen.getByRole("main")).toBeInTheDocument();
  });

  it("el contador de llegadas se pinta en la barra", () => {
    render(
      <MemoryRouter>
        <GymLayout title="Check-in" exitTo="/clases" counter={{ value: 3, of: 12, label: "llegaron" }} />
      </MemoryRouter>,
    );

    expect(screen.getByLabelText("Llegaron 3 de 12")).toHaveTextContent("3 / 12 llegaron");
  });
});
