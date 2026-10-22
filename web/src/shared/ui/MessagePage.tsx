// S2-F2: página de mensaje (No encontrada, Sin permiso, Disponible pronto). Un único h1, un
// texto que dice qué pasó y qué hacer, y un enlace de salida.
// DESIGN-GAP: docs/design/screens/ no dibuja páginas de error ni de permiso; se usa una caja
// como la tarjeta de Login.html con el título en --text-screen-title.
import { useId } from "react";
import { Link } from "react-router";
import buttonStyles from "./Button.module.css";
import { cx } from "./cx";
import styles from "./MessagePage.module.css";

export interface MessagePageProps {
  title: string;
  message: string;
  linkLabel?: string | undefined;
  linkTo?: string | undefined;
}

export function MessagePage({ title, message, linkLabel, linkTo }: MessagePageProps) {
  const titleId = useId();
  return (
    <section className={styles.page} aria-labelledby={titleId}>
      <h1 id={titleId} className={styles.title}>
        {title}
      </h1>
      <p className={styles.message}>{message}</p>
      {linkTo !== undefined && linkLabel !== undefined && (
        <Link to={linkTo} className={cx(buttonStyles.button, buttonStyles.secondary, buttonStyles.md, styles.link)}>
          {linkLabel}
        </Link>
      )}
    </section>
  );
}
