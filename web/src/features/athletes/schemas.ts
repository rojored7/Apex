// S9-F1 (US-178, US-179, US-184): contrato de la pestaña Atleta.
// - Respuestas del api (MetricOut, AthleteSummaryOut, MetricRevealOut) validadas con Zod antes de usarse. Ninguna lleva un valor
//   de salud en claro: la lista solo trae `has_*` (S9-D16); el valor llega solo por el reveal, de uno en uno.
// - metricFormSchema: el formulario de «Registrar medidas». Peso en kg con UN decimal (20 a 400), altura entera (50 a 250), % de grasa
//   entero (1 a 75), notas de hasta 500 caracteres y al menos una medida numérica (como `validate_metric` del api).
// - parseMetricForm: los valores ya validados como los espera `POST /athletes/{id}/metrics` (el peso viaja en gramos enteros, S9-D3).
// - S9-F2 (US-180 a US-182): rmSchema y recordSchema validan RmOut y RecordOut; recordFormSchema y parseRecordForm son el formulario
//   «Registrar récord» (cargas en gramos enteros, S9-D41; sin `capped` manual, S9-D8).
import { z } from "zod";
import type { components } from "../../core/api/types";
import { todayBogota } from "../../core/i18n/format";
import { kgInputToGrams, parseClock, SCORE_KINDS } from "../../shared/data/score";

export type MetricView = components["schemas"]["MetricOut"];
export type AthleteSummaryView = components["schemas"]["AthleteSummaryOut"];
export type SummaryRecordView = components["schemas"]["SummaryRecordOut"];
export type MetricCreate = components["schemas"]["MetricIn"];
export type MetricFieldName = components["schemas"]["MetricRevealIn"]["field"];

export const METRIC_FIELDS = ["weight_g", "height_cm", "body_fat_pct", "notes"] as const satisfies readonly MetricFieldName[];

export const metricSchema = z.object({
  id: z.string().min(1),
  measured_on: z.string().min(1),
  has_weight: z.boolean(),
  has_height: z.boolean(),
  has_body_fat: z.boolean(),
  has_notes: z.boolean(),
  recorded_by: z.string().min(1),
  recorded_by_name: z.string().nullable(),
  voided_at: z.string().nullable(),
  created_at: z.string().min(1),
});

export const summaryRecordSchema = z.object({
  id: z.string().min(1),
  kind: z.enum(["rm", "benchmark"]),
  movement_id: z.string().nullable(),
  movement_name: z.string().nullable(),
  benchmark_id: z.string().nullable(),
  benchmark_name: z.string().nullable(),
  score_type: z.string().nullable(),
  value_g: z.number().int().nullable(),
  level: z.enum(["rx", "rx_plus", "scaled"]).nullable(),
  seconds: z.number().int().nullable(),
  rounds: z.number().int().nullable(),
  reps: z.number().int().nullable(),
  load_g: z.number().int().nullable(),
  capped: z.boolean(),
  achieved_on: z.string().min(1),
  source: z.enum(["manual", "derived"]),
  wod_id: z.string().nullable(),
});

export const athleteSummarySchema = z.object({
  metrics_count: z.number().int().nonnegative(),
  last_metric_on: z.string().nullable(),
  current_rms: z.number().int().nonnegative(),
  benchmarks_with_attempts: z.number().int().nonnegative(),
  truncated: z.boolean(),
  recent_records: z.array(summaryRecordSchema),
});

export const metricRevealSchema = z.object({
  field: z.enum(METRIC_FIELDS),
  value: z.union([z.number(), z.string(), z.null()]),
});

/** ¿El valor de un reveal es del tipo del campo? Entero finito en peso, altura y grasa; texto en notas; `null` si el campo está vacío. */
export function isRevealValueFor(field: MetricFieldName, value: number | string | null): boolean {
  if (value === null) return true;
  if (field === "notes") return typeof value === "string";
  return typeof value === "number" && Number.isSafeInteger(value);
}

export const METRIC_MESSAGES = {
  weight: "Escribe el peso en kg con un decimal, de 20 a 400.",
  height: "Escribe la altura en cm, un número entero de 50 a 250.",
  bodyFat: "Escribe el % de grasa como número entero, de 1 a 75.",
  notes: "Las notas admiten hasta 500 caracteres.",
  date: "La fecha debe estar entre el 1 ene 2000 y hoy.",
  atLeastOne: "Registra al menos una medida: peso, altura o % de grasa.",
} as const;

