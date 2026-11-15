// S2-F6 · US-070 (front): /socios (Socios_Lista.html), admin y coach (`members.view`).
// - PageHeader "Socios" con el total de socios vivos y "Nuevo socio" solo con `members.create`.
// - FilterBar: búsqueda por nombre, documento o teléfono con la espera de 300 ms de FilterBar y,
//   por S2-D41 (M-8), solo en memoria (useListParams con localQuery): el documento nunca queda en
//   la URL. Cambiar la búsqueda vuelve a la primera página y cancela la petición anterior (signal).
// - DataTable: nombre (enlace a /socios/{id}, S2-D34), plan vigente, "Vence", la membresía y el
//   estado del socio con StatusTag. Nada cifrado ni enmascarado (N-01). Estados de carga, vacío
//   (con filtros o sin socios todavía), error con Reintentar, sin permiso y 429.
// - El aviso del alta llega en el estado de la navegación; se muestra una vez y se puede cerrar.
// S3-F2 · US-071 y US-072 (D22, D37, D39):
// - Chips de estado (MemberStatusChips) con conteos del resumen y el filtro "Plan" (PlanFilter).
//   En la URL quedan `status` (solo `deleted`), `membership_status`, `plan_id`, `sort`, `limit` y
//   `offset`, con los nombres del api; un valor desconocido no viaja. Cambiar el chip o el plan
//   vuelve a la primera página (useListParams.setFilters, una sola navegación).
// - Bajo MOBILE_QUERY la lista es MemberCardList ("Cargar más", botón flotante "Nuevo socio");
//   en escritorio, DataTable con Pagination. Solo se monta una de las dos (una sola petición).
// DESIGN-GAP:
// - Sin columnas de teléfono ni "Acción" (Ver, Renovar, Vender): la lista no
//   trae datos cifrados (N-01); sin el documento enmascarado bajo el
//   nombre (N-01). "Vence" muestra la fecha de fin con año; no "Vencido · 5 días", "reanuda 1 nov"
//   (la fila no trae los días de atraso).
// S6-F5 (US-151): `?consent=missing` (enlace de la tarjeta "Sin autorización" de Inicio) filtra la lista y la
//   exportación; se muestra como el chip "Sin autorización" y quitarlo limpia la URL.
// DESIGN-GAP: Socios_Lista.html no dibuja el chip "Sin autorización"; va como un grupo de Chips propio
//   ("Autorización") entre los chips de estado y la FilterBar, solo mientras el filtro está activo.
// S7-F5 (US-163, S7-D15): filtro "Última asistencia" (`last_attendance`, en la URL) y la columna del mismo nombre ("hoy 07:02",
//   "ayer 18:05", fecha con año o "Nunca"); "Plan vigente" dice "12 clases · quedan 2" en una tiquetera. La exportación lo envía (S7-F5b).
//   DESIGN-GAP: el diseño ofrece "Esta semana" y "Hace más de 10
//   días"; el api filtra por 7, 14, 30 y 60 días o nunca. Sin la columna "Acción" ni el teléfono (N-01).
// - S5-F4: "Exportar" (solo admin) con los filtros vigentes. El encabezado no
//   dice "· 269 con membresía": el número está en los chips.
// - Sin la nota de la búsqueda por valor exacto: va como ayuda corta bajo la lista.
// - "Ordenar por" no ofrece "Vencimiento más próximo" (GET /members no ordena por fin de membresía).
import { X } from "lucide-react";
import { useEffect, useMemo, useState, type JSX } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { EMPTY_VALUE, formatCount, formatDate } from "../../../core/i18n/format";
import { parseSort, useListParams } from "../../../shared/hooks/useListParams";
import { MOBILE_QUERY, useMediaQuery } from "../../../shared/hooks/useMediaQuery";
import { Button } from "../../../shared/ui/Button";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { Chips } from "../../../shared/ui/Chips";
import { FilterBar } from "../../../shared/ui/FilterBar";
import { PageHeader, type PageAction } from "../../../shared/ui/PageHeader";
import { Pagination } from "../../../shared/ui/Pagination";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { useMembers, useMembersTotal, type MembersInfiniteParams } from "../api";
import { ExportButton } from "../components/ExportButton";
import { MemberCardList } from "../components/MemberCardList";
import { MemberPhoto } from "../components/MemberPhoto";
import { LAST_ATTENDANCE_FILTER_NAME, lastAttendanceFilter, readLastAttendance } from "../components/LastAttendanceFilter";
import { MemberStatusChips } from "../components/MemberStatusChips";
import { PLAN_FILTER_NAME, readPlanId, usePlanFilter } from "../components/PlanFilter";
import { accountStatusOf, lastAttendanceText, membershipStatusOf, planWithClasses } from "../lib/memberRow";
import { listError } from "../memberErrors";
import { memberHref, NEW_MEMBER_PATH, readCreatedNotice, type MemberCreatedNotice } from "../memberLinks";
import { chipFromFilters, chipToFilter, DEFAULT_MEMBER_SORT, DELETED_STATUS, MEMBER_SORT_FIELDS, MEMBER_SORT_LABELS, MEMBER_SORTS, type MemberChip, type MemberRowView } from "../schemas";
import styles from "./MembersListPage.module.css";

