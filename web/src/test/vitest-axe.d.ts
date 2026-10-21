// vitest-axe 0.1 declara sus matchers en el namespace global `Vi`, que Vitest 3 ya no usa.
// Se declaran aquí sobre el módulo `vitest` para que `toHaveNoViolations` tenga tipos.
import type { AxeMatchers } from "vitest-axe/matchers";

declare module "vitest" {
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type, @typescript-eslint/no-explicit-any, @typescript-eslint/no-unused-vars -- extensión de la interfaz de Vitest
  interface Assertion<T = any> extends AxeMatchers {}
  // eslint-disable-next-line @typescript-eslint/no-empty-object-type -- extensión de la interfaz de Vitest
  interface AsymmetricMatchersContaining extends AxeMatchers {}
}
