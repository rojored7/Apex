// S7-F3 · US-157 (front): semanas ISO de la pantalla Sesiones. `?semana=AAAA-Www` (lunes a domingo, calendario de Bogotá;
// una fecha civil no cambia de zona). Funciones puras: ninguna lee el reloj salvo currentWeek().
// - parseWeek: «2026-W43» válida (2020 a 2100, la semana existe ese año) o null.
// - weekDates: las siete fechas civiles de lunes a domingo; shiftWeek: la semana n semanas después o antes.
// - isoWeekOf: la semana a la que pertenece una fecha civil. currentWeek: la de hoy en Bogotá.
// - weekLabel: «Semana del 19 al 25 de octubre de 2026»; dayHeader: «Lun 19».
import { addDaysCivil, todayBogota } from "../../core/i18n/format";

const WEEK_PATTERN = /^(\d{4})-W(\d{2})$/;
const MIN_YEAR = 2020;
const MAX_YEAR = 2100;
const DAYS_PER_WEEK = 7;
const MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"] as const;
const DAY_SHORT = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"] as const;

interface Civil {
  year: number;
  month: number;
  day: number;
}

function parseCivil(value: string): Civil | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!match) return null;
  const civil = { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
  const date = new Date(Date.UTC(civil.year, civil.month - 1, civil.day));
  const isReal = date.getUTCFullYear() === civil.year && date.getUTCMonth() === civil.month - 1 && date.getUTCDate() === civil.day;
  return isReal ? civil : null;
}

/** Día de la semana ISO: 1 (lunes) a 7 (domingo). */
function isoWeekday(civil: Civil): number {
  const day = new Date(Date.UTC(civil.year, civil.month - 1, civil.day)).getUTCDay();
  return day === 0 ? DAYS_PER_WEEK : day;
}

const pad2 = (n: number): string => String(n).padStart(2, "0");

/** El jueves de la semana de una fecha decide el año ISO. */
export function isoWeekOf(date: string): string | null {
  const civil = parseCivil(date);
  if (!civil) return null;
  const thursday = parseCivil(addDaysCivil(date, 4 - isoWeekday(civil)) ?? "");
  if (!thursday) return null;
  const yearStart = Date.UTC(thursday.year, 0, 1);
  const days = Math.round((Date.UTC(thursday.year, thursday.month - 1, thursday.day) - yearStart) / 86_400_000);
  return `${String(thursday.year)}-W${pad2(Math.floor(days / DAYS_PER_WEEK) + 1)}`;
}

/** Lunes de una semana ISO («2026-W43» → «2026-10-19»); null si la semana no es válida. */
function weekStart(week: string): string | null {
  const match = WEEK_PATTERN.exec(week);
  if (!match) return null;
  const year = Number(match[1]);
  const number = Number(match[2]);
  if (year < MIN_YEAR || year > MAX_YEAR || number < 1) return null;
  const january4 = `${String(year)}-01-04`;
  const parsed = parseCivil(january4);
  if (!parsed) return null;
  const monday = addDaysCivil(january4, 1 - isoWeekday(parsed) + (number - 1) * DAYS_PER_WEEK);
  // La semana existe ese año si su lunes vuelve a dar la misma semana (la 53 no existe en todos los años).
  return monday !== null && isoWeekOf(monday) === week ? monday : null;
}

/** La semana si es `AAAA-Www` válida (2020 a 2100, existente en el calendario ISO); si no, null. */
export function parseWeek(value: string | null): string | null {
  return value !== null && weekStart(value) !== null ? value : null;
}

/** Las siete fechas civiles de la semana, de lunes a domingo; lista vacía si la semana no es válida. */
export function weekDates(week: string): string[] {
  const monday = weekStart(week);
  if (monday === null) return [];
  return Array.from({ length: DAYS_PER_WEEK }, (_, index) => addDaysCivil(monday, index) ?? monday);
}

/** La semana `count` semanas después (o antes si es negativo); null si cae fuera de 2020 a 2100. */
export function shiftWeek(week: string, count: number): string | null {
  const monday = weekStart(week);
  if (monday === null) return null;
  const shifted = addDaysCivil(monday, count * DAYS_PER_WEEK);
  const result = shifted === null ? null : isoWeekOf(shifted);
  return result !== null && parseWeek(result) !== null ? result : null;
}

/** La semana de hoy en Bogotá. */
export function currentWeek(): string {
  return isoWeekOf(todayBogota()) ?? "";
}

/** «Semana del 19 al 25 de octubre de 2026» (con mes o año de cada extremo si cambian). */
export function weekLabel(week: string): string {
  const dates = weekDates(week);
  const first = parseCivil(dates[0] ?? "");
  const last = parseCivil(dates[DAYS_PER_WEEK - 1] ?? "");
  if (!first || !last) return "";
  const month = (c: Civil): string => MONTHS[c.month - 1] ?? "";
  if (first.year !== last.year) return `Semana del ${String(first.day)} de ${month(first)} de ${String(first.year)} al ${String(last.day)} de ${month(last)} de ${String(last.year)}`;
  if (first.month !== last.month) return `Semana del ${String(first.day)} de ${month(first)} al ${String(last.day)} de ${month(last)} de ${String(last.year)}`;
  return `Semana del ${String(first.day)} al ${String(last.day)} de ${month(last)} de ${String(last.year)}`;
}

/** «Lun 19» de una fecha civil. */
export function dayHeader(date: string): string {
  const civil = parseCivil(date);
  if (!civil) return "";
  return `${DAY_SHORT[isoWeekday(civil) - 1] ?? ""} ${String(civil.day)}`;
}


const MONTH_SHORT = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"] as const;

/** «mar 20 oct» de una fecha civil (el título del detalle de una sesión). */
export function shortDate(date: string): string {
  const civil = parseCivil(date);
  if (!civil) return "";
  return `${(DAY_SHORT[isoWeekday(civil) - 1] ?? "").toLowerCase()} ${String(civil.day)} ${MONTH_SHORT[civil.month - 1] ?? ""}`;
}