const FILTERS = ["status", "membership_status", "plan_id", "consent", "last_attendance"] as const;
const CONSENT_MISSING = "missing";
const CONSENT_CHIP_OPTIONS = [{ value: CONSENT_MISSING, label: "Sin autorización" }];
type MemberFilter = (typeof FILTERS)[number];

export const MEMBERS_EMPTY_SEARCH = "No hay socios que coincidan con la búsqueda";
export const MEMBERS_EMPTY = "Todavía no hay socios registrados.";
export const MEMBERS_PAST_END = "Esta página ya no tiene socios.";
export const CONSENT_MISSING_NOTICE = "Falta la autorización de tratamiento de datos. Pídesela al socio.";

const SORT_OPTIONS = MEMBER_SORTS.map((value) => ({ value, label: MEMBER_SORT_LABELS[value] }));

/** `nowMs` se lee una vez por tabla (L3), no por celda: toda la columna «Última asistencia» usa el mismo instante. */
function buildColumns(nowMs: number): Column<MemberRowView>[] {
  return [
  {
    key: "name",
    header: "Socio",
    render: (row) => (
      <span className={styles.person}>
        <MemberPhoto photoAttachmentId={row.photo_attachment_id} size="sm" />
        {`${row.first_name} ${row.last_name}`}
      </span>
    ),
  },
  { key: "plan", header: "Plan vigente", render: (row) => planWithClasses(row) ?? EMPTY_VALUE },
  { key: "end", header: "Vence", render: (row) => (row.membership_end_date ? <span className={styles.nowrap}>{formatDate(row.membership_end_date)}</span> : EMPTY_VALUE) },
  {
    key: "membership",
    header: "Membresía",
    render: (row) => {
      const status = membershipStatusOf(row);
      return status ? <StatusTag status={status} /> : EMPTY_VALUE;
    },
  },
  { key: "status", header: "Estado", render: (row) => <StatusTag account={accountStatusOf(row)} /> },
  { key: "last_attendance", header: "Última asistencia", render: (row) => <span className={styles.nowrap}>{lastAttendanceText(row.last_attendance_at, nowMs)}</span> },
  ];
}

/** El aviso del alta; la región existe siempre para que se anuncie. */
function CreatedNotice({ notice, onDismiss }: { notice: MemberCreatedNotice | null; onDismiss: () => void }) {
  return (
    <div role="status">
      {notice ? (
        <div className={styles.notice}>
          <div className={styles.noticeText}>
            <p>{`Socio registrado: ${notice.name}.`}</p>
            {notice.consentMissing ? <p className={styles.warning}>{CONSENT_MISSING_NOTICE}</p> : null}
          </div>
          <button type="button" className={styles.dismiss} aria-label="Cerrar aviso" onClick={onDismiss}>
            <X size={20} aria-hidden="true" />
          </button>
        </div>
      ) : null}
    </div>
  );
}