export interface MetricFormValues {
  measured_on: string;
  weight_kg: string;
  height_cm: string;
  body_fat_pct: string;
  notes: string;
}

export const EMPTY_METRIC_FORM = (): MetricFormValues => ({ measured_on: todayBogota(), weight_kg: "", height_cm: "", body_fat_pct: "", notes: "" });

/** El código de Zod para una regla propia (no es un código del api). */
const ISSUE_CODE = "custom" as const;
export const NOTES_MAX = 500;
const MIN_DATE = "2000-01-01";
const WEIGHT_MIN_G = 20_000;
const WEIGHT_MAX_G = 400_000;
const HEIGHT_MIN = 50;
const HEIGHT_MAX = 250;
const FAT_MIN = 1;
const FAT_MAX = 75;
const ONE_DECIMAL_KG = /^\d{1,3}(?:[.,]\d)?$/;
const INTEGER_PATTERN = /^\d{1,3}$/;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

/** «61,2» o «61.2» a gramos enteros (61200); `null` si no es un peso de 20 a 400 kg con UN decimal (kgInputToGrams admite dos). */
export function weightInputToGrams(input: string): number | null {
  const text = input.trim();
  if (!ONE_DECIMAL_KG.test(text)) return null;
  const grams = kgInputToGrams(text);
  return grams !== null && grams >= WEIGHT_MIN_G && grams <= WEIGHT_MAX_G ? grams : null;
}

function integerInRange(input: string, min: number, max: number): number | null {
  const text = input.trim();
  if (!INTEGER_PATTERN.test(text)) return null;
  const value = Number(text);
  return value >= min && value <= max ? value : null;
}

const isBlank = (text: string): boolean => text.trim() === "";
const optional = (check: (text: string) => boolean) => (text: string) => isBlank(text) || check(text);

export const metricFormSchema = z
  .object({
    measured_on: z.string().refine((text) => DATE_PATTERN.test(text) && text >= MIN_DATE && text <= todayBogota(), METRIC_MESSAGES.date),
    weight_kg: z.string().refine(optional((text) => weightInputToGrams(text) !== null), METRIC_MESSAGES.weight),
    height_cm: z.string().refine(optional((text) => integerInRange(text, HEIGHT_MIN, HEIGHT_MAX) !== null), METRIC_MESSAGES.height),
    body_fat_pct: z.string().refine(optional((text) => integerInRange(text, FAT_MIN, FAT_MAX) !== null), METRIC_MESSAGES.bodyFat),
    notes: z.string().refine((text) => Array.from(text.trim()).length <= NOTES_MAX, METRIC_MESSAGES.notes),
  })
  .superRefine((values, ctx) => {
    const filled = [values.weight_kg, values.height_cm, values.body_fat_pct].some((text) => !isBlank(text));
    if (!filled) ctx.addIssue({ code: ISSUE_CODE, message: METRIC_MESSAGES.atLeastOne, path: ["weight_kg"] });
  });

/** El cuerpo de POST /athletes/{id}/metrics: solo lo que se llenó, el peso en gramos y las notas recortadas. */
export function parseMetricForm(values: MetricFormValues): MetricCreate {
  const weight = isBlank(values.weight_kg) ? null : weightInputToGrams(values.weight_kg);
  const height = isBlank(values.height_cm) ? null : integerInRange(values.height_cm, HEIGHT_MIN, HEIGHT_MAX);
  const fat = isBlank(values.body_fat_pct) ? null : integerInRange(values.body_fat_pct, FAT_MIN, FAT_MAX);
  const notes = values.notes.trim();
  return {
    measured_on: values.measured_on,
    ...(weight === null ? {} : { weight_g: weight }),
    ...(height === null ? {} : { height_cm: height }),
    ...(fat === null ? {} : { body_fat_pct: fat }),
    ...(notes === "" ? {} : { notes }),
  };
}

export const RECORD_LEVELS = ["rx", "rx_plus", "scaled"] as const;
export type RecordLevel = (typeof RECORD_LEVELS)[number];
export const RECORD_KINDS = ["rm", "benchmark"] as const;
export type RecordKind = (typeof RECORD_KINDS)[number];

export type RmView = components["schemas"]["RmOut"];
export type RecordView = z.infer<typeof recordSchema>;
export type RecordCreate = components["schemas"]["RecordIn"];

