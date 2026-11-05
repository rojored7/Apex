// S5-F4 · US-139 (front): el rango de la exportación de pagos. `GET /payments/export` exige `from` y
// `to` (S5-D41, B12) con un rango de a lo sumo 12 meses de Bogotá (el `to` exclusivo no pasa de un
// año después de `from`). Se valida aquí con Zod antes de llamar, con las mismas fechas civiles del
// filtro "Fecha del pago"; el api vuelve a validar (422 con `field`).
import { z } from "zod";
import { addDaysCivil, bogotaInputToUtc } from "../../core/i18n/format";
import { CUSTOM_ISSUE } from "../../shared/lib/zodIssues";

export const EXPORT_RANGE_MESSAGES = {
  fromRequired: "Elige la fecha 'Desde' del filtro 'Fecha del pago' antes de exportar.",
  toRequired: "Elige la fecha 'Hasta' del filtro 'Fecha del pago' antes de exportar.",
  inverted: "La fecha 'Hasta' es anterior a 'Desde'. Corrígela para exportar.",
  tooLong: "El rango de la exportación puede ser de 12 meses como máximo. Acorta las fechas e intenta de nuevo.",
} as const;

const CIVIL = /^\d{4}-\d{2}-\d{2}$/;
const FEB = 2;
const LEAP_DAY = 29;
const FEB_LAST_COMMON = 28;

const civilDay = (message: string) =>
  z
    .string()
    .regex(CIVIL, message)
    .refine((value) => addDaysCivil(value, 0) === value, message);

/** El mismo día un año después; el 29 de febrero pasa al 28 (igual que el api). */
function sameDayNextYear(day: string): string {
  const [year = "", month = "", date = ""] = day.split("-");
  const leapDay = Number(month) === FEB && Number(date) === LEAP_DAY;
  return `${String(Number(year) + 1).padStart(4, "0")}-${month}-${leapDay ? String(FEB_LAST_COMMON) : date}`;
}

export const paymentsExportRangeSchema = z
  .object({ from: civilDay(EXPORT_RANGE_MESSAGES.fromRequired), to: civilDay(EXPORT_RANGE_MESSAGES.toRequired) })
  .superRefine((range, ctx) => {
    if (range.to < range.from) {
      ctx.addIssue({ code: CUSTOM_ISSUE, path: ["to"], message: EXPORT_RANGE_MESSAGES.inverted });
      return;
    }
    const exclusiveEnd = addDaysCivil(range.to, 1);
    if (exclusiveEnd !== null && exclusiveEnd > sameDayNextYear(range.from)) {
      ctx.addIssue({ code: CUSTOM_ISSUE, path: ["to"], message: EXPORT_RANGE_MESSAGES.tooLong });
    }
  });

export type PaymentsExportRange = z.infer<typeof paymentsExportRangeSchema>;

export interface PaymentsExportFilters {
  q?: string;
  method?: string;
  registered_by?: string;
  voided?: boolean;
}

export interface PaymentsExportQuery extends PaymentsExportFilters {
  from: string;
  to: string;
}

/** El primer mensaje de un rango inválido, o null si es válido. */
export function exportRangeError(range: { from: string; to: string }): string | null {
  const result = paymentsExportRangeSchema.safeParse(range);
  return result.success ? null : (result.error.issues[0]?.message ?? EXPORT_RANGE_MESSAGES.fromRequired);
}

/** Los parámetros de GET /payments/export: el rango en UTC (`[from, to)`, D26) y los filtros vigentes. */
export function toPaymentsExportQuery(range: PaymentsExportRange, filters: PaymentsExportFilters): PaymentsExportQuery {
  const from = bogotaInputToUtc(`${range.from}T00:00`);
  const nextDay = addDaysCivil(range.to, 1);
  const to = nextDay === null ? null : bogotaInputToUtc(`${nextDay}T00:00`);
  if (from === null || to === null) throw new Error("toPaymentsExportQuery: rango no validado");
  return { ...filters, from, to };
}