/** Lee el aviso del alta y lo quita del historial: al recargar o volver atrás no reaparece. */
function useCreatedNotice(): [MemberCreatedNotice | null, () => void] {
  const location = useLocation();
  const navigate = useNavigate();
  const incoming = readCreatedNotice(location.state);
  const [notice, setNotice] = useState<MemberCreatedNotice | null>(incoming);
  const [seenKey, setSeenKey] = useState(location.key);
  if (incoming && seenKey !== location.key) {
    setSeenKey(location.key);
    setNotice(incoming);
  }
  const hasIncoming = incoming !== null;
  useEffect(() => {
    if (hasIncoming) void navigate({ pathname: location.pathname, search: location.search }, { replace: true, state: null });
  }, [hasIncoming, navigate, location.pathname, location.search]);
  return [
    notice,
    () => {
      setNotice(null);
    },
  ];
}

interface EmptyProps {
  isFiltered: boolean;
  canCreate: boolean;
  onClear: () => void;
}

/** El texto del vacío: con filtros guía a limpiarlos; sin socios, a registrar el primero. */
function emptyMessage(isFiltered: boolean): string {
  return isFiltered ? MEMBERS_EMPTY_SEARCH : MEMBERS_EMPTY;
}

function EmptyAction({ isFiltered, canCreate, onClear }: EmptyProps): JSX.Element | null {
  if (isFiltered) {
    return (
      <Button variant="secondary" onClick={onClear}>
        Limpiar filtros
      </Button>
    );
  }
  return canCreate ? (
    <Link className={styles.firstMember} to={NEW_MEMBER_PATH}>
      Registrar el primer socio
    </Link>
  ) : null;
}

interface MembersTableProps extends EmptyProps {
  params: MembersInfiniteParams;
  offset: number;
  onPageChange: (page: number) => void;
  onLimitChange: (limit: number) => void;
}

/** Escritorio: tabla paginada en el servidor (offset en la URL). */
function MembersTable({ params, offset, onPageChange, onLimitChange, ...empty }: MembersTableProps) {
  const query = useMemo(() => ({ ...params, offset }), [params, offset]);
  const [nowMs] = useState(() => Date.now());
  const columns = useMemo(() => buildColumns(nowMs), [nowMs]);
  const members = useMembers(query);
  const page = members.data;
  // Un offset viejo (marcador, o el total bajó): hay socios, pero esta página quedó vacía.
  const isPastEnd = page !== undefined && page.total > 0 && page.items.length === 0;

  return (
    <>
      <DataTable
        caption="Socios"
        columns={columns}
        rows={page?.items}
        total={page?.total}
        limit={params.limit}
        rowKey={(row) => row.id}
        rowHref={(row) => memberHref(row.id)}
        // Mientras llega la página nueva no se muestran las filas de la anterior como si fueran ella.
        isLoading={members.isLoading || members.isPlaceholderData}
        error={listError(members.error)}
        onRetry={() => {
          void members.refetch();
        }}
        emptyMessage={isPastEnd ? MEMBERS_PAST_END : emptyMessage(empty.isFiltered)}
        emptyAction={
          isPastEnd ? (
            <Button
              variant="secondary"
              onClick={() => {
                onPageChange(1);
              }}
            >
              Ir a la primera página
            </Button>
          ) : (
            <EmptyAction {...empty} />
          )
        }
      />
      {page && page.total > 0 ? <Pagination total={page.total} limit={params.limit} offset={offset} onPageChange={onPageChange} onLimitChange={onLimitChange} /> : null}
    </>
  );
}

