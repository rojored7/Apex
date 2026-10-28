// @vitest-environment node
// US-060 T1: formato de dinero y fechas. Todo debe dar lo mismo sin importar la zona
// horaria del equipo: cada caso de fechas se repite con TZ=UTC, Asia/Tokyo y
// America/New_York (Node aplica process.env.TZ en caliente, sin cross-env).
import {
  MONEY_INVALID,
  formatCop,
  formatCount,
  formatDate,
  formatDateRange,
  formatDateTime,
  formatMonth,
  formatTime,
  parseCop,
  todayBogota,
  addDaysCivil,
  civilDaysBetween,
  bogotaInputToUtc,
  nowBogotaInput,
} from "./format";
import { LOCALE, TZ_DISPLAY } from "../../config/locale";

const ZONES = ["UTC", "Asia/Tokyo", "America/New_York"] as const;
const ORIGINAL_TZ = process.env.TZ;

afterEach(() => {
  if (ORIGINAL_TZ === undefined) delete process.env.TZ;
  else process.env.TZ = ORIGINAL_TZ;
  vi.useRealTimers();
  vi.unstubAllEnvs();
});

describe("configuración regional", () => {
  it("es español de Colombia con hora de Bogotá", () => {
    expect(LOCALE).toBe("es-CO");
    expect(TZ_DISPLAY).toBe("America/Bogota");
  });
});

describe("formatCop", () => {
  it.each([
    [120000, "$ 120.000"],
    [0, "$ 0"],
    [999, "$ 999"],
    [1000000, "$ 1.000.000"],
    [50000000, "$ 50.000.000"],
  ])("formatea %i como %s, sin decimales y con espacio normal", (amount, expected) => {
    expect(formatCop(amount)).toBe(expected);
  });

  it("formatea un monto negativo con el signo delante", () => {
    expect(formatCop(-5000)).toBe("-$ 5.000");
  });

  it("lanza en desarrollo si el monto no es entero (RN-01)", () => {
    expect(() => formatCop(1.5)).toThrow(/entero/);
    expect(() => formatCop(Number.NaN)).toThrow(/entero/);
  });

  it("devuelve una raya en producción si el monto no es entero", () => {
    vi.stubEnv("DEV", false);
    expect(formatCop(1.5)).toBe("—");
  });
});

describe("formatCount", () => {
  it.each([
    [0, "0"],
    [999, "999"],
    [1250, "1.250"],
    [1000000, "1.000.000"],
  ])("formatea %i como %s", (value, expected) => {
    expect(formatCount(value)).toBe(expected);
  });

  it("no formatea un número no finito", () => {
    expect(formatCount(Number.POSITIVE_INFINITY)).toBe("—");
  });
});

describe("parseCop", () => {
  it.each([
    ["$ 120.000", 120000],
    ["120000", 120000],
    ["120.000", 120000],
    ["  $120.000  ", 120000],
    ["0", 0],
    ["1.000.000", 1000000],
  ])("interpreta %j como %i", (input, expected) => {
    expect(parseCop(input)).toBe(expected);
  });

  it.each(["120.000,50", "-5", "", "   ", "abc", "12.00", "1.2345", "$", "1e5"])("rechaza %j", (input) => {
    expect(parseCop(input)).toBeNull();
  });

  it("expone el mensaje de error compartido para los formularios", () => {
    expect(MONEY_INVALID).toBe("El monto debe ser un número entero en pesos");
  });
});

describe.each(ZONES)("fechas con TZ=%s", (zone) => {
  beforeEach(() => {
    process.env.TZ = zone;
  });

  it("formatDate trata AAAA-MM-DD como fecha civil, sin conversión de zona", () => {
    expect(formatDate("2026-10-20")).toBe("20 oct 2026");
    expect(formatDate("2026-01-01")).toBe("1 ene 2026");
    expect(formatDate("2026-12-31")).toBe("31 dic 2026");
  });

  it("formatDate con un instante UTC da la fecha civil de Bogotá", () => {
    expect(formatDate("2026-11-01T03:00:00Z")).toBe("31 oct 2026");
    expect(formatDate("2027-01-01T04:59:59Z")).toBe("31 dic 2026");
  });

  it("formatDateTime convierte de UTC a Bogotá con a. m. y p. m.", () => {
    expect(formatDateTime("2026-10-21T02:30:00Z")).toBe("20 oct 2026, 9:30 p. m.");
    expect(formatDateTime("2026-10-21T05:00:00Z")).toBe("21 oct 2026, 12:00 a. m.");
    expect(formatDateTime("2026-10-21T17:05:00Z")).toBe("21 oct 2026, 12:05 p. m.");
    expect(formatDateTime("2027-01-01T04:30:00Z")).toBe("31 dic 2026, 11:30 p. m.");
  });

  it("formatTime da solo la hora de Bogotá", () => {
    expect(formatTime("2026-10-21T02:30:00Z")).toBe("9:30 p. m.");
    expect(formatTime("2026-10-21T14:07:00.123Z")).toBe("9:07 a. m.");
  });

  it("formatMonth da el mes largo y el año", () => {
    expect(formatMonth("2026-10")).toBe("octubre 2026");
    expect(formatMonth("2026-09-15")).toBe("septiembre 2026");
    expect(formatMonth("2026-11-01T03:00:00Z")).toBe("octubre 2026");
  });

  it("todayBogota da la fecha civil de Bogotá aunque el equipo esté en otra zona", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-10-21T03:00:00Z"));
    expect(todayBogota()).toBe("2026-10-20");
    vi.setSystemTime(new Date("2026-10-21T05:00:00Z"));
    expect(todayBogota()).toBe("2026-10-21");
  });
});

