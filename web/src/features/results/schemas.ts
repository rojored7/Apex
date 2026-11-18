// S8-F4 · US-169 y US-170 (front): resultados en la tablet.
// - Respuestas (SessionAttendanceOut, ResultOut) validadas con Zod antes de usarse.
// - scoreFormSchema(scoreType, timeCapS): el formulario de marca. Tiempo mm:ss, rondas, repeticiones y carga en kg (0 a 1.000, hasta
//   dos decimales; el contrato lleva gramos enteros, S8-D41). «No terminó» (capped) solo con tiempo y time cap.
// - toScoreValues: los valores ya validados como los espera `PUT /results`.
// DESIGN-GAP: «Nota (opcional)» y «anterior en Helen» no están en el contrato (EP-24); el récord automático llega con EP-24.
import { z } from "zod";
import { formatClock, formatLoadKg, gramsToKgInput, isCountUpTo, kgInputToGrams, MAX_REPS, MAX_ROUNDS, parseClock } from "../../shared/data/score";
import type { components } from "../../core/api/types";

export const RESULT_LEVELS = ["rx", "rx_plus", "scaled"] as const;
export type ResultLevel = (typeof RESULT_LEVELS)[number];
export const LEVEL_SHORT: Readonly<Record<ResultLevel, string>> = { rx: "RX", rx_plus: "RX+", scaled: "Esc." };
export const LEVEL_FULL: Readonly<Record<ResultLevel, string>> = { rx: "RX", rx_plus: "RX+", scaled: "Escalado" };

export const SCORING_TYPES = ["time", "rounds_reps", "reps", "load"] as const;
export type ScoringType = (typeof SCORING_TYPES)[number];

/** El código de Zod para una regla propia (no es un código del api). */
const ISSUE_CODE = "custom" as const;

export const SCORE_MESSAGES = {
  time: "Escribe el tiempo como mm:ss, por ejemplo 11:42.",
  overCap: (cap: string): string => `El tiempo supera el límite de ${cap}. Marca «No terminó».`,
  cappedReps: "Escribe cuántas repeticiones completó.",
  rounds: "Escribe las rondas completas, de 0 a 1.000.",
  reps: "Escribe las repeticiones, de 0 a 100.000.",
  load: "Escribe la carga en kg, de 0 a 1.000, con hasta dos decimales.",
} as const;

export const resultSchema = z.object({
  id: z.string().min(1),
  wod_id: z.string().min(1),
  member_id: z.string().min(1),
  session_id: z.string().nullable(),
  level: z.enum(RESULT_LEVELS),
  seconds: z.number().int().nullable(),
  rounds: z.number().int().nullable(),
  reps: z.number().int().nullable(),
  load_g: z.number().int().nullable(),
  capped: z.boolean(),
  scaled_movement_ids: z.array(z.string()),
  is_current: z.boolean(),
  status: z.enum(["validated", "pending", "voided"]),
  source: z.enum(["desk", "kiosk"]),
  supersedes_id: z.string().nullable(),
});
export type ResultView = z.infer<typeof resultSchema>;

const scoringWodSchema = z.object({
  id: z.string().min(1),
  title: z.string(),
  score_type: z.enum(["time", "rounds_reps", "reps", "load", "none"]),
  time_cap_s: z.number().int().nullable(),
  movements: z.array(z.object({ movement_id: z.string().min(1), movement_name: z.string(), reps: z.string() })),
});
export type ScoringWod = z.infer<typeof scoringWodSchema>;

const attendeeResultSchema = z.object({
  member_id: z.string().min(1),
  first_name: z.string(),
  last_name: z.string(),
  has_result: z.boolean(),
  result: resultSchema.nullable(),
});
export type AttendeeResultView = z.infer<typeof attendeeResultSchema>;

export const sessionAttendanceSchema = z.object({
  session: z.object({
    id: z.string().min(1),
    session_date: z.string(),
    starts_at: z.string(),
    status: z.enum(["scheduled", "cancelled", "done"]),
    cancel_reason: z.string().nullable(),
    capacity: z.number().int(),
  }),
  wod: scoringWodSchema.nullable(),
  items: z.array(attendeeResultSchema),
  total: z.number().int().nonnegative(),
});
export type SessionAttendanceView = z.infer<typeof sessionAttendanceSchema>;

export const attendeeName = (attendee: Pick<AttendeeResultView, "first_name" | "last_name">): string => `${attendee.first_name} ${attendee.last_name}`.trim();

export interface ScoreFormValues {
  time: string;
  rounds: string;
  reps: string;
  load: string;
  capped: boolean;
  level: ResultLevel;
  scaled: string[];
}

export const emptyScoreForm: ScoreFormValues = { time: "", rounds: "", reps: "", load: "", capped: false, level: "rx", scaled: [] };

