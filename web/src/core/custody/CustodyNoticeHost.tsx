// S5-F5 · US-136: monta el aviso global de custodio no disponible. Se retira solo al pasar los
// segundos de Retry-After (no reintenta nada por su cuenta) y se puede cerrar a mano.
import { useEffect } from "react";
import { CustodyNotice } from "../../shared/ui/CustodyNotice";
import { clearCustodyNotice, useCustodyNotice } from "./custodyNotice";

const MS_PER_S = 1_000;

export function CustodyNoticeHost() {
  const notice = useCustodyNotice();
  const id = notice?.id;
  const retryAfterS = notice?.retryAfterS;

  useEffect(() => {
    if (id === undefined || retryAfterS === undefined) return undefined;
    const timer = setTimeout(clearCustodyNotice, retryAfterS * MS_PER_S);
    return () => {
      clearTimeout(timer);
    };
  }, [id, retryAfterS]);

  if (notice === null) return null;
  return <CustodyNotice retryAfterS={notice.retryAfterS} onDismiss={clearCustodyNotice} />;
}
