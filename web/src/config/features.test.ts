// US-067 T1: features por versión e isRouteEnabled.
import { ENABLED_FEATURES, FEATURES, isRouteEnabled } from "./features";
import { ROUTE_TABLE } from "./routeTable";

describe("features", () => {
  it("declara las 17 features y ninguna repetida", () => {
    expect(FEATURES).toHaveLength(17);
    expect(new Set(FEATURES).size).toBe(17);
  });

  it("habilita dieciséis: las quince anteriores y athletes (S9-F1)", () => {
    expect([...ENABLED_FEATURES].sort()).toEqual(["athletes", "audit", "auth", "classes", "crypto", "dashboard", "members", "memberships", "notifications", "payments", "plans", "results", "settings", "tv", "users", "wods"]);
    expect(ENABLED_FEATURES.size).toBe(16);
    expect(ENABLED_FEATURES.has("athletes")).toBe(true);
    expect(ENABLED_FEATURES.has("tv")).toBe(true);
    expect(ENABLED_FEATURES.has("wods")).toBe(true);
    expect(ENABLED_FEATURES.has("results")).toBe(true);
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

  it("una ruta de una feature futura (portal) está deshabilitada y la de athletes ya no (S9-F1)", () => {
    expect(isRouteEnabled({ feature: "portal" }, ENABLED_FEATURES)).toBe(false);
    expect(isRouteEnabled({ feature: "athletes" }, ENABLED_FEATURES)).toBe(true);
  });

  it("S9-F1: la pestaña Atleta es hija de la ficha con página (load), feature athletes y athletes.view", () => {
    const route = ROUTE_TABLE.find((r) => r.path === "/socios/:id/atleta");

    expect(route).toMatchObject({ parent: "/socios/:id", feature: "athletes", access: "athletes.view", layout: "panel" });
    expect(route?.load).toBeTypeOf("function");
  });

  it("una ruta sin feature siempre está habilitada", () => {
    expect(isRouteEnabled({}, new Set())).toBe(true);
    expect(isRouteEnabled({ feature: undefined }, new Set())).toBe(true);
  });
});
