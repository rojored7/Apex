// S8-F3 (S8-D13, S8-D41): marcas y cargas en pantalla. El contrato lleva gramos enteros; la pantalla, kg con hasta dos decimales.
import { describe, expect, it } from "vitest";
import { formatLoadKg, formatScore, formatScoreDelta, formatSeconds, formatWeightKg, gramsToKgInput, isScoreKind, kgInputToGrams, LOAD_MAX_G, SCORE_KINDS } from "./score";

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

// S9-F2 (US-183): la diferencia entre dos marcas del mismo tipo y nivel, con signo (el menos es U+2212, como en el diseño).
describe("formatScoreDelta", () => {
  const marks = (overrides: Partial<{ seconds: number | null; rounds: number | null; reps: number | null; load_g: number | null; capped: boolean }>) => ({ seconds: null, rounds: null, reps: null, load_g: null, capped: false, ...overrides });

  it("tiempo: 11:42 contra 12:10 es −0:28 y 12:10 contra 11:05 es +1:05", () => {
    expect(formatScoreDelta("time", marks({ seconds: 702 }), marks({ seconds: 730 }))).toBe("−0:28");
    expect(formatScoreDelta("time", marks({ seconds: 730 }), marks({ seconds: 665 }))).toBe("+1:05");
  });

  it("tiempo: con horas, 1:02:05 de diferencia", () => {
    expect(formatScoreDelta("time", marks({ seconds: 4000 }), marks({ seconds: 275 }))).toBe("+1:02:05");
  });

  it("repeticiones: +5 reps y −3 reps", () => {
    expect(formatScoreDelta("reps", marks({ reps: 45 }), marks({ reps: 40 }))).toBe("+5 reps");
    expect(formatScoreDelta("reps", marks({ reps: 37 }), marks({ reps: 40 }))).toBe("−3 reps");
  });

  it("carga: de 100 kg a 102,5 kg es +2,5 kg y de 100 kg a 95 kg es −5 kg", () => {
    expect(formatScoreDelta("load", marks({ load_g: 102_500 }), marks({ load_g: 100_000 }))).toBe("+2,5 kg");
    expect(formatScoreDelta("load", marks({ load_g: 95_000 }), marks({ load_g: 100_000 }))).toBe("−5 kg");
  });

  it("una marca igual dice «Sin cambio» en cada tipo", () => {
    expect(formatScoreDelta("time", marks({ seconds: 702 }), marks({ seconds: 702 }))).toBe("Sin cambio");
    expect(formatScoreDelta("reps", marks({ reps: 40 }), marks({ reps: 40 }))).toBe("Sin cambio");
    expect(formatScoreDelta("load", marks({ load_g: 100_000 }), marks({ load_g: 100_000 }))).toBe("Sin cambio");
  });

  it("rondas + repeticiones no se compara (falta el tamaño de la ronda) y devuelve null", () => {
    expect(formatScoreDelta("rounds_reps", marks({ rounds: 5, reps: 12 }), marks({ rounds: 4, reps: 20 }))).toBeNull();
  });

  it("una marca cortada (DNF), una que falta o un WOD sin marca devuelven null", () => {
    expect(formatScoreDelta("time", marks({ seconds: 900, reps: 100, capped: true }), marks({ seconds: 702 }))).toBeNull();
    expect(formatScoreDelta("time", marks({ seconds: 702 }), marks({ seconds: 900, capped: true }))).toBeNull();
    expect(formatScoreDelta("time", marks({ seconds: null }), marks({ seconds: 702 }))).toBeNull();
    expect(formatScoreDelta("load", marks({ load_g: 100_000 }), marks({ load_g: null }))).toBeNull();
    expect(formatScoreDelta("none", marks({}), marks({}))).toBeNull();
  });
});
