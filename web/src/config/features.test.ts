// US-067 T1: features por versión e isRouteEnabled.
import { ENABLED_FEATURES, FEATURES, isRouteEnabled } from "./features";

describe("features", () => {
  it("declara las 17 features y ninguna repetida", () => {
    expect(FEATURES).toHaveLength(17);
    expect(new Set(FEATURES).size).toBe(17);
  });

  it("habilita ocho: las seis del Sprint 2, memberships (S3-F3) y payments (S3-F4, D36)", () => {
    expect([...ENABLED_FEATURES].sort()).toEqual(["auth", "dashboard", "members", "memberships", "payments", "plans", "settings", "users"]);
    expect(ENABLED_FEATURES.size).toBe(8);
    expect(ENABLED_FEATURES.has("classes")).toBe(false);
  });

  it("una ruta con feature habilitada está habilitada", () => {
    expect(isRouteEnabled({ feature: "members" }, ENABLED_FEATURES)).toBe(true);
  });

  it("una ruta de una feature futura (classes) está deshabilitada", () => {
    expect(isRouteEnabled({ feature: "classes" }, ENABLED_FEATURES)).toBe(false);
  });

  it("una ruta sin feature siempre está habilitada", () => {
    expect(isRouteEnabled({}, new Set())).toBe(true);
    expect(isRouteEnabled({ feature: undefined }, new Set())).toBe(true);
  });
});
