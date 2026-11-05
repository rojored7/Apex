// S5-F2 · US-130 (front): /avisos/historial (Notif_Historial.html), admin y coach. Cada intento es una fila.
// - FilterBar: Socio (búsqueda en memoria, nunca en la URL, S2-D41), Desde y Hasta, Regla, Canal y Resultado
//   (en la URL como `from`, `to`, `rule_id`, `channel` y `status`); lo inválido no viaja (historyFilters).
// - DataTable paginada en el servidor (25, 50 y 100) con "Ver mensaje" (MessagePanel). Estados: carga,
//   vacío con y sin filtros, fuera de rango, error con Reintentar, 403 y 429.
// DESIGN-GAP:
// - Notif_Historial.html trae cuatro tarjetas de los últimos 30 días y "Exportar": el api no tiene resumen
//   ni exportación de avisos en v0.2.
// - "Detalle del proveedor" ("201 · endpoint ok", "Brevo · 250"): el aviso solo guarda un `last_error` de
//   un conjunto cerrado; se muestra ese motivo en palabras. Tampoco hay push ni Telegram para el socio.
// - "Quién" dice "Equipo" o "sistema": el aviso guarda el id de la cuenta y no su nombre; un aviso omitido
//   no guarda quién lo omitió.
// - El filtro por socio busca por nombre (`q`); el diseño no lo filtra por ficha.
// - "Pasó a WhatsApp" y "Ver" de un omitido: el historial solo ofrece "Ver mensaje".
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { formatDateTime } from "../../../core/i18n/format";
import { useListParams } from "../../../shared/hooks/useListParams";
import { memberHref } from "../../../shared/lib/routes";
import { Button } from "../../../shared/ui/Button";
import { cx } from "../../../shared/ui/cx";
import { DataTable, type Column } from "../../../shared/ui/DataTable";
import { FilterBar, type DateRange, type FilterOption } from "../../../shared/ui/FilterBar";
import { PageHeader, type PageAction } from "../../../shared/ui/PageHeader";
import { Pagination } from "../../../shared/ui/Pagination";
import { useHistory, useRuleOptions } from "../adminApi";
import { historyError } from "../adminErrors";
import { CHANNEL_LABELS, HISTORY_FILTERS, STATUS_LABELS, type HistoryFilter } from "../adminSchemas";
import { MessagePanel } from "../components/MessagePanel";
import { hasHistoryFilters, readHistoryFilters, toHistoryParams } from "../historyFilters";
import { detailText, whenOf, whoText } from "../historyView";
import { NOTIFICATION_CHANNELS, NOTIFICATION_STATUSES, type NotificationRowView } from "../schemas";
import styles from "./HistoryPage.module.css";

export const HISTORY_EMPTY = "Todavía no hay envíos. Cuando el sistema genere avisos aparecerán aquí.";
export const HISTORY_EMPTY_FILTERED = "No hay envíos con estos filtros. Prueba con otro rango o limpia los filtros.";
export const HISTORY_PAST_END = "Esta página ya no tiene envíos.";

const HEADER_ACTIONS: PageAction[] = [{ id: "rules", label: "Reglas y plantillas", href: "/avisos/reglas" }];

const STATUS_ORDER = ["sent", "failed", "pending", "skipped"] as const satisfies readonly (typeof NOTIFICATION_STATUSES)[number][];
const STATUS_OPTIONS: FilterOption[] = STATUS_ORDER.map((value) => ({ value, label: STATUS_LABELS[value] }));
const CHANNEL_OPTIONS: FilterOption[] = NOTIFICATION_CHANNELS.map((value) => ({ value, label: CHANNEL_LABELS[value] }));
const SELECTS = ["rule_id", "channel", "status"] as const;
const isSelect = (name: string): name is (typeof SELECTS)[number] => (SELECTS as readonly string[]).includes(name);

