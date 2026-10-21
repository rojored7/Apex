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
});
