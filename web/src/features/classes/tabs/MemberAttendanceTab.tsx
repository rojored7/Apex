// S7-F5 · US-162 (front): pestaña Asistencia de la ficha (/socios/:id/asistencia), admin y coach (`classes.view`). Ruta hija de
// /socios/:id (S3-D65, E3): la ficha la pinta en su <Outlet /> y le pasa el socio por el contexto (useMemberTab, shared/data); esta
// feature no importa features/members y la ficha la carga de forma diferida (lazy en la tabla de rutas).
// - Resumen: última asistencia, clases de los últimos 30 días y total (tres lecturas de GET /attendance con `limit=1`: el `total`
//   es el conteo). Si una falla dice «No disponible» y la lista sigue.
// - Lista GET /members/{id}/attendance paginada en el servidor (25, 50 o 100; `offset` en la URL): clase, llegada, membresía al
//   llegar y marcas con texto. Sin búsqueda: `q` no aporta dentro de un solo socio.
// - Estados: carga, vacío (guía a las clases de hoy), error con Reintentar (404, 403, 429, 5xx) y página fuera de rango.
// DESIGN-GAP: la «racha» de Socio_Ficha.html no existe en el api (S7-D15, BRECHAS 15.8): no se dibuja.
import { useState } from "react";
import { Link, useParams } from "react-router";
import type { UseQueryResult } from "@tanstack/react-query";
import { addDaysCivil, formatCount, formatDateTime, formatRelativeTime, formatTime, todayBogota } from "../../../core/i18n/format";
import { useMemberTab } from "../../../shared/data/members";
import { useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { Pagination } from "../../../shared/ui/Pagination";
import { useMemberAttendance, useMemberAttendanceStats, type AttendanceRowView } from "../attendanceApi";
import { bogotaDayStartUtc } from "../attendanceFilters";
import { memberAttendanceError } from "../classErrors";
import { MarksCell, MembershipAtCheckin } from "../components/AttendanceCells";
import styles from "./MemberAttendanceTab.module.css";

export const MEMBER_ATTENDANCE_EMPTY = "Este socio todavía no tiene asistencias. Aparecen cuando alguien registra su llegada en el check-in de una clase.";
const PAST_END = "Esta página ya no tiene asistencias.";
const RECENT_DAYS = 30;
const UNAVAILABLE = "No disponible";
const NONE_YET = "Sin asistencias";

const COLUMNS: Column<AttendanceRowView>[] = [
  { key: "session", header: "Clase", render: (row) => <span className={styles.nowrap}>{formatDateTime(row.session_starts_at)}</span> },
  { key: "checked_in_at", header: "Llegó", render: (row) => <span className={styles.nowrap}>{formatTime(row.checked_in_at)}</span> },
  { key: "membership", header: "Membresía al llegar", render: (row) => <MembershipAtCheckin status={row.membership_status_at_checkin} /> },
  { key: "flags", header: "Marcas", render: (row) => <MarksCell flags={row.flags} /> },
];

const classes = (count: number): string => `${formatCount(count)} ${count === 1 ? "clase" : "clases"}`;

function valueOf<T>(query: UseQueryResult<T>, text: (data: T) => string): string {
  if (query.isError) return UNAVAILABLE;
  return query.data === undefined ? "Cargando…" : text(query.data);
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.stat}>
      <span className={styles.statLabel}>{label}</span>
      <b className={styles.statValue}>{value}</b>
    </div>
  );
}

export default function MemberAttendanceTab() {
  const member = useMemberTab();
  const { id: routeId = "" } = useParams();
  const memberId = member?.id ?? routeId;
  const [nowMs] = useState(() => Date.now());
  const list = useListParams({ filters: [] });
  const { limit, offset } = list.params;
  const fromUtc = bogotaDayStartUtc(addDaysCivil(todayBogota(), 1 - RECENT_DAYS) ?? todayBogota()) ?? "";
  const attendance = useMemberAttendance(memberId, { limit, offset });
  const stats = useMemberAttendanceStats(memberId, fromUtc);
  const page = attendance.isPlaceholderData ? undefined : attendance.data;
  const isPastEnd = page !== undefined && page.total > 0 && page.items.length === 0;
  const error = memberAttendanceError(attendance.error);

  return (
    <div className={styles.tab}>
      <h2 className={styles.title}>Asistencia</h2>
      <div className={styles.stats}>
        <Stat label="Última asistencia" value={valueOf(stats.last, (data) => (data.lastAt === null ? NONE_YET : formatRelativeTime(data.lastAt, nowMs)))} />
        <Stat label={`Últimos ${String(RECENT_DAYS)} días`} value={valueOf(stats.recent, classes)} />
        <Stat label="En total" value={valueOf(stats.last, (data) => classes(data.total))} />
      </div>
      <DataTable
        caption="Asistencia del socio"
        columns={COLUMNS}
        rows={page?.items}
        total={page?.total}
        limit={limit}
        rowKey={(row) => row.id}
        isLoading={attendance.isLoading || attendance.isPlaceholderData}
        error={error}
        onRetry={() => {
          void attendance.refetch();
        }}
        emptyMessage={isPastEnd ? PAST_END : MEMBER_ATTENDANCE_EMPTY}
        emptyAction={
          isPastEnd ? (
            <Button
              variant="secondary"
              onClick={() => {
                list.setPage(1);
              }}
            >
              Ir a la primera página
            </Button>
          ) : (
            <Link className={styles.link} to="/clases?dia=hoy">
              Ver las clases de hoy
            </Link>
          )
        }
      />
      {page && page.total > 0 ? <Pagination total={page.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
    </div>
  );
}