export default function MembersListPage() {
  const list = useListParams<MemberFilter>({ filters: FILTERS, sorts: MEMBER_SORT_FIELDS, localQuery: true });
  const isMobile = useMediaQuery(MOBILE_QUERY);
  const canCreate = useCan("members.create");
  const canSeeDeleted = useCan("members.view");
  const [notice, dismissNotice] = useCreatedNotice();
  const total = useMembersTotal().data;

  const urlChip = chipFromFilters(list.filters.status, list.filters.membership_status);
  // N-20: los dados de baja son de admin y coach; sin el permiso ni el chip ni el filtro existen.
  const chip: MemberChip | null = urlChip === DELETED_STATUS && !canSeeDeleted ? null : urlChip;
  const planId = readPlanId(list.filters.plan_id);
  const planFilter = usePlanFilter(planId);
  const { limit, offset, sort } = list.params;
  const { q } = list;
  const { status, membership_status } = chipToFilter(chip);
  const lastAttendance = readLastAttendance(list.filters.last_attendance);
  // S6-F5 (US-151): `?consent=missing` es el único valor; cualquier otro se ignora y no viaja.
  const consent = list.filters.consent.includes(CONSENT_MISSING) ? CONSENT_MISSING : undefined;

  const params = useMemo<MembersInfiniteParams>(
    () => ({
      limit,
      ...(q ? { q } : {}),
      ...(status ? { status } : {}),
      ...(membership_status ? { membership_status } : {}),
      ...(planId ? { plan_id: planId } : {}),
      ...(consent ? { consent } : {}),
      ...(lastAttendance ? { last_attendance: lastAttendance } : {}),
      ...(sort ? { sort } : {}),
    }),
    [limit, q, status, membership_status, planId, consent, lastAttendance, sort],
  );
  // Los filtros de la exportación son los de la lista sin paginar ni ordenar.
  const exportFilters = useMemo(() => {
    const filters: Partial<MembersInfiniteParams> = { ...params };
    delete filters.limit;
    delete filters.sort;
    return filters;
  }, [params]);
  const empty: EmptyProps = { isFiltered: Boolean(q) || chip !== null || planId !== "" || consent !== undefined || lastAttendance !== "", canCreate, onClear: list.clear };

  // En el celular "Nuevo socio" es el botón flotante de MemberCardList.
  const actions: PageAction[] = canCreate && !isMobile ? [{ id: "new-member", label: "Nuevo socio", href: NEW_MEMBER_PATH, variant: "primary" }] : [];

  return (
    <div className={styles.page}>
      <PageHeader title="Socios" {...(total === undefined ? {} : { total: `${formatCount(total)} en total` })} actions={actions} />
      <CreatedNotice notice={notice} onDismiss={dismissNotice} />
      <div className={styles.tools}>
        <ExportButton filters={exportFilters} />
      </div>
      <MemberStatusChips
        value={chip}
        onChange={(next) => {
          const filter = chipToFilter(next);
          list.setFilters({ status: filter.status, membership_status: filter.membership_status });
        }}
      />
      {consent ? (
        <Chips
          label="Autorización"
          mode="single"
          options={CONSENT_CHIP_OPTIONS}
          value={[consent]}
          onChange={() => {
            list.setFilter("consent", undefined);
          }}
        />
      ) : null}
      <FilterBar
        query={list.q}
        onQueryChange={list.setQuery}
        onClear={list.clear}
        searchPlaceholder="Nombre, documento o teléfono"
        selects={[planFilter, lastAttendanceFilter(lastAttendance)]}
        onSelectChange={(name, value) => {
          if (name === PLAN_FILTER_NAME) list.setFilter("plan_id", value || undefined);
          if (name === LAST_ATTENDANCE_FILTER_NAME) list.setFilter("last_attendance", value || undefined);
        }}
        sort={{
          value: sort ?? DEFAULT_MEMBER_SORT,
          options: SORT_OPTIONS,
          onChange: (value) => {
            list.setSort(parseSort(value));
          },
        }}
      />
      {isMobile ? (
        <MemberCardList params={params} emptyMessage={emptyMessage(empty.isFiltered)} emptyAction={<EmptyAction {...empty} />} />
      ) : (
        <MembersTable params={params} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} {...empty} />
      )}
      <p className={styles.note}>El documento y el teléfono se buscan por el valor exacto; el nombre, por una parte.</p>
    </div>
  );
}
