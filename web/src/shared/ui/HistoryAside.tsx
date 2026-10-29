// US-066 T5: historial reciente del registro (Socio_Ficha.html, "Historial reciente").
// Fecha y hora de Bogotá, usuario ("Sistema" para el usuario técnico), entidad (N-31),
// acción en español (N-08) y resumen de lo que cambió; nunca descifra ni muestra blobs.
// La posición (derecha en escritorio, al final en celular) la da la cuadrícula de la ficha.
// S4A-F2 (US-106, S4A-D32): la feature members lo conecta a GET /members/{id}/audit. Una entrada con
// `phrase` ("ana editó teléfono y correo") la pinta como línea fuerte, con la entidad y la fecha debajo
// (la frase ya dice quién y qué, así que no se repite el resumen); con `purpose` lleva la etiqueta
// "automático (aviso)". Todo como texto de React: una frase con HTML se ve literal. `moreLabel` cambia
// el texto del botón ("Cargar más" en la pestaña) y `footer` va al final (el enlace de la caja).
import type { ReactNode } from "react";
import { isApiError } from "../../core/api/errors";
import { formatDateTime } from "../../core/i18n/format";
import { actionLabel, actorLabel, entityLabel, PURPOSE_LABEL, summarizeChange, type AuditEntryView } from "../lib/audit-labels";
import { Button } from "./Button";
import styles from "./HistoryAside.module.css";

export const HISTORY_GENERIC_ERROR = "No se pudo cargar el historial. Intenta de nuevo.";

export interface HistoryAsideProps {
  entries: AuditEntryView[];
  total: number;
  /** Pide la página siguiente con offset = entradas ya cargadas. */
  onLoadMore: (nextOffset: number) => void;
  isLoading?: boolean;
  error?: unknown;
  onRetry?: () => void;
  title?: string;
  /** S4A-F2: texto del botón que pide la página siguiente ("Ver más" por defecto). */
  moreLabel?: string;
  /** S4A-F2: contenido al final del aside (el enlace "Ver historial completo →", avisos de la lista). */
  footer?: ReactNode;
}

function Entry({ entry }: { entry: AuditEntryView }) {
  const phrase = entry.phrase?.trim() ? entry.phrase : null;
  const lines = phrase ? [] : summarizeChange(entry);
  const who = phrase ? entityLabel(entry.entity) : actorLabel(entry);
  return (
    <li className={styles.entry}>
      <span className={styles.head}>
        <b className={styles.what}>{phrase ?? `${entityLabel(entry.entity)} · ${actionLabel(entry.action)}`}</b>
        {entry.purpose ? <span className={styles.purpose}>{PURPOSE_LABEL}</span> : null}
      </span>
      {lines.map((line) => (
        <span key={line} className={styles.line}>
          {line}
        </span>
      ))}
      <span className={styles.meta}>
        {`${who} · `}
        <time dateTime={entry.at}>{formatDateTime(entry.at)}</time>
      </span>
    </li>
  );
}

export function HistoryAside({ entries, total, onLoadMore, isLoading = false, error, onRetry, title = "Historial reciente", moreLabel = "Ver más", footer }: HistoryAsideProps) {
  const firstLoad = isLoading && entries.length === 0;

  let body;
  if (error) {
    body = (
      <div className={styles.status}>
        <p role="alert" className={styles.error}>
          {isApiError(error) ? error.message : HISTORY_GENERIC_ERROR}
        </p>
        {onRetry ? (
          <Button variant="secondary" onClick={onRetry}>
            Reintentar
          </Button>
        ) : null}
      </div>
    );
  } else if (entries.length === 0) {
    body = <p className={styles.empty}>{firstLoad ? "Cargando historial" : "Sin cambios registrados"}</p>;
  } else {
    body = (
      <ol className={styles.list}>
        {entries.map((entry) => (
          <Entry key={entry.id} entry={entry} />
        ))}
      </ol>
    );
  }

  return (
    <aside aria-label="Historial" aria-busy={firstLoad ? true : undefined} className={styles.aside}>
      <h2 className={styles.title}>{title}</h2>
      {body}
      {!error && entries.length > 0 && entries.length < total ? (
        <Button
          variant="ghost"
          className={styles.more}
          loading={isLoading}
          onClick={() => {
            onLoadMore(entries.length);
          }}
        >
          {moreLabel}
        </Button>
      ) : null}
      {footer}
    </aside>
  );
}
