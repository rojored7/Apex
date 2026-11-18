// S9-F1 (US-178, US-179, US-184): contrato de la pestaña Atleta.
// - Respuestas del api (MetricOut, AthleteSummaryOut, MetricRevealOut) validadas con Zod antes de usarse. Ninguna lleva un valor
//   de salud en claro: la lista solo trae `has_*` (S9-D16); el valor llega solo por el reveal, de uno en uno.
// - metricFormSchema: el formulario de «Registrar medidas». Peso en kg con UN decimal (20 a 400), altura entera (50 a 250), % de grasa
//   entero (1 a 75), notas de hasta 500 caracteres y al menos una medida numérica (como `validate_metric` del api).
// - parseMetricForm: los valores ya validados como los espera `POST /athletes/{id}/metrics` (el peso viaja en gramos enteros, S9-D3).
import { z } from "zod";
import type { components } from "../../core/api/types";
import { todayBogota } from "../../core/i18n/format";
import { kgInputToGrams } from "../../shared/data/score";

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
