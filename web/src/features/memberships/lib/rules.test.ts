// S3-F3 · reglas de la vista previa de la venta. Manda el servidor; esto solo pinta.
// - computeEndDate: fin inclusivo `inicio + duración` (RN-05, N-23, D16): 29 oct + 30 días termina
//   el 28 nov, no el "27 nov" que dibuja Membresia_Vender.html (DESIGN-GAP).
// - saldo, exceedsBalance y excessOver: el sobrepago se confirma (Q5, S3-D41), sin saldo a favor.
import {
  classesRemainingText,
  computeEndDate,
  daysLeftText,
  exceedsBalance,
  excessOver,
  freezePreview,
  membershipActions,
  NO_MEMBERSHIP_ACTIONS,
  paidText,
  planTermsText,
  saldo,
  splitMemberships,
  untilText,
  type MembershipFacts,
} from "./rules";

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

// S3-F5 · US-089 (front): vista previa de congelar (D14, RN-07). Los días cuentan los dos extremos
// (`days = frozen_to - frozen_from + 1`, CHECK `days_match` de 0009) y el fin se corre esos días.
describe("freezePreview (S3-F5)", () => {
  it("10 días desde el 28 oct con fin el 31 oct: 'Son 10 días; la membresía terminará el 10 nov 2026'", () => {
    expect(freezePreview("2026-10-28", "2026-11-06", "2026-10-31")).toEqual({
      days: 10,
      newEndDate: "2026-11-10",
      text: "Son 10 días; la membresía terminará el 10 nov 2026",
    });
  });

  it("una ventana de un día suma 1 y lo dice en singular", () => {
    expect(freezePreview("2026-10-28", "2026-10-28", "2026-10-31")).toEqual({
      days: 1,
      newEndDate: "2026-11-01",
      text: "Es 1 día; la membresía terminará el 1 nov 2026",
    });
  });

  it("cruza el fin de año y el 29 de febrero", () => {
    expect(freezePreview("2026-12-20", "2027-01-08", "2026-12-31")?.newEndDate).toBe("2027-01-20");
    expect(freezePreview("2028-02-01", "2028-02-29", "2028-02-28")?.days).toBe(29);
  });

  it("fechas invertidas, vacías o que no existen no dan vista previa", () => {
    expect(freezePreview("2026-11-06", "2026-10-28", "2026-10-31")).toBeNull();
    expect(freezePreview("", "2026-11-06", "2026-10-31")).toBeNull();
    expect(freezePreview("2026-10-28", "", "2026-10-31")).toBeNull();
    expect(freezePreview("2026-02-30", "2026-03-02", "2026-10-31")).toBeNull();
    expect(freezePreview("2026-10-28", "2026-11-06", "fin")).toBeNull();
  });
});

describe("paidText y classesRemainingText (columnas de Membresias.html)", () => {
  it("un abono dice cuánto de cuánto: '$ 60.000 de $ 120.000 · abono'", () => {
    expect(paidText(60_000, 120_000)).toBe("$ 60.000 de $ 120.000 · abono");
  });

  it("sin pagos dice '$ 0 de $ 120.000' y pagada completa, el valor con 'pagado'", () => {
    expect(paidText(0, 120_000)).toBe("$ 0 de $ 120.000");
    expect(paidText(120_000, 120_000)).toBe("$ 120.000 · pagado");
    expect(paidText(130_000, 120_000)).toBe("$ 130.000 · pagado");
  });

  it("las clases restantes van 'N de M'; un plan por días no tiene clases", () => {
    expect(classesRemainingText(2, 12)).toBe("2 de 12");
    expect(classesRemainingText(null, null)).toBe("—");
    expect(classesRemainingText(0, 12)).toBe("0 de 12");
  });
});

