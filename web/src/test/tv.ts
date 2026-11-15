// S8-F6: datos de prueba de la pantalla de TV. Imitan TvBoard de GET /tv/today (C2): cargas en gramos enteros (S8-D41),
// ranking «Todos» con `Nombre I.` (nunca ids ni datos personales) y la marca en `score`.
export const TV_TOKEN = "tokenDePrueba0123456789abcdefABCDEF";

export interface TvRowFixture {
  display_name: string;
  level: "rx" | "rx_plus" | "scaled";
  position: number;
  score: { capped: boolean; load_g: number | null; reps: number | null; rounds: number | null; seconds: number | null };
}

export interface TvWodFixture {
  title: string;
  description: string;
  is_benchmark: boolean;
  score_type: "time" | "rounds_reps" | "reps" | "load" | "none";
  time_cap_s: number | null;
  movements: { name: string; reps: string; load_rx_m_g: number | null; load_rx_f_g: number | null }[];
}

export interface TvBoardFixture {
  date: string;
  refresh_seconds: number;
  wod: TvWodFixture | null;
  leaderboard: TvRowFixture[];
}

export function tvRow(position: number, name: string, seconds: number | null, overrides: Partial<TvRowFixture> = {}): TvRowFixture {
  return { display_name: name, level: "rx", position, score: { capped: false, load_g: null, reps: null, rounds: null, seconds }, ...overrides };
}

export function tvWod(overrides: Partial<TvWodFixture> = {}): TvWodFixture {
  return {
    title: "Helen",
    description: "3 rondas por tiempo",
    is_benchmark: true,
    score_type: "time",
    time_cap_s: 1200,
    movements: [
      { name: "Run 400 m", reps: "1", load_rx_m_g: null, load_rx_f_g: null },
      { name: "Kettlebell swing", reps: "21", load_rx_m_g: 24000, load_rx_f_g: 16000 },
      { name: "Pull-up", reps: "12", load_rx_m_g: null, load_rx_f_g: null },
    ],
    ...overrides,
  };
}

export function tvBoard(overrides: Partial<TvBoardFixture> = {}): TvBoardFixture {
  return {
    date: "2026-10-20",
    refresh_seconds: 30,
    wod: tvWod(),
    leaderboard: [tvRow(1, "Ana P.", 598), tvRow(2, "Luis M.", 644), tvRow(3, "Sara N.", null, { level: "scaled", score: { capped: true, load_g: null, reps: 15, rounds: 2, seconds: null } })],
    ...overrides,
  };
}

/** `count` filas ordenadas, de `Atleta 1 X.` en adelante. */
export function tvRows(count: number): TvRowFixture[] {
  return Array.from({ length: count }, (_, index) => tvRow(index + 1, `Atleta ${String(index + 1)} X.`, 600 + index));
}
