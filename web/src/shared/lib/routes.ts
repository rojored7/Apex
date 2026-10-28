// Fase 4 del Sprint 3 (M4): las rutas del panel que enlazan varias features y sus enlaces. Antes cada
// feature tenía su copia (S3-D65 prohíbe importar de otra feature); ahora viven aquí y las features
// las reexportan con sus nombres de siempre.
// - memberHref: la ficha del socio (/socios/:id, US-073). Nunca se enlaza a /socios?q=<documento>:
//   el documento quedaría en la URL, el historial y los logs.
// - sellHref y renewHref: la venta con el socio fijo (`?socio=<id>`) y la renovación (`&renovar=1`,
//   US-088, Q1). Solo el id viaja en la URL, nunca un dato cifrado.
export const MEMBERS_PATH = "/socios";
export const NEW_MEMBER_PATH = "/socios/nuevo";
export const MEMBERSHIPS_PATH = "/membresias";
export const SELL_PATH = "/membresias/vender";
export const PLANS_PATH = "/planes";
export const PAYMENTS_PATH = "/pagos";

/** Los parámetros de la venta en la URL. */
export const SELL_MEMBER_PARAM = "socio";
export const SELL_RENEW_PARAM = "renovar";

/** /socios/{id}: la ficha del socio. */
export function memberHref(memberId: string): string {
  return `${MEMBERS_PATH}/${encodeURIComponent(memberId)}`;
}

/** /membresias/vender?socio=<id>: vender a un socio ya elegido. */
export function sellHref(memberId: string): string {
  return `${SELL_PATH}?${new URLSearchParams({ [SELL_MEMBER_PARAM]: memberId }).toString()}`;
}

/** /membresias/vender?socio=<id>&renovar=1: renovar la membresía del socio. */
export function renewHref(memberId: string): string {
  return `${SELL_PATH}?${new URLSearchParams({ [SELL_MEMBER_PARAM]: memberId, [SELL_RENEW_PARAM]: "1" }).toString()}`;
}
