// S7-F5 · US-163 (front): lo que la lista de socios dice de la última asistencia y de las clases que quedan.
// - lastAttendanceText: «hoy 06:02», «ayer 18:05», «14 oct 2026» (con año, DESIGN.md regla 7) y «Nunca» si no hay instante.
//   El día es el de Bogotá, no el del equipo.
// - membershipDetail suma «quedan N» a una tiquetera («12 clases · quedan 2 · vence ...»).
import { lastAttendanceText, membershipDetail } from "./memberRow";

const NOW = new Date("2026-10-20T15:00:00Z").getTime(); // mar 20 de octubre, 10:00 a. m. en Bogotá

describe("lastAttendanceText", () => {
  it("sin instante dice «Nunca»", () => {
    expect(lastAttendanceText(null, NOW)).toBe("Nunca");
    expect(lastAttendanceText(undefined, NOW)).toBe("Nunca");
  });

  it("hoy y ayer llevan la hora de Bogotá en 24 horas", () => {
    expect(lastAttendanceText("2026-10-20T12:02:00Z", NOW)).toBe("hoy 07:02");
    expect(lastAttendanceText("2026-10-19T23:05:00Z", NOW)).toBe("ayer 18:05");
  });

  it("el día es el de Bogotá: las 02:30 UTC del 20 son las 21:30 del 19", () => {
    expect(lastAttendanceText("2026-10-20T02:30:00Z", NOW)).toBe("ayer 21:30");
  });

  it("antes de ayer lleva la fecha con año", () => {
    expect(lastAttendanceText("2026-10-14T23:00:00Z", NOW)).toBe("14 oct 2026");
    expect(lastAttendanceText("2025-12-31T15:00:00Z", NOW)).toBe("31 dic 2025");
  });

  it("un instante inválido no lanza: dice «—»", () => {
    expect(lastAttendanceText("ayer", NOW)).toBe("—");
  });
});

describe("membershipDetail · tiquetera", () => {
  const base = { membership_status: "active", plan_name: "12 clases", membership_end_date: "2026-11-27" } as const;

  it("con clases que quedan las dice antes del vencimiento", () => {
    expect(membershipDetail({ ...base, membership_classes_remaining: 2 })).toBe("12 clases · quedan 2 · vence 27 nov 2026");
    expect(membershipDetail({ ...base, membership_classes_remaining: 1 })).toBe("12 clases · queda 1 · vence 27 nov 2026");
    expect(membershipDetail({ ...base, membership_classes_remaining: 0 })).toBe("12 clases · quedan 0 · vence 27 nov 2026");
  });

  it("sin clases (plan mensual) queda igual", () => {
    expect(membershipDetail({ ...base, plan_name: "Mensual", membership_classes_remaining: null })).toBe("Mensual · vence 27 nov 2026");
    expect(membershipDetail(base)).toBe("12 clases · vence 27 nov 2026");
  });
});
