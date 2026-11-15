// S7-F3 · US-157 (front): semanas ISO de la pantalla Sesiones (funciones puras).
import { bogotaTime, dayHeader, isoWeekOf, parseWeek, shiftWeek, shortDate, weekDates, weekLabel } from "./weeks";

describe("weeks", () => {
  it("parseWeek acepta AAAA-Www válidas y rechaza el resto", () => {
    expect(parseWeek("2026-W43")).toBe("2026-W43");
    expect(parseWeek("2026-W53")).toBe("2026-W53");
    for (const bad of [null, "", "2026-43", "2026-W00", "2026-W54", "2027-W53", "2019-W52", "2101-W01", "2026-w43", "hoy"]) expect(parseWeek(bad)).toBeNull();
  });

  it("isoWeekOf usa el jueves de la semana: 1 de enero de 2027 es de la semana 53 de 2026", () => {
    expect(isoWeekOf("2026-10-20")).toBe("2026-W43");
    expect(isoWeekOf("2026-10-19")).toBe("2026-W43");
    expect(isoWeekOf("2026-10-25")).toBe("2026-W43");
    expect(isoWeekOf("2027-01-01")).toBe("2026-W53");
    expect(isoWeekOf("2024-12-30")).toBe("2025-W01");
    expect(isoWeekOf("2026-02-30")).toBeNull();
  });

  it("weekDates da de lunes a domingo y vacía si la semana no es válida", () => {
    expect(weekDates("2026-W43")).toEqual(["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24", "2026-10-25"]);
    expect(weekDates("2026-W53")[6]).toBe("2027-01-03");
    expect(weekDates("2027-W53")).toEqual([]);
  });

  it("shiftWeek avanza y retrocede, cruza de año y no sale de 2020 a 2100", () => {
    expect(shiftWeek("2026-W43", 1)).toBe("2026-W44");
    expect(shiftWeek("2026-W43", -1)).toBe("2026-W42");
    expect(shiftWeek("2026-W53", 1)).toBe("2027-W01");
    expect(shiftWeek("2020-W01", -1)).toBeNull();
    expect(shiftWeek("2100-W52", 5)).toBeNull();
    expect(shiftWeek("nope", 1)).toBeNull();
  });

  it("weekLabel dice mes y año solo donde cambian", () => {
    expect(weekLabel("2026-W43")).toBe("Semana del 19 al 25 de octubre de 2026");
    expect(weekLabel("2026-W40")).toBe("Semana del 28 de septiembre al 4 de octubre de 2026");
    expect(weekLabel("2026-W53")).toBe("Semana del 28 de diciembre de 2026 al 3 de enero de 2027");
    expect(weekLabel("x")).toBe("");
  });

  it("dayHeader y bogotaTime", () => {
    expect(dayHeader("2026-10-19")).toBe("Lun 19");
    expect(dayHeader("2026-10-25")).toBe("Dom 25");
    expect(dayHeader("no")).toBe("");
    expect(bogotaTime("2026-10-19T11:00:00Z")).toBe("06:00");
    expect(bogotaTime("2026-10-20T03:30:00Z")).toBe("22:30");
    expect(bogotaTime("basura")).toBe("");
    expect(shortDate("2026-10-20")).toBe("mar 20 oct");
    expect(shortDate("no")).toBe("");
  });
});
