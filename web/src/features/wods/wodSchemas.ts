// S8-F2 · US-166 y US-167 (front): WODs. Respuestas (WodRowOut, WodOut) validadas con Zod y formulario de alta y edición.
// - Cargas: kg con hasta dos decimales en pantalla, gramos enteros en el contrato (S8-D41: «102,5 kg» se envía como 102500).
// - El PATCH lleva solo lo que cambió; los movimientos van completos si cambió cualquiera (el api los reemplaza).
// DESIGN-GAP (S8-D7): WOD_Form.html trae tipo «AMRAP/For time» y plantillas; el contrato solo tiene `score_type`.
import { z } from "zod";
import type { components } from "../../core/api/types";
import { gramsToKgInput, kgInputToGrams } from "../../shared/data/score";

export const WOD_SCORE_TYPES = ["time", "rounds_reps", "reps", "load", "none"] as const;
export type WodScoreType = (typeof WOD_SCORE_TYPES)[number];

export const WOD_SCORE_LABELS: Readonly<Record<WodScoreType, string>> = {
  time: "Tiempo",
  rounds_reps: "Rondas + repeticiones",
  reps: "Repeticiones",
  load: "Carga",
  none: "Sin marca",
};

export const TITLE_MAX = 80;
export const DESCRIPTION_MAX = 2000;
export const REPS_MAX = 40;
export const NOTES_MAX = 200;
export const MOVEMENTS_MAX = 30;
const SECONDS_PER_MINUTE = 60;
const TIME_CAP_MAX_MIN = 1440;

export const wodRowSchema = z.object({
  id: z.string().min(1),
  date: z.string(),
  title: z.string(),
  score_type: z.enum(WOD_SCORE_TYPES),
  time_cap_s: z.number().int().nullable(),
  benchmark_id: z.string().nullable(),
  benchmark_name: z.string().nullable(),
  is_benchmark: z.boolean(),
  movement_count: z.number().int().nonnegative(),
  movement_names: z.array(z.string()),
  result_count: z.number().int().nonnegative(),
});

export const wodMovementSchema = z.object({
  id: z.string(),
  movement_id: z.string(),
  movement_name: z.string(),
  position: z.number().int(),
  reps: z.string(),
  load_rx_m_g: z.number().int().nullable(),
  load_rx_f_g: z.number().int().nullable(),
  is_primary: z.boolean(),
  notes: z.string(),
});

export const wodSchema = z.object({
  id: z.string().min(1),
  date: z.string(),
  title: z.string(),
  description: z.string(),
  score_type: z.enum(WOD_SCORE_TYPES),
  time_cap_s: z.number().int().nullable(),
  benchmark_id: z.string().nullable(),
  benchmark_name: z.string().nullable(),
  is_benchmark: z.boolean(),
  result_count: z.number().int().nonnegative(),
  movements: z.array(wodMovementSchema),
  created_at: z.string(),
  updated_at: z.string(),
});

export type WodRowView = z.infer<typeof wodRowSchema>;
export type WodView = z.infer<typeof wodSchema>;
export type WodCreateBody = components["schemas"]["WodCreate"];
export type WodPatchBody = components["schemas"]["WodPatch"];
type WodMovementBody = components["schemas"]["WodMovementIn"];

export const WOD_MESSAGES = {
  title: `Escribe el título del WOD (hasta ${String(TITLE_MAX)} caracteres).`,
  date: "Elige la fecha del WOD.",
  movements: "Agrega al menos un movimiento.",
  tooManyMovements: `Un WOD admite hasta ${String(MOVEMENTS_MAX)} movimientos.`,
  load: "La carga son kg con hasta dos decimales y no pasa de 1.000.",
  reps: `Las repeticiones admiten hasta ${String(REPS_MAX)} caracteres.`,
  notes: `La nota admite hasta ${String(NOTES_MAX)} caracteres.`,
  timeCap: "El time cap son minutos enteros, de 1 a 1.440.",
  description: `La descripción admite hasta ${String(DESCRIPTION_MAX)} caracteres.`,
} as const;

export interface MovementRowValues {
  /** Clave estable de la fila en la pantalla. */
  key: string;
  movement_id: string;
  movement_name: string;
  reps: string;
  load_m: string;
  load_f: string;
  is_primary: boolean;
  notes: string;
}

export interface WodFormValues {
  date: string;
  title: string;
  score_type: WodScoreType;
  benchmark_id: string;
  time_cap_min: string;
  description: string;
  movements: MovementRowValues[];
}

const loadText = z.string().refine((value) => value.trim() === "" || kgInputToGrams(value) !== null, WOD_MESSAGES.load);

