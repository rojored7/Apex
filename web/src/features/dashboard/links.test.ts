// @vitest-environment node
// S4A-F3 · US-109 (paso 122): los destinos de los KPI de Inicio.
// Desviación anotada en docs/scratch/sprint-04a-front.md (F3.2): el plan pedía para ingresos
// `/pagos?from=2026-10-01T05:00:00Z&to=2026-11-01T05:00:00Z`, pero /pagos lee `from` y `to` de la URL
// como días civiles de Bogotá (usePaymentFilters, S3-F6) y descarta un instante UTC: el enlace caería
// en la lista sin filtrar. El enlace lleva el mes con los días que entiende la pantalla (del 1 al
// último día, `to` incluido) y es la pantalla la que los lleva al rango UTC [2026-10-01T05:00Z,
// 2026-11-01T05:00Z) que pide el plan.
import { kpiLinks } from "./links";

const ZONES = ["UTC", "Asia/Tokyo", "America/New_York"] as const;
const ORIGINAL_TZ = process.env.TZ;

afterEach(() => {
  if (ORIGINAL_TZ === undefined) delete process.env.TZ;
  else process.env.TZ = ORIGINAL_TZ;
});

describe("kpiLinks", () => {
  it("lleva cada KPI de membresías a /socios con el estado del api", () => {
    const links = kpiLinks("2026-10-20");

    expect(links.active).toBe("/socios?membership_status=active");
    expect(links.expiring).toBe("/socios?membership_status=expiring");
    expect(links.expired).toBe("/socios?membership_status=expired");
    expect(links.pendingPayment).toBe("/socios?membership_status=pending_payment");
  });

  it.each(ZONES)("ingresos van a /pagos con el mes de Bogotá completo (TZ=%s)", (zone) => {
    process.env.TZ = zone;

    expect(kpiLinks("2026-10-20").income).toBe("/pagos?from=2026-10-01&to=2026-10-31");
  });

  it.each([
    ["2026-02-10", "/pagos?from=2026-02-01&to=2026-02-28"],
    ["2028-02-29", "/pagos?from=2028-02-01&to=2028-02-29"],
    ["2026-12-31", "/pagos?from=2026-12-01&to=2026-12-31"],
    ["2027-01-01", "/pagos?from=2027-01-01&to=2027-01-31"],
  ])("el mes de %s termina en su último día", (today, href) => {
    expect(kpiLinks(today).income).toBe(href);
  });

  it("una fecha que no es real deja ingresos en /pagos sin rango", () => {
    expect(kpiLinks("2026-13-40").income).toBe("/pagos");
    expect(kpiLinks("").income).toBe("/pagos");
  });
});
