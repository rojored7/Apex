// Revisión S9-F3 (seguridad S1 y S3): el contrato de la serie de benchmarks se valida antes de usarse.
import { attempt, benchmarkRow, seriesOf } from "../../test/athletes";
import { benchmarkSeriesSchema } from "./schemas";

const ROW = benchmarkRow();

describe("benchmarkSeriesSchema", () => {
  it("acepta una serie de hasta 200 intentos", () => {
    const attempts = Array.from({ length: 200 }, (_, i) => attempt(i + 1, { seconds: 300 }));

    expect(benchmarkSeriesSchema.safeParse(seriesOf(ROW, attempts)).success).toBe(true);
  });

  it("rechaza más de 200 intentos (el tope del api)", () => {
    const attempts = Array.from({ length: 201 }, (_, i) => attempt(i + 1, { seconds: 300 }));

    expect(benchmarkSeriesSchema.safeParse(seriesOf(ROW, attempts)).success).toBe(false);
  });

  it.each([["seconds"], ["rounds"], ["reps"], ["load_g"]] as const)("rechaza %s negativo", (field) => {
    const series = seriesOf(ROW, [attempt(1, { [field]: -1 })]);

    expect(benchmarkSeriesSchema.safeParse(series).success).toBe(false);
  });

  it("acepta cero y null en las marcas", () => {
    const series = seriesOf(ROW, [attempt(1, { seconds: 0, rounds: null, reps: 0, load_g: null })]);

    expect(benchmarkSeriesSchema.safeParse(series).success).toBe(true);
  });
});
