// S6-F2 · US-143, US-145: estados de una llave (Activa, Solo descifrar, Retirada) y de un trabajo de
// rotación o recifrado (Pendiente, En curso, Terminado, Falló) en StatusTag; el texto lleva el significado.
import { render, screen } from "@testing-library/react";
import { axe } from "vitest-axe";
import { CRYPTO_LABELS, CRYPTO_TONES, cryptoLabel, cryptoTone, type CryptoStatusView, type StatusTone } from "./statusLabel";
import { StatusTag } from "./StatusTag";

const CASES: [CryptoStatusView, string, StatusTone][] = [
  ["active", "Activa", "ok"],
  ["decrypt_only", "Solo descifrar", "warning"],
  ["retired", "Retirada", "neutral"],
  ["pending", "Pendiente", "neutral"],
  ["running", "En curso", "warning"],
  ["done", "Terminado", "ok"],
  ["failed", "Falló", "danger"],
];

describe("estados de llaves y trabajos", () => {
  it.each(CASES)("%s se lee «%s» con el tono %s", (status, label, tone) => {
    expect(cryptoLabel(status)).toBe(label);
    expect(cryptoTone(status)).toBe(tone);
    render(<StatusTag crypto={status} />);

    expect(screen.getByText(label)).toHaveClass("tag", tone);
    expect(screen.getByText(label)).toHaveAttribute("data-crypto", status);
  });

  it("cubre exactamente los siete estados", () => {
    expect(Object.keys(CRYPTO_LABELS).sort()).toEqual(CASES.map(([status]) => status).sort());
    expect(Object.keys(CRYPTO_TONES).sort()).toEqual(CASES.map(([status]) => status).sort());
  });

  it("sin violaciones de accesibilidad", async () => {
    const { container } = render(
      <div>
        {CASES.map(([status]) => (
          <StatusTag key={status} crypto={status} />
        ))}
      </div>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
