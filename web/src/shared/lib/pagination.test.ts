// @vitest-environment node
// US-063 T1: traducción de páginas a limit/offset (D2) y textos de la paginación.
import { DEFAULT_LIMIT, PAGE_SIZES, clampLimit, offsetToPage, pageToOffset, rangeLabel, totalPages } from "./pagination";

describe("pagination", () => {
  it("ofrece solo 25, 50 y 100 y 25 por defecto", () => {
    expect([...PAGE_SIZES]).toEqual([25, 50, 100]);
    expect(DEFAULT_LIMIT).toBe(25);
  });

  it.each([
    [1, 25, 0],
    [3, 50, 100],
    [2, 100, 100],
    [0, 25, 0],
    [-4, 25, 0],
  ])("pageToOffset(%i, %i) = %i", (page, limit, offset) => {
    expect(pageToOffset(page, limit)).toBe(offset);
  });

  it.each([
    [100, 50, 3],
    [0, 25, 1],
    [30, 25, 2],
    [-10, 25, 1],
  ])("offsetToPage(%i, %i) = %i", (offset, limit, page) => {
    expect(offsetToPage(offset, limit)).toBe(page);
  });

  it.each([
    [0, 25, 1],
    [300, 50, 6],
    [312, 50, 7],
    [1, 25, 1],
  ])("totalPages(%i, %i) = %i", (total, limit, pages) => {
    expect(totalPages(total, limit)).toBe(pages);
  });

  it.each([
    [500, 25],
    [0, 25],
    [-1, 25],
    ["abc", 25],
    [50, 50],
  ])("clampLimit(%j) = %i", (value, expected) => {
    expect(clampLimit(value)).toBe(expected);
  });

  it("rangeLabel muestra el tramo y el total", () => {
    expect(rangeLabel(100, 50, 312)).toBe("Mostrando 101–150 de 312");
    expect(rangeLabel(300, 50, 312)).toBe("Mostrando 301–312 de 312");
    expect(rangeLabel(0, 25, 1250)).toBe("Mostrando 1–25 de 1.250");
    expect(rangeLabel(0, 25, 0)).toBe("Sin resultados");
  });
});
