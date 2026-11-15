// S7-F6 (US-164): la «próxima clase» de Inicio, para el botón «Check-in» del encabezado.
// Una sesión programada cuenta como próxima hasta que termina (`starts_at + duration_min`, igual que
// SessionsPage), así se hace check-in con la clase en curso.
import type { SessionTodayView } from "./schemas";

const MS_PER_MIN = 60_000;

/** La primera sesión programada de hoy que aún no termina; null si no queda ninguna. */
export function nextCheckInSession(sessions: readonly SessionTodayView[], nowMs: number): SessionTodayView | null {
  const open = sessions.filter((s) => s.status === "scheduled" && new Date(s.starts_at).getTime() + s.duration_min * MS_PER_MIN > nowMs);
  return [...open].sort((a, b) => a.starts_at.localeCompare(b.starts_at))[0] ?? null;
}
