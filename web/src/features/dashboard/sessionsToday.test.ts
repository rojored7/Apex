// S7-F6 (US-164): la próxima clase de hoy para el botón «Check-in» de Inicio.
import { nextCheckInSession } from "./sessionsToday";
import type { SessionTodayView } from "./schemas";

const session = (n: number, startsAt: string, status: SessionTodayView["status"] = "scheduled"): SessionTodayView => ({
  id: `aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaa0${String(n)}`,
  starts_at: startsAt,
  coach_name: null,
  capacity: 12,
  attendance_count: 0,
  duration_min: 60,
  status,
});

const AT = (iso: string): number => new Date(iso).getTime();

describe("nextCheckInSession", () => {
  const sessions = [session(1, "2026-10-20T11:00:00Z"), session(2, "2026-10-20T19:00:00Z"), session(3, "2026-10-20T22:00:00Z")];

  it("sin sesiones es null", () => {
    expect(nextCheckInSession([], AT("2026-10-20T10:00:00Z"))).toBeNull();
  });

  it("antes de la primera clase es la primera", () => {
    expect(nextCheckInSession(sessions, AT("2026-10-20T10:00:00Z"))?.id).toBe(sessions[0]?.id);
  });

  it("una clase empezada hace menos de su duración sigue siendo la próxima (se hace check-in en curso)", () => {
    expect(nextCheckInSession(sessions, AT("2026-10-20T19:30:00Z"))?.id).toBe(sessions[1]?.id);
  });

  it("pasada la hora de la clase salta a la siguiente", () => {
    expect(nextCheckInSession(sessions, AT("2026-10-20T20:01:00Z"))?.id).toBe(sessions[2]?.id);
  });

  it("ignora las canceladas y las terminadas", () => {
    const list = [session(1, "2026-10-20T19:00:00Z", "cancelled"), session(2, "2026-10-20T19:30:00Z", "done"), session(3, "2026-10-20T22:00:00Z")];
    expect(nextCheckInSession(list, AT("2026-10-20T18:00:00Z"))?.id).toBe(list[2]?.id);
  });

  it("si ya pasaron todas es null (el botón no aparece)", () => {
    expect(nextCheckInSession(sessions, AT("2026-10-21T03:00:00Z"))).toBeNull();
  });

  it("no depende del orden en que llegan", () => {
    const shuffled = [...sessions].reverse();
    expect(nextCheckInSession(shuffled, AT("2026-10-20T10:00:00Z"))?.id).toBe(sessions[0]?.id);
  });
});

describe("nextCheckInSession con duration_min", () => {
  const withDuration = (s: SessionTodayView, duration_min: number): SessionTodayView => ({ ...s, duration_min });

  it("una clase de 90 minutos sigue siendo la próxima a los 75 minutos de empezar", () => {
    const list = [withDuration(session(1, "2026-10-20T11:00:00Z"), 90), session(2, "2026-10-20T22:00:00Z")];
    expect(nextCheckInSession(list, AT("2026-10-20T12:15:00Z"))?.id).toBe(list[0]?.id);
  });

  it("una clase de 45 minutos ya no es la próxima a los 50 minutos de empezar", () => {
    const list = [withDuration(session(1, "2026-10-20T11:00:00Z"), 45), session(2, "2026-10-20T22:00:00Z")];
    expect(nextCheckInSession(list, AT("2026-10-20T11:50:00Z"))?.id).toBe(list[1]?.id);
  });
});
