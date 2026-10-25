// S3-F7 · US-093 (front): pestaña Membresías de la ficha (/socios/:id/membresias), admin y coach
// (`memberships.view`). Ruta hija de /socios/:id (S3-D65, E3): la ficha la pinta en su <Outlet /> y le
// pasa el socio por el contexto (useMemberTab, shared/data); esta feature no importa features/members.
// - GET /members/{id}/memberships (B11, useMemberMemberships): la primera página da las tarjetas de la
//   vigente y de la futura (MemberMembershipCard) y los botones de membershipActions; el historial es
//   la misma lista paginada en el servidor (25, 50 o 100; `offset` en la URL), con todas las
//   membresías, también las anuladas con su motivo.
// - Renovar (/membresias/vender?socio=&renovar=1) y Vender membresía (?socio=) llevan el nombre del
//   socio en el estado de la navegación; Registrar saldo abre el panel de pagos (?pago=<membresía>);
//   Congelar y Anular abren FreezeModal y CancelMembershipModal. Un socio dado de baja (o la pestaña
//   sin la ficha) es de solo lectura: ningún botón (N-20).
// - Estados: carga, vacío ("Este socio no tiene membresías." con Vender), sin vigente, error con
//   Reintentar (404, 403 y el resto en palabras de la pantalla) y aviso tras congelar o anular.
// DESIGN-GAP:
// - Socio_Ficha.html no dibuja el contenido de la pestaña (enlaza a Membresias.html): tarjetas como
//   la caja "Membresía" de la ficha e historial con las columnas de Membresias.html, sin "Socio" ni
//   acciones por fila (las acciones van en las tarjetas de la vigente y la futura).
import type { UseQueryResult } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router";
import type { Page } from "../../../core/api/page";
import { DEFAULT_LIMIT } from "../../../core/api/query";
import { useRole } from "../../../core/auth/useCan";
import { formatCop, formatDate, todayBogota } from "../../../core/i18n/format";
import { memberFullName, useMemberTab } from "../../../shared/data/members";
import { useMemberMemberships, type MembershipOutView } from "../../../shared/data/memberships";
import { useListParams, type ListParamsApi } from "../../../shared/hooks/useListParams";
import { Button } from "../../../shared/ui/Button";
import buttonStyles from "../../../shared/ui/Button.module.css";
import { cx } from "../../../shared/ui/cx";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { Pagination } from "../../../shared/ui/Pagination";
import { StatusTag } from "../../../shared/ui/StatusTag";
import { classesRemainingText, membershipActions, paidText, splitMemberships, type MembershipActions } from "../lib/rules";
import { memberTabError } from "../membershipErrors";
import { renewHref, sellForMemberHref, type SellLocationState } from "../membershipLinks";
import { CancelMembershipModal } from "./CancelMembershipModal";
import { FreezeModal } from "./FreezeModal";
import { MemberMembershipCard } from "./MemberMembershipCard";
import styles from "./MemberMembershipsTab.module.css";

export const MEMBER_MEMBERSHIPS_EMPTY = "Este socio no tiene membresías.";
export const MEMBER_NO_CURRENT = "Este socio no tiene una membresía vigente.";
export const MEMBER_MEMBERSHIPS_LOADING = "Cargando las membresías…";
const HISTORY_PAST_END = "Esta página ya no tiene membresías.";

/** Las tarjetas salen siempre de la primera página (la vigente y la futura son las más recientes). */
const CARDS_PAGE = { limit: DEFAULT_LIMIT, offset: 0 } as const;

type Notice = { kind: "frozen"; plan: string; endDate: string } | { kind: "cancelled"; plan: string };

function noticeText(notice: Notice): string {
  return notice.kind === "frozen" ? `Membresía ${notice.plan} congelada. Ahora termina el ${formatDate(notice.endDate)}.` : `Membresía ${notice.plan} anulada. Sus pagos siguen registrados.`;
}

/** El aviso de la pestaña; la región existe siempre para que se anuncie. Recibe el foco (S3-F5 L7). */
function TabNotice({ notice }: { notice: Notice | null }) {
  const ref = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    if (notice) ref.current?.focus();
  }, [notice]);
  return (
    <div role="status">
      {notice ? (
        <p ref={ref} tabIndex={-1} className={styles.notice}>
          {noticeText(notice)}
        </p>
      ) : null}
    </div>
  );
}

const HISTORY_COLUMNS: Column<MembershipOutView>[] = [
  { key: "plan", header: "Plan", render: (m) => <span className={styles.nowrap}>{`${m.plan_name} · ${formatCop(m.agreed_price_cop)}`}</span> },
  { key: "start_date", header: "Inicio", render: (m) => <span className={styles.nowrap}>{formatDate(m.start_date)}</span> },
  { key: "end_date", header: "Fin", render: (m) => <span className={styles.nowrap}>{formatDate(m.end_date)}</span> },
  { key: "classes_remaining", header: "Clases restantes", render: (m) => classesRemainingText(m.classes_remaining, m.classes_total) },
  { key: "paid_cop", header: "Pagado", render: (m) => paidText(m.paid_cop, m.agreed_price_cop) },
  {
    key: "status",
    header: "Estado",
    render: (m) => (
      <span className={styles.status}>
        <StatusTag status={m.status} />
        {m.cancel_reason ? <span className={styles.reason}>{`Motivo: ${m.cancel_reason}`}</span> : null}
      </span>
    ),
  },
];