export default function HistoryPage() {
  const list = useListParams<HistoryFilter>({ filters: HISTORY_FILTERS, localQuery: true });
  const { limit, offset } = list.params;
  const { q, setFilter } = list;
  const filters = useMemo(() => readHistoryFilters(list.filters), [list.filters]);
  const params = useMemo(() => toHistoryParams({ limit, offset }, q, filters), [limit, offset, q, filters]);
  const history = useHistory(params);
  const rules = useRuleOptions();
  const [viewing, setViewing] = useState<NotificationRowView | null>(null);
  const page = history.data;
  const settled = history.isPlaceholderData ? undefined : page;
  const isFiltered = hasHistoryFilters(filters, q);
  const isPastEnd = settled !== undefined && settled.total > 0 && settled.items.length === 0;
  const ruleNames = useMemo(() => new Map((rules.data?.items ?? []).map((rule) => [rule.id, rule.name])), [rules.data]);
  const ruleOptions: FilterOption[] = (rules.data?.items ?? []).map((rule) => ({ value: rule.id, label: rule.name }));

  const setRange = (range: DateRange): void => {
    // FilterBar avisa el rango completo; solo cambia una fecha a la vez (dos navegaciones seguidas se pisarían).
    if (range.from !== filters.from) setFilter("from", range.from || undefined);
    else if (range.to !== filters.to) setFilter("to", range.to || undefined);
  };

  const columns: Column<NotificationRowView>[] = [
    { key: "when", header: "Fecha y hora", render: (row) => formatDateTime(whenOf(row)) },
    {
      key: "member",
      header: "Socio",
      render: (row) => (
        <Link to={memberHref(row.member_id)} className={styles.link}>
          {row.member_name}
        </Link>
      ),
    },
    { key: "rule", header: "Regla", render: (row) => ruleNames.get(row.rule_id) ?? "—" },
    { key: "channel", header: "Canal", render: (row) => CHANNEL_LABELS[row.channel] },
    { key: "status", header: "Resultado", render: (row) => <span className={cx(styles.tag, row.status === "sent" && styles.ok)}>{STATUS_LABELS[row.status]}</span> },
    { key: "detail", header: "Detalle", render: (row) => detailText(row) },
    { key: "who", header: "Quién", render: (row) => whoText(row) },
    {
      key: "actions",
      header: "Acción",
      align: "end",
      wide: true,
      render: (row) => (
        <Button
          variant="ghost"
          aria-label={`Ver mensaje de ${row.member_name}`}
          onClick={() => {
            setViewing(row);
          }}
        >
          Ver mensaje
        </Button>
      ),
    },
  ];

  return (
    <div className={styles.page}>
      <PageHeader title="Historial de envíos" {...(settled ? { total: `${String(settled.total)} en total` } : {})} actions={HEADER_ACTIONS} />
      <FilterBar
        query={q}
        onQueryChange={list.setQuery}
        onClear={list.clear}
        searchLabel="Socio"
        searchPlaceholder="Nombre"
        dateRange={{ label: "Fecha del aviso", from: filters.from, to: filters.to, onChange: setRange }}
        selects={[
          { name: "rule_id", label: "Regla", value: filters.rule_id, options: ruleOptions, anyLabel: "Todas" },
          { name: "channel", label: "Canal", value: filters.channel, options: CHANNEL_OPTIONS, anyLabel: "Todos" },
          { name: "status", label: "Resultado", value: filters.status, options: STATUS_OPTIONS, anyLabel: "Todos" },
        ]}
        onSelectChange={(name, value) => {
          if (isSelect(name)) setFilter(name, value || undefined);
        }}
      />
      <DataTable
        caption="Historial de envíos"
        columns={columns}
        rows={settled?.items}
        total={settled?.total}
        limit={limit}
        rowKey={(row) => row.id}
        isLoading={history.isLoading || history.isPlaceholderData}
        error={historyError(history.error)}
        onRetry={() => {
          void history.refetch();
        }}
        emptyMessage={isPastEnd ? HISTORY_PAST_END : isFiltered ? HISTORY_EMPTY_FILTERED : HISTORY_EMPTY}
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
          ) : null
        }
      />
      {settled && settled.total > 0 ? <Pagination total={settled.total} limit={limit} offset={offset} onPageChange={list.setPage} onLimitChange={list.setLimit} /> : null}
      <p className={styles.note}>Cada intento es una fila: un mismo aviso puede tener un correo fallido y un WhatsApp enviado. Esta misma tabla, filtrada por socio, es la pestaña «Avisos» de su ficha.</p>
      <MessagePanel
        notification={viewing}
        onClose={() => {
          setViewing(null);
        }}
      />
    </div>
  );
}
