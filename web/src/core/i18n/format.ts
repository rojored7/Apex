// US-060: único lugar de formato de dinero y fechas del front.
// - Dinero: entero en COP (RN-01), "$ 120.000", sin decimales.
// - Fechas civiles (AAAA-MM-DD) sin conversión de zona; instantes UTC en hora de Bogotá.
// El texto se arma con tablas propias a partir de las partes numéricas de Intl, para que
// no dependa de la versión de ICU (espacio duro, "p. m." con espacio fino, mes con punto).
import { LOCALE, TZ_DISPLAY } from "../../config/locale";

export const MONEY_INVALID = "El monto debe ser un número entero en pesos";

/** Texto que se muestra cuando un valor no se puede formatear. */
export const EMPTY_VALUE = "—";

const MONTHS_SHORT = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"] as const;
const MONTHS_LONG = [
  "enero",
  "febrero",
  "marzo",
  "abril",
  "mayo",
  "junio",
  "julio",
  "agosto",
  "septiembre",
  "octubre",
  "noviembre",
  "diciembre",
] as const;

const integerFormat = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0, useGrouping: true });

const bogotaParts = new Intl.DateTimeFormat("en-US", {
  timeZone: TZ_DISPLAY,
  year: "numeric",
  month: "numeric",
  day: "numeric",
  hour: "numeric",
  minute: "numeric",
  hourCycle: "h23",
});

const CIVIL_DATE = /^(\d{4})-(\d{2})-(\d{2})$/;
const CIVIL_MONTH = /^(\d{4})-(\d{2})$/;
const ISO_INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/;
const MONEY_INPUT = /^(\d+|\d{1,3}(\.\d{3})+)$/;

interface CivilDate {
  year: number;
  month: number; // 1..12
  day: number;
}

interface BogotaInstant extends CivilDate {
  hour: number; // 0..23
  minute: number;
}

/** Espacio duro (U+00A0) y espacio fino duro (U+202F) que ICU puede intercalar. */
const HARD_SPACES = new RegExp(`[${String.fromCharCode(0x00a0, 0x202f)}]`, "g");

/** Separador de miles colombiano ("1.250"), con espacios normales. */
function groupDigits(value: number): string {
  return integerFormat.format(value).replace(HARD_SPACES, " ");
}

/** "$ 120.000". En desarrollo un monto no entero lanza; en producción muestra una raya. */
export function formatCop(amount: number): string {
  if (!Number.isInteger(amount)) {
    if (import.meta.env.DEV) {
      throw new Error(`formatCop: el monto debe ser un entero en COP (RN-01), llegó ${String(amount)}`);
    }
    return EMPTY_VALUE;
  }
  const sign = amount < 0 ? "-" : "";
  return `${sign}$ ${groupDigits(Math.abs(amount))}`;
}

/** Conteo con separador de miles: "1.250". */
export function formatCount(value: number): string {
  return Number.isFinite(value) ? groupDigits(Math.trunc(value)) : EMPTY_VALUE;
}

/** "$ 120.000", "120.000" o "120000" dan 120000; decimales, negativos o texto dan null. */
export function parseCop(input: string): number | null {
  const compact = input.trim().replace(/^\$/, "").replace(/\s+/g, "");
  if (!MONEY_INPUT.test(compact)) return null;
  const value = Number(compact.replace(/\./g, ""));
  return Number.isSafeInteger(value) ? value : null;
}

function isValidCivil({ year, month, day }: CivilDate): boolean {
  if (month < 1 || month > 12 || day < 1) return false;
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return day <= daysInMonth;
}

