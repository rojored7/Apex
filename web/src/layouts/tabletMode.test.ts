// S8-F4 · S8-D27: el modo tablet cubre dos rutas de la clase: el check-in y el registro de resultados.
import { isTabletSession, TABLET_PATH } from "./tabletMode";
import { testUser } from "../test/session";

describe("TABLET_PATH", () => {
  it.each(["/clases/abc/checkin", "/clases/abc/checkin/", "/clases/abc/resultados", "/clases/abc/resultados/"])("reconoce %s", (path) => {
    expect(TABLET_PATH.test(path)).toBe(true);
  });

  it.each(["/clases/abc", "/clases/abc/otra", "/clases/abc/resultados/x", "/wods/abc/resultados", "/clases/checkin"])("no reconoce %s", (path) => {
    expect(TABLET_PATH.test(path)).toBe(false);
  });
});

describe("isTabletSession", () => {
  it("rige mientras la sesión traiga la marca del servidor", () => {
    expect(isTabletSession(testUser("coach", { kioskPath: "/clases/abc/resultados" }))).toBe(true);
    expect(isTabletSession(testUser("coach"))).toBe(false);
    expect(isTabletSession(null)).toBe(false);
  });
});
