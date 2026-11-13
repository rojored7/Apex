// S6-F2 · US-145 (Llaves.html, pestaña «Tareas de recifrado»; S6-D16, S6-B2): trabajos de rotación y recifrado.
// - Tabla paginada (offset) con tipo, clase de dato, estado (StatusTag de texto), barra de progreso con el
//   porcentaje también en texto («61 %», «212 de 342») y fechas de Bogotá. El api no manda el texto `error` del
//   trabajo y el esquema `.strict()` lo rechazaría: un fallo se dice con «Falló».
// - Se relee cada JOBS_POLL_MS solo mientras haya un trabajo pendiente o en curso (useCryptoJobs); al terminar el
//   último se invalida el inventario y el resumen (las llaves cambian de estado).
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { useSearchParams } from "react-router";
import { formatCount, formatDateTime } from "../../../core/i18n/format";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { Pagination } from "../../../shared/ui/Pagination";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { KEYS_QUERY_KEY, hasActiveJob, useCryptoJobs } from "../api";
import { toJobsApiParams } from "../cryptoFilters";
import { JOB_KIND_LABELS, jobTitle } from "../cryptoLabels";
import { jobsListError } from "../keysErrors";
import type { CryptoJobView } from "../schemas";
import styles from "./CryptoJobs.module.css";

export const JOBS_EMPTY = "Todavía no hay trabajos de rotación ni de recifrado";
const EMPTY = "—";

const COLUMNS: Column<CryptoJobView>[] = [
  { key: "kind", header: "Tipo", render: (job) => JOB_KIND_LABELS[job.kind] },
  { key: "data_class", header: "Clase de dato", render: (job) => job.data_class ?? EMPTY },
  { key: "status", header: "Estado", render: (job) => <StatusTag crypto={job.status} /> },
  {
    key: "progress",
    header: "Avance",
    render: (job) => (
      <span className={styles.progress}>
        <progress className={styles.bar} value={job.percent} max={100} aria-label={`Avance de ${jobTitle(job)}`} />
        <span className={styles.percent}>{`${String(job.percent)} %`}</span>
        <span className={styles.count}>{`${formatCount(job.done)} de ${formatCount(job.total)}`}</span>
      </span>
    ),
  },
  { key: "started_at", header: "Inicio", render: (job) => (job.started_at ? <span className={styles.nowrap}>{formatDateTime(job.started_at)}</span> : EMPTY) },
  { key: "finished_at", header: "Fin", render: (job) => (job.finished_at ? <span className={styles.nowrap}>{formatDateTime(job.finished_at)}</span> : EMPTY) },
];

export function CryptoJobs() {
  const list = useListParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const search = searchParams.toString();
  const params = toJobsApiParams(search);
  const jobs = useCryptoJobs(params);
  const limit = Number(params.get("limit"));
  const offset = Number(params.get("offset"));
  const page = jobs.data;
  const active = hasActiveJob(page);
  const wasActive = useRef(false);

  // Al pasar de «hay uno en curso» a «ninguno»: las llaves cambiaron de estado y el resumen de conteos.
  useEffect(() => {
    if (wasActive.current && !active) void queryClient.invalidateQueries({ queryKey: KEYS_QUERY_KEY });
    wasActive.current = active;
  }, [active, queryClient]);

  const goToInventory = (): void => {
    setSearchParams((previous) => {
      const next = new URLSearchParams(previous);
      next.delete("tab");
      next.delete("offset");
      return next;
    });
  };

  return (
    <div className={styles.root}>
      <DataTable
        caption="Trabajos de rotación y recifrado"
        columns={COLUMNS}
        rows={page?.items}
        total={page?.total}
        limit={limit}
        rowKey={(job) => job.id}
        isLoading={jobs.isLoading || jobs.isPlaceholderData}
        error={jobsListError(jobs.error)}
        onRetry={() => {
          void jobs.refetch();
        }}
        emptyMessage={JOBS_EMPTY}
        emptyAction={
          <Button variant="secondary" onClick={goToInventory}>
            Ir al inventario
          </Button>
        }
      />
      {page && page.total > 0 ? <Pagination total={page.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
      <p className={styles.help}>
        {active ? "Hay un trabajo en curso: la tabla se actualiza sola cada 5 segundos. Mientras tanto la lectura y la escritura de datos siguen funcionando." : "Un trabajo nuevo aparece aquí al rotar una llave desde el inventario."}
      </p>
    </div>
  );
}
