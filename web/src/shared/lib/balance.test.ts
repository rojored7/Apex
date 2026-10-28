// Fase 4 del Sprint 3 (M4): la regla del saldo (Q5, S3-D41) en un solo lugar; la venta y el panel de
// pagos la importan de aquí.
import { balance, balanceOf, exceedsBalance, excessOver } from "./balance";

describe("saldo de una membresía (Q5, S3-D41)", () => {
  it("balance es lo que falta para el precio y nunca es negativo", () => {
    expect(balance(120_000, 0)).toBe(120_000);
    expect(balance(120_000, 60_000)).toBe(60_000);
    expect(balance(120_000, 150_000)).toBe(0);
  });

  it("balanceOf lee el precio pactado y lo pagado de la fila", () => {
    expect(balanceOf({ agreed_price_cop: 120_000, paid_cop: 20_000 })).toBe(100_000);
    expect(balanceOf({ agreed_price_cop: 120_000, paid_cop: 130_000 })).toBe(0);
  });

  it("exceedsBalance pide confirmar solo si el pago supera el saldo", () => {
    expect(exceedsBalance(120_000, 60_000, 60_000)).toBe(false);
    expect(exceedsBalance(120_000, 60_000, 60_001)).toBe(true);
    expect(exceedsBalance(120_000, 150_000, 1)).toBe(true);
  });

  it("excessOver es cuánto supera el pago al saldo, o 0", () => {
    expect(excessOver(120_000, 0, 150_000)).toBe(30_000);
    expect(excessOver(120_000, 60_000, 70_000)).toBe(10_000);
    expect(excessOver(120_000, 0, 100_000)).toBe(0);
  });
});
