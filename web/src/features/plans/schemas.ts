// S2-F7 · US-078 y US-079 (front): formulario del alta y filas de la lista de planes.
// - planFormSchema: las reglas de PlanCreate y validate_plan de B9 en el cliente (nombre de 1 a 80
//   tras recortar, precio entero en COP de 1 a 1.000.000.000, duración de 1 a 3.650 días y, solo
//   con `classes`, de 1 a 1.000 clases), con superRefine para la regla que cruza `kind` y
//   `class_count`. Los campos numéricos viajan como texto (lo que se ve en el campo) y
//   toPlanCreate los vuelve enteros. Mensajes "qué pasó y qué hacer".
// - priceInputText (desde S3-F3, moneyInputText de shared/lib/moneyInput.ts, reexportado): el precio
//   se escribe y se muestra con formatCop ("$ 120.000"). Se reformatea
//   un entero bien escrito ("120000", "$ 1.200") o un dígito escrito o borrado sobre un precio ya
//   formateado. Lo demás (una coma, un punto decimal como "1200.50", letras) queda como está y la
//   validación lo explica: nunca se convierte un decimal en otro monto (revisión M1).
// - planRowSchema, plansPageSchema, PLAN_KINDS y PlanKind viven desde S3-F3 en shared/data/plans.ts
//   (S3-D65) y se reexportan aquí. planRowSchema es PlanOut tal cual (precio entero, RN-01); una
//   forma inesperada es una respuesta inválida y no se pinta.
import { z } from "zod";
import type { components } from "../../core/api/types";
import { formatCop, formatCount, parseCop } from "../../core/i18n/format";
import { PLAN_KINDS, type PlanKind } from "../../shared/data/plans";
import { CUSTOM_ISSUE } from "../../shared/lib/zodIssues";

export { PLAN_KINDS, planRowSchema, plansPageSchema, type PlanKind, type PlanRowView } from "../../shared/data/plans";
/** S3-F3: el formato del precio al escribir vive en shared/lib/moneyInput.ts (lo usa también la venta). */
export { moneyInputText as priceInputText } from "../../shared/lib/moneyInput";

export type PlanCreateBody = components["schemas"]["PlanCreate"];
export type PlanOut = components["schemas"]["PlanOut"];
/** Planes.html: "Tipo de duración". */
export const PLAN_KIND_LABELS: Readonly<Record<PlanKind, string>> = { days: "Por días", classes: "Por número de clases" };

/** Topes de PlanCreate (api/src/app/modules/plans/schemas.py, S2-D32). */
export const PLAN_LIMITS = {
  nameMax: 80,
  priceMin: 1,
  priceMax: 1_000_000_000,
  durationMin: 1,
  durationMax: 3_650,
  classMin: 1,
  classMax: 1_000,
} as const;

export interface PlanFormValues {
  name: string;
  /** Lo que se ve en el campo, por ejemplo "$ 120.000". */
  price: string;
  kind: PlanKind;
  duration_days: string;
  class_count: string;
}

export const EMPTY_PLAN_FORM: PlanFormValues = { name: "", price: "", kind: "days", duration_days: "", class_count: "" };

export const PLAN_MESSAGES = {
  nameRequired: "Escribe el nombre del plan.",
  nameTooLong: `El nombre admite hasta ${String(PLAN_LIMITS.nameMax)} caracteres.`,
  nameRejected: "El servidor no aceptó este nombre. Revísalo e intenta de nuevo.",
  priceRequired: "Escribe el precio del plan.",
  priceInvalid: "Escribe el precio en pesos enteros, sin centavos (por ejemplo $ 120.000).",
  priceRange: `El precio debe estar entre ${formatCop(PLAN_LIMITS.priceMin)} y ${formatCop(PLAN_LIMITS.priceMax)}.`,
  kind: "Elige el tipo de duración: por días o por número de clases.",
  durationRequired: "Escribe cuántos días dura el plan.",
  durationRange: `La duración debe ser un número entero entre ${formatCount(PLAN_LIMITS.durationMin)} y ${formatCount(PLAN_LIMITS.durationMax)} días.`,
  classCountRequired: "Escribe cuántas clases incluye el plan.",
  classCountRange: `El número de clases debe ser un entero entre ${formatCount(PLAN_LIMITS.classMin)} y ${formatCount(PLAN_LIMITS.classMax)}.`,
  duplicated: "Ya existe un plan con este nombre. Usa otro nombre.",
} as const;

