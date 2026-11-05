// S5-F1 · US-127 (front): "Abrir WhatsApp" de PorAvisarHoy.html.
// - Un POST (useWaLink) arma el enlace en el servidor y marca el aviso como enviado; solo tras el 200
//   se llama window.open(url, "_blank", "noopener,noreferrer"). La URL lleva el teléfono: vive en una
//   variable local, nunca en el estado, el DOM ni la caché de TanStack (M-9, S5-D59).
// - Objetivo táctil de 48 px (design: .w-wa); en celular ocupa todo el ancho de la tarjeta.
// - Un solo envío a la vez: el botón queda ocupado mientras llega la respuesta. El error (422
//   invalid_phone, 429, 409...) se queda bajo el botón con el mensaje del api.
import { useRef, useState } from "react";
import { Button } from "../../../shared/ui/Button";
import { useWaLink } from "../api";
import { waLinkMessage } from "../noticeErrors";
import styles from "./WaButton.module.css";

export interface WaButtonProps {
  notificationId: string;
  memberName: string;
  /** Se llama una vez abierto WhatsApp. */
  onOpened?: () => void;
}

export function WaButton({ notificationId, memberName, onOpened }: WaButtonProps) {
  const waLink = useWaLink();
  const [error, setError] = useState<string | null>(null);
  const busy = useRef(false);

  const open = async (): Promise<void> => {
    if (busy.current) return;
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
        aria-label={`Abrir WhatsApp de ${memberName}`}
        onClick={() => {
          void open();
        }}
      >
        Abrir WhatsApp
      </Button>
      {error ? (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      ) : null}
    </div>
  );
}
