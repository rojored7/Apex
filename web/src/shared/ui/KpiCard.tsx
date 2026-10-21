// US-064 T3: tarjeta de indicador (Inicio.html). Un valor null es "Disponible en v0.x",
// nunca un cero engañoso (EP-12). Con enlace, toda la tarjeta es un único destino.
import { useId } from "react";
import { Link } from "react-router";
import { formatCop, formatCount } from "../../core/i18n/format";
import { Button } from "./Button";
import { cx } from "./cx";
import styles from "./KpiCard.module.css";

export interface KpiCardProps {
  label: string;
  value: number | null | undefined;
  /** `money` usa formatCop; `count`, separador de miles. */
  kind: "money" | "count";
  /** Versión en la que llega el dato cuando el api lo manda en null ("v0.2"). */
  availableIn?: string;
  note?: string;
  /** Variación ya formateada ("+12 esta semana"). */
  delta?: string;
  href?: string;
  /** Pide atención: fondo --blue-tint y borde azul. */
  attention?: boolean;
  isLoading?: boolean;
  error?: boolean;
  onRetry?: () => void;
}

function display(value: number | null | undefined, kind: KpiCardProps["kind"]): string | null {
  if (value === null || value === undefined) return null;
  return kind === "money" ? formatCop(value) : formatCount(value);
}

export function KpiCard({
  label,
  value,
  kind,
  availableIn,
  note,
  delta,
  href,
  attention = false,
  isLoading = false,
  error = false,
  onRetry,
}: KpiCardProps) {
  const baseId = useId();
  const labelId = `${baseId}-label`;
  const noteId = `${baseId}-note`;
  const deltaId = `${baseId}-delta`;
  const formatted = display(value, kind);
  const emptyText = availableIn ? `Disponible en ${availableIn}` : "Sin datos";
  const className = cx(styles.card, attention && styles.attention);

  if (isLoading || error) {
    return (
      <div role="group" aria-labelledby={labelId} aria-busy={isLoading ? true : undefined} className={className}>
        <span id={labelId} className={styles.label}>
          {label}
        </span>
        {isLoading ? (
          <>
            <span className={styles.skeleton} aria-hidden="true" />
            <span className={styles.srOnly}>Cargando</span>
          </>
        ) : (
          <>
            <span className={styles.errorText}>No se pudo cargar</span>
            {onRetry ? (
              <Button variant="secondary" onClick={onRetry} className={styles.retry}>
                Reintentar
              </Button>
            ) : null}
          </>
        )}
      </div>
    );
  }

  const body = (
    <>
      <span id={labelId} className={styles.label}>
        {label}
      </span>
      {formatted === null ? <span className={styles.empty}>{emptyText}</span> : <span className={styles.value}>{formatted}</span>}
      {delta ? (
        <span id={deltaId} className={styles.delta}>
          {delta}
        </span>
      ) : null}
      {note ? (
        <span id={noteId} className={styles.note}>
          {note}
        </span>
      ) : null}
    </>
  );

  if (href) {
    const describedBy = [delta ? deltaId : null, note ? noteId : null].filter(Boolean).join(" ");
    return (
      <Link
        to={href}
        className={cx(className, styles.link)}
        aria-label={`${label}: ${formatted ?? emptyText}`}
        {...(describedBy ? { "aria-describedby": describedBy } : {})}
      >
        {body}
      </Link>
    );
  }

  return (
    <div role="group" aria-labelledby={labelId} className={className}>
      {body}
    </div>
  );
}