const INTEGER_TEXT = /^\d+$/;

/** Entero de un campo de texto ("30"), o null si no es un entero sin signo. */
function integerOf(text: string): number | null {
  const value = text.trim();
  return INTEGER_TEXT.test(value) ? Number(value) : null;
}

const inRange = (value: number | null, min: number, max: number): boolean => value !== null && value >= min && value <= max;

type AddIssue = (path: keyof PlanFormValues, message: string) => void;

function checkName(name: string, add: AddIssue): void {
  const trimmed = name.trim();
  // Puntos de código, como len() del api (Python), no unidades UTF-16 (revisión L5).
  if (trimmed === "") add("name", PLAN_MESSAGES.nameRequired);
  else if (Array.from(trimmed).length > PLAN_LIMITS.nameMax) add("name", PLAN_MESSAGES.nameTooLong);
}

function checkPrice(price: string, add: AddIssue): void {
  if (price.trim() === "") {
    add("price", PLAN_MESSAGES.priceRequired);
    return;
  }
  const value = parseCop(price);
  if (value === null) add("price", PLAN_MESSAGES.priceInvalid);
  else if (!inRange(value, PLAN_LIMITS.priceMin, PLAN_LIMITS.priceMax)) add("price", PLAN_MESSAGES.priceRange);
}

function checkDuration(days: string, add: AddIssue): void {
  if (days.trim() === "") add("duration_days", PLAN_MESSAGES.durationRequired);
  else if (!inRange(integerOf(days), PLAN_LIMITS.durationMin, PLAN_LIMITS.durationMax)) add("duration_days", PLAN_MESSAGES.durationRange);
}

/** validate_plan: el número de clases solo cuenta (y es obligatorio) en un plan por clases. */
function checkClassCount(kind: PlanKind, classes: string, add: AddIssue): void {
  if (kind !== "classes") return;
  if (classes.trim() === "") add("class_count", PLAN_MESSAGES.classCountRequired);
  else if (!inRange(integerOf(classes), PLAN_LIMITS.classMin, PLAN_LIMITS.classMax)) add("class_count", PLAN_MESSAGES.classCountRange);
}

export const planFormSchema: z.ZodType<PlanFormValues, PlanFormValues> = z
  .object({
    name: z.string(),
    price: z.string(),
    kind: z.enum(PLAN_KINDS, { error: PLAN_MESSAGES.kind }),
    duration_days: z.string(),
    class_count: z.string(),
  })
  .superRefine((values, ctx) => {
    const add: AddIssue = (path, message) => {
      ctx.addIssue({ code: CUSTOM_ISSUE, path: [path], message });
    };
    checkName(values.name, add);
    checkPrice(values.price, add);
    checkDuration(values.duration_days, add);
    checkClassCount(values.kind, values.class_count, add);
  });

/** Revisión L4: un formulario sin validar es un error de programación, no un 0 que el api rechace. */
function required(value: number | null, field: keyof PlanFormValues): number {
  if (value === null) throw new Error(`toPlanCreate: ${field} no pasó por planFormSchema`);
  return value;
}

/** El cuerpo de POST /plans a partir de un formulario ya validado. */
export function toPlanCreate(values: PlanFormValues): PlanCreateBody {
  const base: PlanCreateBody = {
    name: values.name.trim(),
    price_cop: required(parseCop(values.price), "price"),
    kind: values.kind,
    duration_days: required(integerOf(values.duration_days), "duration_days"),
  };
  return values.kind === "classes" ? { ...base, class_count: required(integerOf(values.class_count), "class_count") } : base;
}

/** El filtro `active` de la URL ("true" o "false"); cualquier otro valor no viaja. */
export const ACTIVE_FILTERS = ["true", "false"] as const;
export type ActiveFilter = (typeof ACTIVE_FILTERS)[number];

/** "1 día", "30 días". */
export function daysText(days: number): string {
  return days === 1 ? "1 día" : `${formatCount(days)} días`;
}

/** "1 clase", "12 clases". */
export function classesText(classes: number): string {
  return classes === 1 ? "1 clase" : `${formatCount(classes)} clases`;
}