export const rmSchema = z.object({
  record_id: z.string().min(1),
  movement_id: z.string().min(1),
  movement_name: z.string().nullable(),
  value_g: z.number().int().nonnegative(),
  achieved_on: z.string().min(1),
  source: z.enum(["manual", "derived"]),
});

export const recordSchema = z.object({
  id: z.string().min(1),
  kind: z.enum(RECORD_KINDS),
  movement_id: z.string().nullable(),
  movement_name: z.string().nullable(),
  benchmark_id: z.string().nullable(),
  benchmark_name: z.string().nullable(),
  score_type: z.enum(SCORE_KINDS).nullable(),
  value_g: z.number().int().nullable(),
  level: z.enum(RECORD_LEVELS).nullable(),
  seconds: z.number().int().nullable(),
  rounds: z.number().int().nullable(),
  reps: z.number().int().nullable(),
  load_g: z.number().int().nullable(),
  capped: z.boolean(),
  achieved_on: z.string().min(1),
  source: z.enum(["manual", "derived"]),
  wod_id: z.string().nullable(),
  result_id: z.string().nullable(),
  result_source: z.enum(["desk", "kiosk"]).nullable().optional(),
  is_current: z.boolean(),
  invalidated_at: z.string().nullable(),
  invalidated_reason: z.enum(["superseded", "voided", "manual_error"]).nullable(),
  recorded_by: z.string().min(1),
  recorded_by_name: z.string().nullable(),
  created_at: z.string().min(1),
});

export const RECORD_MESSAGES = {
  movement: "Elige el movimiento.",
  benchmark: "Elige el benchmark.",
  benchmarkAgain: "Elige el benchmark otra vez.",
  load: "Escribe la carga en kg, de 0,01 a 1.000, con hasta dos decimales.",
  time: "Escribe el tiempo como mm:ss, por ejemplo 11:42.",
  rounds: "Escribe las rondas completas, de 0 a 1.000.",
  reps: "Escribe las repeticiones, de 0 a 100.000.",
} as const;

export interface RecordFormValues {
  kind: RecordKind;
  movement_id: string;
  benchmark_id: string;
  /** El tipo de marca del benchmark elegido (lo fija el panel al elegirlo); `""` si no hay benchmark. */
  score_type: string;
  level: RecordLevel;
  load: string;
  time: string;
  rounds: string;
  reps: string;
  achieved_on: string;
}

export const EMPTY_RECORD_FORM = (): RecordFormValues => ({
  kind: "rm",
  movement_id: "",
  benchmark_id: "",
  score_type: "",
  level: "rx",
  load: "",
  time: "",
  rounds: "",
  reps: "",
  achieved_on: todayBogota(),
});

const MAX_ROUNDS = 1000;
const MAX_REPS = 100_000;
const COUNT_PATTERN = /^[0-9]{1,6}$/;

const inRange = (text: string, max: number): boolean => COUNT_PATTERN.test(text.trim()) && Number(text.trim()) <= max;

/** Carga en kg a gramos enteros: 0,01 a 1.000 kg; `null` si no es una carga válida (cero tampoco). */
export function recordLoadToGrams(input: string): number | null {
  const grams = kgInputToGrams(input);
  return grams !== null && grams > 0 ? grams : null;
}

const BENCHMARK_MARKS = ["time", "rounds_reps", "reps", "load"] as const;
type BenchmarkMark = (typeof BENCHMARK_MARKS)[number];

/** El tipo de marca de un benchmark; `null` si el formulario trae uno que no se puede registrar a mano (vacío, `none` u otro). */
function benchmarkMark(text: string): BenchmarkMark | null {
  return BENCHMARK_MARKS.find((mark) => mark === text) ?? null;
}

function checkBenchmarkMark(values: RecordFormValues, scoreType: BenchmarkMark, fail: (path: keyof RecordFormValues, message: string) => void): void {
  if (scoreType === "time" && parseClock(values.time) === null) fail("time", RECORD_MESSAGES.time);
  if (scoreType === "rounds_reps") {
    if (!inRange(values.rounds, MAX_ROUNDS)) fail("rounds", RECORD_MESSAGES.rounds);
    if (!inRange(values.reps, MAX_REPS)) fail("reps", RECORD_MESSAGES.reps);
  }
  if (scoreType === "reps" && !inRange(values.reps, MAX_REPS)) fail("reps", RECORD_MESSAGES.reps);
  if (scoreType === "load" && recordLoadToGrams(values.load) === null) fail("load", RECORD_MESSAGES.load);
}

