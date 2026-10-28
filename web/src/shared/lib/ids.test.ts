// Fase 4 del Sprint 3 (M4): la forma de un UUID se comprueba en un solo lugar.
import { isUuid } from "./ids";

describe("isUuid", () => {
  it.each([
    ["3f2b1c9e-4a5d-4e6f-8a7b-9c0d1e2f3a4b", true],
    ["3F2B1C9E-4A5D-4E6F-8A7B-9C0D1E2F3A4B", true],
    ["", false],
    ["nuevo", false],
    ["3f2b1c9e-4a5d-4e6f-8a7b-9c0d1e2f3a4", false],
    [" 3f2b1c9e-4a5d-4e6f-8a7b-9c0d1e2f3a4b", false],
    ["3f2b1c9e-4a5d-4e6f-8a7b-9c0d1e2f3a4b/editar", false],
  ])("%j → %s", (value, expected) => {
    expect(isUuid(value)).toBe(expected);
  });
});
