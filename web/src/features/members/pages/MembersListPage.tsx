// S2-F6 · US-070 (front): /socios (Socios_Lista.html), admin y coach (`members.view`).
// - PageHeader "Socios" con el total y "Nuevo socio" solo con `members.create`.
// - Chips "Todos" y "Dados de baja" (status=deleted, también para el coach: N-20).
// - FilterBar: búsqueda por nombre, documento o teléfono con la espera de 300 ms de FilterBar y,
//   por S2-D41 (M-8), solo en memoria (useListParams con localQuery): el documento nunca queda en
//   la URL. En la URL quedan `status`, `sort`, `limit` y `offset`; un valor desconocido no viaja.
//   Cambiar la búsqueda vuelve a la primera página y cancela la petición anterior (signal).
// - DataTable: nombre (enlace a /socios/{id}, S2-D34), estado del socio con StatusTag y la
//   membresía (vacía hasta el Sprint 3). Nada cifrado ni enmascarado (N-01). Estados de carga,
//   vacío (con búsqueda o sin socios todavía), error con Reintentar, sin permiso y 429.
// - El aviso del alta llega en el estado de la navegación; se muestra una vez y se puede cerrar.
// DESIGN-GAP:
// - Sin columnas de teléfono, plan vigente, vence, última asistencia ni "Acción" (Ver, Renovar,
//   Vender): la lista no trae datos cifrados (N-01) y membresías y asistencia llegan con el
//   Sprint 3 y v0.4. Sin el documento enmascarado bajo el nombre (N-01).
// - Sin chips por estado de membresía (Al día, Por vencer, Vencidos, Congelados, Sin membresía)
//   ni conteos: llegan con US-071. Sin filtros de plan ni de última asistencia.
// - Sin "Exportar" (US-076, solo admin).
// - Sin la nota de la búsqueda por valor exacto: va como ayuda corta bajo la tabla.
import { X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { useCan } from "../../../core/auth/useCan";
import { EMPTY_VALUE, formatCount } from "../../../core/i18n/format";
import { parseSort, useListParams } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import { Chips } from "../../../shared/ui/Chips";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { FilterBar } from "../../../shared/ui/FilterBar";
import { PageHeader, type PageAction } from "../../../shared/ui/PageHeader";
import { Pagination } from "../../../shared/ui/Pagination";
import { STATUS_LABELS, type MembershipStatusView } from "../../../shared/ui/statusLabel";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { useMembers, type MembersParams } from "../api";
import { listError } from "../memberErrors";
import { memberHref, NEW_MEMBER_PATH, readCreatedNotice, type MemberCreatedNotice } from "../memberLinks";
import { DEFAULT_MEMBER_SORT, DELETED_STATUS, MEMBER_SORT_FIELDS, MEMBER_SORT_LABELS, MEMBER_SORTS, type MemberRowView } from "../schemas";
import styles from "./MembersListPage.module.css";

const FILTERS = ["status"] as const;
const ALL_CHIP = "all";

export const MEMBERS_EMPTY_SEARCH = "No hay socios que coincidan con la búsqueda";
export const MEMBERS_EMPTY = "Todavía no hay socios registrados.";
export const MEMBERS_PAST_END = "Esta página ya no tiene socios.";
export const CONSENT_MISSING_NOTICE = "Falta la autorización de tratamiento de datos. Pídesela al socio.";

const SORT_OPTIONS = MEMBER_SORTS.map((value) => ({ value, label: MEMBER_SORT_LABELS[value] }));
const CHIP_OPTIONS = [
  { value: ALL_CHIP, label: "Todos" },
  { value: DELETED_STATUS, label: "Dados de baja" },
];

function isMembershipStatus(value: string | null): value is MembershipStatusView {
  return value !== null && Object.prototype.hasOwnProperty.call(STATUS_LABELS, value);
}

const COLUMNS: Column<MemberRowView>[] = [
  { key: "name", header: "Socio", render: (row) => `${row.first_name} ${row.last_name}` },
  { key: "status", header: "Estado", render: (row) => <StatusTag account={row.deleted_at ? "deleted" : row.status} /> },
  {
    key: "membership",
    header: "Membresía",
    render: (row) => (isMembershipStatus(row.membership_status) ? <StatusTag status={row.membership_status} /> : EMPTY_VALUE),
  },
];

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

export default function MembersListPage() {
  const list = useListParams<(typeof FILTERS)[number]>({ filters: FILTERS, sorts: MEMBER_SORT_FIELDS, localQuery: true });
  const canCreate = useCan("members.create");
  const [notice, dismissNotice] = useCreatedNotice();
  const status = list.filters.status[0] === DELETED_STATUS ? DELETED_STATUS : undefined;
  const { limit, offset, sort } = list.params;
  const { q } = list;

  const params = useMemo<MembersParams>(
    () => ({ limit, offset, ...(q ? { q } : {}), ...(status ? { status } : {}), ...(sort ? { sort } : {}) }),
    [limit, offset, q, status, sort],
  );
  const members = useMembers(params);
  const page = members.data;
  const isFiltered = Boolean(q) || status !== undefined;
  // Un offset viejo (marcador, o el total bajó): hay socios, pero esta página quedó vacía.
  const isPastEnd = page !== undefined && page.total > 0 && page.items.length === 0;

  const actions: PageAction[] = canCreate ? [{ id: "new-member", label: "Nuevo socio", href: NEW_MEMBER_PATH, variant: "primary" }] : [];

  return (
    <div className={styles.page}>
      <PageHeader title="Socios" {...(page ? { total: `${formatCount(page.total)} en total` } : {})} actions={actions} />
      <CreatedNotice notice={notice} onDismiss={dismissNotice} />
      <Chips
        label="Estado"
        mode="single"
        options={CHIP_OPTIONS}
        value={[status ?? ALL_CHIP]}
        onChange={(value) => {
          list.setFilter("status", value.includes(DELETED_STATUS) ? DELETED_STATUS : undefined);
        }}
      />
      <FilterBar
        query={list.q}
        onQueryChange={list.setQuery}
        onClear={list.clear}
        searchPlaceholder="Nombre, documento o teléfono"
        sort={{
          value: sort ?? DEFAULT_MEMBER_SORT,
          options: SORT_OPTIONS,
          onChange: (value) => {
            list.setSort(parseSort(value));
          },
        }}
      />
      <DataTable
        caption="Socios"
        columns={COLUMNS}
        rows={page?.items}
        total={page?.total}
        limit={limit}
        rowKey={(row) => row.id}
        rowHref={(row) => memberHref(row.id)}
        // Mientras llega la página nueva no se muestran las filas de la anterior como si fueran ella.
        isLoading={members.isLoading || members.isPlaceholderData}
        error={listError(members.error)}
        onRetry={() => {
          void members.refetch();
        }}
        emptyMessage={isPastEnd ? MEMBERS_PAST_END : isFiltered ? MEMBERS_EMPTY_SEARCH : MEMBERS_EMPTY}
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
          ) : isFiltered ? (
            <Button variant="secondary" onClick={list.clear}>
              Limpiar filtros
            </Button>
          ) : canCreate ? (
            <Link className={styles.firstMember} to={NEW_MEMBER_PATH}>
              Registrar el primer socio
            </Link>
          ) : null
        }
      />
      {page && page.total > 0 ? <Pagination total={page.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
      <p className={styles.note}>El documento y el teléfono se buscan por el valor exacto; el nombre, por una parte.</p>
    </div>
  );
}