function parseCivilDate(value: string): CivilDate | null {
  const match = CIVIL_DATE.exec(value);
  if (!match) return null;
  const civil = { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
  return isValidCivil(civil) ? civil : null;
}

function toBogota(isoUtc: string): BogotaInstant | null {
  if (!ISO_INSTANT.test(isoUtc)) return null;
  const date = new Date(isoUtc);
  if (Number.isNaN(date.getTime())) return null;
  const parts: Record<string, number> = {};
  for (const part of bogotaParts.formatToParts(date)) {
    if (part.type !== "literal") parts[part.type] = Number(part.value);
  }
  return {
    year: parts.year ?? 0,
    month: parts.month ?? 0,
    day: parts.day ?? 0,
    hour: parts.hour ?? 0,
    minute: parts.minute ?? 0,
  };
}

/** Fecha civil de una fecha "AAAA-MM-DD" (tal cual) o de un instante UTC (en Bogotá). */
function civilOf(value: string): CivilDate | null {
  return CIVIL_DATE.test(value) ? parseCivilDate(value) : toBogota(value);
}

function civilText({ year, month, day }: CivilDate): string {
  return `${String(day)} ${MONTHS_SHORT[month - 1] ?? ""} ${String(year)}`;
}

function timeText({ hour, minute }: BogotaInstant): string {
  const hour12 = hour % 12 === 0 ? 12 : hour % 12;
  const suffix = hour < 12 ? "a. m." : "p. m.";
  return `${String(hour12)}:${String(minute).padStart(2, "0")} ${suffix}`;
}

/** "20 oct 2026". Una fecha civil no se convierte de zona; un instante se lleva a Bogotá. */
export function formatDate(value: string): string {
  const civil = civilOf(value);
  return civil ? civilText(civil) : EMPTY_VALUE;
}

/** "20 oct 2026, 9:30 p. m." en hora de Bogotá. */
export function formatDateTime(isoUtc: string): string {
  const instant = toBogota(isoUtc);
  return instant ? `${civilText(instant)}, ${timeText(instant)}` : EMPTY_VALUE;
}

/** "9:30 p. m." en hora de Bogotá. */
export function formatTime(isoUtc: string): string {
  const instant = toBogota(isoUtc);
  return instant ? timeText(instant) : EMPTY_VALUE;
}

/** "octubre 2026" a partir de "AAAA-MM", "AAAA-MM-DD" o un instante UTC (en Bogotá). */
export function formatMonth(value: string): string {
  const monthMatch = CIVIL_MONTH.exec(value);
  const civil = monthMatch ? { year: Number(monthMatch[1]), month: Number(monthMatch[2]), day: 1 } : civilOf(value);
  if (!civil || civil.month < 1 || civil.month > 12) return EMPTY_VALUE;
  return `${MONTHS_LONG[civil.month - 1] ?? ""} ${String(civil.year)}`;
}

/** Fecha civil de hoy en Bogotá ("AAAA-MM-DD"), la misma que today_bogota() del api (Q28). */
export function todayBogota(): string {
  const now = toBogota(new Date().toISOString());
  /* v8 ignore next -- toISOString siempre produce un instante válido */
  if (!now) throw new Error("todayBogota: reloj inválido");
  const pad = (n: number): string => String(n).padStart(2, "0");
  return `${String(now.year)}-${pad(now.month)}-${pad(now.day)}`;
}

// S3-F3: fechas de los formularios en hora de Bogotá. Colombia no tiene horario de verano: la
// hora de Bogotá es siempre UTC-5, así que pasar del campo `datetime-local` (que el navegador
// no asocia a ninguna zona) a un instante UTC es una suma fija, sin depender de la zona del equipo.
const BOGOTA_OFFSET_HOURS = 5;
const DATETIME_INPUT = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/;
const MS_PER_DAY = 86_400_000;

const pad2 = (n: number): string => String(n).padStart(2, "0");

function civilIso({ year, month, day }: CivilDate): string {
  return `${String(year)}-${pad2(month)}-${pad2(day)}`;
}

/** "AAAA-MM-DDTHH:mm" de ahora en Bogotá: el valor inicial de un campo `datetime-local`. */
export function nowBogotaInput(nowMs: number = Date.now()): string {
  const now = toBogota(new Date(nowMs).toISOString());
  /* v8 ignore next -- toISOString siempre produce un instante válido */
  if (!now) throw new Error("nowBogotaInput: reloj inválido");
  return `${civilIso(now)}T${pad2(now.hour)}:${pad2(now.minute)}`;
}

/** El valor de un `datetime-local` leído como hora de Bogotá, en UTC ISO; null si no es válido. */
export function bogotaInputToUtc(value: string): string | null {
  const match = DATETIME_INPUT.exec(value);
  if (!match) return null;
  const civil = { year: Number(match[1]), month: Number(match[2]), day: Number(match[3]) };
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  if (!isValidCivil(civil) || hour > 23 || minute > 59) return null;
  return new Date(Date.UTC(civil.year, civil.month - 1, civil.day, hour + BOGOTA_OFFSET_HOURS, minute)).toISOString();
}

/** Fecha civil "AAAA-MM-DD" más `days` días; null si no es una fecha real. */
export function addDaysCivil(value: string, days: number): string | null {
  const civil = parseCivilDate(value);
  if (!civil) return null;
  const date = new Date(Date.UTC(civil.year, civil.month - 1, civil.day) + days * MS_PER_DAY);
  return civilIso({ year: date.getUTCFullYear(), month: date.getUTCMonth() + 1, day: date.getUTCDate() });
}
