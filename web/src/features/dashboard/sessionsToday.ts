// S7-F6 (US-164): la «próxima clase» de Inicio, para el botón «Check-in» del encabezado.
// DESIGN-GAP: `sessions_today` no trae la duración de la clase; una sesión programada cuenta como
// próxima hasta una hora después de empezar (así se hace check-in con la clase en curso).
import type { SessionTodayView } from "./schemas";

/** Minutos después del inicio en que una clase programada sigue siendo la «próxima». */
export const CLASS_WINDOW_MIN = 60;
const MS_PER_MIN = 60_000;

/** La primera sesión programada de hoy que aún no pasó su ventana; null si no queda ninguna. */
export function nextCheckInSession(sessions: readonly SessionTodayView[], nowMs: number): SessionTodayView | null {
  const open = sessions.filter((s) => s.status === "scheduled" && new Date(s.starts_at).getTime() + CLASS_WINDOW_MIN * MS_PER_MIN > nowMs);
  return [...open].sort((a, b) => a.starts_at.localeCompare(b.starts_at))[0] ?? null;
}
