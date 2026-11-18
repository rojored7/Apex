// S8-F3 (S8-D13, S8-D41): formato de marcas y cargas. El contrato lleva gramos enteros (0 a 1.000.000);
// la pantalla muestra kg con hasta dos decimales y coma decimal («102500 g» es «102,5 kg»).
// Lo comparten WODs, resultados, ficha y TV (una feature nunca importa de otra).

export const LOAD_MAX_G = 1_000_000;
const GRAMS_PER_KG = 1000;
const SECONDS_PER_MINUTE = 60;
const SECONDS_PER_HOUR = 3600;
const MAX_CLOCK_SECONDS = 86_400;
const CLOCK = /^([0-9]{1,4}):([0-5][0-9])$/;
const PLACEHOLDER = "—";

export const SCORE_KINDS = ["time", "rounds_reps", "reps", "load", "none"] as const;
export type ScoreKind = (typeof SCORE_KINDS)[number];

/** ¿El texto que manda el api es uno de los tipos de marca que la pantalla sabe leer? */
export function isScoreKind(value: string | null): value is ScoreKind {
  return value !== null && (SCORE_KINDS as readonly string[]).includes(value);
}

export interface ScoreValues {
  seconds: number | null;
  rounds: number | null;
  reps: number | null;
  load_g: number | null;
  capped: boolean;
}

const pad2 = (n: number): string => String(n).padStart(2, "0");

/** «4:05»; con horas, «1:02:05». */
export function formatSeconds(total: number): string {
  const hours = Math.floor(total / SECONDS_PER_HOUR);
  const minutes = Math.floor((total % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE);
  const seconds = total % SECONDS_PER_MINUTE;
  return hours > 0 ? `${String(hours)}:${pad2(minutes)}:${pad2(seconds)}` : `${String(minutes)}:${pad2(seconds)}`;
}

/** Segundos a «10:58» (con horas, «1:02:05»). */
export const formatClock = formatSeconds;

/** «11:42» a segundos, o null si no es un tiempo válido (1 s a 24 h). */
export function parseClock(text: string): number | null {
  const match = CLOCK.exec(text.trim());
  if (!match) return null;
  const seconds = Number(match[1]) * SECONDS_PER_MINUTE + Number(match[2]);
  return seconds >= 1 && seconds <= MAX_CLOCK_SECONDS ? seconds : null;
}

/** Gramos a «102,5 kg» (sin ceros sobrantes). */
export function formatLoadKg(grams: number): string {
  return `${gramsToKgInput(grams)} kg`;
}

/** Gramos al texto de un campo de kg: «102,5», «60», «» si no hay valor. */
export function gramsToKgInput(grams: number | null): string {
  if (grams === null) return "";
  const kg = grams / GRAMS_PER_KG;
  return String(Number(kg.toFixed(2))).replace(".", ",");
}

const KG_PATTERN = /^(\d{1,4})(?:[.,](\d{1,2}))?$/;

/** Texto de kg a gramos enteros, o null si no es una carga válida (0 a 1.000 kg, hasta dos decimales). */
export function kgInputToGrams(input: string): number | null {
  const match = KG_PATTERN.exec(input.trim());
  if (!match) return null;
  const whole = Number(match[1]);
  const decimals = (match[2] ?? "").padEnd(2, "0");
  const grams = whole * GRAMS_PER_KG + Number(decimals) * 10;
  return grams <= LOAD_MAX_G ? grams : null;
}

function roundsReps(values: ScoreValues): string | null {
  if (values.rounds !== null && values.reps !== null) return `${String(values.rounds)} + ${String(values.reps)}`;
  if (values.reps !== null) return `${String(values.reps)} reps`;
  return null;
}

/** La marca como se lee en pantalla: «4:05», «DNF · 2 + 15», «5 + 12», «150 reps», «102,5 kg». */
export function formatScore(scoreType: ScoreKind, values: ScoreValues): string {
  if (values.capped) {
    const done = roundsReps(values);
    return done ? `DNF · ${done}` : "DNF";
  }
  switch (scoreType) {
    case "time":
      return values.seconds === null ? PLACEHOLDER : formatSeconds(values.seconds);
    case "rounds_reps":
    case "reps":
      return roundsReps(values) ?? PLACEHOLDER;
    case "load":
      return values.load_g === null ? PLACEHOLDER : formatLoadKg(values.load_g);
    default:
      return PLACEHOLDER;
  }
}

/** El tipo de marca de un WOD en palabras de la pantalla. */
export const SCORE_TYPE_LABELS: Readonly<Record<ScoreKind, string>> = {
  time: "Por tiempo",
  rounds_reps: "Rondas + repeticiones",
  reps: "Repeticiones",
  load: "Carga",
  none: "Sin marca",
};

/** S9-F1 (US-178): gramos a «61,2 kg» (un decimal fijo, coma decimal) para el peso corporal. */
export function formatWeightKg(grams: number): string {
  return `${(grams / GRAMS_PER_KG).toFixed(1).replace(".", ",")} kg`;
}

const MINUS = "−";
const NO_CHANGE = "Sin cambio";

function signed(delta: number, text: string): string {
  return `${delta < 0 ? MINUS : "+"}${text}`;
}

/** La diferencia de un solo número (segundos, repeticiones o gramos) con su signo, o «Sin cambio». */
function numericDelta(current: number, previous: number, format: (absolute: number) => string): string {
  const delta = current - previous;
  return delta === 0 ? NO_CHANGE : signed(delta, format(Math.abs(delta)));
}

/**
 * S9-F2 (US-183): la diferencia entre dos marcas del mismo tipo y nivel, con signo (el «−» es U+2212):
 * tiempo «−0:28» o «+1:05», repeticiones «+5 reps», carga «+2,5 kg»; igual, «Sin cambio». `null` si no se pueden comparar:
 * rondas + repeticiones (hace falta el tamaño de la ronda), marcas cortadas (DNF), datos que faltan o sin marca.
 */
export function formatScoreDelta(scoreType: ScoreKind, current: ScoreValues, previous: ScoreValues): string | null {
  if (current.capped || previous.capped) return null;
  switch (scoreType) {
    case "time":
      return current.seconds === null || previous.seconds === null ? null : numericDelta(current.seconds, previous.seconds, formatSeconds);
    case "reps":
      return current.reps === null || previous.reps === null ? null : numericDelta(current.reps, previous.reps, (n) => `${String(n)} reps`);
    case "load":
      return current.load_g === null || previous.load_g === null ? null : numericDelta(current.load_g, previous.load_g, formatLoadKg);
    default:
      return null;
  }
}