export const recordFormSchema = z
  .object({
    kind: z.enum(RECORD_KINDS),
    movement_id: z.string(),
    benchmark_id: z.string(),
    score_type: z.string(),
    level: z.enum(RECORD_LEVELS),
    load: z.string(),
    time: z.string(),
    rounds: z.string(),
    reps: z.string(),
    achieved_on: z.string().refine((text) => DATE_PATTERN.test(text) && text >= MIN_DATE && text <= todayBogota(), METRIC_MESSAGES.date),
  })
  .superRefine((values, ctx) => {
    const fail = (path: keyof RecordFormValues, message: string): void => {
      ctx.addIssue({ code: ISSUE_CODE, path: [path], message });
    };
    if (values.kind === "rm") {
      if (values.movement_id === "") fail("movement_id", RECORD_MESSAGES.movement);
      if (recordLoadToGrams(values.load) === null) fail("load", RECORD_MESSAGES.load);
      return;
    }
    if (values.benchmark_id === "") fail("benchmark_id", RECORD_MESSAGES.benchmark);
    else {
      const mark = benchmarkMark(values.score_type);
      if (mark === null) fail("benchmark_id", RECORD_MESSAGES.benchmarkAgain);
      else checkBenchmarkMark(values, mark, fail);
    }
  });

/** Un valor que el esquema ya validó; si falta, el formulario se envió sin pasar por `recordFormSchema` (error de programación, nunca un cero enviado). */
function validated<T>(value: T | null, what: string): T {
  if (value === null) throw new Error(`parseRecordForm: ${what} no es válido; hay que validar con recordFormSchema antes`);
  return value;
}

/** Los valores ya validados como los espera `POST /athletes/{id}/records`: solo los campos del tipo (el api rechaza los demás). */
export function parseRecordForm(values: RecordFormValues): RecordCreate {
  if (values.kind === "rm") {
    return { kind: "rm", movement_id: values.movement_id, value_g: validated(recordLoadToGrams(values.load), "la carga"), achieved_on: values.achieved_on };
  }
  const base = { kind: "benchmark" as const, benchmark_id: values.benchmark_id, level: values.level, achieved_on: values.achieved_on };
  const mark = validated(benchmarkMark(values.score_type), "el tipo de marca");
  switch (mark) {
    case "time":
      return { ...base, seconds: validated(parseClock(values.time), "el tiempo") };
    case "rounds_reps":
      return { ...base, rounds: Number(values.rounds.trim()), reps: Number(values.reps.trim()) };
    case "reps":
      return { ...base, reps: Number(values.reps.trim()) };
    case "load":
      return { ...base, load_g: validated(recordLoadToGrams(values.load), "la carga") };
  }
}

// S9-F3 (US-183): la lista de benchmarks con intentos y la serie de uno (BenchmarkRowOut, BenchmarkSeriesOut y AttemptOut), validadas con Zod.
const scoreSchema = z.object({
  level: z.enum(RECORD_LEVELS),
  seconds: z.number().int().nonnegative().nullable(),
  rounds: z.number().int().nonnegative().nullable(),
  reps: z.number().int().nonnegative().nullable(),
  load_g: z.number().int().nonnegative().nullable(),
  capped: z.boolean(),
});

/** Tope de intentos de una serie (BenchmarkSeriesOut: los 200 más recientes). */
export const SERIES_MAX_ATTEMPTS = 200;

export const benchmarkRowSchema = z.object({
  benchmark_id: z.string().min(1),
  name: z.string(),
  score_type: z.string(),
  attempts: z.number().int().nonnegative(),
  last_on: z.string().min(1),
  best: scoreSchema,
});

export const attemptSchema = scoreSchema.extend({
  result_id: z.string().min(1),
  wod_id: z.string().min(1),
  wod_date: z.string().min(1),
  level_changed: z.boolean(),
  is_best: z.boolean(),
  source: z.enum(["desk", "kiosk"]),
});

export const benchmarkSeriesSchema = z.object({
  benchmark_id: z.string().min(1),
  name: z.string(),
  score_type: z.string(),
  attempts: z.array(attemptSchema).max(SERIES_MAX_ATTEMPTS),
  truncated: z.boolean(),
});

export type BenchmarkRowView = z.infer<typeof benchmarkRowSchema>;
export type BenchmarkSeriesView = z.infer<typeof benchmarkSeriesSchema>;
export type AttemptView = z.infer<typeof attemptSchema>;
