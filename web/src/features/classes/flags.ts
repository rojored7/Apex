// S7-F4 (BRECHAS 15.6): las siete banderas del check-in sobre StatusTag (`flag`). Siempre con texto: el rojo solo refuerza.
// Una bandera que el front no conoce (el api agregó otra) se descarta en vez de pintar un código crudo.
import { isFlagView, type FlagView } from "../../shared/ui/statusLabel";

export const CHECKIN_FLAG_ORDER: readonly FlagView[] = ["expired", "no_membership", "frozen", "pending_payment", "over_capacity", "out_of_window", "other_day"];

/** Las banderas conocidas de `raw`, en el orden del api. */
export function knownFlags(raw: readonly string[]): FlagView[] {
  return CHECKIN_FLAG_ORDER.filter((flag) => raw.includes(flag) && isFlagView(flag));
}
