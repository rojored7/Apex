// S7-F2 · US-155 y US-158 (front): formularios de Clases con Zod.
// - slotFormSchema: días 0 (lunes) a 6 (domingo), `HH:MM`, duración 15 a 240, cupo 1 a 100, nombre hasta 40
//   (mismas reglas que SlotCreate del api). Los números viajan como texto (lo que se ve en el campo).
// - cancelReasonSchema: motivo de 3 a 200 caracteres (CancelReason del api, ConfirmModal pide mínimo 3).
// - toSlotCreate y toSlotPatch arman el cuerpo; el PATCH lleva solo lo que cambió (un campo ausente no es un cambio).
import { z } from "zod";
import type { components } from "../../core/api/types";

export const WEEKDAY_VALUES = [0, 1, 2, 3, 4, 5, 6] as const;
export const WEEKDAY_LETTERS = ["L", "M", "X", "J", "V", "S", "D"] as const;
export const WEEKDAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"] as const;

export const DURATION_MIN = 15;
export const DURATION_MAX = 240;
export const CAPACITY_MIN = 1;
export const CAPACITY_MAX = 100;
export const NAME_MAX = 40;
export const CANCEL_REASON_MIN = 3;
export const CANCEL_REASON_MAX = 200;

const TIME = /^([01][0-9]|2[0-3]):[0-5][0-9]$/;
const CIVIL_DATE = /^\d{4}-\d{2}-\d{2}$/;
const DIGITS = /^\d{1,4}$/;

export const SLOT_MESSAGES = {
  weekdays: "Elige al menos un día.",
  startTime: "La hora de inicio debe ser HH:MM, entre 00:00 y 23:59.",
  duration: "La duración debe estar entre 15 y 240 minutos.",
  capacity: "El cupo debe estar entre 1 y 100.",
  name: "El nombre admite hasta 40 caracteres.",
  validFrom: "La fecha de inicio debe ser una fecha válida.",
} as const;

/** Lo que el usuario escribe (los números como texto). */
export interface SlotFormValues {
  weekdays: number[];
  start_time: string;
  duration_min: string;
  capacity: string;
  coach_id: string;
  name: string;
  valid_from: string;
  is_active: boolean;
}

/** Entero escrito como texto, dentro de [min, max]. */
const integerInRange = (min: number, max: number, message: string) =>
  z.string().refine((value) => {
    const text = value.trim();
    if (!DIGITS.test(text)) return false;
    const n = Number(text);
    return n >= min && n <= max;
  }, message);

export const slotFormSchema: z.ZodType<SlotFormValues, SlotFormValues> = z.object({
  weekdays: z.array(z.number().int().min(0).max(6)).min(1, SLOT_MESSAGES.weekdays),
  start_time: z.string().trim().regex(TIME, SLOT_MESSAGES.startTime),
  duration_min: integerInRange(DURATION_MIN, DURATION_MAX, SLOT_MESSAGES.duration),
  capacity: integerInRange(CAPACITY_MIN, CAPACITY_MAX, SLOT_MESSAGES.capacity),
  coach_id: z.string(),
  name: z.string().trim().max(NAME_MAX, SLOT_MESSAGES.name),
  valid_from: z.string().refine((value) => value === "" || CIVIL_DATE.test(value), SLOT_MESSAGES.validFrom),
  is_active: z.boolean(),
});

export const EMPTY_SLOT_FORM: SlotFormValues = {
  weekdays: [],
  start_time: "",
  duration_min: "60",
  capacity: "",
  coach_id: "",
  name: "",
  valid_from: "",
  is_active: true,
};

export type SlotCreateBody = components["schemas"]["SlotCreate"];
export type SlotPatchBody = components["schemas"]["SlotPatch"];

export interface SlotSource {
  weekdays: readonly number[];
  start_time: string;
  duration_min: number;
  capacity: number;
  default_coach_id: string | null;
  name: string | null;
  valid_from: string;
  is_active: boolean;
}

const sorted = (days: readonly number[]): number[] => [...days].sort((a, b) => a - b);

/** «06:00» de una hora «06:00» o «06:00:00». */
export function hhmm(value: string): string {
  return value.slice(0, 5);
}

export function slotToFormValues(slot: SlotSource): SlotFormValues {
  return {
    weekdays: sorted(slot.weekdays),
    start_time: hhmm(slot.start_time),
    duration_min: String(slot.duration_min),
    capacity: String(slot.capacity),
    coach_id: slot.default_coach_id ?? "",
    name: slot.name ?? "",
    valid_from: slot.valid_from,
    is_active: slot.is_active,
  };
}

export function toSlotCreate(values: SlotFormValues): SlotCreateBody {
  const name = values.name.trim();
  return {
    weekdays: sorted(values.weekdays),
    start_time: values.start_time.trim(),
    duration_min: Number(values.duration_min),
    capacity: Number(values.capacity),
    default_coach_id: values.coach_id === "" ? null : values.coach_id,
    ...(name === "" ? {} : { name }),
    ...(values.valid_from === "" ? {} : { valid_from: values.valid_from }),
  };
}

/** Solo los campos que cambiaron respecto de la franja guardada. */
export function toSlotPatch(values: SlotFormValues, initial: SlotFormValues): SlotPatchBody {
  const patch: SlotPatchBody = {};
  const name = values.name.trim();
  if (sorted(values.weekdays).join() !== sorted(initial.weekdays).join()) patch.weekdays = sorted(values.weekdays);
  if (values.start_time.trim() !== initial.start_time) patch.start_time = values.start_time.trim();
  if (Number(values.duration_min) !== Number(initial.duration_min)) patch.duration_min = Number(values.duration_min);
  if (Number(values.capacity) !== Number(initial.capacity)) patch.capacity = Number(values.capacity);
  if (values.coach_id !== initial.coach_id) patch.default_coach_id = values.coach_id === "" ? null : values.coach_id;
  if (name !== initial.name) patch.name = name === "" ? null : name;
  if (values.valid_from !== initial.valid_from && values.valid_from !== "") patch.valid_from = values.valid_from;
  if (values.is_active !== initial.is_active) patch.is_active = values.is_active;
  return patch;
}

export const cancelReasonSchema = z.object({
  reason: z.string().trim().min(CANCEL_REASON_MIN).max(CANCEL_REASON_MAX),
});

/** «L M X J V» de los días de una franja, de lunes a domingo. */
export function weekdaysText(days: readonly number[]): string {
  return sorted(days)
    .map((day) => WEEKDAY_LETTERS[day] ?? "")
    .join(" ");
}