const movementRowSchema = z.object({
  key: z.string(),
  movement_id: z.string().min(1),
  movement_name: z.string(),
  reps: z.string().max(REPS_MAX, WOD_MESSAGES.reps),
  load_m: loadText,
  load_f: loadText,
  is_primary: z.boolean(),
  notes: z.string().max(NOTES_MAX, WOD_MESSAGES.notes),
});

export const wodFormSchema: z.ZodType<WodFormValues, WodFormValues> = z.object({
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, WOD_MESSAGES.date),
  title: z.string().trim().min(1, WOD_MESSAGES.title).max(TITLE_MAX, WOD_MESSAGES.title),
  score_type: z.enum(WOD_SCORE_TYPES),
  benchmark_id: z.string(),
  time_cap_min: z.string().refine((value) => {
    if (value.trim() === "") return true;
    const minutes = Number(value);
    return Number.isInteger(minutes) && minutes >= 1 && minutes <= TIME_CAP_MAX_MIN;
  }, WOD_MESSAGES.timeCap),
  description: z.string().max(DESCRIPTION_MAX, WOD_MESSAGES.description),
  movements: z.array(movementRowSchema).min(1, WOD_MESSAGES.movements).max(MOVEMENTS_MAX, WOD_MESSAGES.tooManyMovements),
});

export const emptyWodForm = (date: string): WodFormValues => ({
  date,
  title: "",
  score_type: "time",
  benchmark_id: "",
  time_cap_min: "",
  description: "",
  movements: [],
});

export function newMovementRow(movementId: string, name: string): MovementRowValues {
  return { key: `${movementId}-${String(Math.random()).slice(2, 8)}`, movement_id: movementId, movement_name: name, reps: "", load_m: "", load_f: "", is_primary: false, notes: "" };
}

export function wodToFormValues(wod: WodView): WodFormValues {
  return {
    date: wod.date,
    title: wod.title,
    score_type: wod.score_type,
    benchmark_id: wod.benchmark_id ?? "",
    time_cap_min: wod.time_cap_s === null ? "" : String(wod.time_cap_s / SECONDS_PER_MINUTE),
    description: wod.description,
    movements: [...wod.movements]
      .sort((a, b) => a.position - b.position)
      .map((m) => ({
        key: m.id,
        movement_id: m.movement_id,
        movement_name: m.movement_name,
        reps: m.reps,
        load_m: gramsToKgInput(m.load_rx_m_g),
        load_f: gramsToKgInput(m.load_rx_f_g),
        is_primary: m.is_primary,
        notes: m.notes,
      })),
  };
}

function gramsOrNull(text: string): number | null {
  return text.trim() === "" ? null : kgInputToGrams(text);
}

function toMovementBodies(rows: readonly MovementRowValues[]): WodMovementBody[] {
  return rows.map((row, index) => ({
    movement_id: row.movement_id,
    position: index + 1,
    reps: row.reps.trim(),
    load_rx_m_g: gramsOrNull(row.load_m),
    load_rx_f_g: gramsOrNull(row.load_f),
    is_primary: row.is_primary,
    notes: row.notes.trim(),
  }));
}

const timeCapSeconds = (minutes: string): number | null => (minutes.trim() === "" ? null : Number(minutes) * SECONDS_PER_MINUTE);

export function toWodCreate(values: WodFormValues): WodCreateBody {
  return {
    date: values.date,
    title: values.title.trim(),
    description: values.description.trim(),
    score_type: values.score_type,
    benchmark_id: values.benchmark_id === "" ? null : values.benchmark_id,
    time_cap_s: timeCapSeconds(values.time_cap_min),
    movements: toMovementBodies(values.movements),
  };
}

export function toWodPatch(values: WodFormValues, initial: WodFormValues): WodPatchBody {
  const patch: WodPatchBody = {};
  if (values.date !== initial.date) patch.date = values.date;
  if (values.title.trim() !== initial.title) patch.title = values.title.trim();
  if (values.description.trim() !== initial.description.trim()) patch.description = values.description.trim();
  if (values.score_type !== initial.score_type) patch.score_type = values.score_type;
  if (values.benchmark_id !== initial.benchmark_id) patch.benchmark_id = values.benchmark_id === "" ? null : values.benchmark_id;
  if (values.time_cap_min.trim() !== initial.time_cap_min.trim()) patch.time_cap_s = timeCapSeconds(values.time_cap_min);
  const next = toMovementBodies(values.movements);
  if (JSON.stringify(next) !== JSON.stringify(toMovementBodies(initial.movements))) patch.movements = next;
  return patch;
}
