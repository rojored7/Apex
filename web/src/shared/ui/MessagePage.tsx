// S2-F2: página de mensaje (No encontrada, Sin permiso). Un único h1, un texto que dice qué
// pasó y qué hacer, y un enlace de salida. H1 (revisión del Sprint 2): con `alert` el texto se
// anuncia (role="alert") y `children` pone una acción propia (el botón "Recargar").
// DESIGN-GAP: docs/design/screens/ no dibuja páginas de error ni de permiso; se usa una caja
// como la tarjeta de Login.html con el título en --text-screen-title.
import { useId, type ReactNode } from "react";
import { Link } from "react-router";
import buttonStyles from "./Button.module.css";
import { cx } from "./cx";
import styles from "./MessagePage.module.css";

export interface MessagePageProps {
  title: string;
  message: string;
  linkLabel?: string | undefined;
  linkTo?: string | undefined;
  /** El mensaje es un error que se anuncia al aparecer. */
  alert?: boolean;
  /** Acción propia bajo el mensaje (por ejemplo un botón). */
  children?: ReactNode;
}

export function MessagePage({ title, message, linkLabel, linkTo, alert = false, children }: MessagePageProps) {
  const titleId = useId();
  return (
    <section className={styles.page} aria-labelledby={titleId}>
      <h1 id={titleId} className={styles.title}>
        {title}
      </h1>
      <p className={styles.message} role={alert ? "alert" : undefined}>
        {message}
      </p>
      {children}
      {linkTo !== undefined && linkLabel !== undefined && (
        <Link to={linkTo} className={cx(buttonStyles.button, buttonStyles.secondary, buttonStyles.md, styles.link)}>
          {linkLabel}
        </Link>
      )}
    </section>
  );
}
