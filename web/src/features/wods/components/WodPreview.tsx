// S8-F2 · US-167 (front): vista previa del WOD en WOD_Form.html, tal como lo leerá el coach en la pizarra.
import { formatLoadKg, kgInputToGrams } from "../../../shared/data/score";
import { WOD_SCORE_LABELS, type WodFormValues } from "../wodSchemas";
import styles from "./WodPreview.module.css";

export interface WodPreviewProps {
  values: WodFormValues;
}

function loadText(male: string, female: string): string {
  const m = kgInputToGrams(male);
  const f = kgInputToGrams(female);
  if (m === null && f === null) return "";
  return ` (${m === null ? "—" : formatLoadKg(m)} / ${f === null ? "—" : formatLoadKg(f)})`;
}

export function WodPreview({ values }: WodPreviewProps) {
  return (
    <aside className={styles.preview} aria-label="Vista previa del WOD">
      <p className={styles.kicker}>Vista previa</p>
      <h2 className={styles.title}>{values.title.trim() === "" ? "Sin título" : values.title.trim()}</h2>
      <p className={styles.meta}>
        {WOD_SCORE_LABELS[values.score_type]}
        {values.time_cap_min.trim() === "" ? "" : ` · Time cap ${values.time_cap_min} min`}
      </p>
      {values.description.trim() === "" ? null : <p className={styles.description}>{values.description.trim()}</p>}
      {values.movements.length === 0 ? (
        <p className={styles.empty}>Agrega movimientos para verlos aquí.</p>
      ) : (
        <ul className={styles.list}>
          {values.movements.map((row) => (
            <li key={row.key}>
              <b>{row.reps.trim()}</b> {row.movement_name}
              {loadText(row.load_m, row.load_f)}
              {row.is_primary ? " · principal" : ""}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