// S3-F7 · US-093 (front): la pestaña Membresías de la ficha. Hoy es el 2026-10-20 en todas las ramas.
describe("splitMemberships y membershipActions (S3-F7)", () => {
  const TODAY = "2026-10-20";
  const m = (id: string, status: MembershipFacts["status"], start: string, end: string, paid = 120_000): MembershipFacts => ({
    id,
    status,
    start_date: start,
    end_date: end,
    agreed_price_cop: 120_000,
    paid_cop: paid,
  });
  const CURRENT = m("vigente", "expiring", "2026-09-29", "2026-10-28");
  const OWING = m("vigente-abono", "active", "2026-10-10", "2026-11-09", 60_000);
  const FUTURE = m("futura", "pending_payment", "2026-10-29", "2026-11-28", 0);
  const EXPIRED = m("vencida", "expired", "2026-08-01", "2026-08-31");
  const CANCELLED = m("anulada", "cancelled", "2026-09-01", "2026-09-30");
  const FROZEN = m("congelada", "frozen", "2026-10-01", "2026-11-10");

  it("separa la vigente (empezó y está abierta) de la futura (no anulada, empieza después de hoy)", () => {
    expect(splitMemberships([FUTURE, CURRENT, EXPIRED], TODAY)).toEqual({ current: CURRENT, future: FUTURE });
    expect(splitMemberships([EXPIRED, CANCELLED], TODAY)).toEqual({ current: null, future: null });
    expect(splitMemberships([FROZEN], TODAY)).toEqual({ current: FROZEN, future: null });
    // Una pendiente de pago que ya empezó es la vigente; una anulada futura no es la futura.
    const pendingNow = m("pendiente", "pending_payment", "2026-10-20", "2026-11-19", 0);
    expect(splitMemberships([m("anulada-futura", "cancelled", "2026-11-01", "2026-11-30"), pendingNow], TODAY)).toEqual({ current: pendingNow, future: null });
    expect(splitMemberships([], TODAY)).toEqual({ current: null, future: null });
  });

  it("vigente sin futura: Renovar, no Vender; Congelar para admin y coach; Anular solo para el admin", () => {
    expect(membershipActions([CURRENT, EXPIRED], "admin", TODAY, false)).toEqual({ renew: true, sell: false, payIds: [], freezeIds: ["vigente"], cancelIds: ["vigente"] });
    expect(membershipActions([CURRENT, EXPIRED], "coach", TODAY, false)).toEqual({ renew: true, sell: false, payIds: [], freezeIds: ["vigente"], cancelIds: [] });
  });

  it("vencida sin futura: Renovar y Vender; sin membresías: solo Vender", () => {
    expect(membershipActions([EXPIRED, CANCELLED], "coach", TODAY, false)).toEqual({ renew: true, sell: true, payIds: [], freezeIds: [], cancelIds: [] });
    expect(membershipActions([], "admin", TODAY, false)).toEqual({ renew: false, sell: true, payIds: [], freezeIds: [], cancelIds: [] });
  });

  it("la última no anulada manda: una anulada más reciente que la vencida no quita Renovar; solo anuladas no renuevan", () => {
    expect(membershipActions([CANCELLED, EXPIRED], "admin", TODAY, false).renew).toBe(true);
    expect(membershipActions([CANCELLED], "admin", TODAY, false)).toMatchObject({ renew: false, sell: true });
  });

  it("con futura: ni Renovar ni Vender; Registrar saldo sobre la que debe; Congelar no aplica a la pendiente", () => {
    expect(membershipActions([FUTURE, CURRENT], "admin", TODAY, false)).toEqual({ renew: false, sell: false, payIds: ["futura"], freezeIds: ["vigente"], cancelIds: ["futura", "vigente"] });
    expect(membershipActions([FUTURE, OWING], "coach", TODAY, false)).toEqual({ renew: false, sell: false, payIds: ["futura", "vigente-abono"], freezeIds: ["vigente-abono"], cancelIds: [] });
  });

  it("revisión S3-F7 (M4): una futura ya pagada ('Al día') no se congela; la vigente sí", () => {
    const paidFuture = m("futura-pagada", "active", "2026-10-29", "2026-11-28");
    expect(membershipActions([paidFuture, CURRENT], "admin", TODAY, false)).toMatchObject({ freezeIds: ["vigente"], cancelIds: ["futura-pagada", "vigente"] });
  });

  it("una congelada se paga si debe y no se vuelve a congelar", () => {
    expect(membershipActions([{ ...FROZEN, paid_cop: 0 }], "admin", TODAY, false)).toEqual({ renew: true, sell: false, payIds: ["congelada"], freezeIds: [], cancelIds: ["congelada"] });
  });

  it("nada para un socio dado de baja ni para un rol sin permisos (member o sin sesión)", () => {
    expect(membershipActions([FUTURE, OWING], "admin", TODAY, true)).toEqual(NO_MEMBERSHIP_ACTIONS);
    expect(membershipActions([], "admin", TODAY, true)).toEqual(NO_MEMBERSHIP_ACTIONS);
    expect(membershipActions([OWING], "member", TODAY, false)).toEqual(NO_MEMBERSHIP_ACTIONS);
    expect(membershipActions([OWING], null, TODAY, false)).toEqual(NO_MEMBERSHIP_ACTIONS);
  });
});

describe("daysLeftText (S3-F7)", () => {
  it.each([
    ["2026-10-20", "2026-10-28", "Quedan 8 días"],
    ["2026-10-20", "2026-10-21", "Queda 1 día"],
    ["2026-10-20", "2026-10-20", "Vence hoy"],
    ["2026-10-20", "2026-10-19", "Venció"],
    ["2026-12-30", "2027-01-02", "Quedan 3 días"],
  ])("hoy %s y fin %s: %s", (today, end, text) => {
    expect(daysLeftText(today, end)).toBe(text);
  });

  it("una fecha que no es civil no dice nada", () => {
    expect(daysLeftText("2026-10-20", "2026-02-30")).toBe("—");
  });
});
