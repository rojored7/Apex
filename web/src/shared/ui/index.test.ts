import * as ui from "./index";

describe("kit compartido src/shared/ui", () => {
  it("exporta los componentes base y las funciones de estado", () => {
    expect(typeof ui.Button).toBe("function");
    expect(typeof ui.StatusTag).toBe("function");
    expect(ui.Field).toBeDefined();
    expect(ui.statusLabel("active")).toBe("Al día");
    expect(ui.statusTone("expired")).toBe("danger");
    expect(ui.cx("a", false, "b")).toBe("a b");
  });

  it("exporta los componentes del Sprint 1", () => {
    for (const component of [
      ui.PageHeader,
      ui.Tabs,
      ui.KpiCard,
      ui.SidePanel,
      ui.ConfirmModal,
      ui.DataTable,
      ui.Pagination,
      ui.FilterBar,
      ui.Chips,
      ui.MaskedValue,
      ui.HistoryAside,
    ]) {
      expect(typeof component).toBe("function");
    }
  });

  it("exporta la barra superior y el menú lateral del Sprint 2 (US-061)", () => {
    expect(typeof ui.TopBar).toBe("function");
    expect(typeof ui.SideNav).toBe("function");
  });

  it("exporta el diálogo de contenido de S2-F4b", () => {
    expect(typeof ui.Modal).toBe("function");
  });
});
