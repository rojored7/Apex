// S5-F5 · US-136: aviso discreto de "custodio de llaves no disponible" (503 crypto_unavailable).
// Presentacional: dice qué pasó y qué hacer; la espera llega por props.
// DESIGN-GAP: docs/design/ no dibuja este aviso; se usa una franja de aviso con los tokens de
// advertencia (--warning) y el borde de las tarjetas, sin colores literales.
import { Button } from "./Button";
import styles from "./CustodyNotice.module.css";

export interface CustodyNoticeProps {
  /** Segundos de Retry-After. */
  retryAfterS: number;
  onDismiss: () => void;
}

export const CUSTODY_TITLE = "Los datos protegidos no están disponibles por ahora.";

export function CustodyNotice({ retryAfterS, onDismiss }: CustodyNoticeProps) {
  const unit = retryAfterS === 1 ? "segundo" : "segundos";
  return (
    <div className={styles.notice} role="status">
      <p className={styles.text}>
        <strong className={styles.title}>{CUSTODY_TITLE}</strong>{" "}
        {`Intenta de nuevo en ${String(retryAfterS)} ${unit}. Si sigue igual, avisa al administrador del sistema.`}
      </p>
      <Button variant="secondary" onClick={onDismiss}>
        Cerrar aviso
      </Button>
    </div>
  );
}
