// @vitest-environment node
// S5-F4 · US-139: el rango de la exportación de pagos (obligatorio, de 12 meses como máximo, fechas
// civiles de Bogotá) y su traducción a UTC `[from, to)`.
import { EXPORT_RANGE_MESSAGES, exportRangeError, paymentsExportRangeSchema, toPaymentsExportQuery } from "./exportSchema";

describe("paymentsExportRangeSchema", () => {
  it.each([
    ["un día", "2026-10-05", "2026-10-05"],
    ["un mes", "2026-10-01", "2026-10-31"],
    ["12 meses justos", "2025-11-01", "2026-10-31"],
    ["12 meses desde un 29 de febrero", "2024-02-29", "2025-02-27"],
    ["a cruce de año", "2025-12-15", "2026-12-14"],
  ])("acepta %s", (_name, from, to) => {
    expect(paymentsExportRangeSchema.safeParse({ from, to }).success).toBe(true);
  });

  it.each([
    ["13 meses", "2025-10-01", "2026-10-31", EXPORT_RANGE_MESSAGES.tooLong],
    ["un día más de 12 meses", "2025-11-01", "2026-11-01", EXPORT_RANGE_MESSAGES.tooLong],
    ["12 meses desde un 29 de febrero, un día de más", "2024-02-29", "2025-02-28", EXPORT_RANGE_MESSAGES.tooLong],
    ["invertido", "2026-10-31", "2026-10-01", EXPORT_RANGE_MESSAGES.inverted],
    ["sin 'Desde'", "", "2026-10-01", EXPORT_RANGE_MESSAGES.fromRequired],
    ["sin 'Hasta'", "2026-10-01", "", EXPORT_RANGE_MESSAGES.toRequired],
    ["'Desde' que no es una fecha real", "2026-02-30", "2026-03-10", EXPORT_RANGE_MESSAGES.fromRequired],
    ["'Hasta' con otro formato", "2026-10-01", "01/11/2026", EXPORT_RANGE_MESSAGES.toRequired],
  ])("rechaza %s con su mensaje", (_name, from, to, message) => {
    expect(exportRangeError({ from, to })).toBe(message);
  });

  it("un rango válido no tiene error", () => {
    expect(exportRangeError({ from: "2026-10-01", to: "2026-10-31" })).toBeNull();
  });
});

describe("toPaymentsExportQuery", () => {
  it("convierte los días de Bogotá a UTC con el día siguiente como fin exclusivo y conserva los filtros", () => {
    const range = paymentsExportRangeSchema.parse({ from: "2026-10-01", to: "2026-10-31" });

    expect(toPaymentsExportQuery(range, { q: "ana", voided: true })).toEqual({
      q: "ana",
      voided: true,
      from: "2026-10-01T05:00:00.000Z",
      to: "2026-11-01T05:00:00.000Z",
    });
  });

  it("un rango sin validar lanza", () => {
    expect(() => toPaymentsExportQuery({ from: "x", to: "y" }, {})).toThrow("rango no validado");
  });
});
