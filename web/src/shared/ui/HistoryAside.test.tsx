// US-066 T5 y T7: historial del registro. Criterio diferido: la feature lo conecta a
// GET /members/{id}/audit en US-106 (S4A-F2: frase, propósito, "Cargar más" y pie con el enlace).
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ApiError } from "../../core/api/errors";
import { SYSTEM_USER_ID, type AuditEntryView } from "../lib/audit-labels";
import { HistoryAside } from "./HistoryAside";

const ENTRIES: AuditEntryView[] = [
  {
    id: "a1",
    at: "2026-10-21T02:30:00Z",
    actor_id: "u1",
    actor_name: "Ana P.",
    entity: "members",
    action: "update",
    before: { phone: "apx1.k1.A256GCM.bm9uY2U.YQ" },
    after: { phone: "apx1.k1.A256GCM.b3Rybw.Yg" },
  },
  {
    id: "a2",
    at: "2026-10-20T12:00:00Z",
    actor_id: SYSTEM_USER_ID,
    actor_name: "system@apex.local",
    entity: "memberships",
    action: "update",
    before: { status: "active" },
    after: { status: "expired" },
  },
  {
    id: "a3",
    at: "2026-10-02T15:00:00Z",
    actor_id: "u2",
    actor_name: "Carlos",
    entity: "payments",
    action: "insert",
    before: null,
    after: { amount_cop: 120000, method: "nequi" },
  },
];

const noop = () => undefined;

