// Revisión S9-F2 (TS M4, seguridad M, y L9): el formulario de récords no fabrica un cero cuando el tipo de marca no se conoce,
// y el contrato de RecordOut solo acepta los tipos de marca que la pantalla sabe leer.
import { EMPTY_RECORD_FORM, parseRecordForm, recordFormSchema, recordSchema, type RecordFormValues } from "./schemas";
import { record } from "../../test/athletes";

const benchmarkForm = (overrides: Partial<RecordFormValues>): RecordFormValues => ({ ...EMPTY_RECORD_FORM(), kind: "benchmark", benchmark_id: "e1e1e1e1-0000-4000-8000-000000000001", ...overrides });

describe("recordFormSchema · benchmark con tipo de marca desconocido", () => {
  it.each([[""], ["none"], ["parsec"]])("el score_type «%s» no se envía y pide elegir el benchmark otra vez", (scoreType) => {
    const result = recordFormSchema.safeParse(benchmarkForm({ score_type: scoreType, time: "11:42" }));

    expect(result.success).toBe(false);
    expect(result.error?.issues.map((i) => ({ path: i.path.join("."), message: i.message }))).toEqual([{ path: "benchmark_id", message: "Elige el benchmark otra vez." }]);
  });

  it.each([["time", { time: "11:42" }], ["rounds_reps", { rounds: "5", reps: "3" }], ["reps", { reps: "40" }], ["load", { load: "92,5" }]] as const)("el tipo %s con su marca válida pasa", (scoreType, marks) => {
    expect(recordFormSchema.safeParse(benchmarkForm({ score_type: scoreType, ...marks })).success).toBe(true);
  });
});

describe("parseRecordForm", () => {
  it("con un tipo de marca desconocido lanza en vez de fabricar una marca en cero", () => {
    expect(() => parseRecordForm(benchmarkForm({ score_type: "none" }))).toThrow();
    expect(() => parseRecordForm(benchmarkForm({ score_type: "" }))).toThrow();
  });

  it("una carga de benchmark válida viaja en gramos", () => {
    expect(parseRecordForm(benchmarkForm({ score_type: "load", load: "92,5" }))).toMatchObject({ kind: "benchmark", load_g: 92_500 });
  });

  it("una marca inválida lanza (nunca envía 0)", () => {
    expect(() => parseRecordForm(benchmarkForm({ score_type: "time", time: "abc" }))).toThrow();
    expect(() => parseRecordForm({ ...EMPTY_RECORD_FORM(), kind: "rm", movement_id: "x", load: "0" })).toThrow();
  });
});

describe("recordSchema.score_type", () => {
  it("acepta los tipos de marca conocidos y null", () => {
    expect(recordSchema.safeParse({ ...record(1), score_type: "time" }).success).toBe(true);
    expect(recordSchema.safeParse({ ...record(1), score_type: null }).success).toBe(true);
  });

  it("rechaza un tipo de marca que la pantalla no sabe leer", () => {
    expect(recordSchema.safeParse({ ...record(1), score_type: "parsec" }).success).toBe(false);
  });
});
