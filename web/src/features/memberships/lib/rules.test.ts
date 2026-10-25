// S3-F3 · reglas de la vista previa de la venta. Manda el servidor; esto solo pinta.
// - computeEndDate: fin inclusivo `inicio + duración` (RN-05, N-23, D16): 29 oct + 30 días termina
//   el 28 nov, no el "27 nov" que dibuja Membresia_Vender.html (DESIGN-GAP).
// - saldo, exceedsBalance y excessOver: el sobrepago se confirma (Q5, S3-D41), sin saldo a favor.
import { computeEndDate, exceedsBalance, excessOver, planTermsText, saldo, untilText } from "./rules";

describe("computeEndDate (N-23)", () => {
  it("2026-10-29 + 30 días termina el 2026-11-28: 'hasta el 28 nov 2026'", () => {
    const end = computeEndDate("2026-10-29", 30);

    expect(end).toBe("2026-11-28");
    expect(untilText(end ?? "")).toBe("hasta el 28 nov 2026");
  });

  it("cruza el fin de año y el 29 de febrero", () => {
    expect(computeEndDate("2026-12-15", 30)).toBe("2027-01-14");
    expect(computeEndDate("2028-02-28", 1)).toBe("2028-02-29");
  });

  it("sin una fecha válida no calcula nada", () => {
    expect(computeEndDate("", 30)).toBeNull();
    expect(computeEndDate("2026-02-30", 30)).toBeNull();
  });

  it("untilText de una fecha inválida da una raya", () => {
    expect(untilText("no")).toBe("hasta el —");
  });
});

describe("saldo, exceedsBalance y excessOver (Q5, S3-D41)", () => {
  it("el saldo es lo que falta para el precio y nunca es negativo", () => {
    expect(saldo(120_000, 0)).toBe(120_000);
    expect(saldo(120_000, 60_000)).toBe(60_000);
    expect(saldo(120_000, 150_000)).toBe(0);
  });

  it("un pago igual al saldo no lo supera; un peso más sí", () => {
    expect(exceedsBalance(120_000, 0, 120_000)).toBe(false);
    expect(exceedsBalance(120_000, 0, 120_001)).toBe(true);
    expect(exceedsBalance(120_000, 60_000, 60_000)).toBe(false);
    expect(exceedsBalance(120_000, 60_000, 60_001)).toBe(true);
  });

  it("excessOver es cuánto supera el pago al saldo, o 0", () => {
    expect(excessOver(120_000, 0, 150_000)).toBe(30_000);
    expect(excessOver(120_000, 60_000, 70_000)).toBe(10_000);
    expect(excessOver(120_000, 0, 100_000)).toBe(0);
  });
});

describe("planTermsText", () => {
  it("un plan por días dice su duración y su precio; uno por clases, las clases y los días para usarlas", () => {
    expect(planTermsText({ kind: "days", duration_days: 30, class_count: null, price_cop: 120_000 })).toBe("30 días · $ 120.000");
    expect(planTermsText({ kind: "classes", duration_days: 60, class_count: 12, price_cop: 110_000 })).toBe("12 clases · 60 días para usarlas · $ 110.000");
    expect(planTermsText({ kind: "classes", duration_days: 1, class_count: 1, price_cop: 15_000 })).toBe("1 clase · 1 día para usarla · $ 15.000");
    expect(planTermsText({ kind: "days", duration_days: 1, class_count: null, price_cop: 15_000 })).toBe("1 día · $ 15.000");
  });
});
