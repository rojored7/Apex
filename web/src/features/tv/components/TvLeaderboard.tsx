// S8-F6 · US-177 (S8-D19): el ranking «Todos» de la TV, un solo ranking (Rx y Rx+ por marca y después escalados, ya ordenado por el api).
// - 15 filas por página; con más, la página avanza sola cada 12 s y da la vuelta. Con 15 o menos no rota.
// - Posición, `Nombre I.`, marca (formatScore: gramos a kg, DNF) y nivel. Nunca más datos: el api no los manda.
// - Sin resultados: «Registra tu resultado con el coach».
// DESIGN-GAP: TV.html agrupa por sexo y nivel (RX Mujeres, RX Hombres, Escalado) y muestra la diferencia con la vez anterior y «PR»:
// el contrato de la TV es un solo ranking «Todos» sin sexo (S8-D19, P1 del orquestador) y no trae el historial (EP-24).
import { useEffect, useState } from "react";
import { formatScore, type ScoreKind } from "../../../shared/data/score";
import type { TvRowView } from "../schemas";
import styles from "./TvLeaderboard.module.css";

export const TV_PAGE_ROWS = 15;
export const TV_ROTATE_MS = 12_000;

const LEVEL_TEXT = { rx: "RX", rx_plus: "RX+", scaled: "Escalado" } as const;

export interface TvLeaderboardProps {
  rows: readonly TvRowView[];
  scoreType: ScoreKind;
}

export function TvLeaderboard({ rows, scoreType }: TvLeaderboardProps) {
  const pages = Math.max(1, Math.ceil(rows.length / TV_PAGE_ROWS));
  const [shown, setShown] = useState(0);
  // Si el ranking se acorta, la página mostrada se ajusta en el mismo render (sin esperar al reloj).
  const current = shown < pages ? shown : 0;

  useEffect(() => {
    if (pages <= 1) return undefined;
    const timer = setInterval(() => {
      setShown((previous) => (previous + 1 < pages ? previous + 1 : 0));
    }, TV_ROTATE_MS);
    return () => {
      clearInterval(timer);
    };
  }, [pages]);

  if (rows.length === 0) {
    return (
      <section className={styles.board} aria-label="Ranking">
        <h2 className={styles.title}>Ranking</h2>
        <p className={styles.empty}>Registra tu resultado con el coach</p>
      </section>
    );
  }
  const visible = rows.slice(current * TV_PAGE_ROWS, (current + 1) * TV_PAGE_ROWS);
  return (
    <section className={styles.board} aria-label="Ranking">
      <div className={styles.head}>
        <h2 className={styles.title}>Ranking</h2>
        {pages > 1 ? <span className={styles.page}>{`Página ${String(current + 1)} de ${String(pages)}`}</span> : null}
      </div>
      <table className={styles.table} aria-label="Ranking del WOD">
        <thead>
          <tr>
            <th scope="col">Puesto</th>
            <th scope="col">Atleta</th>
            <th scope="col">Marca</th>
            <th scope="col">Nivel</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((row, index) => (
            <tr key={`${String(current)}-${String(index)}`}>
              <td className={styles.pos}>{row.position}</td>
              <td className={styles.name}>{row.display_name}</td>
              <td className={styles.mark}>{formatScore(scoreType, row.score)}</td>
              <td className={styles.level}>{LEVEL_TEXT[row.level]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