/** Lo que `PUT /results` recibe de la marca (el WOD, el socio y la sesión los pone la pantalla). */
export type ScoreValues = Pick<components["schemas"]["ResultIn"], "level" | "capped"> & {
  seconds: number | null;
  rounds: number | null;
  reps: number | null;
  load_g: number | null;
  scaled_movement_ids: string[];
};

/** El prellenado de una marca ya registrada. */
export function scoreFormFrom(result: ResultView | null): ScoreFormValues {
  if (result === null) return emptyScoreForm;
  return {
    time: result.capped || result.seconds === null ? "" : formatClock(result.seconds),
    rounds: result.rounds === null ? "" : String(result.rounds),
    reps: result.reps === null ? "" : String(result.reps),
    load: gramsToKgInput(result.load_g),
    capped: result.capped,
    level: result.level,
    scaled: result.scaled_movement_ids,
  };
}

export function scoreFormSchema(scoreType: ScoringType, timeCapS: number | null) {
  return z
    .object({
      time: z.string(),
      rounds: z.string(),
      reps: z.string(),
      load: z.string(),
      capped: z.boolean(),
      level: z.enum(RESULT_LEVELS),
      scaled: z.array(z.string()),
    })
    .superRefine((values, ctx) => {
      const fail = (path: keyof ScoreFormValues, message: string): void => {
        ctx.addIssue({ code: ISSUE_CODE, path: [path], message });
      };
      if (scoreType === "time") {
        if (values.capped) {
          if (!isCountUpTo(values.reps, MAX_REPS)) fail("reps", SCORE_MESSAGES.cappedReps);
          return;
        }
        const seconds = parseClock(values.time);
        if (seconds === null) fail("time", SCORE_MESSAGES.time);
        else if (timeCapS !== null && seconds > timeCapS) fail("time", SCORE_MESSAGES.overCap(formatClock(timeCapS)));
      }
      if (scoreType === "rounds_reps") {
        if (!isCountUpTo(values.rounds, MAX_ROUNDS)) fail("rounds", SCORE_MESSAGES.rounds);
        if (!isCountUpTo(values.reps, MAX_REPS)) fail("reps", SCORE_MESSAGES.reps);
      }
      if (scoreType === "reps" && !isCountUpTo(values.reps, MAX_REPS)) fail("reps", SCORE_MESSAGES.reps);
      if (scoreType === "load" && kgInputToGrams(values.load) === null) fail("load", SCORE_MESSAGES.load);
    });
}

/** Valores ya validados a la marca del contrato: solo los campos del tipo de marca (el api rechaza los demás). */
export function toScoreValues(values: ScoreFormValues, scoreType: ScoringType): ScoreValues {
  const capped = scoreType === "time" && values.capped;
  return {
    level: values.level,
    seconds: scoreType === "time" && !capped ? parseClock(values.time) : null,
    rounds: scoreType === "rounds_reps" ? Number(values.rounds.trim()) : null,
    reps: scoreType === "rounds_reps" || scoreType === "reps" || capped ? Number(values.reps.trim()) : null,
    load_g: scoreType === "load" ? kgInputToGrams(values.load) : null,
    capped,
    scaled_movement_ids: values.level === "scaled" ? values.scaled : [],
  };
}

/** «10:58 RX», «DNF · 135 reps», «5 + 12 Esc.»: la marca de la lista de asistentes. */
export function markText(result: ResultView, scoreType: ScoringType): string {
  const level = LEVEL_SHORT[result.level];
  if (result.capped) return `DNF · ${String(result.reps ?? 0)} reps ${level}`;
  switch (scoreType) {
    case "time":
      return `${result.seconds === null ? "—" : formatClock(result.seconds)} ${level}`;
    case "rounds_reps":
      return `${String(result.rounds ?? 0)} + ${String(result.reps ?? 0)} ${level}`;
    case "reps":
      return `${String(result.reps ?? 0)} reps ${level}`;
    case "load":
      return `${result.load_g === null ? "—" : formatLoadKg(result.load_g)} ${level}`;
  }
}

// S8-F5 · US-173: una fila de GET /members/{id}/results (MemberResultRow): el WOD copiado (título y fecha) y la marca.
export const memberResultRowSchema = z.object({
  id: z.string().min(1),
  wod_id: z.string().min(1),
  wod_title: z.string(),
  wod_date: z.string(),
  benchmark_id: z.string().nullable(),
  is_benchmark: z.boolean(),
  score_type: z.enum(["time", "rounds_reps", "reps", "load", "none"]),
  level: z.enum(RESULT_LEVELS),
  seconds: z.number().int().nullable(),
  rounds: z.number().int().nullable(),
  reps: z.number().int().nullable(),
  load_g: z.number().int().nullable(),
  capped: z.boolean(),
  status: z.enum(["validated", "pending", "voided"]),
  source: z.enum(["desk", "kiosk"]),
  session_id: z.string().nullable(),
  created_at: z.string(),
});
export type MemberResultRowView = z.infer<typeof memberResultRowSchema>;
