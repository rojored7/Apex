// S9-F3 · US-183: TrendChart, gráfica de línea simple en SVG con solo tokens (los colores viven en TrendChart.module.css).
// - <svg role="img"> con aria-label que describe la serie con palabras, sin depender del color:
//   «<título>: N puntos. <label>: <texto>; <label>: <texto> (mejor); ...». Con más de 12 puntos resume (cantidad, primero, último y
//   mejor): la tabla que acompaña a la gráfica es su equivalente completo.
// - El mejor punto se distingue por forma y tamaño (data-best="true", radio mayor), no solo por color.
// - Los puntos se reparten parejo en horizontal (en el orden recibido) y en vertical entre el mínimo y el máximo de `value`; arriba
//   queda el mayor, o el menor con `lowerIsBetter` (así el mejor punto de una serie por tiempo también queda arriba).
// - Los valores que no son números finitos se ignoran. Las fechas de los extremos van en HTML debajo del SVG (no se deforman al escalar).
// - Un solo punto: un círculo y ninguna línea (ni eje). Con dos o más, el eje cubre de la primera a la última posición de punto.
// - Un solo punto: un círculo y ninguna línea. Sin puntos: sin SVG, solo el mensaje (por omisión «Sin datos para graficar.»).
import styles from "./TrendChart.module.css";

export interface TrendPoint {
  /** Identifica el punto (la clave de React). */
  id: string;
  /** El texto del eje y del aria-label: «20 oct 2026». */
  label: string;
  /** El valor numérico que se dibuja. */
  value: number;
  /** El valor como se lee: «4:05». */
  text: string;
  /** El mejor punto de la serie: se marca con forma y texto, no solo con color. */
  isBest?: boolean;
}

export interface TrendChartProps {
  /** Nombre de la serie («Fran»): abre el aria-label. */
  title: string;
  points: readonly TrendPoint[];
  /** Lo que se dice sin puntos. */
  emptyMessage?: string;
  /** Un valor menor es mejor (tiempos): la escala vertical se invierte y el mejor punto queda arriba. */
  lowerIsBetter?: boolean;
}

export const TREND_EMPTY = "Sin datos para graficar.";

const WIDTH = 360;
const HEIGHT = 120;
const PAD_X = 16;
const PAD_Y = 14;
const RADIUS = 4;
const RADIUS_BEST = 7;
const DECIMALS = 1;
/** Hasta aquí el aria-label lista cada punto; con más resume. */
const DETAIL_MAX = 12;

interface Placed {
  point: TrendPoint;
  x: number;
  y: number;
}

const round = (value: number): number => Number(value.toFixed(DECIMALS));

function extent(points: readonly TrendPoint[]): { min: number; span: number } {
  const first = points[0]?.value ?? 0;
  const { min, max } = points.reduce((acc, { value }) => ({ min: Math.min(acc.min, value), max: Math.max(acc.max, value) }), { min: first, max: first });
  return { min, span: max - min };
}

function place(points: readonly TrendPoint[], lowerIsBetter: boolean): Placed[] {
  const { min, span } = extent(points);
  const innerW = WIDTH - 2 * PAD_X;
  const top = PAD_Y;
  const bottom = HEIGHT - PAD_Y;
  return points.map((point, index) => {
    // Una línea plana (o un solo punto) va a media altura; sin dividir entre cero.
    const ratio = span === 0 || !Number.isFinite(span) ? 0.5 : (point.value - min) / span;
    const up = lowerIsBetter ? 1 - ratio : ratio;
    return {
      point,
      x: round(points.length === 1 ? WIDTH / 2 : PAD_X + (innerW * index) / (points.length - 1)),
      y: round(bottom - (bottom - top) * up),
    };
  });
}

const line = (point: TrendPoint): string => `${point.label}: ${point.text}`;

function describe(title: string, points: readonly TrendPoint[]): string {
  const count = points.length === 1 ? "1 punto" : `${String(points.length)} puntos`;
  if (points.length <= DETAIL_MAX) return `${title}: ${count}. ${points.map((point) => line(point) + (point.isBest === true ? " (mejor)" : "")).join("; ")}`;
  const first = points[0];
  const last = points[points.length - 1];
  const best = points.find((point) => point.isBest === true);
  const parts = [first ? `primero ${line(first)}` : "", last ? `último ${line(last)}` : "", best ? `mejor ${line(best)}` : ""].filter((part) => part !== "");
  return `${title}: ${count}. ${parts.join("; ")}`;
}

export function TrendChart({ title, points, emptyMessage = TREND_EMPTY, lowerIsBetter = false }: TrendChartProps) {
  const drawable = points.filter((point) => Number.isFinite(point.value));
  if (drawable.length === 0) return <p className={styles.empty}>{emptyMessage}</p>;
  const placed = place(drawable, lowerIsBetter);
  const first = drawable[0];
  const last = drawable[drawable.length - 1];
  return (
    <div className={styles.wrap}>
      <svg className={styles.chart} viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`} role="img" aria-label={describe(title, drawable)}>
        {placed.length > 1 ? <line className={styles.axis} x1={PAD_X} x2={WIDTH - PAD_X} y1={HEIGHT - 2} y2={HEIGHT - 2} /> : null}
        {placed.length > 1 ? <polyline className={styles.line} points={placed.map(({ x, y }) => `${String(x)},${String(y)}`).join(" ")} /> : null}
        {placed.map(({ point, x, y }) => (
          <circle key={point.id} className={point.isBest === true ? styles.best : styles.dot} cx={x} cy={y} r={point.isBest === true ? RADIUS_BEST : RADIUS} {...(point.isBest === true ? { "data-best": "true" } : {})} />
        ))}
      </svg>
      <div className={styles.ticks} aria-hidden="true">
        <span>{first?.label}</span>
        {drawable.length > 1 ? <span>{last?.label}</span> : null}
      </div>
    </div>
  );
}
