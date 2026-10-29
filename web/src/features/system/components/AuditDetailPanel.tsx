// S4A-F1 · US-103 (front; S4A-D31, S4A-D52, S4A-D58): el detalle de una entrada de auditoría en un
// SidePanel sobre la lista, abierto por `?seq=`. Solo lectura.
// - `rawSeq` llega tal cual de la URL: si no es un entero seguro >= 1 no hay panel ni petición.
// - Metadatos (entrada, fecha y hora de Bogotá, usuario, acción, entidad, registro y socio), la lista
//   de cambios antes → después y los dos hashes en monoespaciada.
// - Todo valor se pinta como texto (auditValueText): un valor cifrado es "Cifrado" con su llave, un
//   objeto se aplana y se corta a 2.000 caracteres.
// DESIGN-GAP: sin Descifrar dato ni Mostrar (US-103 lo prohíbe en la auditoría); Auditoria.html pinta
// los cifrados como "[cifrado · ver]" y los descifra uno a uno con "ver". Aquí solo "Cifrado" y la llave.
// DESIGN-GAP: el diseño muestra la IP de origen ("desde 181.•••.•••.12") y "hash ok · hash anterior
// ok" por fila; AuditDetail no trae la IP y la integridad se comprueba con "Verificar ahora" (US-104).
// DESIGN-GAP: Auditoria.html enseña valores enmascarados (310•••221); el api no enmascara en la
// auditoría y los campos cifrados nunca salen, así que no hay valor enmascarado que mostrar.
import { Link } from "react-router";
import { HTTP_NOT_FOUND } from "../../../core/api/status";
import { formatDateTime } from "../../../core/i18n/format";
import { FIELD_LABELS } from "../../../shared/lib/audit-labels";
import { memberHref } from "../../../shared/lib/routes";
import { Button } from "../../../shared/ui/Button";
import { SidePanel } from "../../../shared/ui/SidePanel";
import { useAuditEntry } from "../api";
import { auditEntryError } from "../auditErrors";
import { actionLabel, auditUserLabel, parseSeq, tableLabel } from "../auditFilters";
import { auditKeyText, auditValueText } from "../auditValues";
import type { AuditDetailView, FieldChangeView } from "../schemas";
import styles from "./AuditDetailPanel.module.css";

export interface AuditDetailPanelProps {
  /** El `?seq=` de la URL, sin validar. */
  rawSeq: string | null;
  onClose: () => void;
}

const fieldLabel = (field: string): string => FIELD_LABELS[field] ?? auditKeyText(field);

function ChangeItem({ change, index }: { change: FieldChangeView; index: number }) {
  return (
    <li className={styles.change}>
      <span className={styles.field}>{fieldLabel(change.field)}</span>
      <span className={styles.diff}>
        <span className={styles.before} data-testid={`audit-value-before-${String(index)}`}>
          {auditValueText(change.before, change.encrypted)}
        </span>
        <span> → </span>
        <span className={styles.after} data-testid={`audit-value-after-${String(index)}`}>
          {auditValueText(change.after, change.encrypted)}
        </span>
      </span>
    </li>
  );
}

function EntryBody({ entry }: { entry: AuditDetailView }) {
  return (
    <div className={styles.body}>
      <dl className={styles.meta}>
        <dt>Fecha y hora</dt>
        <dd>{formatDateTime(entry.at)}</dd>
        <dt>Usuario</dt>
        <dd>{auditUserLabel(entry)}</dd>
        <dt>Acción</dt>
        <dd>{actionLabel(entry.action)}</dd>
        <dt>Entidad</dt>
        <dd>{tableLabel(entry.table_name)}</dd>
        {entry.record_id ? (
          <>
            <dt>Registro</dt>
            <dd>
              <code className={styles.mono}>{entry.record_id}</code>
            </dd>
          </>
        ) : null}
        {entry.subject_member_id ? (
          <>
            <dt>Socio del registro</dt>
            <dd>
              <Link to={memberHref(entry.subject_member_id)}>Ver la ficha del socio</Link>
            </dd>
          </>
        ) : null}
      </dl>
      <h3 className={styles.subtitle}>Cambios</h3>
      {entry.changes.length > 0 ? (
        <ul aria-label="Cambios" className={styles.changes}>
          {entry.changes.map((change, index) => (
            <ChangeItem key={`${change.field}-${String(index)}`} change={change} index={index} />
          ))}
        </ul>
      ) : (
        <p className={styles.note}>Esta acción no cambió campos del registro.</p>
      )}
      <h3 className={styles.subtitle}>Cadena</h3>
      <dl className={styles.meta}>
        <dt>Hash anterior</dt>
        <dd>
          <code className={styles.mono}>{entry.prev_hash}</code>
        </dd>
        <dt>Hash</dt>
        <dd>
          <code className={styles.mono}>{entry.hash}</code>
        </dd>
      </dl>
      <p className={styles.note}>Solo lectura: nada se edita ni se borra desde aquí.</p>
    </div>
  );
}

function EntryContent({ seq }: { seq: number }) {
  const entry = useAuditEntry(seq);
  // Se decide por los datos antes que por el error: una relectura fallida no borra lo que se ve.
  if (entry.data !== undefined) return <EntryBody entry={entry.data} />;
  const error = auditEntryError(entry.error);
  if (error) {
    const isGone = error.status === HTTP_NOT_FOUND;
    return (
      <div role="alert" className={styles.alert}>
        <p>{error.message}</p>
        {isGone ? null : (
          <Button
            variant="secondary"
            onClick={() => {
              void entry.refetch();
            }}
          >
            Reintentar
          </Button>
        )}
      </div>
    );
  }
  return (
    <p role="status" className={styles.note}>
      Cargando la entrada…
    </p>
  );
}

export function AuditDetailPanel({ rawSeq, onClose }: AuditDetailPanelProps) {
  const seq = parseSeq(rawSeq);
  return (
    <SidePanel open={seq !== null} title={`Entrada #${String(seq ?? "")}`} onClose={onClose} cancelLabel="Cerrar detalle">
      {seq !== null ? <EntryContent key={seq} seq={seq} /> : null}
    </SidePanel>
  );
}
