// S9-F1 · US-184 (Atleta_Perfil.html, subpestaña «Resumen»): GET /athletes/{id}/summary, sin ninguna medida (S9-D16).
// - Cuatro tarjetas: «Medidas corporales» (cuántas y la fecha de la última), «RMs por movimiento» (cuántos vigentes), «Récords
//   recientes» (los tres vigentes más recientes con su origen en palabras) y «Benchmarks» (con cuántos hay intentos); cada «Ver todas»
//   lleva a su subpestaña con `?tab=`.
// - Estados: carga, error con Reintentar (403, 404, 5xx), vacío por tarjeta y el aviso `truncated`.
// DESIGN-GAP: la gráfica de peso, el selector «peso, % grasa, cintura…» y «Laura (portal)» no están en el contrato.
import type { ReactNode } from "react";
import { Link } from "react-router";
import { formatDate } from "../../../core/i18n/format";
import { Button } from "../../../shared/ui/Button";
import { cx } from "../../../shared/ui/cx";
import { useAthleteSummary } from "../api";
import { summaryError } from "../athleteErrors";
import { recordTitle, recordValue } from "../recordFormat";
import type { AthleteSummaryView, SummaryRecordView } from "../schemas";
import styles from "./SummaryCards.module.css";

export interface SummaryCardsProps {
  memberId: string;
}

export const TRUNCATED_NOTICE = "El resumen puede quedar corto: hay más marcas de las que se leen aquí. Revisa cada subpestaña para verlas todas.";

const tabHref = (memberId: string, tab: string): string => `/socios/${encodeURIComponent(memberId)}/atleta?tab=${tab}`;
const plural = (count: number, one: string, many: string): string => `${String(count)} ${count === 1 ? one : many}`;

interface CardProps {
  summary: AthleteSummaryView;
  memberId: string;
}

function Card({ title, wide = false, children }: { title: string; wide?: boolean; children: ReactNode }) {
  return (
    <section className={cx(styles.card, wide && styles.wide)}>
      <h2 className={styles.title}>{title}</h2>
      {children}
    </section>
  );
}

function MetricsCard({ summary, memberId }: CardProps) {
  const count = summary.metrics_count;
  return (
    <Card title="Medidas corporales">
      {count === 0 ? (
        <p className={styles.empty}>Todavía no hay medidas registradas.</p>
      ) : (
        <>
          <p className={styles.text}>{plural(count, "medición registrada", "mediciones registradas")}</p>
          {summary.last_metric_on === null ? null : <p className={styles.text}>{`Última medición: ${formatDate(summary.last_metric_on)}`}</p>}
          <p className={styles.note}>Medidas cifradas en la base: se ven con «Mostrar» en la lista, una por una.</p>
          <Link className={styles.link} to={tabHref(memberId, "medidas")}>
            {`Ver todas (${String(count)})`}
          </Link>
        </>
      )}
    </Card>
  );
}

function RmsCard({ summary, memberId }: CardProps) {
  const count = summary.current_rms;
  return (
    <Card title="RMs por movimiento">
      {count === 0 ? (
        <p className={styles.empty}>Todavía no hay RMs vigentes.</p>
      ) : (
        <>
          <p className={styles.text}>{plural(count, "RM vigente", "RMs vigentes")}</p>
          <Link className={styles.link} to={tabHref(memberId, "rms")}>
            {`Ver todos (${String(count)})`}
          </Link>
        </>
      )}
    </Card>
  );
}

function BenchmarksCard({ summary, memberId }: CardProps) {
  const count = summary.benchmarks_with_attempts;
  return (
    <Card title="Benchmarks">
      {count === 0 ? (
        <p className={styles.empty}>Todavía no hay intentos en benchmarks.</p>
      ) : (
        <>
          <p className={styles.text}>{`${plural(count, "benchmark", "benchmarks")} con intentos`}</p>
          <Link className={styles.link} to={tabHref(memberId, "benchmarks")}>
            Ver todos
          </Link>
        </>
      )}
    </Card>
  );
}

function Origin({ record }: { record: SummaryRecordView }) {
  if (record.source === "manual") return <span>manual</span>;
  return (
    <span>
      <span>automático</span>
      {record.wod_id === null ? null : (
        <>
          {" "}
          <span>del WOD</span>{" "}
          <Link className={styles.link} to={`/wods/${encodeURIComponent(record.wod_id)}`}>
            ver
          </Link>
        </>
      )}
    </span>
  );
}

function RecordsCard({ summary, memberId }: CardProps) {
  const records = summary.recent_records;
  return (
    <Card title="Récords recientes" wide>
      {records.length === 0 ? (
        <p className={styles.empty}>Todavía no hay récords vigentes.</p>
      ) : (
        <>
          <div className={styles.scroll}>
            <table className={styles.table}>
              <caption className={styles.srOnly}>Récords vigentes más recientes</caption>
              <thead>
                <tr>
                  <th scope="col">Fecha</th>
                  <th scope="col">Récord</th>
                  <th scope="col">Valor</th>
                  <th scope="col">Origen</th>
                </tr>
              </thead>
              <tbody>
                {records.map((record) => (
                  <tr key={record.id}>
                    <td className={styles.nowrap}>{formatDate(record.achieved_on)}</td>
                    <td>{recordTitle(record)}</td>
                    <td className={styles.nowrap}>{recordValue(record)}</td>
                    <td>
                      <Origin record={record} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Link className={styles.link} to={tabHref(memberId, "records")}>
            Ver todos
          </Link>
        </>
      )}
    </Card>
  );
}

export function SummaryCards({ memberId }: SummaryCardsProps) {
  const query = useAthleteSummary(memberId);
  const error = summaryError(query.error);
  if (error) {
    return (
      <div className={cx(styles.state, styles.error)} role="alert">
        <p className={styles.text}>{error.message}</p>
        <Button
          variant="secondary"
          onClick={() => {
            void query.refetch();
          }}
        >
          Reintentar
        </Button>
      </div>
    );
  }
  const summary = query.data;
  if (summary === undefined) {
    return (
      <p className={styles.state} role="status">
        Cargando el resumen…
      </p>
    );
  }
  return (
    <div className={styles.state}>
      {summary.truncated ? <p className={styles.truncated}>{TRUNCATED_NOTICE}</p> : null}
      <div className={styles.grid}>
        <MetricsCard summary={summary} memberId={memberId} />
        <RmsCard summary={summary} memberId={memberId} />
        <RecordsCard summary={summary} memberId={memberId} />
        <BenchmarksCard summary={summary} memberId={memberId} />
      </div>
    </div>
  );
}