function Toolbar({ memberId, memberName, actions }: { memberId: string; memberName: string | null; actions: MembershipActions }) {
  if (!actions.renew && !actions.sell) return null;
  const state = memberName ? ({ memberName } satisfies SellLocationState) : undefined;
  return (
    <div className={styles.toolbar}>
      {actions.renew ? (
        <Link className={cx(buttonStyles.button, buttonStyles.primary, buttonStyles.md)} to={renewHref(memberId)} state={state}>
          Renovar
        </Link>
      ) : null}
      {actions.sell ? (
        <Link className={cx(buttonStyles.button, actions.renew ? buttonStyles.secondary : buttonStyles.primary, buttonStyles.md)} to={sellForMemberHref(memberId)} state={state}>
          Vender membresía
        </Link>
      ) : null}
    </div>
  );
}

interface HistoryProps {
  list: ListParamsApi<never>;
  history: UseQueryResult<Page<MembershipOutView>>;
}

/** El historial; su consulta se abre con la de las tarjetas (en la página 1 es la misma). */
function History({ list, history }: HistoryProps) {
  const { limit, offset } = list.params;
  const data = history.data;
  const isPastEnd = data !== undefined && data.total > 0 && data.items.length === 0;
  return (
    <div className={styles.section}>
      <h2 className={styles.sectionTitle}>Historial</h2>
      <DataTable
        caption="Historial de membresías"
        columns={HISTORY_COLUMNS}
        rows={data?.items}
        total={data?.total}
        limit={limit}
        rowKey={(m) => m.id}
        isLoading={history.isLoading || history.isPlaceholderData}
        error={memberTabError(history.error)}
        onRetry={() => {
          void history.refetch();
        }}
        emptyMessage={isPastEnd ? HISTORY_PAST_END : MEMBER_MEMBERSHIPS_EMPTY}
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
          ) : null
        }
      />
      {data && data.total > 0 ? <Pagination total={data.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
    </div>
  );
}

export default function MemberMembershipsTab() {
  const { id = "" } = useParams();
  const member = useMemberTab();
  const role = useRole();
  const today = todayBogota();
  const memberId = id === "" ? null : id;
  const first = useMemberMemberships(memberId, CARDS_PAGE);
  const list = useListParams();
  const history = useMemberMemberships(memberId, { limit: list.params.limit, offset: list.params.offset });
  // La membresía de la tarjeta (es FreezeTarget y CancelTarget): el aviso nombra su plan.
  const [freezing, setFreezing] = useState<MembershipOutView | null>(null);
  const [cancelling, setCancelling] = useState<MembershipOutView | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  if (first.data === undefined) {
    if (first.isError) {
      return (
        <div className={styles.tab}>
          <p className={styles.alert} role="alert">
            {memberTabError(first.error)?.message}
          </p>
          <div>
            <Button
              variant="secondary"
              loading={first.isFetching}
              onClick={() => {
                void first.refetch();
              }}
            >
              Reintentar
            </Button>
          </div>
        </div>
      );
    }
    return (
      <p className={styles.loading} role="status">
        {MEMBER_MEMBERSHIPS_LOADING}
      </p>
    );
  }

  const items = first.data.items;
  // Sin la ficha no se sabe si el socio está dado de baja: la pestaña es de solo lectura.
  const readOnly = member === null || member.deleted_at !== null;
  const actions = membershipActions(items, role, today, readOnly);
  const { current, future } = splitMemberships(items, today);
  const memberName = member ? memberFullName(member) : null;
  const cardActions = (m: MembershipOutView) => ({ pay: actions.payIds.includes(m.id), freeze: actions.freezeIds.includes(m.id), cancel: actions.cancelIds.includes(m.id) });
  const onFreeze = (m: MembershipOutView): void => {
    setNotice(null);
    setFreezing(m);
  };
  const onCancel = (m: MembershipOutView): void => {
    setNotice(null);
    setCancelling(m);
  };

  if (first.data.total === 0) {
    return (
      <div className={styles.empty}>
        <p className={styles.none}>{MEMBER_MEMBERSHIPS_EMPTY}</p>
        {actions.sell ? (
          <Link className={cx(buttonStyles.button, buttonStyles.primary, buttonStyles.md)} to={sellForMemberHref(id)} state={memberName ? ({ memberName } satisfies SellLocationState) : undefined}>
            Vender
          </Link>
        ) : null}
      </div>
    );
  }

  return (
    <div className={styles.tab}>
      <TabNotice notice={notice} />
      {/* Revisión S3-F7 (M2): en la página 1 las dos consultas son la misma; el historial ya avisa. */}
      {first.isError && !history.isError ? (
        <p className={styles.alert} role="alert">
          {memberTabError(first.error)?.message}
        </p>
      ) : null}
      <Toolbar memberId={id} memberName={memberName} actions={actions} />
      {current || future ? (
        <div className={styles.cards}>
          {current ? <MemberMembershipCard kind="current" membership={current} today={today} actions={cardActions(current)} onFreeze={onFreeze} onCancel={onCancel} /> : null}
          {future ? <MemberMembershipCard kind="future" membership={future} today={today} actions={cardActions(future)} onFreeze={onFreeze} onCancel={onCancel} /> : null}
        </div>
      ) : (
        <p className={styles.none}>{MEMBER_NO_CURRENT}</p>
      )}
      <History list={list} history={history} />
      <FreezeModal
        membership={freezing}
        onClose={() => {
          setFreezing(null);
        }}
        onFrozen={(_target, endDate) => {
          setFreezing(null);
          setNotice({ kind: "frozen", plan: freezing?.plan_name ?? "", endDate });
        }}
      />
      <CancelMembershipModal
        membership={cancelling}
        onClose={() => {
          setCancelling(null);
        }}
        onCancelled={() => {
          setCancelling(null);
          setNotice({ kind: "cancelled", plan: cancelling?.plan_name ?? "" });
        }}
      />
    </div>
  );
}
