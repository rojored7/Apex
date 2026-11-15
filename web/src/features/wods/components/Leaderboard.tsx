// S8-F3 · US-171 (S8-D13): leaderboard del WOD (WOD_Detalle.html). La posición la calcula el servidor (empates 1-2-2-4; quien no
// terminó va al final): aquí solo se muestra. Filtros por nivel y sexo en el servidor; paginado en el servidor.
// DESIGN-GAP: «vs. su anterior», «PR» (EP-24) y «Buscar atleta» (el endpoint no recibe `q`) no están en el contrato.
import { useState } from "react";
import { formatScore } from "../../../shared/data/score";
import { LEVEL_LABELS, useLeaderboard, type LeaderboardRowView, type ResultLevel, type ResultSex } from "../../../shared/data/results";
import { resultsLoadError } from "../../../shared/data/resultErrors";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { Pagination } from "../../../shared/ui/Pagination";
import { Segmented } from "../../../shared/ui/Segmented";
import { WOD_SCORE_LABELS, type WodScoreType } from "../wodSchemas";
import styles from "./Leaderboard.module.css";

export const LEADERBOARD_EMPTY = "Todavía no hay resultados para estos filtros. Regístralos desde la tablet de la clase.";
export const LEADERBOARD_NOTE =
  "Orden: tiempo menor primero; quien no terminó va al final ordenado por repeticiones. Para rondas y repeticiones: más rondas, luego más repeticiones. Para carga: mayor carga.";

const ALL = "all";
const LEVEL_OPTIONS = [
  { value: ALL, label: "Todos los niveles" },
  { value: "rx", label: "RX" },
  { value: "rx_plus", label: "RX+" },
  { value: "scaled", label: "Escalado" },
] as const;
const SEX_OPTIONS = [
  { value: ALL, label: "Todos" },
  { value: "f", label: "Mujeres" },
  { value: "m", label: "Hombres" },
] as const;
const DEFAULT_PAGE_SIZE = 50;

export interface LeaderboardProps {
  wodId: string;
  scoreType: WodScoreType;
}

export function Leaderboard({ wodId, scoreType }: LeaderboardProps) {
  const [level, setLevel] = useState<string>(ALL);
  const [sex, setSex] = useState<string>(ALL);
  const [offset, setOffset] = useState(0);
  const [limit, setLimit] = useState(DEFAULT_PAGE_SIZE);
  const board = useLeaderboard(wodId, {
    limit,
    offset,
    ...(level === ALL ? {} : { level: level as ResultLevel }),
    ...(sex === ALL ? {} : { sex: sex as ResultSex }),
  });
  const page = board.data;
  const kind = scoreType;

  const columns: Column<LeaderboardRowView>[] = [
    { key: "position", header: "#", render: (row) => <b>{row.position}</b> },
    { key: "name", header: "Atleta", render: (row) => `${row.first_name} ${row.last_initial}.` },
    { key: "score", header: WOD_SCORE_LABELS[scoreType], render: (row) => <b>{formatScore(kind, row)}</b> },
    { key: "level", header: "Nivel", render: (row) => LEVEL_LABELS[row.level] },
  ];

  return (
    <div className={styles.board}>
      <div className={styles.filters}>
        <Segmented
          label="Nivel"
          options={LEVEL_OPTIONS}
          value={level}
          onChange={(next) => {
            setLevel(next);
            setOffset(0);
          }}
        />
        <Segmented
          label="Sexo"
          options={SEX_OPTIONS}
          value={sex}
          onChange={(next) => {
            setSex(next);
            setOffset(0);
          }}
        />
      </div>
      <DataTable
        caption="Leaderboard"
        columns={columns}
        rows={page?.items}
        total={page?.total}
        limit={limit}
        rowKey={(row) => row.result_id}
        isLoading={board.isLoading || board.isPlaceholderData}
        error={resultsLoadError(board.error)}
        onRetry={() => {
          void board.refetch();
        }}
        emptyMessage={LEADERBOARD_EMPTY}
      />
      {page && page.total > 0 ? (
        <Pagination
          total={page.total}
          limit={limit}
          offset={offset}
          onPageChange={(next) => {
            setOffset((next - 1) * limit);
          }}
          onLimitChange={(next) => {
            setLimit(next);
            setOffset(0);
          }}
        />
      ) : null}
      <p className={styles.note}>{LEADERBOARD_NOTE}</p>
    </div>
  );
}
