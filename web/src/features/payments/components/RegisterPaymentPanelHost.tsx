// S3-F4 (S3-D65, E10): el punto de montaje único del panel "Registrar pago". PanelShell lo descarga y
// lo monta cuando la URL trae `?pago=`; cualquier pantalla lo abre con un enlace de
// shared/lib/paymentPanel.ts (ninguna feature importa a otra).
// - Sin `?pago=` (o con un valor que no sirve) no pinta nada ni pide datos.
// - La precarga desde una anulación llega en el estado de la navegación.
// - Cerrar quita `?pago=` (y su `socio`) conservando los demás parámetros, reemplazando la entrada
//   del historial: "Atrás" no vuelve a abrir el panel.
import { useLocation, useNavigate } from "react-router";
import { closePaymentPanelHref, readPaymentPanel, readPaymentPrefill } from "../../../shared/lib/paymentPanel";
import { RegisterPaymentPanel } from "./RegisterPaymentPanel";

export function RegisterPaymentPanelHost() {
  const location = useLocation();
  const navigate = useNavigate();
  const target = readPaymentPanel(location.search);
  if (!target) return null;
  // Una URL nueva (otra membresía u otro socio) empieza un panel limpio.
  const key = target.kind === "membership" ? target.membershipId : `nuevo:${target.memberId ?? ""}`;
  return (
    <RegisterPaymentPanel
      key={key}
      target={target}
      prefill={readPaymentPrefill(location.state)}
      onClose={() => {
        void navigate(closePaymentPanelHref(location), { replace: true });
      }}
    />
  );
}
