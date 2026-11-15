// S7-F5 · US-162 (front): /clases/asistencia (pestaña «Asistencia por socio» de Sesiones.html), admin y coach (`classes.view`).
// - Filtros en la URL (attendanceFilters): rango de fechas (por omisión las últimas 4 semanas), «Marcas» y la búsqueda del socio
//   (solo en memoria). Rango invertido o de más de 26 semanas: no se pide nada y se explica.
// - «Resumen por semana» (GET /attendance/summary, WeeklySummary) con su propia carga y su propio error, y «Detalle por socio» (GET
//   /attendance) paginada en el servidor: socio con enlace a su ficha, clase, llegada, membresía al llegar y marcas con texto.
// - Estados: carga, vacío (con filtros guía a limpiarlos; sin ellos, a las clases de hoy), error con Reintentar, 403, 429 y sin
//   permiso (sin peticiones).
// DESIGN-GAP: Sesiones.html solo nombra la pestaña; la pantalla no tiene diseño propio (BRECHAS 15.8): se arma con FilterBar,
// DataTable y Pagination del panel. «racha» no existe en el api.
import { Link } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { formatDateTime, formatTime } from "../../../core/i18n/format";
import { Button } from "../../../shared/ui/Button";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { FilterBar } from "../../../shared/ui/FilterBar";
import { PageHeader } from "../../../shared/ui/PageHeader";
import { Pagination } from "../../../shared/ui/Pagination";
import { useAttendance, useAttendanceSummary, type AttendanceRowView } from "../attendanceApi";
import { useAttendanceFilters } from "../attendanceFilters";
import { ATTENDANCE_LIST_MESSAGES, attendanceListError, attendanceSummaryError, RANGE_INVERTED_MESSAGE, RANGE_TOO_LONG_MESSAGE } from "../classErrors";
import { attendanceMemberName, MarksCell, MembershipAtCheckin } from "../components/AttendanceCells";
import { ClassesTabs } from "../components/ClassesTabs";
import { WeeklySummary } from "../components/WeeklySummary";
import styles from "./AttendancePage.module.css";

export const ATTENDANCE_EMPTY_FILTERED = "No hay asistencias con estos filtros. Prueba con otro rango o limpia los filtros.";
export const ATTENDANCE_EMPTY = "Todavía no hay asistencias en estas fechas. Aparecen cuando alguien registra su llegada en el check-in.";
export const ATTENDANCE_PAST_END = "Esta página ya no tiene asistencias.";
const TODAY_CLASSES = "/clases?dia=hoy";

const MARK_OPTIONS = [
  { value: "true", label: "Solo con marca" },
  { value: "false", label: "Sin marca" },
];

const COLUMNS: Column<AttendanceRowView>[] = [
  { key: "member", header: "Socio", render: (row) => attendanceMemberName(row) },
  { key: "session", header: "Clase", render: (row) => <span className={styles.nowrap}>{formatDateTime(row.session_starts_at)}</span> },
  { key: "checked_in_at", header: "Llegó", render: (row) => <span className={styles.nowrap}>{formatTime(row.checked_in_at)}</span> },
  { key: "membership", header: "Membresía al llegar", render: (row) => <MembershipAtCheckin status={row.membership_status_at_checkin} /> },
  { key: "flags", header: "Marcas", render: (row) => <MarksCell flags={row.flags} /> },
];

export default function AttendancePage() {
  const canView = useCan("classes.view");
  const filters = useAttendanceFilters();
  const { list, listParams, summaryRange } = filters;
  const attendance = useAttendance(listParams ?? { limit: list.params.limit, offset: list.params.offset }, canView && listParams !== null);
  const summary = useAttendanceSummary(summaryRange ?? { from: "", to: "" }, canView && summaryRange !== null);
  const page = attendance.isPlaceholderData ? undefined : attendance.data;
  const isPastEnd = page !== undefined && page.total > 0 && page.items.length === 0;
  const listError = attendanceListError(attendance.error);
  const summaryError = attendanceSummaryError(summary.error);
  const rangeMessage = filters.rangeError === "inverted" ? RANGE_INVERTED_MESSAGE : filters.rangeError === "too_long" ? RANGE_TOO_LONG_MESSAGE : null;
  const emptyMessage = isPastEnd ? ATTENDANCE_PAST_END : filters.isFiltered ? ATTENDANCE_EMPTY_FILTERED : ATTENDANCE_EMPTY;

  return (
    <div className={styles.page}>
      <PageHeader title="Clases" />
      <ClassesTabs>
        {!canView ? (
          <p className={styles.error} role="alert">
            {ATTENDANCE_LIST_MESSAGES.forbidden}
          </p>
        ) : (
          <div className={styles.content}>
            <FilterBar
              query={list.q}
              onQueryChange={list.setQuery}
              onClear={list.clear}
              searchPlaceholder="Nombre, documento o teléfono"
              selects={[{ name: "flagged", label: "Marcas", value: filters.flagged, options: MARK_OPTIONS, anyLabel: "Todas" }]}
              onSelectChange={(name, value) => {
                if (name === "flagged") filters.setFlagged(value);
              }}
              dateRange={{ label: "Fechas de llegada", ...filters.range, onChange: filters.setRange }}
            />
            {rangeMessage ? (
              <p className={styles.rangeError} role="alert">
                {rangeMessage}
              </p>
            ) : null}
            <section className={styles.section} aria-labelledby="attendance-summary-title">
              <h2 id="attendance-summary-title" className={styles.heading}>
                Resumen por semana
              </h2>
              {summaryRange === null ? null : summaryError ? (
                <div className={styles.error} role="alert">
                  <p>{summaryError.message}</p>
                  <Button
                    variant="secondary"
                    onClick={() => {
                      void summary.refetch();
                    }}
                  >
                    Reintentar el resumen
                  </Button>
                </div>
              ) : summary.data ? (
                <WeeklySummary weeks={summary.data} />
              ) : (
                <p className={styles.note} role="status">
                  Cargando resumen…
                </p>
              )}
            </section>
            <section className={styles.section} aria-labelledby="attendance-list-title">
              <h2 id="attendance-list-title" className={styles.heading}>
                Detalle por socio
              </h2>
              {listParams === null ? null : (
                <>
                  <DataTable
                    caption="Asistencias"
                    columns={COLUMNS}
                    rows={page?.items}
                    total={page?.total}
                    limit={list.params.limit}
                    rowKey={(row) => row.id}
                    rowHref={(row) => `/socios/${row.member_id}`}
                    isLoading={attendance.isLoading || attendance.isPlaceholderData}
                    error={listError}
                    onRetry={() => {
                      void attendance.refetch();
                    }}
                    emptyMessage={emptyMessage}
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
                      ) : filters.isFiltered ? (
                        <Button variant="secondary" onClick={list.clear}>
                          Limpiar filtros
                        </Button>
                      ) : (
                        <Link className={styles.link} to={TODAY_CLASSES}>
                          Ver las clases de hoy
                        </Link>
                      )
                    }
                  />
                  {page && page.total > 0 ? (
                    <Pagination total={page.total} limit={list.params.limit} offset={list.params.offset} onPageChange={list.setPage} onLimitChange={list.setLimit} />
                  ) : null}
                </>
              )}
            </section>
          </div>
        )}
      </ClassesTabs>
    </div>
  );
}
