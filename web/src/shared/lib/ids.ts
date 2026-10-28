// Fase 4 del Sprint 3 (M4): la forma de un UUID (los `id` del api) en un solo lugar. Un valor de la
// URL (`:id`, `?socio=`, `?pago=`, `?plan=`) solo viaja al api si la tiene; antes la expresión estaba
// copiada en seis archivos.
const UUID_SHAPE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** ¿Tiene `value` la forma de un UUID ("3f2b1c9e-4a5d-…")? */
export function isUuid(value: string): boolean {
  return UUID_SHAPE.test(value);
}