describe("entradas inválidas", () => {
  it.each(["", "ayer", "2026-13-01", "2026-02-30", "2026-10-20T99:00:00Z"])("formatDate(%j) da una raya", (input) => {
    expect(formatDate(input)).toBe("—");
  });

  it("formatDateTime, formatTime y formatMonth dan una raya ante una cadena inválida", () => {
    expect(formatDateTime("no es fecha")).toBe("—");
    expect(formatTime("no es fecha")).toBe("—");
    expect(formatMonth("2026-00")).toBe("—");
    expect(formatMonth("no es fecha")).toBe("—");
  });
});

describe("fechas de los formularios en hora de Bogotá (S3-F3)", () => {
  it.each(ZONES)("nowBogotaInput da 'AAAA-MM-DDTHH:mm' de Bogotá con el equipo en %s", (zone) => {
    process.env.TZ = zone;
    expect(nowBogotaInput(Date.parse("2026-10-28T15:07:59Z"))).toBe("2026-10-28T10:07");
    expect(nowBogotaInput(Date.parse("2026-10-29T03:30:00Z"))).toBe("2026-10-28T22:30");
  });

  it("nowBogotaInput sin argumento usa el reloj", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-01-01T04:59:00Z"));
    expect(nowBogotaInput()).toBe("2025-12-31T23:59");
  });

  it.each(ZONES)("bogotaInputToUtc lleva la hora de Bogotá (UTC-5) a un instante UTC con el equipo en %s", (zone) => {
    process.env.TZ = zone;
    expect(bogotaInputToUtc("2026-10-28T10:00")).toBe("2026-10-28T15:00:00.000Z");
    expect(bogotaInputToUtc("2026-10-27T19:30")).toBe("2026-10-28T00:30:00.000Z");
    expect(bogotaInputToUtc("2026-12-31T23:59")).toBe("2027-01-01T04:59:00.000Z");
  });

  it.each(["", "2026-10-28", "2026-10-28T25:00", "2026-02-30T10:00", "2026-10-28T10:60", "hoy"])("bogotaInputToUtc(%j) da null", (input) => {
    expect(bogotaInputToUtc(input)).toBeNull();
  });

  it("addDaysCivil suma días a una fecha civil (fin de mes, de año y bisiesto) y da null si no es fecha", () => {
    expect(addDaysCivil("2026-10-29", 30)).toBe("2026-11-28");
    expect(addDaysCivil("2026-12-15", 30)).toBe("2027-01-14");
    expect(addDaysCivil("2028-02-28", 1)).toBe("2028-02-29");
    expect(addDaysCivil("2026-10-28", 0)).toBe("2026-10-28");
    expect(addDaysCivil("2026-02-30", 1)).toBeNull();
  });
});

describe("formatDateRange (S3-F4: vigencia corta de una membresía)", () => {
  it("en el mismo año da día y mes con raya: «25 oct–24 nov»", () => {
    expect(formatDateRange("2026-10-25", "2026-11-24")).toBe("25 oct–24 nov");
    expect(formatDateRange("2026-09-25", "2026-10-24")).toBe("25 sept–24 oct");
  });

  it("si cruza de año lleva los dos años", () => {
    expect(formatDateRange("2026-12-15", "2027-01-14")).toBe("15 dic 2026–14 ene 2027");
  });

  it("una fecha que no es civil da la raya de vacío", () => {
    expect(formatDateRange("2026-13-01", "2026-11-24")).toBe("—");
    expect(formatDateRange("2026-10-25", "nunca")).toBe("—");
  });
});

// Fase 4 del Sprint 3 (L8): la diferencia en días entre dos fechas civiles; antes rules.ts tenía su
// propio lector de fechas.
describe("civilDaysBetween", () => {
  it.each([
    ["2026-10-01", "2026-10-10", 9],
    ["2026-10-10", "2026-10-10", 0],
    ["2026-10-10", "2026-10-01", -9],
    ["2026-12-31", "2027-01-01", 1],
    ["2028-02-28", "2028-03-01", 2],
  ])("%s → %s = %s días", (from, to, days) => {
    for (const zone of ZONES) {
      process.env.TZ = zone;
      expect(civilDaysBetween(from, to)).toBe(days);
    }
  });

  it.each([
    ["2026-02-30", "2026-03-01"],
    ["2026-10-01", ""],
    ["1 oct", "2026-10-01"],
  ])("null si alguna no es una fecha real (%s, %s)", (from, to) => {
    expect(civilDaysBetween(from, to)).toBeNull();
  });
});
