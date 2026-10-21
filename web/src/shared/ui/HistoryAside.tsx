// US-066 T5: historial reciente del registro (Socio_Ficha.html, "Historial reciente").
// Fecha y hora de Bogotá, usuario ("Sistema" para el usuario técnico), entidad (N-31),
// acción en español (N-08) y resumen de lo que cambió; nunca descifra ni muestra blobs.
// La posición (derecha en escritorio, al final en celular) la da la cuadrícula de la ficha.
// Criterio diferido: la feature lo conecta a GET /members/{id}/audit?limit&offset en US-106.
import { isApiError } from "../../core/api/errors";
import { formatDateTime } from "../../core/i18n/format";
import { actionLabel, actorLabel, entityLabel, summarizeChange, type AuditEntryView } from "../lib/audit-labels";
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
}

function Entry({ entry }: { entry: AuditEntryView }) {
  const lines = summarizeChange(entry);
  return (
    <li className={styles.entry}>
      <b className={styles.what}>{`${entityLabel(entry.entity)} · ${actionLabel(entry.action)}`}</b>
      {lines.map((line) => (
        <span key={line} className={styles.line}>
          {line}
        </span>
      ))}
      <span className={styles.meta}>
        {`${actorLabel(entry)} · `}
        <time dateTime={entry.at}>{formatDateTime(entry.at)}</time>
      </span>
    </li>
  );
}

export function HistoryAside({ entries, total, onLoadMore, isLoading = false, error, onRetry, title = "Historial reciente" }: HistoryAsideProps) {
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
          Ver más
        </Button>
      ) : null}
    </aside>
  );
}
