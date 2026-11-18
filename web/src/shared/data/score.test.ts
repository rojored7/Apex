// S8-F3 (S8-D13, S8-D41): marcas y cargas en pantalla. El contrato lleva gramos enteros; la pantalla, kg con hasta dos decimales.
import { describe, expect, it } from "vitest";
import { formatLoadKg, formatScore, formatSeconds, formatWeightKg, gramsToKgInput, isScoreKind, kgInputToGrams, LOAD_MAX_G, SCORE_KINDS } from "./score";

describe("formatSeconds", () => {
  it("da minutos y segundos con dos cifras", () => {
    expect(formatSeconds(245)).toBe("4:05");
    expect(formatSeconds(59)).toBe("0:59");
    expect(formatSeconds(3725)).toBe("1:02:05");
  });
});

describe("formatLoadKg", () => {
  it("100000 g es 100 kg y 102500 g es 102,5 kg", () => {
    expect(formatLoadKg(100000)).toBe("100 kg");
    expect(formatLoadKg(102500)).toBe("102,5 kg");
    expect(formatLoadKg(102550)).toBe("102,55 kg");
    expect(formatLoadKg(0)).toBe("0 kg");
  });
});

describe("formatScore", () => {
  it("tiempo, tiempo cortado, rondas, repeticiones y carga", () => {
    expect(formatScore("time", { seconds: 245, rounds: null, reps: null, load_g: null, capped: false })).toBe("4:05");
    expect(formatScore("time", { seconds: 900, rounds: null, reps: 135, load_g: null, capped: true })).toBe("DNF · 135 reps");
    expect(formatScore("rounds_reps", { seconds: null, rounds: 5, reps: 12, load_g: null, capped: false })).toBe("5 + 12");
    expect(formatScore("reps", { seconds: null, rounds: null, reps: 150, load_g: null, capped: false })).toBe("150 reps");
    expect(formatScore("load", { seconds: null, rounds: null, reps: null, load_g: 102500, capped: false })).toBe("102,5 kg");
  });
  it("DNF con rondas y repeticiones", () => {
    expect(formatScore("time", { seconds: 900, rounds: 2, reps: 15, load_g: null, capped: true })).toBe("DNF · 2 + 15");
  });
  it("sin marca da raya", () => {
    expect(formatScore("none", { seconds: null, rounds: null, reps: null, load_g: null, capped: false })).toBe("—");
  });
});

describe("kgInputToGrams", () => {
  it("102,5 kg se envía como 102500", () => {
    expect(kgInputToGrams("102,5")).toBe(102500);
    expect(kgInputToGrams("102.5")).toBe(102500);
    expect(kgInputToGrams("60")).toBe(60000);
    expect(kgInputToGrams("0,01")).toBe(10);
  });
  it("rechaza vacío, negativos, texto, más de dos decimales y más de 1.000 kg", () => {
    expect(kgInputToGrams("")).toBeNull();
    expect(kgInputToGrams("-5")).toBeNull();
    expect(kgInputToGrams("abc")).toBeNull();
    expect(kgInputToGrams("1,234")).toBeNull();
    expect(kgInputToGrams("1000,01")).toBeNull();
    expect(kgInputToGrams("1000")).toBe(LOAD_MAX_G);
  });
});

describe("gramsToKgInput", () => {
  it("devuelve el texto del campo con coma decimal", () => {
    expect(gramsToKgInput(102500)).toBe("102,5");
    expect(gramsToKgInput(60000)).toBe("60");
    expect(gramsToKgInput(null)).toBe("");
  });
});

// S9-F1 (US-178, design Atleta_Perfil.html): el peso corporal se ve con un decimal fijo, «61,2 kg», «62,0 kg».
describe("formatWeightKg", () => {
  it("gramos a kg con un decimal y coma decimal", () => {
    expect(formatWeightKg(61_200)).toBe("61,2 kg");
    expect(formatWeightKg(62_000)).toBe("62,0 kg");
    expect(formatWeightKg(63_100)).toBe("63,1 kg");
  });

  it("los extremos del contrato (20 kg y 400 kg)", () => {
    expect(formatWeightKg(20_000)).toBe("20,0 kg");
    expect(formatWeightKg(400_000)).toBe("400,0 kg");
  });
});

// S9-F1 (revisión L9): el texto del api se reconoce sin un `as`.
describe("isScoreKind", () => {
  it("acepta los cinco tipos de marca y rechaza lo demás", () => {
    for (const kind of SCORE_KINDS) expect(isScoreKind(kind)).toBe(true);
    expect(isScoreKind("distance")).toBe(false);
    expect(isScoreKind(null)).toBe(false);
  });
});
