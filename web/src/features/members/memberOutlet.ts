// S3-F1 (S3-D65): la ficha que MemberDetailPage pasa a sus pestañas por el contexto del <Outlet />.
// La pestaña "Datos" (hija índice) la lee sin un segundo observador de GET /members/{id}. S3-F7: las
// pestañas de otras features (Membresías y Pagos) no importan este archivo (ninguna feature importa
// de otra): leen el mismo contexto con useMemberTab de shared/data, cuyo contrato (MemberTabContext)
// este cumple.
import { useOutletContext } from "react-router";
import type { MemberTabContext } from "../../shared/data/members";
import type { MemberDetailView } from "./schemas";

export interface MemberOutletContext extends MemberTabContext {
  member: MemberDetailView;
}

/** La ficha del padre, o null si la pestaña se pinta sin él. */
export function useMemberOutlet(): MemberDetailView | null {
  const context = useOutletContext<MemberOutletContext | undefined>();
  return context?.member ?? null;
}
