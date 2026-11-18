// Revisión S9-F3 (seguridad S1 y S3): el contrato de la serie de benchmarks se valida antes de usarse.
import { attempt, benchmarkRow, seriesOf, summary, summaryRecord } from "../../test/athletes";
import { athleteSummarySchema, benchmarkRowSchema, benchmarkSeriesSchema } from "./schemas";

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

// V7 M11: `score_type` se valida igual en el resumen, la lista de benchmarks, la serie y los récords: un valor que la pantalla no
// conoce es una respuesta inválida (no un «—» silencioso).
describe("score_type (V7 M11)", () => {
  it("la serie y la fila de la lista rechazan un tipo de marca desconocido", () => {
    expect(benchmarkSeriesSchema.safeParse({ ...seriesOf(ROW, [attempt(1, { seconds: 300 })]), score_type: "banana" }).success).toBe(false);
    expect(benchmarkRowSchema.safeParse({ ...ROW, score_type: "banana" }).success).toBe(false);
  });

  it("el resumen rechaza un récord con tipo de marca desconocido y acepta los cinco conocidos", () => {
    const base = summary();
    const withType = (score_type: string) => athleteSummarySchema.safeParse({ ...base, recent_records: [{ ...summaryRecord(), score_type }] }).success;

    expect(withType("banana")).toBe(false);
    for (const known of ["time", "rounds_reps", "reps", "load", "none"]) expect(withType(known)).toBe(true);
  });
});
