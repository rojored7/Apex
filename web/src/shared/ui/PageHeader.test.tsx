// US-064 T1 y T4: encabezado de página con migas, un solo h1, total y acciones.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { PageHeader, type PageAction } from "./PageHeader";
import { StatusTag } from "./StatusTag";

function renderHeader(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

const four: PageAction[] = [
  { id: "renew", label: "Renovar", variant: "primary", href: "/membresias/vender" },
  { id: "pay", label: "Registrar pago", onClick: vi.fn() },
  { id: "edit", label: "Editar", href: "/socios/1/editar" },
  { id: "drop", label: "Dar de baja", tone: "danger", onClick: vi.fn() },
];

describe("PageHeader", () => {
  it("tiene un único h1 con el título y el total junto al título", () => {
    renderHeader(<PageHeader title="Socios" total="342 en total · 269 con membresía" />);

    const headings = screen.getAllByRole("heading", { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0]).toHaveTextContent("Socios");
    expect(screen.getByText("342 en total · 269 con membresía")).toBeInTheDocument();
  });

  it("muestra migas con enlaces y la página actual marcada", () => {
    renderHeader(
      <PageHeader title="Laura Gómez" breadcrumbs={[{ label: "Socios", href: "/socios" }, { label: "Laura Gómez" }]} />,
    );

    const nav = screen.getByRole("navigation", { name: "Migas" });
    expect(within(nav).getByRole("link", { name: "Socios" })).toHaveAttribute("href", "/socios");
    expect(within(nav).getByText("Laura Gómez")).toHaveAttribute("aria-current", "page");
  });

  it("muestra la insignia y la descripción", () => {
    renderHeader(<PageHeader title="Laura Gómez" badge={<StatusTag status="active" />} description="Socia desde 12 mar 2026" />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Al día");
    expect(screen.getByText("Socia desde 12 mar 2026")).toBeInTheDocument();
  });

  it("con cuatro acciones deja tres visibles y la cuarta en Más acciones", async () => {
    const user = userEvent.setup();
    renderHeader(<PageHeader title="Laura Gómez" actions={four} />);

    expect(screen.getByRole("link", { name: "Renovar" })).toHaveAttribute("href", "/membresias/vender");
    expect(screen.getByRole("button", { name: "Registrar pago" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Editar" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Dar de baja" })).not.toBeInTheDocument();

    const more = screen.getByRole("button", { name: "Más acciones" });
    expect(more).toHaveAttribute("aria-expanded", "false");
    await user.click(more);

    expect(more).toHaveAttribute("aria-expanded", "true");
    const item = screen.getByRole("menuitem", { name: "Dar de baja" });
    expect(item).toHaveFocus();
    await user.click(item);
    expect(four[3]?.onClick).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(more).toHaveFocus();
  });

  it("sin acciones sobrantes no muestra Más acciones", () => {
    renderHeader(<PageHeader title="Pagos" actions={four.slice(0, 3)} />);

    expect(screen.queryByRole("button", { name: "Más acciones" })).not.toBeInTheDocument();
  });

  it("las acciones siguen al título en el orden de tabulación", async () => {
    const user = userEvent.setup();
    renderHeader(
      <PageHeader title="Laura Gómez" breadcrumbs={[{ label: "Socios", href: "/socios" }, { label: "Laura" }]} actions={four} />,
    );

    await user.tab();
    expect(screen.getByRole("link", { name: "Socios" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("link", { name: "Renovar" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Registrar pago" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("link", { name: "Editar" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Más acciones" })).toHaveFocus();
  });

  it("el menú se navega con flechas, Inicio y Fin, y Escape lo cierra", async () => {
    const user = userEvent.setup();
    const extra: PageAction[] = [
      ...four,
      { id: "wa", label: "Enviar WhatsApp", onClick: vi.fn() },
      { id: "portal", label: "Reenviar acceso", href: "/socios/1/portal" },
    ];
    renderHeader(<PageHeader title="Laura" actions={extra} />);
    const more = screen.getByRole("button", { name: "Más acciones" });

    await user.click(more);
    const items = screen.getAllByRole("menuitem");
    expect(items.map((i) => i.textContent)).toEqual(["Dar de baja", "Enviar WhatsApp", "Reenviar acceso"]);
    await user.keyboard("{ArrowDown}");
    expect(items[1]).toHaveFocus();
    await user.keyboard("{ArrowDown}{ArrowDown}");
    expect(items[0]).toHaveFocus();
    await user.keyboard("{ArrowUp}");
    expect(items[2]).toHaveFocus();
    await user.keyboard("{Home}");
    expect(items[0]).toHaveFocus();
    await user.keyboard("{End}");
    expect(items[2]).toHaveFocus();
    expect(items[2]).toHaveAttribute("href", "/socios/1/portal");

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(more).toHaveFocus();
  });

  it("cierra el menú al hacer clic fuera o al volver a pulsar el botón", async () => {
    const user = userEvent.setup();
    renderHeader(<PageHeader title="Laura" actions={four} />);
    const more = screen.getByRole("button", { name: "Más acciones" });

    await user.click(more);
    await user.click(screen.getByRole("heading", { level: 1 }));
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();

    await user.click(more);
    await user.click(more);
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });

  it("una acción deshabilitada no responde", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    renderHeader(<PageHeader title="X" actions={[{ id: "a", label: "Exportar", onClick, disabled: true }]} />);

    await user.click(screen.getByRole("button", { name: "Exportar" }));

    expect(onClick).not.toHaveBeenCalled();
  });
});
