// S8-F3 (S8-D13, S8-D41): formato de marcas y cargas. El contrato lleva gramos enteros (0 a 1.000.000);
// la pantalla muestra kg con hasta dos decimales y coma decimal («102500 g» es «102,5 kg»).
// Lo comparten WODs, resultados, ficha y TV (una feature nunca importa de otra).

export const LOAD_MAX_G = 1_000_000;
const GRAMS_PER_KG = 1000;
const SECONDS_PER_MINUTE = 60;
const SECONDS_PER_HOUR = 3600;
const PLACEHOLDER = "—";

export type ScoreKind = "time" | "rounds_reps" | "reps" | "load" | "none";

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
