// V7 L6: una sola paginación «hasta total» para el catálogo y los benchmarks del atleta, con deduplicación por id.
import { collectPages } from "./collectPages";

interface Row {
  id: string;
}

const rows = (from: number, to: number): Row[] => Array.from({ length: to - from }, (_, i) => ({ id: `r${String(from + i)}` }));
const OPTIONS = { limit: 200, maxPages: 5, idOf: (row: Row) => row.id };

describe("collectPages", () => {
  it("pide páginas hasta cubrir el total y no pide de más", async () => {
    const offsets: number[] = [];
    const result = await collectPages((offset) => {
      offsets.push(offset);
      return Promise.resolve({ items: rows(offset, Math.min(offset + 200, 450)), total: 450 });
    }, OPTIONS);

    expect(offsets).toEqual([0, 200, 400]);
    expect(result.items).toHaveLength(450);
    expect(result.total).toBe(450);
    expect(result.truncated).toBe(false);
  });

  it("quita los repetidos por id (una fila que se movió entre páginas) y conserva el primero", async () => {
    const result = await collectPages((offset) => Promise.resolve({ items: offset === 0 ? [{ id: "a" }, { id: "b" }] : [{ id: "b" }, { id: "c" }], total: 4 }), { ...OPTIONS, limit: 2 });

    expect(result.items.map((row) => row.id)).toEqual(["a", "b", "c"]);
  });

  it("se detiene en el tope de páginas y avisa que quedó incompleta", async () => {
    let calls = 0;
    const result = await collectPages((offset) => {
      calls += 1;
      return Promise.resolve({ items: rows(offset, offset + 200), total: 1500 });
    }, OPTIONS);

    expect(calls).toBe(5);
    expect(result.items).toHaveLength(1000);
    expect(result.truncated).toBe(true);
  });
});