describe("HistoryAside", () => {
  it("es un aside Historial con fecha de Bogotá, usuario, entidad, acción y resumen", () => {
    render(<HistoryAside entries={ENTRIES} total={3} onLoadMore={noop} />);

    const aside = screen.getByRole("complementary", { name: "Historial" });
    const items = within(aside).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    const first = items[0] as HTMLElement;
    expect(first).toHaveTextContent("Socio · modificó");
    expect(first).toHaveTextContent("Teléfono: dato cifrado modificado");
    expect(first).toHaveTextContent("Ana P. · 20 oct 2026, 9:30 p. m.");
    expect(within(first).getByText("20 oct 2026, 9:30 p. m.").tagName).toBe("TIME");
    expect(aside).not.toHaveTextContent("apx1.");
  });

  it("el usuario técnico aparece como Sistema y cada entrada lleva su entidad (N-31)", () => {
    render(<HistoryAside entries={ENTRIES} total={3} onLoadMore={noop} />);
    const items = screen.getAllByRole("listitem");

    expect(items[1]).toHaveTextContent("Membresía · modificó");
    expect(items[1]).toHaveTextContent("Sistema ·");
    expect(items[1]).not.toHaveTextContent("system@apex.local");
    expect(items[2]).toHaveTextContent("Pago · creó");
    expect(items[2]).toHaveTextContent("Monto: $ 120.000");
  });

  it("Ver más pide el siguiente offset mientras haya más", async () => {
    const onLoadMore = vi.fn();
    render(<HistoryAside entries={ENTRIES} total={10} onLoadMore={onLoadMore} />);

    await userEvent.click(screen.getByRole("button", { name: "Ver más" }));

    expect(onLoadMore).toHaveBeenCalledWith(3);
  });

  it("sin más entradas no muestra Ver más; cargando más lo marca ocupado", () => {
    const { rerender } = render(<HistoryAside entries={ENTRIES} total={3} onLoadMore={noop} />);
    expect(screen.queryByRole("button", { name: "Ver más" })).not.toBeInTheDocument();

    rerender(<HistoryAside entries={ENTRIES} total={10} onLoadMore={noop} isLoading />);
    expect(screen.getByRole("button", { name: "Ver más" })).toHaveAttribute("aria-busy", "true");
  });

  it("vacío dice Sin cambios registrados", () => {
    render(<HistoryAside entries={[]} total={0} onLoadMore={noop} />);

    expect(screen.getByText("Sin cambios registrados")).toBeInTheDocument();
  });

  it("cargando por primera vez lo anuncia", () => {
    render(<HistoryAside entries={[]} total={0} onLoadMore={noop} isLoading />);

    expect(screen.getByRole("complementary", { name: "Historial" })).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Cargando historial")).toBeInTheDocument();
    expect(screen.queryByText("Sin cambios registrados")).not.toBeInTheDocument();
  });

  it("con error muestra el mensaje y Reintentar", async () => {
    const onRetry = vi.fn();
    render(
      <HistoryAside
        entries={[]}
        total={0}
        onLoadMore={noop}
        error={new ApiError({ status: 500, code: "internal_error", message: "Error interno" })}
        onRetry={onRetry}
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Error interno");
    await userEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("un error que no es del api da un mensaje genérico", () => {
    render(<HistoryAside entries={[]} total={0} onLoadMore={noop} error={new Error("x")} />);

    expect(screen.getByRole("alert")).toHaveTextContent("No se pudo cargar el historial. Intenta de nuevo.");
  });

  it("una entrada sin resumen solo muestra entidad, acción, usuario y fecha", () => {
    render(
      <HistoryAside
        entries={[{ id: "z", at: "2026-10-20T15:00:00Z", actor_id: "u1", actor_name: "Ana P.", entity: "members", action: "delete", before: { first_name: "x" }, after: null }]}
        total={1}
        onLoadMore={noop}
      />,
    );

    expect(screen.getByRole("listitem")).toHaveTextContent("Socio · eliminóAna P. · 20 oct 2026, 10:00 a. m.");
  });
});

describe("HistoryAside · S4A-F2 (frase, propósito, botón y pie)", () => {
  const phrased: AuditEntryView = {
    id: "p1",
    at: "2026-10-21T02:30:00Z",
    actor_id: "u1",
    actor_name: "ana",
    entity: "members.members",
    action: "update",
    fields: ["phone", "email"],
    phrase: "ana editó teléfono y correo",
  };

  it("pinta la frase como línea fuerte y la entidad con la fecha debajo, sin repetir el resumen", () => {
    render(<HistoryAside entries={[phrased]} total={1} onLoadMore={noop} />);
    const item = screen.getByRole("listitem");

    expect(within(item).getByText("ana editó teléfono y correo").tagName).toBe("B");
    expect(item).toHaveTextContent("Socio · 20 oct 2026, 9:30 p. m.");
    expect(item).not.toHaveTextContent("Cambió:");
    expect(item).not.toHaveTextContent("Socio · modificó");
  });

  it("una entrada con propósito lleva la etiqueta 'automático (aviso)'; sin propósito no", () => {
    render(
      <HistoryAside
        entries={[
          { ...phrased, id: "p2", action: "reveal", fields: ["phone"], phrase: "Sistema mostró el teléfono", purpose: "notify" },
          { ...phrased, id: "p3", purpose: null },
        ]}
        total={2}
        onLoadMore={noop}
      />,
    );
    const [auto, manual] = screen.getAllByRole("listitem") as [HTMLElement, HTMLElement];

    expect(auto).toHaveTextContent("Sistema mostró el teléfono");
    expect(within(auto).getByText("automático (aviso)")).toBeInTheDocument();
    expect(manual).not.toHaveTextContent("automático (aviso)");
  });

  it("una frase con HTML se ve literal (sin innerHTML)", () => {
    render(<HistoryAside entries={[{ ...phrased, phrase: "<b>ana</b> editó <img src=x onerror=alert(1)>" }]} total={1} onLoadMore={noop} />);
    const item = screen.getByRole("listitem");

    expect(item).toHaveTextContent("<b>ana</b> editó <img src=x onerror=alert(1)>");
    expect(item.querySelector("img")).toBeNull();
    expect(item.querySelectorAll("b")).toHaveLength(1);
  });

  it("moreLabel cambia el texto del botón de la página siguiente", async () => {
    const onLoadMore = vi.fn();
    render(<HistoryAside entries={ENTRIES} total={10} onLoadMore={onLoadMore} moreLabel="Cargar más" />);

    await userEvent.click(screen.getByRole("button", { name: "Cargar más" }));

    expect(onLoadMore).toHaveBeenCalledWith(3);
    expect(screen.queryByRole("button", { name: "Ver más" })).not.toBeInTheDocument();
  });

  it("footer se pinta al final del aside", () => {
    render(<HistoryAside entries={ENTRIES} total={3} onLoadMore={noop} footer={<a href="/socios/x/historial">Ver historial completo →</a>} />);

    const aside = screen.getByRole("complementary", { name: "Historial" });
    expect(within(aside).getByRole("link", { name: "Ver historial completo →" })).toHaveAttribute("href", "/socios/x/historial");
  });
});
