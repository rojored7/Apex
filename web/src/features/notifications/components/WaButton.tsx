// S5-F1 · US-127 (front): "Abrir WhatsApp" de PorAvisarHoy.html.
// - Un POST (useWaLink) arma el enlace en el servidor y marca el aviso como enviado; solo tras el 200
//   se llama window.open(url, "_blank", "noopener,noreferrer"). La URL lleva el teléfono: vive en una
//   variable local, nunca en el estado, el DOM ni la caché de TanStack (M-9, S5-D59).
// - Objetivo táctil de 48 px (design: .w-wa); en celular ocupa todo el ancho de la tarjeta.
// - S9-X1 (S9-D22, D65): con canWhatsapp === false no se ofrece el botón: queda deshabilitado con
//   "No se puede abrir WhatsApp" (el api no dice el motivo) y un enlace a la ficha, sin llamar al api.
//   Los 422 member_without_phone e invalid_phone (un fijo con indicativo sí pasa can_whatsapp) y el 503
//   crypto_unavailable se muestran con texto fijo.
// - Un solo envío a la vez: el botón queda ocupado mientras llega la respuesta. El error (422
//   invalid_phone, 429, 409...) se queda bajo el botón: texto fijo en los códigos conocidos, el del api en el resto.
import { useId, useRef, useState } from "react";
import { Link } from "react-router";
import { memberHref } from "../../../shared/lib/routes";
import { Button } from "../../../shared/ui/Button";
import { useWaLink } from "../api";
import { waLinkMessage } from "../noticeErrors";
import styles from "./WaButton.module.css";

export interface WaButtonProps {
  notificationId: string;
  memberName: string;
  /** Socio del aviso: destino del enlace a su ficha cuando no se puede abrir WhatsApp. */
  memberId: string;
  /** false = el api dice que no se puede abrir WhatsApp (sin decir el motivo, S9-D65). */
  canWhatsapp: boolean;
  /** Se llama una vez abierto WhatsApp. */
  onOpened?: () => void;
}

export function WaButton({ notificationId, memberName, memberId, canWhatsapp, onOpened }: WaButtonProps) {
  const waLink = useWaLink();
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);
  const reasonId = useId();
  const blocked = !canWhatsapp;

  const open = async (): Promise<void> => {
    if (blocked || busy.current) return;
    busy.current = true;
    setError(null);
    try {
      const { url } = await waLink.mutateAsync(notificationId);
      window.open(url, "_blank", "noopener,noreferrer");
      onOpened?.();
    } catch (cause) {
      setError(waLinkMessage(cause));
    } finally {
      busy.current = false;
    }
  };

  return (
    <div className={styles.wrap}>
      <Button
        className={styles.wa}
        loading={waLink.isPending}
        disabled={blocked}
        aria-describedby={blocked ? reasonId : undefined}
        aria-label={`Abrir WhatsApp de ${memberName}`}
        onClick={() => {
          void open();
        }}
      >
        Abrir WhatsApp
      </Button>
      {blocked ? (
        // DESIGN-GAP: PorAvisarHoy.html no trae el estado bloqueado; se usa texto de apoyo con --muted.
        <p id={reasonId} className={styles.reason}>
          <span>No se puede abrir WhatsApp</span>
          {" · "}
          <Link to={memberHref(memberId)} className={styles.reasonLink} aria-label={`Revisar la ficha de ${memberName}`}>
            Revisar la ficha
          </Link>
        </p>
      ) : null}
      {error && !blocked ? (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
