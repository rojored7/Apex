// @vitest-environment node
// US-059 T1: armado del query string y parámetros de lista (regla de datos 6, D2).
import { DEFAULT_LIMIT, MAX_LIMIT, clampLimit, listParams, toQueryString } from "./query";

describe("toQueryString", () => {
  it("omite undefined y null y repite los arreglos", () => {
    expect(toQueryString({ q: "pérez", status: ["active", "expired"], plan: undefined, from: null, limit: 25 })).toBe(
      "q=p%C3%A9rez&status=active&status=expired&limit=25",
    );
  });

  it("convierte booleanos y números a texto", () => {
    expect(toQueryString({ renew: true, offset: 0 })).toBe("renew=true&offset=0");
  });

  it("devuelve cadena vacía sin parámetros", () => {
    expect(toQueryString({})).toBe("");
    expect(toQueryString({ a: undefined })).toBe("");
  });

  it("codifica caracteres reservados", () => {
    expect(toQueryString({ q: "a&b=c d" })).toBe("q=a%26b%3Dc%20d");
  });
});

describe("listParams", () => {
  it("expone los límites del contrato", () => {
    expect(MAX_LIMIT).toBe(200);
    expect(DEFAULT_LIMIT).toBe(25);
  });

  it.each([
    [500, "200"],
    [200, "200"],
    [50, "50"],
    [0, "25"],
    [-3, "25"],
    [undefined, "25"],
    [Number.NaN, "25"],
    [12.7, "12"],
  ])("limit %s se envía como %s", (limit, expected) => {
    expect(listParams({ limit }).limit).toBe(expected);
  });

  it("offset negativo o ausente se envía como 0", () => {
    expect(listParams({ offset: -10 }).offset).toBe("0");
    expect(listParams({}).offset).toBe("0");
    expect(listParams({ offset: 100 }).offset).toBe("100");
  });

  it("conserva los filtros y descarta los vacíos", () => {
    expect(listParams({ limit: 50, offset: 100, q: "ana", status: ["active"], plan: undefined, empty: "" })).toEqual({
      limit: "50",
      offset: "100",
      q: "ana",
      status: ["active"],
    });
  });
});

describe("clampLimit", () => {
  it.each([
    [500, 25],
    [0, 25],
    [-1, 25],
    ["abc", 25],
    [undefined, 25],
    [null, 25],
    [50, 50],
    ["100", 100],
    [200, 200],
    [201, 25],
    ["7.5", 25],
  ])("clampLimit(%j) es %i", (value, expected) => {
    expect(clampLimit(value)).toBe(expected);
  });
});
