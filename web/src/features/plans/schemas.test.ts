// S2-F7: reglas del alta de planes en el cliente (PlanCreate y validate_plan de B9), el cuerpo
// de POST /plans, el formato del precio al escribir y la forma de PlanOut.
import { EMPTY_PLAN_FORM, planFormSchema, planRowSchema, priceInputText, toPlanCreate, type PlanFormValues } from "./schemas";

const valid: PlanFormValues = { name: "Mensual", price: "$ 120.000", kind: "days", duration_days: "30", class_count: "" };
const issuesOf = (values: PlanFormValues) => {
  const result = planFormSchema.safeParse(values);
  return result.success ? [] : result.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`);
};

describe("planFormSchema", () => {
  it("acepta un plan por días y uno por clases válidos", () => {
    expect(issuesOf(valid)).toEqual([]);
    expect(issuesOf({ ...valid, kind: "classes", class_count: "12", duration_days: "60" })).toEqual([]);
  });

  it("el formulario vacío marca nombre, precio y duración, no el número de clases", () => {
    expect(issuesOf(EMPTY_PLAN_FORM)).toEqual([
      "name: Escribe el nombre del plan.",
      "price: Escribe el precio del plan.",
      "duration_days: Escribe cuántos días dura el plan.",
    ]);
  });

  it("los topes son los del api", () => {
    expect(issuesOf({ ...valid, name: "x".repeat(80) })).toEqual([]);
    expect(issuesOf({ ...valid, name: "x".repeat(81) })).toEqual(["name: El nombre admite hasta 80 caracteres."]);
    // revisión L5: el api cuenta puntos de código, no unidades UTF-16.
    expect(issuesOf({ ...valid, name: "💪".repeat(80) })).toEqual([]);
    expect(issuesOf({ ...valid, price: "$ 1" })).toEqual([]);
    expect(issuesOf({ ...valid, price: "$ 1.000.000.000" })).toEqual([]);
    expect(issuesOf({ ...valid, price: "$ 1.000.000.001" })).toEqual(["price: El precio debe estar entre $ 1 y $ 1.000.000.000."]);
    expect(issuesOf({ ...valid, price: "$ 0" })).toEqual(["price: El precio debe estar entre $ 1 y $ 1.000.000.000."]);
    expect(issuesOf({ ...valid, duration_days: "3650" })).toEqual([]);
    expect(issuesOf({ ...valid, duration_days: "3651" })).toEqual(["duration_days: La duración debe ser un número entero entre 1 y 3.650 días."]);
    expect(issuesOf({ ...valid, kind: "classes", class_count: "1000" })).toEqual([]);
    expect(issuesOf({ ...valid, kind: "classes", class_count: "1001" })).toEqual(["class_count: El número de clases debe ser un entero entre 1 y 1.000."]);
  });

  it("un precio con centavos o con letras no es un entero en pesos", () => {
    for (const price of ["120000,50", "12.5", "doce mil", "-5"]) {
      expect(issuesOf({ ...valid, price })).toEqual(["price: Escribe el precio en pesos enteros, sin centavos (por ejemplo $ 120.000)."]);
    }
  });

  it("por días ignora el número de clases; por clases lo exige", () => {
    expect(issuesOf({ ...valid, class_count: "abc" })).toEqual([]);
    expect(issuesOf({ ...valid, kind: "classes" })).toEqual(["class_count: Escribe cuántas clases incluye el plan."]);
  });

  it("un tipo desconocido se rechaza con un mensaje propio", () => {
    expect(issuesOf({ ...valid, kind: "weeks" as never })).toEqual(["kind: Elige el tipo de duración: por días o por número de clases."]);
  });
});

describe("toPlanCreate", () => {
  it("revisión L4: un formulario sin validar no se envía con ceros inventados", () => {
    expect(() => toPlanCreate({ ...valid, price: "doce" })).toThrow();
    expect(() => toPlanCreate({ ...valid, kind: "classes", class_count: "" })).toThrow();
  });

  it("por días: nombre recortado, enteros y sin class_count", () => {
    expect(toPlanCreate({ ...valid, name: "  Mensual ", class_count: "12" })).toEqual({ name: "Mensual", price_cop: 120_000, kind: "days", duration_days: 30 });
  });

  it("por clases: con class_count", () => {
    expect(toPlanCreate({ ...valid, kind: "classes", class_count: "12", duration_days: "60" })).toEqual({
      name: "Mensual",
      price_cop: 120_000,
      kind: "classes",
      duration_days: 60,
      class_count: 12,
    });
  });
});

describe("priceInputText", () => {
  it.each([
    ["", ""],
    ["1", "$ 1"],
    ["1200", "$ 1.200"],
    ["120000", "$ 120.000"],
    ["$ ", ""],
    ["007", "$ 7"],
  ])("'%s' se muestra como '%s'", (raw, shown) => {
    expect(priceInputText(raw)).toBe(shown);
  });

  it("escribir o borrar un dígito sobre un precio formateado lo vuelve a formatear", () => {
    expect(priceInputText("$ 1.2000", "$ 1.200")).toBe("$ 12.000");
    expect(priceInputText("$ 1.20", "$ 1.200")).toBe("$ 120");
    expect(priceInputText("$ 1200", "$ 1.200")).toBe("$ 1.200");
  });

  it("revisión M1: un decimal con punto (pegado o escrito) no cambia el monto: queda tal cual y la validación lo rechaza", () => {
    expect(priceInputText("1200.50")).toBe("1200.50");
    expect(priceInputText("1.5")).toBe("1.5");
    expect(priceInputText("$ 1.200.", "$ 1.200")).toBe("$ 1.200.");
    expect(priceInputText("$ 1.200.5", "$ 1.200.")).toBe("$ 1.200.5");
    expect(issuesOf({ ...valid, price: "1200.50" })).toEqual(["price: Escribe el precio en pesos enteros, sin centavos (por ejemplo $ 120.000)."]);
  });

  it("con coma, letras o signo no se reformatea (la validación lo explica)", () => {
    for (const raw of ["120000,5", "12a", "-3"]) expect(priceInputText(raw)).toBe(raw);
  });

  it("más de 15 dígitos no se reformatea (no cabe en un entero seguro)", () => {
    expect(priceInputText("1234567890123456")).toBe("1234567890123456");
  });
});

describe("planRowSchema", () => {
  const row = { id: "x", name: "Mensual", price_cop: 120_000, kind: "days", duration_days: 30, class_count: null, is_active: true, created_at: "a", updated_at: "b" };

  it("acepta PlanOut", () => {
    expect(planRowSchema.safeParse(row).success).toBe(true);
  });

  it("un precio no entero o un tipo desconocido es una respuesta inválida", () => {
    expect(planRowSchema.safeParse({ ...row, price_cop: 1.5 }).success).toBe(false);
    expect(planRowSchema.safeParse({ ...row, kind: "weeks" }).success).toBe(false);
  });
});
