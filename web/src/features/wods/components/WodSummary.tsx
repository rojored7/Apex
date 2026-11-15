// S8-F3 · US-171 (front): «El WOD» de WOD_Detalle.html: tipo de marca, time cap, descripción y movimientos con repeticiones y cargas.
// DESIGN-GAP: «Escalado sugerido» y «Veces hecho en el box» no están en el contrato (EP-24).
import { formatLoadKg } from "../../../shared/data/score";
import { WOD_SCORE_LABELS, type WodView } from "../wodSchemas";
import styles from "./WodSummary.module.css";

const SECONDS_PER_MINUTE = 60;

function loadText(male: number | null, female: number | null): string {
  if (male === null && female === null) return "";
  return ` · ${male === null ? "—" : formatLoadKg(male)} / ${female === null ? "—" : formatLoadKg(female)}`;
}

export function WodSummary({ wod }: { wod: WodView }) {
  return (
    <section className={styles.box} aria-labelledby="wod-summary-title">
      <h2 id="wod-summary-title" className={styles.title}>
        El WOD
      </h2>
      <p className={styles.meta}>
        <b>{WOD_SCORE_LABELS[wod.score_type]}</b>
        {wod.time_cap_s === null ? "" : ` · límite ${String(Math.round(wod.time_cap_s / SECONDS_PER_MINUTE))} min`}
      </p>
      {wod.description.trim() === "" ? null : <p className={styles.description}>{wod.description}</p>}
      <ol className={styles.list}>
        {wod.movements.map((movement) => (
          <li key={movement.id}>
            {`${movement.reps} ${movement.movement_name}${loadText(movement.load_rx_m_g, movement.load_rx_f_g)}`}
            {movement.notes.trim() === "" ? "" : ` (${movement.notes})`}
          </li>
        ))}
      </ol>
    </section>
  );
}
