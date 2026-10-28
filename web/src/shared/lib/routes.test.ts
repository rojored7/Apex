// Fase 4 del Sprint 3 (M4): las rutas del panel y sus enlaces viven en un solo lugar; las features
// los reexportan (ninguna importa de otra, S3-D65).
import { MEMBERS_PATH, MEMBERSHIPS_PATH, memberHref, NEW_MEMBER_PATH, PAYMENTS_PATH, PLANS_PATH, renewHref, SELL_PATH, sellHref } from "./routes";

const ID = "3f2b1c9e-4a5d-4e6f-8a7b-9c0d1e2f3a4b";

describe("rutas del panel", () => {
  it("fija las rutas que enlazan las pantallas", () => {
    expect([MEMBERS_PATH, NEW_MEMBER_PATH, MEMBERSHIPS_PATH, SELL_PATH, PLANS_PATH, PAYMENTS_PATH]).toEqual(["/socios", "/socios/nuevo", "/membresias", "/membresias/vender", "/planes", "/pagos"]);
  });

  it("memberHref lleva a la ficha y escapa el id", () => {
    expect(memberHref(ID)).toBe(`/socios/${ID}`);
    expect(memberHref("a/b?c")).toBe("/socios/a%2Fb%3Fc");
  });

  it("sellHref fija el socio y renewHref además renueva", () => {
    expect(sellHref(ID)).toBe(`/membresias/vender?socio=${ID}`);
    expect(renewHref(ID)).toBe(`/membresias/vender?socio=${ID}&renovar=1`);
    expect(sellHref("a&b")).toBe("/membresias/vender?socio=a%26b");
  });
});
