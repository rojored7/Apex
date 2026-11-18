// S8-F1 · US-165 y US-166 (front): catálogo de movimientos y benchmarks.
// - movementSchema y benchmarkSchema (reexportados de shared/data/catalog) validan las respuestas (CatalogMovementOut y BenchmarkOut).
// - movementFormSchema y benchmarkFormSchema: mismas reglas que el api (nombre de 1 a 60, descripción hasta 2.000).
// - toMovementPatch y toBenchmarkPatch: el PATCH lleva solo lo que cambió (un campo ausente no es un cambio).
// DESIGN-GAP (S8-D5): Movimientos.html trae alias, la unidad «lb» y «Tipos de récord»; el contrato no los tiene
// (todo se guarda en kg, N-45; los récords llegan con EP-24). La unidad es «qué se mide».
import { z } from "zod";
import type { components } from "../../core/api/types";
import { formatCount } from "../../core/i18n/format";
import { BENCHMARK_SCORE_TYPES, benchmarkSchema, MOVEMENT_CATEGORIES, MOVEMENT_UNITS, movementSchema } from "../../shared/data/catalog";

// El contrato de lectura del catálogo vive en shared/data/catalog.ts (S9-F2, E8): una sola fuente para wods y atleta.
export { benchmarkSchema, movementSchema, MOVEMENT_CATEGORIES, MOVEMENT_UNITS };
export const SCORE_TYPES = BENCHMARK_SCORE_TYPES;

export type MovementCategory = (typeof MOVEMENT_CATEGORIES)[number];
export type MovementUnit = (typeof MOVEMENT_UNITS)[number];
export type BenchmarkScoreType = (typeof SCORE_TYPES)[number];

export const CATEGORY_LABELS: Readonly<Record<MovementCategory, string>> = {
  weightlifting: "Fuerza",
  gymnastics: "Gimnástico",
  monostructural: "Mono-estructural",
  other: "Otro",
};

export const UNIT_LABELS: Readonly<Record<MovementUnit, string>> = {
  kg: "kg",
  reps: "Repeticiones",
  m: "Metros",
  cal: "Calorías",
  s: "Segundos",
};

export const SCORE_TYPE_LABELS: Readonly<Record<BenchmarkScoreType, string>> = {
  time: "Tiempo",
  rounds_reps: "Rondas + repeticiones",
  reps: "Repeticiones",
  load: "Carga",
};

export const NAME_MAX = 60;
export const DESCRIPTION_MAX = 2000;

export const MOVEMENT_MESSAGES = {
  name: "Escribe el nombre del movimiento (hasta 60 caracteres).",
  category: "Elige una categoría.",
  unit: "Elige una unidad.",
} as const;

export const BENCHMARK_MESSAGES = {
  name: "Escribe el nombre del benchmark (hasta 60 caracteres).",
  scoreType: "Elige el tipo de marca.",
  description: "La descripción admite hasta 2.000 caracteres.",
} as const;

export interface MovementFormValues {
  name: string;
  category: MovementCategory;
  unit: MovementUnit;
  is_active: boolean;
}

export interface BenchmarkFormValues {
  name: string;
  score_type: BenchmarkScoreType;
  description: string;
}

export const movementFormSchema: z.ZodType<MovementFormValues, MovementFormValues> = z.object({
  name: z.string().trim().min(1, MOVEMENT_MESSAGES.name).max(NAME_MAX, MOVEMENT_MESSAGES.name),
  category: z.enum(MOVEMENT_CATEGORIES, MOVEMENT_MESSAGES.category),
  unit: z.enum(MOVEMENT_UNITS, MOVEMENT_MESSAGES.unit),
  is_active: z.boolean(),
});

export const benchmarkFormSchema: z.ZodType<BenchmarkFormValues, BenchmarkFormValues> = z.object({
  name: z.string().trim().min(1, BENCHMARK_MESSAGES.name).max(NAME_MAX, BENCHMARK_MESSAGES.name),
  score_type: z.enum(SCORE_TYPES, BENCHMARK_MESSAGES.scoreType),
  description: z.string().max(DESCRIPTION_MAX, BENCHMARK_MESSAGES.description),
});

export const EMPTY_MOVEMENT_FORM: MovementFormValues = { name: "", category: "weightlifting", unit: "kg", is_active: true };
export const EMPTY_BENCHMARK_FORM: BenchmarkFormValues = { name: "", score_type: "time", description: "" };

export type MovementCreateBody = components["schemas"]["MovementCreate"];
export type MovementPatchBody = components["schemas"]["MovementPatch"];
export type BenchmarkCreateBody = components["schemas"]["BenchmarkCreate"];
export type BenchmarkPatchBody = components["schemas"]["BenchmarkPatch"];

export function movementToFormValues(source: { name: string; category: MovementCategory; unit: MovementUnit; is_active: boolean }): MovementFormValues {
  return { name: source.name, category: source.category, unit: source.unit, is_active: source.is_active };
}

export function benchmarkToFormValues(source: { name: string; score_type: BenchmarkScoreType; description: string }): BenchmarkFormValues {
  return { name: source.name, score_type: source.score_type, description: source.description };
}

export function toMovementCreate(values: MovementFormValues): MovementCreateBody {
  return { name: values.name.trim(), category: values.category, unit: values.unit };
}

export function toMovementPatch(values: MovementFormValues, initial: MovementFormValues): MovementPatchBody {
  const patch: MovementPatchBody = {};
  const name = values.name.trim();
  if (name !== initial.name) patch.name = name;
  if (values.category !== initial.category) patch.category = values.category;
  if (values.unit !== initial.unit) patch.unit = values.unit;
  if (values.is_active !== initial.is_active) patch.is_active = values.is_active;
  return patch;
}

export function toBenchmarkCreate(values: BenchmarkFormValues): BenchmarkCreateBody {
  return { name: values.name.trim(), score_type: values.score_type, description: values.description.trim() };
}

export function toBenchmarkPatch(values: BenchmarkFormValues, initial: BenchmarkFormValues): BenchmarkPatchBody {
  const patch: BenchmarkPatchBody = {};
  const name = values.name.trim();
  const description = values.description.trim();
  if (name !== initial.name) patch.name = name;
  if (values.score_type !== initial.score_type) patch.score_type = values.score_type;
  if (description !== initial.description.trim()) patch.description = description;
  return patch;
}

/** Texto de «N movimientos» o «N benchmarks» junto al botón de crear. */
export function countText(total: number, one: string, many: string): string {
  return total === 1 ? `1 ${one}` : `${formatCount(total)} ${many}`;
}
