// S8-F6 · US-177: el WOD del día en la TV (TV.html, columna izquierda): título en Michroma, píldoras (Benchmark, tipo y límite),
// descripción y movimientos con su carga Rx. Las cargas llegan en gramos enteros (S8-D41) y se ven en kg con formatLoadKg.
// Todo se pinta como texto (React escapa); nunca innerHTML.
// DESIGN-GAP: TV.html dibuja «Escalado: KB 16/12 kg…» al pie: el contrato de la TV no trae el escalado (S8-D18), no se dibuja.
import { formatLoadKg, formatSeconds, SCORE_TYPE_LABELS } from "../../../shared/data/score";
import type { TvWodView } from "../schemas";
import styles from "./TvWod.module.css";

type Movement = TvWodView["movements"][number];

/** «24 / 16 kg» (hombres / mujeres), «24 kg» si solo hay una, o null sin carga. */
function loadText(movement: Movement): string | null {
  const male = movement.load_rx_m_g;
  const female = movement.load_rx_f_g;
  if (male !== null && female !== null) return `${formatLoadKg(male).replace(" kg", "")} / ${formatLoadKg(female)}`;
  const only = male ?? female;
  return only === null ? null : formatLoadKg(only);
}

export function TvWod({ wod }: { wod: TvWodView }) {
  return (
    <section className={styles.wod} aria-label="WOD del día">
      <p className={styles.eyebrow}>WOD del día</p>
      <h2 className={styles.title}>{wod.title}</h2>
      <ul className={styles.pills} aria-label="Datos del WOD">
        {wod.is_benchmark ? <li className={styles.pill}>Benchmark</li> : null}
        {wod.score_type === "none" ? null : <li className={styles.pill}>{SCORE_TYPE_LABELS[wod.score_type]}</li>}
        {wod.time_cap_s === null ? null : <li className={styles.pill}>{`Límite ${formatSeconds(wod.time_cap_s)}`}</li>}
      </ul>
      {wod.description === "" ? null : <p className={styles.description}>{wod.description}</p>}
      <ul className={styles.movements} aria-label="Movimientos">
        {wod.movements.map((movement, index) => {
          const load = loadText(movement);
          return (
            // El orden del WOD no cambia entre dos lecturas y un nombre puede repetirse: posición y nombre hacen la llave.
            <li key={`${String(index)}-${movement.name}`}>
              {`${movement.reps} ${movement.name}`}
              {load === null ? null : (
                <>
                  {" · "}
                  <span className={styles.load}>{load}</span>
                </>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
