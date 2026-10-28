// S3-F3 · enlaces de membresías y lectura de la URL de la venta.
// - /membresias/vender: vender. `?socio=<id>` fija el socio; con `&renovar=1` renueva (US-088,
//   Q1). Un `socio` que no es un UUID se ignora (vuelve a la venta normal con buscador).
// - El nombre del socio viaja en el estado de la navegación (validado con Zod) para no pedirlo de
//   nuevo; sin él la venta lo pide a GET /members/{id} (S3-F7, useMemberName de shared/data).
// - Fase 4 del Sprint 3 (M4): las rutas y sus enlaces (memberHref, sellHref, renewHref) viven en
//   shared/lib/routes.ts y aquí se reexportan; `sellForMemberHref` es `sellHref`.
import { z } from "zod";
import { isUuid } from "../../shared/lib/ids";
import { SELL_MEMBER_PARAM, SELL_RENEW_PARAM } from "../../shared/lib/routes";

export {
  MEMBERS_PATH,
  MEMBERSHIPS_PATH,
  memberHref,
  NEW_MEMBER_PATH,
  PLANS_PATH,
  renewHref,
  SELL_PATH,
  sellHref as sellForMemberHref,
} from "../../shared/lib/routes";

export interface SellParams {
  /** El socio fijado por la URL, o null. */
  memberId: string | null;
  /** Renovar: solo con un socio fijo. */
  renew: boolean;
}

export function readSellParams(search: string): SellParams {
  const params = new URLSearchParams(search);
  const socio = params.get(SELL_MEMBER_PARAM);
  const memberId = socio !== null && isUuid(socio) ? socio : null;
  return { memberId, renew: memberId !== null && params.get(SELL_RENEW_PARAM) === "1" };
}

/** Estado de la navegación hacia la venta: el nombre del socio ya elegido. */
export const sellLocationStateSchema = z.object({ memberName: z.string().min(1).max(250) });
export type SellLocationState = z.infer<typeof sellLocationStateSchema>;

/** El nombre del socio del estado de la navegación, o null. */
export function memberNameFromState(state: unknown): string | null {
  const parsed = sellLocationStateSchema.safeParse(state);
  return parsed.success ? parsed.data.memberName : null;
}
