// US-067 T1: features por versión e isRouteEnabled.
import { ENABLED_FEATURES, FEATURES, isRouteEnabled } from "./features";
import { ROUTE_TABLE } from "./routeTable";

describe("features", () => {
  it("declara las 17 features y ninguna repetida", () => {
    expect(FEATURES).toHaveLength(17);
    expect(new Set(FEATURES).size).toBe(17);
  });

  it("habilita doce: las once anteriores y classes (S7-F2)", () => {
    expect([...ENABLED_FEATURES].sort()).toEqual(["audit", "auth", "classes", "crypto", "dashboard", "members", "memberships", "notifications", "payments", "plans", "settings", "users"]);
    expect(ENABLED_FEATURES.size).toBe(12);
    expect(ENABLED_FEATURES.has("wods")).toBe(false);
  });

  it("/sistema/llaves tiene pantalla (load) y solo el admin la ve en el menú Sistema", () => {
    const route = ROUTE_TABLE.find((r) => r.path === "/sistema/llaves");
    expect(route?.feature).toBe("crypto");
    expect(route?.load).toBeTypeOf("function");
    expect(isRouteEnabled({ feature: "crypto" }, ENABLED_FEATURES)).toBe(true);
  });

  it("una ruta con feature habilitada está habilitada", () => {
    expect(isRouteEnabled({ feature: "members" }, ENABLED_FEATURES)).toBe(true);
  });

  it("una ruta de una feature futura (wods) está deshabilitada", () => {
    expect(isRouteEnabled({ feature: "wods" }, ENABLED_FEATURES)).toBe(false);
  });

  it("una ruta sin feature siempre está habilitada", () => {
    expect(isRouteEnabled({}, new Set())).toBe(true);
    expect(isRouteEnabled({ feature: undefined }, new Set())).toBe(true);
  });
});
