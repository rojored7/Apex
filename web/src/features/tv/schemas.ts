// S8-F6 · US-177: la forma de GET /tv/today (TvBoard del contrato, C2) validada con Zod antes de pintarla.
// Cargas en gramos enteros (S8-D41: `load_rx_m_g`, `load_rx_f_g` y `score.load_g`). Sin ids ni datos personales: el api solo manda
// `Nombre I.`, el nivel y la marca (S8-D18, S8-D19).
import { z } from "zod";

export const TV_SCORE_TYPES = ["time", "rounds_reps", "reps", "load", "none"] as const;
export const TV_LEVELS = ["rx", "rx_plus", "scaled"] as const;

const grams = z.number().int().nonnegative().nullable();

const tvMovementSchema = z.object({
  name: z.string(),
  reps: z.string(),
  load_rx_m_g: grams,
  load_rx_f_g: grams,
});

const tvWodSchema = z.object({
  title: z.string(),
  description: z.string(),
  is_benchmark: z.boolean(),
  score_type: z.enum(TV_SCORE_TYPES),
  time_cap_s: z.number().int().positive().nullable(),
  movements: z.array(tvMovementSchema),
});

const tvScoreSchema = z.object({
  capped: z.boolean(),
  load_g: grams,
  reps: z.number().int().nullable(),
  rounds: z.number().int().nullable(),
  seconds: z.number().int().nullable(),
});

const tvRowSchema = z.object({
  display_name: z.string(),
  level: z.enum(TV_LEVELS),
  position: z.number().int().positive(),
  score: tvScoreSchema,
});

/** El refresco que pide el api (S8-D33: de 15 a 300 s). */
export const tvBoardSchema = z.object({
  date: z.string(),
  refresh_seconds: z.number().int().min(15).max(300),
  wod: tvWodSchema.nullable(),
  /** M-3: con false el api manda el ranking vacío y la TV oculta el panel (no pinta «Registra tu resultado»). */
  show_leaderboard: z.boolean(),
  leaderboard: z.array(tvRowSchema),
});

export type TvBoardView = z.infer<typeof tvBoardSchema>;
export type TvWodView = NonNullable<TvBoardView["wod"]>;
export type TvRowView = TvBoardView["leaderboard"][number];
