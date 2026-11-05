// @vitest-environment node
// S5-F4: el nombre de archivo de Content-Disposition (RFC 6266).
import { filenameFromDisposition } from "./disposition";

describe("filenameFromDisposition", () => {
  it.each([
    ["attachment; filename=recibo-9a8b7c6d.pdf", "recibo-9a8b7c6d.pdf"],
    ['attachment; filename="socios-20261105.csv"', "socios-20261105.csv"],
    ["attachment; filename*=UTF-8''pagos%20oct.csv", "pagos oct.csv"],
    ['attachment; filename="a.csv"; filename*=UTF-8\'\'b.csv', "b.csv"],
    ['attachment; filename="co\\"mo.csv"', 'co"mo.csv'],
  ])("%s -> %s", (header, expected) => {
    expect(filenameFromDisposition(header)).toBe(expected);
  });

  it.each([[null], ["attachment"], ["inline"], ['attachment; filename=""'], ["attachment; filename*=UTF-8''%E0%A4%A"]])("sin nombre útil (%s) devuelve null", (header) => {
    expect(filenameFromDisposition(header)).toBeNull();
  });
});
