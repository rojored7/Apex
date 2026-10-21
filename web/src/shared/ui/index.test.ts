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
});
